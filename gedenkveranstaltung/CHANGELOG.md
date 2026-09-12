# Änderungen

## 1.7.1

- Aufräumen an der Testsperre: Der Rückfall auf `X-Forwarded-For` war wirkungslos,
  weil waitress diese Kopfzeilen ohne `trusted_proxy` verwirft — er ist raus.
  Maßgeblich ist `Cf-Connecting-Ip` von Cloudflare; fehlt sie, zählt die
  tatsächliche Absenderadresse. Als „aus dem Haus" gilt jetzt nur noch eine
  private Adresse, nicht mehr jede Anfrage ohne Kopfzeile. Damit greift die
  Sperre auch bei einer direkten Portfreigabe am Router.

## 1.7.0

- Neue Option `nur_fuer_ip`: Zum Testen vor dem Aushang ist die Gästeseite nur
  noch für die eingetragenen Adressen sichtbar, alle anderen bekommen „Noch
  nicht freigeschaltet". Einzelne Adressen oder ganze Bereiche, IPv4 wie IPv6.
  Die Sperrseite zeigt die eigene Adresse an, damit man sie eintragen kann.
  Gesperrt wird nur, was von außen durch den Tunnel kommt — die Verwaltung,
  das Heimnetz und der Watchdog von Home Assistant bleiben erreichbar.
- Sicherheitslücke in der Verwaltung geschlossen: Ein Gästename mit
  Anführungszeichen konnte aus der Löschabfrage ausbrechen und beliebiges
  JavaScript im Browser der Orga ausführen. Der Name wird jetzt als Attribut
  übergeben statt in den Skripttext geschrieben.
- Die Kopfzeile `X-Ingress-Path` wird nur noch auf dem Ingress-Port und nur als
  einfacher Pfad ausgewertet. Vorher ließ sich damit von außen eine fremde
  Adresse in alle Links der Seite schieben.
- Der CSV-Export entschärft Formeln: Eine Zelle, die mit `=`, `+`, `-` oder `@`
  beginnt, bekommt ein Hochkomma davor. Ein Gästename wie `=HYPERLINK(…)` wurde
  sonst beim Öffnen der Datei in Excel ausgeführt.
- waitress von 3.0.0 auf 3.0.2. In 3.0.0 stecken zwei Schwachstellen
  (CVE-2024-49768, CVE-2024-49769), und der Port hängt öffentlich am Tunnel.
- Ein Altbestand ohne `id` führt nicht mehr zum Serverfehler auf der
  Bestätigungsseite und in der Verwaltung.

## 1.6.0

- **Selbst ändern und absagen**: Die Bestätigungsseite führt jetzt zu einem
  Formular zum Ändern und zu einer Absage mit Rückfrage. Die Links stehen auch
  in der Bestätigungsmail. Eine Absage gibt die Plätze sofort frei, löscht die
  Anmeldung aber nicht — in der Verwaltung bleibt sie durchgestrichen stehen,
  in der CSV mit dem Status `abgesagt`.
- Mails für Änderung und Absage, neue Events `gedenkveranstaltung_aenderung`
  und `gedenkveranstaltung_absage` (mit freien Plätzen).
- **Startseite neu aufgeteilt**: Die Überschrift steht über die volle Breite,
  darunter links Text und Ablauf, rechts Termin, Plätze und Anmeldeknopf. Die
  Spalten sind jetzt ausgewogen, statt dass rechts eine große leere Fläche
  blieb.
- Der Ablauf trennt auch vor Punkten ohne Uhrzeit, etwa `anschl. |`.

## 1.5.2

- Neue Option `smtp_antwort_an`: Antworten der Gäste gehen an eine echte
  Adresse, auch wenn die Absenderdomain kein Postfach hat.

## 1.5.1

- Nach dem Lasttest: bis zu 500 gleichzeitige Verbindungen statt 100 — mehr
  offene Verbindungen bedeuteten vorher nur Warten, jetzt auch das nicht.
- Wer im Wettlauf um die letzten Plätze verliert, sieht auf der Startseite
  einen klaren Hinweis statt nur „ausgebucht“.

## 1.5.0

- **Bestätigungsmail**: optionales E-Mail-Feld im Formular; wer es ausfüllt,
  bekommt Zusammenfassung, Termin und seinen persönlichen Link. Postausgang
  über die neuen `smtp_*`-Optionen.
- **Impressum und Datenschutz** als eigene Seiten mit Fußzeile. Der
  Datenschutztext ist eingebaut und beschreibt genau, was das Add-on tut;
  den Verantwortlichen holt er aus `impressum`.
- **Schriften liegen im Add-on**, kein Nachladen von Google mehr.
- **Watchdog**: Home Assistant startet das Add-on neu, wenn die Seite nicht
  mehr antwortet. Statische Dateien werden einen Tag lang gepuffert, mit
  Versionsstempel für sofortige Updates. 16 statt 8 Bearbeitungsthreads.
- **Vorschau beim Teilen** (WhatsApp, Signal): Titel, Beschreibung und
  Wappenbild über Open-Graph-Angaben. Dafür `oeffentliche_adresse` setzen.
- Aus der Durchsicht der Live-Seite: Fokusreihenfolge auf dem Handy stimmt
  wieder mit der Anzeige überein, Kontraste von Hilfetexten und Rändern
  angehoben, „Zurück“ als 44-Pixel-Klickfläche, toter Skriptrest entfernt,
  Halbgeviertstrich statt Geviertstrich.

## 1.4.1

- Der Ablauf verträgt jetzt auch einen Copy-Paste aus der Dokumentation:
  mehrere Punkte in einer Zeile werden vor jeder Uhrzeit getrennt, ein
  mitkopiertes `ablauf: |-` entfernt.
- Das Anmeldeformular ist am Rechner zweispaltig — links Name, Personenzahl
  und Anmerkung, rechts Essen und Getränke. Vorher eine lange Spalte.
- Sachlicherer Standardtext für die Startseite, mit mehr Inhalt zum Ablauf
  und dazu, wer eingeladen ist.

## 1.4.0

- Neue Option `ablauf`: Programm des Vormittags als eigener Kasten auf der
  Startseite, eine Zeile je Punkt (`9:30 | Ankommen`).
- Die Startseite ist ab 820 Pixel Breite zweispaltig — links der Text, rechts
  Plätze, Anmeldeknopf und Anmeldeschluss. Vorher war die Seite auch am
  Rechner eine schmale Handy-Spalte.
- Wappen der Feuerwehr Lehrberg als Favicon und als Add-on-Symbol.

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
