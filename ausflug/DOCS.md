# Ausflug Anmeldung

Eine Anmeldeseite für den Vereinsausflug, mit begrenzter Platzzahl, Preisen
für Mitglieder und Nichtmitglieder und Zahlung per Überweisung (GiroCode)
oder PayPal. Gäste tragen sich
ohne Login ein, die Organisation sieht die Liste samt Zahlungsstand in Home
Assistant.

Das Add-on ist aus der Anmeldung zur Gedenkveranstaltung entstanden und läuft
neben ihr: Die Gästeseite liegt hier auf Port **8081**, die der
Gedenkveranstaltung auf 8080.

## Was das Add-on startet

| Zweck | Erreichbar über |
| --- | --- |
| Öffentliche Anmeldeseite | `http://<home-assistant>:8081` |
| Verwaltung (Liste, Zahlungen, CSV, öffnen/schließen) | Seitenleiste in Home Assistant („Ausflug“) |

Die Verwaltung ist **nur** über Ingress erreichbar. Wer die Adresse auf Port
8081 aufruft, bekommt für `/verwaltung` eine 404 zurück.

## So läuft die Anmeldung

1. Startseite: Titel, Datum, Abfahrt, Treffpunkt, Ziel, Einladungstext, die
   Preise je Person und wie viele Plätze noch frei sind.
2. Anmeldung: Name, E-Mail, **Mitglieder**, **Nichtmitglieder** und
   **Kinder bis 14 Jahre** als drei Zahlen mit Plus und Minus, darunter der
   Gesamtbetrag, optional eine Anmerkung.
3. Bestätigung mit Zusammenfassung, Betrag und den eingerichteten Bezahlwegen:
   einem QR-Code für die Überweisung und/oder PayPal. Die Gäste wählen.

Die Bestätigungsseite ist zugleich der persönliche Zugang zur Anmeldung: Von
dort lässt sie sich **ändern**, **absagen** und **bezahlen**. Die Adresse
enthält eine zufällige, nicht erratbare Kennung — wer den Link hat, darf
ändern. Die Bestätigungsmail enthält diesen Link und einen eigenen Link
„Jetzt … € bezahlen“, solange etwas offen ist. Wer im ersten Anlauf nicht
bezahlt, kann das also später über die Mail nachholen.

Eine Absage löscht nichts, sondern markiert die Anmeldung. Die Plätze werden
sofort wieder frei, in der Verwaltung bleibt die Zeile durchgestrichen stehen
und in der CSV steht sie mit dem Status `abgesagt`.

### Personen und Plätze

* Auf die Platzzahl zählen Mitglieder, Nichtmitglieder und Kinder zusammen —
  auch ein kostenloses Kind belegt einen Sitzplatz.
* `max_personen_pro_anmeldung` gilt ebenfalls für die Summe aller drei.
* Mindestens eine **erwachsene** Person (Mitglied oder Nichtmitglied) muss
  angemeldet sein. Eine Anmeldung nur mit Kindern wird abgelehnt („Bitte
  mindestens eine erwachsene Person angeben.“), 0, 0 und 0 ebenso.
* Anmeldungen aus der Zeit vor 1.4.0 haben kein Feld `kinder`; sie zählen
  überall mit 0 Kindern.
* Ob jemand Mitglied ist, prüft die Seite nicht. Sie verlässt sich auf die
  Angabe des Gastes; die Verwaltung zeigt die Aufteilung je Anmeldung.

### Essen und Getränke (optional)

Für einen Ausflug sind die Listen `essen` und `getraenke` zunächst **leer**.
Dann gibt es im Formular, in der Mail, in der Verwaltung und in der CSV keinen
Bestellabschnitt, und das Formular steht auch am Rechner in einer Spalte.

Wer doch etwas vorbestellen lassen will — etwa die Brotzeit im Bus —, trägt
die Gerichte und Getränke ein:

```yaml
essen:
  - Brezen | Paar
  - Leberkässemmel
getraenke:
  - Wasser
  - Apfelschorle
```

Essen wird in Stück je Gericht abgefragt, Getränke nur als Häkchen. Hinter
einem Gericht legt `| Paar` einen Knopf an, der zwei auf einmal dazulegt
(`| Dutzend` legt zwölf dazu). Die Bestellung kostet nichts extra — der Betrag
ergibt sich allein aus den Personen.

### Ablauf des Ausflugs

Der Ablauf steht als Zeitstrahl auf der Startseite. Die Punkte werden durch
einen senkrechten Strich getrennt; eine Uhrzeit zwischen zwei Strichen gehört
zum nächsten Punkt:

```
7:00 | Abfahrt am Feuerwehrhaus | 10:00 | Führung | Mittagessen | 18:00 | Rückfahrt
```

Ohne Uhrzeiten geht es genauso. Ist das Feld leer, entfällt der Kasten.

## Preise und Beträge

```yaml
preis_mitglied: "15,00"
preis_nichtmitglied: "25,00"
preis_kind: "0"
```

* Eingetragen wird in Euro je Person, so wie man es schreibt: `15`, `15,5`,
  `15,50`, `15.50` und auch `15,00 €` gehen. Mehr als zwei Nachkommastellen
  oder Buchstaben gehen nicht — dann steht oben in der Verwaltung eine rote
  Meldung, und bis zur Korrektur gilt der Preis als 0 €.
