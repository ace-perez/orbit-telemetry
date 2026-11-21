// Orbit Telemetry console. Every value on the page comes from the /api routes of this app.
// Text is always set with textContent, never innerHTML, so API data can never become markup.
/* global d3, topojson */
"use strict";

(() => {
  const POLL = { list: 5000, telemetry: 2000, track: 60000, sun: 60000, info: 30000 };
  const REQUEST_TIMEOUT_MS = 4000;
  const DEFAULT_NORAD = 25544; // ISS
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const state = {
    selected: null,
    telemetry: null,
    track: [],
    periodMinutes: null,
    subsolar: null,
    autoTrack: true,
    failures: 0,
  };

  const $ = (id) => document.getElementById(id);
  const setText = (id, text) => {
    const el = $(id);
    if (el && el.textContent !== text) el.textContent = text;
  };
  const fixed = (value, digits) => (Number.isFinite(value) ? value.toFixed(digits) : "--");
  const hemi = (value, pos, neg) => `${fixed(Math.abs(value), 2)}° ${value >= 0 ? pos : neg}`;

  // --- API ----------------------------------------------------------------------------

  async function api(path) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(path, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
      const body = await response.json();
      state.failures = 0;
      return body;
    } catch (error) {
      state.failures += 1;
      renderLink();
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function every(ms, task) {
    const run = () => task().catch(() => undefined); // failures are shown in the link chip
    run();
    return setInterval(run, ms);
  }

  // --- top bar and footer ----------------------------------------------------------------

  let info = null;

  function renderLink() {
    const chip = $("link");
    let text = "DATA LINK: OK";
    let kind = "chip-ok";
    if (state.failures >= 2) {
      text = "API UNREACHABLE";
      kind = "chip-error";
    } else if (info && !info.orbital_data_ok) {
      text = "ORBITAL DATA STALE";
      kind = "chip-warn";
    } else if (!info) {
      text = "CONNECTING";
      kind = "chip-wait";
    }
    chip.className = `chip ${kind}`;
    setText("link", text);
  }

  async function loadInfo() {
    info = await api("/api/v1/info");
    setText("environment", info.environment);
    setText("version", info.version);
    setText("ephemeris", `${info.satellites_ready}/${info.satellites_tracked} READY`);
    renderLink();
  }

  // --- constellation list -------------------------------------------------------------------

  const listItems = new Map(); // norad_id -> { li, button, chip, alt, meta }

  function makeSpan(className, text) {
    const span = document.createElement("span");
    span.className = className;
    if (text !== undefined) span.textContent = text;
    return span;
  }

  function createListItem(sat) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sat";
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => select(sat.norad_id));

    const top = makeSpan("sat-top");
    const name = makeSpan("sat-name", sat.name);
    const chip = makeSpan("chip");
    top.append(name, chip);

    const meta = makeSpan("sat-meta");
    const bottom = makeSpan("sat-bottom");
    const orbitClass = makeSpan("sat-class", sat.orbit_class);
    const alt = makeSpan("sat-alt");
    bottom.append(orbitClass, alt);

    button.append(top, meta, bottom);
    li.append(button);
    $("sat-list").append(li);
    const item = { li, button, chip, alt, meta, name: sat.name };
    listItems.set(sat.norad_id, item);
    return item;
  }

  function setLightChip(el, sunlit) {
    el.className = `chip ${sunlit ? "chip-sunlit" : "chip-eclipse"}`;
    el.textContent = sunlit ? "Sunlit" : "Eclipse";
  }

  function renderList(satellites) {
    for (const sat of satellites) {
      const item = listItems.get(sat.norad_id) || createListItem(sat);
      setLightChip(item.chip, sat.sunlit);
      item.meta.textContent = `NORAD ${sat.norad_id} · INC ${fixed(sat.inclination_deg, 2)}°`;
      item.alt.textContent = fixed(sat.altitude_km, 1);
      const unit = document.createElement("small");
      unit.textContent = "km";
      item.alt.append(unit);
    }
    setText("count", `${satellites.length} active`);
    applyFilter();
  }

  function applyFilter() {
    const query = $("filter").value.trim().toLowerCase();
    for (const [norad, item] of listItems) {
      const match = !query || item.name.toLowerCase().includes(query) || String(norad).includes(query);
      item.li.hidden = !match;
    }
  }

  async function loadList() {
    const satellites = await api("/api/v1/satellites");
    renderList(satellites);
    if (state.selected === null && satellites.length) {
      const fromHash = Number.parseInt(window.location.hash.slice(1), 10);
      const wanted = satellites.find((s) => s.norad_id === fromHash)
        || satellites.find((s) => s.norad_id === DEFAULT_NORAD)
        || satellites[0];
      select(wanted.norad_id);
    }
  }

  function select(noradId) {
    if (state.selected === noradId) return;
    state.selected = noradId;
    state.telemetry = null;
    state.track = [];
    for (const [norad, item] of listItems) {
      item.button.setAttribute("aria-pressed", String(norad === noradId));
    }
    history.replaceState(null, "", `#${noradId}`);
    setAutoTrack(true);
    loadTelemetry().catch(() => undefined);
    loadTrack().catch(() => undefined);
  }

  // --- selected satellite ----------------------------------------------------------------

  function relativeAge(seconds) {
    if (!Number.isFinite(seconds)) return "--";
    if (seconds < 90) return `${Math.round(seconds)} s ago`;
    if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
    return `${(seconds / 3600).toFixed(1)} h ago`;
  }

  function renderTelemetry(t) {
    const p = t.position;
    setText("d-name", t.name);
    setLightChip($("d-light"), t.power.sunlit);
    setText("d-norad", String(t.norad_id));
    setText("d-intl", t.intl_designator);
    setText("d-class", t.orbit_class);

    setText("lat", hemi(p.latitude_deg, "N", "S"));
    setText("lon", hemi(p.longitude_deg, "E", "W"));
    setText("alt", `${fixed(p.altitude_km, 1)} km`);
    setText("speed", `${fixed(p.speed_km_s, 2)} km/s`);
    setText("beta", `${fixed(t.beta_angle_deg, 1)}°`);
    setText("footprint", `${fixed(t.coverage_half_angle_deg, 1)}°`);

    const power = t.power;
    const bands = power.bands;
    setLightChip($("p-light"), power.sunlit);
    setText("p-volt", `${fixed(power.battery_voltage_v, 1)} V`);
    const span = bands.overvoltage_v - bands.critical_v;
    const position = Math.min(1, Math.max(0, (power.battery_voltage_v - bands.critical_v) / span));
    $("volt-marker").style.left = `${(position * 100).toFixed(1)}%`;
    setText("b-crit", `CRIT ${fixed(bands.critical_v, 0)} V`);
    setText("b-nominal", `NOMINAL ${fixed(bands.nominal_min_v, 0)} to ${fixed(bands.nominal_max_v, 0)} V`);
    setText("b-ovp", `OVP ${fixed(bands.overvoltage_v, 0)} V`);
    setText("p-soc", `${fixed(power.state_of_charge_pct, 0)}%`);
    renderCells(power.state_of_charge_pct);
    setText("p-solar", `${fixed(power.solar_array_current_a, 2)} A`);

    setText("t-core", `${fixed(t.thermal.core_temperature_c, 1)} °C`);
    setText("t-target", `${fixed(t.thermal.target_temperature_c, 1)} °C`);

    setText("lock", `${t.name} (${t.norad_id})`);
    setText("epoch", t.elements_epoch.replace("T", " ").slice(0, 19) + " UTC");
    setText("inclination", `${fixed(t.inclination_deg, 2)}°`);
    setText("period", `${fixed(t.period_minutes, 1)} min`);
    setText("age", `Orbital data fetched ${relativeAge(t.data_age_seconds)}${t.data_stale ? " (stale)" : ""}`);
  }

  function renderCells(percent) {
    const cells = $("soc-cells");
    if (!cells.childElementCount) {
      for (let i = 0; i < 10; i += 1) cells.append(makeSpan("cell"));
    }
    const lit = Math.round(percent / 10);
    [...cells.children].forEach((cell, i) => cell.classList.toggle("cell-on", i < lit));
  }

  async function loadTelemetry() {
    if (state.selected === null) return;
    const wanted = state.selected;
    const t = await api(`/api/v1/satellites/${wanted}/telemetry`);
    if (wanted !== state.selected) return; // the user picked another satellite meanwhile
    state.telemetry = t;
    state.periodMinutes = t.period_minutes;
    renderTelemetry(t);
    if (state.autoTrack) rotateTo(t.position.longitude_deg, t.position.latitude_deg);
    globe.draw();
  }

  async function loadTrack() {
    if (state.selected === null) return;
    const wanted = state.selected;
    const track = await api(`/api/v1/satellites/${wanted}/track?orbits=3&step_seconds=60`);
    if (wanted !== state.selected) return;
    state.track = track.points;
    globe.draw();
  }

  async function loadSun() {
    const sun = await api("/api/v1/sun");
    state.subsolar = [sun.subsolar_longitude_deg, sun.subsolar_latitude_deg];
    setText("subsolar", `${hemi(sun.subsolar_latitude_deg, "N", "S")} · ${hemi(sun.subsolar_longitude_deg, "E", "W")}`);
    globe.draw();
  }

  // --- globe ------------------------------------------------------------------------------

  const globe = (() => {
    const svg = d3.select("#globe");
    const projection = d3.geoOrthographic().clipAngle(90).precision(0.3).rotate([0, -20]);
    const path = d3.geoPath(projection);
    const graticule = d3.geoGraticule10();
    let land = null;

    const layer = (cls) => svg.append("path").attr("class", cls);
    const ocean = layer("ocean");
    const grid = layer("graticule");
    const landPath = layer("land");
    const night = layer("night");
    const footprint = layer("footprint");
    const tracks = [layer("track track-0"), layer("track track-1"), layer("track track-2")];
    const outline = layer("outline");
    const subsolar = svg.append("circle").attr("class", "subsolar").attr("r", 4);
    const halo = svg.append("circle").attr("class", "sat-halo").attr("r", 11);
    const dot = svg.append("circle").attr("class", "sat-dot").attr("r", 4.5);

    function resize() {
      const box = document.getElementById("globe-wrap").getBoundingClientRect();
      const size = Math.min(box.width, box.height);
      projection.translate([box.width / 2, box.height / 2]).scale(Math.max(10, size / 2 - 16));
      draw();
    }

    function splitPasses(points) {
      if (!points.length || !state.periodMinutes) return [[], [], []];
      const start = Date.parse(points[0].time);
      const periodMs = state.periodMinutes * 60000;
      const passes = [[], [], []];
      for (const point of points) {
        const index = Math.min(2, Math.floor((Date.parse(point.time) - start) / periodMs));
        passes[index].push([point.longitude_deg, point.latitude_deg]);
      }
      return passes;
    }

    function place(circle, lonLat) {
      const center = projection.invert(projection.translate());
      const visible = lonLat && d3.geoDistance(lonLat, center) < Math.PI / 2 - 0.01;
      circle.attr("display", visible ? null : "none");
      if (visible) {
        const [x, y] = projection(lonLat);
        circle.attr("cx", x).attr("cy", y);
      }
    }

    function draw() {
      ocean.attr("d", path({ type: "Sphere" }));
      outline.attr("d", path({ type: "Sphere" }));
      grid.attr("d", path(graticule));
      if (land) landPath.attr("d", path(land));

      if (state.subsolar) {
        const antisolar = [state.subsolar[0] + 180, -state.subsolar[1]];
        night.attr("d", path(d3.geoCircle().center(antisolar).radius(90)()));
      }
      place(subsolar, state.subsolar);

      const passes = splitPasses(state.track);
      tracks.forEach((track, i) => {
        const coords = passes[i];
        track.attr("d", coords.length > 1 ? path({ type: "LineString", coordinates: coords }) : null);
      });

      const t = state.telemetry;
      if (t) {
        const here = [t.position.longitude_deg, t.position.latitude_deg];
        footprint.attr("d", path(d3.geoCircle().center(here).radius(t.coverage_half_angle_deg)()));
        place(halo, here);
        place(dot, here);
      } else {
        footprint.attr("d", null);
        place(halo, null);
        place(dot, null);
      }

      const [lambda, phi] = projection.rotate();
      const camLongitude = ((((-lambda + 180) % 360) + 360) % 360) - 180; // wrap to -180..180
      setText("cam", `${hemi(-phi, "N", "S")} · ${hemi(camLongitude, "E", "W")}`);
    }

    async function loadLand() {
      const topology = await fetch("/static/vendor/land-110m.json").then((r) => r.json());
      land = topojson.feature(topology, topology.objects.land);
      draw();
    }

    svg.call(
      d3.drag().on("start", () => {
        svg.interrupt("rotate");
        setAutoTrack(false);
      }).on("drag", (event) => {
        const [lambda, phi] = projection.rotate();
        const k = 75 / projection.scale();
        projection.rotate([lambda + event.dx * k, Math.max(-89, Math.min(89, phi - event.dy * k))]);
        draw();
      }),
    );

    new ResizeObserver(resize).observe(document.getElementById("globe-wrap"));
    loadLand().catch(() => undefined);
    return { projection, draw };
  })();

  function rotateTo(longitude, latitude) {
    const target = [-longitude, -Math.max(-60, Math.min(60, latitude))];
    const from = globe.projection.rotate();
    const delta = Math.abs(((target[0] - from[0] + 540) % 360) - 180) + Math.abs(target[1] - from[1]);
    if (reducedMotion || delta < 3) {
      globe.projection.rotate(target);
      return;
    }
    // Unwrap the longitude so the globe turns the short way round.
    const end = [from[0] + ((((target[0] - from[0]) % 360) + 540) % 360) - 180, target[1]];
    const interpolate = d3.interpolate(from, end);
    d3.select("#globe")
      .interrupt("rotate")
      .transition("rotate")
      .duration(700)
      .tween("rotate", () => (k) => {
        globe.projection.rotate(interpolate(k));
        globe.draw();
      });
  }

  function setAutoTrack(on) {
    state.autoTrack = on;
    const button = $("autotrack");
    button.setAttribute("aria-pressed", String(on));
    button.textContent = on ? "Auto-track: on" : "Auto-track: off";
    if (on && state.telemetry) {
      rotateTo(state.telemetry.position.longitude_deg, state.telemetry.position.latitude_deg);
    }
  }

  // --- start --------------------------------------------------------------------------

  $("autotrack").addEventListener("click", () => setAutoTrack(!state.autoTrack));
  $("filter").addEventListener("input", applyFilter);

  every(POLL.info, loadInfo);
  every(POLL.list, loadList);
  every(POLL.sun, loadSun);
  setInterval(() => loadTelemetry().catch(() => undefined), POLL.telemetry);
  setInterval(() => loadTrack().catch(() => undefined), POLL.track);
})();
