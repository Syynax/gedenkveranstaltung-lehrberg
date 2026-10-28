"""Anmeldeseite für einen Vereinsausflug, als Home-Assistant-Add-on.

Zwei Server im selben Prozess:
  * PUBLIC_PORT  - die öffentliche Anmeldeseite (im config.yaml nach außen gemappt)
  * INGRESS_PORT - die Verwaltung, nur über Home Assistant Ingress erreichbar

Gegenüber der Anmeldung zur Gedenkveranstaltung, aus der diese Seite
entstanden ist, kommen Preise und die Zahlung per PayPal dazu. Gerechnet wird
durchgehend in ganzen Cent - nie mit Kommazahlen, die beim Aufsummieren
Rundungsfehler einschleppen.
"""

import base64
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
import time
import unicodedata
from email.message import EmailMessage
from html import escape
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import segno
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from markupsafe import Markup
from waitress import serve

# Im Add-on immer 8081/8099. Die Variablen gibt es nur, damit sich zum Testen
# ein zweiter Server neben dem ersten starten lässt.
PUBLIC_PORT = int(os.environ.get("ANMELDUNG_PORT", "8081"))
INGRESS_PORT = int(os.environ.get("ANMELDUNG_INGRESS_PORT", "8099"))

DATA_DIR = Path(os.environ.get("ANMELDUNG_DATA", "/data"))
OPTIONS_FILE = DATA_DIR / "options.json"
STORE_FILE = DATA_DIR / "anmeldungen.json"

SENSOR_ID = "sensor.ausflug_freie_plaetze"
# Vorsilbe der Events auf dem Home-Assistant-Bus: ausflug_anmeldung usw.
EREIGNIS = "ausflug"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
# Im Add-on immer http://supervisor; die Variable gibt es nur, damit sich der
# Weg nach Home Assistant außerhalb testen lässt.
SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")

# Die Schnittstelle von PayPal. Welche gilt, entscheidet die Option
# paypal_modus. ANMELDUNG_PAYPAL_URL gibt es nur zum Testen gegen einen
# nachgebauten PayPal-Server - im Add-on ist sie nie gesetzt.
PAYPAL_ADRESSEN = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}
PAYPAL_TESTADRESSE = os.environ.get("ANMELDUNG_PAYPAL_URL", "").rstrip("/")
WAEHRUNG = "EUR"

STANDARD_OPTIONEN = {
    "untertitel": "Vereinsausflug",
    "titel": "Vereinsausflug der Feuerwehr Lehrberg",
    "datum": "",
    "uhrzeit": "",
    "ort": "",
    "ziel": "",
    "text": "",
    "ablauf": "",
    "plaetze_gesamt": 50,
    "max_personen_pro_anmeldung": 6,
    "anmeldeschluss": "",
    "kontakt": "",
    "essen": [],
    "getraenke": [],
    "anmeldung_offen": True,
    "datenschutz_hinweis": "Die Angaben werden nur für die Planung des Ausflugs verwendet.",
    "preis_mitglied": "15,00",
    "preis_nichtmitglied": "25,00",
    "preis_kind": "0",
    "iban": "",
    "kontoinhaber": "",
    "bic": "",
    "paypal_client_id": "",
    "paypal_secret": "",
    "paypal_modus": "sandbox",
    "paypal_me": "",
    "paypal_email": "",
    "zahlung_hinweis": "",
    "sensor_erstellen": True,
    "benachrichtigung_dienst": "",
    "benachrichtigung_jede_anmeldung": True,
    "benachrichtigung_schwellen": "",
    "oeffentliche_adresse": "",
    "impressum": "",
    "datenschutz": "",
    "veranstalter": "",
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


# --------------------------------------------------------------------------
# Geld
# --------------------------------------------------------------------------

# Ein Preis, wie man ihn in das Feld schreibt: "15", "15,5", "15,50", "15.50",
# auch mit Euro-Zeichen oder Tausenderpunkt ("1.250,00"). Mehr als zwei
# Nachkommastellen sind kein Preis, sondern ein Tippfehler.
PREIS_MUSTER = re.compile(r"(\d{1,7})(?:[.,](\d{1,2}))?")
_unlesbare_preise = set()


def preis_in_cent(text):
    """Ein Preis aus den Optionen als ganze Cent, oder None, wenn er sich
    nicht lesen lässt. Als Kommazahl wird hier nie gerechnet: Euro und Cent
    werden getrennt gelesen und als ganze Zahlen zusammengesetzt."""
    roh = str(text if text is not None else "").strip()
    roh = re.sub(r"(?i)\s*(€|eur|euro)\s*", "", roh).replace(" ", "")
    if not roh:
        return 0
    if "," in roh and "." in roh:
        # "1.250,00": Punkt als Tausendertrenner, Komma als Dezimalzeichen.
        roh = roh.replace(".", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", roh):
        # "1.250" ohne Komma ist ein Tausenderpunkt, keine 1,25 Euro.
        roh = roh.replace(".", "")
    treffer = PREIS_MUSTER.fullmatch(roh)
    if not treffer:
        return None
    euro, cent = treffer.group(1), (treffer.group(2) or "0")
    # "15,5" heißt 15,50 und nicht 15,05.
    return int(euro) * 100 + int(cent.ljust(2, "0"))


def euro(cent):
    """Ganze Cent als deutscher Betrag: 1550 -> "15,50 €"."""
    cent = int(cent or 0)
    vorzeichen = "−" if cent < 0 else ""
    cent = abs(cent)
    ganz = f"{cent // 100:,}".replace(",", ".")
    return f"{vorzeichen}{ganz},{cent % 100:02d}\u00a0€"


def euro_zahl(cent):
    """Ganze Cent als Zahl ohne Währung für die CSV: 1550 -> "15,50".
    Mit Komma, damit ein deutsches Excel damit rechnet."""
    cent = int(cent or 0)
    vorzeichen = "-" if cent < 0 else ""
    cent = abs(cent)
    return f"{vorzeichen}{cent // 100},{cent % 100:02d}"


def paypal_wert(cent):
    """Ganze Cent so, wie PayPal den Betrag erwartet: 1550 -> "15.50"."""
    cent = int(cent)
    return f"{cent // 100}.{cent % 100:02d}"


# PayPal.me-Namen bestehen nur aus Buchstaben und Ziffern.
PAYPAL_ME_MUSTER = re.compile(r"[A-Za-z0-9]+")
PAYPAL_ME_VORSATZ = re.compile(
    r"(?:https?://)?(?:www\.)?(?:paypal\.me|paypal\.com/paypalme)/", re.IGNORECASE
)


def paypal_me_lesen(roh):
    """Der Name aus der Option paypal_me. Erlaubt sind der Name allein
    ("feuerwehrlehrberg") und der Link in den üblichen Schreibweisen
    ("paypal.me/name", "https://www.paypal.me/name/"). Rückgabe: (Name, Fehler).
    Leer ist kein Fehler; alles, was kein PayPal.me-Name ist, schon - dann
    gibt es keinen Link, damit kein falsches Ziel auf der Seite steht."""
    text = str(roh or "").strip()
    if not text:
        return "", False
    text = PAYPAL_ME_VORSATZ.sub("", text, count=1)
    # Hinter dem Namen darf noch ein Betrag oder ein Schrägstrich stehen.
    name = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if PAYPAL_ME_MUSTER.fullmatch(name):
        return name, False
    return "", True


def paypal_me_link(opt, cent):
    """Der PayPal.me-Link mit vorausgefülltem Betrag, oder "" wenn die
    Variante nicht gilt oder nichts zu zahlen ist."""
    if not opt.get("paypal_me_aktiv") or int(cent or 0) <= 0:
        return ""
    return f"https://www.paypal.com/paypalme/{opt['paypal_me_name']}/{paypal_wert(cent)}{WAEHRUNG}"


# E-Mail-Adresse des PayPal-Kontos: bewusst streng. Ein @, keine Leerzeichen,
# ein Punkt in der Domain und keine Zeichen, die in einem Link etwas bedeuten.
PAYPAL_EMAIL_MUSTER = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
)


def paypal_email_lesen(roh):
    """Die Adresse aus der Option paypal_email. Rückgabe: (Adresse, Fehler).
    Leer ist kein Fehler; alles, was nicht wie eine Adresse aussieht, schon -
    dann gibt es keinen Link, damit das Geld nicht an ein falsches Ziel geht."""
    text = str(roh or "").strip()
    if not text:
        return "", False
    if len(text) <= 254 and PAYPAL_EMAIL_MUSTER.fullmatch(text):
        return text, False
    return "", True


def paypal_email_link(opt, eintrag, cent):
    """Der Bezahllink über die E-Mail-Adresse mit Betrag, Verwendungszweck und
    Anmelde-ID als Artikelnummer, oder "" wenn die Variante nicht gilt oder
    nichts zu zahlen ist. Alle Werte werden kodiert."""
    if not opt.get("paypal_email_aktiv") or int(cent or 0) <= 0:
        return ""
    parameter = [
        ("cmd", "_xclick"),
        ("business", opt["paypal_email_adresse"]),
        ("item_name", zahlung_betreff(opt, eintrag)),
        ("item_number", eintrag.get("id", "")),
        ("amount", paypal_wert(cent)),
        ("currency_code", WAEHRUNG),
        ("no_shipping", "1"),
        ("no_note", "1"),
        ("charset", "utf-8"),
    ]
    return "https://www.paypal.com/cgi-bin/webscr?" + urllib.parse.urlencode(parameter)


def zahlung_betreff(opt, eintrag):
    """Die Mitteilung, die der Gast bei PayPal angeben soll: der Titel des
    Ausflugs und der Name der Anmeldung. PayPal.me füllt nur den Betrag aus,
    die Mitteilung kann der Link nicht vorgeben."""
    return f"{opt['titel']} – {eintrag.get('name', '')}".strip(" –")


def paypal_in_cent(wert):
    """Den Betrag aus einer Antwort von PayPal ("15.50") in ganze Cent. Wer
    hier float() nimmt, bekommt bei 0.29 schon 28 Cent heraus."""
    treffer = re.fullmatch(r"(\d+)(?:\.(\d{1,2}))?", str(wert or "").strip())
    if not treffer:
        return None
    return int(treffer.group(1)) * 100 + int((treffer.group(2) or "0").ljust(2, "0"))


# --------------------------------------------------------------------------
# Überweisung per GiroCode
# --------------------------------------------------------------------------

# Der GiroCode ist ein QR-Code nach dem EPC-Standard (EPC069-12, Version 002):
# ein Text aus elf Zeilen, den die Banking-App als fertig ausgefüllte
# SEPA-Überweisung öffnet. Alles darin baut der Server - Betrag und
# Verwendungszweck kommen nie aus dem Browser.

# Aufbau einer IBAN: zwei Buchstaben (Land), zwei Prüfziffern, dann bis zu 30
# Buchstaben und Ziffern - insgesamt 15 bis 34 Zeichen.
IBAN_MUSTER = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")
# Feste Längen der Länder, in denen ein Vereinskonto am ehesten liegt. Die
# Prüfziffer allein übersieht eine verlorene Ziffer in jedem 97. Fall.
IBAN_LAENGEN = {"DE": 22, "AT": 20, "CH": 21, "LI": 21}
# BIC: 8 oder 11 Zeichen. Bei Konten im SEPA-Raum braucht der GiroCode sie nicht.
BIC_MUSTER = re.compile(r"[A-Z0-9]{8}(?:[A-Z0-9]{3})?")
# Der Standard verlangt für den Kontoinhaber höchstens 70 und für den
# Verwendungszweck höchstens 140 Zeichen, den ganzen Text in höchstens 331 Byte.
GIROCODE_NAME_MAX = 70
GIROCODE_ZWECK_MAX = 140
GIROCODE_BYTES_MAX = 331
# Höchstbetrag laut Standard: 999 999 999,99 EUR.
GIROCODE_CENT_MAX = 99_999_999_999
# Im Verwendungszweck bleiben nur Zeichen, die jede Bank im SEPA-Verkehr
# annimmt (dazu die Umlaute); alles andere wird zum Leerzeichen.
GIROCODE_UNERLAUBT = re.compile(r"[^A-Za-z0-9ÄÖÜäöüß /\-?:().,'+]")


def iban_lesen(roh):
    """Die IBAN aus der Option iban. Rückgabe: (IBAN ohne Leerzeichen in
    Großbuchstaben, Fehler). Leer ist kein Fehler; alles, was keine gültige
    IBAN ist (Aufbau, Länge, Prüfziffer nach ISO 7064 Mod 97-10), schon - dann
    gibt es keinen GiroCode, damit kein Geld auf ein falsches Konto läuft."""
    text = re.sub(r"\s+", "", str(roh or "")).upper()
    if not text:
        return "", False
    if not IBAN_MUSTER.fullmatch(text):
        return "", True
    if len(text) != IBAN_LAENGEN.get(text[:2], len(text)):
        return "", True
    # Die ersten vier Zeichen ans Ende, Buchstaben als Zahlen (A=10 ... Z=35;
    # int(zeichen, 36) liefert genau das). Eine gültige IBAN lässt dann den
    # Rest 1, wenn man die Zahl durch 97 teilt.
    umgestellt = text[4:] + text[:4]
    zahl = int("".join(str(int(zeichen, 36)) for zeichen in umgestellt))
    if zahl % 97 != 1:
        return "", True
    return text, False


def iban_gruppiert(iban):
    """Die IBAN in Vierergruppen, wie sie auf Kontoauszügen steht."""
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def bic_lesen(roh):
    """Die BIC aus der Option bic. Rückgabe: (BIC in Großbuchstaben, Fehler).
    Leer ist kein Fehler; eine unlesbare BIC wird gemeldet und ignoriert - die
    Überweisung geht auch ohne."""
    text = re.sub(r"\s+", "", str(roh or "")).upper()
    if not text:
        return "", False
    if BIC_MUSTER.fullmatch(text):
        return text, False
    return "", True


def kontoinhaber_lesen(roh):
    """Der Name des Kontoinhabers, einzeilig und auf die 70 Zeichen gekürzt,
    die der GiroCode erlaubt. Ein Zeilenumbruch darin würde die Zeilen des
    Codes verschieben."""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(roh or ""))
    return " ".join(text.split())[:GIROCODE_NAME_MAX].rstrip()


