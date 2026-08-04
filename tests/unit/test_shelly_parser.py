"""
File: tests/unit/test_shelly_parser.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Verifies defensive Shelly topic, JSON, numeric, phase, and total parsing.
Changes:
- 0.1.0: Initial implementation.
"""

import json
from datetime import UTC, datetime

from app.services.shelly_parser import parse_online, parse_status, topic_device_id


def test_parses_all_shelly_fields() -> None:
    now = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    payload = {
        "a_current": 1.1,
        "b_current": 2.2,
        "c_current": 3.3,
        "total_current": 6.6,
        "a_voltage": 229.1,
        "b_voltage": 230.2,
        "c_voltage": 231.3,
        "a_act_power": 100,
        "b_act_power": 200,
        "c_act_power": 300,
        "total_act_power": 600,
        "unknown_future_field": "ignored",
    }
    result = parse_status("ga/devices/kueche/status/em:0", json.dumps(payload), now)
    assert result.valid
    assert result.technical_device_id == "kueche"
    assert result.values == {
        "current_l1": 1.1,
        "current_l2": 2.2,
        "current_l3": 3.3,
        "current_total": 6.6,
        "voltage_l1": 229.1,
        "voltage_l2": 230.2,
        "voltage_l3": 231.3,
        "power_l1": 100.0,
        "power_l2": 200.0,
        "power_l3": 300.0,
        "power_total": 600.0,
    }


def test_missing_totals_are_calculated_from_complete_phases() -> None:
    now = datetime.now(UTC)
    result = parse_status(
        "ga/devices/stage/status/em:0",
        json.dumps(
            {
                "a_current": 1,
                "b_current": 2,
                "c_current": 3,
                "a_act_power": 10,
                "b_act_power": 20,
                "c_act_power": 30,
            }
        ),
        now,
    )
    assert result.values is not None
    assert result.values["current_total"] == 6
    assert result.values["power_total"] == 60
    assert result.values["voltage_l1"] is None


def test_invalid_json_topic_numbers_and_null_are_ignored() -> None:
    now = datetime.now(UTC)
    assert parse_status("wrong/topic", "{}", now).error == "invalid_topic"
    assert parse_status("ga/devices/a/status/em:0", "{", now).error == "invalid_json"
    result = parse_status(
        "ga/devices/a/status/em:0",
        '{"a_current":"NaN","b_current":null,"c_current":"invalid","a_voltage":230}',
        now,
    )
    assert result.valid
    assert result.values is not None
    assert result.values["current_l1"] is None
    assert result.values["current_l2"] is None
    assert result.values["current_l3"] is None
    assert result.values["voltage_l1"] == 230


def test_device_time_outside_tolerance_uses_server_time() -> None:
    now = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    result = parse_status(
        "ga/devices/a/status/em:0",
        '{"a_voltage":230,"ts":0}',
        now,
    )
    assert result.measured_at == now


def test_topic_and_online_mapping() -> None:
    assert topic_device_id("ga/devices/roemerbad/status/em:0") == "roemerbad"
    assert topic_device_id("ga/devices/roemerbad/status/em:1") is None
    assert parse_online("ga/devices/roemerbad/online", b"true") == ("roemerbad", True)
    assert parse_online("ga/devices/roemerbad/online", b"maybe") == ("roemerbad", None)
