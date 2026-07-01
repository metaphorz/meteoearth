"""Per-source adapters: each knows how to discover its latest cycle, download
the raw GRIB for a canonical variable at a forecast hour, and decode it.

Sources (all global, so they fill the whole globe):
  - gfs    NOAA GFS 0.5°   via NOMADS filter endpoint
  - ecmwf  ECMWF IFS 0.25° via the ecmwf-opendata client
  - gem    ECCC GDPS 0.15° via the MSC hpfx file server
  - icon   DWD ICON 0.25°  via opendata.dwd.de (icosahedral grid, regridded)

Not every source provides every canonical variable (see SPECS per source).
"""

from __future__ import annotations

import bz2
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import time

import numpy as np
import requests
import xarray as xr

from decode import DecodedField, decode_grib

FORECAST_HOURS = list(range(0, 49, 3))   # analysis + 2-day forecast, every 3 h


def get_grib(url: str, timeout: int = 120, retries: int = 3) -> bytes:
    """GET a GRIB body, retrying transient failures (timeouts, 5xx, non-GRIB)."""
    last = ""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            if r.content[:4] == b"GRIB":
                return r.content
            last = f"HTTP {r.status_code}, first bytes {r.content[:12]!r}"
        except requests.RequestException as e:
            last = repr(e)[:120]
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries ({last}): {url}")


# --------------------------------------------------------------------------- #
#  GFS  (NOAA)                                                                 #
# --------------------------------------------------------------------------- #

class GFSSource:
    id = "gfs"
    label = "NOAA GFS"
    resolution_deg = 0.5
    forecast_hours = FORECAST_HOURS
    _NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p50.pl"
    _LAG_H = 5
    _FILTER = {"stepType": "instant"}

    # canonical -> (nomads params, [(cfgrib key or None) per component])
    SPECS: dict[str, tuple[dict, tuple]] = {
        "wind_10m":    ({"var_UGRD": "on", "var_VGRD": "on", "lev_10_m_above_ground": "on"}, ("u10", "v10")),
        "wind_250mb":  ({"var_UGRD": "on", "var_VGRD": "on", "lev_250_mb": "on"}, ("u", "v")),
        "tmp_2m":      ({"var_TMP": "on", "lev_2_m_above_ground": "on"}, (None,)),
        "rh_2m":       ({"var_RH": "on", "lev_2_m_above_ground": "on"}, (None,)),
        "mslp":        ({"var_PRMSL": "on", "lev_mean_sea_level": "on"}, (None,)),
        "cloud_cover": ({"var_TCDC": "on", "lev_entire_atmosphere": "on"}, (None,)),
        "pwat":        ({"var_PWAT": "on", "lev_entire_atmosphere_(considered_as_a_single_layer)": "on"}, (None,)),
        "gust":        ({"var_GUST": "on", "lev_surface": "on"}, (None,)),
        "prate":       ({"var_PRATE": "on", "lev_surface": "on"}, (None,)),
        "cape":        ({"var_CAPE": "on", "lev_surface": "on"}, (None,)),
    }

    def supported(self) -> list[str]:
        return list(self.SPECS)

    def candidate_cycles(self) -> list[datetime]:
        now = datetime.now(timezone.utc) - timedelta(hours=self._LAG_H)
        base = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
        return [base - timedelta(hours=6 * i) for i in range(4)]

    def _url(self, params: dict, cycle: datetime, fhr: int) -> str:
        ymd, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        base = {"dir": f"/gfs.{ymd}/{hh}/atmos",
                "file": f"gfs.t{hh}z.pgrb2full.0p50.f{fhr:03d}"}
        qs = "&".join(f"{k}={v}" for k, v in {**base, **params}.items())
        return f"{self._NOMADS}?{qs}"

    def cycle_available(self, cycle: datetime) -> bool:
        url = self._url(self.SPECS["tmp_2m"][0], cycle, 0)
        try:
            return requests.get(url, timeout=60).content[:4] == b"GRIB"
        except requests.RequestException:
            return False

    def fetch(self, canon: str, cycle: datetime, fhr: int, raw: Path) -> list[Path]:
        params, _keys = self.SPECS[canon]
        dest = raw / f"{canon}.f{fhr:03d}.grib2"
        body = get_grib(self._url(params, cycle, fhr))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return [dest]

    def decode(self, canon: str, fhr: int, raw: Path, transform, kind: str) -> DecodedField:
        _params, keys = self.SPECS[canon]
        f = raw / f"{canon}.f{fhr:03d}.grib2"
        pairs = [(f, k) for k in keys]          # one file, 1 or 2 keys
        return decode_grib(pairs, kind, transform, self._FILTER)