def girocode_zweck(opt, eintrag):
    """Der Verwendungszweck, so wie ihn der GiroCode verträgt: der Betreff aus
    zahlung_betreff, der Gedankenstrich als Bindestrich, Zeichen außerhalb des
    erlaubten Vorrats als Leerzeichen, höchstens 140 Zeichen. NFC zuerst, damit
    ein Umlaut aus Grundbuchstabe und Pünktchen nicht in zwei Teile zerfällt."""
    text = unicodedata.normalize("NFC", zahlung_betreff(opt, eintrag))
    text = GIROCODE_UNERLAUBT.sub(" ", text.replace("–", "-"))
    return " ".join(text.split())[:GIROCODE_ZWECK_MAX].rstrip()


def _girocode_bauen(opt, eintrag, cent):
    """(Inhalt des GiroCodes, Verwendungszweck darin) - oder ("", ""), wenn die
    Überweisung nicht eingerichtet ist oder nichts zu zahlen ist. Ist der Text
    länger als 331 Byte (Umlaute zählen doppelt), wird der Verwendungszweck
    gekürzt; er ist das Einzige, was sich kürzen lässt."""
    cent = int(cent or 0)
    if not opt.get("ueberweisung_aktiv") or not 0 < cent <= GIROCODE_CENT_MAX:
        return "", ""
    zweck = girocode_zweck(opt, eintrag)
    while True:
        inhalt = "\n".join([
            "BCD",                            # Kennung
            "002",                            # Version
            "1",                              # Zeichensatz 1 = UTF-8
            "SCT",                            # SEPA-Überweisung
            opt.get("bic") or "",             # BIC, bei SEPA-Konten leer
            opt["kontoinhaber"],              # Empfänger
            opt["iban"],                      # IBAN ohne Leerzeichen
            f"EUR{paypal_wert(cent)}",        # Betrag mit Punkt: EUR55.00
            "",                               # Purpose-Code
            "",                               # strukturierte Referenz
            zweck,                            # Verwendungszweck
        ])
        if len(inhalt.encode("utf-8")) <= GIROCODE_BYTES_MAX:
            return inhalt, zweck
        if not zweck:
            return "", ""
        zweck = zweck[:-1].rstrip()


def girocode_inhalt(opt, eintrag, cent):
    """Der Text des GiroCodes für den Betrag "cent" (der offene Betrag der
    Anmeldung): elf Zeilen, durch Zeilenumbrüche getrennt, keiner am Ende.
    Leer, wenn es nichts zu überweisen gibt."""
    return _girocode_bauen(opt, eintrag, cent)[0]


def girocode_svg(inhalt):
    """Der GiroCode als Inline-SVG für die Seite, oder "" wenn kein Inhalt da
    ist. Fehlerkorrektur M, UTF-8 ohne ECI-Kennung wie bei den gängigen
    Erzeugern, kein Micro-QR und keine stillschweigend höhere Stufe. Rand von
    vier Modulen, damit jede App den Code findet; die Größe legt das CSS fest."""
    if not inhalt:
        return Markup("")
    try:
        code = segno.make_qr(inhalt, error="m", encoding="utf-8", boost_error=False)
        svg = code.svg_inline(
            border=4, dark="#000000", light="#FFFFFF", omitsize=True,
            title="GiroCode zum Scannen mit der Banking-App",
        )
    except (ValueError, segno.DataOverflowError) as fehler:
        print(f"[anmeldung] GiroCode konnte nicht erzeugt werden: {fehler}", flush=True)
        return Markup("")
    return Markup(svg)


def ueberweisung_angaben(opt, eintrag, cent):
    """Alles, was Seite und Mail zur Überweisung zeigen - oder None, wenn
    keine eingerichtet ist oder nichts offen ist. "zweck" ist derselbe Text,
    der im GiroCode steht; wer von Hand überweist, soll ihn genauso eintragen."""
    inhalt, zweck = _girocode_bauen(opt, eintrag, cent)
    if not inhalt:
        return None
    return {
        "inhalt": inhalt,
        "empfaenger": opt["kontoinhaber"],
        "iban": opt["iban_anzeige"],
        "iban_kurz": opt["iban"],
        "betrag": euro(cent),
        "betrag_zahl": euro_zahl(cent),
        "zweck": zweck,
    }


def _preis_lesen(werte, schluessel):
    cent = preis_in_cent(werte.get(schluessel))
    if cent is None:
        roh = str(werte.get(schluessel))
        if (schluessel, roh) not in _unlesbare_preise:
            # Einmal je Schreibweise melden - optionen() läuft bei jedem Aufruf.
            _unlesbare_preise.add((schluessel, roh))
            print(
                f"[anmeldung] {schluessel}: '{roh}' ist kein lesbarer Preis. "
                "Bis zur Korrektur gilt 0 €.",
                flush=True,
            )
        werte.setdefault("preisfehler", []).append(schluessel)
        return 0
    return cent


def betrag_berechnen(mitglieder, nichtmitglieder, opt, kinder=0):
    """Der Betrag einer Anmeldung in Cent. Er entsteht nur hier, aus den
    Preisen in den Optionen - nie aus dem, was der Browser schickt."""
    return (int(mitglieder) * opt["preis_mitglied_cent"]
            + int(nichtmitglieder) * opt["preis_nichtmitglied_cent"]
            + int(kinder) * opt.get("preis_kind_cent", 0))


# Sammelknöpfe im Formular: ein Tipp legt gleich mehrere Stück dazu. In den
# Optionen steht dafür "Weißwürste | Paar" hinter dem Gericht. Der Name
# bleibt "Weißwürste" - er ist zugleich Schlüssel im Datensatz, Spalte in
# der CSV und Zeile in der Mail, daran darf sich nichts ändern.
SAMMELKNOEPFE = {
    "paar": {"name": "Paar", "schritt": 2},
    "dutzend": {"name": "Dutzend", "schritt": 12},
}
_unbekannte_knoepfe = set()


def gericht_zerlegen(eintrag):
    """Ein Eintrag der Speisenliste als (Name, Sammelknopf oder None)."""
    name, _, zusatz = str(eintrag).partition("|")
    name, zusatz = name.strip(), zusatz.strip()
    knopf = SAMMELKNOEPFE.get(zusatz.lower())
    if zusatz and not knopf and zusatz not in _unbekannte_knoepfe:
        # Einmal je Schreibweise melden - optionen() läuft bei jedem Aufruf.
        _unbekannte_knoepfe.add(zusatz)
        moeglich = ", ".join(sorted(k["name"] for k in SAMMELKNOEPFE.values()))
        print(
            f"[anmeldung] Speisen: '{zusatz}' hinter '{name}' ist kein bekannter "
            f"Sammelknopf ({moeglich}) und wird übergangen",
            flush=True,
        )
    return name, knopf


