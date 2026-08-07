"""
File: tests/integration/test_api.py
Version: 0.3.2
Date: 2026-08-07
Purpose: Exercises public access, auth, CSRF, device lifecycle, history, and WebSockets.
Changes:
- 0.1.0: Initial implementation.
- 0.1.1: Verifies readiness when MQTT is intentionally disabled.
- 0.2.0: Verifies bundled multi-unit history and raw live-series metadata.
- 0.3.1: Verifies write-only MQTT password storage and blank-edit preservation.
- 0.3.2: Verifies Tasmota creation and validation errors during device-type edits.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db.models import Device

pytestmark = pytest.mark.integration


def device_payload(name: str = "Werkstatt") -> dict[str, object]:
    return {
        "name": name,
        "technical_device_id": "werkstatt",
        "mqtt_topic_prefix": "ga/devices/werkstatt",
        "mqtt_client_id": "shelly-werkstatt",
        "mqtt_username": "werkstatt",
        "enabled": True,
        "sort_order": 5,
        "color": "#123abc",
    }


def tasmota_payload(name: str = "Löwenweg") -> dict[str, object]:
    return {
        "name": name,
        "technical_device_id": "id139_loewenweg",
        "mqtt_topic_prefix": "id139",
        "mqtt_client_id": "smartplug_id139",
        "mqtt_username": "user1",
        "device_type": "tasmota_plug",
        "controllable": True,
        "relay_index": 1,
        "enabled": True,
        "sort_order": 0,
        "color": "#ffff00",
    }


def test_public_page_health_and_protected_access(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "historyCanvas" in page.text
    assert 'name="mqtt_password"' in page.text
    assert client.get("/health/live").json() == {"status": "alive"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["mqtt_connected"] is True
    assert client.get("/api/public/devices").status_code == 200
    assert client.get("/api/admin/devices").status_code == 401


def test_login_logout_and_csrf(client: TestClient) -> None:
    failed = client.post("/api/auth/login", json={"username": "operator", "password": "wrong"})
    assert failed.status_code == 401
    response = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    assert client.post("/api/admin/devices", json=device_payload()).status_code == 403
    assert (
        client.post(
            "/api/admin/devices",
            json=device_payload(),
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 201
    )
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/admin/devices").status_code == 401


def test_device_create_rename_disable_and_identity_stability(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    created = client.post(
        "/api/admin/devices",
        json=device_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201
    device_id = created.json()["id"]
    assert "generated_mqtt_password" not in created.json()
    assert "mqtt_password" not in created.json()
    renamed = client.patch(
        f"/api/admin/devices/{device_id}",
        json={"name": "Neue Werkstatt"},
        headers={"X-CSRF-Token": csrf},
    )
    assert renamed.status_code == 200
    assert renamed.json()["id"] == device_id
    assert renamed.json()["name"] == "Neue Werkstatt"
    disabled = client.patch(
        f"/api/admin/devices/{device_id}",
        json={"enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert disabled.json()["enabled"] is False
    assert client.get("/api/public/devices").json() == []


def test_tasmota_create_and_invalid_type_edit_returns_422(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    created_tasmota = client.post(
        "/api/admin/devices",
        json=tasmota_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    assert created_tasmota.status_code == 201
    assert created_tasmota.json()["device_type"] == "tasmota_plug"
    assert created_tasmota.json()["mqtt_topic_prefix"] == "id139"

    created_shelly = client.post(
        "/api/admin/devices",
        json=device_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    assert created_shelly.status_code == 201
    device_id = created_shelly.json()["id"]

    invalid = client.patch(
        f"/api/admin/devices/{device_id}",
        json={
            "device_type": "tasmota_plug",
            "mqtt_topic_prefix": "ga/devices/id140",
            "controllable": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == (
        "Für Tasmota nur das nackte Gerätetopic ohne cmnd/, stat/ oder tele/ speichern."
    )

    valid = client.patch(
        f"/api/admin/devices/{device_id}",
        json={
            "device_type": "tasmota_plug",
            "mqtt_topic_prefix": "id140",
            "controllable": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert valid.status_code == 200
    assert valid.json()["device_type"] == "tasmota_plug"
    assert valid.json()["mqtt_topic_prefix"] == "id140"


def test_device_mqtt_password_is_write_only_and_blank_update_keeps_hash(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    initial_credential = "mqtt-device-secret"
    created = client.post(
        "/api/admin/devices",
        json=device_payload() | {"mqtt_password": initial_credential},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["mqtt_password_configured"] is True
    assert "mqtt_password" not in body
    assert "mqtt_password_hash" not in body

    runtime = client.app.state.runtime
    with runtime.database.sessions() as session:
        stored = session.get(Device, body["id"])
        assert stored is not None
        original_hash = stored.mqtt_password_hash
    assert original_hash
    assert original_hash != initial_credential
    assert original_hash.startswith("$argon2")

    unchanged = client.patch(
        f"/api/admin/devices/{body['id']}",
        json={"mqtt_password": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["mqtt_password_configured"] is True
    with runtime.database.sessions() as session:
        stored = session.get(Device, body["id"])
        assert stored is not None
        assert stored.mqtt_password_hash == original_hash

    replaced = client.patch(
        f"/api/admin/devices/{body['id']}",
        json={"mqtt_password": "replacement-secret"},
        headers={"X-CSRF-Token": csrf},
    )
    assert replaced.status_code == 200
    assert "mqtt_password" not in replaced.json()
    with runtime.database.sessions() as session:
        stored = session.get(Device, body["id"])
        assert stored is not None
        assert stored.mqtt_password_hash
        assert stored.mqtt_password_hash != original_hash
        assert stored.mqtt_password_hash != "replacement-secret"


def test_simulated_mqtt_creates_live_and_one_minute_row(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    created = client.post(
        "/api/admin/devices",
        json=device_payload(),
        headers={"X-CSRF-Token": csrf},
    ).json()
    runtime = client.app.state.runtime
    received = datetime(2026, 8, 3, 18, 5, 10, tzinfo=UTC)
    payload = (
        '{"a_current":1,"b_current":2,"c_current":3,'
        '"a_voltage":230,"b_voltage":231,"c_voltage":232,'
        '"a_act_power":100,"b_act_power":200,"c_act_power":300,"total_act_power":600}'
    )
    assert runtime.mqtt.handle_message("ga/devices/werkstatt/status/em:0", payload, received)
    assert not runtime.mqtt.handle_message("ga/devices/werkstatt/status/em:0", payload, received)
    assert client.get("/api/public/live").json()["measurements"][0]["values"]["power_total"] == 600
    runtime.aggregator.flush_due(force=True)
    historical = client.get(
        "/api/public/history?metric=power&phase=total"
        "&from=2026-08-03T18:00:00%2B00:00&to=2026-08-03T19:00:00%2B00:00"
    ).json()
    assert historical["series"][0]["points"][0][1] == 600
    bundled = client.get(
        "/api/public/history-batch?series=current:l1,voltage:l2,power:total"
        "&from=2026-08-03T18:00:00%2B00:00&to=2026-08-03T19:00:00%2B00:00"
    ).json()
    assert bundled["aggregated"] is True
    assert bundled["interval"] == "minute"
    assert {
        (item["metric"], item["phase"], item["points"][0][1]) for item in bundled["series"]
    } == {
        ("current", "l1", 1),
        ("voltage", "l2", 231),
        ("power", "total", 600),
    }
    public_device = client.get("/api/public/devices").json()[0]
    assert "voltage:total" not in public_device["available_series"]
    assert public_device["stale_seconds"] < public_device["offline_seconds"]
    with runtime.database.sessions() as session:
        assert session.query(Device).filter_by(id=created["id"]).one().last_seen_at is not None


def test_history_batch_ignores_invalid_and_duplicate_series(client: TestClient) -> None:
    response = client.get(
        "/api/public/history-batch?series=voltage:total,current:l1,current:l1,unknown:l2"
    )
    assert response.status_code == 200
    assert response.json()["series"] == []
    assert "error" not in response.json()

    invalid = client.get("/api/public/history-batch?series=voltage:total")
    assert invalid.json() == {"series": [], "error": "no_valid_series"}


def test_websocket_connection_receives_snapshot(client: TestClient) -> None:
    with client.websocket_connect("/api/public/live-stream") as websocket:
        message = websocket.receive_json()
        assert message == {"type": "snapshot", "data": []}
