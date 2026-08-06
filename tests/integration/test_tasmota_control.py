"""
File: tests/integration/test_tasmota_control.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Exercises protected Tasmota control, confirmation, timeout, and MQTT safety.
"""

import time
from types import SimpleNamespace
from unittest.mock import Mock

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.db.models import AuditLog

pytestmark = pytest.mark.integration


def tasmota_payload(
    *,
    controllable: bool = True,
    topic: str = "id139_bauwagen",
) -> dict[str, object]:
    return {
        "name": "Bauwagen",
        "technical_device_id": "id139_bauwagen",
        "device_type": "tasmota_plug",
        "mqtt_topic_prefix": topic,
        "mqtt_client_id": "DVES_5ED4C8",
        "mqtt_username": "bauwagen",
        "controllable": controllable,
        "relay_index": 1,
        "enabled": True,
        "sort_order": 10,
        "color": "#21d4a7",
    }


def create_plug(client: TestClient, csrf: str, *, controllable: bool = True) -> dict[str, object]:
    response = client.post(
        "/api/admin/devices",
        json=tasmota_payload(controllable=controllable),
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.json()


def make_online_with_state(client: TestClient, state: str = "OFF") -> None:
    runtime = client.app.state.runtime
    assert runtime.mqtt.handle_message("tele/id139_bauwagen/LWT", "Online")
    assert runtime.mqtt.handle_message("stat/id139_bauwagen/POWER", state)


def test_power_is_pending_until_matching_confirmation(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    device = create_plug(client, csrf)
    make_online_with_state(client)
    runtime = client.app.state.runtime
    runtime.mqtt.connected = True
    runtime.mqtt.publish_power = Mock(return_value=True)

    accepted = client.post(
        f"/api/admin/control/devices/{device['id']}/power",
        json={"state": "on"},
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 202
    assert accepted.json()["control"]["pending"] is True
    assert accepted.json()["control"]["confirmed_state"] is False
    assert runtime.mqtt.publish_power.call_count == 1

    pending = client.get("/api/admin/control/devices").json()["devices"][0]["control"]
    assert pending["pending"] is True
    assert pending["confirmed_state"] is False
    assert runtime.mqtt.handle_message("stat/id139_bauwagen/POWER", "ON")
    confirmed = client.get("/api/admin/control/devices").json()["devices"][0]["control"]
    assert confirmed["pending"] is False
    assert confirmed["confirmed_state"] is True
    with runtime.database.sessions() as session:
        actions = set(session.scalars(select(AuditLog.action)))
    assert {"device.power.requested", "device.power.confirmed"} <= actions


def test_control_rejections_and_input_security(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    device = create_plug(client, csrf, controllable=False)
    path = f"/api/admin/control/devices/{device['id']}/power"
    assert client.post(path, json={"state": "on"}).status_code == 403
    assert (
        client.post(path, json={"state": "toggle"}, headers={"X-CSRF-Token": csrf}).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={"state": "on", "topic": "cmnd/other/POWER"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 422
    )
    assert (
        client.post(path, json={"state": "on"}, headers={"X-CSRF-Token": csrf}).json()["detail"][
            "code"
        ]
        == "device_not_controllable"
    )
    missing = client.post(
        "/api/admin/control/devices/not-a-device/power",
        json={"state": "on"},
        headers={"X-CSRF-Token": csrf},
    )
    assert missing.status_code == 404
    response_text = client.get("/api/admin/control/devices").text.lower()
    assert "password" not in response_text
    assert "secret" not in response_text


def test_offline_mqtt_pending_conflict_and_timeout(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    device = create_plug(client, csrf)
    path = f"/api/admin/control/devices/{device['id']}/power"
    offline = client.post(path, json={"state": "on"}, headers={"X-CSRF-Token": csrf})
    assert offline.json()["detail"]["code"] == "device_offline"

    make_online_with_state(client)
    runtime = client.app.state.runtime
    runtime.mqtt.connected = False
    disconnected = client.post(path, json={"state": "on"}, headers={"X-CSRF-Token": csrf})
    assert disconnected.json()["detail"]["code"] == "mqtt_not_connected"

    runtime.mqtt.connected = True
    runtime.mqtt.publish_power = Mock(return_value=True)
    accepted = client.post(path, json={"state": "on"}, headers={"X-CSRF-Token": csrf})
    assert accepted.status_code == 202
    second = client.post(path, json={"state": "on"}, headers={"X-CSRF-Token": csrf})
    assert second.json()["detail"]["code"] == "command_pending"
    assert runtime.mqtt.handle_message("stat/id139_bauwagen/POWER", "OFF")
    control = client.get("/api/admin/control/devices").json()["devices"][0]["control"]
    assert control["last_error"] == "confirmation_conflict"
    assert control["confirmed_state"] is False

    runtime.control.timeout_seconds = 0.05
    accepted = client.post(path, json={"state": "on"}, headers={"X-CSRF-Token": csrf})
    assert accepted.status_code == 202
    time.sleep(0.12)
    timed_out = client.get("/api/admin/control/devices").json()["devices"][0]["control"]
    assert timed_out["pending"] is False
    assert timed_out["confirmed_state"] is False
    assert timed_out["last_error"] == "confirmation_timeout"


def test_power_state_query_after_reconnect(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    create_plug(client, csrf)
    runtime = client.app.state.runtime
    published: list[tuple[str, str, int, bool]] = []

    class FakeClient:
        def publish(self, topic: str, payload: str, qos: int, retain: bool) -> object:
            published.append((topic, payload, qos, retain))
            return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

        def disconnect(self) -> None:
            return None

        def loop_stop(self) -> None:
            return None

    runtime.mqtt.client = FakeClient()
    runtime.mqtt.connected = True
    assert runtime.mqtt.request_tasmota_power_states() == 1
    assert published == [("cmnd/id139_bauwagen/POWER", "", 1, False)]


def test_control_websocket_is_authenticated_and_separate(
    authenticated: tuple[TestClient, str],
) -> None:
    client, csrf = authenticated
    create_plug(client, csrf)
    runtime = client.app.state.runtime
    assert runtime.websockets is not runtime.control_websockets
    with client.websocket_connect("/api/admin/control-stream") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "snapshot"
        assert message["data"]["devices"][0]["name"] == "Bauwagen"


def test_control_requires_session(client: TestClient) -> None:
    assert client.get("/api/admin/control/devices").status_code == 401
    with (
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect("/api/admin/control-stream"),
    ):
        pass
    assert error.value.code == 4401
