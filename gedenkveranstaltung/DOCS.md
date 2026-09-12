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

## So läuft die Anmeldung

1. Startseite: Titel, Datum, Ort, Gedenktext und wie viele Plätze noch frei sind.
2. Anmeldung: Name, Anzahl Personen, Essen und Getränke, optionale Anmerkung.
3. Bestätigung mit Zusammenfassung der Anmeldung.

Die Bestätigungsseite ist zugleich der persönliche Zugang zur Anmeldung: Von
dort lässt sie sich **ändern** oder **absagen**. Die Adresse enthält eine
zufällige, nicht erratbare Kennung — wer den Link hat, darf ändern. Wer eine
E-Mail angegeben hat, bekommt den Link zugeschickt; alle anderen sollten ihn
sich merken oder sich bei Rückfragen an die Kontaktperson wenden.

Eine Absage löscht nichts, sondern markiert die Anmeldung. Die Plätze werden
sofort wieder frei, in der Verwaltung bleibt die Zeile durchgestrichen stehen
und in der CSV steht sie mit dem Status `abgesagt`. So sieht die Organisation,
wer abgesprungen ist, statt dass jemand spurlos verschwindet.

Essen und Getränke werden unterschiedlich abgefragt:

* **Essen** in Stück je Gericht — für den Einkauf. Zwei Weißwürste für eine
  Person sind also ausdrücklich möglich; abgelehnt werden erst offensichtliche
  Zahlendreher (mehr als zehn Stück je angemeldeter Person).
* **Getränke** nur als Häkchen, für den groben Überblick. Keine Mengen.

Auf die Platzzahl zählt allein die Anzahl der Personen.

### Ablauf der Veranstaltung

Der Ablauf steht als eigener Kasten auf der Startseite. Ein Punkt je Zeile,
Uhrzeit und Text durch einen senkrechten Strich getrennt. In das Feld
`ablauf` gehört genau das hier — **ohne** `ablauf:` davor:

```
9:30 | Ankommen und Begrüßung
10:00 | Gedenken
10:30 | Gemeinsames Frühstück
12:30 | Ausklang
```

Statt einer Uhrzeit geht auch eine kurze Angabe wie `anschl.` oder `ca. 12:30`.

Soll nur der Beginn eine Uhrzeit tragen und der Rest keine, trennt ein
Semikolon die Punkte:

```
9:30 | Andacht; Rückblick auf den Einsatz; Weißwurstfrühstück; Ausklang
```

Das Semikolon ist dafür nötig, weil ein Punkt ohne Strich sonst nicht von der
Fortsetzung des vorigen zu unterscheiden wäre. Sobald ein einziger Punkt eine
Uhrzeit hat, bleibt die Spalte für alle stehen, damit die Texte untereinander
bündig sind.

Das Feld in der Add-on-Oberfläche ist einzeilig, alles landet also
hintereinander. Das macht nichts: vor jedem neuen Punkt wird automatisch
getrennt, und ein versehentlich mitkopiertes `ablauf: |-` wird entfernt. Ist das
Feld leer, entfällt der Kasten ganz.

### Handy und Rechner

Bis 820 Pixel Breite läuft alles untereinander: Überschrift, Termin, Text,
Ablauf, dann Plätze und Anmeldeknopf.

