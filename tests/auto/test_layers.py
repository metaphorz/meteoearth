"""Selenium verification for the Phase 9 data layers (gust, prate, cape).

Loads the frontend, then for each new overlay button:
  - clicks it and asserts the legend title shows the variable's label+units,
  - confirms the overlay button becomes active.
Then pins a point and asserts the readout panel includes Gust / Precip / CAPE
rows. Finally checks there are no severe console errors.

Run from project root (server must be up on :5862):
    venv/bin/python tests/auto/test_layers.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "tests" / "auto"
LOG_FILE = LOG_DIR / "test_layers.log"
URL = "http://localhost:5862/frontend/index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, mode="w"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("layers-test")

# overlay button data-overlay -> expected substring in the legend title
EXPECT = {
    "gust": "Wind gusts",
    "prate": "Precipitation rate",
    "cape": "CAPE",
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    log.info("%s %s %s", "PASS" if ok else "FAIL", name, detail)


def main() -> int:
    opts = Options()
    opts.add_argument("--window-size=1400,900")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(URL)
        WebDriverWait(driver, 30).until(
            lambda d: "GFS" in d.find_element(By.ID, "status").text)
        time.sleep(2)

        for overlay, want in EXPECT.items():
            btn = driver.find_element(
                By.CSS_SELECTOR, f"button[data-overlay='{overlay}']")
            btn.click()
            WebDriverWait(driver, 10).until(
                lambda d: want in d.find_element(By.ID, "legend-title").text)
            title = driver.find_element(By.ID, "legend-title").text
            check(f"{overlay} legend title", want in title, repr(title))
            check(f"{overlay} button active",
                  "active" in (btn.get_attribute("class") or ""), "")
            p = LOG_DIR / f"selenium-layer-{overlay}.png"
            driver.save_screenshot(str(p))

        # Pin a point and confirm the new rows appear in the readout.
        canvas = driver.find_element(By.TAG_NAME, "canvas")
        webdriver.ActionChains(driver).move_to_element(canvas).context_click().perform()
        time.sleep(1)
        rows = driver.find_element(By.ID, "pin-rows").text
        log.info("pin rows:\n%s", rows)
        check("readout has Gust row", "Gust" in rows, "")
        check("readout has Precip row", "Precip" in rows, "")
        check("readout has CAPE row", "CAPE" in rows, "")

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
