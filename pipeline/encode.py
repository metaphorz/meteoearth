"""Encode a decoded field as a PNG plus a metadata JSON the frontend reads.

Vector: R = u byte, G = v byte (imageType VECTOR).
Scalar: R = value byte, G/B mirror R (imageType SCALAR).
Image origin top-left = (-180, +90); longitude rolled from [0,360) to [-180,180).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from decode import DecodedField
from variables import Variable


def to_byte(arr: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    arr = np.nan_to_num(arr, nan=vmin, posinf=vmax, neginf=vmin)  # fill gaps at vmin
    scaled = (arr - vmin) / (vmax - vmin) * 255.0
    return np.clip(scaled, 0, 255).astype(np.uint8)


def roll_to_180(arr: np.ndarray) -> np.ndarray:
    """Roll the longitude (last) axis from [0, 360) to [-180, 180)."""
    return np.roll(arr, shift=arr.shape[-1] // 2, axis=-1)


def encode_field(field: DecodedField, var: Variable, out_stem: Path) -> dict:
    """Write <out_stem>.png and <out_stem>.json; return the metadata dict."""
    vmin, vmax = var.encode_range
    rolled = [roll_to_180(a) for a in field.arrays]
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

    # NB: don't use with_suffix() — the stem ends in ".f###", which Path treats
    # as the extension. Append the real extensions instead.
    png_path = out_stem.parent / f"{out_stem.name}.png"
    json_path = out_stem.parent / f"{out_stem.name}.json"
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(png_path, optimize=True)

    meta = {
        "variable": var.name,
        "label": var.label,
        "units": var.units,
        "kind": var.kind,
        "imageType": image_type,
        "imageUnscale": [vmin, vmax],
        "run_time": field.run_time,
        "valid_time": field.valid_time,
        "width": int(w),
        "height": int(h),
        "bounds": [-180.0, -90.0, 180.0, 90.0],
        "palette": [[v_, list(c)] for v_, c in var.palette],
    }
    json_path.write_text(json.dumps(meta, indent=2))
    return meta