Darüber steht die Überschrift über die volle Breite, darunter links Text und
Ablauf, rechts Termin, freie Plätze, Anmeldeknopf und Anmeldeschluss als ein
Block, der beim Scrollen stehen bleibt. Auch das Anmeldeformular wird
zweispaltig: links Name, E-Mail, Personenzahl und Anmerkung, rechts Essen und
Getränke, der Absendeknopf darunter. Die Bestätigung bleibt schmal, die liest
sich so besser.

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
| `ort` | Z. B. `Feuerwehrgerätehaus Lehrberg` |
| `ablauf` | Programm des Vormittags, eine Zeile je Punkt. Leer = kein Ablauf |
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
| `oeffentliche_adresse` | Adresse der Seite von außen, z. B. `https://anmeldung.example.de` — für Links in Mails und die Vorschau beim Teilen |
| `impressum` | Anbieterkennzeichnung. Ein senkrechter Strich trennt die Zeilen. Erscheint unter /impressum und als Verantwortlicher im Datenschutz |
| `datenschutz` | Eigener Datenschutztext. Leer = die eingebaute Erklärung |
| `veranstalter` | Name unter der Bestätigungsmail, z. B. `Freiwillige Feuerwehr Lehrberg` |
| `loeschfrist` | Wann die Daten nach der Veranstaltung gelöscht werden, für die Datenschutzerklärung |
| `email_abfragen` | E-Mail-Feld im Formular anzeigen. Angeschaltet ist es ein Pflichtfeld |
| `smtp_server`, `smtp_port`, `smtp_verschluesselung` | Postausgang für Bestätigungsmails |
| `smtp_benutzer`, `smtp_passwort`, `smtp_absender` | Zugangsdaten und Absenderadresse |
| `smtp_antwort_an` | Adresse für Antworten der Gäste, falls die Absenderdomain kein Postfach hat |
| `nur_fuer_ip` | Zum Testen: Gästeseite nur für diese Adressen sichtbar. Leer = für alle |

Leere Felder werden auf der Seite weggelassen — es steht also nie ein leerer
Platzhalter herum. Änderungen an den Optionen greifen nach dem Neustart des
Add-ons.

Gerichte und Getränke können nachträglich ergänzt werden. Umbenennen oder
Löschen eines Eintrags ändert **nicht** die bereits gespeicherten Anmeldungen:
alte Bestellungen behalten den alten Namen und tauchen dann nicht mehr in den
Summen auf. Vor dem ersten Aushang die Liste also festzurren.

## Seite zum Testen sperren

Solange die Seite noch nicht ausgehängt ist, kann man sie hinter der Option
`nur_fuer_ip` verstecken: Steht dort etwas, bekommt **nur** diese Adresse die
Gästeseite zu sehen, alle anderen eine Seite „Noch nicht freigeschaltet"
(Status 503). Leeres Feld heißt: normal für alle offen.

```yaml
nur_fuer_ip: 84.123.45.67
```

Mehrere Einträge durch Komma oder Leerzeichen trennen. Neben einzelnen
Adressen gehen auch ganze Bereiche in CIDR-Schreibweise, IPv4 wie IPv6:

```yaml
nur_fuer_ip: 84.123.45.67, 91.0.0.0/8, 2001:db8::/32
```

Das ist praktisch, weil sich die Adresse am Hausanschluss bei jeder
Zwangstrennung ändert — mit dem passenden Bereich muss man nicht jedes Mal
nachtragen. Ein Eintrag, der keine Adresse ist, wird übergangen und im
Add-on-Protokoll vermerkt; die übrigen gelten weiter.

**Die eigene Adresse herausfinden:** Die Sperrseite zeigt sie unten an. Also:
Option auf einen Platzhalter wie `0.0.0.0` setzen, **Add-on neu starten**, die
Seite von außen über die öffentliche Adresse aufrufen, den angezeigten Wert
eintragen und wieder neu starten. Jeder abgewiesene Zugriff steht außerdem mit
Adresse und Pfad im Add-on-Protokoll.

> Wie alle Optionen greift auch diese erst nach einem Neustart des Add-ons —
> zwischen Speichern und Wirkung liegt immer ein Neustart.

Zu beachten:

* **Aus dem Heimnetz bleibt die Seite offen.** Gesperrt wird nur, was von außen
  kommt. Ein Aufruf im eigenen WLAN über `http://homeassistant.local:8080` zeigt
  also weiter die normale Seite — zum Prüfen der Sperre muss man über die
  öffentliche Adresse gehen, etwa vom Handy im Mobilfunknetz.
