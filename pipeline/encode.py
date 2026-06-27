"""Encode each variable as a PNG plus a metadata JSON the frontend reads.

Vector variables (u, v):
  - PNG mode RGBA, R = u byte, G = v byte (B unused, A = 255)
  - imageType = "VECTOR"

Scalar variables:
  - PNG mode RGBA, R = value byte (G/B = R, A = 255)
  - imageType = "SCALAR"

Image origin is top-left = (-180, +90).  Longitude axis is rolled from the
GFS [0, 360) convention into [-180, 180].
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from decode import load
from variables import VARIABLES, Variable

OUT_DIR = Path(__file__).resolve().parents[1] / "data"


def to_byte(arr: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    scaled = (arr - vmin) / (vmax - vmin) * 255.0
    return np.clip(scaled, 0, 255).astype(np.uint8)


def roll_to_180(arr: np.ndarray) -> np.ndarray:
    """Roll the longitude (last) axis from [0, 360) to [-180, 180)."""
    return np.roll(arr, shift=arr.shape[-1] // 2, axis=-1)


def encode_variable(var: Variable) -> dict:
    d = load(var)
    vmin, vmax = var.encode_range
    rolled = [roll_to_180(a) for a in d.arrays]
    h, w = rolled[0].shape

    if var.kind == "vector":
        u_byte = to_byte(rolled[0], vmin, vmax)
        v_byte = to_byte(rolled[1], vmin, vmax)
        rgba = np.stack(
            [u_byte, v_byte, np.zeros_like(u_byte), np.full_like(u_byte, 255)],
            axis=-1,
        )
        image_type = "VECTOR"
    else:
        s_byte = to_byte(rolled[0], vmin, vmax)
        rgba = np.stack(
            [s_byte, s_byte, s_byte, np.full_like(s_byte, 255)],
            axis=-1,
        )
        image_type = "SCALAR"

    img = Image.fromarray(rgba, mode="RGBA")
    png_path = OUT_DIR / f"{var.name}.png"
    img.save(png_path, optimize=True)

    stats_arrays = {
        f"{var.grib_keys[i]}_min": float(d.arrays[i].min())
        for i in range(len(d.arrays))
    }
    stats_arrays.update({
        f"{var.grib_keys[i]}_max": float(d.arrays[i].max())
        for i in range(len(d.arrays))
    })

    meta = {
        "variable": var.name,
        "label": var.label,
        "units": var.units,
        "kind": var.kind,
        "imageType": image_type,
        "imageUnscale": [vmin, vmax],
        "run_time": d.run_time,
        "valid_time": d.valid_time,
        "width": int(w),
        "height": int(h),
        "bounds": [-180.0, -90.0, 180.0, 90.0],
        "palette": [[v_, list(c)] for v_, c in var.palette],
        "stats": stats_arrays,
    }
    json_path = OUT_DIR / f"{var.name}.json"
    json_path.write_text(json.dumps(meta, indent=2))

    print(f"[encode] {var.name:10s} kind={var.kind:6s} "
          f"-> {png_path.name} ({png_path.stat().st_size/1024:.1f} KB) "
          f"{w}x{h}")
    return meta


def main() -> int:
    metas = []
    for v in VARIABLES:
        metas.append(encode_variable(v))
    # Index file the frontend can fetch to know what's available.
    (OUT_DIR / "index.json").write_text(json.dumps({
        "variables": [
            {"name": m["variable"], "label": m["label"], "kind": m["kind"]}
            for m in metas
        ],
        "run_time": metas[0]["run_time"] if metas else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
