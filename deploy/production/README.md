<!--
File: deploy/production/README.md
Version: 0.2.0
Date: 2026-08-04
Purpose: Describes image-only production installation, updates, rollback and persistence.
-->

# GA-Server mit fertigen Container-Images betreiben

Dieser Ordner ist eigenständig. Auf dem Server werden weder Python-Quellcode
noch Repository-Checkout oder lokaler Docker-Build benötigt. Standardmäßig
wird der feste Release-Stand geladen:

```text
ghcr.io/henrigruber-ai/ga-server:0.2.0
```

## Deployment-Dateien ohne Repository beziehen

Für Produktion einen Release-Tag oder vollständigen Commit-SHA verwenden:

```bash
install -d -m 0755 /opt/ga-server-production
cd /opt/ga-server-production
deployment_ref="v0.2.0"
base_url="https://raw.githubusercontent.com/henrigruber-ai/GA-Server/${deployment_ref}/deploy/production"
curl -fsSLO "$base_url/docker-compose.yml"
curl -fsSLO "$base_url/Caddyfile"
curl -fsSLO "$base_url/mosquitto.conf"
curl -fsSLO "$base_url/update.sh"
curl -fsSL "$base_url/.env.example" -o .env.example
chmod 0755 update.sh
```

`main` ist für kontrollierte Tests möglich, aber beweglich. Ein Release-Tag
oder vollständiger Commit fixiert die Deployment-Konfiguration. Auf GCP
automatisiert [`deploy/gcp/bootstrap.sh`](../gcp/bootstrap.sh) denselben
schlanken Download.

## Konfiguration und Host-Verzeichnisse

```bash
cp .env.example .env
nano .env
chmod 0600 .env
```

Mindestens `GA_PUBLIC_BASE_URL`, `GA_MQTT_PUBLIC_HOST` und `ACME_EMAIL` setzen.
`GA_PUBLIC_BASE_URL` ist eine HTTPS-Origin ohne Pfad.

```bash
export GA_DATA_DIR=/srv/ga-server
sudo install -d -m 0750 "$GA_DATA_DIR"
sudo install -d -m 0750 -o 10001 -g 10001 "$GA_DATA_DIR/app"
sudo install -d -m 0700 "$GA_DATA_DIR/backups"
sudo install -d -m 0750 "$GA_DATA_DIR/caddy/data" "$GA_DATA_DIR/caddy/config"
sudo install -d -m 0750 -o 1883 -g 1883 \
  "$GA_DATA_DIR/mosquitto/data" "$GA_DATA_DIR/mosquitto/log"
sudo install -d -m 0750 -o root -g 1883 \
  "$GA_DATA_DIR/mqtt/certs" "$GA_DATA_DIR/mqtt/config"
sudo install -d -m 0700 "$GA_DATA_DIR/secrets"
```

GA-Server verwendet UID/GID `10001`, Mosquitto `1883`. Caddy-Verzeichnisse
bleiben root-eigen.

## MQTT-Secret und Passwortdatenbank

Keine Secrets im Repository, Image oder `.env`. GA-Server liest:

```text
GA_MQTT_PASSWORD_FILE=/run/secrets/ga_mqtt_password
```

Hostdateien:

```text
/srv/ga-server/secrets/ga_mqtt_password
/srv/ga-server/mqtt/config/passwords
```

Ein neues Secret wird außerhalb des Repositorys erzeugt. Die Passwortdatenbank
wird ohne Klartext-Zwischendatei erstellt:

```bash
sudo chown 10001:1883 /srv/ga-server/secrets/ga_mqtt_password
sudo chmod 0440 /srv/ga-server/secrets/ga_mqtt_password
sudo docker run --rm -i \
  -v /srv/ga-server/mqtt/config:/mosquitto/config \
  eclipse-mosquitto:2.0.22 \
  sh -c 'IFS= read -r mqtt_value; mosquitto_passwd -b -c \
    /mosquitto/config/passwords ga-server "$mqtt_value"' \
  < /srv/ga-server/secrets/ga_mqtt_password
sudo chown root:1883 /srv/ga-server/mqtt/config/passwords
sudo chmod 0640 /srv/ga-server/mqtt/config/passwords
```

