"""Selenium verification for the H/L pressure-center overlay (Phase 6).

Boots Chrome, loads the local server, and checks that:
  * the HighLowLayer detects L/H centers from the MSLP field,
  * the glyphs render (default on) and disappear when toggled off,
  * a glyph is pickable and carries type / central pressure / coordinates,
  * hovering a glyph shows the detail badge.

Run from the project root (server must be up):
    ./start
    venv/bin/python tests/auto/test_highlow.py
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
LOG_FILE = LOG_DIR / "test_highlow.log"
URL = "http://localhost:5862/frontend/index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, mode="w"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("highlow-test")


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--window-size=1400,900")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Chrome(options=opts)


def snapshot(driver, name: str) -> Path:
    path = LOG_DIR / f"selenium-{name}.png"
    driver.save_screenshot(str(path))
    log.info("snapshot %s -> %s (%d KB)", name, path, path.stat().st_size // 1024)
    return path


# JS: pull the detected H/L features off the inner composite layer's state.
# (HighLowLayer wraps a "highlow-composite" sublayer that holds state.points.)
GET_POINTS_JS = """
const lm = window.deckgl.layerManager;
const layer = lm.getLayers().find(l => l.state && Array.isArray(l.state.points));
if (!layer) return null;
return layer.state.points.map(f => ({
  type: f.properties.type,
  value: f.properties.value,
  lng: f.geometry.coordinates[0],
  lat: f.geometry.coordinates[1],
}));
"""

# JS: find a glyph that is actually on the near hemisphere AND pickable, and
# return its screen pixel (CSS px, canvas top-left origin) plus the picked info.
FIND_PICKABLE_JS = """
const lm = window.deckgl.layerManager;
const layer = lm.getLayers().find(l => l.state && Array.isArray(l.state.points));
if (!layer) return null;
const vp = window.deckgl.getViewports()[0];
for (const f of layer.state.points) {
  const [lng, lat] = f.geometry.coordinates;
  const px = vp.project([lng, lat]);
  if (!px) continue;
  const [x, y] = px;
  if (x < 0 || y < 0 || x > vp.width || y > vp.height) continue;
  const info = window.deckgl.pickObject({ x: Math.round(x), y: Math.round(y), radius: 10 });
  const t = info && info.object && info.object.properties && info.object.properties.type;
  if (t === 'L' || t === 'H') {
    return { x: Math.round(x), y: Math.round(y), type: t,
             value: info.object.properties.value };
  }
}
return null;
"""


def main() -> int:
    log.info("launching Chrome")
    driver = make_driver()
    failures: list[str] = []

    try:
        driver.get(URL)
        canvas = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        WebDriverWait(driver, 30).until(
            lambda d: "GFS" in d.find_element(By.ID, "status").text
            or "error" in d.find_element(By.ID, "status").text.lower())
        log.info("status: %r", driver.find_element(By.ID, "status").text)
        time.sleep(2)  # let layers compute + a few frames render

        # 1) Features detected?
        points = driver.execute_script(GET_POINTS_JS)
        if not points:
            failures.append("HighLowLayer produced no L/H features")
            log.error("no points; dumping console")
            for e in driver.get_log("browser"):
                log.info("[browser %s] %s", e.get("level"), e.get("message"))
        else:
            lows = [p for p in points if p["type"] == "L"]
            highs = [p for p in points if p["type"] == "H"]
            log.info("detected %d centers: %d lows, %d highs",
                     len(points), len(lows), len(highs))
            for p in points[:8]:
                log.info("  %s  %.0f hPa  @ %.1f,%.1f",
                         p["type"], p["value"], p["lat"], p["lng"])
            if not lows:
                failures.append("no LOW centers detected")
            if not highs:
                failures.append("no HIGH centers detected")

        snapshot(driver, "07-highlow-initial")

        # 2) With MSLP overlay for visual context (glyphs over the pressure map)
        driver.find_element(
            By.CSS_SELECTOR, '#controls button[data-overlay="mslp"]').click()
        time.sleep(1.5)
        snapshot(driver, "07-highlow-mslp")

        # 3) Hover a glyph -> detail badge.
        hit = driver.execute_script(FIND_PICKABLE_JS)
        if not hit:
            failures.append("no pickable on-screen glyph found")
        else:
            log.info("pickable glyph: %s %.0f hPa at px (%d,%d)",
                     hit["type"], hit["value"], hit["x"], hit["y"])
            # Selenium 4 offsets are from the element center.
            rect = driver.execute_script(
                "const r=document.querySelector('canvas').getBoundingClientRect();"
                "return {w:r.width,h:r.height};")
            dx = int(hit["x"] - rect["w"] / 2)
            dy = int(hit["y"] - rect["h"] / 2)
            ActionChains(driver).move_to_element_with_offset(canvas, dx, dy).perform()
            time.sleep(0.8)
            disp = driver.execute_script(
                "return getComputedStyle(document.getElementById('hover-badge')).display")
            text = driver.find_element(By.ID, "hover-badge").text
            log.info("badge display=%r text=%r", disp, text.replace("\n", " | "))
            if disp == "none" or "pressure system" not in text.lower():
                failures.append(f"hover badge missing system detail: {text!r}")
            snapshot(driver, "07-highlow-hover")

        # 4) Toggle off -> layer/glyphs gone.
        driver.find_element(
            By.CSS_SELECTOR, '#controls button[data-toggle="highLow"]').click()
        time.sleep(1.0)
        present = driver.execute_script(
            "return !!window.deckgl.layerManager.getLayers()"
            ".find(l => l.id === 'highlow');")
        log.info("after toggle off, highlow layer present=%s", present)
        if present:
            failures.append("highlow layer still present after toggle off")
        snapshot(driver, "07-highlow-off")

        # With glyphs off, the plain point readout must still carry pressure:
        # hover open globe and confirm the badge has an MSLP row.
        ActionChains(driver).move_to_element_with_offset(canvas, 60, -30).perform()
        time.sleep(0.8)
        point_badge = driver.find_element(By.ID, "hover-badge").text
        log.info("point-hover badge: %r", point_badge.replace("\n", " | "))
        if "MSLP" not in point_badge:
            failures.append("point-hover badge missing MSLP/pressure row")

        # toggle back on for a clean final state
        driver.find_element(
            By.CSS_SELECTOR, '#controls button[data-toggle="highLow"]').click()

        severe = [e for e in driver.get_log("browser")
                  if e.get("level") == "SEVERE"
                  and "favicon.ico" not in e.get("message", "")]
        for e in severe:
            log.error("[browser SEVERE] %s", e.get("message"))
        if severe:
            failures.append(f"{len(severe)} severe console errors")

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
