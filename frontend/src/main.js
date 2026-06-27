// meteoearth: globe + wind particles + scalar overlays + hover/pin readout.
// Uses UMD globals from index.html: `deck`, `WeatherLayers`.

const DATA_DIR = "../data";
const VARIABLES = [
  "wind_10m", "wind_250mb",
  "tmp_2m", "rh_2m", "mslp", "cloud_cover", "pwat",
];
const LAND_GEOJSON =
  "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson";

// Pressure-center glyph colors: blue lows, red highs, switching near the
// 1013 hPa standard. Keyed on the central pressure value of each H/L feature.
const HIGHLOW_PALETTE = [
  [940,  [80, 150, 255]],
  [1012, [110, 170, 255]],
  [1014, [255, 130, 100]],
  [1060, [255, 70, 55]],
];

const status     = document.getElementById("status");
const badge      = document.getElementById("hover-badge");
const pinPanel   = document.getElementById("pin-panel");
const pinRows    = document.getElementById("pin-rows");
const pinTitle   = document.getElementById("pin-title");
const legendEl   = document.getElementById("legend");
const legendTitle= document.getElementById("legend-title");
const legendBar  = document.getElementById("legend-bar");
const legendTicks= document.getElementById("legend-ticks");

function setStatus(t) { status.textContent = t; }

async function loadAll() {
  const tasks = VARIABLES.map(async (name) => {
    const meta = await fetch(`${DATA_DIR}/${name}.json`).then((r) => r.json());
    const image = await WeatherLayers.loadTextureData(`${DATA_DIR}/${name}.png`);
    return [name, { meta, image }];
  });
  return Object.fromEntries(await Promise.all(tasks));
}

// ---------- value-at-lat-lon ----------

function sampleAt(entry, lat, lng) {
  const { meta, image } = entry;
  const [west, south, east, north] = meta.bounds;
  const w = image.width, h = image.height;
  let u = (lng - west) / (east - west);
  if (u < 0) u += 1; if (u >= 1) u -= 1;
  const v = (north - lat) / (north - south);
  if (v < 0 || v >= 1) return null;
  const px = Math.min(Math.max(Math.floor(u * w), 0), w - 1);
  const py = Math.min(Math.max(Math.floor(v * h), 0), h - 1);
  const idx = (py * w + px) * 4;
  const [vMin, vMax] = meta.imageUnscale;

  if (meta.kind === "vector") {
    const ub = image.data[idx];
    const vb = image.data[idx + 1];
    const uVal = (ub / 255) * (vMax - vMin) + vMin;
    const vVal = (vb / 255) * (vMax - vMin) + vMin;
    const speed = Math.hypot(uVal, vVal);
    // Meteorological "from" bearing: where the wind is coming from.
    const toBearing = (Math.atan2(uVal, vVal) * 180 / Math.PI + 360) % 360;
    const fromBearing = (toBearing + 180) % 360;
    return { speed, direction: fromBearing, u: uVal, v: vVal };
  }
  const r = image.data[idx];
  return { value: (r / 255) * (vMax - vMin) + vMin };
}

// ---------- formatting ----------

const COMPASS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                 "S","SSW","SW","WSW","W","WNW","NW","NNW"];

function compass(deg) {
  return COMPASS[Math.round(deg / 22.5) % 16];
}

function fmtRow(name, sample, windLevel) {
  if (!sample) return null;
  if (name === "wind_10m" || name === "wind_250mb") {
    if (name !== windLevel) return null;            // only show active wind layer
    const label = name === "wind_10m" ? "Wind 10m" : "Wind 250hPa";
    return [label,
      `${sample.speed.toFixed(1)} m/s ${compass(sample.direction)} (${sample.direction.toFixed(0)}°)`];
  }
  if (name === "tmp_2m")
    return ["Temp", `${sample.value.toFixed(1)} °C`];
  if (name === "rh_2m")
    return ["RH",   `${sample.value.toFixed(0)} %`];
  if (name === "mslp")
    return ["MSLP", `${sample.value.toFixed(0)} hPa`];
  if (name === "cloud_cover")
    return ["Cloud", `${sample.value.toFixed(0)} %`];
  if (name === "pwat")
    return ["PWAT", `${sample.value.toFixed(1)} kg/m²`];
  return null;
}

