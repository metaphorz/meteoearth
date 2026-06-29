"""Per-source adapters: each knows how to discover its latest cycle, download
the raw GRIB for a canonical variable at a forecast hour, and decode it.

Sources (all global, so they fill the whole globe):
  - gfs    NOAA GFS 0.5°   via NOMADS filter endpoint
  - ecmwf  ECMWF IFS 0.25° via the ecmwf-opendata client
  - gem    ECCC GDPS 0.15° via the MSC hpfx file server

Not every source provides every canonical variable (see SPECS per source).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import time

import requests

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


SOURCES = {s.id: s for s in (GFSSource, ECMWFSource, GEMSource)}


def make_source(sid: str):
    return SOURCES[sid]()
