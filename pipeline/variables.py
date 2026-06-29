"""Canonical variable registry — the source-independent view of what the
frontend can display.

Each canonical variable carries only presentation/encoding metadata:
  - display label, units, kind ("vector" | "scalar")
  - the encode range used for byte-packing the PNG
  - an optional unit transform from raw GRIB units to display units
    (these are the same across GFS/ECMWF/GEM because all ship SI GRIB)
  - palette stops for the legend/overlay

How each *source* fetches and decodes a canonical variable lives in
`sources.py`; not every source provides every canonical variable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Variable:
    name: str                          # canonical stem, e.g. "wind_10m"
    label: str                         # human label
    units: str                         # display units
    kind: str                          # "vector" | "scalar"
    encode_range: tuple[float, float]  # [vMin, vMax] used for byte packing
    transform: Optional[Callable] = None  # raw GRIB units -> display units
    palette: list[tuple[float, tuple[int, int, int]]] = field(default_factory=list)


VARIABLES: list[Variable] = [
    Variable(
        name="wind_10m",
        label="10 m wind",
        units="m/s",
        kind="vector",
        encode_range=(-50.0, 50.0),
    ),
    Variable(
        name="wind_250mb",
        label="250 hPa wind (jet stream)",
        units="m/s",
        kind="vector",
        encode_range=(-150.0, 150.0),
    ),
    Variable(
        name="tmp_2m",
        label="2 m temperature",
        units="°C",
        kind="scalar",
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
        name="gust",
        label="Wind gusts",
        units="m/s",
        kind="scalar",
        encode_range=(0.0, 50.0),
        palette=[
            (0.0,  (20, 30, 50)),
            (10.0, (60, 130, 180)),
            (20.0, (120, 200, 120)),
            (30.0, (240, 200, 60)),
            (40.0, (240, 110, 40)),
            (50.0, (180, 0, 30)),
        ],
    ),
    Variable(
        name="prate",
        label="Precipitation rate",
        units="mm/h",
        kind="scalar",
        transform=lambda x: x * 3600.0,  # kg/m²/s -> mm/h
        encode_range=(0.0, 25.0),
        palette=[
            (0.0,  (10, 18, 32)),
            (0.5,  (70, 120, 200)),
            (2.0,  (60, 180, 200)),
            (6.0,  (120, 220, 120)),
            (12.0, (240, 220, 80)),
            (25.0, (220, 60, 60)),
        ],
    ),
    Variable(
        name="cape",
        label="CAPE (thunderstorm potential)",
        units="J/kg",
        kind="scalar",
        encode_range=(0.0, 5000.0),
        palette=[
            (0.0,    (12, 18, 30)),
            (500.0,  (60, 110, 160)),
            (1000.0, (110, 200, 140)),
            (2000.0, (240, 210, 80)),
            (3000.0, (240, 120, 50)),
            (5000.0, (170, 0, 60)),
        ],
    ),
]


def by_name(name: str) -> Variable:
    for v in VARIABLES:
        if v.name == name:
            return v
    raise KeyError(name)