# --------------------------------------------------------------------------- #
#  ECMWF  (IFS open data)                                                      #
# --------------------------------------------------------------------------- #

class ECMWFSource:
    id = "ecmwf"
    label = "ECMWF IFS"
    resolution_deg = 0.25
    forecast_hours = FORECAST_HOURS
    _FILTER: dict = {}

    # canonical -> (retrieve kwargs, [cfgrib keys], optional transform override)
    SPECS: dict[str, tuple[dict, tuple, Optional[Callable]]] = {
        "wind_10m":    ({"param": ["10u", "10v"]}, ("u10", "v10"), None),
        "wind_250mb":  ({"levtype": "pl", "levelist": 250, "param": ["u", "v"]}, ("u", "v"), None),
        "tmp_2m":      ({"param": "2t"}, (None,), None),
        "mslp":        ({"param": "msl"}, (None,), None),
        # ECMWF tcc is a 0–1 fraction; scale to % to match the canonical palette.
        "cloud_cover": ({"param": "tcc"}, (None,), lambda x: x * 100.0),
        "pwat":        ({"param": "tcwv"}, (None,), None),
        "gust":        ({"param": "10fg"}, (None,), None),
    }

    def __init__(self):
        from ecmwf.opendata import Client
        self._client = Client(source="ecmwf")

    def supported(self) -> list[str]:
        return list(self.SPECS)

    def latest_cycle(self) -> datetime:
        dt = self._client.latest(type="fc", param="2t")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def fetch(self, canon: str, cycle: datetime, fhr: int, raw: Path) -> list[Path]:
        kwargs, _keys, _tf = self.SPECS[canon]
        dest = raw / f"{canon}.f{fhr:03d}.grib2"
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._client.retrieve(
            date=cycle.strftime("%Y%m%d"), time=cycle.hour,
            type="fc", step=fhr, target=str(dest), **kwargs,
        )
        return [dest]

    def decode(self, canon: str, fhr: int, raw: Path, transform, kind: str) -> DecodedField:
        _kwargs, keys, tf_override = self.SPECS[canon]
        f = raw / f"{canon}.f{fhr:03d}.grib2"
        pairs = [(f, k) for k in keys]
        return decode_grib(pairs, kind, tf_override or transform, self._FILTER)


# --------------------------------------------------------------------------- #
#  GEM / GDPS  (ECCC)                                                          #
# --------------------------------------------------------------------------- #