def optionen():
    """Add-on-Optionen lesen. Wird bei jedem Zugriff gelesen, damit eine
    Änderung in Home Assistant ohne Neustart der Seite wirkt."""
    werte = dict(STANDARD_OPTIONEN)
    try:
        werte.update(json.loads(OPTIONS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    gerichte = [gericht_zerlegen(x) for x in werte.get("essen") or []]
    werte["essen"] = [name for name, _ in gerichte if name]
    werte["essen_knoepfe"] = {
        name: knopf for name, knopf in gerichte if name and knopf
    }
    werte["getraenke"] = [str(x).strip() for x in werte.get("getraenke") or [] if str(x).strip()]
    werte["preisfehler"] = []
    werte["preis_mitglied_cent"] = _preis_lesen(werte, "preis_mitglied")
    werte["preis_nichtmitglied_cent"] = _preis_lesen(werte, "preis_nichtmitglied")
    # Kinder bis 14 Jahre fahren normalerweise kostenlos mit; leer heißt 0.
    if not str(werte.get("preis_kind") or "").strip():
        werte["preis_kind"] = "0"
    werte["preis_kind_cent"] = _preis_lesen(werte, "preis_kind")
    # Überweisung per GiroCode. Ohne gültige IBAN und ohne Kontoinhaber gibt es
    # sie nicht; beides wird in der Verwaltung gemeldet, statt stillschweigend
    # zu fehlen. Der Kontoinhaber ist Pflicht, weil der GiroCode ihn verlangt.
    iban_eingetragen = bool(str(werte.get("iban") or "").strip())
    werte["iban"], werte["iban_fehler"] = iban_lesen(werte.get("iban"))
    werte["iban_anzeige"] = iban_gruppiert(werte["iban"])
    werte["kontoinhaber"] = kontoinhaber_lesen(werte.get("kontoinhaber"))
    werte["kontoinhaber_fehlt"] = iban_eingetragen and not werte["kontoinhaber"]
    werte["bic"], werte["bic_fehler"] = bic_lesen(werte.get("bic"))
    werte["ueberweisung_aktiv"] = bool(werte["iban"] and werte["kontoinhaber"])
    werte["paypal_client_id"] = (werte.get("paypal_client_id") or "").strip()
    # Ein Leerzeichen am Rand rutscht beim Einfügen leicht mit und führt bei
    # PayPal zu "invalid_client", ohne dass man dem Feld etwas ansieht.
    werte["paypal_secret"] = (werte.get("paypal_secret") or "").strip()
    werte["paypal_modus"] = "live" if werte.get("paypal_modus") == "live" else "sandbox"
    werte["paypal_aktiv"] = bool(werte["paypal_client_id"] and werte["paypal_secret"])
    # PayPal.me ist die einfache Variante ohne Geschäftskonto. Der Knopf mit
    # Client-ID und Secret hat Vorrang; ein ungültiger Name wird trotzdem
    # gemeldet, damit er nicht unbemerkt liegen bleibt.
    werte["paypal_me_name"], werte["paypal_me_fehler"] = paypal_me_lesen(werte.get("paypal_me"))
    werte["paypal_me_aktiv"] = bool(werte["paypal_me_name"]) and not werte["paypal_aktiv"]
    # Dritte Variante: Link über die E-Mail-Adresse des PayPal-Kontos. Sie gilt
    # nur, wenn weder der Knopf noch PayPal.me greifen; eine ungültige Adresse
    # wird trotzdem gemeldet.
    werte["paypal_email_adresse"], werte["paypal_email_fehler"] = paypal_email_lesen(
        werte.get("paypal_email")
    )
    werte["paypal_email_aktiv"] = (
        bool(werte["paypal_email_adresse"])
        and not werte["paypal_aktiv"]
        and not werte["paypal_me_aktiv"]
    )
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
    """Alle Anmeldungen außer den abgesagten."""
    return [a for a in anmeldungen if not a.get("abgesagt")]


def belegte_plaetze(daten, ausser=None):
    """Belegte Plätze. Abgesagte zählen nicht mit; mit "ausser" lässt sich
    zusätzlich eine Anmeldung aussparen - beim Ändern soll die eigene
    Personenzahl den eigenen Platz nicht blockieren."""
    return sum(
        int(a.get("personen", 0))
        for a in aktive(daten["anmeldungen"])
        if a.get("id") != ausser
    )


# Zahlungen stehen als Liste an der Anmeldung, jede mit Art, Betrag in Cent
# und Zeitpunkt; PayPal-Zahlungen zusätzlich mit Order- und Capture-ID. Was
# bezahlt ist, ergibt sich immer aus dieser Liste - es gibt keine zweite
# Summe, die davon abweichen könnte. Arten:
#   paypal      über den Knopf auf der Bestätigungsseite
#   bar         in der Verwaltung von Hand als bezahlt markiert
#   erstattung  in der Verwaltung vermerkt, negativer Betrag
#   bar         (Name aus der Zeit vor PayPal.me, bleibt für gespeicherte Daten;
#               gemeint ist "von Hand als bezahlt markiert", auch für Zahlungen,
#               die in PayPal eingegangen sind)
ZAHLARTEN = {"paypal": "PayPal", "bar": "bar", "erstattung": "Erstattung"}


def bezahlt_cent(eintrag):
    return sum(int(z.get("betrag_cent", 0)) for z in eintrag.get("zahlungen") or [])


def soll_cent(eintrag):
    """Was diese Anmeldung kosten soll. Nach einer Absage nichts mehr."""
    if eintrag.get("abgesagt"):
        return 0
    return int(eintrag.get("betrag_cent", 0))


def zahlstand(eintrag):
    """Alles, was Seite, Mail, Verwaltung und CSV über das Geld einer
    Anmeldung wissen müssen, an einer Stelle gerechnet."""
    betrag = int(eintrag.get("betrag_cent", 0))
    soll = soll_cent(eintrag)
    bezahlt = bezahlt_cent(eintrag)
    offen = max(0, soll - bezahlt)
    if betrag <= 0 and bezahlt <= 0:
        stand = "frei"
    elif eintrag.get("abgesagt"):
        # Nichts mehr zu zahlen - aber auch nicht "bezahlt". Was schon
        # gezahlt war, steht unter "zuviel".
        stand = "abgesagt"
    elif offen <= 0:
        stand = "bezahlt"
    elif bezahlt > 0:
        stand = "teilweise"
    else:
        stand = "offen"
    zahlungen = eintrag.get("zahlungen") or []
    return {
        "betrag": betrag,
        "bezahlt": bezahlt,
        "offen": offen,
        # Zu viel bezahlt - nach einer Änderung nach unten oder einer Absage.
        # Erstattet wird von Hand; die Verwaltung zeigt den Betrag an.
        "zuviel": max(0, bezahlt - soll),
        "stand": stand,
        "bar": any(z.get("art") == "bar" for z in zahlungen),
        "zahlungen": zahlungen,
    }


def geldsummen(anmeldungen):
    """Summen für die Verwaltung und den Sensor, in Cent. Erwartet und offen
    zählen nur aktive Anmeldungen; eingegangen ist alles, was tatsächlich
    gezahlt wurde, auch von inzwischen Abgesagten."""
    je_anmeldung = [zahlstand(a) for a in anmeldungen]
    aktiv = [s for a, s in zip(anmeldungen, je_anmeldung) if not a.get("abgesagt")]
    return {
        "erwartet": sum(s["betrag"] for s in aktiv),
        "eingegangen": sum(s["bezahlt"] for s in je_anmeldung),
        "offen": sum(s["offen"] for s in aktiv),
        "zuviel": sum(s["zuviel"] for s in je_anmeldung),
        "bezahlt_anzahl": sum(1 for s in aktiv if s["stand"] == "bezahlt"),
    }


def lage():
    """Aktueller Stand für die Anzeige."""
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


# Was als Uhrzeit gilt. Bewusst eng: früher war es jedes kurze Wort vor einem
# Strich, und dann stand "Andacht" in der Zeitspalte.
ZEITANGABE = r"(?:(?:ca\.|ab|gegen)\s*)?\d{1,2}[:.]\d{2}(?:\s*Uhr)?|anschl\.|anschließend|danach"
NUR_ZEIT = re.compile(
    rf"(?:(?:Beginn|Start|Uhrzeit)\s*:?\s*)?({ZEITANGABE})", re.IGNORECASE
)
ZEIT_AM_ENDE = re.compile(rf"(.*\S)\s+({ZEITANGABE})", re.IGNORECASE)
YAML_KOPF = re.compile(r"^\s*ablauf\s*:\s*(?:\|-?|>-?)?\s*", re.IGNORECASE)


def ablauf_punkte(text):
    """Der Ablauf aus den Optionen.

    Punkte werden durch einen senkrechten Strich, ein Semikolon oder eine neue
    Zeile getrennt. Steht zwischen zwei Trennern nur eine Uhrzeit, gehört sie
    zum folgenden Punkt: "Beginn 9:30 | Andacht | Vortrag" ergibt Andacht mit
    9:30 und Vortrag ohne Zeit. Die ältere Schreibweise mit der Zeit direkt
    vor dem Strich ("9:30 | Andacht 10:00 | Vortrag") liest sich genauso.

    Das Feld in der Add-on-Oberfläche ist einzeilig, und oft kommt beim
    Kopieren der YAML-Kopf "ablauf: |-" mit. Beides wird hier aufgeräumt.
    """
    roh = YAML_KOPF.sub("", (text or "").strip())
    stuecke = [s.strip().lstrip("-").strip() for s in re.split(r"[|;\n]", roh)]
    stuecke = [s for s in stuecke if s]

    punkte = []
    zeit = ""
    for i, stueck in enumerate(stuecke):
        nur = NUR_ZEIT.fullmatch(stueck)
        if nur:
            zeit = nur.group(1)
            continue
        folgt_noch = i + 1 < len(stuecke)
        am_ende = ZEIT_AM_ENDE.fullmatch(stueck) if folgt_noch else None
        if am_ende:
            # "Andacht 10:00 | Vortrag": die Zeit gehört schon zum Vortrag.
            punkte.append({"zeit": zeit, "text": am_ende.group(1)})
            zeit = am_ende.group(2)
        else:
            punkte.append({"zeit": zeit, "text": stueck})
            zeit = ""
    if zeit:
        punkte.append({"zeit": zeit, "text": ""})
    return punkte


def als_mengen(wert):
    """Das Essen einer Anmeldung als {Gericht: Anzahl}. Fängt auch Einträge
    ab, die noch als reine Liste gespeichert wurden."""
    if isinstance(wert, dict):
        return {name: int(menge) for name, menge in wert.items() if int(menge) > 0}
    return {str(name): 1 for name in (wert or [])}


def als_liste(wert):
    """Die Getränke-Auswahl einer Anmeldung als Liste. Fängt auch Einträge
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
    """Wie viele Personen wollen welches Getränk. Gezählt wird die ganze
    Anmeldung: wer zu dritt kommt und Helles ankreuzt, zählt mit drei."""
    ergebnis = {name: 0 for name in auswahl}
    for a in anmeldungen:
        for name in als_liste(a.get("getraenke")):
            ergebnis[name] = ergebnis.get(name, 0) + int(a.get("personen", 0))
    return {name: menge for name, menge in ergebnis.items() if menge > 0}


# --------------------------------------------------------------------------
# Sensor in Home Assistant
# --------------------------------------------------------------------------


def _an_supervisor(pfad, nutzlast, leise=False):
    """POST an die Home-Assistant-Kernschnittstelle über den Supervisor.
    Schlägt es fehl, wird das nur geloggt - eine Anmeldung darf daran nicht
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
    alle = stand["daten"]["anmeldungen"]
    angemeldet = aktive(alle)
    geld = geldsummen(alle)
    nutzlast = {
        "state": stand["frei"],
        "attributes": {
            "friendly_name": "Ausflug freie Plätze",
            "unit_of_measurement": "Plätze",
            "icon": "mdi:bus",
            "plaetze_gesamt": stand["gesamt"],
            "belegte_plaetze": stand["belegt"],
            "anmeldungen": len(angemeldet),
            "mitglieder": sum(int(a.get("mitglieder", 0)) for a in angemeldet),
            "nichtmitglieder": sum(int(a.get("nichtmitglieder", 0)) for a in angemeldet),
            "kinder": sum(int(a.get("kinder", 0)) for a in angemeldet),
            "anmeldung_offen": stand["offen"],
            # Euro mit zwei Nachkommastellen, für Karten und Automatisierungen.
            # Gerechnet wurde vorher in Cent; geteilt wird erst ganz am Schluss.
            "summe_erwartet": round(geld["erwartet"] / 100, 2),
            "summe_eingegangen": round(geld["eingegangen"] / 100, 2),
            "summe_offen": round(geld["offen"] / 100, 2),
            "summe_zu_erstatten": round(geld["zuviel"] / 100, 2),
            "anmeldungen_bezahlt": geld["bezahlt_anzahl"],
            "essen": portionen(angemeldet, stand["opt"]["essen"]),
            "getraenke": nachfrage(angemeldet, stand["opt"]["getraenke"]),
        },
    }
    _an_supervisor(f"core/api/states/{SENSOR_ID}", nutzlast)


def ereignis_senden(name, daten):
    """Löst ein Event auf dem Home-Assistant-Bus aus. Damit lassen sich
    beliebige Automatisierungen bauen."""
    _an_supervisor(f"core/api/events/{name}", daten)


def nachricht_senden(text):
    """Schickt eine Nachricht über den in den Optionen hinterlegten Dienst.

    Erlaubt ist beides, was in Home Assistant "notify.irgendwas" heißen kann:
    eine klassische Aktion (notify.mobile_app_handy, persistent_notification.
    create) und eine Notify-Entität neuerer Installationen, die über
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
        {"title": "Ausflug", "message": text},
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
    aus einer älteren Fassung der Optionen."""
    roh = opt.get("benachrichtigung_schwellen") or ""
    return sorted({int(zahl) for zahl in re.findall(r"\d+", str(roh))})


EMAIL_MUSTER = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")


BETREFFE = {
    "neu": "Ihre Anmeldung: {titel}",
    "geaendert": "Ihre Anmeldung wurde geändert: {titel}",
    "abgesagt": "Ihre Absage: {titel}",
    "bezahlt": "Zahlung erhalten: {titel}",
}


def personen_text(eintrag):
    """"3 Personen (2 Mitglieder, 1 Nichtmitglied)" - für Mail, Seite und
    Nachrichten. Steht nur eine Gruppe drin, fällt die Klammer weg. Kinder
    bis 14 Jahre stehen als eigene Gruppe dabei; ältere Anmeldungen haben
    das Feld nicht und zählen dann 0 Kinder."""
    mitglieder = int(eintrag.get("mitglieder", 0))
    nicht = int(eintrag.get("nichtmitglieder", 0))
    kinder = int(eintrag.get("kinder", 0))
    personen = int(eintrag.get("personen", mitglieder + nicht + kinder))
    gruppen = []
    if mitglieder:
        gruppen.append(f"{mitglieder} {'Mitglied' if mitglieder == 1 else 'Mitglieder'}")
    if nicht:
        gruppen.append(f"{nicht} {'Nichtmitglied' if nicht == 1 else 'Nichtmitglieder'}")
    if kinder:
        gruppen.append(f"{kinder} {'Kind' if kinder == 1 else 'Kinder'}")
    text = f"{personen} {'Person' if personen == 1 else 'Personen'}"
    if len(gruppen) > 1:
        text += f" ({', '.join(gruppen)})"
    elif gruppen:
        text = gruppen[0]
    return text


def preis_aufstellung(eintrag):
    """"2 × 15,00 € + 1 × 25,00 €" aus den Preisen, die beim Speichern der
    Anmeldung galten - nicht aus den heutigen Optionen."""
    teile = []
    for anzahl, preis in (
        (eintrag.get("mitglieder", 0), eintrag.get("preis_mitglied_cent", 0)),
        (eintrag.get("nichtmitglieder", 0), eintrag.get("preis_nichtmitglied_cent", 0)),
        (eintrag.get("kinder", 0), eintrag.get("preis_kind_cent", 0)),
    ):
        # Kostenlose Kinder tauchen in der Rechnung nicht als "× 0,00 €" auf;
        # in der Mail stehen sie in einer eigenen Zeile.
        if int(anzahl) and int(preis):
            teile.append(f"{int(anzahl)} × {euro(preis)}")
    return " + ".join(teile)


def zahlung_text(stand):
    """Der Zahlungsstand in einem Satzteil."""
    if stand["stand"] == "bezahlt":
        return f"bezahlt ({euro(stand['bezahlt'])})"
    if stand["stand"] == "teilweise":
        return f"{euro(stand['bezahlt'])} bezahlt, offen {euro(stand['offen'])}"
    if stand["stand"] == "offen":
        return f"offen ({euro(stand['offen'])})"
    if stand["stand"] == "abgesagt":
        if stand["zuviel"] > 0:
            return f"abgesagt, {euro(stand['zuviel'])} zu erstatten"
        return "abgesagt, nichts zu zahlen"
    return "nichts zu zahlen"


def veranstalter_name(opt):
    """Der Name unter der Mail.

    Früher stand hier die erste Zeile des Impressums. Das Feld in der
    Add-on-Oberfläche ist aber einzeilig, also war "die erste Zeile" das ganze
    Impressum samt Haftungsausschluss - und genau so stand es unter jeder Mail.
    Jetzt gibt es ein eigenes Feld; das Impressum ist nur noch der Rückfall,
    und auch dort zählt nur der erste Abschnitt, und der nur, solange er kurz
    genug ist, um ein Name zu sein.
    """
    name = (opt.get("veranstalter") or "").strip()
    if name:
        return name
    teile = [t for t in zeilen(opt.get("impressum")).splitlines() if t]
    if teile and len(teile[0]) <= 60:
        return teile[0]
    return "Das Organisationsteam"


def _mail_inhalt(opt, eintrag, art, adresse):
    """Der Inhalt der Bestätigung, einmal gebaut und noch ohne Darstellung.
    Text- und HTML-Fassung lesen dasselbe, damit sie nicht auseinanderlaufen."""
    titel = opt["titel"]
    stand = zahlstand(eintrag)
    inhalt = {
        "anrede": f"Guten Tag {eintrag['name']},",
        "absaetze": [],
        "angaben": [],
        "termin": [],
        "links": [],
        "links_titel": "Ihre Anmeldung",
        "hinweis": "",
        "kontakt": (opt.get("kontakt") or "").strip(),
        "veranstalter": veranstalter_name(opt),
    }

    if art == "abgesagt":
        inhalt["absaetze"] = [
            f"Ihre Anmeldung zu „{titel}“ ist abgesagt. "
            "Ihre Plätze sind wieder frei.",
        ]
        if stand["zuviel"] > 0:
            # Keine automatische Erstattung: Das Geld zurückzuschicken ist
            # Sache der Orga, die Verwaltung zeigt ihr den Betrag an.
            inhalt["absaetze"].append(
                f"Sie hatten bereits {euro(stand['bezahlt'])} bezahlt. Um die "
                "Erstattung kümmert sich das Organisationsteam."
            )
        inhalt["absaetze"].append(
            "War das ein Versehen? Dann melden Sie sich einfach neu an."
        )
        if adresse:
            inhalt["links_titel"] = "Erneut anmelden"
            inhalt["links"] = [("Zur Anmeldeseite", adresse + "/")]
        return inhalt

    if art == "bezahlt":
        inhalt["absaetze"].append(
            f"vielen Dank, Ihre Zahlung für „{titel}“ ist bei uns eingegangen."
        )
    elif art == "geaendert":
        inhalt["absaetze"].append(
            f"Ihre Anmeldung zu „{titel}“ wurde geändert. Es gilt jetzt:"
        )
    else:
        inhalt["absaetze"].append(
            f"vielen Dank für Ihre Anmeldung zu „{titel}“. Wir freuen uns, "
            "dass Sie mitfahren."
        )

    bezahlen_moeglich = stand["offen"] > 0 and opt.get("paypal_aktiv")
    me_link = paypal_me_link(opt, stand["offen"])
    email_link = paypal_email_link(opt, eintrag, stand["offen"])
    ueberweisung_da = ueberweisung_angaben(opt, eintrag, stand["offen"])
    paypal_absatz = ""
    if stand["offen"] > 0:
        if email_link:
            paypal_absatz = (
                f"Offen sind noch {euro(stand['offen'])}. Bezahlen können Sie "
                "über den PayPal-Link unten; Betrag und Verwendungszweck sind "
                "dort schon eingetragen."
            )
        elif me_link:
            paypal_absatz = (
                f"Offen sind noch {euro(stand['offen'])}. Bezahlen können Sie "
                "über den PayPal-Link unten; der Betrag ist dort schon "
                "eingetragen. Bitte geben Sie bei PayPal als Mitteilung an: "
                f"{zahlung_betreff(opt, eintrag)}"
            )
        elif bezahlen_moeglich and adresse:
            paypal_absatz = (
                f"Offen sind noch {euro(stand['offen'])}. Über „Jetzt bezahlen“ "
                "unten können Sie den Betrag direkt per PayPal bezahlen."
            )
        elif bezahlen_moeglich:
            paypal_absatz = (
                f"Offen sind noch {euro(stand['offen'])}. Bezahlen können Sie "
                "auf der Bestätigungsseite Ihrer Anmeldung per PayPal."
            )
        elif (opt.get("zahlung_hinweis") or "").strip() and not ueberweisung_da:
            # Der Hinweis gilt nur, solange kein Bezahlweg eingerichtet ist.
            paypal_absatz = (
                f"Offen sind noch {euro(stand['offen'])}. "
                + opt["zahlung_hinweis"].strip()
            )
    if ueberweisung_da:
        # Erst die Überweisung, dann PayPal. Der Block steht zwischen den
        # Absätzen; der Text- und der HTML-Satz setzen ihn als Angabenblock.
        if paypal_absatz:
            inhalt["absaetze"].append("Sie können wählen, wie Sie bezahlen.")
        else:
            inhalt["absaetze"].append(
                f"Offen sind noch {euro(stand['offen'])}. Bezahlen können Sie "
                "per Überweisung."
            )
        inhalt["absaetze"].append((
            "Überweisung",
            [
                ("Empfänger", ueberweisung_da["empfaenger"]),
                ("IBAN", ueberweisung_da["iban"]),
                ("Betrag", ueberweisung_da["betrag"]),
                ("Verwendungszweck", ueberweisung_da["zweck"]),
            ],
        ))
        if adresse:
            inhalt["absaetze"].append(
                "Einen QR-Code zum Scannen mit der Banking-App finden Sie auf "
                "Ihrer Anmeldeseite („Anmeldung ansehen“ unten)."
            )
    if paypal_absatz:
        inhalt["absaetze"].append(paypal_absatz)

    inhalt["angaben"].append(("Angemeldet", personen_text(eintrag)))
    kinder = int(eintrag.get("kinder", 0))
    if kinder > 0:
        preis_kind = int(eintrag.get("preis_kind_cent", 0))
        inhalt["angaben"].append((
            "Kinder bis 14 Jahre",
            f"{kinder} ({'kostenlos' if preis_kind == 0 else 'je ' + euro(preis_kind)})",
        ))
    if stand["betrag"] > 0:
        betrag = euro(stand["betrag"])
        aufstellung = preis_aufstellung(eintrag)
        if aufstellung and (int(eintrag.get("personen", 0)) > 1):
            betrag += f" ({aufstellung})"
        inhalt["angaben"].append(("Betrag", betrag))
    if stand["stand"] != "frei":
        inhalt["angaben"].append(("Zahlung", zahlung_text(stand)))
    essen = als_mengen(eintrag.get("essen"))
    if essen:
        # "1× Weißwürste" statt "1 Weißwürste": das Mal-Zeichen liest sich bei
        # jedem Gerichtnamen richtig, auch wenn er schon im Plural steht.
        inhalt["angaben"].append(
            ("Essen", " · ".join(f"{menge}× {name}" for name, menge in essen.items()))
        )
    getraenke = als_liste(eintrag.get("getraenke"))
    if getraenke:
        # Getrennt wird mit einem Punkt statt mit Komma: "Helles, alkoholfrei"
        # trägt selbst schon eines und sah sonst nach zwei Getränken aus.
        inhalt["angaben"].append(("Getränke", " · ".join(getraenke)))
    if eintrag.get("anmerkung"):
        inhalt["angaben"].append(("Anmerkung", eintrag["anmerkung"]))

    if opt.get("datum"):
        wann = opt["datum"]
        if opt.get("uhrzeit"):
            wann += f", Abfahrt {opt['uhrzeit']} Uhr"
        inhalt["termin"].append(("Wann", wann))
    if opt.get("ort"):
        inhalt["termin"].append(("Treffpunkt", opt["ort"]))
    if opt.get("ziel"):
        inhalt["termin"].append(("Ziel", opt["ziel"]))

    if adresse:
        kennung = eintrag["id"]
        inhalt["links"] = [
            ("Anmeldung ansehen", f"{adresse}/danke/{kennung}"),
            ("Anmeldung ändern", f"{adresse}/anmeldung/{kennung}/aendern"),
            ("Anmeldung absagen", f"{adresse}/anmeldung/{kennung}/absagen"),
        ]
        if bezahlen_moeglich:
            # Der Bezahl-Link steht vorn und wird damit in der HTML-Fassung
            # zum großen Knopf.
            inhalt["links"].insert(
                0,
                (f"Jetzt {euro(stand['offen'])} bezahlen",
                 f"{adresse}/anmeldung/{kennung}/bezahlen"),
            )
        inhalt["hinweis"] = (
            "Bitte behalten Sie diese Mail, bis der Ausflug vorbei ist. "
            "Die Links gelten nur für Ihre Anmeldung."
        )
    if email_link:
        inhalt["links"].insert(0, (f"Jetzt {euro(stand['offen'])} mit PayPal bezahlen", email_link))
        if not adresse:
            inhalt["links_titel"] = "Bezahlen"
    if me_link:
        # Auch ohne öffentliche Adresse: der Link führt direkt zu PayPal.
        inhalt["links"].insert(0, (f"Jetzt {euro(stand['offen'])} mit PayPal bezahlen", me_link))
        if not adresse:
            inhalt["links_titel"] = "Bezahlen"
    return inhalt


def _als_text(inhalt):
    """Die Nur-Text-Fassung. Keine Spalten, die mit Leerzeichen aufgefüllt
    sind: in einer Proportionalschrift steht so etwas krumm."""
    def block(ueberschrift, paare):
        if not paare:
            return []
        raus = [ueberschrift, "-" * len(ueberschrift)]
        raus += [f"{name}: {wert}" for name, wert in paare]
        return raus + [""]

    zeilen = [inhalt["anrede"], ""]
    for absatz in inhalt["absaetze"]:
        if isinstance(absatz, tuple):
            # Ein Angabenblock zwischen den Absätzen: (Überschrift, Paare).
            zeilen += block(*absatz)
        else:
            zeilen += [absatz, ""]

    zeilen += block("Ihre Angaben", inhalt["angaben"])
    zeilen += block("Termin", inhalt["termin"])
    if inhalt["links"]:
        zeilen += [inhalt["links_titel"], "-" * len(inhalt["links_titel"])]
        for name, verweis in inhalt["links"]:
            zeilen += [f"{name}:", verweis, ""]
    if inhalt["hinweis"]:
        zeilen += [inhalt["hinweis"], ""]
    if inhalt["kontakt"]:
        zeilen += [f"Bei Fragen: {inhalt['kontakt']}", ""]
    zeilen += ["Mit freundlichen Grüßen", inhalt["veranstalter"]]
    return "\n".join(zeilen)


# Mailprogramme laden keine Schriften nach und rechnen kein modernes CSS aus.
# Deshalb Tabellen, Stile direkt am Element und Schriften, die jedes Gerät hat.
MAIL_SANS = "font-family:'Segoe UI',Helvetica,Arial,sans-serif;"
MAIL_SERIF = "font-family:Georgia,'Times New Roman',serif;"


def _als_html(inhalt, titel):
    """Die HTML-Fassung: dieselben Angaben wie im Text, nur gesetzt."""
    def ueberschrift(text):
        return (
            f'<tr><td style="{MAIL_SANS}padding:10px 0 6px;font-size:12px;'
            f'letter-spacing:.08em;text-transform:uppercase;color:#7B7466;">'
            f"{escape(text)}</td></tr>"
        )

    def block(titelzeile, paare):
        if not paare:
            return ""
        reihen = ""
        for name, wert in paare:
            reihen += (
                f'<tr><td style="{MAIL_SANS}padding:3px 14px 3px 0;font-size:14px;'
                f'color:#6B6558;vertical-align:top;white-space:nowrap;">{escape(name)}</td>'
                f'<td style="{MAIL_SANS}padding:3px 0;font-size:16px;color:#221F1B;">'
                f"{escape(wert)}</td></tr>"
            )
        return ueberschrift(titelzeile) + (
            '<tr><td style="padding:0 0 6px;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'width="100%" style="background:#FAF7F2;border:1px solid #EBE4D8;'
            'border-radius:4px;border-collapse:separate;">'
            '<tr><td style="padding:10px 14px;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
            + reihen
            + "</table></td></tr></table></td></tr>"
        )

    teile = [
        f'<tr><td style="{MAIL_SANS}padding:0 0 16px;font-size:17px;color:#221F1B;">'
        f"{escape(inhalt['anrede'])}</td></tr>"
    ]
    for absatz in inhalt["absaetze"]:
        if isinstance(absatz, tuple):
            # Ein Angabenblock zwischen den Absätzen: (Überschrift, Paare).
            teile.append(block(*absatz))
        else:
            teile.append(
                f'<tr><td style="{MAIL_SANS}padding:0 0 14px;font-size:17px;'
                f'line-height:1.5;color:#3B372F;">{escape(absatz)}</td></tr>'
            )

    teile.append(block("Ihre Angaben", inhalt["angaben"]))
    teile.append(block("Termin", inhalt["termin"]))

    if inhalt["links"]:
        haupt, haupt_verweis = inhalt["links"][0]
        teile.append(ueberschrift(inhalt["links_titel"]))
        teile.append(
            '<tr><td style="padding:2px 0 4px;">'
            f'<a href="{escape(haupt_verweis, quote=True)}" style="{MAIL_SANS}'
            'display:inline-block;background:#8A6334;color:#FFFFFF;font-size:16px;'
            'text-decoration:none;padding:11px 20px;border-radius:4px;">'
            f"{escape(haupt)}</a></td></tr>"
        )
        weitere = ""
        for name, verweis in inhalt["links"][1:]:
            weitere += (
                f'<div style="{MAIL_SANS}padding:4px 0;font-size:15px;">'
                f'<a href="{escape(verweis, quote=True)}" style="color:#8A6334;">'
                f"{escape(name)}</a></div>"
            )
        if weitere:
            teile.append(f'<tr><td style="padding:6px 0 2px;">{weitere}</td></tr>')

    if inhalt["hinweis"]:
        teile.append(
            f'<tr><td style="{MAIL_SANS}padding:16px 0 0;font-size:14px;'
            f'line-height:1.5;color:#6B6558;">{escape(inhalt["hinweis"])}</td></tr>'
        )

    fuss = "Mit freundlichen Grüßen<br>" + escape(inhalt["veranstalter"])
    if inhalt["kontakt"]:
        fuss = f"Bei Fragen: {escape(inhalt['kontakt'])}<br><br>" + fuss
    teile.append(
        f'<tr><td style="{MAIL_SANS}padding:18px 0 0;font-size:15px;'
        f'line-height:1.6;color:#3B372F;">'
        '<div style="border-top:1px solid #EBE4D8;padding-top:16px;">'
        f"{fuss}</div></td></tr>"
    )

    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(titel)}</title></head>"
        '<body style="margin:0;padding:0;background:#F4F1EB;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="background:#F4F1EB;"><tr>'
        '<td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="max-width:560px;background:#FFFFFF;border:1px solid #DDD6CA;'
        'border-radius:6px;border-collapse:separate;">'
        '<tr><td style="padding:26px 26px 0;">'
        '<div style="height:3px;width:38px;background:#8A6334;font-size:0;line-height:0;">'
        "&nbsp;</div>"
        f'<div style="{MAIL_SERIF}padding:14px 0 4px;font-size:21px;line-height:1.3;'
        f'color:#221F1B;">{escape(titel)}</div></td></tr>'
        '<tr><td style="padding:12px 26px 26px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        + "".join(teile)
        + "</table></td></tr></table></td></tr></table></body></html>"
    )


