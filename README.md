<!--
File: README.md
Version: 0.3.0
Date: 2026-08-06
Purpose: Explains installation, Shelly/Tasmota operation, security, tests, and recovery.
-->

# GA-Server 0.3.0

GA-Server empfängt elektrische Messwerte von Shelly Pro 3EM und
Tasmota-Steckdosen, fasst sie zu
Minutenwerten zusammen und zeigt sie als öffentlichen, bildschirmfüllenden
24-Stunden-Verlauf. Die Geräte- und Systemverwaltung ist durch Anmeldung
geschützt.

Wichtig:

- `https://strom.gruber-automation.de` ist die Website.
- `mqtt.strom.gruber-automation.de:8883` ist der verschlüsselte MQTT-Broker.
- Ein Shelly darf **nicht** die HTTPS-Adresse als MQTT-Server verwenden.
- Port 1883 bleibt im Docker-Netz und wird nicht öffentlich freigegeben.

## Funktionsumfang 0.3.0

- geschützte „Steckdosen-Übersicht“ mit Rohwerten, Onlinezustand und
  bestätigungsbasierter Tasmota-Schaltsteuerung
- getrennte Shelly- und Tasmota-Parser bei gemeinsamer Live- und
  Minutenwertverarbeitung
- additive Alembic-Migration für bestehende Gerätebestände

- Strom L1/L2/L3/Gesamt, Spannung L1/L2/L3 und Wirkleistung
  L1/L2/L3/Gesamt
- über den GA-Button einblendbare, in den Graphen eingebettete Hierarchie für eine unabhängige
  Auswahl beliebiger Messstellen, Messgrößen und Phasen
- deterministische Farbe je Datenreihe sowie ergänzende Phasen-Linienmuster
- Canvas-Graph mit getrennten, nur bei Bedarf sichtbaren Skalen für A, V und
  W/kW, gruppiertem Tooltip, Retina-Skalierung und `ResizeObserver`
- Pinch-Zoom und Verschieben auf Touchgeräten, Rechteck-Zoom und Doppelklick zum
  Zurücksetzen auf Desktopgeräten
- Vollbildansicht mit `100dvh`, Safe Areas und ohne permanente Kopfzeile
- sekündlich dargestellte WebSocket-Roh-Livewerte in der Legende mit
  Alterskennzeichnung und begrenztem Reconnect-Backoff
- gebündelte, leere Antworten tolerierende Diagrammaktualisierung im Abstand von zehn Sekunden
- begrenzter RAM-Puffer; keine dauerhafte Speicherung hochaufgelöster Rohwerte
- genau eine aggregierte Zeile pro Gerät/UTC-Minute
- Min/Max/Mittel je Messreihe sowie rollierende 1h-/24h-/7d-Statistik
- Adminbereiche für Geräte, MQTT-Hilfe, Speicher, System, Benutzer und Versionen
- Argon2id, serverseitige Sitzungen, sichere Cookies, CSRF und Login-Drosselung
- SQLite WAL, Größenüberwachung und älteste-Messwerte-zuerst-Bereinigung
- Docker Compose mit Mosquitto und Caddy
- Alembic, CI, Unit-, Integrations- und responsive Browser-Tests
- Veröffentlichung fertiger Multi-Architecture-Images in GHCR und eigenständige
  Produktionskonfiguration unter
  [`deploy/production`](deploy/production/README.md)
- reproduzierbare GCP-Infrastruktur mit sicherer Wiederverwendung und
  Importmöglichkeit für bestehende Ressourcen

## Architektur

```text
Shelly Pro 3EM / Tasmota -- MQTT/TLS :8883 --> Mosquitto
                                         |
                               internes MQTT :1883
                                         |
Browser <-- HTTPS/WSS :443 --> Caddy --> FastAPI
                                         |
                       RAM-Livepuffer + Minutenaggregator
                                         |
                                  SQLite (WAL)
```

FastAPI ist ein modularer Monolith. Mosquitto terminiert MQTT-TLS, Caddy
terminiert Website-HTTPS. Die technische Entscheidung steht in
[`docs/architecture.md`](docs/architecture.md).

## Lokale Entwicklung

Voraussetzungen: Python 3.12+, Git und optional Docker.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:GA_MQTT_ENABLED = "false"
alembic upgrade head
uvicorn app.main:app --reload
```

Danach:

- Website: `http://127.0.0.1:8000`
- OpenAPI in Entwicklung: `http://127.0.0.1:8000/api/docs`
- Liveness: `http://127.0.0.1:8000/health/live`
- Readiness: `http://127.0.0.1:8000/health/ready`