* Intern wird **in ganzen Cent** gerechnet und gespeichert, nie mit
  Kommazahlen. So gibt es keine Rundungsfehler beim Aufsummieren.
* Der Betrag wird **immer auf dem Server** berechnet: Mitglieder × Preis für
  Mitglieder + Nichtmitglieder × Preis für Nichtmitglieder + Kinder × Preis
  für Kinder (Standard 0, dann heißt es überall „kostenlos“). Was der Browser als
  Summe anzeigt, ist nur Anzeige und wird beim Speichern nicht übernommen.
* An jeder Anmeldung stehen die Einzelpreise, die beim Speichern galten. Ändert
  ihr die Preise später, bleiben bestehende Anmeldungen, wie sie sind — bis
  der Gast seine Anmeldung ändert: Dann wird mit den **aktuellen** Preisen neu
  gerechnet. Die Preise deshalb vor dem Aushang festlegen.

### Wenn sich eine Anmeldung ändert

* **Mehr Personen nach der Zahlung:** Der Betrag steigt, der Unterschied ist
  offen. Die Bestätigungsseite zeigt „Noch offen“ und die Bezahlwege (QR-Code
  für die Überweisung, PayPal) für genau diesen Rest.
* **Weniger Personen nach der Zahlung:** Es ist zu viel bezahlt. Die
  Verwaltung zeigt oben „Zu erstatten“ und an der Zeile den Betrag. Erstattet
  wird **von Hand** (siehe unten), automatisch passiert nichts.
* **Absage nach der Zahlung:** genauso — die Plätze werden frei, das Geld
  bleibt verbucht und steht in der Verwaltung als „zu erstatten“. Der Gast
  sieht vor dem Absagen einen Hinweis darauf.

Bei „zu viel bezahlt“ kommt außerdem eine Nachricht über
`benachrichtigung_dienst`, auch wenn `benachrichtigung_jede_anmeldung` aus ist.

## Bezahlwege: Überweisung oder PayPal

Gäste können wählen, wie sie bezahlen. Auf der Bestätigungsseite stehen die
eingerichteten Wege als zwei Karten nebeneinander (am Handy untereinander):
**Überweisen** mit QR-Code und **Mit PayPal**. Der offene Betrag steht darüber.

| Eingerichtet | Der Gast sieht |
| --- | --- |
| Überweisung und PayPal | beide Karten, dazu einmal den Hinweis, dass Überweisungen von Hand abgehakt werden |
| nur Überweisung | nur die Karte „Überweisen“ |
| nur PayPal | nur PayPal, so wie in den Abschnitten unten beschrieben |
| nichts von beidem | den Text aus `zahlung_hinweis`, z. B. „Bitte bar beim Ausflug zahlen.“ |

Beide Wege sind gleichberechtigt und unabhängig voneinander. Welche
**PayPal-Variante** gilt, entscheidet weiterhin die Reihenfolge Client-ID und
Secret (Knopf), dann `paypal_me`, dann `paypal_email`. Die Überweisung ist
eingerichtet, sobald `iban` und `kontoinhaber` stimmen.

## Bezahlen per Überweisung (GiroCode)

Ein **GiroCode** ist ein QR-Code nach dem EPC-Standard. Er enthält die
komplette Überweisung: Empfänger, IBAN, Betrag und Verwendungszweck. Der Gast
scannt ihn in der Banking-App seiner Bank, die Überweisung ist dann schon
ausgefüllt, und er muss sie nur noch bestätigen. Praktisch alle deutschen
Banking-Apps können das. Für die Zahlung selbst fallen keine Gebühren an
(anders als bei PayPal; die gewöhnlichen Kontogebühren der Bank bleiben), und
das Geld kommt direkt auf das Vereinskonto.

### Einrichten

```yaml
iban: "DE89 3704 0044 0532 0130 00"
kontoinhaber: Freiwillige Feuerwehr Lehrberg e. V.
bic: ""
```

* `iban` ist die IBAN des Vereinskontos, mit oder ohne Leerzeichen und in
  Groß- oder Kleinschreibung. Das Add-on prüft Aufbau, Länge und die
  Prüfziffer (ISO 7064, Mod 97). Stimmt etwas nicht, steht oben in der
  Verwaltung eine rote Meldung, und es gibt keine Überweisung. Leer = keine
  Überweisung, ohne Meldung.
* `kontoinhaber` ist **Pflicht**, sobald eine IBAN eingetragen ist: Der
  GiroCode kann ohne Empfängernamen nicht erzeugt werden. Er gehört so
  geschrieben, wie er bei der Bank steht, und wird auf 70 Zeichen gekürzt.
  Fehlt er, zeigt die Verwaltung eine rote Meldung.
* `bic` ist nur für Konten außerhalb des SEPA-Raums nötig; **für deutsche
  Konten leer lassen.** Ist sie eingetragen, muss sie aus 8 oder 11
  Buchstaben und Ziffern bestehen, sonst steht eine Meldung in der Verwaltung
  und die BIC wird ignoriert.

Stimmen die Angaben, steht in der Verwaltung die Meldung „Überweisung per
QR-Code ist eingerichtet“ mit der IBAN.

