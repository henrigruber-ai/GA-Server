# File: scripts/backup.ps1
# Version: 0.1.0
# Date: 2026-08-03
# Purpose: Creates a consistent SQLite backup from the running GA-Server volume.

param(
    [string]$Destination = ".\backups",
    [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"
$resolvedDestination = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $resolvedDestination | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $resolvedDestination "ga-server-$stamp.db"

docker compose exec -T ga-server python -c "import sqlite3; source=sqlite3.connect('/data/ga-server.db'); target=sqlite3.connect('/tmp/backup.db'); source.backup(target); target.close(); source.close()"
docker compose cp "ga-server:/tmp/backup.db" $target

Get-ChildItem -LiteralPath $resolvedDestination -Filter "ga-server-*.db" -File |
    Where-Object LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) |
    Remove-Item -Force

Write-Host "Backup erstellt: $target"
