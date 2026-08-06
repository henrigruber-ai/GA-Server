"""
File: tests/unit/test_tasmota_parser.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Verifies defensive Tasmota topic, telemetry, LWT, POWER, and fingerprint parsing.
"""

import json
from datetime import UTC, datetime, timedelta

from app.services.tasmota_parser import (
    classify_topic,
    parse_lwt,
    parse_measurement,
    parse_power,
)


def test_sensor_maps_current_voltage_and_power() -> None:
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    parsed = parse_measurement(
        "tele/id139_bauwagen/SENSOR",
        json.dumps(
            {
                "Time": now.isoformat(),
                "ENERGY": {"Current": 1.25, "Voltage": 231.2, "Power": 288},
            }
        ),
        now,
    )
    assert parsed.valid
    assert parsed.technical_device_id == "id139_bauwagen"
    assert parsed.values is not None
    assert parsed.values["current_l1"] == parsed.values["current_total"] == 1.25
    assert parsed.values["voltage_l1"] == 231.2
    assert parsed.values["power_l1"] == parsed.values["power_total"] == 288
    assert parsed.values["current_l2"] is None


def test_status10_uses_nested_statussns_energy() -> None:
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    parsed = parse_measurement(
        "stat/id139_bauwagen/STATUS10",
        '{"StatusSNS":{"ENERGY":{"Current":0.5,"Voltage":230,"Power":115}}}',
        now,
    )
    assert parsed.valid
    assert parsed.values is not None
    assert parsed.values["current_total"] == 0.5


def test_lwt_and_power_states() -> None:
    assert parse_lwt("tele/plug/LWT", b"Online") == ("plug", True)
    assert parse_lwt("tele/plug/LWT", b"Offline") == ("plug", False)
    assert parse_power("stat/plug/POWER", "ON").state is True
    assert parse_power("stat/plug/POWER", "OFF").state is False
    assert parse_power("stat/plug/RESULT", '{"POWER":"ON"}').state is True


def test_invalid_json_boolean_nonfinite_foreign_and_empty_are_rejected() -> None:
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    assert parse_measurement("tele/plug/SENSOR", "{", now).error == "invalid_json"
    assert (
        parse_measurement(
            "tele/plug/SENSOR",
            '{"ENERGY":{"Current":true,"Voltage":"NaN","Power":"Infinity"}}',
            now,
        ).error
        == "no_valid_values"
    )
    assert parse_measurement("tele/plug/STATE", "{}", now).error == "invalid_topic"
    assert (
        parse_measurement("tele/plug/SENSOR", '{"ENERGY":{"Today":1}}', now).error
        == "no_valid_values"
    )
    assert classify_topic("stat/plug/SENSOR") is None


def test_implausible_time_uses_receive_time_and_fingerprint_is_canonical() -> None:
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    first = parse_measurement(
        "tele/plug/SENSOR",
        '{"Time":"2000-01-01T00:00:00Z","ENERGY":{"Power":10,"Current":1}}',
        now,
    )
    second = parse_measurement(
        "tele/plug/SENSOR",
        '{"ENERGY":{"Current":1,"Power":10},"Time":"2000-01-01T00:00:00Z"}',
        now + timedelta(seconds=1),
    )
    assert first.measured_at == now
    assert second.measured_at == now + timedelta(seconds=1)
    assert first.fingerprint == second.fingerprint
