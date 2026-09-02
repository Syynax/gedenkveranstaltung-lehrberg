"""Anmeldeseite fuer eine Gedenkveranstaltung, als Home-Assistant-Add-on.

Zwei Server im selben Prozess:
  * PUBLIC_PORT  - die oeffentliche Anmeldeseite (im config.yaml nach aussen gemappt)
  * INGRESS_PORT - die Verwaltung, nur ueber Home Assistant Ingress erreichbar
"""

import csv
import io
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)
from waitress import serve

PUBLIC_PORT = 8080
INGRESS_PORT = 8099

DATA_DIR = Path(os.environ.get("ANMELDUNG_DATA", "/data"))
OPTIONS_FILE = DATA_DIR / "options.json"
STORE_FILE = DATA_DIR / "anmeldungen.json"

SENSOR_ID = "sensor.gedenkveranstaltung_freie_plaetze"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
# Im Add-on immer http://supervisor; die Variable gibt es nur, damit sich der
# Weg nach Home Assistant ausserhalb testen laesst.
SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")

STANDARD_OPTIONEN = {
    "untertitel": "Gedenkveranstaltung",
    "titel": "20. Jahrestag der Gasexplosion in Lehrberg",
    "datum": "",
    "uhrzeit": "",
    "ort": "",
    "text": "",
    "plaetze_gesamt": 120,
    "max_personen_pro_anmeldung": 10,
    "anmeldeschluss": "",
    "kontakt": "",
    "essen": [],
    "getraenke": [],
    "anmeldung_offen": True,
    "datenschutz_hinweis": "Die Angaben werden nur fuer die Planung der Veranstaltung verwendet.",
    "sensor_erstellen": True,
    "benachrichtigung_dienst": "",
    "benachrichtigung_jede_anmeldung": True,
    "benachrichtigung_schwellen": [],
}


