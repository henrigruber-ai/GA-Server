<!--
File: deploy/production/README.md
Version: 0.1.1
Date: 2026-08-04
Purpose: Describes installation, updates, rollback, persistence, and GHCR access.
-->

# GA-Server mit fertigen Container-Images betreiben

Dieser Ordner ist eigenständig. Auf dem Server werden weder Python-Quellcode noch
ein lokaler Docker-Build benötigt. Die Standardkonfiguration zieht:

```text
ghcr.io/henrigruber-ai/ga-server:latest
```

Voraussetzungen sind Linux, Docker Engine mit Compose-Plugin, funktionierende
DNS-Einträge sowie die manuell bereitgestellten MQTT-Zertifikate. Diese Anleitung
erstellt keine Cloud-Ressourcen.

## Deployment-Dateien beziehen

### Möglichkeit A: Nur den kleinen Deployment-Ordner herunterladen

Die Dateien können direkt aus dem freigegebenen Branch geladen werden:

```bash
mkdir -p ga-server-production
cd ga-server-production
base_url="https://raw.githubusercontent.com/henrigruber-ai/GA-Server/main/deploy/production"
curl -fsSLO "$base_url/docker-compose.yml"
curl -fsSLO "$base_url/Caddyfile"
curl -fsSLO "$base_url/mosquitto.conf"
curl -fsSLO "$base_url/update.sh"
curl -fsSL "$base_url/.env.example" -o .env.example
chmod 0755 update.sh
```

Für streng reproduzierbare Installationen sollte statt `main` ein Release-Tag,
beispielsweise `v0.1.1`, in `base_url` verwendet werden.

### Möglichkeit B: Repository einmalig klonen

```bash
git clone https://github.com/henrigruber-ai/GA-Server.git
cd GA-Server/deploy/production
chmod 0755 update.sh
```

Ein späteres `git pull` ist nur nötig, wenn sich Compose-, Caddy- oder
Mosquitto-Konfiguration ändern. Reine Anwendungsupdates werden als Image gezogen.

## Konfiguration und Host-Verzeichnisse vorbereiten

```bash
cp .env.example .env
nano .env
```

Mindestens `GA_PUBLIC_BASE_URL`, `GA_MQTT_PUBLIC_HOST` und `ACME_EMAIL` auf die
echten Werte setzen. `GA_PUBLIC_BASE_URL` muss eine Origin ohne Pfad sein, zum
Beispiel `https://strom.example.com`.

Die Standardbasis ist `/srv/ga-server`; `GA_DATA_DIR` kann in `.env` geändert
werden. Bei einem abweichenden Wert die folgenden Befehle entsprechend anpassen:

```bash
export GA_DATA_DIR=/srv/ga-server
sudo install -d -m 0750 "$GA_DATA_DIR"
sudo install -d -m 0750 -o 10001 -g 10001 "$GA_DATA_DIR/app"
sudo install -d -m 0750 "$GA_DATA_DIR/caddy/data" "$GA_DATA_DIR/caddy/config"
sudo install -d -m 0750 -o 1883 -g 1883 \
  "$GA_DATA_DIR/mosquitto/data" "$GA_DATA_DIR/mosquitto/log"
sudo install -d -m 0750 -o root -g 1883 \
  "$GA_DATA_DIR/mqtt/certs" "$GA_DATA_DIR/mqtt/config"
sudo install -d -m 0700 "$GA_DATA_DIR/secrets" "$GA_DATA_DIR/backups"
```

Die numerischen IDs entsprechen dem GA-Server-Image (10001) und dem offiziellen
Mosquitto-Image (1883). Die Caddy-Verzeichnisse bleiben root-eigen und sind nur
im Caddy-Container schreibbar.

## MQTT-Zugang vorbereiten

GA-Server und die öffentlichen Shelly-Clients authentifizieren sich an
Mosquitto. Das Klartext-Passwort von GA-Server liegt ausschließlich in:

```text
/srv/ga-server/secrets/ga_mqtt_password
```

Die Mosquitto-Passwortdatenbank liegt gehasht in:

```text
/srv/ga-server/mqtt/config/passwords
```

Beide Einträge werden einmalig mit demselben zufälligen Passwort erzeugt. Die
gehashte Datenbank entsteht direkt aus dem Secret; es gibt keine
Klartext-Zwischendatei:

```bash
sudo sh -c '
  umask 077
  openssl rand -base64 32 > /srv/ga-server/secrets/ga_mqtt_password
'
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

Bei geändertem `GA_DATA_DIR` die absoluten Pfade anpassen. Weitere
Shelly-Benutzer werden interaktiv ergänzt:

```bash
sudo docker run --rm -it \
  -v /srv/ga-server/mqtt/config:/mosquitto/config \
  eclipse-mosquitto:2.0.22 \
  mosquitto_passwd /mosquitto/config/passwords shelly-geraet
