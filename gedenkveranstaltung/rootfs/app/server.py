"""Anmeldeseite fuer eine Gedenkveranstaltung, als Home-Assistant-Add-on.

Zwei Server im selben Prozess:
  * PUBLIC_PORT  - die oeffentliche Anmeldeseite (im config.yaml nach aussen gemappt)
  * INGRESS_PORT - die Verwaltung, nur ueber Home Assistant Ingress erreichbar
"""

import csv
import io
import ipaddress
import json
import os
import re
import secrets
import smtplib
import ssl
import threading
from email.message import EmailMessage
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

# Im Add-on immer 8080/8099. Die Variablen gibt es nur, damit sich zum Testen
# ein zweiter Server neben dem ersten starten laesst.
PUBLIC_PORT = int(os.environ.get("ANMELDUNG_PORT", "8080"))
INGRESS_PORT = int(os.environ.get("ANMELDUNG_INGRESS_PORT", "8099"))

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
    "ablauf": "",
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
    "benachrichtigung_schwellen": "",
    "oeffentliche_adresse": "",
    "impressum": "",
    "datenschutz": "",
    "email_abfragen": True,
    "smtp_server": "",
    "smtp_port": 587,
    "smtp_verschluesselung": "starttls",
    "smtp_benutzer": "",
    "smtp_passwort": "",
    "smtp_absender": "",
    "smtp_antwort_an": "",
    "loeschfrist": "4 Wochen",
    "nur_fuer_ip": "",
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


def aktive(anmeldungen):
    """Alle Anmeldungen ausser den abgesagten."""
    return [a for a in anmeldungen if not a.get("abgesagt")]


def belegte_plaetze(daten, ausser=None):
    """Belegte Plaetze. Abgesagte zaehlen nicht mit; mit "ausser" laesst sich
    zusaetzlich eine Anmeldung aussparen - beim Aendern soll die eigene
    Personenzahl den eigenen Platz nicht blockieren."""
    return sum(
        int(a.get("personen", 0))
        for a in aktive(daten["anmeldungen"])
        if a.get("id") != ausser
    )


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
        "ablauf": ablauf_punkte(opt.get("ablauf")),
        "daten": daten,
        "belegt": belegt,
        "frei": frei,
        "gesamt": opt["plaetze_gesamt"],
        "offen": offen,
        "ausgebucht": frei <= 0,
        "manuell_geschlossen": bool(daten["geschlossen"]),
    }


# Trennt vor jedem neuen Punkt: eine kurze Angabe ohne Leerzeichen, gefolgt
# von einem senkrechten Strich - also "10:00 |" ebenso wie "anschl. |".
ZEIT_AM_ANFANG = re.compile(r"\s+(?=[^\s|]{1,14}\s*\|)")
YAML_KOPF = re.compile(r"^\s*ablauf\s*:\s*(?:\|-?|>-?)?\s*", re.IGNORECASE)


def ablauf_punkte(text):
    """Der Ablauf aus den Optionen: eine Zeile je Punkt, Uhrzeit und Text durch
    einen senkrechten Strich getrennt ("9:30 | Empfang").

    Das Feld in der Add-on-Oberflaeche ist einzeilig. Wer mehrere Punkte
    hineinkopiert, hat sie am Ende hintereinander stehen - und oft noch den
    YAML-Kopf "ablauf: |-" davor. Beides wird hier aufgeraeumt, damit die
    Seite nicht wegen eines Kopierfehlers Unsinn anzeigt.
    """
    roh = YAML_KOPF.sub("", (text or "").strip())
    punkte = []
    for zeile in roh.splitlines():
        for stueck in ZEIT_AM_ANFANG.split(zeile):
            stueck = stueck.strip().lstrip("-").strip()
            if not stueck:
                continue
            zeit, strich, beschreibung = stueck.partition("|")
            if strich:
                punkte.append({"zeit": zeit.strip(), "text": beschreibung.strip()})
            else:
                punkte.append({"zeit": "", "text": stueck})
    return punkte


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


