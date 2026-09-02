# Gedenkveranstaltung Anmeldung

Eine schlichte Anmeldeseite mit begrenzter Platzzahl. Gäste tragen sich ohne
Login ein, die Organisation sieht die Liste in Home Assistant.

## Was das Add-on startet

| Zweck | Erreichbar über |
| --- | --- |
| Öffentliche Anmeldeseite | `http://<home-assistant>:8080` |
| Verwaltung (Liste, CSV, öffnen/schließen) | Seitenleiste in Home Assistant |

Die Verwaltung ist **nur** über Ingress erreichbar. Wer die Adresse auf Port
8080 aufruft, bekommt für `/verwaltung` eine 404 zurück.

## Ablauf für die Gäste

1. Startseite: Titel, Datum, Ort, Gedenktext und wie viele Plätze noch frei sind.
2. Anmeldung: Name, Anzahl Personen, Essen und Getränke, optionale Anmerkung.
3. Bestätigung mit Zusammenfassung der Anmeldung.

Essen und Getränke werden unterschiedlich abgefragt:

* **Essen** in Stück je Gericht — für den Einkauf. Zwei Weißwürste für eine
  Person sind also ausdrücklich möglich; abgelehnt werden erst offensichtliche
  Zahlendreher (mehr als zehn Stück je angemeldeter Person).
* **Getränke** nur als Häkchen, für den groben Überblick. Keine Mengen.

Auf die Platzzahl zählt allein die Anzahl der Personen.

Sind alle Plätze vergeben oder ist die Anmeldung geschlossen, zeigt die
Startseite das statt des Formulars an — das Formular ist dann auch direkt
nicht mehr erreichbar.

## Einstellungen

| Option | Bedeutung |
| --- | --- |
| `untertitel` | Kleine Zeile über der Überschrift |
| `titel` | Überschrift der Seite |
| `datum` | Frei formulierbar, z. B. `Samstag, 14. September 2026` |
| `uhrzeit` | Z. B. `9:30` — wird als `ab 9:30 Uhr` angezeigt |
| `ort` | Z. B. `Schulturnhalle, Lehrberg` |
| `text` | Gedenktext. Leerzeilen ergeben Absätze |
| `plaetze_gesamt` | Obergrenze über alle Anmeldungen zusammen |
| `max_personen_pro_anmeldung` | Bremse gegen Zahlendreher |
| `anmeldeschluss` | Nur ein Hinweis unter dem Knopf, schließt nichts automatisch |
| `kontakt` | Name und Telefonnummer für Rückfragen und Absagen |
| `essen` | Liste der Gerichte zur Auswahl |
| `getraenke` | Liste der Getränke zur Auswahl |
| `anmeldung_offen` | Hauptschalter. Aus = keine Anmeldung möglich |
| `datenschutz_hinweis` | Kleingedrucktes unter dem Absende-Knopf |
| `sensor_erstellen` | Legt `sensor.gedenkveranstaltung_freie_plaetze` an |
| `benachrichtigung_dienst` | Notify-Dienst für Nachrichten, leer = aus |
| `benachrichtigung_jede_anmeldung` | Nachricht bei jeder einzelnen Anmeldung |
| `benachrichtigung_schwellen` | Belegte Plätze als Text, z. B. `60, 100`. Leer = aus |

Leere Felder werden auf der Seite weggelassen — es steht also nie ein leerer
Platzhalter herum. Änderungen an den Optionen greifen nach dem Neustart des
Add-ons.

Gerichte und Getränke können nachträglich ergänzt werden. Umbenennen oder
Löschen eines Eintrags ändert **nicht** die bereits gespeicherten Anmeldungen:
alte Bestellungen behalten den alten Namen und tauchen dann nicht mehr in den
Summen auf. Vor dem ersten Aushang die Liste also festzurren.

## Verwaltung

* **CSV herunterladen** — Semikolon-getrennt und mit BOM, öffnet sich in Excel
  ohne Umlautsalat. Je Gericht eine Spalte mit der Stückzahl, je Getränk eine
  Spalte mit `ja` wo angekreuzt.
* **Anmeldung schließen** — sofort wirksam, jederzeit wieder zu öffnen. Der
  Schalter ist unabhängig von der Option `anmeldung_offen`.
* **Löschen** — für Absagen. Der Platz wird sofort wieder frei.

## Benachrichtigungen

Zwei Wege, die sich auch kombinieren lassen.

### Direkt aus dem Add-on

In `benachrichtigung_dienst` den Namen eintragen, unter dem dein Handy in Home
Assistant erreichbar ist — etwa `notify.mobile_app_dein_handy`,
`notify.handy_cedric` oder `persistent_notification.create`. Beides geht: eine
klassische Aktion und eine Notify-Entität neuerer Installationen; das Add-on
probiert erst die Aktion und dann `notify.send_message`. Leer lassen schaltet
die Nachrichten ab.

Kommt nichts an, steht der Grund im Log des Add-ons. Den richtigen Namen zeigt
**Entwicklerwerkzeuge → Aktionen** (dort nach `notify` suchen); dort lässt sich
auch gleich eine Testnachricht schicken.

```yaml
benachrichtigung_dienst: notify.mobile_app_dein_handy
benachrichtigung_jede_anmeldung: true
benachrichtigung_schwellen: "60, 100"
```

* `benachrichtigung_jede_anmeldung` meldet jede einzelne Anmeldung mit Name,
  Personenzahl, Bestellung und den verbleibenden Plätzen.
* `benachrichtigung_schwellen` ist ein einfaches Textfeld: Zahlen mit Komma
  oder Leerzeichen getrennt. Gemeldet wird, sobald die Zahl der **belegten
  Plätze** eine dieser Marken überschreitet — je Marke genau einmal. Leer
  lassen heißt: keine Schwellenmeldungen.
