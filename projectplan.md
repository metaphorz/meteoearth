# meteoearth — project plan

## Goal
Build a nullschool.net-style interactive globe showing live NOAA GFS data, in
`/Users/paul/code/weather/meteoearth/`. User can drag to rotate, scroll to zoom,
see animated wind particles, and switch between overlays (temperature, RH,
pressure).

## Architecture (decided)
- **Frontend**: static HTML/JS. deck.gl `GlobeView` + WeatherLayers GL community
  edition. Vanilla ES modules from CDN — no bundler in the MVP.
- **Pipeline**: Python (venv) script. Downloads latest GFS run from NOAA NOMADS,
  decodes selected variables with `xarray + cfgrib`, encodes each as a PNG
  (u→R, v→G channels for vectors; single-channel for scalars) plus a metadata
  JSON describing bounds and value ranges.
- **Refresh**: manual `./refresh-data.sh` for now. (cron later.)
- **Data scope (MVP)**: 0.5° GFS, analysis hour (f000), global. Variables:
  - 10 m wind u/v (vector, MVP)
  - 2 m temperature (scalar overlay, phase 3)
  - 2 m relative humidity (scalar overlay, phase 3)
  - mean sea-level pressure (scalar overlay, phase 3)

## Project layout
```
meteoearth/
├── projectplan.md
├── refresh-data.sh           # one-shot pipeline driver
├── start                     # launch local dev server
├── stop                      # kill dev server
├── frontend/
│   ├── index.html            # globe + UI
│   └── src/main.js           # deck.gl + WeatherLayers wiring
├── pipeline/
│   ├── requirements.txt
│   ├── fetch_gfs.py          # latest run discovery + GRIB download
│   ├── decode.py             # GRIB → numpy via cfgrib
│   └── encode.py             # numpy → PNG + metadata JSON
├── data/                     # pipeline output (consumed by frontend)
└── tests/
    └── auto/
```

## Phase 1 — Pipeline (Python) — MVP
- [x] 1.1 Create `venv/`, write `pipeline/requirements.txt`
      (`xarray`, `cfgrib`, `eccodes`, `numpy`, `pillow`, `requests`)
- [x] 1.2 `fetch_gfs.py`: discover latest available GFS run (00/06/12/18 UTC,
      with publication-lag awareness), download a single GRIB2 subset for
      10 m UGRD + VGRD at f000, 0.5° resolution, via NOMADS
      `filter_gfs_0p50.pl`. Save under `data/raw/`.
- [x] 1.3 `decode.py`: open the GRIB2 with `cfgrib`, return u, v numpy arrays
      plus lat/lon vectors and run timestamp.
- [x] 1.4 `encode.py`: linearly map u and v to 0-255 with a known min/max,
      write `data/wind_10m.png` (R = u-byte, G = v-byte) and
      `data/wind_10m.json` (`{run, valid_time, bounds, uMin, uMax, vMin, vMax,
       width, height}`).
- [x] 1.5 `refresh-data.sh`: activate venv, run fetch → decode → encode.
- [x] 1.6 Run the script end-to-end. Verify PNG is 720×361 (0.5° global) and
      JSON metadata looks plausible.

## Phase 2 — Frontend (static globe + wind) — MVP
- [x] 2.1 `index.html`: minimal page, full-window canvas, UMD bundles for
      deck.gl + weatherlayers-gl from unpkg (matches the official globe demo
      pattern — ESM via esm.sh hit luma.gl version conflicts).
- [x] 2.2 `src/main.js`: instantiate deck.gl `Deck` with `_GlobeView`,
      enable orbit controller (drag rotate, scroll zoom).
- [x] 2.3 Add a coastlines basemap layer (`GeoJsonLayer` reading
      Natural Earth 1:110m land via raw GitHub).
- [x] 2.4 Wire `ParticleLayer` to `data/wind_10m.png` +
      `wind_10m.json`. Required: `imageType: 'VECTOR'`, `imageUnscale`,
      `animate: true`, `getPolygonOffset` for globe depth handling.
