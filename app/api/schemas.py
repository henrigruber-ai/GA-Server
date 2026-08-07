"""
File: app/api/schemas.py
Version: 0.3.1
Date: 2026-08-07
Purpose: Defines strict validated input contracts for authentication, devices, and control.
Changes:
- 0.3.1: Accepts write-only device MQTT passwords; empty update values preserve the stored secret.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(StrictInput):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class DeviceInput(StrictInput):
    name: str = Field(min_length=1, max_length=120)
    technical_device_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    mqtt_topic_prefix: str = Field(min_length=1, max_length=255)
    mqtt_client_id: str = Field(min_length=1, max_length=120)
    mqtt_username: str | None = Field(default=None, max_length=120)
    mqtt_password: str | None = Field(default=None, max_length=512)
    device_type: Literal["shelly_pro_3em", "tasmota_plug"] = "shelly_pro_3em"
    controllable: bool = False
    relay_index: int = Field(default=1, ge=1, le=1)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("mqtt_password", mode="before")
    @classmethod
    def empty_mqtt_password_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_device_type(self) -> "DeviceInput":
        topic = self.mqtt_topic_prefix.strip().rstrip("/")
        if "+" in topic or "#" in topic:
            raise ValueError("Das MQTT-Gerätetopic darf keine Wildcards enthalten.")
        if self.device_type == "shelly_pro_3em":
            if not topic.startswith("ga/devices/"):
                raise ValueError("Shelly-Topics müssen mit ga/devices/ beginnen.")
            if self.controllable:
                raise ValueError("Shelly Pro 3EM wird nicht als schaltbares Gerät unterstützt.")
        else:
            if topic.startswith(("cmnd/", "stat/", "tele/")) or "/" in topic:
                raise ValueError(
                    "Für Tasmota nur das nackte Gerätetopic ohne cmnd/, stat/ oder tele/ speichern."
                )
            if not topic or any(character.isspace() for character in topic):
                raise ValueError("Das Tasmota-Gerätetopic ist ungültig.")
        self.mqtt_topic_prefix = topic
        return self


class DeviceUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    technical_device_id: str | None = Field(
        default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$"
    )
    mqtt_topic_prefix: str | None = Field(default=None, min_length=1, max_length=255)
    mqtt_client_id: str | None = Field(default=None, min_length=1, max_length=120)
    mqtt_username: str | None = Field(default=None, max_length=120)
    mqtt_password: str | None = Field(default=None, max_length=512)
    device_type: Literal["shelly_pro_3em", "tasmota_plug"] | None = None
    controllable: bool | None = None
    relay_index: int | None = Field(default=None, ge=1, le=1)
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("mqtt_password", mode="before")
    @classmethod
    def empty_mqtt_password_keeps_existing(cls, value: object) -> object:
        return None if value == "" else value


class PowerInput(StrictInput):
    state: Literal["on", "off"]


class DeleteDeviceInput(StrictInput):
    delete_history: bool = False
    confirmation: str = Field(min_length=1, max_length=120)


class UserInput(StrictInput):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=512)
    enabled: bool = True


class UserUpdate(StrictInput):
    enabled: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=512)
