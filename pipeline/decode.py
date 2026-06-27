"""Decode a per-variable GRIB2 subset into numpy arrays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr

from variables import Variable

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


@dataclass
class DecodedField:
    name: str
    kind: str                 # "vector" | "scalar"
    arrays: list[np.ndarray]  # length 1 (scalar) or 2 (vector u, v)
    lat: np.ndarray
    lon: np.ndarray
    run_time: str
    valid_time: str


def load(var: Variable) -> DecodedField:
    path = RAW_DIR / f"{var.name}.f000.grib2"
    ds = xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"indexpath": ""},
    )
    arrays: list[np.ndarray] = []
    for key in var.grib_keys:
        a = ds[key].values.astype(np.float32)
        if var.transform is not None:
            a = var.transform(a)
        arrays.append(a)

    lat = ds["latitude"].values.astype(np.float32)
    lon = ds["longitude"].values.astype(np.float32)
    run_time = str(np.datetime_as_string(ds["time"].values, unit="s")) + "Z"
    valid_time = str(np.datetime_as_string(ds["valid_time"].values, unit="s")) + "Z"

    return DecodedField(
        name=var.name, kind=var.kind, arrays=arrays,
        lat=lat, lon=lon, run_time=run_time, valid_time=valid_time,
    )


def main() -> int:
    from variables import VARIABLES
    for v in VARIABLES:
        d = load(v)
        a = d.arrays[0]
        print(f"[decode] {v.name:10s} kind={v.kind:6s} "
              f"shape={a.shape} dtype={a.dtype} "
              f"min={a.min():.2f} max={a.max():.2f} units={v.units}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