def _an_supervisor(pfad, nutzlast, leise=False):
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
    except urllib.error.HTTPError as fehler:
        # Home Assistant schreibt den Grund in den Rumpf - ohne den ist ein
        # "400 Bad Request" im Log wertlos.
        try:
            grund = fehler.read().decode("utf-8", "replace").strip()[:300]
        except OSError:
            grund = ""
        if not leise:
            print(f"[anmeldung] {pfad} fehlgeschlagen: {fehler} {grund}", flush=True)
        return False
    except (urllib.error.URLError, OSError) as fehler:
        if not leise:
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
    """Schickt eine Nachricht ueber den in den Optionen hinterlegten Dienst.

    Erlaubt ist beides, was in Home Assistant "notify.irgendwas" heissen kann:
    eine klassische Aktion (notify.mobile_app_handy, persistent_notification.
    create) und eine Notify-Entitaet neuerer Installationen, die ueber
    notify.send_message angesprochen wird. Welches von beidem es ist, sieht man
    dem Namen nicht an - deshalb wird der zweite Weg nur versucht, wenn der
    erste nicht klappt.
    """
    dienst = (optionen().get("benachrichtigung_dienst") or "").strip()
    if dienst.count(".") != 1:
        return
    bereich, name = dienst.split(".")

    als_aktion = _an_supervisor(
        f"core/api/services/{bereich}/{name}",
        {"title": "Gedenkveranstaltung", "message": text},
        leise=(bereich == "notify"),
    )
    if als_aktion or bereich != "notify":
        return

    if _an_supervisor(
        "core/api/services/notify/send_message",
        {"entity_id": dienst, "message": text},
    ):
        return

    print(
        f"[anmeldung] {dienst} ist weder eine Aktion noch eine Notify-Entität. "
        "Den richtigen Namen zeigt Entwicklerwerkzeuge > Aktionen.",
        flush=True,
    )


def schwellen(opt):
    """Die Marken aus den Optionen als sortierte Zahlen. Erlaubt ist alles,
    was man dort hinschreibt: "60, 100" ebenso wie "60 100" - und eine Liste
    aus einer aelteren Fassung der Optionen."""
    roh = opt.get("benachrichtigung_schwellen") or ""
    return sorted({int(zahl) for zahl in re.findall(r"\d+", str(roh))})


EMAIL_MUSTER = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")


BETREFFE = {
    "neu": "Ihre Anmeldung: {titel}",
    "geaendert": "Ihre Anmeldung wurde geändert: {titel}",
    "abgesagt": "Ihre Absage: {titel}",
}


