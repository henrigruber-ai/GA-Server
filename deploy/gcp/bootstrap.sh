#!/usr/bin/env bash
# File: deploy/gcp/bootstrap.sh
# Version: 0.2.0
# Date: 2026-08-04
# Purpose: Idempotently prepares a GCP host and starts the published production stack.

set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo --preserve-env=GA_* ./bootstrap.sh" >&2
  exit 1
fi

GA_PROJECT_ID="${GA_PROJECT_ID:-}"
GA_DATA_DEVICE_NAME="${GA_DATA_DEVICE_NAME:-ga-server-data}"
GA_ALLOW_DATA_DISK_FORMAT="${GA_ALLOW_DATA_DISK_FORMAT:-false}"
GA_DEPLOYMENT_SOURCE_BASE_URL="${GA_DEPLOYMENT_SOURCE_BASE_URL:-https://raw.githubusercontent.com/henrigruber-ai/GA-Server}"
GA_DEPLOYMENT_SOURCE_REF="${GA_DEPLOYMENT_SOURCE_REF:-v0.2.0}"
GA_SERVER_IMAGE_TAG="${GA_SERVER_IMAGE_TAG:-0.2.0}"
GA_MQTT_SECRET_NAME="${GA_MQTT_SECRET_NAME:-}"
GA_PUBLIC_BASE_URL="${GA_PUBLIC_BASE_URL:-}"
GA_MQTT_PUBLIC_HOST="${GA_MQTT_PUBLIC_HOST:-}"
GA_ACME_EMAIL="${GA_ACME_EMAIL:-}"
GA_DATA_DIR="/srv/ga-server"
GA_STACK_DIR="/opt/ga-server-production"

case "${GA_ALLOW_DATA_DISK_FORMAT}" in
  true | false) ;;
  *)
    echo "GA_ALLOW_DATA_DISK_FORMAT must be true or false." >&2
    exit 1
    ;;
esac

if [[ ! "${GA_DEPLOYMENT_SOURCE_REF}" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$ ]] ||
  [[ "${GA_DEPLOYMENT_SOURCE_REF}" == *".."* ]]; then
  echo "GA_DEPLOYMENT_SOURCE_REF is not a safe Git ref." >&2
  exit 1
fi

