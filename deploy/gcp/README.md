<!--
File: deploy/gcp/README.md
Version: 0.1.1
Date: 2026-08-04
Purpose: Provides a complete small-VM deployment, backup, update, rollback, and recovery runbook.
-->

# GCP-Betriebshandbuch

## Empfohlene Basis

Für vier bis etwa zwanzig Geräte genügt typischerweise:

- Compute Engine `e2-small` (2 vCPU, 2 GB RAM); bei knappen Reserven `e2-medium`
- Ubuntu 24.04 LTS
- 20 GB Boot-Disk
- separate persistente Balanced-PD ab 20 GB für Docker-Daten und Backups
- statische externe IPv4-Adresse
- täglicher Snapshot plus anwendungsseitiges SQLite-Backup

Container-Optimized OS ist möglich, Ubuntu ist für weniger erfahrene Betreiber
wegen Docker-Compose, Zertifikatsablage und Diagnose einfacher.

## DNS

Beide A/AAAA-Einträge zeigen auf dieselbe statische IP:

```text
strom.gruber-automation.de
mqtt.strom.gruber-automation.de
```

Die Website und der MQTT-Broker sind verschiedene Protokolle/Endpunkte.

## Firewall

Öffentlich:

- TCP 80 und 443 für Caddy/ACME/HTTPS
- TCP 8883 für MQTT über TLS

Nicht öffentlich:

- TCP 1883
- Caddy-Admin-Port 2019
- FastAPI-Port 8000

SSH 22 nur über IAP (`35.235.240.0/20`) oder definierte Betreiber-IP-Adressen.
Bevorzugt OS Login, MFA und keine Passwortanmeldung.

## VM und Docker vorbereiten

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Danach neu anmelden. Für den Betrieb genügt der eigenständige Ordner
[`deploy/production`](../production/README.md); Python-Quellcode und lokaler
Image-Build werden auf der VM nicht benötigt. Die persistente Disk unter
`/srv/ga-server` einhängen und per UUID in `/etc/fstab` eintragen. Vor dem
Formatieren den exakten Gerätenamen mit `lsblk` prüfen.

## Secrets und Zertifikate

Caddy bezieht das HTTPS-Zertifikat automatisch und speichert ACME-Daten im
persistenten `caddy-data`-Volume.

Für Mosquitto wird ein eigenes Serverzertifikat benötigt, dessen SAN
`mqtt.strom.gruber-automation.de` enthält. Sichere Optionen:

1. ACME-DNS-Challenge außerhalb des Containers und kontrolliertes Kopieren nach
   `certs/mqtt`.
2. Google Certificate Manager plus gesicherter Export ist nur geeignet, wenn der
   private Schlüssel für Mosquitto verfügbar ist.
3. Interne CA nur, wenn deren Root-Zertifikat sicher auf allen Shellys installiert
   werden kann.

Dateien mit restriktiven Rechten unter der Produktionsbasis:

```text
/srv/ga-server/mqtt/certs/ca.crt
/srv/ga-server/mqtt/certs/server.crt
/srv/ga-server/mqtt/certs/server.key
/srv/ga-server/secrets/ga_mqtt_password
/srv/ga-server/mqtt/config/passwords
```

