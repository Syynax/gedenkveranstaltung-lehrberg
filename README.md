# Gedenkveranstaltung Lehrberg

Anmeldung zum 20. Jahrestag der Gasexplosion — als Home-Assistant-Add-on, plus
der Entwurf, aus dem die Seite gebaut ist.

```
gedenkveranstaltung/            das Add-on
  config.yaml                   Optionen, Ports, Ingress
  build.yaml                    Basis-Images je Architektur
  Dockerfile
  DOCS.md                       Anleitung, die in Home Assistant angezeigt wird
  rootfs/app/
    server.py                   der ganze Server
    templates/                  Startseite, Formular, Bestätigung, Verwaltung
    static/style.css
repository.yaml                 macht diesen Ordner zum Add-on-Repository
design/                         Arbeitsdateien des Entwurfs
gedenkveranstaltung-lehrberg.html   der Entwurf als Design-Leinwand
```

## Installieren

1. Diesen Ordner in ein Git-Repository legen und zu GitHub schieben. Vorher in
   `repository.yaml` die `url` auf das eigene Repository ändern.
2. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ →
   Repositories** und die Repository-Adresse eintragen.
3. **Gedenkveranstaltung Anmeldung** installieren.
4. Unter **Konfiguration** Datum, Uhrzeit, Ort, Kontakt, Platzzahl sowie die
   Listen für Essen und Getränke eintragen.
5. Starten. In der Seitenleiste erscheint **Anmeldungen** (die Verwaltung), die
   Gästeseite läuft auf Port 8080.

Zum Ausprobieren ohne GitHub: den Ordner `gedenkveranstaltung` nach
`/addons/gedenkveranstaltung` auf dem Home-Assistant-Rechner kopieren (Samba-
oder SSH-Add-on) und den Add-on Store neu laden — er taucht dann unter „Lokale
Add-ons" auf.

Alles Weitere — Optionen, Sensor, CSV-Export, Daten und Backups — steht in
[DOCS.md](gedenkveranstaltung/DOCS.md).

## Was noch offen ist

* Datum, Uhrzeit, Ort, Anmeldeschluss und Kontakt sind absichtlich leer
  vorbelegt und müssen in den Add-on-Optionen gesetzt werden.
* Essen (Weißwürste, Wiener) und Getränke (Weizen, Helles, beide auch
  alkoholfrei, dazu alkoholfreie Getränke) sind bereits eingetragen.
* Veröffentlicht wird über das Cloudflare-Tunnel-Add-on auf Port 8080; der
  Servicename dort ist der volle Add-on-Slug mit Bindestrichen —
  siehe [DOCS.md](gedenkveranstaltung/DOCS.md).
