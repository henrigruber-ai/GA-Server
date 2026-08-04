#!/usr/bin/env bash
# File: deploy/gcp/prepare-runtime.sh
# Version: 0.1.0
# Date: 2026-08-04
# Purpose: Materializes runtime secrets, validates TLS files and starts GA-Server on GCP.

set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root: sudo ./deploy/gcp/prepare-runtime.sh" >&2
  exit 1
fi

PROJECT_ID="${PROJECT_ID:-$(curl -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)}"
MQTT_SECRET_NAME="${MQTT_SECRET_NAME:-ga-mqtt-password}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://strom.gruber-automation.de}"
MQTT_PUBLIC_HOST="${MQTT_PUBLIC_HOST:-mqtt.strom.gruber-automation.de}"
ACME_EMAIL="${ACME_EMAIL:-}"
APP_DIR="${APP_DIR:-/opt/ga-server}"

if [[ -z "${ACME_EMAIL}" ]]; then
  echo "ACME_EMAIL is required." >&2
  exit 1
fi

cd "${APP_DIR}"

TOKEN="$(curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token \
  | jq -r '.access_token')"
SECRET_JSON="$(curl -fsS \
  -H "Authorization: Bearer ${TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/${MQTT_SECRET_NAME}/versions/latest:access")"

install -d -m 0750 /srv/ga-data/secrets
printf '%s' "${SECRET_JSON}" | jq -r '.payload.data' | base64 -d \
  > /srv/ga-data/secrets/ga_mqtt_password
chown 10001:10001 /srv/ga-data/secrets/ga_mqtt_password
chmod 0400 /srv/ga-data/secrets/ga_mqtt_password

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

python3 - <<PY
from pathlib import Path

path = Path('.env')
values = {
    'GA_ENV': 'production',
    'GA_PUBLIC_BASE_URL': '${PUBLIC_BASE_URL}',
    'GA_COOKIE_SECURE': 'true',
    'GA_SEED_EXAMPLE_DEVICES': 'true',
    'GA_MQTT_PUBLIC_HOST': '${MQTT_PUBLIC_HOST}',
    'ACME_EMAIL': '${ACME_EMAIL}',
}
lines = path.read_text(encoding='utf-8').splitlines()
seen = set()
out = []
for line in lines:
    key = line.split('=', 1)[0] if '=' in line and not line.lstrip().startswith('#') else None
    if key in values:
        out.append(f'{key}={values[key]}')
        seen.add(key)
    else:
        out.append(line)
for key, value in values.items():
    if key not in seen:
        out.append(f'{key}={value}')
path.write_text('\n'.join(out) + '\n', encoding='utf-8')
PY
chmod 0600 .env

required_files=(
  /srv/ga-data/mqtt/certs/ca.crt
  /srv/ga-data/mqtt/certs/server.crt
  /srv/ga-data/mqtt/certs/server.key
  /srv/ga-data/mqtt/passwords
)
for file in "${required_files[@]}"; do
  if [[ ! -s "${file}" ]]; then
    echo "Missing required production file: ${file}" >&2
    exit 1
  fi
done
chown -R 1883:1883 /srv/ga-data/mosquitto /srv/ga-data/mqtt
chmod 0644 /srv/ga-data/mqtt/certs/ca.crt /srv/ga-data/mqtt/certs/server.crt
chmod 0600 /srv/ga-data/mqtt/certs/server.key /srv/ga-data/mqtt/passwords

docker compose \
  -f docker-compose.yml \
  -f deploy/gcp/docker-compose.gcp.yml \
  config >/dev/null

docker compose \
  -f docker-compose.yml \
  -f deploy/gcp/docker-compose.gcp.yml \
  build --pull

docker compose \
  -f docker-compose.yml \
  -f deploy/gcp/docker-compose.gcp.yml \
  up -d

docker compose \
  -f docker-compose.yml \
  -f deploy/gcp/docker-compose.gcp.yml \
  ps