if [[ ! "${GA_SERVER_IMAGE_TAG}" =~ ^(latest|main|sha-[0-9a-f]{7,40}|[0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
  echo "GA_SERVER_IMAGE_TAG must be latest, main, sha-<commit>, or x.y.z." >&2
  exit 1
fi

if [[ ! "${GA_PUBLIC_BASE_URL}" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
  echo "GA_PUBLIC_BASE_URL must be an HTTPS origin without a path." >&2
  exit 1
fi

if [[ ! "${GA_MQTT_PUBLIC_HOST}" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "GA_MQTT_PUBLIC_HOST must be a DNS hostname." >&2
  exit 1
fi

if [[ -z "${GA_ACME_EMAIL}" || "${GA_ACME_EMAIL}" != *@* ]]; then
  echo "GA_ACME_EMAIL is required." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg jq e2fsprogs

install -o root -g root -m 0755 -d /etc/apt/keyrings
if [[ ! -s /etc/apt/keyrings/docker.gpg ]]; then
  docker_key_tmp="$(mktemp)"
  trap 'rm -f "${docker_key_tmp:-}" "${download_dir:-}"' EXIT
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "${docker_key_tmp}"
  gpg --dearmor --yes --output /etc/apt/keyrings/docker.gpg "${docker_key_tmp}"
  chmod 0644 /etc/apt/keyrings/docker.gpg
fi

# shellcheck disable=SC1091
. /etc/os-release
printf '%s\n' \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

install -o root -g root -m 0750 -d "${GA_DATA_DIR}"
data_device="/dev/disk/by-id/google-${GA_DATA_DEVICE_NAME}"
for _ in {1..60}; do
  [[ -b "${data_device}" ]] && break
  sleep 2
done
if [[ ! -b "${data_device}" ]]; then
  echo "Data disk ${data_device} was not found." >&2
  exit 1
fi

if mountpoint -q "${GA_DATA_DIR}"; then
  expected_uuid="$(blkid -s UUID -o value "${data_device}")"
  mounted_source="$(findmnt -n -o SOURCE --target "${GA_DATA_DIR}")"
  mounted_uuid="$(blkid -s UUID -o value "${mounted_source}")"
  if [[ -z "${expected_uuid}" || "${mounted_uuid}" != "${expected_uuid}" ]]; then
    echo "${GA_DATA_DIR} is mounted from an unexpected device; refusing to continue." >&2
    exit 1
  fi
else
  if ! blkid "${data_device}" >/dev/null 2>&1; then
    if [[ "${GA_ALLOW_DATA_DISK_FORMAT}" != "true" ]]; then
      echo "Data disk has no filesystem; refusing to format without GA_ALLOW_DATA_DISK_FORMAT=true." >&2
      exit 1
    fi
    mkfs.ext4 -F -L ga-server-data "${data_device}"
  fi

  data_uuid="$(blkid -s UUID -o value "${data_device}")"
  if [[ -z "${data_uuid}" ]]; then
    echo "Could not determine the data disk UUID." >&2
    exit 1
  fi
  if grep -Eq "[[:space:]]${GA_DATA_DIR//\//\\/}[[:space:]]" /etc/fstab &&
    ! grep -Fq "UUID=${data_uuid} ${GA_DATA_DIR} " /etc/fstab; then
    echo "/etc/fstab already contains a different source for ${GA_DATA_DIR}." >&2
    exit 1
  fi
  if ! grep -Fq "UUID=${data_uuid} ${GA_DATA_DIR} " /etc/fstab; then
    printf 'UUID=%s %s ext4 defaults,nofail,discard 0 2\n' \
      "${data_uuid}" "${GA_DATA_DIR}" >> /etc/fstab
  fi
  mount "${GA_DATA_DIR}"
fi

chown root:root "${GA_DATA_DIR}"
chmod 0750 "${GA_DATA_DIR}"
install -o 10001 -g 10001 -m 0750 -d "${GA_DATA_DIR}/app"
install -o root -g root -m 0700 -d "${GA_DATA_DIR}/backups"
install -o root -g root -m 0750 -d \
  "${GA_DATA_DIR}/caddy/data" \
  "${GA_DATA_DIR}/caddy/config"
install -o 1883 -g 1883 -m 0750 -d \
  "${GA_DATA_DIR}/mosquitto/data" \
  "${GA_DATA_DIR}/mosquitto/log"
install -o root -g 1883 -m 0750 -d \
  "${GA_DATA_DIR}/mqtt/certs" \
  "${GA_DATA_DIR}/mqtt/config"
install -o root -g root -m 0700 -d "${GA_DATA_DIR}/secrets"
install -o root -g root -m 0755 -d "${GA_STACK_DIR}"

download_dir="$(mktemp -d)"
trap 'rm -f "${docker_key_tmp:-}"; rm -rf "${download_dir:-}"' EXIT
production_url="${GA_DEPLOYMENT_SOURCE_BASE_URL}/${GA_DEPLOYMENT_SOURCE_REF}/deploy/production"
for production_file in docker-compose.yml Caddyfile mosquitto.conf update.sh .env.example; do
  curl -fsSL --retry 5 --retry-delay 2 \
    "${production_url}/${production_file}" \
    -o "${download_dir}/${production_file}"
done
install -o root -g root -m 0644 \
  "${download_dir}/docker-compose.yml" \
  "${download_dir}/Caddyfile" \
  "${download_dir}/mosquitto.conf" \
  "${download_dir}/.env.example" \
  "${GA_STACK_DIR}/"
install -o root -g root -m 0755 \
  "${download_dir}/update.sh" \
  "${GA_STACK_DIR}/update.sh"

environment_file="${GA_STACK_DIR}/.env"
if [[ ! -e "${environment_file}" ]]; then
  umask 077
  {
    printf 'GA_SERVER_IMAGE=ghcr.io/henrigruber-ai/ga-server:%s\n' "${GA_SERVER_IMAGE_TAG}"
    printf 'GA_DATA_DIR=%s\n' "${GA_DATA_DIR}"
    printf 'GA_PUBLIC_BASE_URL=%s\n' "${GA_PUBLIC_BASE_URL}"
    printf 'GA_MQTT_PUBLIC_HOST=%s\n' "${GA_MQTT_PUBLIC_HOST}"
    printf 'GA_TIMEZONE=Europe/Berlin\n'
    printf 'GA_MQTT_USERNAME=ga-server\n'
    printf 'GA_SEED_EXAMPLE_DEVICES=false\n'
    printf 'ACME_EMAIL=%s\n' "${GA_ACME_EMAIL}"
  } > "${environment_file}"
fi
chown root:root "${environment_file}"
chmod 0600 "${environment_file}"

mqtt_secret_file="${GA_DATA_DIR}/secrets/ga_mqtt_password"
if [[ ! -s "${mqtt_secret_file}" && -n "${GA_MQTT_SECRET_NAME}" ]]; then
  if [[ -z "${GA_PROJECT_ID}" ]]; then
    GA_PROJECT_ID="$(curl -fsS -H 'Metadata-Flavor: Google' \
      http://metadata.google.internal/computeMetadata/v1/project/project-id)"
  fi
  metadata_bearer="$(curl -fsS -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token |
    jq -er '.access_token')"
  secret_tmp="$(mktemp "${GA_DATA_DIR}/secrets/.ga_mqtt_password.XXXXXX")"
  chmod 0600 "${secret_tmp}"
  curl -fsS \
    -H "Authorization: Bearer ${metadata_bearer}" \
    "https://secretmanager.googleapis.com/v1/projects/${GA_PROJECT_ID}/secrets/${GA_MQTT_SECRET_NAME}/versions/latest:access" |
    jq -er '.payload.data' |
    base64 --decode > "${secret_tmp}"
  unset metadata_bearer
  if [[ ! -s "${secret_tmp}" ]]; then
    rm -f "${secret_tmp}"
    echo "Secret Manager returned an empty MQTT password." >&2
    exit 1
  fi
  chown 10001:1883 "${secret_tmp}"
  chmod 0440 "${secret_tmp}"
  mv -n "${secret_tmp}" "${mqtt_secret_file}"
  rm -f "${secret_tmp}"
fi

if [[ ! -s "${mqtt_secret_file}" ]]; then
  echo "Missing ${mqtt_secret_file}; bootstrap leaves existing files untouched." >&2
  exit 1
fi
chown 10001:1883 "${mqtt_secret_file}"
chmod 0440 "${mqtt_secret_file}"

password_file="${GA_DATA_DIR}/mqtt/config/passwords"
if [[ ! -s "${password_file}" ]]; then
  password_tmp_dir="$(mktemp -d "${GA_DATA_DIR}/mqtt/config/.passwords.XXXXXX")"
  docker run --rm -i \
    -v "${password_tmp_dir}:/mosquitto/config" \
    eclipse-mosquitto:2.0.22 \
    sh -c 'IFS= read -r mqtt_value; mosquitto_passwd -b -c /mosquitto/config/passwords ga-server "$mqtt_value"' \
    < "${mqtt_secret_file}"
  install -o root -g 1883 -m 0640 "${password_tmp_dir}/passwords" "${password_file}"
  rm -rf "${password_tmp_dir}"
fi
chown root:1883 "${password_file}"
chmod 0640 "${password_file}"

required_tls_files=(
  "${GA_DATA_DIR}/mqtt/certs/ca.crt"
  "${GA_DATA_DIR}/mqtt/certs/server.crt"
  "${GA_DATA_DIR}/mqtt/certs/server.key"
)
for tls_file in "${required_tls_files[@]}"; do
  if [[ ! -s "${tls_file}" ]]; then
    echo "Missing required MQTT TLS file: ${tls_file}" >&2
    exit 1
  fi
  chown root:1883 "${tls_file}"
done
chmod 0644 \
  "${GA_DATA_DIR}/mqtt/certs/ca.crt" \
  "${GA_DATA_DIR}/mqtt/certs/server.crt"
chmod 0640 "${GA_DATA_DIR}/mqtt/certs/server.key"

cd "${GA_STACK_DIR}"
docker compose config --quiet
if ! docker compose pull; then
  echo "Image pull failed. For private GHCR, log in separately with a read:packages-only token." >&2
  exit 1
fi
docker compose up -d --remove-orphans
docker compose ps

health_url="${GA_PUBLIC_BASE_URL}/health/ready"
for _ in {1..30}; do
  if curl -fsS --max-time 5 "${health_url}" >/dev/null; then
    touch /var/lib/ga-server-bootstrap-complete
    echo "GA-Server is ready at ${health_url}."
    exit 0
  fi
  sleep 10
done

docker compose logs --tail 100 ga-server mosquitto caddy >&2
echo "GA-Server did not become ready at ${health_url}." >&2
exit 1
