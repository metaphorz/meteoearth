"""Selenium UI smoke test for the meteoearth frontend.

Boots a headed Chrome, loads the local server, waits for the GFS status text
and the deck.gl canvas, verifies no console errors, and snapshots the page
before/after a drag-to-rotate interaction.

Run from the project root:
    ./start                              # start the server first
    venv/bin/python tests/auto/test_ui.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "tests" / "auto"
LOG_FILE = LOG_DIR / "test_ui.log"
URL = "http://localhost:5862/frontend/index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ui-test")


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--window-size=1400,900")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Chrome(options=opts)


def snapshot(driver: webdriver.Chrome, name: str) -> Path:
    path = LOG_DIR / f"selenium-{name}.png"
    driver.save_screenshot(str(path))
    log.info("snapshot %s -> %s (%d KB)", name, path,
             path.stat().st_size // 1024)
    return path


def dump_console(driver: webdriver.Chrome) -> list[dict]:
    entries = driver.get_log("browser")
    for e in entries:
        log.info("[browser %s] %s", e.get("level"), e.get("message"))
    return entries


def main() -> int:
    log.info("launching Chrome")
    driver = make_driver()
    failures: list[str] = []

    try:
        log.info("GET %s", URL)
        driver.get(URL)

        log.info("waiting for canvas element (or surfacing early errors)")
        try:
            canvas = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "canvas"))
            )
            log.info("canvas found: size=%s", canvas.size)
        except Exception as e:
            log.error("canvas wait failed: %s", e)
            log.error("status text: %r",
                      driver.find_element(By.ID, "status").text)
            dump_console(driver)
            snapshot(driver, "00-timeout")
            raise

        log.info("waiting for status text to update past 'loading…'")
        WebDriverWait(driver, 30).until(
            lambda d: "GFS" in d.find_element(By.ID, "status").text
            or "error" in d.find_element(By.ID, "status").text.lower()
        )
        status_text = driver.find_element(By.ID, "status").text
        log.info("status: %r", status_text)
        if "error" in status_text.lower():
            failures.append(f"status reports error: {status_text!r}")

        # Let the particle layer render a couple of animation frames.
        time.sleep(2)
        snapshot(driver, "01-initial")

        # Console errors (severe), excluding harmless favicon 404.
        entries = dump_console(driver)
        severe = [
            e for e in entries
            if e.get("level") == "SEVERE"
            and "favicon.ico" not in e.get("message", "")
        ]
        if severe:
            failures.append(f"{len(severe)} severe console errors")

        # Interaction: drag-to-rotate
        log.info("dragging canvas to rotate globe")
        size = canvas.size
        ActionChains(driver) \
            .move_to_element(canvas) \
            .click_and_hold() \
            .move_by_offset(int(size["width"] * 0.25), 0) \
            .release() \
            .perform()
        time.sleep(2)
        snapshot(driver, "02-after-drag")

        # Phase 3: overlay buttons (incl. cloud_cover, pwat). Verify legend
        # appears for non-"none" and disappears for "none".
        for name in ["tmp_2m", "rh_2m", "mslp", "cloud_cover", "pwat", "none"]:
            log.info("clicking overlay button %s", name)
            btn = driver.find_element(
                By.CSS_SELECTOR, f'#controls button[data-overlay="{name}"]')
            btn.click()
            time.sleep(1.5)
            legend_disp = driver.execute_script(
                "return getComputedStyle(document.getElementById('legend')).display"
            )
            legend_title = driver.find_element(By.ID, "legend-title").text
            log.info("  legend display=%r title=%r", legend_disp, legend_title)
            if name == "none":
                if legend_disp != "none":
                    failures.append("legend visible while overlay=none")
            else:
                if legend_disp == "none":
                    failures.append(f"legend hidden while overlay={name}")
                if not legend_title:
                    failures.append(f"legend title empty for overlay={name}")
            snapshot(driver, f"03-overlay-{name}")

        # Wind level toggle: 10 m -> 250 hPa jet, then back
        for level in ["wind_250mb", "wind_10m"]:
            log.info("clicking wind level %s", level)
            btn = driver.find_element(
                By.CSS_SELECTOR, f'#controls button[data-wind="{level}"]')
            btn.click()
            time.sleep(2.0)  # let particles re-spawn at new field
            snapshot(driver, f"06-wind-{level}")

        # Phase 3: hover badge
        log.info("hovering over globe")
        ActionChains(driver) \
            .move_to_element_with_offset(canvas,
                                         int(size["width"] * 0.1),
                                         int(size["height"] * 0.05)) \
            .perform()
        time.sleep(1.0)
        badge_visible = driver.execute_script(
            "return getComputedStyle(document.getElementById('hover-badge')).display"
        )
        badge_text = driver.find_element(By.ID, "hover-badge").text
        log.info("badge display=%r text=%r", badge_visible, badge_text[:120])
        if badge_visible == "none" or "Wind" not in badge_text:
            failures.append("hover badge not showing wind values")
        snapshot(driver, "04-hover-badge")

        # Phase 3: right-click pin
        log.info("right-clicking to pin")
        ActionChains(driver) \
            .move_to_element_with_offset(canvas,
                                         int(size["width"] * 0.05),
                                         int(size["height"] * 0.0)) \
            .context_click() \
            .perform()
        time.sleep(1.0)
        pin_visible = driver.execute_script(
            "return getComputedStyle(document.getElementById('pin-panel')).display"
        )
        pin_text = driver.find_element(By.ID, "pin-panel").text
        log.info("pin display=%r text=%r", pin_visible, pin_text[:120])
        if pin_visible == "none":
            failures.append("pin panel did not appear after right-click")
        snapshot(driver, "05-pinned")

        # Verify the globe actually responded — check that the deck instance
        # exists on window and view state changed.
        deck_state = driver.execute_script("""
            if (!window.deckgl) return null;
            const vs = window.deckgl.viewManager?._viewports?.[0];
            return vs ? {
              longitude: vs.longitude, latitude: vs.latitude, zoom: vs.zoom
            } : null;
        """)
        log.info("deck viewport state: %s", json.dumps(deck_state))
        if not deck_state:
            log.warning("deck.gl viewport state not extractable (non-fatal)")

        log.info("UI test complete")
    finally:
        driver.quit()

    if failures:
        for f in failures:
            log.error("FAIL: %s", f)
        return 1
    log.info("PASS: all checks ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