* **Die Adresse des Gastes kommt von Cloudflare.** Der Tunnel setzt dafür die
  Kopfzeile `Cf-Connecting-Ip`; ohne sie zählt schlicht, von wo die Verbindung
  kam. Andere Weiterleitungs-Kopfzeilen wertet das Add-on bewusst nicht aus,
  weil sie jeder selbst schreiben kann. Wer die Seite später über einen anderen
  Weg veröffentlicht — etwa das NGINX-Add-on auf demselben Rechner — sollte die
  Sperre vorher einmal von außen prüfen: Dann sieht der Server nur noch den
  Proxy und damit eine Adresse aus dem eigenen Netz, und die Sperre greift
  nicht mehr.
* **Der Watchdog läuft weiter.** Home Assistant prüft die Startseite
  regelmäßig; diese Prüfung kommt von innen und wird nicht gesperrt. Sonst
  würde das Add-on während der Testphase dauernd neu gestartet.
* **Die Verwaltung ist nie gesperrt.** Sie läuft über Home Assistant und bleibt
  auch dann erreichbar, wenn man sich mit einem Tippfehler von der Gästeseite
  aussperrt.
* **Impressum und Datenschutz sind mitgesperrt.** In der Testphase ist die
  Seite nicht öffentlich angeboten, das ist also in Ordnung — vor dem Aushang
  muss die Option aber leer sein.
* **Das ist eine Testsperre, kein Schutzwall.** Die Adresse kommt aus der
  Kopfzeile `Cf-Connecting-Ip`, die Cloudflare setzt. Wer das Add-on im
  Heimnetz direkt am Tunnel vorbei erreicht, kann diese Kopfzeile selbst
  setzen und damit vorbei. Für „die Seite soll noch niemand sehen" reicht es,
  für echten Zugriffsschutz nicht.

## Verwaltung

* **CSV herunterladen** — Semikolon-getrennt und mit BOM, öffnet sich in Excel
  ohne Umlautsalat. Je Gericht eine Spalte mit der Stückzahl, je Getränk eine
  Spalte mit `ja` wo angekreuzt.

  Beginnt ein Name oder eine Anmerkung mit `=`, `+`, `-` oder `@`, steht in der
  Datei ein Hochkomma davor: `'- Rollstuhl`. Das ist Absicht — Excel würde eine
  solche Zelle sonst als Formel ausrechnen, und was dort steht, tippen die
  Gäste. Das Hochkomma bleibt beim Öffnen sichtbar und gehört nicht zur
  Angabe.
* **Anmeldung schließen** — sofort wirksam, jederzeit wieder zu öffnen. Der
  Schalter ist unabhängig von der Option `anmeldung_offen`.
* **Löschen** — entfernt eine Anmeldung endgültig. Für Absagen ist das
  meistens nicht nötig: Sagt jemand selbst über seinen Link ab, bleibt die
  Zeile durchgestrichen stehen und der Platz ist trotzdem frei.

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

  Gezählt werden Personen über alle Anmeldungen hinweg, nicht die Anzahl der
  Anmeldungen. Bei `60, 100` und 200 Plätzen kommt die erste Meldung also erst,
  wenn die 60. Person angemeldet ist. Eine Marke, die schon überschritten war
  als du sie eingetragen hast, meldet sich nicht mehr. Zum Ausprobieren kurz
  eine `1` eintragen, Add-on neu starten, eine Testanmeldung machen.

  Bei jeder Anmeldung schreibt das Add-on eine Zeile ins Log, etwa
  `belegte Plätze 57 -> 67, Schwellen [60, 100], davon erreicht: [60]`. Damit
  ist immer klar, ob eine Marke bloß noch nicht erreicht ist.
* Ist der letzte Platz vergeben, kommt immer eine Nachricht, unabhängig von
  den beiden Schaltern.

Schlägt der Versand fehl, steht das im Log des Add-ons. Die Anmeldung des
Gastes geht trotzdem durch — der Versand läuft im Hintergrund.