class GEMSource:
    id = "gem"
    label = "ECCC GEM"
    resolution_deg = 0.15
    forecast_hours = FORECAST_HOURS
    _HOST = "https://hpfx.collab.science.gc.ca"
    _FILTER: dict = {}

    # canonical -> [(token, level) per component]; vectors have two components,
    # which GDPS publishes as two separate files.
    SPECS: dict[str, list[tuple[str, str]]] = {
        "wind_10m":    [("WindU", "AGL-10m"), ("WindV", "AGL-10m")],
        "wind_250mb":  [("WindU", "IsbL-0250"), ("WindV", "IsbL-0250")],
        "tmp_2m":      [("AirTemp", "AGL-2m")],
        "rh_2m":       [("RelativeHumidity", "AGL-2m")],
        "mslp":        [("Pressure", "MSL")],
        "cloud_cover": [("TotalCloudCover", "Sfc")],
        "gust":        [("WindGust", "AGL-10m")],
        "cape":        [("CAPE", "Sfc")],
    }

    def supported(self) -> list[str]:
        return list(self.SPECS)

    def _url(self, ymd: str, hh: str, fhr: int, token: str, level: str) -> str:
        fname = f"{ymd}T{hh}Z_MSC_GDPS_{token}_{level}_LatLon0.15_PT{fhr:03d}H.grib2"
        return f"{self._HOST}/{ymd}/WXO-DD/model_gdps/15km/{hh}/{fhr:03d}/{fname}"

    def candidate_cycles(self) -> list[datetime]:
        now = datetime.now(timezone.utc)
        base = now.replace(hour=(now.hour // 12) * 12, minute=0, second=0, microsecond=0)
        return [base - timedelta(hours=12 * i) for i in range(4)]   # 00/12 cycles

    def cycle_available(self, cycle: datetime) -> bool:
        ymd, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        token, level = self.SPECS["tmp_2m"][0]
        url = self._url(ymd, hh, max(self.forecast_hours), token, level)
        try:
            return requests.head(url, timeout=30).status_code == 200
        except requests.RequestException:
            return False

    def fetch(self, canon: str, cycle: datetime, fhr: int, raw: Path) -> list[Path]:
        ymd, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        out: list[Path] = []
        for i, (token, level) in enumerate(self.SPECS[canon]):
            dest = raw / f"{canon}.f{fhr:03d}.{i}.grib2"
            body = get_grib(self._url(ymd, hh, fhr, token, level))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            out.append(dest)
        return out

    def decode(self, canon: str, fhr: int, raw: Path, transform, kind: str) -> DecodedField:
        # Each GDPS file holds a single message → take its sole data var (key None).
        n = len(self.SPECS[canon])
        pairs = [(raw / f"{canon}.f{fhr:03d}.{i}.grib2", None) for i in range(n)]
        return decode_grib(pairs, kind, transform, self._FILTER)


# --------------------------------------------------------------------------- #
#  ICON global  (DWD)                                                          #
# --------------------------------------------------------------------------- #

# ICON global publishes on an icosahedral (unstructured) grid — ~2.95M cells,
# not a lat-lon raster. We fetch the cell-center coordinates (CLAT/CLON, which
# are time-invariant) once per cycle, build a nearest-neighbor KD-tree in 3D
# unit-vector space (robust across the dateline and poles), and resample every
# field onto our standard 0.25° lat-lon grid. The grid mapping is identical for
# every variable and step, so it is built once and reused.

# Target raster: lat 90 -> -90, lon 0 -> 359.75 (matches encode's [0,360) roll).
_ICON_LAT = np.arange(90.0, -90.001, -0.25)    # 721 rows, north -> south
_ICON_LON = np.arange(0.0, 360.0, 0.25)        # 1440 cols, [0, 360)


def _latlon_to_xyz(lat_deg, lon_deg):
    """Unit vectors on the sphere — lets a KD-tree ignore the lon seam/poles."""
    la, lo = np.radians(lat_deg), np.radians(lon_deg)
    cl = np.cos(la)
    return np.stack([cl * np.cos(lo), cl * np.sin(lo), np.sin(la)], axis=-1)


def _fetch_bz2_grib(url: str, timeout: int = 120, retries: int = 3) -> bytes:
    """GET a .bz2-wrapped GRIB body, decompress, retry transient failures."""
    last = ""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                data = bz2.decompress(r.content)
                if data[:4] == b"GRIB":
                    return data
                last = f"decompressed head {data[:12]!r}"
            else:
                last = f"HTTP {r.status_code}"
        except (requests.RequestException, OSError) as e:
            last = repr(e)[:120]
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"ICON GET failed after {retries} tries ({last}): {url}")


def _icon_sole_values(path: Path) -> np.ndarray:
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    keys = list(ds.data_vars)
    if len(keys) != 1:
        raise ValueError(f"{path}: expected 1 data var, got {keys}")
    return ds[keys[0]].values


class ICONSource:
    id = "icon"
    label = "DWD ICON"
    resolution_deg = 0.25           # delivered grid (native ~0.13° icosahedral)
    forecast_hours = FORECAST_HOURS
    _HOST = "https://opendata.dwd.de/weather/nwp/icon/grib"

    # canonical -> (level_kind, level, [(dir, VAR_UPPER) per component])
    SPECS: dict[str, tuple[str, Optional[int], list[tuple[str, str]]]] = {
        "wind_10m":    ("single",   None, [("u_10m", "U_10M"), ("v_10m", "V_10M")]),
        "wind_250mb":  ("pressure", 250,  [("u", "U"), ("v", "V")]),
        "tmp_2m":      ("single",   None, [("t_2m", "T_2M")]),
        "rh_2m":       ("single",   None, [("relhum_2m", "RELHUM_2M")]),
        "mslp":        ("single",   None, [("pmsl", "PMSL")]),
        "cloud_cover": ("single",   None, [("clct", "CLCT")]),
        "pwat":        ("single",   None, [("tqv", "TQV")]),
        "gust":        ("single",   None, [("vmax_10m", "VMAX_10M")]),
        "cape":        ("single",   None, [("cape_ml", "CAPE_ML")]),
    }

    def __init__(self):
        self._cycle: Optional[datetime] = None
        self._idx: Optional[np.ndarray] = None   # target-grid -> source cell index

    def supported(self) -> list[str]:
        return list(self.SPECS)

    def candidate_cycles(self) -> list[datetime]:
        now = datetime.now(timezone.utc)
        base = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
        return [base - timedelta(hours=6 * i) for i in range(4)]   # 00/06/12/18

    def _comp_url(self, canon: str, cycle: datetime, fhr: int, d: str, up: str) -> str:
        ymdh, hh = cycle.strftime("%Y%m%d%H"), cycle.strftime("%H")
        kind, level, _ = self.SPECS[canon]
        if kind == "pressure":
            fn = f"icon_global_icosahedral_pressure-level_{ymdh}_{fhr:03d}_{level}_{up}.grib2.bz2"
        else:
            fn = f"icon_global_icosahedral_single-level_{ymdh}_{fhr:03d}_{up}.grib2.bz2"
        return f"{self._HOST}/{hh}/{d}/{fn}"

    def _invariant_url(self, cycle: datetime, name: str) -> str:
        ymdh, hh = cycle.strftime("%Y%m%d%H"), cycle.strftime("%H")
        fn = f"icon_global_icosahedral_time-invariant_{ymdh}_{name}.grib2.bz2"
        return f"{self._HOST}/{hh}/{name.lower()}/{fn}"

    def cycle_available(self, cycle: datetime) -> bool:
        # A cycle is usable only if its last forecast step is published.
        url = self._comp_url("mslp", cycle, max(self.forecast_hours), "pmsl", "PMSL")
        try:
            return requests.head(url, timeout=30).status_code == 200
        except requests.RequestException:
            return False

    def fetch(self, canon: str, cycle: datetime, fhr: int, raw: Path) -> list[Path]:
        self._cycle = cycle
        _, _, comps = self.SPECS[canon]
        out: list[Path] = []
        for i, (d, up) in enumerate(comps):
            dest = raw / f"{canon}.f{fhr:03d}.{i}.grib2"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_fetch_bz2_grib(self._comp_url(canon, cycle, fhr, d, up)))
            out.append(dest)
        return out

    def _ensure_grid(self, raw: Path) -> None:
        """Build the icosahedral -> lat-lon nearest-neighbor mapping once."""
        if self._idx is not None:
            return
        from scipy.spatial import cKDTree
        coords = {}
        for name in ("CLAT", "CLON"):
            p = raw / f"{name.lower()}.grib2"
            p.write_bytes(_fetch_bz2_grib(self._invariant_url(self._cycle, name)))
            coords[name] = _icon_sole_values(p).astype(np.float64)
        clat, clon = coords["CLAT"], coords["CLON"]
        if np.nanmax(np.abs(clat)) <= np.pi + 1e-3:     # radians -> degrees
            clat, clon = np.degrees(clat), np.degrees(clon)
        tree = cKDTree(_latlon_to_xyz(clat, clon))
        LON, LAT = np.meshgrid(_ICON_LON, _ICON_LAT)
        _, self._idx = tree.query(_latlon_to_xyz(LAT.ravel(), LON.ravel()), k=1)

    def decode(self, canon: str, fhr: int, raw: Path, transform, kind: str) -> DecodedField:
        self._ensure_grid(raw)
        _, _, comps = self.SPECS[canon]
        arrays: list[np.ndarray] = []
        run_time = valid_time = None
        for i in range(len(comps)):
            f = raw / f"{canon}.f{fhr:03d}.{i}.grib2"
            ds = xr.open_dataset(f, engine="cfgrib", backend_kwargs={"indexpath": ""})
            (key,) = list(ds.data_vars)
            vals = ds[key].values.astype(np.float32)
            a = vals[self._idx].reshape(_ICON_LAT.size, _ICON_LON.size)
            if transform is not None:
                a = transform(a)
            arrays.append(a)
            if run_time is None:
                run_time = str(np.datetime_as_string(ds["time"].values, unit="s")) + "Z"
                valid_time = str(np.datetime_as_string(ds["valid_time"].values, unit="s")) + "Z"
        return DecodedField(kind=kind, arrays=arrays, lat=_ICON_LAT, lon=_ICON_LON,
                            run_time=run_time, valid_time=valid_time)


SOURCES = {s.id: s for s in (GFSSource, ECMWFSource, GEMSource, ICONSource)}


def make_source(sid: str):
    return SOURCES[sid]()
