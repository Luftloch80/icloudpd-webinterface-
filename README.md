# icloudpd Webinterface

Ein selbst gehostetes Webinterface für [icloudpd](https://github.com/icloud-photos-downloader/icloud_photos_downloader)
mit Login in den Apple-Account (inkl. Zwei-Faktor-/Zwei-Schritt-Bestätigung) und
umfangreichen Einstellmöglichkeiten. Gebaut für den Betrieb per Docker auf einem
Raspberry Pi (funktioniert genauso auf jedem anderen Linux-Host).

## Funktionen

- **Eigener Login fürs Webinterface** (Benutzername/Passwort, unabhängig von der Apple-ID)
- **Apple-ID-Anmeldung im Browser**, inkl. Live-Ausgabe und Eingabe des
  Zwei-Faktor-/Zwei-Schritt-Codes – es wird dafür der echte `icloudpd`-Client
  selbst angesteuert (`--auth-only`), damit die erzeugte Session garantiert
  mit den späteren Sync-Läufen kompatibel ist
- **Einstellungen** für Zielverzeichnis, Bildgrößen, Live-Photo-Größe, Album,
  Datei-Abgleich-Policy, Video-/Live-Photo-Filter, „nur die letzten N“,
  Auto-Delete, Dry-Run, Log-Level, Dauerbetrieb mit Intervall u.v.m.
- **Freitextfeld für zusätzliche icloudpd-Argumente**, damit auch Optionen
  genutzt werden können, für die es kein eigenes Formularfeld gibt
- **Eingebaute `icloudpd --help`-Ansicht** direkt aus der laufenden Version,
  als verlässliche Referenz für alle verfügbaren Optionen
- **Job-Steuerung**: einmalig synchronisieren oder dauerhaft im Intervall
  überwachen, inkl. Live-Log, Start/Stopp und Lauf-Verlauf
- **Dropbox-Upload**: heruntergeladene Fotos optional automatisch nach jedem
  erfolgreichen Sync zu Dropbox hochladen (nur neue/geänderte Dateien)

## Schnellstart (Docker Compose)

```bash
git clone <dieses-repo> icloudpd-webinterface
cd icloudpd-webinterface
cp .env.example .env
# .env anpassen: APP_PASSWORD unbedingt setzen!
docker compose up -d --build
```

Danach ist das Interface unter `http://<pi-ip>:5000` erreichbar. Anmelden mit
`APP_USERNAME`/`APP_PASSWORD` aus der `.env`. Anschließend im Menü
„Apple-ID verbinden“ die iCloud-Zugangsdaten eingeben.

Falls `APP_PASSWORD` nicht gesetzt wird, generiert die App beim ersten Start
automatisch ein zufälliges Passwort und zeigt es (nur so lange, bis eine
eigene Umgebungsvariable gesetzt wird) als Hinweisbanner im Interface an.

## Raspberry Pi Hinweise

- Empfohlen: **64-Bit Raspberry Pi OS** (`arm64`) – dafür gibt es für alle
  Python-Abhängigkeiten fertige Wheels, der Build ist entsprechend schnell.
- Auf **32-Bit** Raspberry Pi OS (`armv7`) werden `cryptography` u.a. beim
  Docker-Build ggf. aus dem Quellcode kompiliert (Rust-Toolchain ist im
  Dockerfile enthalten) – das dauert beim ersten Build spürbar länger,
  funktioniert aber ohne weiteres Zutun.
- Das Docker-Image ist multi-arch-fähig (`python:3.12-slim-bookworm`), ein
  `docker compose build` auf dem Pi selbst reicht aus.

## Verzeichnisse & Daten

Alle persistenten Daten liegen unter `/data` im Container:

| Pfad im Container      | Zweck                                             |
|-------------------------|----------------------------------------------------|
| `/data/config`          | SQLite-Datenbank, Verschlüsselungs-/Session-Keys   |
| `/data/config/cookies`  | iCloud-Session-/Cookie-Dateien (pro Apple-ID)      |
| `/data/config/logs`     | Log-Dateien aller Sync-Läufe                       |
| `/data/drive_d`         | Gesamtes `D:`-Laufwerk (Standard-Zielverzeichnis)  |

Im mitgelieferten `docker-compose.yml` wird `./data/config` (lokaler Ordner
neben dem Repo) sowie das komplette `D:\`-Laufwerk (`D:\` → `/data/drive_d`)
auf dem Host gemountet. Das Zielverzeichnis in den Einstellungen kann per
integriertem Ordner-Browser innerhalb von `/data` (also auch innerhalb von
`/data/drive_d`, sprich überall auf `D:`) ausgewählt werden.

**Achtung:** Da hier das komplette Laufwerk eingebunden ist, hat der
Container vollen Lese-/Schreibzugriff auf alles auf `D:`. Bei aktivierten
Optionen wie „Auto-Delete“ oder „Delete after download“ in den
Einstellungen betrifft das ausschließlich das gewählte Zielverzeichnis
selbst – trotzdem empfiehlt es sich, sicherheitshalber einen dedizierten
Unterordner (z. B. `D:\iCloud-Fotos`) als Ziel zu wählen statt das
Laufwerk direkt als Ziel zu nutzen. Wer stattdessen nur einen bestimmten
Ordner statt des ganzen Laufwerks mounten möchte, ersetzt in der
`docker-compose.yml` die Zeile `- D:\:/data/drive_d` durch z. B.
`- D:\iCloud-Fotos:/data/photos`.

## Sicherheit

- Das Apple-ID-Passwort wird **verschlüsselt** (Fernet/AES) in der lokalen
  SQLite-Datenbank gespeichert. Der Schlüssel dafür wird beim ersten Start
  automatisch erzeugt und unter `/data/config/secret.key` abgelegt (oder per
  `FERNET_KEY`-Umgebungsvariable fest vorgegeben).
- Das Webinterface selbst ist durch einen eigenen Login geschützt
  (`APP_USERNAME`/`APP_PASSWORD`). Da hierüber vollständige Kontrolle über
  den Apple-Account (Downloads, ggf. Löschungen) möglich ist, sollte der
  Zugriff zusätzlich per Reverse-Proxy/VPN/Firewall auf das eigene Netzwerk
  beschränkt werden.
- Der Container läuft standardmäßig mit **einem** Gunicorn-Worker, da
  Login-Zustand (2FA) und laufende Jobs im Prozessspeicher gehalten werden.

## Umgebungsvariablen

| Variable              | Beschreibung                                                        | Default            |
|------------------------|----------------------------------------------------------------------|---------------------|
| `APP_USERNAME`         | Benutzername fürs Webinterface                                       | `admin`             |
| `APP_PASSWORD`         | Passwort fürs Webinterface (dringend setzen!)                        | auto-generiert      |
| `FERNET_KEY`           | Fester Schlüssel zur Passwort-Verschlüsselung                        | auto-generiert      |
| `SECRET_KEY`           | Flask-Session-Secret                                                 | auto-generiert      |
| `DATA_DIR`             | Basisverzeichnis für alle persistenten Daten                         | `/data`             |
| `ICLOUDPD_BIN`         | Pfad/Name der icloudpd-Binary                                        | `icloudpd`          |
| `TZ`                   | Zeitzone für Zeitstempel in Logs/Verlauf                             | Container-Default   |
| `DROPBOX_APP_KEY`      | App Key der eigenen Dropbox-App (siehe unten)                        | – (Feature deaktiviert ohne diese) |
| `DROPBOX_APP_SECRET`   | App Secret der eigenen Dropbox-App                                   | –                   |

## Dropbox-Upload einrichten

1. Auf https://www.dropbox.com/developers/apps eine neue App anlegen:
   - **Scoped access**
   - Zugriff auf **App folder** (empfohlen, sieht nur den eigenen Unterordner)
     oder **Full Dropbox**
2. Im Reiter „Permissions“ der neuen App die Berechtigungen
   `files.content.write` und `files.content.read` aktivieren und speichern.
3. Im Reiter „Settings“ **App key** und **App secret** kopieren, in die
   `.env` als `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` eintragen, dann
   `docker compose up -d --build`.
4. Im Webinterface unter „Dropbox“ auf **Verbinden** klicken. Es erscheint
   ein Link zu Dropbox; dort den Zugriff bestätigen, den angezeigten Code
   kopieren und im Webinterface einfügen. Eine öffentlich erreichbare
   Adresse für den Pi ist dafür **nicht** nötig.
5. Zielordner in Dropbox festlegen und „Nach jedem erfolgreichen Sync
   automatisch hochladen“ aktivieren, oder jederzeit manuell über
   „Jetzt zu Dropbox hochladen“ anstoßen.

Bereits hochgeladene, unveränderte Dateien werden bei späteren Läufen
übersprungen (Abgleich über Dateigröße und Änderungsdatum).

## Entwicklung / lokal ohne Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=./data
export APP_PASSWORD=devpassword
python run.py
```

Das Interface läuft dann unter `http://localhost:5000`.

## Einschränkungen (v1)

- Es wird aktuell **ein** Apple-Account pro Installation unterstützt.
- Der eingebaute Login-Flow deckt Standard-2FA/2SA ab; bei ungewöhnlichen
  Apple-Sicherheitsabfragen hilft ein Blick in die Live-Ausgabe auf der
  Bestätigungsseite, da dort die rohe icloudpd-Ausgabe angezeigt wird.