function sampleAll(data, lat, lng) {
  const out = {};
  for (const name of VARIABLES) out[name] = sampleAt(data[name], lat, lng);
  return out;
}

function formatBadge(samples, lat, lng, windLevel) {
  const lines = [
    `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ` +
    `${Math.abs(lng).toFixed(2)}° ${lng >= 0 ? "E" : "W"}`,
  ];
  for (const name of VARIABLES) {
    const row = fmtRow(name, samples[name], windLevel);
    if (row) lines.push(`${row[0].padEnd(8)} ${row[1]}`);
  }
  return lines.join("\n");
}

function fillPinPanel(samples, lat, lng, windLevel) {
  pinTitle.textContent =
    `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ` +
    `${Math.abs(lng).toFixed(2)}° ${lng >= 0 ? "E" : "W"}`;
  pinRows.replaceChildren();
  for (const name of VARIABLES) {
    const row = fmtRow(name, samples[name], windLevel);
    if (!row) continue;
    const el = document.createElement("div");
    el.className = "row";
    const k = document.createElement("span"); k.className = "k"; k.textContent = row[0];
    const v = document.createElement("span"); v.className = "v"; v.textContent = row[1];
    el.append(k, v);
    pinRows.append(el);
  }
}

// ---------- main ----------

async function main() {
  setStatus("fetching weather data…");
  const [data, land] = await Promise.all([
    loadAll(),
    fetch(LAND_GEOJSON).then((r) => r.json()),
  ]);

  setStatus("rendering…");

  const settings = {
    overlay: "none",
    windLevel: "wind_10m",
    highLow: true,
    maxAge: 40, speedFactor: 3, numParticles: 5000, width: 2,
  };
  const state = { pin: null };  // { lng, lat, samples }

  const deckgl = new deck.Deck({
    parent: document.getElementById("container"),
    views: new deck._GlobeView({ id: "globe", resolution: 5 }),
    initialViewState: { longitude: 0, latitude: 20, zoom: 2 },
    controller: true,
    layers: buildLayers(data, land, settings, state),
    onHover: (info) => onDeckHover(info, data, settings),
    onLoad: () => attachCanvasHandlers(deckgl, data, state, settings, rebuild),
  });

  function rebuild() {
    deckgl.setProps({ layers: buildLayers(data, land, settings, state) });
    if (state.pin) {
      fillPinPanel(state.pin.samples, state.pin.lat, state.pin.lng,
                   settings.windLevel);
    }
    updateLegend(settings.overlay !== "none" ? data[settings.overlay] : null);
  }

  wireSliders(settings, rebuild);
  wireOverlayButtons(settings, rebuild);
  wireWindButtons(settings, rebuild);
  wireToggleButtons(settings, rebuild);

  document.getElementById("pin-close").addEventListener("click", () => {
    state.pin = null;
    pinPanel.style.display = "none";
    rebuild();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && state.pin) {
      state.pin = null;
      pinPanel.style.display = "none";
      rebuild();
    }
  });

  setStatus(`GFS ${data.wind_10m.meta.run_time}`);
  window.deckgl = deckgl;
}

function attachCanvasHandlers(deckgl, data, state, settings, rebuild) {
  const canvas = deckgl.getCanvas();
  if (!canvas) return;
  canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());
  canvas.addEventListener("mousedown", (ev) => {
    if (ev.button !== 2) return;
    const coord = coordFromEvent(deckgl, ev);
    if (!coord) return;
    const [lng, lat] = coord;
    const samples = sampleAll(data, lat, lng);
    state.pin = { lng, lat, samples };
    fillPinPanel(samples, lat, lng, settings.windLevel);
    pinPanel.style.display = "block";
    rebuild();
  });
}

function coordFromEvent(deckgl, ev) {
  const rect = deckgl.getCanvas().getBoundingClientRect();
  const pixel = [ev.clientX - rect.left, ev.clientY - rect.top];
  const info = deckgl.pickObject({ x: pixel[0], y: pixel[1], radius: 0 });
  return info?.coordinate ?? null;
}