> **Vor der Einladung einmal selbst prüfen:** Das Add-on kann die
> Prüfziffer kontrollieren, aber nicht wissen, ob die IBAN dem Verein gehört.
> Nach dem Eintragen eine Testanmeldung machen, auf der Bestätigungsseite den
> QR-Code mit der eigenen Banking-App scannen und prüfen, ob Empfänger, IBAN,
> Betrag und Verwendungszweck stimmen. Abschicken muss man die Überweisung dafür
> nicht.

### Was der Gast sieht

Auf der Karte **Überweisen** stehen der QR-Code mit dem Satz „Mit der
Banking-App scannen: Empfänger, IBAN, Betrag und Verwendungszweck sind schon
ausgefüllt.“ und darunter dieselben Angaben als Text, jede mit einem Knopf
„Kopieren“ für alle, die lieber von Hand überweisen oder am Rechner sitzen.

* Unter dem QR-Code steht der Knopf **„QR-Code als Bild speichern“** (und, wo
  der Browser es kann, **„Teilen“**). Am Handy lässt sich der Code auf dem
  eigenen Bildschirm nicht scannen; stattdessen speichert der Gast das Bild
  und wählt es in der Banking-App bei der QR-Code-Überweisung aus der
  Galerie. Das Bild kommt von `/anmeldung/<id>/girocode.png`, ist wie die
  Bestätigungsseite nur über die Anmelde-ID erreichbar und zeigt immer den
  aktuell offenen Betrag.
* Der **Betrag** ist immer der **offene** Betrag, auf dem Server gerechnet.
  Nach einer Teilzahlung oder einer Änderung der Anmeldung steht der Rest im
  Code; ist alles bezahlt, gibt es keinen Code.
* Der **Verwendungszweck** ist `<Titel> - <Name der Anmeldung>` (die Option
  `titel`, ein Bindestrich statt des Gedankenstrichs). Damit ordnet ihr die
  Überweisung auf dem Kontoauszug zu. Zeichen, die im Überweisungsverkehr
  nicht erlaubt sind (zum Beispiel `&`, `<`, `>` oder Anführungszeichen),
  werden durch Leerzeichen ersetzt; Umlaute bleiben. Er wird auf 140 Zeichen
  gekürzt, und der ganze Code darf höchstens 331 Byte lang sein.
* Auch die **Bestätigungsmail** nennt Empfänger, IBAN, Betrag und
  Verwendungszweck. Ist `oeffentliche_adresse` gesetzt, steht dort außerdem,
  dass der QR-Code auf der Anmeldeseite zu finden ist (Link „Anmeldung
  ansehen“).

### Zahlungen abhaken

Das Add-on erfährt **nicht**, wann eine Überweisung eingeht. Ihr gleicht das
Vereinskonto ab und markiert die Anmeldung in der Verwaltung mit **Als
bezahlt markieren**; erst dann wechselt der Stand auf „bezahlt“, und die Mail
„Zahlung erhalten“ geht raus. Der Gast sieht den Hinweis, dass das von Hand
geschieht und etwas dauern kann. Erstattet wird wie bei allen Zahlungen von
Hand (siehe „Erstatten“ unten).

### Technisches

Der Code folgt dem EPC-Standard (EPC069-12, Version 002, SEPA-Überweisung,
Zeichensatz UTF-8) und hat die Fehlerkorrektur-Stufe **M**. Er wird auf dem
Server mit der Python-Bibliothek `segno` erzeugt und als SVG direkt in die
Seite geschrieben: kein Dienst im Internet, keine Bilddatei, nichts wird an
eine Bank übermittelt. Die Seite skaliert ihn je nach Bildschirm.

## Zahlung per PayPal

### Wie es abläuft

1. Der Gast sendet die Anmeldung ab und landet auf der Bestätigungsseite. Dort
   steht der offene Betrag und der PayPal-Knopf.
2. Ein Tipp auf den Knopf fragt **diesen Server** nach einer Bestellung. Der
   Server holt sich mit Client-ID und Secret ein Zugangstoken bei PayPal und
   legt dort eine Order über den offenen Betrag an — den Betrag rechnet er
   selbst, der Browser kann ihn nicht vorgeben. In der Order steht die
   Kennung der Anmeldung.
3. Der Gast bezahlt im PayPal-Fenster (mit PayPal-Konto oder, je nach Land und
   Einstellung, per Karte).
4. Danach bucht der Server die Zahlung bei PayPal ab („Capture“) und prüft,
   dass PayPal `COMPLETED` meldet, dass Betrag und Währung (EUR) stimmen und
   dass die Order zu genau dieser Anmeldung gehört. Erst dann wird die Zahlung
   mit Betrag, Zeitpunkt und PayPal-Capture-ID an der Anmeldung gespeichert.

Doppelklick, ein zweiter Tab oder Neuladen buchen nichts doppelt: Jede Order
wird höchstens einmal verbucht, und hat sich der offene Betrag seit dem
Anlegen der Order geändert, bucht der Server gar nicht erst ab und bittet um
Neuladen.

Passt etwas nicht — anderer Betrag, andere Anmeldung, Status nicht
`COMPLETED` —, wird **nichts verbucht**. Hat PayPal trotzdem schon abgebucht,
steht das als rote Meldung „Nicht verbuchte PayPal-Zahlung“ in der Verwaltung,
mit Grund und Capture-ID. Dann im PayPal-Konto nachsehen, von Hand klären und
in der Zeile „Als geklärt markieren“.

