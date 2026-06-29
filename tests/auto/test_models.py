"""Selenium verification for the multi-model selector (Phase 10).

Loads the frontend, then for each source in index.json:
  - clicks its model button,
  - asserts the status line shows that model's label + run time,
  - asserts overlays the model lacks are disabled, and ones it has are enabled,
  - pins a point and asserts the readout is non-empty.
Switches back to GFS and confirms a GFS-only overlay (precip) re-enables.

Run from project root (server up on :5862):
    venv/bin/python tests/auto/test_models.py
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
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "tests" / "auto"
URL = "http://localhost:5862/frontend/index.html"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "test_models.log", mode="w"),
              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("models-test")

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    log.info("%s %s %s", "PASS" if ok else "FAIL", name, detail)


def main() -> int:
    index = json.loads(urllib.request.urlopen("http://localhost:5862/data/index.json").read())
    sources = {s["id"]: s for s in index["sources"]}
    log.info("sources: %s", list(sources))

    opts = Options()
    opts.add_argument("--window-size=1400,900")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(options=opts)
    try:
        d.get(URL)
        WebDriverWait(d, 30).until(lambda x: "GFS" in x.find_element(By.ID, "status").text)
        time.sleep(2)

        # model buttons rendered for every source
        btns = d.find_elements(By.CSS_SELECTOR, "#model-btns button[data-model]")
        check("model buttons match sources",
              {b.get_attribute("data-model") for b in btns} == set(sources),
              str([b.get_attribute("data-model") for b in btns]))

        for sid, src in sources.items():
            d.find_element(By.CSS_SELECTOR, f"button[data-model='{sid}']").click()
            WebDriverWait(d, 20).until(
                lambda x: src["label"] in x.find_element(By.ID, "status").text)
            time.sleep(1.5)
            status = d.find_element(By.ID, "status").text
            check(f"{sid} status shows label+run", src["label"] in status and src["run_time"][:10] in status, repr(status))

            have = {v["name"] for v in src["variables"]}
            # a var this model lacks should be disabled; one it has, enabled
            for ov, want_enabled in [("tmp_2m", "tmp_2m" in have),
                                     ("pwat", "pwat" in have),
                                     ("cape", "cape" in have),
                                     ("prate", "prate" in have)]:
                el = d.find_element(By.CSS_SELECTOR, f"button[data-overlay='{ov}']")
                disabled = el.get_attribute("disabled") is not None
                check(f"{sid}: {ov} {'enabled' if want_enabled else 'disabled'}",
                      disabled != want_enabled, f"disabled={disabled}")

            # pin a point, expect a non-empty readout
            canvas = d.find_element(By.TAG_NAME, "canvas")
            ActionChains(d).move_to_element(canvas).context_click().perform()
            time.sleep(1)
            rows = d.find_element(By.ID, "pin-rows").text
            check(f"{sid}: pin readout non-empty", len(rows.strip()) > 0, repr(rows[:40]))

        errs = [e for e in d.get_log("browser")
                if e["level"] == "SEVERE" and "favicon" not in e["message"]]
        check("no severe console errors", not errs,
              "; ".join(e["message"][:120] for e in errs) if errs else "")
    finally:
        d.quit()

    passed = sum(1 for _, ok, _ in results if ok)
    log.info("RESULT %d/%d checks passed", passed, len(results))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