Weitere Gerätebenutzer interaktiv ergänzen; Passwörter nicht in der
Shell-History angeben.

## MQTT-TLS-Zertifikate

Außerhalb des Projekts bereitstellen:

```text
/srv/ga-server/mqtt/certs/ca.crt
/srv/ga-server/mqtt/certs/server.crt
/srv/ga-server/mqtt/certs/server.key
```

```bash
sudo chown root:1883 /srv/ga-server/mqtt/certs/*
sudo chmod 0644 /srv/ga-server/mqtt/certs/ca.crt \
  /srv/ga-server/mqtt/certs/server.crt
sudo chmod 0640 /srv/ga-server/mqtt/certs/server.key
```

Der private Schlüssel wird nie ins Image kopiert. Das Serverzertifikat muss zum
öffentlichen MQTT-Namen passen. Caddy speichert ACME-Daten persistent unter
`/srv/ga-server/caddy/data`.

## Validieren und starten

```bash
docker compose config
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
curl --fail https://<PUBLIC_HOSTNAME>/health/ready
```

Öffentlich gebunden sind nur TCP 80, TCP/UDP 443 und TCP 8883. Port 1883,
FastAPI 8000 und Caddy-Admin 2019 bleiben intern.

## Updates und Tags

```bash
./update.sh
```

oder:

```bash
docker compose config
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
```

Tag-Verhalten:

- `latest`: beweglicher erfolgreicher Main-Stand.
- `main`: ebenfalls beweglicher Main-Stand.
- `sha-<commit>`: konkreter Commit, rückverfolgbar und für Rollback geeignet.
- `0.2.0`: fester Release-Stand und Produktionsstandard.

Normale Image-Updates benötigen weder Terraform noch `git pull`.

## Rollback

In `.env` den vorherigen Tag setzen:

```text
GA_SERVER_IMAGE=ghcr.io/henrigruber-ai/ga-server:sha-<PREVIOUS_COMMIT>
```

Danach `config`, `pull`, `up -d --remove-orphans`, `ps` und Readiness prüfen.
Vor Migrationen ein konsistentes SQLite-Backup erstellen. Ein Image-Rollback
ersetzt bei inkompatiblen Migrationen keinen Datenbank-Restore.

## Persistenz, Backup und Restore

| Pfad unter `/srv/ga-server` | Inhalt |
| --- | --- |
| `app` | SQLite-Datenbank einschließlich WAL/SHM |
| `backups` | lokale Betreiber-Backups |
| `caddy/data` | ACME-Zertifikate und Caddy-Daten |
| `caddy/config` | Caddy-Laufzeitkonfiguration |
| `mosquitto/data` | persistente MQTT-Nachrichten |
| `mosquitto/log` | persistenter Logpfad |
| `mqtt/certs` | manuelle MQTT-TLS-Dateien |
| `mqtt/config` | gehashte Mosquitto-Passwortdatenbank |
| `secrets` | dateibasierte Klartext-Secrets mit restriktiven Rechten |

Container-Neuerstellung löscht diese Bind-Mounts nicht. Disk-Snapshots,
konsistente SQLite-Backups, externe GCS-Kopien und Image-Rollback erfüllen
unterschiedliche Zwecke. Restore regelmäßig getrennt von Produktion testen.

## GHCR-Zugriff

Bei einem öffentlichen Paket ist keine Anmeldung nötig:

```bash
docker pull ghcr.io/henrigruber-ai/ga-server:0.2.0
```

Bei einem privaten Paket ein Token ausschließlich mit `read:packages` über
`docker login --password-stdin` verwenden. Token nicht committen, nicht in
`.env` oder Terraform speichern und nicht direkt in Befehlszeilen schreiben.

## Diagnose

```bash
docker compose ps
docker compose logs --tail 200 ga-server mosquitto caddy
curl -fsS https://<PUBLIC_HOSTNAME>/health/live
curl -fsS https://<PUBLIC_HOSTNAME>/health/ready
```

Ersten Administrator interaktiv anlegen:

```bash
docker compose exec ga-server \
  python -m app.cli create-admin --username betreiber
```