Das **Secret** verlässt den Server nie: Der Browser bekommt nur die Client-ID
(die ist ohnehin öffentlich), und im Protokoll stehen bei Fehlern nur
PayPals Fehlername und `debug_id`.

Ist PayPal nicht eingerichtet (Client-ID oder Secret leer), gibt es keinen
Knopf. Stattdessen steht — solange auch keine Überweisung eingerichtet ist —
`zahlung_hinweis` auf der Bestätigungsseite, im Formular und in der Mail,
zum Beispiel „Bitte bar beim Ausflug zahlen.“

### Bezahlen ohne Geschäftskonto: PayPal.me

Wer kein PayPal-Geschäftskonto hat und deshalb keine Client-ID und kein Secret
bekommt, nutzt PayPal.me:

1. In PayPal einen **PayPal.me-Link** anlegen (in der PayPal-App oder auf
   paypal.com unter „PayPal.Me“) und den Namen merken, z. B.
   `feuerwehrlehrberg`.
2. In der Add-on-Konfiguration `paypal_me` eintragen. Der Name allein genügt,
   ebenso `paypal.me/feuerwehrlehrberg` oder der ganze Link mit `https://`.
   Erlaubt sind nur Buchstaben und Ziffern; alles andere zeigt die Verwaltung
   als rote Meldung, und es gibt dann keinen Link.
3. `paypal_client_id` und `paypal_secret` **leer lassen.** Sind beide gesetzt,
   gilt der PayPal-Knopf von oben, auch wenn `paypal_me` gefüllt ist.

Der Gast sieht auf der Bestätigungsseite (und über „Jetzt bezahlen“ in der
Mail) den offenen Betrag, ein Feld mit der Mitteilung und den Knopf „Mit
PayPal bezahlen“. Der Link hat die Form
`https://www.paypal.com/paypalme/<name>/<betrag>EUR`; der Betrag ist der
**offene** Betrag und wird auf dem Server gerechnet — nach einer Teilzahlung
steht der Rest im Link, bei bezahlter Anmeldung gibt es keinen Knopf.

PayPal.me füllt nur den Betrag aus, **nicht** die Mitteilung. Deshalb steht
über dem Knopf die Mitteilung `<Titel> – <Name der Anmeldung>` zum Kopieren
(Knopf „Kopieren“). Der Titel ist die Option `titel`; eine eigene Option dafür
gibt es nicht. Die Mitteilung hilft euch beim Zuordnen, ist aber Sache des
Gastes: PayPal kann sie weglassen.

Das Add-on erfährt **nicht**, ob bezahlt wurde. Ihr gleicht die Zahlungen in
PayPal ab und markiert die Anmeldung in der Verwaltung mit **Als bezahlt
markieren**. Erst dann wechselt der Stand auf „bezahlt“ und die Mail „Zahlung
erhalten“ geht raus. Der Gast sieht den Hinweis, dass das von Hand geschieht
und etwas dauern kann.

### Bezahlen über die E-Mail-Adresse

Gibt es keinen PayPal.me-Namen und kein Geschäftskonto mit Client-ID, kann der
Gast über die E-Mail-Adresse des PayPal-Kontos bezahlen:

1. In der Add-on-Konfiguration `paypal_email` eintragen, die Adresse des
   PayPal-Kontos, das das Geld bekommt (z. B. `kasse@example.org`). Die
   Prüfung ist streng: ein `@`, keine Leerzeichen, ein Punkt in der Domain und
   keine Zeichen wie `< > " ' & ? # / \`. Sonst zeigt die Verwaltung eine rote
   Meldung, und es gibt keinen Knopf.
2. `paypal_client_id`, `paypal_secret` und `paypal_me` **leer lassen.**
   Vorrang: Client-ID und Secret (Knopf), dann `paypal_me`, dann
   `paypal_email`, dann `zahlung_hinweis`.

**Vorteil:** Betrag und Verwendungszweck sind im Link schon eingetragen (der
Gast muss nichts abtippen), und die Anmelde-ID steht als Artikelnummer in der
Zahlung, damit ihr in PayPal leichter abgleichen könnt. Der Link wird auf dem
Server gebaut (`https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business=…`);
der Betrag ist der **offene** Betrag, bei bezahlter Anmeldung gibt es keinen
Knopf.

**Nachteile:** PayPal wertet die Zahlung als **Kauf**, der Empfänger zahlt
Gebühren. Ob das mit einem **Privatkonto ohne Geschäftskonto** klappt, hängt
vom Konto ab und muss mit einer kleinen Testzahlung geprüft werden, bevor die
Einladung rausgeht. Wie bei PayPal.me erfährt das Add-on nicht, ob bezahlt
wurde: Ihr gleicht in PayPal ab und markiert die Anmeldung mit **Als bezahlt
markieren**.

### PayPal einrichten — Schritt für Schritt

Für echte Zahlungen braucht ihr ein **PayPal-Geschäftskonto** für den Verein.
Zum Testen in der Sandbox genügt zunächst jedes PayPal-Konto. Dann:

1. **Developer-Konto öffnen:** <https://developer.paypal.com> aufrufen und mit
   dem PayPal-Geschäftskonto des Vereins anmelden. Das Developer-Dashboard
   gehört automatisch dazu, es kostet nichts.
2. **App anlegen:** Im Dashboard **Apps & Credentials** öffnen. Oben steht ein
   Schalter **Sandbox / Live** — zuerst **Sandbox** wählen. **Create App**,
   einen Namen vergeben (z. B. „Ausflug Anmeldung“), als Typ „Merchant“
   wählen, falls gefragt, und anlegen.
3. **Client-ID und Secret holen:** In der App stehen **Client ID** und
   **Secret** (das Secret über „Show“ einblenden). Beide in die Add-on-Optionen
   kopieren:

   ```yaml
   paypal_client_id: "<Client ID aus dem Dashboard>"
   paypal_secret: "<Secret aus dem Dashboard>"
   paypal_modus: sandbox
   ```

   Add-on neu starten. In der Verwaltung steht dann oben rot „PayPal läuft im
   Sandbox-Modus“.
4. **In der Sandbox testen:** Unter **Testing Tools → Sandbox Accounts** legt
   PayPal Testkonten an — ein „Personal“-Konto ist der zahlende Gast. Dessen
   E-Mail und Passwort stehen dort unter „View/Edit account“. Jetzt eine
   Testanmeldung machen, auf den PayPal-Knopf tippen und mit dem
   Sandbox-Personal-Konto bezahlen. In der Verwaltung muss die Anmeldung
   danach „bezahlt“ zeigen, mit Capture-ID. Gegenprobe: unter
   <https://www.sandbox.paypal.com> mit dem Sandbox-*Business*-Konto anmelden —
   dort taucht die Zahlung auf. Am besten auch einmal Ändern (mehr Personen →
   Rest nachzahlen) und Absagen durchspielen.
5. **Auf live stellen:** Im Dashboard den Schalter auf **Live** stellen und dort
   eine App anlegen (Live-Zugangsdaten sind **andere** als die aus der
   Sandbox). Client-ID und Secret der Live-App eintragen, dazu

   ```yaml
   paypal_modus: live
   ```

   und das Add-on neu starten. Die Sandbox-Testanmeldungen vorher in der
   Verwaltung löschen.

Klappt etwas nicht, steht der Grund im Protokoll des Add-ons. Häufig:
„PayPal hat Client-ID oder Secret abgelehnt“ — dann passen die Zugangsdaten
nicht zum gewählten Modus.

PayPal berechnet für jede Zahlung eine Gebühr. Die zahlt der Verein; sie ist
im Betrag des Gastes nicht enthalten.

### Erstatten

Das Add-on erstattet nie selbst. So geht es:

1. Im PayPal-Konto unter **Aktivitäten** die Zahlung suchen (die Capture-ID aus
   der Verwaltung oder der CSV hilft) und **Rückzahlung** wählen — ganz oder
   teilweise. Bei Barzahlern das Geld bar zurückgeben.
2. In der Verwaltung in der Zeile **Erstattung vermerken** drücken. Damit
   verschwindet der Hinweis „zu erstatten“, und die Summen stimmen wieder.

### Barzahlung und Zahlungen von Hand

In der Verwaltung hat jede Zeile mit offenem Betrag den Knopf **Als bar
bezahlt markieren**. Er verbucht den offenen Betrag als Barzahlung. Ein
versehentlicher Klick lässt sich mit **Barzahlung zurücknehmen** rückgängig
machen; PayPal-Zahlungen bleiben davon unberührt. Überweisungen, PayPal.me-
und E-Mail-Zahlungen gleicht ihr mit Konto oder PayPal ab und hakt sie mit
**Als bezahlt markieren** ab.

## Einstellungen

Die Einstellungsseite ist in Gruppen sortiert. Jedes Feld trägt vorne den
Namen seiner Gruppe und darunter eine kurze Erklärung. Die technischen Namen in
Klammern braucht man nur in der YAML-Ansicht. Alle Angaben zum Ausflug sind
absichtlich leer oder Platzhalter und müssen vor dem Aushang eingetragen
werden.

**Ausflug** — was auf der Startseite steht

| Feld | Bedeutung |
| --- | --- |
| Titel (`titel`) | Überschrift der Seite, auch Betreff der Mail |
| Überzeile (`untertitel`) | Kleine Zeile über der Überschrift |
| Datum (`datum`) | Frei formulierbar, z. B. `Samstag, 12. Juni 2027` |
| Abfahrt (`uhrzeit`) | Z. B. `7:00` — wird als `Abfahrt 7:00 Uhr` angezeigt |
| Treffpunkt (`ort`) | Z. B. `Feuerwehrgerätehaus Lehrberg` |
| Ziel (`ziel`) | Wohin es geht, z. B. `Bodensee` |
| Einladungstext (`text`) | Fließtext. Ein senkrechter Strich beginnt einen neuen Absatz |
| Ablauf (`ablauf`) | Programm, siehe oben. Leer = kein Ablauf |
| Ansprechpartner (`kontakt`) | Name und Telefonnummer für Rückfragen |

**Anmeldung**

| Feld | Bedeutung |
| --- | --- |
| geöffnet (`anmeldung_offen`) | Hauptschalter. Aus = keine Anmeldung möglich |
| Plätze insgesamt (`plaetze_gesamt`) | Obergrenze über alle Anmeldungen, Mitglieder, Nichtmitglieder und Kinder zusammen |
| höchstens Personen je Anmeldung (`max_personen_pro_anmeldung`) | Gilt für die Summe aus Mitgliedern, Nichtmitgliedern und Kindern |
| Anmeldeschluss (`anmeldeschluss`) | Nur ein Hinweis, schließt nichts automatisch |
| Speisen vorbestellen (`essen`) | Optional, Standard leer. Gerichte mit Stückzahl |
| Getränke vorbestellen (`getraenke`) | Optional, Standard leer. Getränke zum Ankreuzen |
| E-Mail-Adresse abfragen (`email_abfragen`) | An = Pflichtfeld mit Bestätigungsmail |
| Hinweis unter dem Absende-Knopf (`datenschutz_hinweis`) | Eine Zeile Kleingedrucktes |

**Zahlung**

| Feld | Bedeutung |
| --- | --- |
| Preis für Mitglieder (`preis_mitglied`) | Euro je Person, z. B. `15,00` |
| Preis für Nichtmitglieder (`preis_nichtmitglied`) | Euro je Person, z. B. `25,00` |
| Preis für Kinder bis 14 Jahre (`preis_kind`) | Euro je Kind, Standard `0` = kostenlos |
| Überweisung, IBAN (`iban`) | IBAN des Vereinskontos, mit oder ohne Leerzeichen, die Prüfziffer wird kontrolliert. Leer = keine Überweisung |
| Überweisung, Kontoinhaber (`kontoinhaber`) | Name wie bei der Bank, Pflicht zur IBAN, höchstens 70 Zeichen |
| Überweisung, BIC (`bic`) | Nur bei Konten außerhalb des SEPA-Raums; für deutsche Konten leer lassen |
| PayPal Client-ID (`paypal_client_id`) | Aus dem PayPal-Developer-Dashboard. Leer = kein PayPal |
| PayPal Secret (`paypal_secret`) | Gehört zur Client-ID, bleibt auf dem Server |
| PayPal-Modus (`paypal_modus`) | `sandbox` zum Testen, `live` für echte Zahlungen |
| PayPal.me-Name oder Link (`paypal_me`) | Einfache Variante ohne Geschäftskonto, nur wirksam bei leerer Client-ID/Secret |
| PayPal-E-Mail-Adresse (`paypal_email`) | Link über die Adresse des PayPal-Kontos, nur wirksam ohne Client-ID/Secret und ohne `paypal_me` |
| Hinweis ohne Überweisung und PayPal (`zahlung_hinweis`) | Steht statt der Bezahlwege, solange weder Überweisung noch PayPal eingerichtet ist |

**E-Mail** — die Bestätigungsmail

| Feld | Bedeutung |
| --- | --- |
| Unterschrift (`veranstalter`) | Name unter der Mail, z. B. `Freiwillige Feuerwehr Lehrberg` |
| Mailserver, Port, Verschlüsselung (`smtp_server`, `smtp_port`, `smtp_verschluesselung`) | Postausgang. Leerer Server = keine Mails |
| Benutzername, Passwort (`smtp_benutzer`, `smtp_passwort`) | Zugang beim Mailanbieter |
| Absenderadresse (`smtp_absender`) | Von dieser Adresse kommt die Mail |
| Antworten gehen an (`smtp_antwort_an`) | Für Antworten, falls der Absender kein Postfach hat |

**Webseite** — Adresse und Rechtliches

| Feld | Bedeutung |
| --- | --- |
| öffentliche Adresse (`oeffentliche_adresse`) | Z. B. `https://ausflug.example.de` — für Links in Mails (auch den Bezahl-Link) und die Vorschau beim Teilen |
| Impressum (`impressum`) | Ein senkrechter Strich trennt die Zeilen. Erscheint auch als Verantwortlicher im Datenschutz |
| eigene Datenschutzerklärung (`datenschutz`) | Leer = die eingebaute Erklärung |
| Löschfrist (`loeschfrist`) | Steht in der Datenschutzerklärung |
| vorab nur sichtbar für (`nur_fuer_ip`) | Zum Testen: Gästeseite nur für diese Adressen. Leer = für alle |