* Ist der letzte Platz vergeben, kommt immer eine Nachricht, unabhängig von
  den beiden Schaltern.

Schlägt der Versand fehl, steht das im Log des Add-ons. Die Anmeldung des
Gastes geht trotzdem durch — der Versand läuft im Hintergrund.

### Über eigene Automatisierungen

Das Add-on löst zwei Events aus:

| Event | Daten |
| --- | --- |
| `gedenkveranstaltung_anmeldung` | `name`, `personen`, `essen`, `getraenke`, `anmerkung`, `anmeldungen`, `belegte_plaetze`, `freie_plaetze`, `ausgebucht` |
| `gedenkveranstaltung_absage` | `name`, `personen` |

Nachricht bei jeder Anmeldung:

```yaml
automation:
  - alias: Neue Anmeldung
    triggers:
      - trigger: event
        event_type: gedenkveranstaltung_anmeldung
    actions:
      - action: notify.mobile_app_dein_handy
        data:
          title: Neue Anmeldung
          message: >-
            {{ trigger.event.data.name }} mit {{ trigger.event.data.personen }}
            Personen. Noch {{ trigger.event.data.freie_plaetze }} Plätze frei.
```

Für Schwellen ist der Sensor der bessere Auslöser — `numeric_state` meldet sich
nur beim Überschreiten, nicht bei jeder weiteren Anmeldung:

```yaml
  - alias: Nur noch 20 Plätze
    triggers:
      - trigger: numeric_state
        entity_id: sensor.gedenkveranstaltung_freie_plaetze
        below: 20
    actions:
      - action: notify.mobile_app_dein_handy
        data:
          message: "Nur noch 20 Plätze frei."
```

Absage, damit jemand hinterhertelefonieren kann:

```yaml
  - alias: Absage eingegangen
    triggers:
      - trigger: event
        event_type: gedenkveranstaltung_absage
    actions:
      - action: notify.mobile_app_dein_handy
        data:
          message: >-
            Absage: {{ trigger.event.data.name }},
            {{ trigger.event.data.personen }} Personen.
```

## Sensor

Bei `sensor_erstellen: true` schreibt das Add-on nach jeder Änderung
`sensor.gedenkveranstaltung_freie_plaetze` in Home Assistant. Zustand ist die
Zahl der freien Plätze, dazu kommen als Attribute `plaetze_gesamt`,
`belegte_plaetze`, `anmeldungen`, `anmeldung_offen`, `essen` und `getraenke`.
`essen` zählt die bestellten Stück, `getraenke` die Personen, in deren
Anmeldung das Getränk angekreuzt ist.

Damit lässt sich zum Beispiel eine Benachrichtigung bauen:

```yaml
automation:
  - alias: Letzte Plätze
    triggers:
      - trigger: numeric_state
        entity_id: sensor.gedenkveranstaltung_freie_plaetze
        below: 10
    actions:
      - action: notify.persistent_notification
        data:
          message: "Nur noch {{ states('sensor.gedenkveranstaltung_freie_plaetze') }} Plätze frei."
```

Der Sensor wird über die States-API gesetzt. Er verschwindet daher beim
Neustart von Home Assistant und wird beim nächsten Start des Add-ons oder bei
der nächsten Anmeldung neu geschrieben.

## Daten

Alle Anmeldungen liegen in `/data/anmeldungen.json` im Add-on. Sie sind damit
Teil der Home-Assistant-Backups. Beim Deinstallieren des Add-ons werden sie
gelöscht — vorher CSV exportieren.

## Die Seite von außen erreichbar machen

Das Add-on selbst kümmert sich nicht um Zertifikate oder Portfreigaben. Ohne
Weiterleitung ist die Seite nur im Heimnetz erreichbar — für einen Aushang mit
QR-Code im Dorf reicht das nicht.

Hier läuft die Veröffentlichung über das **Cloudflare-Tunnel-Add-on**. Dort
einen zusätzlichen Hostname auf dieses Add-on zeigen lassen:

```yaml
additional_hosts:
  - hostname: anmeldung.deine-domain.de
    service: http://1a2b3c4d-gedenkveranstaltung:8080
```

`1a2b3c4d-gedenkveranstaltung` ist ein **Beispiel** und muss ersetzt werden.
Der Servicename ist der volle Slug dieses Add-ons, mit Bindestrichen statt
Unterstrichen. Den vollen Slug zeigt die Adresszeile, wenn die Add-on-Seite
geöffnet ist:

```
http://homeassistant.local:8123/hassio/addon/1a2b3c4d_gedenkveranstaltung/info
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

Aus `1a2b3c4d_gedenkveranstaltung` wird also `1a2b3c4d-gedenkveranstaltung`.
Bei einem lokal installierten Add-on (Ordner unter `/addons`) lautet der Slug
`local_gedenkveranstaltung` und der Servicename `local-gedenkveranstaltung`.

Funktioniert das nicht, tut es auch die IP von Home Assistant — Port 8080 ist
auf dem Host veröffentlicht:

```yaml
    service: http://192.168.1.10:8080
```

Das Add-on muss dabei **laufen**. Ist es gestoppt, gibt es keinen DNS-Eintrag
und cloudflared meldet `no such host`.

Danach im Cloudflare-Dashboard prüfen, dass der Hostname auf den Tunnel zeigt,
und das Tunnel-Add-on neu starten. Die Verwaltung bleibt außen vor: sie hängt
an Port 8099 und ist nur über Home Assistant erreichbar — den Port also **nicht**
in den Tunnel legen.
