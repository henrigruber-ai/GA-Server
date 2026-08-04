"""
File: app/config.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Loads typed application settings from environment variables.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _secret_from_file(name: str) -> str | None:
    direct = os.getenv(name)
    if direct:
        return direct
    file_name = os.getenv(f"{name}_FILE")
    if file_name and Path(file_name).is_file():
        return Path(file_name).read_text(encoding="utf-8").strip()
    return None


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = os.getenv("GA_ENV", "development")
    database_url: str = os.getenv("GA_DATABASE_URL", "sqlite:///./data/ga-server.db")
    public_base_url: str = os.getenv("GA_PUBLIC_BASE_URL", "https://strom.gruber-automation.de")
    timezone: str = os.getenv("GA_TIMEZONE", "Europe/Berlin")
    cookie_secure: bool = _bool("GA_COOKIE_SECURE", False)
    session_hours: int = int(os.getenv("GA_SESSION_HOURS", "12"))
    mqtt_enabled: bool = _bool("GA_MQTT_ENABLED", True)
    mqtt_host: str = os.getenv("GA_MQTT_HOST", "localhost")
    mqtt_port: int = int(os.getenv("GA_MQTT_PORT", "1883"))
    mqtt_tls: bool = _bool("GA_MQTT_TLS", False)
    mqtt_username: str | None = os.getenv("GA_MQTT_USERNAME") or None
    mqtt_password: str | None = _secret_from_file("GA_MQTT_PASSWORD")
    mqtt_ca_file: str | None = os.getenv("GA_MQTT_CA_FILE") or None
    mqtt_client_id: str = os.getenv("GA_MQTT_CLIENT_ID", "ga-server")
    mqtt_public_host: str = os.getenv("GA_MQTT_PUBLIC_HOST", "mqtt.strom.gruber-automation.de")
    mqtt_public_port: int = int(os.getenv("GA_MQTT_PUBLIC_PORT", "8883"))
    db_max_mb: int = int(os.getenv("GA_DB_MAX_MB", "500"))
    cleanup_start_percent: int = int(os.getenv("GA_DB_CLEANUP_START_PERCENT", "85"))
    cleanup_target_percent: int = int(os.getenv("GA_DB_CLEANUP_TARGET_PERCENT", "70"))
    min_history_days: int = int(os.getenv("GA_MIN_HISTORY_DAYS", "8"))
    min_free_disk_mb: int = int(os.getenv("GA_MIN_FREE_DISK_MB", "512"))
    stale_seconds: int = int(os.getenv("GA_STALE_SECONDS", "60"))
    offline_seconds: int = int(os.getenv("GA_OFFLINE_SECONDS", "300"))
    live_buffer_minutes: int = int(os.getenv("GA_LIVE_BUFFER_MINUTES", "15"))
    live_buffer_max_samples: int = int(os.getenv("GA_LIVE_BUFFER_MAX_SAMPLES", "3600"))
    seed_example_devices: bool = _bool("GA_SEED_EXAMPLE_DEVICES", True)
    log_level: str = os.getenv("GA_LOG_LEVEL", "INFO")

    @property
    def database_path(self) -> Path | None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        value = self.database_url.removeprefix(prefix)
        return Path(value).resolve()


settings = Settings()