def bestaetigung_mailen(eintrag, art="neu"):
    """Schickt dem Gast eine Bestaetigung, wenn er eine Adresse angegeben hat
    und ein Postausgang eingerichtet ist. Scheitert der Versand, steht das im
    Log - die Anmeldung selbst ist da laengst gespeichert."""
    empfaenger = (eintrag.get("email") or "").strip()
    opt = optionen()
    server = (opt.get("smtp_server") or "").strip()
    absender = (opt.get("smtp_absender") or opt.get("smtp_benutzer") or "").strip()
    if not empfaenger or not server or not absender:
        return

    adresse = (opt.get("oeffentliche_adresse") or "").rstrip("/")
    zeilen = [f"Guten Tag {eintrag['name']},", ""]

    if art == "abgesagt":
        zeilen += [
            f"Ihre Anmeldung zur Veranstaltung „{opt['titel']}“ ist abgesagt. "
            "Ihre Plätze sind wieder frei.",
            "",
            "Falls das ein Versehen war, melden Sie sich einfach neu an"
            + (f":\n{adresse}/" if adresse else "."),
        ]
        if opt.get("kontakt"):
            zeilen += ["", f"Bei Fragen: {opt['kontakt']}"]
        _mail_abschicken(opt, empfaenger, art, zeilen)
        return

    if art == "geaendert":
        zeilen.append(
            f"Ihre Anmeldung zur Veranstaltung „{opt['titel']}“ wurde geändert. "
            "Es gilt jetzt:"
        )
    else:
        zeilen.append(
            f"vielen Dank für Ihre Anmeldung zur Veranstaltung „{opt['titel']}“."
        )
    zeilen += ["", "Ihre Angaben:", f"  Personen: {eintrag['personen']}"]

    essen = als_mengen(eintrag.get("essen"))
    if essen:
        zeilen.append("  Essen:    " + ", ".join(f"{m} {n}" for n, m in essen.items()))
    getraenke = als_liste(eintrag.get("getraenke"))
    if getraenke:
        zeilen.append("  Getränke: " + ", ".join(getraenke))
    if eintrag.get("anmerkung"):
        zeilen.append(f"  Anmerkung: {eintrag['anmerkung']}")
    zeilen.append("")
    if opt.get("datum"):
        wann = opt["datum"] + (f", ab {opt['uhrzeit']} Uhr" if opt.get("uhrzeit") else "")
        zeilen.append(f"Wann: {wann}")
    if opt.get("ort"):
        zeilen.append(f"Wo:   {opt['ort']}")
    if adresse:
        zeilen += [
            "",
            "Anmeldung ansehen:",
            f"{adresse}/danke/{eintrag['id']}",
            "",
            "Anmeldung ändern:",
            f"{adresse}/anmeldung/{eintrag['id']}/aendern",
            "",
            "Anmeldung absagen:",
            f"{adresse}/anmeldung/{eintrag['id']}/absagen",
            "",
            "Bitte behalten Sie diese Mail, solange die Veranstaltung noch",
            "aussteht - die Links gelten nur für Ihre Anmeldung.",
        ]
    if opt.get("kontakt"):
        zeilen += ["", f"Bei Fragen: {opt['kontakt']}"]
    _mail_abschicken(opt, empfaenger, art, zeilen)


def _mail_abschicken(opt, empfaenger, art, zeilen):
    server = (opt.get("smtp_server") or "").strip()
    absender = (opt.get("smtp_absender") or opt.get("smtp_benutzer") or "").strip()
    # Unterschrift: die erste Zeile des Impressums ist der Veranstalter.
    veranstalter = (opt.get("impressum") or "").strip().splitlines()
    zeilen = list(zeilen) + [
        "",
        "Mit freundlichen Grüßen",
        veranstalter[0].strip() if veranstalter else "Das Organisationsteam",
    ]

    nachricht = EmailMessage()
    nachricht["Subject"] = BETREFFE.get(art, BETREFFE["neu"]).format(titel=opt["titel"])
    nachricht["From"] = absender
    nachricht["To"] = empfaenger
    # Wenn die Absenderdomain kein Postfach hat, laufen Antworten ins Leere.
    # Antwort-an lenkt sie auf eine Adresse, die wirklich jemand liest.
    antwort_an = (opt.get("smtp_antwort_an") or "").strip()
    if antwort_an:
        nachricht["Reply-To"] = antwort_an
    nachricht.set_content("\n".join(zeilen))

    port = int(opt.get("smtp_port") or 587)
    verschluesselung = (opt.get("smtp_verschluesselung") or "starttls").lower()
    benutzer = (opt.get("smtp_benutzer") or "").strip()
    passwort = opt.get("smtp_passwort") or ""
    try:
        if verschluesselung == "ssl":
            verbindung = smtplib.SMTP_SSL(server, port, timeout=20,
                                          context=ssl.create_default_context())
        else:
            verbindung = smtplib.SMTP(server, port, timeout=20)
        with verbindung:
            if verschluesselung == "starttls":
                verbindung.starttls(context=ssl.create_default_context())
            if benutzer:
                verbindung.login(benutzer, passwort)
            verbindung.send_message(nachricht)
        print(f"[anmeldung] Mail ({art}) an {empfaenger} verschickt", flush=True)
    except (smtplib.SMTPException, OSError) as fehler:
        print(f"[anmeldung] Mail an {empfaenger} fehlgeschlagen: {fehler}", flush=True)


