"""Capture Ventusky for comparison with meteoearth.

Loads ventusky.com at the Wisconsin coordinates, screenshots the default
view, then opens the layer menu and screenshots the full list of plottable
data layers. Also dumps the visible layer labels to a text file.

    venv/bin/python tests/auto/capture_ventusky.py
"""
from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT = Path(__file__).resolve().parent
URL = "https://www.ventusky.com/#p=43.5;-88.5;3"


def main() -> None:
    opts = Options()
    opts.add_argument("--window-size=1600,1000")
    opts.add_argument("--lang=en-US")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(URL)
        time.sleep(8)  # let the WebGL map + UI settle
        driver.save_screenshot(str(OUT / "ventusky-01-default.png"))
        print("saved ventusky-01-default.png")

        # Open the weather-layer menu (hamburger / layers button, top-left).
        # Ventusky exposes the layer list in the left menu; click it open.
        try:
            driver.find_element("css selector", "#menu_button, .menu_button").click()
            time.sleep(2)
            driver.save_screenshot(str(OUT / "ventusky-02-menu.png"))
            print("saved ventusky-02-menu.png")
        except Exception as e:  # noqa: BLE001
            print("menu click failed:", e)

        # Dump every bit of visible text containing layer names.
        body = driver.find_element("tag name", "body").text
        (OUT / "ventusky-text.txt").write_text(body, encoding="utf-8")
        print("saved ventusky-text.txt (%d chars)" % len(body))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