function onDeckHover(info, data, settings) {
  // Pressure-center glyph hover → show the system's type, central pressure
  // and location instead of the point readout.
  const hl = info?.object?.properties;
  if (hl && (hl.type === "L" || hl.type === "H")) {
    const [glng, glat] = info.object.geometry.coordinates;
    const kind = hl.type === "L" ? "Low-pressure system" : "High-pressure system";
    badge.textContent =
      `${kind}\n` +
      `Central pressure  ${Math.round(hl.value)} hPa\n` +
      `${Math.abs(glat).toFixed(1)}° ${glat >= 0 ? "N" : "S"}, ` +
      `${Math.abs(glng).toFixed(1)}° ${glng >= 0 ? "E" : "W"}`;
    badge.style.left = (info.x + 14) + "px";
    badge.style.top  = (info.y + 14) + "px";
    badge.style.display = "block";
    return;
  }

  if (!info?.coordinate) {
    badge.style.display = "none";
    return;
  }
  const [lng, lat] = info.coordinate;
  const samples = sampleAll(data, lat, lng);
  badge.textContent = formatBadge(samples, lat, lng, settings.windLevel);
  badge.style.left = (info.x + 14) + "px";
  badge.style.top  = (info.y + 14) + "px";
  badge.style.display = "block";
}

// ---------- layers ----------

function buildLayers(data, land, s, state) {
  const layers = [
    // Invisible pickable polygon covering the globe so hover/pick fire
    // everywhere on the visible sphere, not just over land.
    new deck.SolidPolygonLayer({
      id: "pick-globe",
      data: [{ polygon: [[-180, 90], [180, 90], [180, -90], [-180, -90]] }],
      getPolygon: (d) => d.polygon,
      filled: true,
      getFillColor: [0, 0, 0, 0],
      pickable: true,
      parameters: { depthCompare: "always" },
    }),
  ];

  // Active scalar overlay (raster) goes underneath the wind particles.
  if (s.overlay !== "none" && data[s.overlay]) {
    const entry = data[s.overlay];
    layers.push(new WeatherLayers.RasterLayer({
      id: "overlay",
      image: entry.image,
      imageType: entry.meta.imageType,           // "SCALAR"
      imageUnscale: entry.meta.imageUnscale,
      bounds: entry.meta.bounds,
      palette: entry.meta.palette
        .map(([v, [r, g, b]]) => [v, [r, g, b, 255]]),
      opacity: 0.55,
      parameters: { cullMode: "back", depthCompare: "always" },
      getPolygonOffset: () => [0, -500],
    }));
  }

  layers.push(new deck.GeoJsonLayer({
    id: "land",
    data: land,
    stroked: true, filled: !s.overlay || s.overlay === "none",
    getFillColor: [28, 36, 48, s.overlay === "none" ? 255 : 0],
    getLineColor: [70, 84, 100, 255],
    lineWidthMinPixels: 0.6,
    parameters: { cullMode: "back", depthCompare: "always" },
  }));

  const windEntry = data[s.windLevel] ?? data.wind_10m;
  layers.push(new WeatherLayers.ParticleLayer({
    id: `wind-${s.windLevel}`,
    image: windEntry.image,
    imageType: "VECTOR",
    imageUnscale: windEntry.meta.imageUnscale,
    bounds: windEntry.meta.bounds,
    numParticles: s.numParticles,
    maxAge: s.maxAge,
    speedFactor: s.speedFactor,
    width: s.width,
    color: [255, 255, 255],
    opacity: 0.4,
    animate: true,
    getPolygonOffset: () => [0, -1000],
  }));

  // High/Low pressure-center glyphs, detected from the MSLP field. Sit above
  // the wind particles so the L/H letters mark the eyes of the vortices.
  if (s.highLow && data.mslp) {
    const m = data.mslp;
    layers.push(new WeatherLayers.HighLowLayer({
      id: "highlow",
      image: m.image,
      imageType: "SCALAR",
      imageUnscale: m.meta.imageUnscale,
      bounds: m.meta.bounds,
      radius: 1500,                 // km — keep to the major synoptic centers
      palette: HIGHLOW_PALETTE,
      textSize: 24,
      textOutlineWidth: 2,
      textOutlineColor: [8, 12, 20, 255],
      pickable: true,
      parameters: { depthCompare: "always" },
      getPolygonOffset: () => [0, -2000],
    }));
  }

  if (state.pin) {
    layers.push(new deck.ScatterplotLayer({
      id: "pin-marker",
      data: [state.pin],
      getPosition: (d) => [d.lng, d.lat],
      getRadius: 4,
      radiusUnits: "pixels",
      getFillColor: [255, 255, 255, 230],
      lineWidthUnits: "pixels",
      getLineColor: [106, 166, 255, 255],
      lineWidthMinPixels: 2,
      stroked: true,
      parameters: { depthCompare: "always" },
    }));
  }

  return layers;
}

