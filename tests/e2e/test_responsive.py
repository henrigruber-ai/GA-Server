"""
File: tests/e2e/test_responsive.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Verifies full-screen responsive layout, controls, canvas resize, and anonymous login entry.
Changes:
- 0.1.0: Initial implementation.
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


def test_controls_login_and_canvas_resize(page: Page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server)
    page.get_by_role("button", name="Spannung").click()
    assert page.locator("[data-phase='total']").is_disabled()
    page.get_by_role("button", name="L2").click()
    page.get_by_role("button", name="Menü öffnen").click()
    page.get_by_role("heading", name="Anmelden").wait_for(state="visible")
    page.get_by_role("button", name="Schließen").click()
    before = page.locator("#historyCanvas").evaluate("(canvas) => canvas.width")
    page.set_viewport_size({"width": 844, "height": 390})
    page.wait_for_timeout(200)
    after = page.locator("#historyCanvas").evaluate("(canvas) => canvas.width")
    assert before != after