def postausgang_fehlt(opt):
    """Adressen werden abgefragt, aber es ist kein Postausgang eingerichtet -
    dann geht bei keiner einzigen Anmeldung eine Bestätigung raus."""
    return bool(opt.get("email_abfragen")) and not (
        (opt.get("smtp_server") or "").strip()
        and (opt.get("smtp_absender") or opt.get("smtp_benutzer") or "").strip()
    )


def mailstand_merken(anmeldung_id, art, stand, grund=""):
    """Das Ergebnis des Versands an der Anmeldung vermerken, damit es in der
    Verwaltung sichtbar ist. Der Versand läuft im Hintergrund, deshalb wird
    hier frisch gelesen - inzwischen kann sich der Datensatz geändert haben."""
    if not anmeldung_id:
        return
    with _lock:
        daten = _lesen()
        eintrag = _suchen(daten, anmeldung_id)
        if eintrag is None:
            return
        eintrag["mail"] = {
            "stand": stand,
            "art": art,
            "zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
            "grund": str(grund)[:300],
        }
        _schreiben(daten)


def bestaetigung_mailen(eintrag, art="neu"):
    """Schickt dem Gast eine Bestätigung, wenn eine Adresse da ist und ein
    Postausgang eingerichtet ist. Wie es ausgegangen ist, steht danach am
    Datensatz und damit in der Verwaltung - die Anmeldung selbst ist zu diesem
    Zeitpunkt längst gespeichert."""
    empfaenger = (eintrag.get("email") or "").strip()
    opt = optionen()
    server = (opt.get("smtp_server") or "").strip()
    absender = (opt.get("smtp_absender") or opt.get("smtp_benutzer") or "").strip()
    if not empfaenger or not server or not absender:
        # Kein Versuch, also auch kein Vermerk an der einzelnen Anmeldung: ein
        # fehlender Postausgang betrifft alle und steht als Hinweis oben in der
        # Verwaltung.
        return

    adresse = (opt.get("oeffentliche_adresse") or "").rstrip("/")
    stand, grund = _mail_abschicken(
        opt, empfaenger, art, _mail_inhalt(opt, eintrag, art, adresse)
    )
    mailstand_merken(eintrag.get("id"), art, stand, grund)