Ohne vorhandene Geräte werden in der Standardkonfiguration Römerbad, Bühne,
Küche und Sektbar angelegt. Es werden keine Benutzer und keine Passwörter
automatisch erzeugt.

## Ersten Administrator anlegen

Bei lokaler Entwicklung:

```powershell
python -m app.cli create-admin --username betreiber
```

Im Container:

```powershell
docker compose exec ga-server python -m app.cli create-admin --username betreiber
```

Das Passwort wird verdeckt abgefragt, muss mindestens zwölf Zeichen lang sein
und wird ausschließlich als Argon2id-Hash gespeichert. Es gibt bewusst kein
Konto `admin/admin`.

## Start mit Docker Compose

1. `.env.example` als `.env` kopieren und Werte prüfen.
2. Verzeichnisse `certs/mqtt` und `secrets` anlegen.
3. MQTT-TLS-Zertifikate bereitstellen:
   `certs/mqtt/ca.crt`, `certs/mqtt/server.crt`, `certs/mqtt/server.key`.
4. Eine leere Datei `secrets/ga_mqtt_password` anlegen, wenn der interne Listener
   ohne Authentifizierung verwendet wird. Für internen Login denselben Wert wie
   in der Mosquitto-Konfiguration setzen.
5. Öffentliche MQTT-Benutzer erzeugen:

```powershell
docker run --rm -it `
  -v "${PWD}/mosquitto/config:/mosquitto/config" `
  eclipse-mosquitto:2.0 `
  mosquitto_passwd -c /mosquitto/config/passwords shelly-roemerbad
```

6. Start:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail 100 ga-server
```

Caddy benötigt funktionierende DNS-Einträge und die öffentlichen Ports 80/443,
um automatisch ein Website-Zertifikat zu beziehen. Mosquitto-Zertifikate werden
absichtlich nicht ins Image kopiert.

Sind 80/443 auf einem Entwicklungsrechner belegt, können nur die lokalen
Hostports in `.env` geändert werden, beispielsweise `GA_HTTP_PORT=18080` und
`GA_HTTPS_PORT=18443`. Die Containerports und Produktionsstandards bleiben
80/443.

## Gerät anlegen

Nach Anmeldung Burger-Menü → **Geräte** → Plus-Button:

- Anzeigename, z. B. `Römerbad`
- Geräteart `Shelly Pro 3EM` oder `Tasmota-Steckdose`
- technische Geräte-ID, z. B. `roemerbad`
- Shelly-Topic-Präfix `ga/devices/roemerbad` oder nacktes Tasmota-Topic
  `id139_bauwagen`
- eindeutige MQTT-Client-ID
- MQTT-Benutzer
- optionale Steuerfreigabe und Relais 1 für Tasmota
- Sortierung, Farbe, aktiv/deaktiviert

MQTT-Zugangsdaten werden bewusst nicht über HTML, JavaScript oder API-Antworten
übertragen. Broker-Benutzer werden außerhalb der Weboberfläche mit
`mosquitto_passwd` verwaltet. Eine Umbenennung ändert die interne UUID und die
historischen Daten nicht.

Beim Entfernen gibt es zwei Varianten:

- Anzeige entfernen: Gerät wird deaktiviert, historische Daten bleiben.
- endgültig löschen: Gerät und Messhistorie werden nach zusätzlicher
  Namensbestätigung gelöscht.

## Shelly Pro 3EM konfigurieren

```text
MQTT-Server:
mqtt.strom.gruber-automation.de:8883

TLS:
aktiviert

Benutzer:
<konfigurierter MQTT-Benutzer>

Passwort:
<vergebenes MQTT-Passwort>

Client-ID:
<eindeutige Client-ID>

Topic-Präfix:
ga/devices/<geräte-id>
```

Statusmeldungen:

```text
ga/devices/<geräte-id>/status/em:0
ga/devices/<geräte-id>/online
```

Der Server abonniert:

```text
ga/devices/+/status/em:0
ga/devices/+/online
```

Der Status-Payload kann direkt oder unter dem Schlüssel `em:0` stehen.
Unterstützt werden `a_current`, `b_current`, `c_current`, `total_current`,
`a_voltage`, `b_voltage`, `c_voltage`, `a_act_power`, `b_act_power`,
`c_act_power` und `total_act_power`. Fehlende, ungültige, nicht endliche oder
zusätzliche Werte führen nicht zum Prozessabbruch. Gesamtstrom und
Gesamtleistung werden nur bei drei vollständigen Phasen ersatzweise addiert.

## Tasmota-Steckdose konfigurieren