- [x] 2.5 `start` / `stop` scripts on port 5862 (unique). `start` kills any
      pre-existing process holding the port before launching.
- [x] 2.6 Selenium harness in `tests/auto/test_ui.py` verifies: canvas
      appears, status text shows GFS run, drag-to-rotate changes viewport
      state, no console errors. Snapshots saved to `tests/auto/`.

## Phase 3 — Scalar overlays + click-to-query
- [x] 3.1 New `pipeline/variables.py` registry. `fetch_gfs.py` now pulls
      wind + TMP at 2 m + RH at 2 m + MSLP, one GRIB2 subset per variable.
- [x] 3.2 `encode.py` handles vector and scalar uniformly. Per-variable
      `<name>.png` + `<name>.json` (with `imageType`, `imageUnscale`, palette).
- [x] 3.3 `refresh-data.sh` drives all four variables and lists outputs.
- [x] 3.4 Overlay picker (none / temp / RH / MSLP) above the slider panel.
- [x] 3.5 `RasterLayer` rendering the selected scalar with a per-variable
      gradient palette (defined in `variables.py` and shipped in metadata).
- [x] 3.6 Hover readout: small near-cursor badge with lat/lon + wind
      (speed, compass + degrees, meteorological "from" convention) +
      temp + RH + MSLP, sampled by reading the in-memory PNG bytes and
      unscaling via `imageUnscale`.
- [x] 3.7 Right-click pin: sticky bottom-right panel + globe marker.
      Esc or × button clears the pin. Browser context menu suppressed.
- [x] 3.8 Selenium test exercises overlay switching, hover, and right-click
      pin. Snapshots saved to `tests/auto/`.

## Phase 3.5 — Additional variables
- [x] 3.5.1 Total cloud cover (TCDC) at entire atmosphere — added with
      grayscale palette, looks like a satellite IR view.
- [x] 3.5.2 Total precipitable water (PWAT) at entire-atmosphere column —
      atmospheric rivers visible.
- [x] 3.5.3 250 hPa wind (jet stream) as a second wind variable. New "wind
      level" toggle in the controls (10 m vs 250 hPa). The active level
      drives both the particle layer and the readout label.
- [x] 3.5.4 Selenium test extended to click the new overlay buttons and
      switch the wind level.

## Phase 4 — Polish
- [x] 4.1 GFS run timestamp displayed top-left as the status line.
- [x] 4.2 Colorbar legend top-right. Built from the active overlay's palette
      (gradient + tick labels at each palette stop). Hidden when overlay is
      "none". Selenium asserts visibility tracks the overlay choice.
- [x] 4.3 Smoke test: refresh data, Selenium re-runs all checks, snapshots
      saved.

## Phase 5 — Automated refresh via GitHub Actions (DONE)
- [x] 5.1 Initialise git repo, push to GitHub
      (`https://github.com/metaphorz/meteoearth`).
- [x] 5.2 Workflow `.github/workflows/deploy.yml`: 6 h cron (+ push +
      manual dispatch) refreshes the GFS data in CI (micromamba/conda-forge
      eccodes) and deploys the static globe to Pages as an artifact — data is
      built fresh each run, never committed back. Root redirect → the globe.
- [x] 5.3 Served from GitHub Pages (Actions source) at
      `https://metaphorz.github.io/meteoearth/`. First run green: build 42 s,
      deploy 9 s; live data confirmed. Auto-refreshes every 6 h — no more
      manual `./refresh-data.sh`.

## How the user will run it
After Phase 1 + 2 land:
1. `./refresh-data.sh` — pulls latest GFS, writes data files (~30 s)
2. `./start` — launches local server, prints URL
3. open the printed URL in a browser
4. `./stop` to shut down when done

## Phase 6 — H/L pressure-center overlay
Goal: show a large **L** at low-pressure centers and **H** at high-pressure
centers (the eyes of the vortices), with hover details. Reuses the existing
`mslp` data and the purpose-built `WeatherLayers.HighLowLayer` (already in the
loaded UMD bundle) — no new pipeline work, no custom extrema math.