### Über eigene Automatisierungen

Das Add-on löst zwei Events aus:

| Event | Daten |
| --- | --- |
| `gedenkveranstaltung_anmeldung` | `name`, `personen`, `essen`, `getraenke`, `anmerkung`, `anmeldungen`, `belegte_plaetze`, `freie_plaetze`, `ausgebucht` |
| `gedenkveranstaltung_aenderung` | `name`, `personen`, `essen`, `getraenke`, `anmerkung` |
| `gedenkveranstaltung_absage` | `name`, `personen`, `freie_plaetze` |

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

## Bestätigungsmail

Die E-Mail-Adresse ist ein Pflichtfeld, solange `email_abfragen` an ist.
Jeder Gast bekommt damit eine Bestätigung mit seinen Angaben, Datum und Ort
und den persönlichen Links zu seiner Anmeldung, und ihr könnt alle erreichen,
falls die Veranstaltung selbst verschoben werden muss. Dafür braucht das
Add-on einen Postausgang:

```yaml
email_abfragen: true
smtp_server: smtp.example.de
smtp_port: 587
smtp_verschluesselung: starttls
smtp_benutzer: anmeldung@example.de
smtp_passwort: "…"
smtp_absender: anmeldung@example.de
oeffentliche_adresse: https://anmeldung.example.de
```

* Bei den meisten Anbietern (GMX, web.de, Strato, IONOS, Gmail mit
  App-Passwort) ist es `587` mit `starttls`. Manche wollen `465` mit `ssl`.
* Bleibt `smtp_server` leer, wird keine Mail verschickt — das Feld im Formular
  gibt es trotzdem, solange `email_abfragen` an ist. Wer beides nicht will,
  schaltet `email_abfragen` aus.
* Der Versand läuft im Hintergrund. Klappt er nicht, steht der Grund im Log;
  die Anmeldung ist davon unabhängig gespeichert.
* Die Adresse wird nur für diese eine Mail verwendet und steht in der
  Verwaltung unter dem Namen sowie in der CSV.
* `smtp_antwort_an` setzen, wenn die Absenderdomain kein eigenes Postfach hat.
  Antworten der Gäste gehen dann an diese Adresse statt ins Leere.
* Die Mail geht als Text **und** als gesetzte HTML-Fassung raus. Beide kommen
  aus derselben Quelle; wessen Programm kein HTML anzeigt, sieht denselben
  Inhalt als Text. Geladen wird dabei nichts nach, auch keine Bilder.
* Unter der Mail steht `veranstalter`. Ist das Feld leer, wird die erste Zeile
  des Impressums genommen, aber nur wenn sie kurz genug für einen Namen ist —
  sonst steht dort „Das Organisationsteam“.

### Versanddienst statt eigenem Mailserver

Vom Heimanschluss aus lassen sich Mails praktisch nicht zustellen: Die IP steht
in der Spamhaus-PBL, ein passender Reverse-DNS-Eintrag fehlt, und viele
Anbieter sperren Port 25 ausgehend. Es gibt zwar ein gepflegtes
Mailserver-Add-on für Home Assistant (Postfix/Dovecot von Erik73), das
empfiehlt für den Ausgang aber selbst einen externen Smarthost.

Der einfache Weg ist ein Versanddienst wie SMTP2GO, Brevo oder der
Mailserver des Domain-Hosters. Beispiel SMTP2GO:

```yaml
smtp_server: mail.smtp2go.com
smtp_port: 587
smtp_verschluesselung: starttls
smtp_benutzer: "<SMTP-Benutzer aus dem SMTP2GO-Konto>"
smtp_passwort: "<zugehöriges Passwort>"
smtp_absender: anmeldung@eure-domain.de
smtp_antwort_an: vorstand@echtes-postfach.de
```

Wichtig: Die Absenderdomain muss beim Dienst **verifiziert** sein (ein paar
DNS-Einträge für DKIM). Ohne das greift ein vorhandener DMARC-Eintrag und die
Mails landen im Spam. Blockiert der Anschluss Port 587, geht bei SMTP2GO auch
Port 2525.

