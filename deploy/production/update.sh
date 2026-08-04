#!/usr/bin/env sh
# File: deploy/production/update.sh
# Version: 0.2.0
# Date: 2026-08-04
# Purpose: Pulls and restarts the production stack without touching persistent data.

set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

echo "GA-Server: pulling configured images..."
docker compose config --quiet
docker compose pull

echo "GA-Server: applying the updated stack..."
docker compose up -d --remove-orphans

echo "GA-Server: removing only unused image layers..."
docker image prune -f

echo "GA-Server: current service status:"
docker compose ps
