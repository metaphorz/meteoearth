"""Generic GRIB2 → numpy decoding, shared by every source.

A canonical variable maps to one or two (file, cfgrib-key) pairs:
  - scalar  → one pair
  - vector  → two pairs (u, v), which may live in one file (GFS/ECMWF) or in
    two separate files (GEM publishes WindU / WindV as distinct files).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import xarray as xr


@dataclass
class DecodedField:
    kind: str                 # "vector" | "scalar"
    arrays: list[np.ndarray]  # length 1 (scalar) or 2 (vector u, v)
    lat: np.ndarray
    lon: np.ndarray
    run_time: str
    valid_time: str


def _open(path: Path, grib_filter: dict) -> xr.Dataset:
    return xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"indexpath": "", "filter_by_keys": grib_filter},
    )


def decode_grib(
    pairs: list[tuple[Path, str]],
    kind: str,
    transform: Optional[Callable],
    grib_filter: dict,
) -> DecodedField:
    """pairs: [(grib_path, cfgrib_var_key), ...] — 1 for scalar, 2 for vector."""
    arrays: list[np.ndarray] = []
    lat = lon = None
    run_time = valid_time = None
    for path, key in pairs:
        ds = _open(Path(path), grib_filter)
        if key is None:                       # take the sole data variable
            data_keys = list(ds.data_vars)
            if len(data_keys) != 1:
                raise ValueError(f"{path}: expected 1 data var, got {data_keys}")
            key = data_keys[0]
        a = ds[key].values.astype(np.float32)
        if transform is not None:
            a = transform(a)
        arrays.append(a)
        if lat is None:
            lat = ds["latitude"].values.astype(np.float32)
            lon = ds["longitude"].values.astype(np.float32)
            run_time = str(np.datetime_as_string(ds["time"].values, unit="s")) + "Z"
            valid_time = str(np.datetime_as_string(ds["valid_time"].values, unit="s")) + "Z"
    # Normalize to north-at-top (row 0 = +90°). encode.py maps image row 0 to
    # +90°, so a source that publishes latitude ascending (south-to-north, e.g.
    # GEM/GDPS) would otherwise render vertically flipped. No-op for GFS/ECMWF,
    # which are already descending.
    if lat is not None and lat[0] < lat[-1]:
        lat = lat[::-1]
        arrays = [a[::-1, :] for a in arrays]

    return DecodedField(
        kind=kind, arrays=arrays, lat=lat, lon=lon,
        run_time=run_time, valid_time=valid_time,
    )
