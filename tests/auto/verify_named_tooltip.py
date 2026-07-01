"""Verify named-system labels appear in the H/L hover tooltip.

Loads the app, aims at the North Atlantic, finds the Icelandic-Low glyph, moves
the mouse onto it, and asserts the hover badge names it "Icelandic Low".

    venv/bin/python tests/auto/verify_named_tooltip.py
"""
from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

OUT = Path(__file__).resolve().parent
URL = "http://localhost:5862/frontend/index.html"
AIM_JS = ("window.deckgl.setProps({ viewState: "
          "{ longitude: -30, latitude: 63, zoom: 3.4 }}); return true;")

# Project the deepest low in the Greenland-Iceland box to a screen pixel.
FIND_JS = """
const lm = window.deckgl.layerManager;
const layer = lm.getLayers().find(l => l.state && Array.isArray(l.state.points));
if (!layer) return null;
const vp = window.deckgl.getViewports()[0];
let best = null;
for (const f of layer.state.points) {
  const [lng, lat] = f.geometry.coordinates;
  if (f.properties.type !== 'L') continue;
  if (lat < 58 || lat > 68 || lng < -40 || lng > -10) continue;
  const px = vp.project([lng, lat]); if (!px) continue;
  const [x, y] = px;
  if (x < 0 || y < 0 || x > vp.width || y > vp.height) continue;
  if (!best || f.properties.value < best.value)
    best = { x: Math.round(x), y: Math.round(y), value: f.properties.value };
}
return best;
"""


def main() -> int:
    opts = Options()
    opts.add_argument("--window-size=1200,900")
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

        target = driver.execute_script(FIND_JS)
        if not target:
            print("FAIL: no Icelandic-Low glyph found on screen")
            return 1
        print(f"Icelandic-Low glyph at px ({target['x']},{target['y']}) "
              f"value {target['value']:.0f} hPa")

        canvas = driver.find_element(By.TAG_NAME, "canvas")
        rect = driver.execute_script(
            "const r=arguments[0].getBoundingClientRect();return [r.left,r.top];",
            canvas)
        ActionChains(driver).move_to_element_with_offset(
            canvas, target["x"] - canvas.size["width"] // 2,
            target["y"] - canvas.size["height"] // 2).perform()
        time.sleep(1.5)

        badge = driver.find_element(By.ID, "hover-badge")
        text = badge.text
        print("--- badge text ---")
        print(text or "(empty)")
        driver.save_screenshot(str(OUT / "named-tooltip.png"))
        ok = "Icelandic Low" in text
        print("\nPASS" if ok else "\nFAIL: badge did not name the Icelandic Low")
        return 0 if ok else 1
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