- [x] 6.1 `buildLayers`: add a `WeatherLayers.HighLowLayer` (id `highlow`) fed by
      `data.mslp` (`image`, `imageType: "SCALAR"`, `imageUnscale`, `bounds`).
      - `radius` ≈ 1500 km so only the major synoptic systems show (the "large"
        L/H), not every tiny ripple.
      - Conventional colors: blue **L**, red **H** (palette keyed on pressure
        value, split near 1013 hPa), white outline for legibility.
      - `pickable: true`, sits above the wind layer.
      - Gated on a new `settings.highLow` boolean (default on).
- [x] 6.2 `index.html`: add an "H/L centers" toggle button to the controls
      (independent of the mutually-exclusive overlay buttons, since markers
      ride on top of any overlay). Wire it like the other toggles → `rebuild()`.
- [x] 6.3 Hover details: in `onDeckHover`, when the picked object is from the
      `highlow` layer, show a richer badge from `info.object.properties`
      (type L/H → "Low/High-pressure system"), `properties.value`
      (central pressure, hPa), and `geometry.coordinates` (lat/lon).
- [x] 6.4 Test in browser (Selenium → screenshot) that L/H glyphs land on the
      vortex centers and that hovering a glyph shows the detail badge.
      (`tests/auto/test_highlow.py` — PASS.)

## Phase 7 — LaTeX manual (docs/)
Match the `~/code/*/docs/` convention (e.g. nodez, mechanix): a `docs/manual.tex`
article with a `figures/` subdir, figures captured via Selenium, compiled to
`docs/manual.pdf`.
- [x] 7.1 `docs/capture_figures.py`: Selenium driver that loads the app and
      saves crisp full-window PNGs of key states to `docs/figures/`
      (overview, H/L overlay, H/L hover, temp, PWAT, cloud, jet, pin).
- [x] 7.2 `docs/manual.tex`: user+developer manual, figures referenced before
      they appear, `\author{Paul Fishwick and Claude Code}`.
- [x] 7.3 `docs/build.sh`: capture figures + run pdflatex twice → `manual.pdf`.
- [x] 7.4 Build the PDF and verify it compiles with all figures embedded.

## Review

### Phase 6 — H/L pressure-center overlay (done)
Added a large blue **L** / red **H** glyph at each pressure center, riding on
top of any overlay, with hover details — built on the existing `mslp` field.

Changes (small, localized):
- `frontend/src/main.js`
  - `HIGHLOW_PALETTE` constant (blue lows / red highs, split at ~1013 hPa).
  - `settings.highLow = true` (on by default, per request).
  - `buildLayers`: a `WeatherLayers.HighLowLayer` fed by `data.mslp`
    (`radius: 1500` km → major synoptic centers), pickable, above the wind.
  - `onDeckHover`: when the picked object is an H/L feature, show a detail
    badge ("Low/High-pressure system · central hPa · lat/lon").
  - `wireToggleButtons`: generic on/off wiring for `data-toggle` buttons.
- `frontend/index.html`: "H/L centers" toggle button in the controls.
- `tests/auto/test_highlow.py`: Selenium verification — confirms 95 lows /
  100 highs detected, glyph hover badge, toggle off removes the layer, and
  the normal point readout still carries the MSLP row. All checks PASS.

