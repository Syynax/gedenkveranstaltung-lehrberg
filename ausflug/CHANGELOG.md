# Änderungen

## 1.3.1

- **GiroCode als Bild.** Am Handy lässt sich der QR-Code auf dem eigenen
  Bildschirm nicht scannen. Unter dem Code gibt es jetzt „QR-Code als Bild
  speichern“ und, wo der Browser es kann, „Teilen“; die Banking-App liest das
  Bild aus der Galerie. Neue Adresse `/anmeldung/<id>/girocode.png` (PNG, nur
  mit der Anmelde-ID erreichbar, immer der offene Betrag; 404, wenn nichts zu
  überweisen ist).

## 1.3.0

- **Überweisung per GiroCode als zusätzlicher, gleichberechtigter Bezahlweg.**
  Neue Optionen `iban`, `kontoinhaber` und `bic` (nur außerhalb des
  SEPA-Raums). Auf der Bestätigungsseite steht der QR-Code (EPC-Standard,
  Version 002, Fehlerkorrektur M) mit dem **offenen** Betrag; die Banking-App
  füllt Empfänger, IBAN, Betrag und Verwendungszweck („Titel - Name“) selbst
  aus. Darunter dieselben Angaben als Text, jede mit „Kopieren“-Knopf. Der
  Code entsteht auf dem Server mit der Bibliothek `segno` (reines Python,
  neue Abhängigkeit) und steht als SVG in der Seite, ohne externen Dienst.
- **Die Gäste wählen:** Sind Überweisung und PayPal eingerichtet, stehen zwei
  Karten nebeneinander (am Handy untereinander). Ist nur eines eingerichtet,
  steht nur dieses da; ist nichts eingerichtet, gilt wie bisher
  `zahlung_hinweis`. Welche PayPal-Variante gilt, bleibt bei der alten
  Vorrangliste.
- **Prüfung:** Die IBAN wird auf Aufbau, Länge und Prüfziffer (Mod 97)
  kontrolliert, der Kontoinhaber ist Pflicht, die BIC muss 8 oder 11 Zeichen
  haben. Fehler stehen als rote Meldung in der Verwaltung; dann gibt es keine
  Überweisung. Eingerichtet zeigt die Verwaltung eine Info mit der IBAN.
- Die Bestätigungsmail nennt Empfänger, IBAN, Betrag und Verwendungszweck und
  verweist (mit `oeffentliche_adresse`) auf den QR-Code auf der
  Anmeldeseite. Sind beide Wege eingerichtet, steht die Überweisung vor PayPal.
- Alle „Kopieren“-Knöpfe der Bestätigungsseite funktionieren mit einem
  gemeinsamen Skript; die Rückmeldung „Kopiert“ erscheint am Knopf selbst.
- Das Formular nennt die Überweisung im Hinweis unter dem Preis, die
  Datenschutzvorlage hat einen Absatz „Bezahlung per Überweisung“, und die
  Beschreibung der Optionen `zahlung_hinweis` und `datenschutz` ist angepasst.

## 1.2.0

- **Dritte Bezahlvariante: Link über die E-Mail-Adresse.** Neue Option
  `paypal_email` (Adresse des PayPal-Kontos). Der Gast bekommt den Knopf „Mit
  PayPal bezahlen“; Betrag, Verwendungszweck (Titel – Name) und Anmelde-ID
  (als Artikelnummer) sind im Link schon eingetragen, ein Kopierfeld entfällt.
  PayPal wertet es als Kauf, der Empfänger zahlt Gebühren; ob es mit einem
  Privatkonto klappt, bitte mit einer Testzahlung prüfen.
- **Vorrang:** Client-ID und Secret, dann `paypal_me`, dann `paypal_email`,
  dann `zahlung_hinweis`. Eine ungültige Adresse steht als rote Meldung in der
  Verwaltung; dann gibt es keinen Link.
- Bestätigungsmail, Seitentext und Datenschutzvorlage kennen die neue Variante.

## 1.1.0

- **Bezahlen ohne Geschäftskonto: PayPal.me.** Neue Option `paypal_me` (Name
  oder Link, z. B. „paypal.me/feuerwehrlehrberg“). Der Gast sieht den offenen
  Betrag, die Mitteilung zum Kopieren („Titel – Name der Anmeldung“) und den
  Knopf „Mit PayPal bezahlen“, der einen PayPal.me-Link mit eingetragenem
  Betrag öffnet. Der Betrag kommt immer vom Server; nach einer Teilzahlung
  steht der Rest im Link. Die Mitteilung kann PayPal.me nicht vorausfüllen,
  deshalb das Kopierfeld.
- **Vorrang:** Sind Client-ID und Secret gesetzt, gilt wie bisher der
  PayPal-Knopf. Sonst gilt PayPal.me, sonst der Hinweis `zahlung_hinweis`.
- Die Bestätigungsmail enthält bei PayPal.me Betrag, Mitteilung und den
  direkten Link. Ein ungültiger Name in `paypal_me` steht als rote Meldung in
  der Verwaltung; dann gibt es keinen Link.
