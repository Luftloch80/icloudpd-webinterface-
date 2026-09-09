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
| `/data/photos`          | Standard-Zielverzeichnis für heruntergeladene Fotos |

Im mitgelieferten `docker-compose.yml` werden `./data/config` und
`./data/photos` auf dem Host gemountet.

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

| Variable         | Beschreibung                                                        | Default            |
|-------------------|----------------------------------------------------------------------|---------------------|
| `APP_USERNAME`    | Benutzername fürs Webinterface                                       | `admin`             |
| `APP_PASSWORD`    | Passwort fürs Webinterface (dringend setzen!)                        | auto-generiert      |
| `FERNET_KEY`      | Fester Schlüssel zur Passwort-Verschlüsselung                        | auto-generiert      |
| `SECRET_KEY`      | Flask-Session-Secret                                                 | auto-generiert      |
| `DATA_DIR`        | Basisverzeichnis für alle persistenten Daten                         | `/data`             |
| `ICLOUDPD_BIN`    | Pfad/Name der icloudpd-Binary                                        | `icloudpd`          |
| `TZ`              | Zeitzone für Zeitstempel in Logs/Verlauf                             | Container-Default   |

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
