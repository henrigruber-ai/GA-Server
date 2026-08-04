"""
File: app/api/schemas.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Defines validated input contracts for authentication and administration.
Changes:
- 0.1.0: Initial implementation.
"""

from pydantic import BaseModel, Field, field_validator


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class DeviceInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    technical_device_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    mqtt_topic_prefix: str = Field(min_length=1, max_length=255)
    mqtt_client_id: str = Field(min_length=1, max_length=120)
    mqtt_username: str | None = Field(default=None, max_length=120)
    mqtt_password: str | None = Field(default=None, min_length=12, max_length=255)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("mqtt_topic_prefix")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if "+" in value or "#" in value or not value.startswith("ga/devices/"):
            raise ValueError(
                "Topic-Präfix muss mit ga/devices/ beginnen und darf keine Wildcards enthalten."
            )
        return value.rstrip("/")


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    technical_device_id: str | None = Field(
        default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$"
    )
    mqtt_topic_prefix: str | None = Field(default=None, min_length=1, max_length=255)
    mqtt_client_id: str | None = Field(default=None, min_length=1, max_length=120)
    mqtt_username: str | None = Field(default=None, max_length=120)
    mqtt_password: str | None = Field(default=None, min_length=12, max_length=255)
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class DeleteDeviceInput(BaseModel):
    delete_history: bool = False
    confirmation: str = Field(min_length=1, max_length=120)


class UserInput(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=512)
    enabled: bool = True


class UserUpdate(BaseModel):
    enabled: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=512)
