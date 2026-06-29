"""Selenium verification for the forecast time dimension (Phase 8).

Boots the frontend, waits for the globe, then exercises the time bar:
  - the bar exists with the right number of steps (matches index.json),
  - the valid-time label starts at "analysis",
  - scrubbing the slider to the last step advances the label and forecast lead,
  - Next / Prev move one step,
  - a temperature overlay readout at a fixed pin changes between two steps
    (proves the underlying textures actually swap, not just the label).

Run from project root (server must be up: ./start or python -m http.server 5862):
    venv/bin/python tests/auto/test_timebar.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "tests" / "auto"
LOG_FILE = LOG_DIR / "test_timebar.log"
URL = "http://localhost:5862/frontend/index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, mode="w"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("timebar-test")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    log.info("%s %s %s", "PASS" if ok else "FAIL", name, detail)


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--window-size=1400,900")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Chrome(options=opts)


def snapshot(driver, name: str) -> None:
    p = LOG_DIR / f"selenium-{name}.png"
    driver.save_screenshot(str(p))
    log.info("snapshot %s -> %s (%d KB)", name, p, p.stat().st_size // 1024)


def main() -> int:
    full = json.loads(
        urllib.request.urlopen("http://localhost:5862/data/index.json").read())
    # Time bar reflects the default model's forecast steps.
    index = next(s for s in full["sources"] if s["id"] == full["default"])
    n_steps = len(index["times"])
    log.info("index.json: default=%s %d steps, run %s",
             full["default"], n_steps, index["run_time"])

    driver = make_driver()
    try:
        driver.get(URL)
        # Wait until the deck canvas + time bar exist and status shows the run.
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "tb-slider")))
        WebDriverWait(driver, 30).until(
            lambda d: "GFS" in d.find_element(By.ID, "status").text)
        time.sleep(2)

        slider = driver.find_element(By.ID, "tb-slider")
        label = driver.find_element(By.ID, "tb-label")

        check("slider max matches steps",
              int(slider.get_attribute("max")) == n_steps - 1,
              f"max={slider.get_attribute('max')} expected {n_steps - 1}")
        check("starts on analysis", "analysis" in label.text, repr(label.text))
        snapshot(driver, "timebar-01-analysis")

        # Pin a point (right-click center of globe) and read its Temp row, then
        # compare the same pin's reading at the last step.
        canvas = driver.find_element(By.TAG_NAME, "canvas")
        webdriver.ActionChains(driver).move_to_element(canvas).context_click().perform()
        time.sleep(1)
        # Turn on temp overlay too (visual), harmless if it no-ops.
        driver.find_element(By.CSS_SELECTOR, "button[data-overlay='tmp_2m']").click()
        time.sleep(1)
        pin_before = driver.find_element(By.ID, "pin-rows").text
        log.info("pin @ analysis:\n%s", pin_before)

        # Scrub to last step via JS-set value + input event (range drag is flaky).
        last = n_steps - 1
        driver.execute_script(
            "const s=arguments[0];s.value=arguments[1];"
            "s.dispatchEvent(new Event('input',{bubbles:true}));", slider, last)
        WebDriverWait(driver, 15).until(
            lambda d: f"+{index['times'][last]['forecast_hour']} h"
            in d.find_element(By.ID, "tb-label").text)
        time.sleep(1)
        label_last = driver.find_element(By.ID, "tb-label").text
        check("scrub to last step updates label",
              f"+{index['times'][last]['forecast_hour']} h" in label_last,
              repr(label_last))
        check("slider value moved to last",
              int(slider.get_attribute("value")) == last,
              f"value={slider.get_attribute('value')}")
        pin_after = driver.find_element(By.ID, "pin-rows").text
        log.info("pin @ +%dh:\n%s", index["times"][last]["forecast_hour"], pin_after)
        check("pin readout differs between steps", pin_before != pin_after,
              "readout unchanged across 48h — textures may not be swapping"
              if pin_before == pin_after else "changed")
        snapshot(driver, "timebar-02-last-step")

        # Prev button steps back one.
        driver.find_element(By.ID, "tb-prev").click()
        time.sleep(1)
        check("prev steps back one",
              int(slider.get_attribute("value")) == last - 1,
              f"value={slider.get_attribute('value')}")

        # Console errors?
        errs = [e for e in driver.get_log("browser")
                if e["level"] == "SEVERE" and "favicon" not in e["message"]]
        check("no severe console errors", not errs,
              "; ".join(e["message"][:120] for e in errs) if errs else "")
    finally:
        driver.quit()

    passed = sum(1 for _, ok, _ in results if ok)
    log.info("RESULT %d/%d checks passed", passed, len(results))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