def _mail_abschicken(opt, empfaenger, art, inhalt):
    server = (opt.get("smtp_server") or "").strip()
    absender = (opt.get("smtp_absender") or opt.get("smtp_benutzer") or "").strip()

    nachricht = EmailMessage()
    nachricht["Subject"] = BETREFFE.get(art, BETREFFE["neu"]).format(titel=opt["titel"])
    nachricht["From"] = absender
    nachricht["To"] = empfaenger
    # Wenn die Absenderdomain kein Postfach hat, laufen Antworten ins Leere.
    # Antwort-an lenkt sie auf eine Adresse, die wirklich jemand liest.
    antwort_an = (opt.get("smtp_antwort_an") or "").strip()
    if antwort_an:
        nachricht["Reply-To"] = antwort_an
    nachricht.set_content(_als_text(inhalt))
    # Die HTML-Fassung ist nur die Alternative: wer lieber Text liest oder
    # dessen Programm kein HTML anzeigt, sieht oben genau dasselbe.
    nachricht.add_alternative(_als_html(inhalt, opt["titel"]), subtype="html")

    port = int(opt.get("smtp_port") or 587)
    verschluesselung = (opt.get("smtp_verschluesselung") or "starttls").lower()
    benutzer = (opt.get("smtp_benutzer") or "").strip()
    # Auch das Passwort bereinigen: Beim Einfügen in das Feld in Home Assistant
    # rutscht leicht ein Leerzeichen oder Zeilenumbruch mit, und SMTP ist
    # zeilenweise - der Server lehnt die Anmeldung dann mit 535 ab, ohne dass
    # man dem Feld etwas ansieht. Ein Passwort mit Leerzeichen am Rand vergibt
    # kein Mailanbieter.
    passwort = (opt.get("smtp_passwort") or "").strip()
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
        return "zugestellt", ""
    except smtplib.SMTPAuthenticationError as fehler:
        # Der Server war erreichbar und hat die Zugangsdaten abgelehnt. Die
        # Meldung allein hilft niemandem weiter, deshalb die häufigen Ursachen
        # gleich dazu.
        print(
            f"[anmeldung] Mail an {empfaenger} fehlgeschlagen: {fehler}\n"
            f"[anmeldung] Der Mailserver hat Benutzer '{benutzer}' abgelehnt. "
            "Häufigste Ursachen: Benutzername muss meist die vollständige "
            "Adresse sein (nicht nur der Teil vor dem @); Postfach-Passwort "
            "statt Konto-Passwort; bei Zwei-Faktor-Anmeldung ein eigenes "
            "App-Passwort; bei GMX und Web.de muss der Zugang für "
            "E-Mail-Programme erst im Webmailer freigeschaltet werden.",
            flush=True,
        )
        return "fehlgeschlagen", "Der Mailserver hat die Zugangsdaten abgelehnt"
    except (smtplib.SMTPException, OSError) as fehler:
        print(f"[anmeldung] Mail an {empfaenger} fehlgeschlagen: {fehler}", flush=True)
        return "fehlgeschlagen", f"{type(fehler).__name__}: {fehler}"


def _nachbereiten(arbeit):
    """Sensor, Events und Nachrichten laufen im Hintergrund - der Gast soll
    nicht warten, bis Home Assistant geantwortet hat."""
    threading.Thread(target=arbeit, daemon=True).start()


def _ereignis_daten(eintrag):
    """Was jedes Event über eine Anmeldung mitbringt. Beträge in Cent, so wie
    sie gespeichert sind."""
    stand = zahlstand(eintrag)
    return {
        "name": eintrag["name"],
        "personen": eintrag["personen"],
        "mitglieder": eintrag.get("mitglieder", 0),
        "nichtmitglieder": eintrag.get("nichtmitglieder", 0),
        "kinder": eintrag.get("kinder", 0),
        "betrag_cent": stand["betrag"],
        "bezahlt_cent": stand["bezahlt"],
        "offen_cent": stand["offen"],
    }


def _aenderung_melden(eintrag, betrag_vorher):
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag, "geaendert")
    ereignis_senden(
        f"{EREIGNIS}_aenderung",
        dict(
            _ereignis_daten(eintrag),
            essen=eintrag.get("essen", {}),
            getraenke=eintrag.get("getraenke", []),
            anmerkung=eintrag.get("anmerkung", ""),
        ),
    )
    stand = zahlstand(eintrag)
    if stand["zuviel"] > 0:
        # Die Orga muss Geld zurückgeben - das soll sie nicht erst in der
        # Verwaltung entdecken, auch wenn sonst keine Nachrichten kommen.
        nachricht_senden(
            f"Anmeldung geändert: {eintrag['name']} hat {euro(stand['zuviel'])} "
            "zu viel bezahlt. Bitte von Hand erstatten."
        )
    elif optionen().get("benachrichtigung_jede_anmeldung"):
        text = f"Anmeldung geändert: {_beschreibung(eintrag)}"
        if stand["betrag"] != betrag_vorher:
            text += f". Betrag vorher {euro(betrag_vorher)}"
        nachricht_senden(text)


def _absage_melden(eintrag):
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag, "abgesagt")
    stand = lage()
    geld = zahlstand(eintrag)
    ereignis_senden(
        f"{EREIGNIS}_absage",
        dict(_ereignis_daten(eintrag), freie_plaetze=stand["frei"]),
    )
    erstatten = (
        f" Bereits bezahlt: {euro(geld['zuviel'])} - bitte von Hand erstatten."
        if geld["zuviel"] > 0 else ""
    )
    if geld["zuviel"] > 0 or optionen().get("benachrichtigung_jede_anmeldung"):
        nachricht_senden(
            f"Absage: {eintrag['name']}, {personen_text(eintrag)}. "
            f"Wieder {stand['frei']} von {stand['gesamt']} Plätzen frei."
            + erstatten
        )


def _zahlung_melden(eintrag, zahlung):
    """Nach einer PayPal-Zahlung: Sensor, Event, Nachricht und eine kurze
    Mail an den Gast."""
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag, "bezahlt")
    ereignis_senden(
        f"{EREIGNIS}_zahlung",
        dict(
            _ereignis_daten(eintrag),
            art=zahlung["art"],
            zahlung_cent=zahlung["betrag_cent"],
        ),
    )
    if optionen().get("benachrichtigung_jede_anmeldung"):
        nachricht_senden(
            f"Zahlung eingegangen: {eintrag['name']}, "
            f"{euro(zahlung['betrag_cent'])} per {ZAHLARTEN.get(zahlung['art'], zahlung['art'])}."
        )


def _beschreibung(eintrag):
    teile = [f"{eintrag['name']}, {personen_text(eintrag)}"]
    stand = zahlstand(eintrag)
    if stand["stand"] != "frei":
        teile.append(f"{euro(stand['betrag'])}, {zahlung_text(stand)}")
    essen = als_mengen(eintrag.get("essen"))
    if essen:
        teile.append(", ".join(f"{menge} {name}" for name, menge in essen.items()))
    getraenke = als_liste(eintrag.get("getraenke"))
    if getraenke:
        teile.append(", ".join(getraenke))
    return ". ".join(teile)


# --------------------------------------------------------------------------
# PayPal
# --------------------------------------------------------------------------

# Bezahlt wird über den PayPal-Knopf auf der Bestätigungsseite. Der Knopf
# selbst kennt keinen Betrag: Er fragt diesen Server nach einer Order, und der
# legt sie bei PayPal über den offenen Betrag an, den er selbst gerechnet hat.
# Nach der Freigabe durch den Gast bucht ("captured") wieder dieser Server und
# prüft dabei Status, Betrag, Währung und Zugehörigkeit. Das Secret verlässt
# den Server nie - der Browser bekommt nur die Client-ID, die ohnehin
# öffentlich ist.

ORDER_ID_MUSTER = re.compile(r"[A-Za-z0-9-]{5,64}")


class PayPalFehler(Exception):
    """Ein Aufruf bei PayPal ist schiefgegangen. "status" ist der HTTP-Status
    (0, wenn PayPal gar nicht erreichbar war), "issue" der genauere Grund aus
    der Antwort, etwa ORDER_ALREADY_CAPTURED."""

    def __init__(self, text, status=0, issue=""):
        super().__init__(text)
        self.status = status
        self.issue = issue


_paypal_zugang = {"schluessel": None, "token": "", "bis": 0.0}
_paypal_zugang_lock = threading.Lock()
# Buchungen laufen nacheinander. Ein Doppelklick oder zwei offene Tabs dürfen
# nicht zweimal buchen; bei der Handvoll Zahlungen für einen Ausflug kostet
# das Warten nichts.
_zahlung_lock = threading.Lock()


def _paypal_basis(opt):
    return PAYPAL_TESTADRESSE or PAYPAL_ADRESSEN[opt["paypal_modus"]]


