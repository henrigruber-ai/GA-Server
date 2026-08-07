"""
File: tests/e2e/test_responsive.py
Version: 0.3.1
Date: 2026-08-07
Purpose: Verifies legend, zoom, repeated refresh, and protected plug control behavior.
Changes:
- 0.1.0: Initial implementation.
- 0.2.0: Covers hierarchical selection, persistence, axis clearance, and mouse zoom.
- 0.3.0: Adds GA-button, Tasmota control, mobile overflow, timeout, and refresh regression tests.
- 0.3.1: Disambiguates the login password field from the device MQTT password field.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from app.auth.security import hash_password
from app.config import Settings
from app.db.models import Device, MinuteMeasurement, User
from app.main import create_app

pytestmark = pytest.mark.e2e
VIEWPORTS = [
    (320, 568),
    (390, 844),
    (844, 390),
    (768, 1024),
    (1366, 768),
    (1920, 1080),
    (2560, 1440),
]
E2E_APP: Any = None


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context()
    instance = context.new_page()
    yield instance
    context.close()


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    global E2E_APP
    path = (tmp_path_factory.mktemp("e2e") / "e2e.db").as_posix()
    application = create_app(
        Settings(
            database_url=f"sqlite:///{path}",
            mqtt_enabled=False,
            seed_example_devices=True,
        )
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.02)
    runtime = application.state.runtime
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with runtime.database.sessions.begin() as session:
        first_device = session.query(Device).order_by(Device.sort_order).first()
        assert first_device is not None
        session.add(
            MinuteMeasurement(
                device_id=first_device.id,
                bucket_start=now - timedelta(minutes=5),
                sample_count=1,
                current_l1_avg=1.5,
                current_l1_min=1.5,
                current_l1_max=1.5,
            )
        )
        session.add(
            User(
                username="operator",
                password_hash=hash_password("correct-horse-battery-staple"),
                enabled=True,
            )
        )
        session.add_all(
            [
                Device(
                    name="Bauwagen",
                    technical_device_id="id139_bauwagen",
                    mqtt_topic_prefix="id139_bauwagen",
                    mqtt_client_id="DVES_5ED4C8",
                    mqtt_username="bauwagen",
                    device_type="tasmota_plug",
                    controllable=True,
                    relay_index=1,
                    sort_order=20,
                    color="#21d4a7",
                ),
                Device(
                    name="Kühltruhe",
                    technical_device_id="kuehltruhe",
                    mqtt_topic_prefix="kuehltruhe",
                    mqtt_client_id="DVES_TEST0001",
                    device_type="tasmota_plug",
                    controllable=False,
                    relay_index=1,
                    sort_order=21,
                    color="#36a3ff",
                ),
            ]
        )
    runtime.mqtt.handle_message(
        "tele/id139_bauwagen/SENSOR",
        '{"ENERGY":{"Current":1.25,"Voltage":231,"Power":289}}',
    )
    runtime.mqtt.handle_message("tele/id139_bauwagen/LWT", "Online")
    runtime.mqtt.handle_message("stat/id139_bauwagen/POWER", "OFF")
    runtime.mqtt.handle_message(
        "tele/kuehltruhe/SENSOR",
        '{"ENERGY":{"Current":0.75,"Voltage":230,"Power":172}}',
    )
    runtime.mqtt.handle_message("tele/kuehltruhe/LWT", "Offline")
    E2E_APP = application
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    E2E_APP = None


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_fullscreen_monitor_at_all_viewports(
    page: Page, live_server: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(live_server)
    page.wait_for_selector("#historyCanvas")
    dimensions = page.evaluate(
        """() => ({
          bodyScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          monitorWidth: document.querySelector('#monitor').getBoundingClientRect().width,
          monitorHeight: document.querySelector('#monitor').getBoundingClientRect().height,
          canvasWidth: document.querySelector('#historyCanvas').getBoundingClientRect().width,
          menu: document.querySelector('#menuButton').getBoundingClientRect(),
        })"""
    )
    assert dimensions["bodyScroll"] == 0
    assert abs(dimensions["monitorWidth"] - width) <= 1
    assert abs(dimensions["monitorHeight"] - height) <= 1
    assert abs(dimensions["canvasWidth"] - width) <= 1
    assert dimensions["menu"]["right"] <= width
    assert dimensions["menu"]["top"] >= 0


def test_legend_selection_persistence_login_and_canvas_resize(page: Page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server)
    assert page.locator("#metricControls").count() == 0
    assert page.locator("#phaseControls").count() == 0
    assert page.locator("#liveCards").count() == 0
    legend = page.locator("#deviceLegend")
    canvas = page.locator("#historyCanvas")
    assert legend.is_hidden()
    ga_button = page.get_by_role("button", name="Diagrammlegende öffnen")
    ga_button.focus()
    page.keyboard.press("Enter")
    assert legend.is_visible()
    legend_box = legend.bounding_box()
    canvas_box = canvas.bounding_box()
    assert legend_box is not None and canvas_box is not None
    assert legend_box["x"] >= 46
    assert legend_box["y"] >= 60
    assert legend_box["x"] + legend_box["width"] <= canvas_box["width"]

    device = page.locator(".legend-device").first
    device.get_by_role("button").click()
    current_group = device.locator(".legend-metric").filter(has_text="Strom")
    voltage_group = device.locator(".legend-metric").filter(has_text="Spannung")
    current_group.get_by_role("button").click()
    voltage_group.get_by_role("button").click(force=True)
    voltage_l1 = (
        voltage_group.locator(".legend-series").filter(has_text="L1").get_by_role("checkbox")
    )
    voltage_l1.check()
    assert current_group.locator(".legend-series input:checked").count() == 3
    assert voltage_l1.is_checked()
    assert device.locator(".legend-device-header input").evaluate("(input) => input.indeterminate")

    page.get_by_role("button", name="Diagrammlegende schließen").click()
    assert legend.is_hidden()
    page.reload()
    assert legend.is_hidden()
    page.get_by_role("button", name="Diagrammlegende öffnen").focus()
    page.keyboard.press("Space")
    assert legend.is_visible()

    page.get_by_role("button", name="Menü öffnen").click()
    page.get_by_role("heading", name="Anmelden").wait_for(state="visible")
    page.get_by_role("button", name="Schließen", exact=True).click()
    before = canvas.evaluate("(element) => element.width")
    page.set_viewport_size({"width": 844, "height": 390})
    page.wait_for_timeout(200)
    after = canvas.evaluate("(element) => element.width")
    assert before != after


def test_mouse_rectangle_zoom_and_reset(page: Page, live_server: str) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    history_requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            history_requests.append(request.url)
            if "/api/public/history-batch" in request.url
            else None
        ),
    )
    page.goto(live_server)
    canvas = page.locator("#historyCanvas")
    box = canvas.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 500, box["y"] + 300)
    page.mouse.down()
    page.mouse.move(box["x"] + 850, box["y"] + 430, steps=8)
    page.mouse.up()
    reset = page.get_by_role("button", name="Diagrammzoom zurücksetzen")
    assert reset.is_visible()
    page.wait_for_timeout(10_500)
    assert reset.is_visible()
    assert len(history_requests) >= 2
    assert "from=" in history_requests[1]
    reset.click()
    assert reset.is_hidden()


def test_touch_pinch_zoom_and_reset(page: Page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server)
    canvas = page.locator("#historyCanvas")
    events = [
        ("pointerdown", 1, 130),
        ("pointerdown", 2, 260),
        ("pointermove", 1, 90),
        ("pointermove", 2, 300),
        ("pointerup", 1, 90),
        ("pointerup", 2, 300),
    ]
    for event_type, pointer_id, client_x in events:
        canvas.dispatch_event(
            event_type,
            {
                "pointerId": pointer_id,
                "pointerType": "touch",
                "isPrimary": pointer_id == 1,
                "clientX": client_x,
                "clientY": 360,
                "button": 0,
            },
        )
    reset = page.get_by_role("button", name="Diagrammzoom zurücksetzen")
    assert reset.is_visible()
    reset.click()
    assert reset.is_hidden()


def test_series_colors_are_unique_and_stable(page: Page, live_server: str) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(live_server)
    colors = page.locator(".series-marker").evaluate_all(
        "(markers) => markers.map((marker) => "
        "getComputedStyle(marker).getPropertyValue('--series-color'))"
    )
    assert len(colors) >= 44
    assert len(set(colors)) == len(colors)
    assert page.get_by_role("checkbox", name="Römerbad, Spannung, Gesamt").count() == 0
    page.reload()
    reloaded_colors = page.locator(".series-marker").evaluate_all(
        "(markers) => markers.map((marker) => "
        "getComputedStyle(marker).getPropertyValue('--series-color'))"
    )
    assert reloaded_colors == colors


def login(page: Page, live_server: str) -> None:
    page.goto(live_server)
    page.get_by_role("button", name="Menü öffnen").click()
    page.get_by_label("Benutzername").fill("operator")
    page.get_by_label("Passwort", exact=True).fill("correct-horse-battery-staple")
    page.get_by_role("button", name="Anmelden").click()
    page.locator("#adminDrawer").wait_for(state="visible")


def test_protected_plug_overview_responsive_and_confirmation_driven(
    page: Page,
    live_server: str,
) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 360, "height": 800})
    login(page, live_server)
    page.get_by_role("button", name="Steckdosen-Übersicht").click()
    page.get_by_role("heading", name="Steckdosen-Übersicht").wait_for()
    assert page.locator(".plug-card").count() == 2
    assert page.locator(".plug-card", has_text="Kühltruhe").get_by_role("switch").count() == 0
    bauwagen = page.locator(".plug-card", has_text="Bauwagen")
    power_switch = bauwagen.get_by_role("switch")
    assert power_switch.count() == 1
    assert (
        page.locator("#adminContent").evaluate(
            "(element) => element.scrollWidth - element.clientWidth"
        )
        == 0
    )

    runtime = E2E_APP.state.runtime
    runtime.mqtt.connected = True
    runtime.mqtt.publish_power = lambda _device, _state: True
    power_switch.click()
    bauwagen.locator("[data-relay-state]").get_by_text("Wird eingeschaltet …").wait_for()
    assert power_switch.is_disabled()
    runtime.mqtt.handle_message("stat/id139_bauwagen/POWER", "ON")
    bauwagen.locator("[data-relay-state]").get_by_text("Eingeschaltet", exact=True).wait_for()
    assert bauwagen.get_by_role("switch").get_attribute("aria-checked") == "true"

    runtime.control.timeout_seconds = 0.1
    bauwagen.get_by_role("switch").click()
    bauwagen.locator("[data-relay-state]").get_by_text("Wird ausgeschaltet …").wait_for()
    bauwagen.get_by_text("Schalten nicht bestätigt", exact=True).wait_for(timeout=2000)
    assert bauwagen.get_by_role("switch").get_attribute("aria-checked") == "true"
    assert errors == []


def test_confirmed_state_is_restored_from_snapshot_after_reload(
    page: Page,
    live_server: str,
) -> None:
    page.set_viewport_size({"width": 900, "height": 720})
    login(page, live_server)
    page.get_by_role("button", name="Steckdosen-Übersicht").click()
    bauwagen = page.locator(".plug-card", has_text="Bauwagen")
    assert bauwagen.get_by_role("switch").get_attribute("aria-checked") == "true"
    page.reload()
    page.get_by_role("button", name="Menü öffnen").click()
    page.get_by_role("button", name="Steckdosen-Übersicht").click()
    bauwagen = page.locator(".plug-card", has_text="Bauwagen")
    assert bauwagen.get_by_role("switch").get_attribute("aria-checked") == "true"


def test_chart_survives_repeated_empty_refreshes_without_duplicate_runtime(
    page: Page,
    live_server: str,
) -> None:
    requests = 0
    errors: list[str] = []
    with E2E_APP.state.runtime.database.sessions() as session:
        first_device = session.query(Device).order_by(Device.sort_order).first()
        assert first_device is not None
        existing_series_key = f"{first_device.id}:current:l1"
    empty_existing_series = json.dumps(
        {
            "series": [{"key": existing_series_key, "points": []}],
            "to": "2026-08-06T12:00:00+00:00",
        }
    )
    sparse_existing_series = json.dumps(
        {
            "series": [
                {
                    "key": existing_series_key,
                    "points": [["2026-08-06T11:59:00+00:00", 1.5]],
                }
            ],
            "to": "2026-08-06T12:00:00+00:00",
        }
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("window.GA_TEST_HISTORY_INTERVAL_MS = 80")

    def history_route(route: Any) -> None:
        nonlocal requests
        requests += 1
        if requests == 1:
            route.continue_()
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=sparse_existing_series if requests % 2 == 0 else empty_existing_series,
            )

    page.route("**/api/public/history-batch**", history_route)
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(live_server)
    for _ in range(30):
        if page.evaluate("window.GAApp?.getVisibleSeriesCount() || 0") > 0:
            break
        page.wait_for_timeout(100)
    else:
        pytest.fail("Initial history series did not become visible")
    initial_count = page.evaluate("window.GAApp.getVisibleSeriesCount()")
    canvas = page.locator("#historyCanvas")
    box = canvas.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 420, box["y"] + 260)
    page.mouse.down()
    page.mouse.move(box["x"] + 820, box["y"] + 420)
    page.mouse.up()
    reset = page.get_by_role("button", name="Diagrammzoom zurücksetzen")
    assert reset.is_visible()
    page.wait_for_timeout(550)
    assert requests >= 4
    assert requests < 14
    assert page.evaluate("window.GAApp.getVisibleSeriesCount()") == initial_count
    assert reset.is_visible()
    assert E2E_APP.state.runtime.websockets.count == 1
    assert errors == []
