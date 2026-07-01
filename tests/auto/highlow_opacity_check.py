"""Screenshot the H/L glyphs to check value-keyed opacity.

Deep lows / strong highs should render solid; weak centers near 1013 hPa should
be semi-transparent. Captures a wide North-Atlantic/Europe view (many systems of
varying strength) and reports any console errors (e.g. palette-parse failures).

    venv/bin/python tests/auto/highlow_opacity_check.py
"""
from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

OUT = Path(__file__).resolve().parent
URL = "http://localhost:5862/frontend/index.html"
AIM_JS = ("window.deckgl.setProps({ viewState: "
          "{ longitude: -15, latitude: 55, zoom: 1.9 }}); return true;")


def main() -> int:
    opts = Options()
    opts.add_argument("--window-size=1400,950")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        WebDriverWait(driver, 30).until(
            lambda d: any(m in d.find_element(By.ID, "status").text
                          for m in ("GFS", "ICON", "GEM", "ECMWF")))
        time.sleep(2)
        driver.execute_script(AIM_JS)
        time.sleep(2)
        driver.save_screenshot(str(OUT / "highlow-opacity.png"))
        print("saved highlow-opacity.png")
        errs = [e for e in driver.get_log("browser") if e["level"] == "SEVERE"]
        print(f"severe console errors: {len(errs)}")
        for e in errs[:5]:
            print("  ", e["message"][:200])
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
