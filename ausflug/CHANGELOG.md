# Änderungen

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