Private Schlüssel, `.env` und Passwörter nie committen. Das Erzeugen des
internen GA-Server-Zugangs und weiterer MQTT-Benutzer ist in der
[Produktionsanleitung](../production/README.md#mqtt-zugang-vorbereiten)
beschrieben.

## Produktionsstart

```bash
cd /opt/ga-server-production
cp .env.example .env
nano .env
chmod 600 .env
docker compose config
docker compose pull
docker compose up -d
docker compose ps
curl --fail https://strom.gruber-automation.de/health/ready
```

Die konkreten Verzeichnis-, Besitzer- und Zertifikatsbefehle stehen in
[`deploy/production/README.md`](../production/README.md). Die obigen relativen
Pfade sind nur eine Kurzform; produktiv liegen die Dateien standardmäßig unter
`/srv/ga-server`.

Ersten Administrator anlegen:

```bash
docker compose exec ga-server python -m app.cli create-admin --username betreiber
```

MQTT-TLS extern testen:

```bash
mosquitto_sub \
  -h mqtt.strom.gruber-automation.de -p 8883 \
  --cafile certs/mqtt/ca.crt \
  -u shelly-roemerbad -P '<nicht-in-shell-history-speichern>' \
  -t 'ga/devices/roemerbad/online' -C 1
```

Passwörter bevorzugt interaktiv beziehungsweise über geschützte Dateien
übergeben, nicht dauerhaft in Shell-History.

## Healthchecks und Diagnose

```bash
curl -fsS https://strom.gruber-automation.de/health/live
curl -fsS https://strom.gruber-automation.de/health/ready
docker compose ps
docker compose logs --tail 200 ga-server
docker compose logs --tail 200 mosquitto
docker compose logs --tail 200 caddy
docker stats --no-stream
df -h
du -h /var/lib/docker/volumes/*/_data 2>/dev/null | sort -h | tail
```

Typische Fehler:

- Website-Zertifikat fehlt: DNS, Ports 80/443 und Caddy-Logs prüfen.
- MQTT-TLS scheitert: SAN, Zertifikatskette, Uhrzeit und Port 8883 prüfen.
- Gerät unbekannt: technische ID im Topic stimmt nicht mit Adminbereich überein.
- Readiness 503: Datenbankrechte, Datenverzeichnis und MQTT-Initialisierung prüfen.
- Speicherwarnung: Adminbereich → Datenspeicher, `df -h`, WAL und Backups prüfen.

## Backup

Täglich eine SQLite-Backup-API ausführen (Python `sqlite3.Connection.backup`,
nicht bloß die laufende Datei kopieren), verschlüsselt in einen getrennten
GCS-Bucket übertragen und nach 14 Tagen löschen. GCS:

- Uniform Bucket-Level Access
- Public Access Prevention
- CMEK optional
- Lifecycle-Regel nach betrieblicher Vorgabe
- dediziertes Servicekonto nur mit Object-Creator/Object-Viewer nach Bedarf

Zusätzlich täglicher PD-Snapshot. Ein Snapshot ersetzt keinen getesteten
SQLite-Restore.

## Restore

1. Incident und gewünschten Wiederherstellungspunkt festhalten.
2. `docker compose stop ga-server`.
3. Aktuelle Datenbank/WAL/SHM separat sichern.
4. Konsistentes Backup als `ga-server.db` in das Datenvolume schreiben.
5. `-wal` und `-shm` nur nach gesicherter Prüfung entfernen.
6. Besitzer/Rechte korrigieren.
7. `docker compose start ga-server`.
8. Readiness, Logs, Benutzer, Geräte und Historie prüfen.
9. Ergebnis im Betriebsprotokoll dokumentieren.

Restore mindestens vierteljährlich auf einer separaten VM testen.

## Update

```bash
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
curl --fail https://strom.gruber-automation.de/health/ready
```

Vor jedem Update Release Notes und Migrationen lesen und ein konsistentes
SQLite-Backup erstellen. Ein `git pull` ist nur nötig, wenn sich die
Deployment-Konfiguration selbst geändert hat.

## Rollback

- vorheriges Image/Tag und Datenbankbackup bereithalten
- in `.env` beispielsweise
  `GA_SERVER_IMAGE=ghcr.io/henrigruber-ai/ga-server:0.1.1` setzen
- `docker compose pull && docker compose up -d --remove-orphans` ausführen
- nach nicht rückwärtskompatibler Migration das zugehörige Backup restaurieren
- nie blind `alembic downgrade` in Produktion ausführen
- anschließend Healthchecks, MQTT-Eingang und öffentliche Darstellung prüfen

## Logging und Alarmierung

Docker-JSON-Logs sind auf 10 MB × 5 Dateien je Dienst begrenzt. Für zentrale
Auswertung optional Google Ops Agent einsetzen. Sinnvolle Alarme:

- `/health/ready` länger als fünf Minuten fehlerhaft
- freier Datenträger unter 15 %
- Container-Neustarts
- MQTT länger als fünf Minuten ohne Nachricht bei erwarteter Veranstaltung
- Caddy/Mosquitto-Zertifikat weniger als 21 Tage gültig

## Wartung

- monatlich Betriebssystem und Docker aktualisieren
- Zertifikatsverlängerung überwachen
- Backups und Restore-Berichte prüfen
- deaktivierte Benutzer/Geräte kontrollieren
- Speichertrend und Bereinigungs-Audit prüfen
- Secrets bei Personalwechsel rotieren