def _nachbereiten(arbeit):
    """Sensor, Events und Nachrichten laufen im Hintergrund - der Gast soll
    nicht warten, bis Home Assistant geantwortet hat."""
    threading.Thread(target=arbeit, daemon=True).start()


def _aenderung_melden(eintrag):
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag, "geaendert")
    ereignis_senden(
        "gedenkveranstaltung_aenderung",
        {
            "name": eintrag["name"],
            "personen": eintrag["personen"],
            "essen": eintrag.get("essen", {}),
            "getraenke": eintrag.get("getraenke", []),
            "anmerkung": eintrag.get("anmerkung", ""),
        },
    )
    if optionen().get("benachrichtigung_jede_anmeldung"):
        nachricht_senden(f"Anmeldung geändert: {_beschreibung(eintrag)}")


def _absage_melden(eintrag):
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag, "abgesagt")
    stand = lage()
    ereignis_senden(
        "gedenkveranstaltung_absage",
        {
            "name": eintrag["name"],
            "personen": eintrag["personen"],
            "freie_plaetze": stand["frei"],
        },
    )
    if optionen().get("benachrichtigung_jede_anmeldung"):
        nachricht_senden(
            f"Absage: {eintrag['name']}, {eintrag['personen']} "
            f"{'Person' if eintrag['personen'] == 1 else 'Personen'}. "
            f"Wieder {stand['frei']} von {stand['gesamt']} Plätzen frei."
        )


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


# Ingress-Pfade sehen aus wie /api/hassio_ingress/<token>. Alles andere wird
# verworfen: ein "//fremde-seite.example" im Header landete sonst in jedem
# url_for und machte aus einem redirect() eine Weiterleitung nach auswaerts.
INGRESS_PFAD = re.compile(r"/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*/?")


