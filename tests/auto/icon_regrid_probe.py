"""Validation probe for the ICON icosahedral -> lat-lon regrid.

Downloads ICON global CLAT/CLON (cell-center coords) + PMSL f000 for the most
recent cycle, builds a 3D KD-tree nearest-neighbor mapping to a 0.25 deg
lat-lon grid, regrids MSLP, and reports the lows in the North Atlantic
(Greenland-Iceland). Reference (Windy/Ventusky 2026-07-01): an Icelandic Low
~995.6 hPa (29.4 inHg) between Greenland and Iceland, a second low to the SE.

    venv/bin/python tests/auto/icon_regrid_probe.py
"""
from __future__ import annotations

import bz2
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
import xarray as xr
from scipy.spatial import cKDTree

HOST = "https://opendata.dwd.de/weather/nwp/icon/grib"
OUT = Path(__file__).resolve().parent / "icon_probe"
OUT.mkdir(exist_ok=True)


def candidate_cycles() -> list[datetime]:
    now = datetime.now(timezone.utc)
    base = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    return [base - timedelta(hours=6 * i) for i in range(6)]


def single_url(hh: str, ymdh: str, fhr: int, var_dir: str, var_up: str) -> str:
    fn = f"icon_global_icosahedral_single-level_{ymdh}_{fhr:03d}_{var_up}.grib2.bz2"
    return f"{HOST}/{hh}/{var_dir}/{fn}"


def invariant_url(hh: str, ymdh: str, name: str) -> str:
    fn = f"icon_global_icosahedral_time-invariant_{ymdh}_{name}.grib2.bz2"
    return f"{HOST}/{hh}/{name.lower()}/{fn}"


def fetch_bz2(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    dest.write_bytes(bz2.decompress(r.content))
    return dest


def sole_values(path: Path) -> np.ndarray:
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    (key,) = list(ds.data_vars)
    return ds[key].values.astype(np.float64)


def main() -> int:
    # Discover a cycle whose PMSL f000 is published.
    cycle = None
    for c in candidate_cycles():
        hh, ymdh = c.strftime("%H"), c.strftime("%Y%m%d%H")
        url = single_url(hh, ymdh, 0, "pmsl", "PMSL")
        if requests.head(url, timeout=30).status_code == 200:
            cycle = c
            break
    if cycle is None:
        print("no ICON cycle found")
        return 1
    hh, ymdh = cycle.strftime("%H"), cycle.strftime("%Y%m%d%H")
    print(f"cycle {cycle.isoformat()}")

    clat = sole_values(fetch_bz2(invariant_url(hh, ymdh, "CLAT"), OUT / "clat.grib2"))
    clon = sole_values(fetch_bz2(invariant_url(hh, ymdh, "CLON"), OUT / "clon.grib2"))
    pmsl = sole_values(fetch_bz2(single_url(hh, ymdh, 0, "pmsl", "PMSL"), OUT / "pmsl.grib2"))
    print(f"cells: clat={clat.shape} clon={clon.shape} pmsl={pmsl.shape}")
    print(f"clat range [{clat.min():.3f}, {clat.max():.3f}]  "
          f"clon range [{clon.min():.3f}, {clon.max():.3f}]")

    # CLAT/CLON come in degrees already for ICON GRIB; guard for radians.
    if np.nanmax(np.abs(clat)) <= np.pi + 1e-3:
        clat, clon = np.degrees(clat), np.degrees(clon)
        print("(converted radians -> degrees)")

    # Build 3D unit-vector KD-tree of source cells (robust across the poles / seam).
    def to_xyz(lat, lon):
        la, lo = np.radians(lat), np.radians(lon)
        cl = np.cos(la)
        return np.stack([cl * np.cos(lo), cl * np.sin(lo), np.sin(la)], axis=-1)

    tree = cKDTree(to_xyz(clat, clon))

    # Target grid: 0.25 deg, lat 90 -> -90, lon 0 -> 359.75 (matches encode roll).
    lat_t = np.arange(90.0, -90.001, -0.25)
    lon_t = np.arange(0.0, 360.0, 0.25)
    LON, LAT = np.meshgrid(lon_t, lat_t)
    _, idx = tree.query(to_xyz(LAT.ravel(), LON.ravel()), k=1)
    grid = (pmsl[idx].reshape(LAT.shape)) / 100.0  # Pa -> hPa
    print(f"regridded MSLP grid {grid.shape}  range [{grid.min():.1f}, {grid.max():.1f}] hPa")

    # North Atlantic box: 55-70 N, 45 W - 5 E (Greenland-Iceland).
    lat_mask = (lat_t >= 55) & (lat_t <= 70)
    # express lon in [-180,180) for the box test
    lon180 = ((lon_t + 180) % 360) - 180
    lon_mask = (lon180 >= -45) & (lon180 <= 5)
    box = grid[np.ix_(lat_mask, lon_mask)]
    blat = lat_t[lat_mask]
    blon = lon180[lon_mask]
    i, j = np.unravel_index(np.argmin(box), box.shape)
    print("\n=== North Atlantic (55-70N, 45W-5E) ===")
    print(f"minimum MSLP {box[i, j]:.1f} hPa at lat {blat[i]:.2f}, lon {blon[j]:.2f}")
    print("reference Icelandic Low ~995.6 hPa between Greenland and Iceland "
          "(~63N, 30W)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
