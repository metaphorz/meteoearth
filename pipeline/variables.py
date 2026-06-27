"""Registry of GFS variables we ingest.

Each entry describes:
  - the NOMADS filter parameters for the subset download
  - the cfgrib short_name(s) used to read u/v (vector) or scalar data
  - an optional unit transform applied at decode time
  - the encoding range used for byte packing in the PNG
  - presentation metadata consumed by the frontend (label, unit, palette stops)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Variable:
    name: str                          # output stem, e.g. "wind_10m"
    label: str                         # human label
    units: str                         # display units
    kind: str                          # "vector" | "scalar"
    nomads_params: dict                # filter_gfs_0p50.pl parameters (level + var flags)
    grib_keys: tuple[str, ...]         # cfgrib short_names (1 for scalar, 2 for vector)
    encode_range: tuple[float, float]  # [vMin, vMax] used for byte packing
    transform: Optional[Callable] = None  # raw GRIB units -> display units
    palette: list[tuple[float, tuple[int, int, int]]] = field(default_factory=list)


VARIABLES: list[Variable] = [
    Variable(
        name="wind_10m",
        label="10 m wind",
        units="m/s",
        kind="vector",
        nomads_params={
            "var_UGRD": "on",
            "var_VGRD": "on",
            "lev_10_m_above_ground": "on",
        },
        grib_keys=("u10", "v10"),
        encode_range=(-50.0, 50.0),
    ),
    Variable(
        name="tmp_2m",
        label="2 m temperature",
        units="°C",
        kind="scalar",
        nomads_params={
            "var_TMP": "on",
            "lev_2_m_above_ground": "on",
        },
        grib_keys=("t2m",),
        transform=lambda x: x - 273.15,  # K -> °C
        encode_range=(-60.0, 50.0),
        palette=[
            (-60.0, (60, 0, 90)),
            (-40.0, (60, 60, 200)),
            (-20.0, (60, 160, 220)),
            (0.0,   (220, 220, 220)),
            (10.0,  (130, 200, 100)),
            (20.0,  (240, 200, 60)),
            (30.0,  (240, 110, 40)),
            (45.0,  (180, 0, 30)),
        ],
    ),
    Variable(
        name="rh_2m",
        label="2 m relative humidity",
        units="%",
        kind="scalar",
        nomads_params={
            "var_RH": "on",
            "lev_2_m_above_ground": "on",
        },
        grib_keys=("r2",),
        encode_range=(0.0, 100.0),
        palette=[
            (0.0,   (140, 90, 40)),
            (25.0,  (200, 170, 90)),
            (50.0,  (210, 220, 160)),
            (75.0,  (90, 180, 130)),
            (100.0, (10, 80, 120)),
        ],
    ),
    Variable(
        name="mslp",
        label="Mean sea-level pressure",
        units="hPa",
        kind="scalar",
        nomads_params={
            "var_PRMSL": "on",
            "lev_mean_sea_level": "on",
        },
        grib_keys=("prmsl",),
        transform=lambda x: x / 100.0,  # Pa -> hPa
        encode_range=(940.0, 1060.0),
        palette=[
            (940.0,  (130, 50, 160)),
            (980.0,  (90, 110, 200)),
            (1000.0, (220, 220, 220)),
            (1020.0, (240, 180, 90)),
            (1060.0, (180, 60, 40)),
        ],
    ),
    Variable(
        name="cloud_cover",
        label="Total cloud cover",
        units="%",
        kind="scalar",
        nomads_params={
            "var_TCDC": "on",
            "lev_entire_atmosphere": "on",
        },
        grib_keys=("tcc",),
        encode_range=(0.0, 100.0),
        palette=[
            (0.0,   (10, 18, 32)),
            (20.0,  (60, 70, 90)),
            (50.0,  (140, 150, 170)),
            (80.0,  (220, 225, 235)),
            (100.0, (255, 255, 255)),
        ],
    ),
    Variable(
        name="pwat",
        label="Total precipitable water",
        units="kg/m²",
        kind="scalar",
        nomads_params={
            "var_PWAT": "on",
            "lev_entire_atmosphere_(considered_as_a_single_layer)": "on",
        },
        grib_keys=("pwat",),
        encode_range=(0.0, 75.0),
        palette=[
            (0.0,  (60, 30, 20)),
            (10.0, (180, 120, 60)),
            (25.0, (220, 200, 120)),
            (40.0, (130, 200, 200)),
            (55.0, (60, 130, 220)),
            (75.0, (30, 50, 160)),
        ],
    ),
    Variable(
        name="wind_250mb",
        label="250 hPa wind (jet stream)",
        units="m/s",
        kind="vector",
        nomads_params={
            "var_UGRD": "on",
            "var_VGRD": "on",
            "lev_250_mb": "on",
        },
        grib_keys=("u", "v"),
        encode_range=(-150.0, 150.0),
    ),
]


def by_name(name: str) -> Variable:
    for v in VARIABLES:
        if v.name == name:
            return v
    raise KeyError(name)