Notes:
- The glyphs also show the central pressure value beneath the letter (the
  library's default), which matches the nullschool convention.
- Pressure was already in the point-hover readout (`MSLP` row) — no change
  needed for that ask.
- `radius` is a separation distance, not a prominence filter, so a few weak
  tropical highs (e.g. "H 1015") appear. Raise `radius` if you want fewer.

---

# Ventusky-comparison roadmap (PROPOSED — awaiting verification)

Source: looked closely at ventusky.com (Selenium capture in
`tests/auto/ventusky-01-default.png` + `ventusky-text.txt`). Two gaps vs.
meteoearth stood out: (1) Ventusky is a **forecast** (time scrubber + history),
meteoearth shows one analysis frame; (2) Ventusky plots **~14 layers**,
meteoearth has 7. The phases below close those gaps, smallest-change-first.

## Phase 8 — Forecast time dimension (highest value)
Turn the single f000 snapshot into a scrubbable forecast. GFS already publishes
the steps; this is the headline difference.

Design decisions to confirm:
- **Horizon & cadence**: default **f000 → f048, every 3 h = 17 steps**.
  (To f120 every 3h = 41 steps if you want longer range — costs more data.)
- **Data layout**: filename suffix per step, `data/<var>.f###.png` + `.json`,
  with `index.json` gaining a `times: [{fhr, valid_time}, …]` array. Keeps the
  flat `data/` dir; no per-var schema change.
- **Loading**: lazy-load per timestep on demand (don't fetch all 17×7 PNGs up
  front — that's ~23 MB). Cache decoded textures as the user scrubs.

Tasks:
- [x] 8.1 `fetch_gfs.py`: accept a list of forecast hours; download each
      (var, fhr) to `data/raw/<var>.f###.grib2`; record `forecast_hours` in
      `run.json`. Keep all-or-nothing per cycle.
- [x] 8.2 `encode.py`: loop forecast hours, emit `data/<var>.f###.png/.json`;
      write `times[]` into `index.json`.
- [x] 8.3 `frontend/src/main.js`: lazy per-step texture loader keyed by fhr;
      swap layer `image`s on step change.
- [x] 8.4 `index.html` + main.js: time slider + Play/Prev/Next + valid-time
      label (mirrors Ventusky's bottom bar).
- [x] 8.5 Selenium test: scrub to a future step, assert overlay/wind/H-L and
      the point readout all update; assert the valid-time label advances.

Phase 8 DONE — `tests/auto/test_timebar.py` 7/7. Pipeline now fetches 17 steps
(f000–f048/3h), encodes `<var>.f###.png/.json` + `times[]` in index.json;
frontend lazy-loads/caches per step with a centered time bar (‹ ▶ › + slider +
"Tue, Jun 30, 2:00 PM (+48 h)" label). Fix: `grib_filter` (stepType=instant) on
`Variable` so cloud cover decodes at forecast hours.

## Phase 9 — Additional data layers (low-risk, additive)
Each new variable = one `variables.py` entry + one overlay button + one
`fmtRow` line. No architecture change. GFS-available, globe-appropriate:
- [x] 9.1 **Wind gusts** (`GUST`, surface) — scalar overlay.
- [x] 9.2 **Precipitation rate** (`PRATE`) — instantaneous, works at f000;
      true accumulated precip (`APCP`) needs Phase 8 (it's a step accumulation).
- [x] 9.3 **CAPE** (`CAPE`) — thunderstorm-potential proxy (Ventusky's
      "Thunderstorms").
- [ ] 9.4 (deferred, user choice) **SST / snow depth** — low value in summer.
- [ ] 9.5 (deferred) "Feels like" — derivable from tmp+rh+wind, no download.
- Out of scope for GFS: Radar, Satellite, Air quality, Webcams (separate data
  providers, not in GFS) — see Phase 10 on Ventusky's mixed sourcing.

Phase 9 DONE — added `gust`, `prate` (→mm/h), `cape` to `variables.py`; refresh
now ingests 10 vars × 17 steps (170 files). Frontend: overlay buttons
gust/precip/CAPE + readout rows. `tests/auto/test_layers.py` 10/10; timebar 7/7
and highlow tests still green (no regressions).

## Controls panel redesign (user request)
With 9 overlay buttons the lower-left panel had grown wide and overlapped the
globe. Changes (CSS + small markup, `index.html`; toggle in `main.js`):
- Each control group stacks its label over a wrapping `.btns` grid; panel
  capped at ~230px so buttons flow into rows instead of one long line.
- Added a `controls` header with a − / + **minimize** button that collapses to
  a small "controls +" chip and restores on click (`wireControlsToggle`).
- **Hover tooltips** (`title` attributes) on every overlay/wind/pressure button,
  each slider row, and the time slider, explaining what each control does.

## Phase 10 — Alternate models / sources (optional; global-only fit)
Re: the regional models in Ventusky's list — meteoearth renders a **whole
globe**, so regional/limited-area models (HRRR-USA, NAM, ICON-EU, HARMONIE,
AROME-FR, ICON-DE/CH, MEPS-NO, NAM-Hawaii, HARMONIE-CAR) only paint a patch and
would leave most of the sphere blank — poor fit unless we add a zoomed regional
mode. The **global** models are the ones worth a selector:
Current source = **NOAA GFS** (agency NOAA → center NCEP → model GFS), fetched
via the **NOMADS** GRIB-subset filter endpoint. Phase 10 generalizes the
pipeline to multiple global sources behind a model selector.

### Source survey (researched 2026-06)
| Source | Grid / format | Access | Fit |
|---|---|---|---|
| **GFS** (NOAA, current) | 0.5° lat-lon GRIB2, server-side var subset | NOMADS filter URL | baseline |
| **ECMWF IFS open data** | 0.25° lat-lon GRIB2 | `ecmwf-opendata` pip client | clean — best 2nd model |
| **GEM / GDPS** (ECCC, Canada) | 0.15° lat-lon GRIB2, per-var-per-step files | HTTP GET (Datamart) | manageable |
| **ICON global** (DWD) | **icosahedral** grid, per-var `.grib2.bz2`, no subset | HTTP GET (opendata.dwd.de) | hard — needs regridding to lat-lon + bz2 + big files |

**Variable coverage is NOT identical across models.** GFS gives all 10 of our
fields; ECMWF open data exposes a different subset (2t, msl, 10u/10v, tp
accumulated, tcwv≈PWAT, cape, gust, pressure-level u/v — but no native 2 m RH or
instantaneous precip rate). So the selector must treat each model's variable
list as its own manifest and grey out / hide overlays a model doesn't provide.

### Architecture
- [x] 10.0 Refactored `variables.py` → canonical registry; `sources.py` holds
      per-source adapters (fetch + decode), `decode.py` generic, `build.py`
      orchestrates, `encode.py` exposes `encode_field`.
- [x] 10.0b Data layout `data/<model>/<var>.f###.png/.json`; `index.json` =
      `{sources:[{id,label,resolution_deg,run_time,variables[],times[]}], default}`.
- [x] 10.1 **ECMWF IFS open data** adapter via `ecmwf-opendata`, 0.25°.
- [x] 10.2 **GEM / GDPS** adapter (ECCC, 0.15°) via the MSC hpfx file server.
- [x] 10.3 Model-selector UI; switching reloads the model's path and greys out
      overlays it doesn't provide (per-model variable manifest).
- [x] 10.4 `tests/auto/test_models.py` — 20/20 (switch model, run-time updates,
      unavailable overlays disabled, readouts work).
- (Deferred) Regional high-res models — only with a zoomed regional viewport.

Phase 10 DONE — three global models behind a selector. Coverage built:
GFS = all 10 vars; ECMWF = wind_10m/wind_250mb/tmp_2m/mslp/cloud/pwat/gust;
GEM = wind_10m/wind_250mb/tmp_2m/rh_2m/mslp/cloud/gust/cape. Network notes:
added `get_grib` retry (transient ECMWF/GEM timeouts); ECMWF lacks plain
cape/rh/instantaneous-precip, GEM lacks pwat/instantaneous-precip — handled by
greying out. CI: `.github/workflows/deploy.yml` updated to `build.py` + per-model
copy + `ecmwf-opendata` install + 30-min timeout (data still ships as the Pages
artifact, so no git-history bloat).

Note on Ventusky's sources: Ventusky does pull from **many providers**, not one
— numerical models from NOAA (GFS/NAM/HRRR/NBM), ECMWF, DWD (ICON), Météo-France
(AROME/Aladin), ECCC (GEM), the Met Office (UKMO), MET Norway (MEPS), plus
**non-model** layers from other sources: radar mosaics, satellite imagery, air
quality (e.g. CAMS), and user-contributed webcams. meteoearth today is
single-source (NOAA GFS via NOMADS). Matching radar/satellite/AQ means wiring up
those separate feeds, not just more GFS variables.

---

# Phase 11 — Add DWD ICON (4th global model) + Icelandic-Low validation

Motivation: Ventusky offers ICON, GEM, ECMWF, GFS as global models; we had the
last three. User also flagged our H/L overlay placing the **Icelandic Low**
poorly vs. reference software (Windy/Ventusky 2026-07-01 showed an Icelandic Low
~995.6 hPa / 29.4 inHg between Greenland and Iceland, plus a 2nd low to the SE;
GFS and ICON "practically identical" in the reference).

ICON global is on an **icosahedral** grid (~2.95M cells), not a lat-lon raster —
the item Phase 10 deferred as "hard." Solved with a dependency-light regrid:
fetch the time-invariant CLAT/CLON cell-center coords once per cycle, build a 3D
unit-vector KD-tree (scipy), nearest-neighbor onto our standard 0.25° grid. The
mapping is identical for every var/step, so it's built once and reused.

- [x] 11.0 Verified DWD open-data layout + CLAT/CLON availability; chose
      nearest-neighbor (scipy KDTree) over CDO (user decision).
- [x] 11.1 `icon_regrid_probe.py`: proved the regrid — ICON MSLP minimum in the
      N-Atlantic box = **995.5 hPa at 64.5°N, 34°W**, matching the reference
      Icelandic Low (995.6 hPa) almost exactly.
- [x] 11.2 `sources.py`: `ICONSource` (bz2 fetch, KD-tree regrid, decode) +
      registered in `SOURCES`; `scipy` added to `requirements.txt`.
- [x] 11.3 Full local build: 8 vars × 17 steps. ICON provides wind_10m,
      wind_250mb, tmp_2m, rh_2m, mslp, cloud_cover, pwat, cape. Not provided:
      `gust` (VMAX_10M is a max-over-interval, 404 at f000) and `prate` (no
      instantaneous rate) — greyed out per the existing per-model manifest.
- [x] 11.4 `index.json` now lists gfs/ecmwf/gem/**icon**; frontend model
      selector is data-driven, so ICON appears with no frontend code change.
- [x] 11.5 CI `deploy.yml`: added `scipy` to the micromamba env so the 12h
      deploy rebuilds all **4** models.
- [x] 11.6 In-browser verification (`compare_icelandic_low.py`, matched 12Z
      cycle): all 4 model buttons render; ICON greys out gust/precip. The
      Icelandic-Low **L** lands between Greenland and Iceland for both models —
      GFS 994.8 hPa @ 65.1N/33.5W, ICON 995.4 hPa @ 64.5N/34.0W — matching the
      reference 995.6 hPa. Screenshots: `tests/auto/icelandic-{gfs,icon}.png`.
- [x] 11.7 No detection/radius tuning needed — the original "poor Icelandic-Low
      location" was **stale local data** (a June-28 cycle); a fresh cycle places
      the L correctly for every model.
- [x] 11.8 CI `timeout-minutes` 30 → 45 (4 models fetch in ~20-25 min).

## Phase 12 — H/L glyph color-by-type + strength opacity (user request)
The `HighLowLayer` colored the L/H letters by *raw pressure value* (blue < 1013,
red > 1013), so a weak low with a central pressure above 1013 hPa rendered as a
**red L** — wrong. User also wanted dominant systems emphasized.
- [x] 12.1 Color by **type** (blue L, red H), not value — fixes the red-L. The
      library's `getColor` is hardcoded to the value palette, so override the two
      inner text sublayers ("type"/"value") via nested `_subLayerProps` (through
      the "composite" wrapper) with a per-feature color keyed on `properties.type`.
- [x] 12.2 **Opacity by strength**: alpha scales with |value − 1013| — deep lows
      / strong highs solid, weak centers near 1013 hPa fade to ~alpha 70. Softened
      the text outline to alpha 200.
- [x] 12.3 Verified in-browser (`highlow_opacity_check.py`): all L blue / all H
      red, prominence tracks strength, no console errors. `highlow-opacity.png`.

### Review — Phases 11 & 12
- **ICON added** as the 4th global model (`pipeline/sources.py::ICONSource`):
  bz2 fetch from opendata.dwd.de, a one-time CLAT/CLON KD-tree (3D unit vectors,
  scipy) nearest-neighbor regrid of the icosahedral grid (~2.95M cells) onto our
  0.25° raster, reused for every var/step. `scipy` added to `requirements.txt`
  and the CI env; CI now rebuilds 4 models each 12h (timeout 45 min). No frontend
  change — the model selector is data-driven off `index.json` (ICON = 8 vars;
  gust/precip greyed).
- **Icelandic Low** was never a bug: with a fresh cycle the L sits correctly
  between Greenland and Iceland for GFS and ICON (near-identical), matching the
  Windy/Ventusky reference.
- **H/L glyphs** now color by type (blue L / red H) with opacity by strength
  (`frontend/src/main.js`), fixing red-Ls and emphasizing dominant systems.
- Diagnostics in `tests/auto/`: `icon_regrid_probe.py`,
  `compare_icelandic_low.py`, `highlow_opacity_check.py`.

## Phase 13 — Name climatological systems in the H/L hover tooltip
- [x] 13.1 `frontend/src/main.js`: `NAMED_SYSTEMS` table (climatological "centers
      of action") + `namedSystem(type, lat, lng)` lookup (inclusive lat/lng boxes;
      an lng box with min>max wraps the ±180° seam, e.g. the Aleutian Low). Covers
      Icelandic/Aleutian/Southern-Ocean/monsoon/heat lows and Azores–Bermuda /
      N-Pacific / Siberian / Greenland / S-Atlantic / S-Pacific / Mascarene highs.
- [x] 13.2 The H/L hover badge prepends the system name when the glyph falls in a
      named region. Verified with `tests/auto/verify_named_tooltip.py` (PASS —
      badge reads "Icelandic Low").
- [x] 13.3 The Southern Ocean is a circumpolar trough (a belt of 3–6 cyclones),
      so a single "Southern Ocean Low" label repeated across many centers. Split
      into four longitude sectors that tile the full 360°: **Amundsen Sea Low**
      (the recognized semi-permanent center), **Weddell Sea Low**, **South Indian
      Ocean Low**, **Ross Sea Low** (wraps the dateline). Sector logic checked in
      node against sample coords.

## Phase 14 — Fix GEM upside-down bug (latitude orientation)
Cross-checking the Icelandic Low across models exposed a real bug: GEM placed a
phantom **966 hPa** low SE of Iceland while GFS/ICON/ECMWF agreed on ~995 hPa at
34°W. Root cause: **GEM/GDPS publishes latitude ascending (−90→+90)** whereas
GFS/ECMWF/ICON are descending (+90→−90). `encode.py` maps image row 0 to +90°,
so the entire GEM globe (every variable) rendered **vertically flipped** — the
real 65°N low mirrored to 65°S, and a deep Southern-Ocean winter low (~966 hPa)
mirrored up to appear "SE of Iceland."
- [x] 14.1 `decode.py`: normalize any ascending-lat source to north-at-top (flip
      arrays + reverse lat). No-op for GFS/ECMWF (already descending); ICON has
      its own descending grid.
- [x] 14.2 Verified: GEM MSLP now reads 995.1 hPa @ 65.7°N/32.7°W, matching
      GFS/ICON and Ventusky (Icelandic Low + the low W of N. Scotland agree
      across all 4 models). Rebuilt the full GEM dataset (all vars were flipped).
