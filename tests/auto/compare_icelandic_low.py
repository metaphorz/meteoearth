"""Diagnose Icelandic-Low glyph placement for GFS vs ICON.

Loads the app, aims the globe at the North Atlantic, and for each model pulls
the detected HighLowLayer features. Reports every L/H in the Greenland-Iceland
box (50-75 N, 50 W - 10 E) and screenshots the view. Reference (Windy/Ventusky
2026-07-01): Icelandic Low ~995.6 hPa between Greenland and Iceland, a 2nd low
to the SE, and a high over southern Greenland.

    venv/bin/python tests/auto/compare_icelandic_low.py
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

# Center the globe on the North Atlantic (near Iceland).
AIM_JS = """
window.deckgl.setProps({ viewState: { longitude: -22, latitude: 63, zoom: 3.1 }});
return true;
"""

# Pull detected H/L features off the HighLowLayer's composite sublayer.
POINTS_JS = """
const lm = window.deckgl.layerManager;
const layer = lm.getLayers().find(l => l.state && Array.isArray(l.state.points));
if (!layer) return null;
return layer.state.points.map(f => ({
  type: f.properties.type, value: f.properties.value,
  lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1],
}));
"""


def in_box(p) -> bool:
    return 50 <= p["lat"] <= 75 and -50 <= p["lng"] <= 10


def report(driver, model: str) -> None:
    pts = driver.execute_script(POINTS_JS) or []
    box = sorted([p for p in pts if in_box(p)], key=lambda p: (p["type"], p["value"]))
    print(f"\n=== {model.upper()}  ({len(pts)} total H/L glyphs, "
          f"{len(box)} in N-Atlantic box) ===")
    for p in box:
        kind = "LOW " if p["type"] == "L" else "HIGH"
        print(f"  {kind} {p['value']:6.1f} hPa  at {p['lat']:5.1f}N "
              f"{p['lng']:7.1f}E")
    lows = [p for p in box if p["type"] == "L"]
    ice = [p for p in lows if -40 <= p["lng"] <= -10 and 58 <= p["lat"] <= 68]
    print(f"  -> {len(lows)} low(s) in box; "
          f"{'ICELANDIC LOW present' if ice else 'NO low between Greenland/Iceland'}")


def main() -> int:
    opts = Options()
    opts.add_argument("--window-size=1200,900")
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

        for model in ("gfs", "icon"):
            btn = driver.find_elements(By.CSS_SELECTOR, f'button[data-model="{model}"]')
            if btn:
                btn[0].click()
                time.sleep(4)  # model reload + H/L recompute
            driver.execute_script(AIM_JS)
            time.sleep(2)
            report(driver, model)
            driver.save_screenshot(str(OUT / f"icelandic-{model}.png"))
            print(f"  saved icelandic-{model}.png")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
