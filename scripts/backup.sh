#!/usr/bin/env sh
# File: scripts/backup.sh
# Version: 0.1.0
# Date: 2026-08-03
# Purpose: Creates and retains consistent SQLite backups on Linux hosts.

set -eu

destination="${1:-./backups}"
retention_days="${RETENTION_DAYS:-14}"
timestamp="$(date -u +%Y%m%d-%H%M%S)"
target="${destination}/ga-server-${timestamp}.db"

mkdir -p "${destination}"
docker compose exec -T ga-server python -c \
  "import sqlite3; source=sqlite3.connect('/data/ga-server.db'); target=sqlite3.connect('/tmp/backup.db'); source.backup(target); target.close(); source.close()"
docker compose cp ga-server:/tmp/backup.db "${target}"
find "${destination}" -type f -name 'ga-server-*.db' -mtime "+${retention_days}" -delete
printf 'Backup erstellt: %s\n' "${target}"
