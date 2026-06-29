"""Capture manual figures for meteoearth via Selenium.

Drives the live app through a sequence of states and saves crisp full-window
PNGs into docs/figures/. Figures are then included by docs/manual.tex.

Run from the project root (server must be up):
    ./start
    venv/bin/python docs/capture_figures.py
"""

from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "docs" / "figures"
URL = "http://localhost:5862/frontend/index.html"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)s  %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("capture")


def driver_new() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--window-size=1500,950")
    opts.add_argument("--force-device-scale-factor=2")  # crisp retina figures
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Chrome(options=opts)


def save(driver, name: str) -> None:
    path = FIG_DIR / f"{name}.png"
    driver.save_screenshot(str(path))
    log.info("saved %s (%d KB)", path.name, path.stat().st_size // 1024)


def click_overlay(driver, name: str) -> None:
    driver.find_element(
        By.CSS_SELECTOR, f'#controls button[data-overlay="{name}"]').click()


def click_wind(driver, level: str) -> None:
    driver.find_element(
        By.CSS_SELECTOR, f'#controls button[data-wind="{level}"]').click()


def toggle_highlow(driver) -> None:
    driver.find_element(
        By.CSS_SELECTOR, '#controls button[data-toggle="highLow"]').click()


def click_model(driver, sid: str) -> None:
    driver.find_element(
        By.CSS_SELECTOR, f'#controls button[data-model="{sid}"]').click()


def set_step(driver, where: str) -> None:
    """Move the forecast time slider to 'max' or '0' and fire its input event."""
    driver.execute_script(
        "const s=document.getElementById('tb-slider');"
        "s.value = arguments[0]==='max' ? s.max : '0';"
        "s.dispatchEvent(new Event('input',{bubbles:true}));", where)


# Pick an on-screen H/L glyph and return its CSS pixel + central pressure.
FIND_GLYPH_JS = """
const lm = window.deckgl.layerManager;
const layer = lm.getLayers().find(l => l.state && Array.isArray(l.state.points));
if (!layer) return null;
const vp = window.deckgl.getViewports()[0];
let best = null;
for (const f of layer.state.points) {
  const [lng, lat] = f.geometry.coordinates;
  const px = vp.project([lng, lat]);
  if (!px) continue;
  const [x, y] = px;
  if (x < 80 || y < 80 || x > vp.width - 80 || y > vp.height - 80) continue;
  const info = window.deckgl.pickObject({ x: Math.round(x), y: Math.round(y), radius: 10 });
  const t = info && info.object && info.object.properties && info.object.properties.type;
  // Prefer a deep low so the figure shows a clear cyclonic vortex.
  if (t === 'L') return { x: Math.round(x), y: Math.round(y) };
  if ((t === 'L' || t === 'H') && !best) best = { x: Math.round(x), y: Math.round(y) };
}
return best;
"""


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    log.info("launching Chrome")
    driver = driver_new()
    try:
        driver.get(URL)
        canvas = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        WebDriverWait(driver, 30).until(
            lambda d: "GFS" in d.find_element(By.ID, "status").text)
        log.info("status: %r", driver.find_element(By.ID, "status").text)
        time.sleep(3)  # let particles animate into long trails

        # 1) Overview: default state (no overlay, 10 m wind, H/L centers on).
        save(driver, "fig_overview")

        # 2) Pressure systems: MSLP overlay + H/L centers (the hero shot).
        click_overlay(driver, "mslp")
        time.sleep(2)
        save(driver, "fig_highlow")

        # 3) Hover detail badge on a pressure center.
        hit = driver.execute_script(FIND_GLYPH_JS)
        if hit:
            rect = driver.execute_script(
                "const r=document.querySelector('canvas').getBoundingClientRect();"
                "return {w:r.width,h:r.height};")
            dx = int(hit["x"] - rect["w"] / 2)
            dy = int(hit["y"] - rect["h"] / 2)
            ActionChains(driver).move_to_element_with_offset(canvas, dx, dy).perform()
            time.sleep(1.0)
            save(driver, "fig_highlow_hover")
        else:
            log.warning("no on-screen glyph found for hover figure")

        # 4) Temperature overlay.
        click_overlay(driver, "tmp_2m")
        time.sleep(2)
        save(driver, "fig_temp")

        # 5) Precipitable water (atmospheric rivers).
        click_overlay(driver, "pwat")
        time.sleep(2)
        save(driver, "fig_pwat")

        # 6) Cloud cover (satellite-like).
        click_overlay(driver, "cloud_cover")
        time.sleep(2)
        save(driver, "fig_cloud")

        # 7) Jet stream: 250 hPa wind, no overlay, H/L off for a clean field.
        click_overlay(driver, "none")
        click_wind(driver, "wind_250mb")
        toggle_highlow(driver)            # off
        time.sleep(3)                     # re-spawn particles + animate
        save(driver, "fig_jet")
        toggle_highlow(driver)            # back on
        click_wind(driver, "wind_10m")

        # 8) Pinned readout panel (right-click to pin a point).
        click_overlay(driver, "tmp_2m")
        time.sleep(1.5)
        size = canvas.size
        ActionChains(driver).move_to_element_with_offset(
            canvas, int(size["width"] * 0.15), int(size["height"] * 0.1)) \
            .context_click().perform()
        time.sleep(1.0)
        save(driver, "fig_pin")

        # 9) Forecast time dimension: scrub to the +48 h step.
        driver.find_element(By.ID, "pin-close").click()
        set_step(driver, "max")
        time.sleep(2)
        save(driver, "fig_forecast")

        # 10) CAPE overlay (thunderstorm potential) — a Phase-9 layer.
        set_step(driver, "0")
        click_overlay(driver, "cape")
        time.sleep(2)
        save(driver, "fig_cape")

        # 11) Model selector: switch to ECMWF; RH/precip/CAPE grey out.
        click_model(driver, "ecmwf")
        WebDriverWait(driver, 20).until(
            lambda d: "ECMWF" in d.find_element(By.ID, "status").text)
        click_overlay(driver, "tmp_2m")
        time.sleep(2)
        save(driver, "fig_models")

        log.info("done — %d figures in %s", len(list(FIG_DIR.glob('*.png'))), FIG_DIR)
    finally:
        driver.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
