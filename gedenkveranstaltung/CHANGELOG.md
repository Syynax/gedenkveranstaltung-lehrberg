# Änderungen

## 1.3.3

- Das Add-on schreibt bei jeder Anmeldung eine Logzeile mit belegten Plätzen,
  eingestellten Schwellen und den davon erreichten. Vorher war nicht zu sehen,
  ob eine Schwelle einfach noch nicht erreicht war.

## 1.3.2

- Nachrichten gehen jetzt auch an eine **Notify-Entität** (`notify.send_message`),
  nicht nur an eine klassische Aktion. Vorher gab es in dem Fall nur ein
  `HTTP Error 400` im Log.
- Fehler von Home Assistant werden mit Begründung geloggt statt nur mit dem
  Statuscode.

## 1.3.1

- `benachrichtigung_schwellen` ist jetzt ein Textfeld (`60, 100`) statt einer
  Zahlenliste. Die Liste ließ sich in der Add-on-Konfiguration nicht speichern
  ("Invalid list for option"). Eine bereits gespeicherte Liste wird weiterhin
  verstanden.

## 1.3.0

- Benachrichtigungen: Das Add-on kann bei jeder Anmeldung und beim Erreichen
  eingestellter Schwellen eine Nachricht über einen Notify-Dienst schicken.
  Neue Optionen `benachrichtigung_dienst`, `benachrichtigung_jede_anmeldung`
  und `benachrichtigung_schwellen`.
- Neue Events `gedenkveranstaltung_anmeldung` und `gedenkveranstaltung_absage`
  für eigene Automatisierungen.
- Sensor, Events und Nachrichten laufen im Hintergrund — der Gast wartet nicht
  mehr auf Home Assistant.

## 1.2.0

- Startseite: Termin und Ort stehen in einer eigenen Karte, der Anmeldeschluss
  als hervorgehobener Block darunter, dazu die Kontaktzeile.
- Neuer Standardtext, passend zum Vormittag mit gemeinsamem Frühstück.
- Voreingestellte Uhrzeit 9:30, Anzeige als `ab 9:30 Uhr`.
- Essen wird in **Stück** abgefragt. Die Zahl ist nicht mehr an die
  Personenzahl gekoppelt — zwei Weißwürste für eine Person gehen also.

## 1.1.0

- Essen wird mit Anzahl je Gericht abgefragt, Getränke nur noch als Häkchen
  für den groben Überblick.
- Startseite läuft nicht mehr über die volle Bildschirmhöhe: die Lücke in der
  Mitte und das Scrollen auf dem Handy sind weg, Überschriften skalieren mit
  der Breite.
- Verwaltung zeigt die bestellten Portionen und getrennt davon die
  Getränke-Nachfrage in Personen.
- CSV: je Gericht eine Zahlenspalte, je Getränk eine `ja`-Spalte.
- Anleitung für den Cloudflare-Tunnel: erklärt, woher der Servicename kommt.

## 1.0.0

- Erste Fassung: öffentliche Anmeldeseite, Verwaltung über Ingress, CSV-Export,
  Platzbegrenzung und Sensor für die freien Plätze.