class IngressPfad:
    """Home Assistant schickt den Ingress-Prefix als Header mit. Ausgewertet
    wird er nur auf dem Ingress-Port - auf der oeffentlichen Seite kommt der
    Header von aussen und laesst sich frei erfinden."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_INGRESS_PATH") or ""
        if environ.get("SERVER_PORT") == str(INGRESS_PORT) and INGRESS_PFAD.fullmatch(
            prefix
        ):
            environ["SCRIPT_NAME"] = prefix.rstrip("/")
        return self.wsgi_app(environ, start_response)


app.wsgi_app = IngressPfad(app.wsgi_app)


def ueber_ingress():
    return request.environ.get("SERVER_PORT") == str(INGRESS_PORT)


def besucher_adresse():
    """Adresse des Gastes.

    Hinter dem Cloudflare-Tunnel steht in remote_addr nur der Tunnel selbst -
    die echte Adresse setzt Cloudflare als Cf-Connecting-Ip. Ohne diese
    Kopfzeile gilt schlicht, von wo die Verbindung kam.

    X-Forwarded-For wird bewusst nicht ausgewertet: waitress wirft alle
    X-Forwarded-Kopfzeilen weg, solange kein trusted_proxy eingetragen ist, und
    ihnen zu vertrauen hiesse, dass sich jeder eine beliebige Adresse ausstellen
    kann.
    """
    return (request.headers.get("Cf-Connecting-Ip") or "").strip() or (
        request.remote_addr or ""
    )


def aus_dem_haus():
    """Kam die Anfrage aus dem eigenen Netz?

    Der Watchdog des Supervisors und Aufrufe aus dem Heimnetz haben eine private
    Adresse und keine Kopfzeile von Cloudflare. Die bleiben von der Testsperre
    unberuehrt - sonst bekaeme der Watchdog dauerhaft eine 503 und startete das
    Add-on womoeglich im Kreis neu.
    """
    if (request.headers.get("Cf-Connecting-Ip") or "").strip():
        return False
    try:
        wer = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return wer.is_private or wer.is_loopback or wer.is_link_local


def adressnetze(text):
    """Die Option in Netze uebersetzen. Eine einzelne Adresse wird dabei zu
    ihrem eigenen Netz, damit beides gleich geprueft werden kann."""
    netze = []
    for teil in re.split(r"[,;\s]+", str(text or "")):
        if not teil:
            continue
        try:
            netze.append(ipaddress.ip_network(teil, strict=False))
        except ValueError:
            print(
                f"[anmeldung] nur_fuer_ip: '{teil}' ist keine Adresse und wird "
                "uebergangen",
                flush=True,
            )
    return netze


def adresse_erlaubt(adresse, netze):
    if not netze:
        return True
    try:
        wer = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    return any(wer in netz for netz in netze)


@app.before_request
def verwaltung_abschirmen():
    """Die Verwaltung ist ausschliesslich ueber Home Assistant erreichbar."""
    if request.path.startswith("/verwaltung") and not ueber_ingress():
        abort(404)


@app.before_request
def testsperre():
    """Zum Testen vor dem Aushang: die oeffentliche Seite nur fuer bestimmte
    Adressen. Die Verwaltung ueber Ingress bleibt immer offen, sonst sperrt man
    sich mit einem Tippfehler selbst aus.

    Das ist eine Testsperre, kein Schutzwall: wer das Add-on am Tunnel vorbei
    direkt erreicht, kann die Kopfzeile Cf-Connecting-Ip selbst setzen. Und wer
    aus dem Heimnetz kommt, wird gar nicht erst geprueft."""
    if ueber_ingress() or request.endpoint == "static":
        return None
    if aus_dem_haus():
        return None
    opt = optionen()
    netze = adressnetze(opt["nur_fuer_ip"])
    if not netze:
        return None
    adresse = besucher_adresse()
    if adresse_erlaubt(adresse, netze):
        return None
    print(
        f"[anmeldung] Testsperre: {adresse or 'unbekannte Adresse'} abgewiesen "
        f"({request.path})",
        flush=True,
    )
    return (
        render_template("gesperrt.html", opt=opt, adresse=adresse),
        503,
        {"Retry-After": "3600"},
    )


# Statische Dateien einen Tag lang puffern lassen - Cloudflare und die
# Browser holen CSS und Wappen dann nicht bei jedem Aufruf neu. Damit eine
# neue Fassung trotzdem sofort ankommt, haengt an jeder Adresse die
# Aenderungszeit der Datei.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400
STATIC_DIR = Path(app.static_folder)


def statisch(dateiname):
    try:
        stand = int((STATIC_DIR / dateiname).stat().st_mtime)
    except OSError:
        stand = 0
    return url_for("static", filename=dateiname, v=stand)


@app.context_processor
def vorlagen_werte():
    return {"ist_verwaltung": ueber_ingress(), "statisch": statisch}


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
        "formular.html", eingaben={}, fehler=None, eintrag=None, **stand
    )


def _suchen(daten, anmeldung_id):
    return next((a for a in daten["anmeldungen"] if a.get("id") == anmeldung_id), None)


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


def _formular_lesen(opt, frei):
    """Formular auslesen und pruefen. Gibt die Werte und - falls etwas nicht
    stimmt - eine Meldung zurueck. "frei" ist die Zahl der Plaetze, die diese
    eine Anmeldung hoechstens belegen darf."""
    werte = {
        "name": " ".join((request.form.get("name") or "").split())[:80],
        "anmerkung": (request.form.get("anmerkung") or "").strip()[:500],
        "email": (request.form.get("email") or "").strip()[:120],
        "personen": 0,
        "essen": {},
        "getraenke": _auswahl("getraenke", opt["getraenke"]),
    }
    try:
        werte["personen"] = _menge("personen")
        for i, gericht in enumerate(opt["essen"]):
            anzahl = _menge(f"essen_{i}")
            if anzahl > 0:
                werte["essen"][gericht] = anzahl
    except ValueError as problem:
        return werte, str(problem)

    personen = werte["personen"]
    stueck = sum(werte["essen"].values())
    if len(werte["name"]) < 2:
        return werte, "Bitte tragen Sie einen Namen ein."
    if personen < 1:
        return werte, "Bitte geben Sie mindestens eine Person an."
    if werte["email"] and not EMAIL_MUSTER.fullmatch(werte["email"]):
        return werte, (
            "Die E-Mail-Adresse sieht nicht vollständig aus. "
            "Bitte prüfen oder das Feld leer lassen."
        )
    if personen > opt["max_personen_pro_anmeldung"]:
        return werte, (
            "Pro Anmeldung sind höchstens "
            f"{opt['max_personen_pro_anmeldung']} Personen möglich."
        )
    if personen > frei:
        return werte, (
            f"Es sind nur noch {frei} Plätze frei. "
            "Bitte passen Sie die Personenzahl an."
        )
    if stueck > personen * 10:
        # Die Zahl sind Stueck, nicht Portionen je Person - eine Person nimmt
        # durchaus zwei Weisswuerste. Die Grenze faengt nur Zahlendreher ab.
        return werte, (
            f"Das sind {stueck} Stück für {personen} "
            f"{'Person' if personen == 1 else 'Personen'}. "
            "Bitte prüfen Sie die Zahlen noch einmal."
        )
    return werte, None


@app.post("/anmeldung")
def anmelden():
    stand = lage()
    opt = stand["opt"]

    # Honigtopf gegen einfache Bots: fuer Menschen unsichtbar, bleibt leer.
    if (request.form.get("webseite") or "").strip():
        return redirect(url_for("start"))

    if not stand["offen"]:
        return redirect(url_for("start"))

    werte, fehler = _formular_lesen(opt, stand["frei"])
    if fehler:
        return (
            render_template(
                "formular.html", fehler=fehler, eingaben=werte, eintrag=None, **stand
            ),
            400,
        )

    eintrag = dict(
        werte,
        id=secrets.token_urlsafe(9),
        zeit=datetime.now().astimezone().isoformat(timespec="seconds"),
    )

    # Zweite Pruefung unter Sperre: zwischen Anzeige und Absenden koennen
    # andere Anmeldungen die letzten Plaetze belegt haben.
    anzahl = 0
    with _lock:
        daten = _lesen()
        belegt_vorher = belegte_plaetze(daten)
        frei_jetzt = opt["plaetze_gesamt"] - belegt_vorher
        if daten["geschlossen"] or werte["personen"] > frei_jetzt:
            zu_spaet = True
        else:
            zu_spaet = False
            daten["anmeldungen"].append(eintrag)
            _schreiben(daten)
            anzahl = len(aktive(daten["anmeldungen"]))

    if zu_spaet:
        # Zwischen Anzeige und Absenden sind die letzten Plaetze weggegangen.
        # Die Startseite sagt das dann ausdruecklich, statt nur "ausgebucht".
        return redirect(url_for("start", voll=1))

    _nachbereiten(
        lambda: _melden(
            eintrag, belegt_vorher, belegt_vorher + werte["personen"], anzahl
        )
    )
    return redirect(url_for("danke", anmeldung_id=eintrag["id"]))


@app.get("/anmeldung/<anmeldung_id>/aendern")
def aendern(anmeldung_id):
    stand = lage()
    eintrag = _suchen(stand["daten"], anmeldung_id)
    if eintrag is None or eintrag.get("abgesagt"):
        return redirect(url_for("start"))
    # Die eigene Personenzahl blockiert den eigenen Platz nicht.
    stand["frei"] = stand["frei"] + eintrag["personen"]
    return render_template(
        "formular.html", eingaben=eintrag, fehler=None, eintrag=eintrag, **stand
    )


@app.post("/anmeldung/<anmeldung_id>/aendern")
def aendern_speichern(anmeldung_id):
    if (request.form.get("webseite") or "").strip():
        return redirect(url_for("start"))

    stand = lage()
    opt = stand["opt"]
    eintrag = _suchen(stand["daten"], anmeldung_id)
    if eintrag is None or eintrag.get("abgesagt"):
        return redirect(url_for("start"))

    frei_fuer_diese = opt["plaetze_gesamt"] - belegte_plaetze(
        stand["daten"], ausser=anmeldung_id
    )
    werte, fehler = _formular_lesen(opt, frei_fuer_diese)
    if fehler:
        stand["frei"] = frei_fuer_diese
        return (
            render_template(
                "formular.html",
                fehler=fehler,
                eingaben=werte,
                eintrag=eintrag,
                **stand,
            ),
            400,
        )

    with _lock:
        daten = _lesen()
        gespeichert = _suchen(daten, anmeldung_id)
        if gespeichert is None or gespeichert.get("abgesagt"):
            return redirect(url_for("start"))
        frei_jetzt = opt["plaetze_gesamt"] - belegte_plaetze(daten, ausser=anmeldung_id)
        if werte["personen"] > frei_jetzt:
            zu_spaet = True
        else:
            zu_spaet = False
            gespeichert.update(werte)
            gespeichert["geaendert"] = (
                datetime.now().astimezone().isoformat(timespec="seconds")
            )
            _schreiben(daten)
            neu = dict(gespeichert)

    if zu_spaet:
        return redirect(url_for("start", voll=1))

    _nachbereiten(lambda: _aenderung_melden(neu))
    return redirect(url_for("danke", anmeldung_id=anmeldung_id, geaendert=1))


@app.get("/anmeldung/<anmeldung_id>/absagen")
def absagen(anmeldung_id):
    stand = lage()
    eintrag = _suchen(stand["daten"], anmeldung_id)
    if eintrag is None:
        return redirect(url_for("start"))
    if eintrag.get("abgesagt"):
        return redirect(url_for("danke", anmeldung_id=anmeldung_id))
    return render_template("absagen.html", eintrag=eintrag, **stand)


@app.post("/anmeldung/<anmeldung_id>/absagen")
def absagen_bestaetigen(anmeldung_id):
    abgesagt = None
    with _lock:
        daten = _lesen()
        eintrag = _suchen(daten, anmeldung_id)
        if eintrag is not None and not eintrag.get("abgesagt"):
            eintrag["abgesagt"] = (
                datetime.now().astimezone().isoformat(timespec="seconds")
            )
            _schreiben(daten)
            abgesagt = dict(eintrag)

    if abgesagt:
        _nachbereiten(lambda: _absage_melden(abgesagt))
    return redirect(url_for("danke", anmeldung_id=anmeldung_id))


def _melden(eintrag, belegt_vorher, belegt_nachher, anzahl):
    """Sensor schreiben, Event ausloesen, Nachricht schicken, Mail an den Gast."""
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag)
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
        marken = schwellen(opt)
        erreicht = [s for s in marken if belegt_vorher < s <= belegt_nachher]
        if marken:
            # Ohne diese Zeile bleibt im Log offen, ob eine Schwelle einfach
            # noch nicht erreicht ist oder ob etwas nicht funktioniert.
            print(
                f"[anmeldung] belegte Plätze {belegt_vorher} -> {belegt_nachher}, "
                f"Schwellen {marken}, davon erreicht: {erreicht or 'keine'}",
                flush=True,
            )
        for schwelle in erreicht:
            nachricht_senden(
                f"{belegt_nachher} von {gesamt} Plätzen sind belegt "
                f"(Schwelle {schwelle} erreicht). Noch {frei} frei."
            )


@app.get("/impressum")
def impressum():
    stand = lage()
    return render_template(
        "seite.html",
        ueberschrift="Impressum",
        inhalt=stand["opt"].get("impressum") or "",
        feldname="impressum",
        **stand,
    )


@app.get("/datenschutz")
def datenschutz():
    stand = lage()
    eigener_text = (stand["opt"].get("datenschutz") or "").strip()
    if eigener_text:
        return render_template(
            "seite.html",
            ueberschrift="Datenschutz",
            inhalt=eigener_text,
            feldname="datenschutz",
            **stand,
        )
    # Ohne eigenen Text: die eingebaute Erklaerung, die genau beschreibt, was
    # dieses Add-on tut. Den Verantwortlichen holt sie aus dem Impressum.
    return render_template("datenschutz_vorlage.html", **stand)


@app.get("/danke/<anmeldung_id>")
def danke(anmeldung_id):
    stand = lage()
    # ueber _suchen, weil das auch mit Altbestaenden ohne id zurechtkommt -
    # ein direktes a["id"] warf dort einen KeyError und damit einen 500er.
    eintrag = _suchen(stand["daten"], anmeldung_id)
    if eintrag is None:
        return redirect(url_for("start"))
    return render_template("danke.html", eintrag=eintrag, **stand)


# ------------------------------- Verwaltung --------------------------------


@app.get("/verwaltung")
def verwaltung():
    stand = lage()
    alle = sorted(
        stand["daten"]["anmeldungen"], key=lambda a: a.get("zeit", ""), reverse=True
    )
    anmeldungen = aktive(alle)
    abgesagte = [a for a in alle if a.get("abgesagt")]
    essen_summe = portionen(anmeldungen, stand["opt"]["essen"])
    return render_template(
        "verwaltung.html",
        anmeldungen=anmeldungen,
        abgesagte=abgesagte,
        essen_summe=essen_summe,
        getraenke_summe=nachfrage(anmeldungen, stand["opt"]["getraenke"]),
        portionen_gesamt=sum(essen_summe.values()),
        **stand,
    )


@app.post("/verwaltung/loeschen/<anmeldung_id>")
def loeschen(anmeldung_id):
    with _lock:
        daten = _lesen()
        entfernt = _suchen(daten, anmeldung_id)
        daten["anmeldungen"] = [
            a for a in daten["anmeldungen"] if a.get("id") != anmeldung_id
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


# Excel und LibreOffice rechnen eine Zelle als Formel aus, wenn sie mit =, +,
# - oder @ beginnt. Name und Anmerkung tippen die Gaeste selbst - ein
# vorangestelltes Hochkomma macht daraus wieder gewoehnlichen Text.
CSV_FORMELZEICHEN = ("=", "+", "-", "@", "\t", "\r", "\n")


def _csv_feld(wert):
    text = "" if wert is None else str(wert)
    return "'" + text if text.startswith(CSV_FORMELZEICHEN) else text


@app.get("/verwaltung/anmeldungen.csv")
def csv_export():
    stand = lage()
    opt = stand["opt"]
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    kopf = (["Status", "Name", "Personen"] + opt["essen"] + opt["getraenke"]
            + ["Anmerkung", "E-Mail", "Eingang", "Abgesagt am"])
    schreiber.writerow(kopf)
    # Abgesagte stehen mit drin, aber deutlich als solche - so laesst sich in
    # Excel filtern und man sieht trotzdem, wer abgesprungen ist.
    for a in sorted(stand["daten"]["anmeldungen"], key=lambda x: x.get("zeit", "")):
        gewaehlt_essen = als_mengen(a.get("essen"))
        gewaehlt_trinken = als_liste(a.get("getraenke"))
        zeile = (
            ["abgesagt" if a.get("abgesagt") else "angemeldet",
             a.get("name", ""), a.get("personen", 0)]
            + [gewaehlt_essen.get(g, 0) for g in opt["essen"]]
            + ["ja" if g in gewaehlt_trinken else "" for g in opt["getraenke"]]
            + [a.get("anmerkung", ""), a.get("email", ""), a.get("zeit", ""),
               a.get("abgesagt", "")]
        )
        schreiber.writerow([_csv_feld(f) for f in zeile])
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
        # 16 Threads: die Seite rechnet fast nichts, sie wartet hoechstens auf
        # die Platte. Mehr Threads heisst mehr gleichzeitige Gaeste ohne Schlange.
        # connection_limit: waitress nimmt sonst ab 100 offenen Verbindungen
        # keine neuen mehr an - beim Lasttest mit 200 Gleichzeitigen war das
        # der einzige Engpass. Mehr offene Verbindungen kosten nur Speicher.
        kwargs={"host": "0.0.0.0", "port": PUBLIC_PORT, "threads": 16,
                "connection_limit": 500, "ident": None},
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
