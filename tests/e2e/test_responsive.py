"""
File: tests/e2e/test_responsive.py
Version: 0.2.0
Date: 2026-08-04
Purpose: Verifies the responsive embedded legend, independent selection, zoom, and login entry.
Changes:
- 0.1.0: Initial implementation.
- 0.2.0: Covers hierarchical selection, persistence, axis clearance, and mouse zoom.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from app.config import Settings
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
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


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
    voltage_group.get_by_role("button").click()
    voltage_l1 = (
        voltage_group.locator(".legend-series").filter(has_text="L1").get_by_role("checkbox")
    )
    voltage_l1.check()
    assert current_group.locator(".legend-series input:checked").count() == 3
    assert voltage_l1.is_checked()
    assert device.locator(".legend-device-header input").evaluate("(input) => input.indeterminate")

    page.get_by_role("button", name="Messstellen").click()
    assert page.get_by_role("button", name="Messstellen").get_attribute("aria-expanded") == "false"
    page.reload()
    assert page.get_by_role("button", name="Messstellen").get_attribute("aria-expanded") == "false"

    page.get_by_role("button", name="Menü öffnen").click()
    page.get_by_role("heading", name="Anmelden").wait_for(state="visible")
    page.get_by_role("button", name="Schließen").click()
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
    assert len(colors) == 44
    assert len(set(colors)) == len(colors)
    assert page.get_by_role("checkbox", name="Römerbad, Spannung, Gesamt").count() == 0
    page.reload()
    reloaded_colors = page.locator(".series-marker").evaluate_all(
        "(markers) => markers.map((marker) => "
        "getComputedStyle(marker).getPropertyValue('--series-color'))"
    )
    assert reloaded_colors == colors
