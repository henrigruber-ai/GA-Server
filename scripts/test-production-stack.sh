#!/usr/bin/env bash
# File: scripts/test-production-stack.sh
# Version: 0.1.1
# Date: 2026-08-04
# Purpose: Smoke-tests the production Compose stack with temporary credentials and certificates.

set -Eeuo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repository_root/deploy/production/docker-compose.yml"
runtime_dir="$(mktemp -d)"
host_runtime_dir="$runtime_dir"
openssl_subject_prefix="/"
if command -v cygpath >/dev/null 2>&1; then
  host_runtime_dir="$(cygpath -m "$runtime_dir")"
  openssl_subject_prefix="//"
fi
environment_file="$runtime_dir/production.env"
project_suffix="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
export COMPOSE_PROJECT_NAME="ga-server-ci-$project_suffix"
test_image="${GA_SERVER_TEST_IMAGE:-ga-server:ci}"

compose() {
  docker compose --env-file "$environment_file" -f "$compose_file" "$@"
}

cleanup() {
  if [[ -f "$environment_file" ]]; then
    compose down --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -rf "$runtime_dir"
}
trap cleanup EXIT

report_failure() {
  local status="$?"
  echo "Production stack smoke test failed; service status and logs follow." >&2
  compose ps >&2 || true
  for service in mosquitto ga-server caddy; do
    container_id="$(compose ps -q "$service" 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      docker inspect \
        --format '{{json .Config.Healthcheck.Test}} {{json .State.Health.Log}}' \
        "$container_id" >&2 || true
    fi
  done
  compose logs --no-color >&2 || true
  return "$status"
}
trap report_failure ERR

wait_for_health() {
  local service="$1"
  local container_id
  local health
  for _ in {1..60}; do
    container_id="$(compose ps -q "$service")"
    if [[ -n "$container_id" ]]; then
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
      if [[ "$health" == "healthy" || "$health" == "running" ]]; then
        return 0
      fi
    fi
    sleep 2
  done
  compose ps
  compose logs --no-color "$service"
  return 1
}

mkdir -p \
  "$runtime_dir/app" \
  "$runtime_dir/caddy/data" \
  "$runtime_dir/caddy/config" \
  "$runtime_dir/mosquitto/data" \
  "$runtime_dir/mosquitto/log" \
  "$runtime_dir/mqtt/certs" \
  "$runtime_dir/mqtt/config" \
  "$runtime_dir/secrets" \
  "$runtime_dir/backups"
chmod 0777 \
  "$runtime_dir/app" \
  "$runtime_dir/caddy/data" \
  "$runtime_dir/caddy/config" \
  "$runtime_dir/mosquitto/data" \
  "$runtime_dir/mosquitto/log" \
  "$runtime_dir/mqtt/config"

openssl rand -base64 32 >"$runtime_dir/secrets/ga_mqtt_password"
test_value="$(tr -d '\r\n' <"$runtime_dir/secrets/ga_mqtt_password")"
printf '%s\n' "$test_value" >"$runtime_dir/secrets/ga_mqtt_password"
chmod 0444 "$runtime_dir/secrets/ga_mqtt_password"

docker pull eclipse-mosquitto:2.0.22
docker run --rm -i --user 1883:1883 \
  -v "$host_runtime_dir/mqtt/config:/mosquitto/config" \
  eclipse-mosquitto:2.0.22 \
  sh -c 'IFS= read -r mqtt_value; mosquitto_passwd -b -c /mosquitto/config/passwords ga-server "$mqtt_value"' \
  <"$runtime_dir/secrets/ga_mqtt_password"
chmod 0644 "$runtime_dir/mqtt/config/passwords"
[[ -s "$runtime_dir/mqtt/config/passwords" ]]

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj "${openssl_subject_prefix}CN=GA-Server CI CA" \
  -keyout "$runtime_dir/ca.key" \
  -out "$runtime_dir/mqtt/certs/ca.crt" \
  2>/dev/null
openssl req -newkey rsa:2048 -nodes \
  -subj "${openssl_subject_prefix}CN=localhost" \
  -keyout "$runtime_dir/mqtt/certs/server.key" \
  -out "$runtime_dir/server.csr" \
  2>/dev/null
printf 'subjectAltName=DNS:localhost\n' >"$runtime_dir/server.ext"
openssl x509 -req -days 1 \
  -in "$runtime_dir/server.csr" \
  -CA "$runtime_dir/mqtt/certs/ca.crt" \
  -CAkey "$runtime_dir/ca.key" \
  -CAcreateserial \
  -extfile "$runtime_dir/server.ext" \
  -out "$runtime_dir/mqtt/certs/server.crt" \
  2>/dev/null
chmod 0644 "$runtime_dir/mqtt/certs/"*