Im Geräteformular wird nur das nackte Tasmota-Topic gespeichert, beispielsweise
`id139_bauwagen`. Präfixe wie `tele/`, `stat/` oder `cmnd/` sind nicht zulässig.
GA-Server abonniert:

```text
tele/+/SENSOR
tele/+/LWT
stat/+/STATUS10
stat/+/POWER
stat/+/RESULT
```

Schaltbefehle werden ausschließlich serverseitig an
`cmnd/<topic>/POWER` mit `ON` oder `OFF`, QoS 1 und `retain=false`
veröffentlicht. `TOGGLE` und frei übergebene Topics werden abgewiesen. Nach
jedem Reconnect fragt GA-Server den aktuellen POWER-Zustand aller aktiven
Tasmota-Steckdosen mit leerer Payload ab.

Die Oberfläche zeigt „Eingeschaltet“ oder „Ausgeschaltet“ erst nach einer
passenden Meldung auf `stat/<topic>/POWER`. Bis dahin bleibt der Schalter
deaktiviert im Pending-Zustand; nach fünf Sekunden folgt ein Timeout auf den
letzten bestätigten Zustand. Ausführliche Einrichtung und Fehlersuche:
[`docs/tasmota.md`](docs/tasmota.md).

## Speicherung und Begrenzung

SQLite liegt standardmäßig unter `/data/ga-server.db`. Die Tabellen sind:

- `users`
- `sessions`
- `devices` einschließlich Geräteart, Steuerfreigabe und Relaisindex
- `minute_measurements`
- `device_window_stats`
- `settings`
- `audit_log`

Die Einzelmessungen bleiben nur in einem zeitlich und mengenmäßig begrenzten
RAM-Puffer. Je Gerät und UTC-Minute existiert durch einen eindeutigen Index
höchstens eine Minutenzeile. Durchschnitt, Minimum und Maximum werden für alle
elf Messreihen getrennt gespeichert.

Standardgrenzen:

```text
Maximum:                 500 MB
Bereinigung ab:          85 %
Ziel nach Bereinigung:   70 %
Mindesthistorie:         8 Tage
```

Hauptdatei, WAL, SHM und freier Datenträger werden berücksichtigt. Normalerweise
werden nur Werte älter als acht Tage in Batches gelöscht. Bei kritischem freien
Speicher darf die Mindesthistorie unterschritten werden. Benutzer, Geräte,
Einstellungen und Auditdaten bleiben erhalten. Danach folgen WAL-Checkpoint und
inkrementelles Vacuum, kein regelmäßiges blockierendes Voll-Vacuum.

## Backup und Restore

Konsistentes Backup unter Windows:

```powershell
.\scripts\backup.ps1 -Destination .\backups -RetentionDays 14
```

Restore:

1. Wartungsfenster ankündigen.
2. `docker compose stop ga-server`.
3. Aktuelle Volume-Datei zusätzlich sichern.
4. Backup als `/data/ga-server.db` zurückkopieren.
5. Besitzer/Rechte des Volume prüfen.
6. `docker compose start ga-server`.
7. `/health/ready`, Logs und Historie prüfen.

Details für GCP stehen in [`deploy/gcp/README.md`](deploy/gcp/README.md).

## APIs

Öffentlich und ausschließlich lesend:

```text
GET /api/public/devices
GET /api/public/live
GET /api/public/history?metric=power&phase=total&from=...&to=...
GET /api/public/history-batch?series=current:l1,voltage:l1,power:total&from=...&to=...
GET /api/public/window-stats?metric=power&phase=total
WS  /api/public/live-stream
```

Geschützt und nur mit gültiger Sitzung; POST zusätzlich mit CSRF:

```text
GET  /api/admin/control/devices
POST /api/admin/control/devices/{device_id}/power
WS   /api/admin/control-stream
```

Der POST-Body enthält ausschließlich `{"state":"on"}` oder
`{"state":"off"}` und bestätigt mit HTTP 202 nur die Annahme. Bestätigung,
Konflikt oder Timeout folgen über den getrennten Control-WebSocket. Der
öffentliche WebSocket enthält keine Control-Ereignisse.

Die Historie ist auf acht Tage, 2.880 ausgegebene Punkte je Gerät und begrenzte
SQL-Ergebnisse beschränkt. Öffentliche Antworten enthalten keine Sessions,
Hashes, MQTT-Passwörter, privaten Settings oder Auditdaten.

