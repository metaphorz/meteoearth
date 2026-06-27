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

## Phase 5 — Automated refresh via GitHub Actions (future)
- [ ] 5.1 Initialise git repo, push to GitHub.
- [ ] 5.2 Workflow `.github/workflows/refresh.yml` on a 6 h cron that runs
      the pipeline and commits/pushes the regenerated `data/` files (or
      uploads them to a release / Pages artifact).
- [ ] 5.3 Serve the frontend from GitHub Pages so the site auto-updates
      whenever the workflow finishes.

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
