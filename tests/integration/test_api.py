"""
File: tests/integration/test_api.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Exercises public access, auth, CSRF, device lifecycle, history, and WebSockets.
Changes:
- 0.1.0: Initial implementation.
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


def test_public_page_health_and_protected_access(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert "historyCanvas" in client.get("/").text
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/health/ready").status_code == 200
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
    assert created.json()["generated_mqtt_password"]
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
    history = client.get("/api/public/history?metric=power&phase=total").json()
    assert history["series"][0]["device_id"] == created["id"]
    assert history["series"][0]["points"][0][1] == 600
    historical = client.get(
        "/api/public/history?metric=power&phase=total"
        "&from=2026-08-03T18:00:00%2B00:00&to=2026-08-03T19:00:00%2B00:00"
    ).json()
    assert historical["series"][0]["points"][0][1] == 600
    with runtime.database.sessions() as session:
        assert session.query(Device).filter_by(id=created["id"]).one().last_seen_at is not None


def test_websocket_connection_receives_snapshot(client: TestClient) -> None:
    with client.websocket_connect("/api/public/live-stream") as websocket:
        message = websocket.receive_json()
        assert message == {"type": "snapshot", "data": []}