Der Strommonitor fragt alle historischen Minutenreihen gebündelt ungefähr alle
zehn Sekunden ab. Diese Kurvenpunkte sind weiterhin Minutenmittelwerte. Davon
getrennt stammen die Werte in der Legende aus dem letzten tatsächlich über MQTT
empfangenen Rohdatensatz und werden aus dem bestehenden WebSocket-Zustand jede
Sekunde neu dargestellt; es findet keine Interpolation und keine Umrechnung aus
Minutenwerten statt. Die in der Serverkonfiguration definierten Schwellen
`GA_STALE_SECONDS` und `GA_OFFLINE_SECONDS` steuern die Kennzeichnung als
„veraltet“ beziehungsweise „nicht aktuell“.

Auswahl und aufgeklappte Gruppen werden als validierter, versionierter Zustand
im lokalen Browser gespeichert. Die Legende selbst ist nach jedem Seitenaufruf
geschlossen und wird ausschließlich über den GA-Button bedient. Nicht mehr vorhandene
Messstellen oder Reihen werden beim Laden ignoriert. Der Zoom bleibt bei
automatischen Diagrammaktualisierungen bestehen. Auf Touchgeräten wird mit zwei
Fingern horizontal gezoomt und im vergrößerten Bereich verschoben; am Desktop
wird ein Zeitbereich mit gedrückter linker Maustaste aufgezogen. Doppelklick
oder „Zoom zurücksetzen“ stellt den rollierenden 24-Stunden-Bereich wieder her.

## Tests

```powershell
ruff check .
ruff format --check .
mypy app
pytest -m "not e2e" --cov=app
python -m playwright install chromium
pytest -m e2e
alembic upgrade head
docker build -t ga-server:local .
.\scripts\check-secrets.ps1
```

Die vollständige Testmatrix und die Regression für mehrere verkürzte
10-Sekunden-Zyklen stehen in [`docs/testing.md`](docs/testing.md). Das
Migrations- und Rollbackverfahren steht in
[`docs/migration-0.3.0.md`](docs/migration-0.3.0.md).

Die Browser-Tests decken 320×568, 390×844, 844×390, 768×1024, 1366×768,
1920×1080 und 2560×1440 ab.

## Update und Rollback

Für Produktionsserver wird die eigenständige
[`deploy/production`](deploy/production/README.md)-Konfiguration empfohlen. Sie
zieht das freigegebene Image aus GHCR; Quellcode und lokaler Build sind auf dem
Server nicht erforderlich:

```bash
docker compose pull
docker compose up -d --remove-orphans
```

Die folgenden Befehle beschreiben weiterhin den quellcodebasierten
Entwicklungsbetrieb.

Update:

```powershell
.\scripts\backup.ps1
git fetch --prune
git checkout <freigegebener-tag>
docker compose build --pull
docker compose run --rm ga-server alembic upgrade head
docker compose up -d
```

Rollback:

1. Datenbankbackup vor dem Update bereithalten.
2. Vorheriges Release auschecken.
3. Bei nicht rückwärtskompatibler Migration Datenbankbackup zurückspielen.
4. Images neu bauen/starten und Healthchecks prüfen.

## Sicherheit

- TLS für Website und öffentliches MQTT
- kein öffentlicher Port 1883
- keine produktiven Secrets im Repository
- Argon2id-Hashes, zufällige serverseitige Session-Tokens
- `HttpOnly`, im Produktivbetrieb `Secure`, `SameSite=Strict`
- CSRF-Token für alle Schreibaktionen
- Login-Drosselung, Ablauf und Abmeldung
- Auditierung administrativer Änderungen
- Content Security Policy und weitere Browser-Sicherheitsheader
- Container `no-new-privileges`, nicht-root GA-Server, begrenzte JSON-Logs

Setze in Produktion mindestens `GA_ENV=production` und
`GA_COOKIE_SECURE=true`.

## Bekannte Einschränkungen 0.3.0

- Mosquitto-Passwörter werden aus Sicherheitsgründen weder durch die Web-API
  geschrieben noch in der Oberfläche verarbeitet. Der Betreiber verwaltet sie
  mit `mosquitto_passwd`.
- Die Benutzerseite zeigt vorhandene Benutzer; Anlegen/Zurücksetzen ist in der
  API und CLI verfügbar, in der Oberfläche folgt die komfortable Formularführung
  nach dem MVP.
- SQLite setzt eine einzelne schreibende Anwendungsinstanz voraus.
- Der Live-Puffer ist nach Neustart leer; Minutenhistorie bleibt erhalten.
- Die Referenzdateien des privaten `fronius-regler` waren während der
  Implementierung nicht abrufbar. Das Canvas-Verhalten wurde anhand der
  beschriebenen Anforderungen unabhängig implementiert.
