"""Build per-source data products the frontend reads.

For each requested source: discover its latest cycle, then for every canonical
variable the source supports and every forecast hour, download the raw GRIB,
decode it, and encode <var>.f###.png/.json under data/<source>/. Finally write
data/index.json listing every source present in data/.

    venv/bin/python pipeline/build.py            # all sources
    venv/bin/python pipeline/build.py gfs ecmwf  # selected sources
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from encode import encode_field
from sources import SOURCES, make_source
from variables import by_name

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"


def resolve_cycle(src):
    if hasattr(src, "latest_cycle"):
        return src.latest_cycle()
    for c in src.candidate_cycles():
        if src.cycle_available(c):
            return c
    raise RuntimeError(f"{src.id}: no recent cycle available")


def build_source(sid: str) -> dict | None:
    src = make_source(sid)
    cycle = resolve_cycle(src)
    print(f"[{sid}] cycle {cycle.isoformat()}  ({src.label} {src.resolution_deg}°)", flush=True)

    out_dir = DATA / sid
    raw_dir = RAW / sid
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if raw_dir.exists():
        shutil.rmtree(raw_dir)

    times: dict[int, str] = {}
    ok_vars: list = []
    run_time = None

    for canon in src.supported():
        var = by_name(canon)
        try:
            for fhr in src.forecast_hours:
                src.fetch(canon, cycle, fhr, raw_dir)
                field = src.decode(canon, fhr, raw_dir, var.transform, var.kind)
                meta = encode_field(field, var, out_dir / f"{canon}.f{fhr:03d}")
                run_time = run_time or meta["run_time"]
                times.setdefault(fhr, meta["valid_time"])
            ok_vars.append(var)
            print(f"[{sid}]   {canon:12s} ok ({len(src.forecast_hours)} steps)", flush=True)
        except Exception as e:  # noqa: BLE001 — drop a var that fails, keep the rest
            print(f"[{sid}]   {canon:12s} SKIPPED: {repr(e)[:120]}", flush=True)

    if not ok_vars:
        print(f"[{sid}] no variables built", file=sys.stderr)
        return None

    manifest = {
        "id": sid,
        "label": src.label,
        "resolution_deg": src.resolution_deg,
        "run_time": run_time,
        "variables": [{"name": v.name, "label": v.label, "kind": v.kind} for v in ok_vars],
        "times": [{"forecast_hour": f, "valid_time": times[f]} for f in sorted(times)],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def write_index() -> None:
    """Assemble data/index.json from whatever per-source manifests exist."""
    manifests = []
    for sid in SOURCES:                       # stable order: gfs, ecmwf, gem
        mf = DATA / sid / "manifest.json"
        if mf.exists():
            manifests.append(json.loads(mf.read_text()))
    default = "gfs" if any(m["id"] == "gfs" for m in manifests) else (
        manifests[0]["id"] if manifests else None)
    (DATA / "index.json").write_text(json.dumps(
        {"sources": manifests, "default": default}, indent=2))


def main(argv: list[str]) -> int:
    ids = argv or list(SOURCES)
    for sid in ids:
        if sid not in SOURCES:
            print(f"unknown source {sid!r}; choices: {list(SOURCES)}", file=sys.stderr)
            return 2
    for sid in ids:
        try:
            build_source(sid)
        except Exception as e:  # noqa: BLE001
            print(f"[{sid}] FAILED: {repr(e)[:160]}", file=sys.stderr)
    write_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