**Home Assistant**

| Feld | Bedeutung |
| --- | --- |
| Sensor anlegen (`sensor_erstellen`) | Legt `sensor.ausflug_freie_plaetze` an |
| Benachrichtigung an (`benachrichtigung_dienst`) | Notify-Aktion oder -Entität. Leer = aus |
| bei jeder Anmeldung benachrichtigen (`benachrichtigung_jede_anmeldung`) | Aus = nur bei den Schwellen und bei Erstattungen |
| Schwellen (`benachrichtigung_schwellen`) | Belegte Plätze als Text, z. B. `30, 45`. Leer = aus |

Leere Felder werden auf der Seite weggelassen. Änderungen an den Optionen
greifen nach dem Neustart des Add-ons.

## Seite zum Testen sperren

Solange die Seite noch nicht ausgehängt ist, kann man sie hinter der Option
`nur_fuer_ip` verstecken: Steht dort etwas, bekommt **nur** diese Adresse die
Gästeseite zu sehen, alle anderen „Noch nicht freigeschaltet“ (Status 503).
Mehrere Adressen und Bereiche durch Komma trennen, z. B.
`84.123.45.67, 91.0.0.0/8`. Aus dem Heimnetz bleibt die Seite offen, ebenso
die Verwaltung. Die Adresse des Gastes kommt aus der Kopfzeile
`Cf-Connecting-Ip` des Cloudflare-Tunnels — das ist eine Testsperre, kein
Schutzwall. Die Einzelheiten stehen in der Anleitung der Gedenkveranstaltung;
das Verhalten ist dasselbe.