## Impressum und Datenschutz

Beide Seiten sind über die Fußzeile jeder öffentlichen Seite erreichbar.

* `impressum`: Vereinsname, Anschrift, Vertretung, Kontakt. Das Feld in der
  Oberfläche ist einzeilig, deshalb trennt ein senkrechter Strich die Zeilen:
  `Freiwillige Feuerwehr Lehrberg e. V. | Gartenstraße 3 | 91611 Lehrberg`.
  Haltet es kurz — Haftungsausschlüsse aus einem Impressum-Generator gehören
  nicht hierher, sie stehen sonst mit auf der Seite.
* `/datenschutz` zeigt ohne weiteres Zutun eine **eingebaute Erklärung**, die
  genau beschreibt, was dieses Add-on tut: welche Daten, wofür, Cloudflare als
  Durchleiter, keine Cookies, lokale Schriften, Löschfrist, Rechte der
  Betroffenen, Aufsichtsbehörde. Den Verantwortlichen holt sie aus dem
  Impressum. Wer einen eigenen Text will, trägt ihn in `datenschutz` ein.
* Die Schriften liegen im Add-on. Es wird nichts von Google nachgeladen — das
  Landgericht München hat das 2022 ohne Einwilligung als Datenschutzverstoß
  gewertet.

Das ist kein Rechtsrat. Vor dem offiziellen Start sollte jemand darüber
schauen — vor allem die Frage, ob der Verein (e.V.) oder die Feuerwehr als
gemeindliche Einrichtung die Seite betreibt. Davon hängen Impressum und
zuständige Aufsichtsbehörde ab.

## Andrang und Ausfallsicherheit

Die Seite rechnet fast nichts und hält Anmeldungen in einer kleinen Datei —
für einen Dorfstart mit ein paar hundert Besuchern in der ersten Stunde ist
das reichlich. Ein Lasttest auf einem PC (die echte Seite läuft auf dem
schwächeren Home-Assistant-Gerät, dort dauert alles entsprechend länger):

| Was | Ergebnis |
| --- | --- |
| 200 gleichzeitige Leser, 1 200 Seitenaufrufe | 985 Aufrufe/s, kein Fehler |
| 100 gleichzeitige Anmeldungen | alle angenommen, Summe stimmt exakt |
| 60 s Mischlast, 50 Leser und 10 Schreiber | 29 000 Aufrufe, kein Fehler |
| 200 gleichzeitige Anmeldungen auf 50 Plätze | genau 50 angenommen, 150 abgewiesen |

Was das Add-on dafür tut:

* **Watchdog**: Der Supervisor ruft die Startseite regelmäßig auf und startet
  das Add-on neu, wenn sie nicht mehr antwortet.
* **Cloudflare puffert** CSS, Schriften und Bilder einen Tag lang. Nur die
  Seiten selbst gehen bis zum Home Assistant durch.
* **Überbuchung ist ausgeschlossen**: Die letzten Plätze werden unter einer
  Sperre vergeben; gleichzeitige Anmeldungen können nicht über die
  Gesamtzahl hinaus.
* Sensor, Events, Nachrichten und Mails laufen im Hintergrund — der Gast
  wartet nie auf Home Assistant.

Was du zusätzlich tun kannst:

* Am Starttag **kein Home-Assistant-Update** und keinen Neustart einplanen.
* Bei Cloudflare unter *Security → WAF → Rate limiting rules* eine Regel
  anlegen, die pro IP mehr als etwa 10 Anmeldungen (POST auf `/anmeldung`)
  in 10 Sekunden blockt. Das hält Skripte fern, ohne echte Gäste zu stören.
* **Backups** in Home Assistant einschalten (Einstellungen → System →
  Backups → automatisch). Die Anmeldungen liegen in `/data` des Add-ons und
  sind damit im Backup.

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