- Verwaltung: „Als bezahlt markieren“ statt „Als bar bezahlt markieren“, denn
  bei PayPal.me wird nach dem Abgleich in PayPal von Hand abgehakt. Gespeicherte
  Zahlungen bleiben unverändert lesbar.
- Datenschutzvorlage gilt für beide Varianten; bei PayPal.me geht nichts von
  der Seite an PayPal.

## 1.0.1

- Neuer Standardtext für die Startseite: Weihnachtsmarkt in Ulm, am Abend
  gemeinsames Essen in einem Lokal auf der Rückfahrt. Wer das Add-on schon
  installiert hat, behält seinen gespeicherten Text und trägt den neuen in
  der Konfiguration unter „Text“ ein.

## 1.0.0

Erste Fassung, entstanden aus der Anmeldung zur Gedenkveranstaltung (1.13.0).
Aufbau, Verwaltung, Mail, Sensor, CSV-Export, Testsperre und Gestaltung sind
von dort übernommen; neu sind Preise und die Zahlung per PayPal.

- **Eigenes Add-on neben der Gedenkveranstaltung:** Slug `ausflug`, Gästeseite
  auf Port 8081, in der Seitenleiste „Ausflug“. Alle Angaben zum Ausflug sind
  Platzhalter: Titel „Vereinsausflug der Feuerwehr Lehrberg“, Datum, Abfahrt,
  Treffpunkt und das neue Feld **Ziel** sind leer.
- **Mitglieder und Nichtmitglieder:** Im Formular stehen statt einer
  Personenzahl zwei Mengenfelder mit Einzelpreis, darunter der Gesamtbetrag,
  der beim Tippen mitläuft. Auf die Plätze und auf die Höchstzahl je Anmeldung
  zählt die Summe, mindestens eine Person muss dabei sein.
- **Preise** `preis_mitglied` und `preis_nichtmitglied` in Euro, eingetragen
  wie man sie schreibt („15“, „15,50“, „15.50“). Gerechnet wird in ganzen Cent,
  und der Betrag entsteht immer auf dem Server — was der Browser schickt, wird
  nicht übernommen. Ein unlesbarer Preis steht als rote Meldung in der
  Verwaltung.
- **Zahlung per PayPal** (Checkout-Knopf, Orders API v2) auf der
  Bestätigungsseite, erreichbar auch später über den Link „Jetzt bezahlen“ in
  der Mail. Der Server legt die Order über den offenen Betrag an, bucht nach
  der Freigabe ab und prüft Status, Betrag, Währung und Zugehörigkeit, bevor er
  die Zahlung mit Capture-ID verbucht. Doppelklick, zweiter Tab und Neuladen
  buchen nichts doppelt. Neue Optionen `paypal_client_id`, `paypal_secret`,
  `paypal_modus` (sandbox/live) und `zahlung_hinweis` für den Fall ohne
  PayPal.
- **Änderung nach der Zahlung:** Steigt der Betrag, ist der Rest offen und per
  PayPal nachzahlbar. Sinkt er oder wird abgesagt, zeigt die Verwaltung den
  Betrag zum Erstatten und es kommt eine Nachricht; erstattet wird von Hand.
- **Verwaltung:** Summen erwartet, eingegangen und offen; je Anmeldung
  Mitglieder, Nichtmitglieder, Betrag, Zahlungsstand und Capture-ID. Knöpfe
  „Als bar bezahlt markieren“, „Barzahlung zurücknehmen“, „Erstattung
  vermerken“ und „Als geklärt markieren“ für nicht verbuchte Zahlungen.
- **CSV** mit den Spalten Mitglieder, Nichtmitglieder, Betrag, Bezahlt, Offen,
  Zu erstatten, Zahlungsart, PayPal-Capture-ID und Bezahlt am.
- **Mail** mit Aufteilung, Gesamtbetrag, Zahlungsstand und Bezahl-Link; nach
  einer Zahlung eine kurze Mail „Zahlung erhalten“.
- **Sensor** `sensor.ausflug_freie_plaetze` mit den Attributen
  `summe_erwartet`, `summe_eingegangen`, `summe_offen`, `summe_zu_erstatten`,
  `mitglieder`, `nichtmitglieder` und `anmeldungen_bezahlt`. Events heißen
  `ausflug_anmeldung`, `ausflug_aenderung`, `ausflug_absage` und neu
  `ausflug_zahlung`.
- **Essen und Getränke** sind optional und standardmäßig leer. Ohne Listen
  verschwindet der Bestellabschnitt aus Formular, Mail, Verwaltung und CSV,
  und das Formular steht auch am Rechner in einer Spalte.
- **Datenschutz:** Die eingebaute Erklärung nennt die Mitgliedsangabe, Betrag
  und Zahlungsstand und — sobald PayPal eingerichtet ist — die Weitergabe an
  PayPal.