def optionen():
    """Add-on-Optionen lesen. Wird bei jedem Zugriff gelesen, damit eine
    Aenderung in Home Assistant ohne Neustart der Seite wirkt."""
    werte = dict(STANDARD_OPTIONEN)
    try:
        werte.update(json.loads(OPTIONS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    werte["essen"] = [str(x).strip() for x in werte.get("essen") or [] if str(x).strip()]
    werte["getraenke"] = [str(x).strip() for x in werte.get("getraenke") or [] if str(x).strip()]
    werte["plaetze_gesamt"] = max(1, int(werte.get("plaetze_gesamt") or 1))
    werte["max_personen_pro_anmeldung"] = max(
        1, int(werte.get("max_personen_pro_anmeldung") or 1)
    )
    return werte


# --------------------------------------------------------------------------
# Speicher
# --------------------------------------------------------------------------

_lock = threading.Lock()


def _leer():
    return {"geschlossen": False, "anmeldungen": []}


def _lesen():
    try:
        daten = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _leer()
    if not isinstance(daten, dict):
        return _leer()
    daten.setdefault("geschlossen", False)
    if not isinstance(daten.get("anmeldungen"), list):
        daten["anmeldungen"] = []
    return daten


def _schreiben(daten):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = STORE_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STORE_FILE)


def belegte_plaetze(daten):
    return sum(int(a.get("personen", 0)) for a in daten["anmeldungen"])


def lage():
    """Aktueller Stand fuer die Anzeige."""
    opt = optionen()
    with _lock:
        daten = _lesen()
    belegt = belegte_plaetze(daten)
    frei = max(0, opt["plaetze_gesamt"] - belegt)
    offen = bool(opt["anmeldung_offen"]) and not daten["geschlossen"] and frei > 0
    return {
        "opt": opt,
        "daten": daten,
        "belegt": belegt,
        "frei": frei,
        "gesamt": opt["plaetze_gesamt"],
        "offen": offen,
        "ausgebucht": frei <= 0,
        "manuell_geschlossen": bool(daten["geschlossen"]),
    }


def als_mengen(wert):
    """Das Essen einer Anmeldung als {Gericht: Anzahl}. Faengt auch Eintraege
    ab, die noch als reine Liste gespeichert wurden."""
    if isinstance(wert, dict):
        return {name: int(menge) for name, menge in wert.items() if int(menge) > 0}
    return {str(name): 1 for name in (wert or [])}


def als_liste(wert):
    """Die Getraenke-Auswahl einer Anmeldung als Liste. Faengt auch Eintraege
    ab, die noch als Mengen-Dict gespeichert wurden."""
    if isinstance(wert, dict):
        return [name for name, menge in wert.items() if menge]
    return [str(x) for x in (wert or [])]


def portionen(anmeldungen, auswahl):
    """Bestellte Portionen je Gericht."""
    ergebnis = {name: 0 for name in auswahl}
    for a in anmeldungen:
        for name, menge in als_mengen(a.get("essen")).items():
            ergebnis[name] = ergebnis.get(name, 0) + menge
    return {name: menge for name, menge in ergebnis.items() if menge > 0}


def nachfrage(anmeldungen, auswahl):
    """Wie viele Personen wollen welches Getraenk. Gezaehlt wird die ganze
    Anmeldung: wer zu dritt kommt und Helles ankreuzt, zaehlt mit drei."""
    ergebnis = {name: 0 for name in auswahl}
    for a in anmeldungen:
        for name in als_liste(a.get("getraenke")):
            ergebnis[name] = ergebnis.get(name, 0) + int(a.get("personen", 0))
    return {name: menge for name, menge in ergebnis.items() if menge > 0}


# --------------------------------------------------------------------------
# Sensor in Home Assistant
# --------------------------------------------------------------------------


def _an_supervisor(pfad, nutzlast):
    """POST an die Home-Assistant-Kernschnittstelle ueber den Supervisor.
    Schlaegt es fehl, wird das nur geloggt - eine Anmeldung darf daran nicht
    scheitern."""
    if not SUPERVISOR_TOKEN:
        return False
    anfrage = urllib.request.Request(
        f"{SUPERVISOR_URL}/{pfad}",
        data=json.dumps(nutzlast).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=10):
            return True
    except (urllib.error.URLError, OSError) as fehler:
        print(f"[anmeldung] {pfad} fehlgeschlagen: {fehler}", flush=True)
        return False


def sensor_aktualisieren():
    stand = lage()
    if not stand["opt"].get("sensor_erstellen") or not SUPERVISOR_TOKEN:
        return
    nutzlast = {
        "state": stand["frei"],
        "attributes": {
            "friendly_name": "Gedenkveranstaltung freie Plaetze",
            "unit_of_measurement": "Plätze",
            "icon": "mdi:seat",
            "plaetze_gesamt": stand["gesamt"],
            "belegte_plaetze": stand["belegt"],
            "anmeldungen": len(stand["daten"]["anmeldungen"]),
            "anmeldung_offen": stand["offen"],
            "essen": portionen(stand["daten"]["anmeldungen"], stand["opt"]["essen"]),
            "getraenke": nachfrage(
                stand["daten"]["anmeldungen"], stand["opt"]["getraenke"]
            ),
        },
    }
    _an_supervisor(f"core/api/states/{SENSOR_ID}", nutzlast)


def ereignis_senden(name, daten):
    """Loest ein Event auf dem Home-Assistant-Bus aus. Damit lassen sich
    beliebige Automatisierungen bauen."""
    _an_supervisor(f"core/api/events/{name}", daten)


def nachricht_senden(text):
    """Schickt eine Nachricht ueber den in den Optionen hinterlegten Dienst,
    z. B. notify.mobile_app_pixel oder persistent_notification.create."""
    dienst = (optionen().get("benachrichtigung_dienst") or "").strip()
    if dienst.count(".") != 1:
        return
    bereich, name = dienst.split(".")
    _an_supervisor(
        f"core/api/services/{bereich}/{name}",
        {"title": "Gedenkveranstaltung", "message": text},
    )


def _nachbereiten(arbeit):
    """Sensor, Events und Nachrichten laufen im Hintergrund - der Gast soll
    nicht warten, bis Home Assistant geantwortet hat."""
    threading.Thread(target=arbeit, daemon=True).start()


def _beschreibung(eintrag):
    teile = [f"{eintrag['name']}, {eintrag['personen']} "
             f"{'Person' if eintrag['personen'] == 1 else 'Personen'}"]
    essen = als_mengen(eintrag.get("essen"))
    if essen:
        teile.append(", ".join(f"{menge} {name}" for name, menge in essen.items()))
    getraenke = als_liste(eintrag.get("getraenke"))
    if getraenke:
        teile.append(", ".join(getraenke))
    return ". ".join(teile)


# --------------------------------------------------------------------------
# Flask
# --------------------------------------------------------------------------

app = Flask(__name__)


class IngressPfad:
    """Home Assistant schickt den Ingress-Prefix als Header mit."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_INGRESS_PATH")
        if prefix:
            environ["SCRIPT_NAME"] = prefix.rstrip("/")
        return self.wsgi_app(environ, start_response)


app.wsgi_app = IngressPfad(app.wsgi_app)


def ueber_ingress():
    return request.environ.get("SERVER_PORT") == str(INGRESS_PORT)


@app.before_request
def verwaltung_abschirmen():
    """Die Verwaltung ist ausschliesslich ueber Home Assistant erreichbar."""
    if request.path.startswith("/verwaltung") and not ueber_ingress():
        abort(404)


@app.context_processor
def vorlagen_werte():
    return {"ist_verwaltung": ueber_ingress()}


# ---------------------------- oeffentliche Seite ---------------------------


@app.get("/")
def start():
    # Ueber Ingress geoeffnet ist die Verwaltung gemeint, nicht die Besucherseite.
    if ueber_ingress():
        return redirect(url_for("verwaltung"))
    return render_template("start.html", **lage())


@app.get("/anmeldung")
def formular():
    stand = lage()
    if not stand["offen"]:
        return redirect(url_for("start"))
    return render_template(
        "formular.html", eingaben={}, fehler=None, **stand
    )


def _menge(feldname):
    """Eine Zahl aus dem Formular. Wird nicht stillschweigend zurechtgebogen -
    was nicht passt, meldet die Pruefung unten als Fehler zurueck."""
    roh = (request.form.get(feldname) or "0").strip()
    if not re.fullmatch(r"\d{0,3}", roh):
        raise ValueError("Bitte nur ganze Zahlen eintragen.")
    return int(roh or 0)


def _auswahl(feldname, erlaubt):
    """Angekreuzte Gerichte bzw. Getraenke, in der eingestellten Reihenfolge.
    Alles, was nicht in den Optionen steht, faellt raus."""
    gewaehlt = set(request.form.getlist(feldname))
    return [name for name in erlaubt if name in gewaehlt]


@app.post("/anmeldung")
def anmelden():
    stand = lage()
    opt = stand["opt"]

    # Honigtopf gegen einfache Bots: fuer Menschen unsichtbar, bleibt leer.
    if (request.form.get("webseite") or "").strip():
        return redirect(url_for("start"))

    if not stand["offen"]:
        return redirect(url_for("start"))

    name = " ".join((request.form.get("name") or "").split())[:80]
    anmerkung = (request.form.get("anmerkung") or "").strip()[:500]

    fehler = None
    personen = 0
    essen = {}
    getraenke = _auswahl("getraenke", opt["getraenke"])
    try:
        personen = _menge("personen")
        for i, gericht in enumerate(opt["essen"]):
            anzahl = _menge(f"essen_{i}")
            if anzahl > 0:
                essen[gericht] = anzahl
    except ValueError as problem:
        fehler = str(problem)

    if fehler is None:
        if len(name) < 2:
            fehler = "Bitte tragen Sie einen Namen ein."
        elif personen < 1:
            fehler = "Bitte geben Sie mindestens eine Person an."
        elif personen > opt["max_personen_pro_anmeldung"]:
            fehler = (
                "Pro Anmeldung sind höchstens "
                f"{opt['max_personen_pro_anmeldung']} Personen möglich."
            )
        elif personen > stand["frei"]:
            fehler = (
                f"Es sind nur noch {stand['frei']} Plätze frei. "
                "Bitte passen Sie die Personenzahl an."
            )
        elif sum(essen.values()) > personen * 10:
            # Die Zahl sind Stueck, nicht Portionen je Person - eine Person
            # nimmt durchaus zwei Weisswuerste. Die Grenze faengt nur
            # Zahlendreher ab.
            fehler = (
                f"Das sind {sum(essen.values())} Stück für {personen} "
                f"{'Person' if personen == 1 else 'Personen'}. "
                "Bitte prüfen Sie die Zahlen noch einmal."
            )

    if fehler:
        return (
            render_template(
                "formular.html",
                fehler=fehler,
                eingaben={
                    "name": name,
                    "personen": personen or 1,
                    "essen": essen,
                    "getraenke": getraenke,
                    "anmerkung": anmerkung,
                },
                **stand,
            ),
            400,
        )

    eintrag = {
        "id": secrets.token_urlsafe(9),
        "name": name,
        "personen": personen,
        "essen": essen,
        "getraenke": getraenke,
        "anmerkung": anmerkung,
        "zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    # Zweite Pruefung unter Sperre: zwischen Anzeige und Absenden koennen
    # andere Anmeldungen die letzten Plaetze belegt haben.
    anzahl = 0
    with _lock:
        daten = _lesen()
        belegt_vorher = belegte_plaetze(daten)
        if daten["geschlossen"] or personen > opt["plaetze_gesamt"] - belegt_vorher:
            zu_spaet = True
        else:
            zu_spaet = False
            daten["anmeldungen"].append(eintrag)
            _schreiben(daten)
            anzahl = len(daten["anmeldungen"])

    if zu_spaet:
        return redirect(url_for("start"))

    _nachbereiten(
        lambda: _melden(eintrag, belegt_vorher, belegt_vorher + personen, anzahl)
    )
    return redirect(url_for("danke", anmeldung_id=eintrag["id"]))


def _melden(eintrag, belegt_vorher, belegt_nachher, anzahl):
    """Sensor schreiben, Event ausloesen, Nachricht schicken."""
    sensor_aktualisieren()
    opt = optionen()
    gesamt = opt["plaetze_gesamt"]
    frei = max(0, gesamt - belegt_nachher)

    ereignis_senden(
        "gedenkveranstaltung_anmeldung",
        {
            "name": eintrag["name"],
            "personen": eintrag["personen"],
            "essen": eintrag["essen"],
            "getraenke": eintrag["getraenke"],
            "anmerkung": eintrag["anmerkung"],
            "anmeldungen": anzahl,
            "belegte_plaetze": belegt_nachher,
            "freie_plaetze": frei,
            "ausgebucht": frei <= 0,
        },
    )

    if opt.get("benachrichtigung_jede_anmeldung"):
        nachricht_senden(
            f"Neue Anmeldung: {_beschreibung(eintrag)}. "
            f"Noch {frei} von {gesamt} Plätzen frei."
        )

    if frei <= 0:
        nachricht_senden(
            f"Alle {gesamt} Plätze sind vergeben — die Anmeldung ist geschlossen."
        )
    else:
        for schwelle in sorted(
            int(s)
            for s in (opt.get("benachrichtigung_schwellen") or [])
            if belegt_vorher < int(s) <= belegt_nachher
        ):
            nachricht_senden(
                f"{belegt_nachher} von {gesamt} Plätzen sind belegt "
                f"(Schwelle {schwelle} erreicht). Noch {frei} frei."
            )


@app.get("/danke/<anmeldung_id>")
def danke(anmeldung_id):
    stand = lage()
    eintrag = next(
        (a for a in stand["daten"]["anmeldungen"] if a["id"] == anmeldung_id), None
    )
    if eintrag is None:
        return redirect(url_for("start"))
    return render_template("danke.html", eintrag=eintrag, **stand)


# ------------------------------- Verwaltung --------------------------------


@app.get("/verwaltung")
def verwaltung():
    stand = lage()
    anmeldungen = sorted(
        stand["daten"]["anmeldungen"], key=lambda a: a.get("zeit", ""), reverse=True
    )
    essen_summe = portionen(anmeldungen, stand["opt"]["essen"])
    return render_template(
        "verwaltung.html",
        anmeldungen=anmeldungen,
        essen_summe=essen_summe,
        getraenke_summe=nachfrage(anmeldungen, stand["opt"]["getraenke"]),
        portionen_gesamt=sum(essen_summe.values()),
        **stand,
    )


@app.post("/verwaltung/loeschen/<anmeldung_id>")
def loeschen(anmeldung_id):
    with _lock:
        daten = _lesen()
        entfernt = next(
            (a for a in daten["anmeldungen"] if a["id"] == anmeldung_id), None
        )
        daten["anmeldungen"] = [
            a for a in daten["anmeldungen"] if a["id"] != anmeldung_id
        ]
        _schreiben(daten)

    def melden():
        sensor_aktualisieren()
        if entfernt:
            ereignis_senden(
                "gedenkveranstaltung_absage",
                {"name": entfernt["name"], "personen": entfernt["personen"]},
            )

    _nachbereiten(melden)
    return redirect(url_for("verwaltung"))


@app.post("/verwaltung/umschalten")
def umschalten():
    with _lock:
        daten = _lesen()
        daten["geschlossen"] = not daten["geschlossen"]
        _schreiben(daten)
    sensor_aktualisieren()
    return redirect(url_for("verwaltung"))


@app.get("/verwaltung/anmeldungen.csv")
def csv_export():
    stand = lage()
    opt = stand["opt"]
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    kopf = ["Name", "Personen"] + opt["essen"] + opt["getraenke"] + ["Anmerkung", "Eingang"]
    schreiber.writerow(kopf)
    for a in sorted(stand["daten"]["anmeldungen"], key=lambda x: x.get("zeit", "")):
        gewaehlt_essen = als_mengen(a.get("essen"))
        gewaehlt_trinken = als_liste(a.get("getraenke"))
        schreiber.writerow(
            [a["name"], a["personen"]]
            + [gewaehlt_essen.get(g, 0) for g in opt["essen"]]
            + ["ja" if g in gewaehlt_trinken else "" for g in opt["getraenke"]]
            + [a.get("anmerkung", ""), a.get("zeit", "")]
        )
    # BOM voranstellen, damit Excel die Umlaute erkennt
    inhalt = "﻿" + puffer.getvalue()
    return Response(
        inhalt,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="anmeldungen.csv"'},
    )


# --------------------------------------------------------------------------


@app.template_filter("uhrzeit")
def uhrzeit(iso_zeit):
    try:
        return datetime.fromisoformat(iso_zeit).strftime("%d.%m., %H:%M")
    except (TypeError, ValueError):
        return ""


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sensor_aktualisieren()
    oeffentlich = threading.Thread(
        target=serve,
        args=(app,),
        kwargs={"host": "0.0.0.0", "port": PUBLIC_PORT, "threads": 8, "ident": None},
        daemon=True,
    )
    oeffentlich.start()
    print(
        f"[anmeldung] oeffentlich auf Port {PUBLIC_PORT}, "
        f"Verwaltung ueber Ingress auf Port {INGRESS_PORT}",
        flush=True,
    )
    serve(app, host="0.0.0.0", port=INGRESS_PORT, threads=4, ident=None)


if __name__ == "__main__":
    main()