def _paypal_anfrage(opt, methode, pfad, nutzlast=None, kopf=None, rumpf=None):
    """Eine Anfrage an die PayPal-Schnittstelle, Antwort als dict.

    Ins Protokoll kommt bei einem Fehler nur, was PayPal zurückschickt
    (Fehlername, Grund, debug_id) - nie die Kopfzeilen der Anfrage, denn in
    denen stehen Token oder Secret."""
    kopfzeilen = {"Accept": "application/json"}
    kopfzeilen.update(kopf or {})
    if nutzlast is not None:
        rumpf = json.dumps(nutzlast).encode("utf-8")
        kopfzeilen["Content-Type"] = "application/json"
    anfrage = urllib.request.Request(
        _paypal_basis(opt) + pfad, data=rumpf, headers=kopfzeilen, method=methode
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            inhalt = antwort.read()
        daten = json.loads(inhalt or b"{}")
        if not isinstance(daten, dict):
            raise ValueError("Antwort ist kein Objekt")
        return daten
    except urllib.error.HTTPError as fehler:
        try:
            daten = json.loads(fehler.read() or b"{}")
        except (OSError, ValueError):
            daten = {}
        if not isinstance(daten, dict):
            daten = {}
        name = str(daten.get("name") or daten.get("error") or "")
        details = daten.get("details") or []
        issue = ""
        if details and isinstance(details[0], dict):
            issue = str(details[0].get("issue") or "")
        print(
            f"[anmeldung] PayPal {methode} {pfad}: {fehler.code} {name} {issue} "
            f"debug_id={daten.get('debug_id', '-')}",
            flush=True,
        )
        raise PayPalFehler(name or f"HTTP {fehler.code}", fehler.code, issue) from None
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        print(f"[anmeldung] PayPal {methode} {pfad}: {type(fehler).__name__}", flush=True)
        raise PayPalFehler("PayPal ist nicht erreichbar") from None


def _paypal_token(opt):
    """Ein Zugangstoken für die Schnittstelle. PayPal stellt es für einige
    Stunden aus; es wird so lange wiederverwendet und neu geholt, sobald sich
    Modus oder Zugangsdaten ändern."""
    schluessel = (_paypal_basis(opt), opt["paypal_client_id"], opt["paypal_secret"])
    with _paypal_zugang_lock:
        if (_paypal_zugang["schluessel"] == schluessel
                and time.monotonic() < _paypal_zugang["bis"]):
            return _paypal_zugang["token"]
        zugang = base64.b64encode(
            f"{opt['paypal_client_id']}:{opt['paypal_secret']}".encode("utf-8")
        ).decode("ascii")
        try:
            antwort = _paypal_anfrage(
                opt,
                "POST",
                "/v1/oauth2/token",
                kopf={
                    "Authorization": f"Basic {zugang}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                rumpf=b"grant_type=client_credentials",
            )
        except PayPalFehler as fehler:
            if fehler.status == 401:
                print(
                    "[anmeldung] PayPal hat Client-ID oder Secret abgelehnt. Passen "
                    f"beide zum Modus '{opt['paypal_modus']}'? Sandbox- und "
                    "Live-Zugangsdaten sind verschieden.",
                    flush=True,
                )
            raise
        token = str(antwort.get("access_token") or "")
        if not token:
            raise PayPalFehler("PayPal hat kein Token geschickt")
        dauer = int(antwort.get("expires_in") or 300)
        _paypal_zugang.update(
            schluessel=schluessel,
            token=token,
            bis=time.monotonic() + max(60, dauer - 120),
        )
        return token


def _paypal(opt, methode, pfad, nutzlast=None, kopf=None):
    kopfzeilen = {"Authorization": f"Bearer {_paypal_token(opt)}"}
    kopfzeilen.update(kopf or {})
    return _paypal_anfrage(opt, methode, pfad, nutzlast=nutzlast, kopf=kopfzeilen)


def paypal_order_anlegen(opt, eintrag, cent):
    """Legt bei PayPal eine Order über "cent" an. Die Anmelde-ID steht als
    reference_id und custom_id darin - daran erkennt der Abschluss, dass die
    Order zu genau dieser Anmeldung gehört."""
    return _paypal(
        opt,
        "POST",
        "/v2/checkout/orders",
        {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": eintrag["id"],
                    "custom_id": eintrag["id"],
                    "description": opt["titel"][:127],
                    "amount": {"currency_code": WAEHRUNG, "value": paypal_wert(cent)},
                }
            ],
            # Ein Ausflug wird nicht verschickt: ohne diese Angabe fragt
            # PayPal nach einer Lieferadresse.
            "application_context": {
                "brand_name": veranstalter_name(opt)[:127],
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
            },
        },
    )


def paypal_order_buchen(opt, order_id):
    """Bucht eine vom Gast freigegebene Order. Ist sie schon gebucht - etwa
    weil der erste Versuch bei PayPal durchging, die Antwort aber nicht mehr
    hier ankam -, wird die Order stattdessen nur abgefragt."""
    try:
        return _paypal(
            opt,
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            {},
            # Dieselbe Request-ID für dieselbe Order: Wiederholt sich der
            # Aufruf, antwortet PayPal mit dem ersten Ergebnis, statt noch
            # einmal abzubuchen.
            kopf={
                "PayPal-Request-Id": f"capture-{order_id}",
                "Prefer": "return=representation",
            },
        )
    except PayPalFehler as fehler:
        if fehler.issue == "ORDER_ALREADY_CAPTURED":
            return _paypal(opt, "GET", f"/v2/checkout/orders/{order_id}")
        raise


def _capture_lesen(order):
    """Das Wichtige aus der Antwort von PayPal, Betrag in Cent."""
    einheiten = order.get("purchase_units") or [{}]
    einheit = einheiten[0] if isinstance(einheiten[0], dict) else {}
    captures = (einheit.get("payments") or {}).get("captures") or [{}]
    capture = captures[0] if isinstance(captures[0], dict) else {}
    betrag = capture.get("amount") or {}
    return {
        "order_status": str(order.get("status") or ""),
        "capture_status": str(capture.get("status") or ""),
        "capture_id": str(capture.get("id") or ""),
        "cent": paypal_in_cent(betrag.get("value")),
        "waehrung": str(betrag.get("currency_code") or ""),
        # Jede Kennung, die PayPal zurückmeldet. Alle müssen auf diese eine
        # Anmeldung zeigen.
        "referenzen": {
            str(x)
            for x in (
                einheit.get("reference_id"),
                einheit.get("custom_id"),
                capture.get("custom_id"),
            )
            if x
        },
    }


def capture_pruefen(ergebnis, anmeldung_id, erwartet_cent):
    """Der Grund, warum eine Buchung nicht verbucht werden darf - oder ein
    leerer Text, wenn alles stimmt."""
    if ergebnis["referenzen"] != {anmeldung_id}:
        return "Die Zahlung gehört laut PayPal nicht zu dieser Anmeldung"
    if ergebnis["order_status"] != "COMPLETED" or ergebnis["capture_status"] != "COMPLETED":
        return (
            f"PayPal meldet Status {ergebnis['order_status'] or '?'}/"
            f"{ergebnis['capture_status'] or '?'} statt COMPLETED"
        )
    if not ergebnis["capture_id"]:
        return "PayPal hat keine Capture-ID geschickt"
    if ergebnis["waehrung"] != WAEHRUNG:
        return f"Währung {ergebnis['waehrung'] or '?'} statt {WAEHRUNG}"
    if ergebnis["cent"] != erwartet_cent:
        gezahlt = euro(ergebnis["cent"]) if ergebnis["cent"] is not None else "?"
        return f"Betrag {gezahlt} statt {euro(erwartet_cent)}"
    return ""


# --------------------------------------------------------------------------
# Flask
# --------------------------------------------------------------------------

app = Flask(__name__)


# Ingress-Pfade sehen aus wie /api/hassio_ingress/<token>. Alles andere wird
# verworfen: ein "//fremde-seite.example" im Header landete sonst in jedem
# url_for und machte aus einem redirect() eine Weiterleitung nach auswärts.
INGRESS_PFAD = re.compile(r"/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*/?")


class IngressPfad:
    """Home Assistant schickt den Ingress-Prefix als Header mit. Ausgewertet
    wird er nur auf dem Ingress-Port - auf der öffentlichen Seite kommt der
    Header von außen und lässt sich frei erfinden."""

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
    ihnen zu vertrauen hieße, dass sich jeder eine beliebige Adresse ausstellen
    kann.
    """
    return (request.headers.get("Cf-Connecting-Ip") or "").strip() or (
        request.remote_addr or ""
    )


def aus_dem_haus():
    """Kam die Anfrage aus dem eigenen Netz?

    Der Watchdog des Supervisors und Aufrufe aus dem Heimnetz haben eine private
    Adresse und keine Kopfzeile von Cloudflare. Die bleiben von der Testsperre
    unberührt - sonst bekäme der Watchdog dauerhaft eine 503 und startete das
    Add-on womöglich im Kreis neu.
    """
    if (request.headers.get("Cf-Connecting-Ip") or "").strip():
        return False
    try:
        wer = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return wer.is_private or wer.is_loopback or wer.is_link_local


def adressnetze(text):
    """Die Option in Netze übersetzen. Eine einzelne Adresse wird dabei zu
    ihrem eigenen Netz, damit beides gleich geprüft werden kann."""
    netze = []
    for teil in re.split(r"[,;\s]+", str(text or "")):
        if not teil:
            continue
        try:
            netze.append(ipaddress.ip_network(teil, strict=False))
        except ValueError:
            print(
                f"[anmeldung] nur_fuer_ip: '{teil}' ist keine Adresse und wird "
                "übergangen",
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
    """Die Verwaltung ist ausschließlich über Home Assistant erreichbar."""
    if request.path.startswith("/verwaltung") and not ueber_ingress():
        abort(404)


@app.before_request
def testsperre():
    """Zum Testen vor dem Aushang: die öffentliche Seite nur für bestimmte
    Adressen. Die Verwaltung über Ingress bleibt immer offen, sonst sperrt man
    sich mit einem Tippfehler selbst aus.

    Das ist eine Testsperre, kein Schutzwall: wer das Add-on am Tunnel vorbei
    direkt erreicht, kann die Kopfzeile Cf-Connecting-Ip selbst setzen. Und wer
    aus dem Heimnetz kommt, wird gar nicht erst geprüft."""
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
# neue Fassung trotzdem sofort ankommt, hängt an jeder Adresse die
# Änderungszeit der Datei.
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
    return {
        "ist_verwaltung": ueber_ingress(),
        "statisch": statisch,
        "zahlstand": zahlstand,
        "personen_text": personen_text,
        "preis_aufstellung": preis_aufstellung,
        "paypal_me_link": paypal_me_link,
        "paypal_email_link": paypal_email_link,
        "zahlung_betreff": zahlung_betreff,
        "ueberweisung": ueberweisung_angaben,
        "girocode_svg": girocode_svg,
    }


# ---------------------------- öffentliche Seite ---------------------------


@app.get("/")
def start():
    # Über Ingress geöffnet ist die Verwaltung gemeint, nicht die Besucherseite.
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
    was nicht passt, meldet die Prüfung unten als Fehler zurück."""
    roh = (request.form.get(feldname) or "0").strip()
    if not re.fullmatch(r"\d{0,3}", roh):
        raise ValueError("Bitte nur ganze Zahlen eintragen.")
    return int(roh or 0)


def _auswahl(feldname, erlaubt):
    """Angekreuzte Gerichte bzw. Getränke, in der eingestellten Reihenfolge.
    Alles, was nicht in den Optionen steht, fällt raus."""
    gewaehlt = set(request.form.getlist(feldname))
    return [name for name in erlaubt if name in gewaehlt]


class Formularfehler(str):
    """Eine Fehlermeldung, die weiß, zu welchem Feld sie gehört. Sie bleibt
    ein gewöhnlicher Text - das Template zeigt sie oben wie bisher - und
    markiert zusätzlich das Feld selbst."""

    def __new__(cls, text, feld=""):
        neu = super().__new__(cls, text)
        neu.feld = feld
        return neu


def _formular_lesen(opt, frei):
    """Formular auslesen und prüfen. Gibt die Werte und - falls etwas nicht
    stimmt - eine Meldung zurück. "frei" ist die Zahl der Plätze, die diese
    eine Anmeldung höchstens belegen darf.

    Einen Betrag liest diese Funktion bewusst nicht: Was der Browser als
    Summe anzeigt, ist nur Anzeige. Gerechnet wird beim Speichern, aus den
    Personenzahlen und den Preisen in den Optionen."""
    werte = {
        "name": " ".join((request.form.get("name") or "").split())[:80],
        "anmerkung": (request.form.get("anmerkung") or "").strip()[:500],
        "email": (request.form.get("email") or "").strip()[:120],
        "mitglieder": 0,
        "nichtmitglieder": 0,
        "kinder": 0,
        "personen": 0,
        "essen": {},
        "getraenke": _auswahl("getraenke", opt["getraenke"]),
    }
    for feld in ("mitglieder", "nichtmitglieder", "kinder"):
        try:
            werte[feld] = _menge(feld)
        except ValueError as problem:
            return werte, Formularfehler(str(problem), "personen")
    erwachsene = werte["mitglieder"] + werte["nichtmitglieder"]
    # Kinder belegen einen Platz im Bus wie alle anderen.
    werte["personen"] = erwachsene + werte["kinder"]
    for i, gericht in enumerate(opt["essen"]):
        try:
            anzahl = _menge(f"essen_{i}")
        except ValueError as problem:
            return werte, Formularfehler(str(problem), "essen")
        if anzahl > 0:
            werte["essen"][gericht] = anzahl

    personen = werte["personen"]
    stueck = sum(werte["essen"].values())
    if len(werte["name"]) < 2:
        return werte, Formularfehler("Bitte tragen Sie einen Namen ein.", "name")
    if personen < 1:
        return werte, Formularfehler("Bitte geben Sie mindestens eine Person an.", "personen")
    if erwachsene < 1:
        return werte, Formularfehler(
            "Bitte mindestens eine erwachsene Person angeben.", "personen"
        )
    if opt["email_abfragen"]:
        # Pflichtfeld: ohne Adresse gibt es weder Bestätigung noch den Link
        # zum Ändern, Absagen und Bezahlen, und genau daran hängt die Planung.
        if not werte["email"]:
            return werte, Formularfehler("Bitte tragen Sie eine E-Mail-Adresse ein.", "email")
        if not EMAIL_MUSTER.fullmatch(werte["email"]):
            return werte, Formularfehler(
                "Die E-Mail-Adresse sieht nicht vollständig aus. "
                "Bitte prüfen Sie die Schreibweise.",
                "email",
            )
    if personen > opt["max_personen_pro_anmeldung"]:
        return werte, Formularfehler(
            "Pro Anmeldung sind höchstens "
            f"{opt['max_personen_pro_anmeldung']} Personen möglich, "
            "Mitglieder, Nichtmitglieder und Kinder zusammen.",
            "personen",
        )
    if personen > frei:
        return werte, Formularfehler(
            (f"Es ist nur noch {frei} Platz frei. " if frei == 1
             else f"Es sind nur noch {frei} Plätze frei. ")
            + "Bitte passen Sie die Personenzahl an.",
            "personen",
        )
    if stueck > personen * 10:
        # Die Zahl sind Stück, nicht Portionen je Person - eine Person nimmt
        # durchaus zwei Weißwürste. Die Grenze fängt nur Zahlendreher ab.
        return werte, Formularfehler(
            f"Das sind {stueck} Stück für {personen} "
            f"{'Person' if personen == 1 else 'Personen'}. "
            "Bitte prüfen Sie die Zahlen noch einmal.",
            "essen",
        )
    return werte, None


