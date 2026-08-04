"""
File: app/db/seed.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Creates optional example devices without creating any user credentials.
Changes:
- 0.1.0: Initial implementation.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Device

EXAMPLE_DEVICES = (
    ("Römerbad", "roemerbad", "#21d4a7"),
    ("Bühne", "buehne", "#36a3ff"),
    ("Küche", "kueche", "#ffb02e"),
    ("Sektbar", "sektbar", "#ff5c8a"),
)


def seed_example_devices(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(Device)):
        return
    for order, (name, technical_id, color) in enumerate(EXAMPLE_DEVICES):
        session.add(
            Device(
                name=name,
                technical_device_id=technical_id,
                mqtt_topic_prefix=f"ga/devices/{technical_id}",
                mqtt_client_id=f"shelly-{technical_id}",
                sort_order=order,
                color=color,
            )
        )
    session.commit()