## Verwaltung

* **Kennzahlen** — Anmeldungen, Personen (mit Aufteilung Mitglieder,
  Nichtmitglieder und Kinder), freie Plätze und wie viele Anmeldungen bezahlt sind.
  Darunter die Summen **erwartet** (alle Beträge aktiver Anmeldungen),
  **eingegangen** (alles tatsächlich Gezahlte, abzüglich vermerkter
  Erstattungen) und **offen**.
* **Je Anmeldung** — Personen (M/N/K), Betrag, Stand „bezahlt“ oder „offen“,
  jede Zahlung mit Art, Betrag, Zeitpunkt und bei PayPal der Capture-ID, dazu
  „zu erstatten“ und nicht verbuchte Zahlungen. Knöpfe: **Als bar bezahlt
  markieren**, **Barzahlung zurücknehmen**, **Erstattung vermerken**, **Als
  geklärt markieren**.
* **CSV herunterladen** — Semikolon-getrennt und mit BOM für Excel. Spalten
  `Mitglieder`, `Nichtmitglieder`, `Kinder`, `Personen` (Summe aller drei),
  `Betrag (€)`, `Bezahlt (€)`,
  `Offen (€)`, `Zu erstatten (€)`, `Zahlungsart`, `PayPal-Capture-ID`,
  `Bezahlt am`; Beträge mit Komma, damit Excel damit rechnet. Spalten für
  Essen und Getränke nur, wenn es die Listen gibt. Beginnt ein Name oder eine
  Anmerkung mit `=`, `+`, `-` oder `@`, steht ein Hochkomma davor, damit Excel
  nichts als Formel ausrechnet.
* **Anmeldung schließen** — sofort wirksam, jederzeit wieder zu öffnen.
* **Nicht zugestellte Bestätigungen** — stehen mit Grund an der Anmeldung.
  Diese Gäste haben keinen Link zum Ändern, Absagen und Bezahlen.
* **Löschen** — entfernt eine Anmeldung endgültig, samt ihrer Zahlungsdaten.
  Bei bezahlten Anmeldungen vorher die CSV sichern.

## Benachrichtigungen

In `benachrichtigung_dienst` den Namen eintragen, unter dem dein Handy in Home
Assistant erreichbar ist — etwa `notify.mobile_app_dein_handy`. Das Add-on
meldet:

* jede Anmeldung, Änderung, Absage und **jede eingegangene Zahlung**
  (abschaltbar über `benachrichtigung_jede_anmeldung`),
* immer: wenn Geld zu erstatten ist und wenn der letzte Platz vergeben ist,
* die Schwellen aus `benachrichtigung_schwellen`.

### Events für eigene Automatisierungen

| Event | Daten |
| --- | --- |
| `ausflug_anmeldung` | `name`, `personen`, `mitglieder`, `nichtmitglieder`, `kinder`, `betrag_cent`, `bezahlt_cent`, `offen_cent`, `essen`, `getraenke`, `anmerkung`, `anmeldungen`, `belegte_plaetze`, `freie_plaetze`, `ausgebucht` |
| `ausflug_aenderung` | wie oben ohne die Platzangaben |
| `ausflug_absage` | `name`, `personen`, `mitglieder`, `nichtmitglieder`, `kinder`, Beträge, `freie_plaetze` |
| `ausflug_zahlung` | `name`, `personen`, Beträge, `art`, `zahlung_cent` |

Beträge kommen in Cent (`5500` = 55,00 €).

```yaml
automation:
  - alias: Zahlung eingegangen
    triggers:
      - trigger: event
        event_type: ausflug_zahlung
    actions:
      - action: notify.mobile_app_dein_handy
        data:
          message: >-
            {{ trigger.event.data.name }} hat
            {{ (trigger.event.data.zahlung_cent / 100) | round(2) }} € bezahlt.
```

## Sensor

Bei `sensor_erstellen: true` schreibt das Add-on nach jeder Änderung
`sensor.ausflug_freie_plaetze`. Zustand ist die Zahl der freien Plätze, dazu
kommen als Attribute `plaetze_gesamt`, `belegte_plaetze`, `anmeldungen`,
`mitglieder`, `nichtmitglieder`, `kinder`, `anmeldung_offen`, `summe_erwartet`,
`summe_eingegangen`, `summe_offen`, `summe_zu_erstatten` (in Euro),
`anmeldungen_bezahlt`, `essen` und `getraenke`. Gezählt werden nur aktive
Anmeldungen; `summe_eingegangen` enthält auch Zahlungen inzwischen Abgesagter.

```yaml
type: entities
entities:
  - entity: sensor.ausflug_freie_plaetze
  - type: attribute
    entity: sensor.ausflug_freie_plaetze
    attribute: summe_eingegangen
    name: Eingegangen (€)
```