def _preise_festhalten(werte, opt):
    """Betrag und die Preise, aus denen er entstanden ist, an die Werte
    hängen. Die Einzelpreise bleiben an der Anmeldung stehen: Ändert die Orga
    später die Optionen, bleibt nachvollziehbar, wie der Betrag zustande kam."""
    werte["preis_mitglied_cent"] = opt["preis_mitglied_cent"]
    werte["preis_nichtmitglied_cent"] = opt["preis_nichtmitglied_cent"]
    werte["preis_kind_cent"] = opt["preis_kind_cent"]
    werte["betrag_cent"] = betrag_berechnen(
        werte["mitglieder"], werte["nichtmitglieder"], opt, werte["kinder"]
    )
    return werte


@app.post("/anmeldung")
def anmelden():
    stand = lage()
    opt = stand["opt"]

    # Honigtopf gegen einfache Bots: für Menschen unsichtbar, bleibt leer.
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
        _preise_festhalten(werte, opt),
        id=secrets.token_urlsafe(9),
        zeit=datetime.now().astimezone().isoformat(timespec="seconds"),
        zahlungen=[],
    )

    # Zweite Prüfung unter Sperre: zwischen Anzeige und Absenden können
    # andere Anmeldungen die letzten Plätze belegt haben.
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
        # Zwischen Anzeige und Absenden sind die letzten Plätze weggegangen.
        # Die Startseite sagt das dann ausdrücklich, statt nur "ausgebucht".
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
    # Der Betrag wird neu gerechnet. Was schon bezahlt ist, bleibt in der
    # Zahlungsliste stehen: Ist der neue Betrag höher, ist die Differenz
    # offen und lässt sich nachzahlen; ist er niedriger, zeigt die Verwaltung
    # den Betrag zum Erstatten.
    _preise_festhalten(werte, opt)

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
            betrag_vorher = int(gespeichert.get("betrag_cent", 0))
            gespeichert.update(werte)
            gespeichert["geaendert"] = (
                datetime.now().astimezone().isoformat(timespec="seconds")
            )
            _schreiben(daten)
            neu = dict(gespeichert)

    if zu_spaet:
        return redirect(url_for("start", voll=1))

    _nachbereiten(lambda: _aenderung_melden(neu, betrag_vorher))
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
            # Bezahltes wird nicht automatisch erstattet. Die Zahlungen
            # bleiben stehen, die Verwaltung zeigt den Betrag zum Erstatten.
            eintrag["abgesagt"] = (
                datetime.now().astimezone().isoformat(timespec="seconds")
            )
            _schreiben(daten)
            abgesagt = dict(eintrag)

    if abgesagt:
        _nachbereiten(lambda: _absage_melden(abgesagt))
    return redirect(url_for("danke", anmeldung_id=anmeldung_id))


def _melden(eintrag, belegt_vorher, belegt_nachher, anzahl):
    """Sensor schreiben, Event auslösen, Nachricht schicken, Mail an den Gast."""
    sensor_aktualisieren()
    bestaetigung_mailen(eintrag)
    opt = optionen()
    gesamt = opt["plaetze_gesamt"]
    frei = max(0, gesamt - belegt_nachher)

    ereignis_senden(
        f"{EREIGNIS}_anmeldung",
        dict(
            _ereignis_daten(eintrag),
            essen=eintrag["essen"],
            getraenke=eintrag["getraenke"],
            anmerkung=eintrag["anmerkung"],
            anmeldungen=anzahl,
            belegte_plaetze=belegt_nachher,
            freie_plaetze=frei,
            ausgebucht=frei <= 0,
        ),
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
    # Ohne eigenen Text: die eingebaute Erklärung, die genau beschreibt, was
    # dieses Add-on tut. Den Verantwortlichen holt sie aus dem Impressum.
    return render_template("datenschutz_vorlage.html", **stand)


@app.get("/danke/<anmeldung_id>")
def danke(anmeldung_id):
    stand = lage()
    # über _suchen, weil das auch mit Altbeständen ohne id zurechtkommt -
    # ein direktes a["id"] warf dort einen KeyError und damit einen 500er.
    eintrag = _suchen(stand["daten"], anmeldung_id)
    if eintrag is None:
        return redirect(url_for("start"))
    return render_template("danke.html", eintrag=eintrag, **stand)


@app.get("/anmeldung/<anmeldung_id>/bezahlen")
def bezahlen(anmeldung_id):
    """Der Bezahl-Link aus der Mail. Bezahlt wird auf der Bestätigungsseite,
    der Link springt dort direkt zum Abschnitt „Zu bezahlen“ mit dem QR-Code
    für die Überweisung und dem PayPal-Knopf oder -Link."""
    return redirect(url_for("danke", anmeldung_id=anmeldung_id, _anchor="bezahlen"))


def dateiname_ascii(text, laenge=30):
    """Ein Dateiname-Teil nur aus a-z, 0-9 und Bindestrichen (Umlaute werden
    ausgeschrieben), damit der Header Content-Disposition überall passt."""
    text = str(text or "")
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"),
                     ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:laenge].strip("-")


@app.get("/anmeldung/<anmeldung_id>/girocode.png")
def girocode_png(anmeldung_id):
    """Der GiroCode der Anmeldung als Bild zum Speichern oder Teilen: am Handy
    lässt sich der QR-Code auf dem eigenen Bildschirm nicht scannen, die
    Banking-App kann ihn aber aus der Galerie lesen. Wie die Bestätigungsseite
    nur über die Anmelde-ID erreichbar; Inhalt und Betrag baut allein der
    Server (offener Betrag). 404, wenn es nichts zu überweisen gibt."""
    opt = optionen()
    with _lock:
        eintrag = _suchen(_lesen(), anmeldung_id)
    if eintrag is None or eintrag.get("abgesagt"):
        abort(404)
    offen = zahlstand(eintrag)["offen"]
    inhalt = girocode_inhalt(opt, eintrag, offen)
    if not inhalt:
        abort(404)
    try:
        code = segno.make_qr(inhalt, error="m", encoding="utf-8", boost_error=False)
        puffer = io.BytesIO()
        code.save(puffer, kind="png", scale=10, border=4, dark="#000000", light="#FFFFFF")
    except (ValueError, segno.DataOverflowError) as fehler:
        print(f"[anmeldung] GiroCode-Bild konnte nicht erzeugt werden: {fehler}", flush=True)
        abort(404)
    teile = [t for t in ("ueberweisung", dateiname_ascii(opt.get("titel")), euro_zahl(offen).replace(",", "-").replace(".", "-")) if t]
    antwort = Response(puffer.getvalue(), mimetype="image/png")
    antwort.headers["Content-Disposition"] = f'attachment; filename="{"-".join(teile)}.png"'
    antwort.headers["Cache-Control"] = "no-store"
    return antwort


def _antwort(text, status):
    """Antwort an den PayPal-Knopf. Der Text wird dem Gast so angezeigt."""
    return jsonify({"fehler": text}), status


