"""Discover the latest available GFS cycle and download GRIB2 subsets, one
per variable defined in `variables.py`.

NOMADS filter endpoint lets us request only specific variables/levels, so
each subset is a few hundred KB instead of hundreds of MB.

Outputs:
  data/raw/<var>.f000.grib2  -- one per variable
  data/raw/run.json          -- which cycle the files came from
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from variables import VARIABLES, Variable

NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p50.pl"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

PUBLICATION_LAG_HOURS = 5  # GFS cycle published ~3.5-4.5h after run; pad to 5


def latest_cycles() -> list[datetime]:
    """Candidate cycles to try, newest first, all at least PUBLICATION_LAG_HOURS old."""
    now = datetime.now(timezone.utc) - timedelta(hours=PUBLICATION_LAG_HOURS)
    cycle_hour = (now.hour // 6) * 6
    base = now.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)
    return [base - timedelta(hours=6 * i) for i in range(4)]  # last 4 cycles


def build_url(var: Variable, cycle: datetime, forecast_hour: int = 0) -> str:
    yyyymmdd = cycle.strftime("%Y%m%d")
    hh = cycle.strftime("%H")
    fxxx = f"f{forecast_hour:03d}"
    base = {
        "dir": f"/gfs.{yyyymmdd}/{hh}/atmos",
        "file": f"gfs.t{hh}z.pgrb2full.0p50.{fxxx}",
    }
    params = {**base, **var.nomads_params}
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{NOMADS}?{qs}"


def download(url: str, dest: Path, timeout: int = 60) -> bool:
    print(f"[fetch] GET {url}", flush=True)
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        print(f"[fetch]   HTTP {r.status_code}", flush=True)
        return False
    body = r.content
    if not body.startswith(b"GRIB"):
        print(f"[fetch]   not a GRIB2 response (first 16 bytes: {body[:16]!r})",
              flush=True)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    size_kb = dest.stat().st_size / 1024
    print(f"[fetch]   wrote {dest.name} ({size_kb:.1f} KB)", flush=True)
    return True


def fetch_cycle(cycle: datetime) -> bool:
    """Try to download every variable for this cycle. All-or-nothing per cycle."""
    successes = []
    for var in VARIABLES:
        dest = RAW_DIR / f"{var.name}.f000.grib2"
        url = build_url(var, cycle)
        if not download(url, dest):
            return False
        successes.append(var.name)
    return True


def main() -> int:
    for cycle in latest_cycles():
        print(f"[fetch] trying cycle {cycle.isoformat()}", flush=True)
        if fetch_cycle(cycle):
            (RAW_DIR / "run.json").write_text(json.dumps({
                "run": cycle.strftime("%Y-%m-%dT%H:00:00Z"),
                "forecast_hour": 0,
                "resolution_deg": 0.5,
                "variables": [v.name for v in VARIABLES],
            }, indent=2))
            print(f"[fetch] using cycle {cycle.isoformat()}", flush=True)
            return 0
        print(f"[fetch] cycle {cycle.isoformat()} unavailable, trying older",
              flush=True)
    print("[fetch] no recent GFS cycle available", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