// ---------- ui wiring ----------

function wireSliders(settings, onChange) {
  const knobs = [
    { id: "ctl-maxAge", key: "maxAge",       fmt: (v) => `${v|0}` },
    { id: "ctl-speed",  key: "speedFactor",  fmt: (v) => v.toFixed(1) },
    { id: "ctl-num",    key: "numParticles", fmt: (v) => `${v|0}` },
    { id: "ctl-width",  key: "width",        fmt: (v) => v.toFixed(1) },
  ];
  for (const { id, key, fmt } of knobs) {
    const input = document.getElementById(id);
    const valEl = document.getElementById(`${id}-val`);
    valEl.textContent = fmt(settings[key]);
    input.value = settings[key];
    input.addEventListener("input", () => {
      const v = parseFloat(input.value);
      settings[key] = v;
      valEl.textContent = fmt(v);
      onChange();
    });
  }
}

function updateLegend(entry) {
  const palette = entry?.meta?.palette;
  if (!entry || !palette || palette.length < 2) {
    legendEl.style.display = "none";
    return;
  }
  const minVal = palette[0][0];
  const maxVal = palette[palette.length - 1][0];
  const span = maxVal - minVal || 1;

  const stops = palette.map(([v, [r, g, b]]) => {
    const pct = ((v - minVal) / span) * 100;
    return `rgb(${r},${g},${b}) ${pct.toFixed(2)}%`;
  }).join(", ");

  legendTitle.textContent = `${entry.meta.label} (${entry.meta.units})`;
  legendBar.style.background = `linear-gradient(to right, ${stops})`;

  legendTicks.replaceChildren();
  for (const [v] of palette) {
    const pct = ((v - minVal) / span) * 100;
    const tick = document.createElement("span");
    tick.className = "legend-tick";
    tick.textContent = formatTick(v);
    tick.style.left = `${pct}%`;
    legendTicks.appendChild(tick);
  }
  legendEl.style.display = "block";
}

function formatTick(v) {
  if (Math.abs(v) >= 100) return v.toFixed(0);
  if (Number.isInteger(v)) return `${v}`;
  return v.toFixed(0);
}

function wireOverlayButtons(settings, onChange) {
  const buttons = document.querySelectorAll("#controls button[data-overlay]");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      settings.overlay = btn.getAttribute("data-overlay");
      onChange();
    });
  });
}

function wireToggleButtons(settings, onChange) {
  const buttons = document.querySelectorAll("#controls button[data-toggle]");
  buttons.forEach((btn) => {
    const key = btn.getAttribute("data-toggle");
    btn.classList.toggle("active", !!settings[key]);
    btn.addEventListener("click", () => {
      settings[key] = !settings[key];
      btn.classList.toggle("active", settings[key]);
      onChange();
    });
  });
}

function wireWindButtons(settings, onChange) {
  const buttons = document.querySelectorAll("#controls button[data-wind]");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      settings.windLevel = btn.getAttribute("data-wind");
      onChange();
    });
  });
}

main().catch((err) => {
  console.error(err);
  setStatus(`error: ${err.message}`);
});