Der Sensor wird über die States-API gesetzt. Er verschwindet beim Neustart von
Home Assistant und wird beim nächsten Start des Add-ons oder bei der nächsten
Anmeldung neu geschrieben.

## Bestätigungsmail

Die Mail nennt die Aufteilung (z. B. „5 Personen (2 Mitglieder, 1
Nichtmitglied, 2 Kinder)“), bei Kindern zusätzlich eine Zeile „Kinder bis 14
Jahre: 2 (kostenlos)“, den Gesamtbetrag mit Aufstellung, den Zahlungsstand und —
solange etwas offen ist und die Überweisung eingerichtet ist — einen Absatz
**Überweisung** mit Empfänger, IBAN, Betrag und Verwendungszweck (mit
`oeffentliche_adresse` dazu der Hinweis auf den QR-Code auf der Anmeldeseite).
Sind Überweisung und PayPal eingerichtet, steht die Überweisung zuerst, mit dem
Satz „Sie können wählen, wie Sie bezahlen.“ Mit PayPal-Knopf kommt als großer
Knopf der Link **Jetzt … € bezahlen**. Mit PayPal.me stehen dort Betrag, Mitteilung und der direkte PayPal.me-Link, mit der E-Mail-Adresse Betrag und der direkte PayPal-Link (der Verwendungszweck ist darin vorausgefüllt).
Ohne Überweisung und PayPal steht dort `zahlung_hinweis`. Nach
einer PayPal-Zahlung bekommt der Gast eine kurze Mail „Zahlung erhalten“.

Für die Links muss `oeffentliche_adresse` gesetzt sein. Postausgang, Port und
Versanddienst funktionieren wie bei der Gedenkveranstaltung:

```yaml
email_abfragen: true
smtp_server: smtp.example.de
smtp_port: 587
smtp_verschluesselung: starttls
smtp_benutzer: anmeldung@example.de
smtp_passwort: "…"
smtp_absender: anmeldung@example.de
oeffentliche_adresse: https://ausflug.example.de
```

Vom Heimanschluss aus lassen sich Mails praktisch nicht zustellen; ein
Versanddienst wie SMTP2GO, Brevo oder der Mailserver des Domain-Hosters ist der
einfache Weg. Die Absenderdomain muss dort verifiziert sein.

## Impressum und Datenschutz

Beide Seiten sind über die Fußzeile jeder öffentlichen Seite erreichbar.
`/datenschutz` zeigt ohne weiteres Zutun eine eingebaute Erklärung, die genau
beschreibt, was dieses Add-on tut. Ist die Überweisung eingerichtet, enthält sie
einen Abschnitt **Bezahlung per Überweisung**: Die Seite übermittelt nichts an
eine Bank, der QR-Code enthält nur die Kontodaten des Vereins, den Betrag und
den Verwendungszweck, und der Gast überweist über seine eigene Bank. Ist PayPal
eingerichtet (Knopf, PayPal.me oder E-Mail-Adresse), enthält sie einen
Abschnitt **Bezahlung mit PayPal**. Beim Knopf: welche Angaben an PayPal gehen (Betrag,
Währung, Titel, Kennung der Anmeldung — nicht Name oder E-Mail), dass der
Bezahlknopf von paypal.com geladen wird, was PayPal zurückmeldet und dass
Zahlungsbelege länger aufbewahrt werden müssen als die übrigen
Anmeldedaten. Bei PayPal.me steht dort stattdessen, dass die Seite nichts an
PayPal übermittelt und der Gast seine Angaben bei PayPal selbst eingibt. Bei der
E-Mail-Adresse gilt dasselbe; zusätzlich steht dort, dass Betrag, Titel,
Name der Anmeldung und Anmelde-ID im Link stehen.

Das ist kein Rechtsrat. Vor dem offiziellen Start sollte jemand darüber
schauen — vor allem, ob ein Auftragsverarbeitungsvertrag oder eine eigene
Verantwortlichkeit mit PayPal greift und welche Aufbewahrungsfristen für den
Verein gelten.

## Daten

Alle Anmeldungen samt Zahlungen liegen in `/data/anmeldungen.json` im Add-on.
Sie sind Teil der Home-Assistant-Backups. Beim Deinstallieren des Add-ons
werden sie gelöscht — vorher CSV exportieren.

## Die Seite von außen erreichbar machen

Wie bei der Gedenkveranstaltung über das **Cloudflare-Tunnel-Add-on**, nur mit
Port 8081:

```yaml
additional_hosts:
  - hostname: ausflug.deine-domain.de
    service: http://1a2b3c4d-ausflug:8081
```

`1a2b3c4d-ausflug` ist ein **Beispiel**: Der Servicename ist der volle Slug
dieses Add-ons mit Bindestrichen statt Unterstrichen (aus der Adresszeile der
Add-on-Seite, z. B. `1a2b3c4d_ausflug` → `1a2b3c4d-ausflug`; lokal installiert
`local-ausflug`). Ersatzweise geht die IP von Home Assistant mit Port 8081.
Port 8099 (Verwaltung) gehört **nicht** in den Tunnel.

PayPal braucht keine Weiterleitung nach innen: Alle Aufrufe gehen vom Add-on
zu PayPal hinaus, und der Knopf im Browser spricht nur mit dieser Seite und
mit paypal.com.