cat >"$environment_file" <<EOF
GA_SERVER_IMAGE=$test_image
GA_DATA_DIR=$host_runtime_dir
GA_PUBLIC_BASE_URL=http://localhost
GA_MQTT_PUBLIC_HOST=localhost
GA_TIMEZONE=UTC
GA_DB_MAX_MB=50
GA_DB_CLEANUP_START_PERCENT=85
GA_DB_CLEANUP_TARGET_PERCENT=70
GA_MIN_FREE_DISK_MB=1
GA_MQTT_USERNAME=ga-server
GA_MQTT_BIND_ADDRESS=127.0.0.1
GA_MQTT_TLS_PORT=18883
GA_HTTP_BIND_ADDRESS=127.0.0.1
GA_HTTP_PORT=18080
GA_HTTPS_BIND_ADDRESS=127.0.0.1
GA_HTTPS_PORT=18443
ACME_EMAIL=ci@example.invalid
EOF

echo "Validating the rendered production Compose configuration..."
compose config --quiet
compose config >"$runtime_dir/rendered-compose.yml"
if grep -Eq 'published: "?1883"?' "$runtime_dir/rendered-compose.yml"; then
  echo "Internal MQTT port 1883 must not be published." >&2
  exit 1
fi

docker image inspect "$test_image" >/dev/null
docker pull caddy:2.11.4-alpine

echo "Starting the production stack with temporary test material..."
compose up -d --pull never
wait_for_health mosquitto
wait_for_health ga-server
wait_for_health caddy
curl --fail --silent --show-error http://localhost:18080/health/ready >/dev/null

echo "Validating public MQTT TLS, Caddy, and GA-Server-to-Mosquitto connectivity..."
openssl s_client \
  -connect 127.0.0.1:18883 \
  -servername localhost \
  -CAfile "$runtime_dir/mqtt/certs/ca.crt" \
  -verify_hostname localhost \
  -verify_return_error \
  </dev/null >/dev/null 2>&1
compose exec -T caddy sh -c 'caddy validate --config /etc/caddy/Caddyfile'
compose exec -T ga-server python -c \
  "from pathlib import Path; from app.config import settings; assert settings.mqtt_password == Path('/run/secrets/ga_mqtt_password').read_text(encoding='utf-8').strip()"
compose exec -T ga-server python -c \
  "from app.config import settings; import paho.mqtt.client as mqtt; c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2); c.username_pw_set(settings.mqtt_username, settings.mqtt_password); c.connect(settings.mqtt_host, settings.mqtt_port, 10); c.publish('ci/connectivity', 'ok', qos=1).wait_for_publish(5); c.disconnect()"

echo "Verifying SQLite persistence after recreating GA-Server..."
compose exec -T ga-server python -c \
  "import sqlite3; c=sqlite3.connect('/data/ga-server.db'); c.execute('CREATE TABLE IF NOT EXISTS ci_persistence (value TEXT NOT NULL)'); c.execute('DELETE FROM ci_persistence'); c.execute(\"INSERT INTO ci_persistence VALUES ('survives')\"); c.commit(); c.close()"
compose up -d --force-recreate --no-deps --pull never ga-server
wait_for_health ga-server
compose exec -T ga-server python -c \
  "import sqlite3; c=sqlite3.connect('/data/ga-server.db'); assert c.execute('SELECT value FROM ci_persistence').fetchone() == ('survives',); c.close()"

echo "Verifying retained Mosquitto data after recreating Mosquitto..."
compose exec -T mosquitto mosquitto_pub \
  -h 127.0.0.1 -p 1883 -u ga-server -P "$test_value" \
  -t ci/persistence -m survives -q 1 -r
compose stop mosquitto
compose up -d --force-recreate --no-deps --pull never mosquitto
wait_for_health mosquitto
retained_value="$(compose exec -T mosquitto mosquitto_sub \
  -h 127.0.0.1 -p 1883 -u ga-server -P "$test_value" \
  -t ci/persistence -C 1 -W 5)"
[[ "$retained_value" == "survives" ]]

echo "Checking that internal service ports are not host-published..."
ga_server_binding="$(docker port "$(compose ps -q ga-server)" 8000/tcp 2>/dev/null || true)"
mosquitto_binding="$(docker port "$(compose ps -q mosquitto)" 1883/tcp 2>/dev/null || true)"
[[ -z "$ga_server_binding" ]]
[[ -z "$mosquitto_binding" ]]

echo "Checking that runtime secrets are absent from the image..."
docker run --rm --entrypoint sh "$test_image" -c \
  'test ! -e /run/secrets/ga_mqtt_password && test ! -e /mosquitto/config/passwords && test ! -e /mosquitto/certs/server.key'

compose ps
echo "Production stack smoke test completed successfully."
