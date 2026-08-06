"""
File: app/db/models.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Defines the persisted users, sessions, devices, measurements, stats, and audit data.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.time import utc_now


def uuid_string() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    user: Mapped[User] = relationship()


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_type_enabled", "device_type", "enabled"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    name: Mapped[str] = mapped_column(String(120))
    technical_device_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    mqtt_topic_prefix: Mapped[str] = mapped_column(String(255), unique=True)
    mqtt_client_id: Mapped[str] = mapped_column(String(120), unique=True)
    mqtt_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mqtt_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_type: Mapped[str] = mapped_column(String(32), default="shelly_pro_3em")
    controllable: Mapped[bool] = mapped_column(Boolean, default=False)
    relay_index: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    color: Mapped[str] = mapped_column(String(7), default="#36c5f0")
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    measurements: Mapped[list[MinuteMeasurement]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class MinuteMeasurement(Base):
    __tablename__ = "minute_measurements"
    __table_args__ = (
        UniqueConstraint("device_id", "bucket_start", name="uq_measurement_device_bucket"),
        Index("ix_measurement_bucket_device", "bucket_start", "device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sample_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    current_l1_avg: Mapped[float | None] = mapped_column(Float)
    current_l1_min: Mapped[float | None] = mapped_column(Float)
    current_l1_max: Mapped[float | None] = mapped_column(Float)
    current_l2_avg: Mapped[float | None] = mapped_column(Float)
    current_l2_min: Mapped[float | None] = mapped_column(Float)
    current_l2_max: Mapped[float | None] = mapped_column(Float)
    current_l3_avg: Mapped[float | None] = mapped_column(Float)
    current_l3_min: Mapped[float | None] = mapped_column(Float)
    current_l3_max: Mapped[float | None] = mapped_column(Float)
    current_total_avg: Mapped[float | None] = mapped_column(Float)
    current_total_min: Mapped[float | None] = mapped_column(Float)
    current_total_max: Mapped[float | None] = mapped_column(Float)

    voltage_l1_avg: Mapped[float | None] = mapped_column(Float)
    voltage_l1_min: Mapped[float | None] = mapped_column(Float)
    voltage_l1_max: Mapped[float | None] = mapped_column(Float)
    voltage_l2_avg: Mapped[float | None] = mapped_column(Float)
    voltage_l2_min: Mapped[float | None] = mapped_column(Float)
    voltage_l2_max: Mapped[float | None] = mapped_column(Float)
    voltage_l3_avg: Mapped[float | None] = mapped_column(Float)
    voltage_l3_min: Mapped[float | None] = mapped_column(Float)
    voltage_l3_max: Mapped[float | None] = mapped_column(Float)

    power_l1_avg: Mapped[float | None] = mapped_column(Float)
    power_l1_min: Mapped[float | None] = mapped_column(Float)
    power_l1_max: Mapped[float | None] = mapped_column(Float)
    power_l2_avg: Mapped[float | None] = mapped_column(Float)
    power_l2_min: Mapped[float | None] = mapped_column(Float)
    power_l2_max: Mapped[float | None] = mapped_column(Float)
    power_l3_avg: Mapped[float | None] = mapped_column(Float)
    power_l3_min: Mapped[float | None] = mapped_column(Float)
    power_l3_max: Mapped[float | None] = mapped_column(Float)
    power_total_avg: Mapped[float | None] = mapped_column(Float)
    power_total_min: Mapped[float | None] = mapped_column(Float)
    power_total_max: Mapped[float | None] = mapped_column(Float)

    device: Mapped[Device] = relationship(back_populates="measurements")


class DeviceWindowStat(Base):
    __tablename__ = "device_window_stats"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "window_type", "metric", "phase", name="uq_device_window_metric_phase"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    window_type: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(16))
    phase: Mapped[str] = mapped_column(String(8))
    minimum: Mapped[float | None] = mapped_column(Float)
    minimum_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maximum: Mapped[float | None] = mapped_column(Float)
    maximum_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(120))
    details: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="info")