```

Das Passwort nicht in der Shell-History angeben.

## MQTT-TLS-Zertifikate bereitstellen

Die Zertifikate werden außerhalb dieses Projekts erzeugt. Keine privaten
Schlüssel in das Repository oder Container-Image kopieren. Mosquitto erwartet:

```text
/srv/ga-server/mqtt/certs/ca.crt
/srv/ga-server/mqtt/certs/server.crt
/srv/ga-server/mqtt/certs/server.key
```

`server.crt` muss zum öffentlichen Namen aus `GA_MQTT_PUBLIC_HOST` passen.
Empfohlene Rechte:

```bash
sudo chown root:1883 /srv/ga-server/mqtt/certs/*
sudo chmod 0644 /srv/ga-server/mqtt/certs/ca.crt \
  /srv/ga-server/mqtt/certs/server.crt
sudo chmod 0640 /srv/ga-server/mqtt/certs/server.key
```

Caddy verwaltet das Website-Zertifikat automatisch und speichert ACME-Zustand
unter `/srv/ga-server/caddy/data`.

## Prüfen und starten

```bash
docker compose config
docker compose pull
docker compose up -d
docker compose ps
```

Status und Logs:

```bash
curl --fail https://strom.example.com/health/ready
docker compose logs --tail 100 ga-server mosquitto caddy
```

Nach dem ersten Start kann ein Administrator angelegt werden:

```bash
docker compose exec ga-server python -m app.cli create-admin --username betreiber
```

Öffentlich gebunden sind standardmäßig nur TCP 80, TCP/UDP 443 und TCP 8883.
Port 1883, FastAPI-Port 8000 und Caddy-Admin-Port 2019 bleiben innerhalb der
Container-Netzwerke.

## Updates

Für jedes normale Anwendungsupdate genügen:

```bash
docker compose pull
docker compose up -d --remove-orphans
```

Alternativ:

```bash
./update.sh
```

Das Skript bricht bei Fehlern ab, löscht keine Volumes oder persistenten Daten
und entfernt nur nicht mehr verwendete Image-Layer.

## Feste Version und Rollback

`latest` bewegt sich mit jedem erfolgreich veröffentlichten Stand von `main`.
Ein Versions-Tag ist unveränderlich. Für einen reproduzierbaren Stand in `.env`
setzen:

```text
GA_SERVER_IMAGE=ghcr.io/henrigruber-ai/ga-server:0.1.1
```

Rollback:

```bash
nano .env
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
```

Vor einem Update mit Datenbankmigrationen immer ein konsistentes SQLite-Backup
erstellen und die Release Notes prüfen. Ein Image-Rollback ersetzt bei nicht
rückwärtskompatiblen Migrationen keinen Datenbank-Restore.

## Persistente Daten und Backups

Alle wichtigen Zustände liegen auf dem Host:

| Pfad unter `GA_DATA_DIR` | Inhalt |
| --- | --- |
| `app` | SQLite-Datenbank einschließlich WAL/SHM |
| `caddy/data` | ACME-Zertifikate und Caddy-Daten |
| `caddy/config` | Caddy-Laufzeitkonfiguration |
| `mosquitto/data` | persistente MQTT-Nachrichten |
| `mosquitto/log` | reservierter persistenter Logpfad |
| `mqtt/certs` | manuell bereitgestellte MQTT-TLS-Dateien |
| `mqtt/config` | gehashte Mosquitto-Passwortdatenbank |
| `secrets` | Klartext-Secrets mit restriktiven Rechten |
| `backups` | Ziel für Betreiber-Backups |

`docker compose down` entfernt diese Bind-Mount-Daten nicht. Trotzdem regelmäßig
konsistente SQLite-Backups und Restore-Tests durchführen.

## GHCR-Paket und Anmeldung

Verfügbare Image-Tags:

- `latest`, `main` und `sha-<kurzer-commit-sha>` für erfolgreiche Stände von
  `main`
- `0.1.1`, `0.1`, `0` und `sha-<kurzer-commit-sha>` für das Tag `v0.1.1`

Direkter Pull:

```bash
docker pull ghcr.io/henrigruber-ai/ga-server:latest
```

Falls das Paket privat ist, mit einem GitHub-Token mit mindestens
`read:packages` anmelden:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io \
  -u GITHUB-BENUTZERNAME --password-stdin
```

Keinen echten Token in `.env`, Compose oder dieses Repository schreiben. Das
GHCR-Paket sollte in GitHub nach Möglichkeit manuell auf öffentlich lesbar
gestellt werden; dann benötigt der Produktionsserver kein dauerhaft
gespeichertes GitHub-Zugriffstoken.