@app.post("/anmeldung/<anmeldung_id>/zahlung/erstellen")
def zahlung_erstellen(anmeldung_id):
    """Legt bei PayPal eine Order über den offenen Betrag an und gibt ihre ID
    an den Knopf zurück. Der Betrag kommt allein aus dem Datensatz."""
    opt = optionen()
    if not opt["paypal_aktiv"]:
        return _antwort("Die Zahlung per PayPal ist nicht eingerichtet.", 404)
    with _lock:
        eintrag = _suchen(_lesen(), anmeldung_id)
    if eintrag is None:
        return _antwort("Diese Anmeldung gibt es nicht.", 404)
    if eintrag.get("abgesagt"):
        return _antwort("Diese Anmeldung ist abgesagt.", 409)
    offen = zahlstand(eintrag)["offen"]
    if offen <= 0:
        return _antwort("Diese Anmeldung ist bereits bezahlt.", 409)

    try:
        order = paypal_order_anlegen(opt, eintrag, offen)
    except PayPalFehler:
        return _antwort(
            "PayPal ist gerade nicht erreichbar. Bitte versuchen Sie es in ein "
            "paar Minuten noch einmal.",
            502,
        )
    order_id = str(order.get("id") or "")
    if not ORDER_ID_MUSTER.fullmatch(order_id):
        print("[anmeldung] PayPal hat beim Anlegen keine Order-ID geschickt", flush=True)
        return _antwort("PayPal hat nicht wie erwartet geantwortet.", 502)

    # Die Order wird an der Anmeldung vermerkt. Nur Orders aus dieser Liste
    # werden später gebucht, und zwar nur über genau diesen Betrag.
    with _lock:
        daten = _lesen()
        gespeichert = _suchen(daten, anmeldung_id)
        if gespeichert is None:
            return _antwort("Diese Anmeldung gibt es nicht mehr.", 404)
        bestellungen = gespeichert.setdefault("paypal_bestellungen", [])
        bestellungen.append({
            "order_id": order_id,
            "betrag_cent": offen,
            "zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        # Jeder Klick auf den Knopf legt eine Order an. Die letzten zwanzig
        # reichen, um jede noch offene Freigabe buchen zu können.
        del bestellungen[:-20]
        _schreiben(daten)
    return jsonify({"order_id": order_id})


def _problem_merken(anmeldung_id, order_id, ergebnis, grund):
    """Eine Zahlung, die bei PayPal durchging, aber hier nicht verbucht werden
    durfte, an der Anmeldung vermerken. Die Verwaltung zeigt sie rot an - das
    Geld liegt womöglich schon auf dem Konto und muss von Hand geklärt werden."""
    with _lock:
        daten = _lesen()
        eintrag = _suchen(daten, anmeldung_id)
        if eintrag is None:
            return
        probleme = eintrag.setdefault("zahlungsprobleme", [])
        if any(p.get("order_id") == order_id and p.get("grund") == grund for p in probleme):
            return
        probleme.append({
            "order_id": order_id,
            "capture_id": ergebnis.get("capture_id", ""),
            "grund": grund,
            "zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        _schreiben(daten)


@app.post("/anmeldung/<anmeldung_id>/zahlung/abschliessen")
def zahlung_abschliessen(anmeldung_id):
    """Bucht eine vom Gast freigegebene Order und verbucht sie an der
    Anmeldung - genau einmal, auch bei Doppelklick oder Neuladen."""
    opt = optionen()
    if not opt["paypal_aktiv"]:
        return _antwort("Die Zahlung per PayPal ist nicht eingerichtet.", 404)
    order_id = str((request.get_json(silent=True) or {}).get("order_id") or "")
    if not ORDER_ID_MUSTER.fullmatch(order_id):
        return _antwort("Ungültige Zahlung.", 400)

    gebucht = None
    with _zahlung_lock:
        with _lock:
            eintrag = _suchen(_lesen(), anmeldung_id)
        if eintrag is None:
            return _antwort("Diese Anmeldung gibt es nicht.", 404)

        # Gehört die Order zu dieser Anmeldung? Geprüft wird an der eigenen
        # Liste, bevor PayPal überhaupt gefragt wird.
        bestellung = next(
            (b for b in eintrag.get("paypal_bestellungen") or []
             if b.get("order_id") == order_id),
            None,
        )
        if bestellung is None:
            print(
                f"[anmeldung] Zahlung: Order {order_id} gehört nicht zu "
                f"Anmeldung {anmeldung_id}",
                flush=True,
            )
            return _antwort("Diese Zahlung gehört nicht zu dieser Anmeldung.", 403)

        stand = zahlstand(eintrag)
        if any(z.get("order_id") == order_id for z in stand["zahlungen"]):
            # Schon verbucht: Doppelklick, Neuladen oder ein zweiter Tab.
            return jsonify({"ok": True, "bezahlt": euro(stand["bezahlt"]),
                            "offen": euro(stand["offen"])})
        if eintrag.get("abgesagt"):
            return _antwort("Diese Anmeldung ist inzwischen abgesagt.", 409)
        if bestellung["betrag_cent"] > stand["offen"]:
            # Seit dem Anlegen der Order wurde anderweitig bezahlt oder die
            # Anmeldung verkleinert. Dann nicht abbuchen - sonst wäre zu viel
            # gezahlt.
            return _antwort(
                "Der offene Betrag hat sich inzwischen geändert. Bitte laden "
                "Sie die Seite neu.",
                409,
            )

        try:
            order = paypal_order_buchen(opt, order_id)
        except PayPalFehler as fehler:
            if fehler.issue == "INSTRUMENT_DECLINED":
                # Die Zahlungsquelle wurde abgelehnt. Der Knopf bietet dann
                # von sich aus eine andere an.
                return jsonify({"fehler": "Die Zahlung wurde abgelehnt.",
                                "neu_versuchen": True}), 402
            return _antwort(
                "Die Zahlung konnte bei PayPal nicht abgeschlossen werden. "
                "Es wurde nichts abgebucht, falls PayPal nichts anderes meldet.",
                502,
            )

        ergebnis = _capture_lesen(order)
        grund = capture_pruefen(ergebnis, anmeldung_id, bestellung["betrag_cent"])
        if grund:
            print(
                f"[anmeldung] Zahlung für {anmeldung_id} nicht verbucht: {grund} "
                f"(Order {order_id}, Capture {ergebnis['capture_id'] or '-'})",
                flush=True,
            )
            _problem_merken(anmeldung_id, order_id, ergebnis, grund)
            kontakt = (opt.get("kontakt") or "").strip()
            return _antwort(
                "Die Zahlung konnte nicht verbucht werden. Bitte wenden Sie "
                "sich an das Organisationsteam"
                + (f": {kontakt}." if kontakt else "."),
                409,
            )

        zahlung = {
            "art": "paypal",
            "betrag_cent": ergebnis["cent"],
            "zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
            "order_id": order_id,
            "capture_id": ergebnis["capture_id"],
        }
        with _lock:
            daten = _lesen()
            gespeichert = _suchen(daten, anmeldung_id)
            if gespeichert is None:
                # Zwischen Abbuchen und Verbuchen gelöscht: das Geld ist da,
                # die Anmeldung nicht mehr. Bleibt nur das Protokoll.
                print(
                    f"[anmeldung] Zahlung {ergebnis['capture_id']} über "
                    f"{euro(ergebnis['cent'])} für gelöschte Anmeldung {anmeldung_id}",
                    flush=True,
                )
                return _antwort("Diese Anmeldung gibt es nicht mehr.", 404)
            zahlungen = gespeichert.setdefault("zahlungen", [])
            if not any(z.get("capture_id") == zahlung["capture_id"]
                       or z.get("order_id") == order_id for z in zahlungen):
                zahlungen.append(zahlung)
                _schreiben(daten)
                gebucht = dict(gespeichert)
            stand = zahlstand(gespeichert)

    if gebucht:
        print(
            f"[anmeldung] Zahlung verbucht: {euro(zahlung['betrag_cent'])} per "
            f"PayPal, Capture {zahlung['capture_id']}",
            flush=True,
        )
        _nachbereiten(lambda: _zahlung_melden(gebucht, zahlung))
    return jsonify({"ok": True, "bezahlt": euro(stand["bezahlt"]),
                    "offen": euro(stand["offen"])})


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
        mitglieder=sum(int(a.get("mitglieder", 0)) for a in anmeldungen),
        nichtmitglieder=sum(int(a.get("nichtmitglieder", 0)) for a in anmeldungen),
        kinder=sum(int(a.get("kinder", 0)) for a in anmeldungen),
        geld=geldsummen(alle),
        # Spalten für Essen und Getränke nur, wenn es etwas zu bestellen gibt
        # oder schon bestellt wurde.
        essen_spalte=bool(stand["opt"]["essen"]) or any(a.get("essen") for a in alle),
        getraenke_spalte=bool(stand["opt"]["getraenke"])
        or any(a.get("getraenke") for a in alle),
        # Nicht zugestellte Bestätigungen: wer keine bekommen hat, hat auch
        # keinen Link zum Ändern und Absagen und muss angerufen werden.
        mail_fehler=[
            a for a in alle if (a.get("mail") or {}).get("stand") == "fehlgeschlagen"
        ],
        zahlungsprobleme=[a for a in alle if a.get("zahlungsprobleme")],
        zu_erstatten=[a for a in alle if zahlstand(a)["zuviel"] > 0],
        postausgang_fehlt=postausgang_fehlt(stand["opt"]),
        **stand,
    )


def _zahlungen_aendern(anmeldung_id, aenderung):
    """Ändert die Zahlungsliste einer Anmeldung unter Sperre. "aenderung"
    bekommt den Datensatz und gibt zurück, ob sich etwas geändert hat."""
    with _lock:
        daten = _lesen()
        eintrag = _suchen(daten, anmeldung_id)
        if eintrag is not None and aenderung(eintrag):
            _schreiben(daten)
            _nachbereiten(sensor_aktualisieren)
    return redirect(url_for("verwaltung"))


def _jetzt():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@app.post("/verwaltung/bar/<anmeldung_id>")
def bar_bezahlt(anmeldung_id):
    """Den offenen Betrag als bar bezahlt vermerken."""

    def aenderung(eintrag):
        offen = zahlstand(eintrag)["offen"]
        if offen <= 0:
            return False
        eintrag.setdefault("zahlungen", []).append(
            {"art": "bar", "betrag_cent": offen, "zeit": _jetzt()}
        )
        return True

    return _zahlungen_aendern(anmeldung_id, aenderung)


@app.post("/verwaltung/bar/<anmeldung_id>/zuruecknehmen")
def bar_zuruecknehmen(anmeldung_id):
    """Barzahlungen wieder austragen - etwa nach einem Klick in die falsche
    Zeile. PayPal-Zahlungen bleiben unberührt."""

    def aenderung(eintrag):
        vorher = eintrag.get("zahlungen") or []
        nachher = [z for z in vorher if z.get("art") != "bar"]
        eintrag["zahlungen"] = nachher
        return len(nachher) != len(vorher)

    return _zahlungen_aendern(anmeldung_id, aenderung)


@app.post("/verwaltung/erstattung/<anmeldung_id>")
def erstattung_vermerken(anmeldung_id):
    """Vermerkt, dass die Orga zu viel Bezahltes zurückgegeben hat. Die
    Erstattung selbst - in PayPal oder bar - läuft außerhalb dieser Seite."""

    def aenderung(eintrag):
        zuviel = zahlstand(eintrag)["zuviel"]
        if zuviel <= 0:
            return False
        eintrag.setdefault("zahlungen", []).append(
            {"art": "erstattung", "betrag_cent": -zuviel, "zeit": _jetzt()}
        )
        return True

    return _zahlungen_aendern(anmeldung_id, aenderung)


@app.post("/verwaltung/problem/<anmeldung_id>/erledigt")
def problem_erledigt(anmeldung_id):
    """Vermerkte Zahlungsprobleme ausblenden, wenn die Orga sie geklärt hat."""

    def aenderung(eintrag):
        if not eintrag.get("zahlungsprobleme"):
            return False
        eintrag.setdefault("geklaerte_zahlungsprobleme", []).extend(
            eintrag.pop("zahlungsprobleme")
        )
        return True

    return _zahlungen_aendern(anmeldung_id, aenderung)


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
            ereignis_senden(f"{EREIGNIS}_absage", _ereignis_daten(entfernt))

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
# - oder @ beginnt. Name und Anmerkung tippen die Gäste selbst - ein
# vorangestelltes Hochkomma macht daraus wieder gewöhnlichen Text.
CSV_FORMELZEICHEN = ("=", "+", "-", "@", "\t", "\r", "\n")


def _csv_feld(wert):
    text = "" if wert is None else str(wert)
    return "'" + text if text.startswith(CSV_FORMELZEICHEN) else text


@app.get("/verwaltung/anmeldungen.csv")
def csv_export():
    stand = lage()
    opt = stand["opt"]
    alle = stand["daten"]["anmeldungen"]
    # Spalten für Essen und Getränke nur, wenn es die Listen gibt. Gerichte,
    # die schon bestellt, aber inzwischen aus den Optionen gestrichen sind,
    # behalten ihre Spalte.
    gerichte = list(opt["essen"])
    for a in alle:
        gerichte += [g for g in als_mengen(a.get("essen")) if g not in gerichte]
    getraenke = list(opt["getraenke"])
    for a in alle:
        getraenke += [g for g in als_liste(a.get("getraenke")) if g not in getraenke]

    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    kopf = (["Status", "Name", "Mitglieder", "Nichtmitglieder", "Kinder", "Personen",
             "Betrag (€)", "Bezahlt (€)", "Offen (€)", "Zu erstatten (€)",
             "Zahlungsart", "PayPal-Capture-ID", "Bezahlt am"]
            + gerichte + getraenke
            + ["Anmerkung", "E-Mail", "Bestätigungsmail", "Eingang", "Abgesagt am"])
    schreiber.writerow(kopf)
    # Abgesagte stehen mit drin, aber deutlich als solche - so lässt sich in
    # Excel filtern und man sieht trotzdem, wer abgesprungen ist.
    for a in sorted(alle, key=lambda x: x.get("zeit", "")):
        gewaehlt_essen = als_mengen(a.get("essen"))
        gewaehlt_trinken = als_liste(a.get("getraenke"))
        geld = zahlstand(a)
        arten = []
        for z in geld["zahlungen"]:
            art = ZAHLARTEN.get(z.get("art"), z.get("art", ""))
            if art not in arten:
                arten.append(art)
        # "Bezahlt am" ist die letzte echte Zahlung, nicht eine Erstattung.
        eingaenge = [z for z in geld["zahlungen"] if int(z.get("betrag_cent", 0)) > 0]
        zeile = (
            ["abgesagt" if a.get("abgesagt") else "angemeldet",
             a.get("name", ""), a.get("mitglieder", 0), a.get("nichtmitglieder", 0),
             a.get("kinder", 0), a.get("personen", 0),
             euro_zahl(geld["betrag"]), euro_zahl(geld["bezahlt"]),
             euro_zahl(geld["offen"]), euro_zahl(geld["zuviel"]),
             ", ".join(arten),
             ", ".join(z["capture_id"] for z in geld["zahlungen"] if z.get("capture_id")),
             eingaenge[-1].get("zeit", "") if eingaenge else ""]
            + [gewaehlt_essen.get(g, 0) for g in gerichte]
            + ["ja" if g in gewaehlt_trinken else "" for g in getraenke]
            + [a.get("anmerkung", ""), a.get("email", ""),
               (a.get("mail") or {}).get("stand", ""), a.get("zeit", ""),
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


ERGAENZUNGSSTRICH = re.compile(r"(?<=\s)-(?=\w)")


@app.template_filter("zeilen")
def zeilen(text):
    """Einzeiliges Feld, mehrzeiliger Text.

    Die Eingabefelder in der Add-on-Oberfläche sind einzeilig. Ein Impressum
    oder ein eigener Rechtstext braucht aber Umbrüche. Wie schon beim Ablauf
    gilt deshalb der senkrechte Strich als Zeilenwechsel - echte Umbrüche aus
    der YAML-Ansicht bleiben natürlich erhalten.
    """
    teile = []
    for zeile in (text or "").splitlines():
        teile.extend(zeile.split("|"))
    ergebnis = "\n".join(t.strip() for t in teile if t.strip())
    # "Kameradinnen und -kameraden": Nach dem Strich darf der Browser umbrechen,
    # dann steht "und -" allein am Zeilenende. Ein Wortverbinder hält den
    # Strich am Wort.
    return ERGAENZUNGSSTRICH.sub("-\u2060", ergebnis)


# Beträge in den Vorlagen: {{ eintrag.betrag_cent | euro }}. Gerechnet wird
# hier in server.py, die Vorlagen schreiben nur.
app.add_template_filter(euro, "euro")


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
        # 16 Threads: die Seite rechnet fast nichts, sie wartet höchstens auf
        # die Platte. Mehr Threads heißt mehr gleichzeitige Gäste ohne Schlange.
        # connection_limit: waitress nimmt sonst ab 100 offenen Verbindungen
        # keine neuen mehr an - beim Lasttest mit 200 Gleichzeitigen war das
        # der einzige Engpass. Mehr offene Verbindungen kosten nur Speicher.
        kwargs={"host": "0.0.0.0", "port": PUBLIC_PORT, "threads": 16,
                "connection_limit": 500, "ident": None},
        daemon=True,
    )
    oeffentlich.start()
    print(
        f"[anmeldung] öffentlich auf Port {PUBLIC_PORT}, "
        f"Verwaltung über Ingress auf Port {INGRESS_PORT}",
        flush=True,
    )
    serve(app, host="0.0.0.0", port=INGRESS_PORT, threads=4, ident=None)


if __name__ == "__main__":
    main()
