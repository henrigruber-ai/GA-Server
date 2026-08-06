/*
File: app/web/static/js/app.js
Version: 0.3.0
Date: 2026-08-06
Purpose: Coordinates the GA legend, resilient history refresh, raw live values, and auth.
Changes:
- 0.1.0: Initial implementation.
- 0.2.0: Adds independent multi-series selection, persistent legend state, and raw live values.
- 0.3.0: Makes GA the initial-closed legend control and preserves valid history on empty refreshes.
*/

(() => {
  "use strict";

  if (window.GAApp?.initialized) return;

  const STORAGE_KEY = "ga.monitor.selection.v2";
  const METRICS = {
    current: { label: "Strom", unit: "A", phases: ["l1", "l2", "l3", "total"] },
    voltage: { label: "Spannung", unit: "V", phases: ["l1", "l2", "l3"] },
    power: { label: "Leistung", unit: "W", phases: ["l1", "l2", "l3", "total"] },
  };
  const PHASE_LABELS = { l1: "L1", l2: "L2", l3: "L3", total: "Gesamt" };
  const ALL_SERIES = Object.entries(METRICS)
    .flatMap(([metric, definition]) => definition.phases.map((phase) => `${metric}:${phase}`))
    .join(",");
  const saved = readSavedState();
  const state = {
    devices: [],
    latest: new Map(),
    selected: new Set(saved?.selected || []),
    expanded: new Set(saved?.expanded || []),
    legendOpen: false,
    hasSavedSelection: Boolean(saved),
    visuals: new Map(),
    socket: null,
    reconnectDelay: 1000,
    reconnectTimer: null,
    historyInFlight: null,
    historyCursor: null,
    historyTimer: null,
    liveTimer: null,
    destroyed: false,
    historyRefreshCount: 0,
  };

  const canvas = document.querySelector("#historyCanvas");
  const tooltip = document.querySelector("#tooltip");
  const chart = new window.GAHistoryChart(canvas, tooltip, {
    onZoomChange: (zoomed) => document.querySelector("#zoomReset").classList.toggle("hidden", !zoomed),
  });
  const legend = document.querySelector("#deviceLegend");
  const legendRows = document.querySelector("#legendRows");
  const legendToggle = document.querySelector("#legendToggle");
  const menuButton = document.querySelector("#menuButton");
  const loginDialog = document.querySelector("#loginDialog");
  const loginForm = document.querySelector("#loginForm");
  const connectionBadge = document.querySelector("#connectionBadge");

  function readSavedState() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (
        parsed?.version !== 2 ||
        !Array.isArray(parsed.selected) ||
        !Array.isArray(parsed.expanded)
      ) {
        return null;
      }
      return {
        selected: parsed.selected.filter((value) => typeof value === "string"),
        expanded: parsed.expanded.filter((value) => typeof value === "string"),
      };
    } catch {
      return null;
    }
  }

  function saveState() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: 2,
          selected: [...state.selected],
          expanded: [...state.expanded],
        }),
      );
    } catch {
      // A disabled or full local storage must not make the monitor unusable.
    }
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  function availableKeys(device) {
    const catalog = Array.isArray(device.available_series)
      ? device.available_series
      : ALL_SERIES.split(",");
    return catalog.map((item) => `${device.id}:${item}`);
  }

  function defaultKeys(device) {
    return ["l1", "l2", "l3"]
      .map((phase) => `${device.id}:current:${phase}`)
      .filter((key) => availableKeys(device).includes(key));
  }

  function buildVisuals() {
    const usedHues = new Set();
    const keys = state.devices.flatMap(availableKeys).sort();
    state.visuals.clear();
    keys.forEach((key) => {
      let hue = hashString(key) % 360;
      while (usedHues.has(hue)) hue = (hue + 47) % 360;
      usedHues.add(hue);
      const phase = key.split(":").at(-1);
      const dash = {
        l1: [],
        l2: [8, 4],
        l3: [2, 3],
        total: [11, 3, 2, 3],
      }[phase];
      state.visuals.set(key, { color: `hsl(${hue} 78% 64%)`, dash });
    });
  }

  function hashString(value) {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  async function loadDevices() {
    state.devices = await fetchJson("/api/public/devices");
    const valid = new Set(state.devices.flatMap(availableKeys));
    state.selected = new Set([...state.selected].filter((key) => valid.has(key)));
    state.expanded = new Set(
      [...state.expanded].filter((key) =>
        state.devices.some((device) => key === device.id || key.startsWith(`${device.id}:`)),
      ),
    );
    if (!state.hasSavedSelection) {
      state.devices.forEach((device) => {
        defaultKeys(device).forEach((key) => state.selected.add(key));
      });
      state.hasSavedSelection = true;
      saveState();
    }
    buildVisuals();
    renderLegend();
    updateChartSelection();
  }

  async function loadHistory({ force = false } = {}) {
    if (document.hidden && !force) return;
    if (state.historyInFlight) return state.historyInFlight;
    const query = new URLSearchParams({
      series: ALL_SERIES,
      max_points: String(window.innerWidth < 700 ? 720 : 1440),
    });
    if (state.historyCursor) {
      query.set("from", new Date(state.historyCursor - 2 * 60_000).toISOString());
    }
    const request = fetchJson(`/api/public/history-batch?${query}`)
      .then((data) => {
        if (!Array.isArray(data.series)) throw new Error("Invalid history response");
        const series = (data.series || []).map((item) => ({
          ...item,
          ...state.visuals.get(item.key),
        }));
        const hasPoints = series.some((item) => item.points?.length);
        if (hasPoints) {
          if (state.historyCursor) chart.mergeSeries(series);
          else chart.setSeries(series);
          state.historyRefreshCount += 1;
        }
        const cursor = new Date(data.to).getTime();
        if (hasPoints && Number.isFinite(cursor)) state.historyCursor = cursor;
        updateChartSelection();
      })
      .finally(() => {
        state.historyInFlight = null;
      });
    state.historyInFlight = request;
    return request;
  }

  function updateChartSelection() {
    chart.setActiveSeries(state.selected);
    const selectedCount = state.selected.size;
    const warning = document.querySelector("#legendWarning");
    warning.textContent =
      selectedCount > 12 ? `${selectedCount} Kurven aktiv – die Darstellung kann dicht werden.` : "";
    warning.classList.toggle("hidden", selectedCount <= 12);
  }

  function setCheckedState(checkbox, selectedCount, totalCount) {
    checkbox.checked = totalCount > 0 && selectedCount === totalCount;
    checkbox.indeterminate = selectedCount > 0 && selectedCount < totalCount;
    checkbox.setAttribute(
      "aria-checked",
      checkbox.indeterminate ? "mixed" : String(checkbox.checked),
    );
  }

  function renderLegend() {
    legendRows.replaceChildren();
    document.querySelector("#legendCount").textContent = String(state.devices.length);
    state.devices.forEach((device) => legendRows.append(createDeviceGroup(device)));
    updateLiveValues();
  }

  function createDeviceGroup(device) {
    const group = document.createElement("section");
    group.className = "legend-device";
    const header = document.createElement("div");
    header.className = "legend-device-header";

    const disclosure = createDisclosure(
      `${device.name} ein- oder ausklappen`,
      state.expanded.has(device.id),
      () => toggleExpanded(device.id),
    );
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "legend-checkbox";
    checkbox.setAttribute("aria-label", `Alle Standardreihen von ${device.name}`);
    const deviceKeys = availableKeys(device);
    setCheckedState(checkbox, deviceKeys.filter((key) => state.selected.has(key)).length, deviceKeys.length);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) defaultKeys(device).forEach((key) => state.selected.add(key));
      else deviceKeys.forEach((key) => state.selected.delete(key));
      selectionChanged();
    });

    const name = document.createElement("span");
    name.className = "legend-device-name";
    name.textContent = device.name;
    name.title = device.name;
    const status = document.createElement("span");
    status.className = `device-state ${device.status}`;
    status.title = device.status;
    const live = document.createElement("output");
    live.className = "legend-device-live";
    live.dataset.deviceId = device.id;
    live.setAttribute("aria-label", `Aktueller Stromwert ${device.name}`);
    header.append(disclosure, checkbox, name, live, status);
    group.append(header);

    const content = document.createElement("div");
    content.className = "legend-device-content";
    content.hidden = !state.expanded.has(device.id);
    Object.entries(METRICS).forEach(([metric, definition]) => {
      const phases = definition.phases.filter((phase) =>
        deviceKeys.includes(`${device.id}:${metric}:${phase}`),
      );
      if (phases.length) content.append(createMetricGroup(device, metric, definition, phases));
    });
    group.append(content);
    return group;
  }

  function createMetricGroup(device, metric, definition, phases) {
    const group = document.createElement("section");
    group.className = "legend-metric";
    const groupKey = `${device.id}:${metric}`;
    const header = document.createElement("div");
    header.className = "legend-metric-header";
    const disclosure = createDisclosure(
      `${definition.label} bei ${device.name} ein- oder ausklappen`,
      state.expanded.has(groupKey),
      () => toggleExpanded(groupKey),
    );
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "legend-checkbox";
    checkbox.setAttribute("aria-label", `Alle Phasen ${definition.label} bei ${device.name}`);
    const keys = phases.map((phase) => `${device.id}:${metric}:${phase}`);
    setCheckedState(checkbox, keys.filter((key) => state.selected.has(key)).length, keys.length);
    checkbox.addEventListener("change", () => {
      keys.forEach((key) => (checkbox.checked ? state.selected.add(key) : state.selected.delete(key)));
      selectionChanged();
    });
    const label = document.createElement("span");
    label.textContent = definition.label;
    header.append(disclosure, checkbox, label);
    group.append(header);

    const rows = document.createElement("div");
    rows.className = "legend-series-list";
    rows.hidden = !state.expanded.has(groupKey);
    phases.forEach((phase) => rows.append(createSeriesRow(device, metric, definition, phase)));
    group.append(rows);
    return group;
  }

  function createSeriesRow(device, metric, definition, phase) {
    const key = `${device.id}:${metric}:${phase}`;
    const label = document.createElement("label");
    label.className = "legend-series";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "legend-checkbox";
    checkbox.checked = state.selected.has(key);
    checkbox.setAttribute(
      "aria-label",
      `${device.name}, ${definition.label}, ${PHASE_LABELS[phase]}`,
    );
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selected.add(key);
      else state.selected.delete(key);
      selectionChanged();
    });
    const marker = document.createElement("span");
    marker.className = `series-marker phase-${phase}`;
    marker.style.setProperty("--series-color", state.visuals.get(key)?.color || "#fff");
    const name = document.createElement("span");
    name.className = "legend-series-name";
    name.textContent = PHASE_LABELS[phase];
    const value = document.createElement("output");
    value.className = "legend-live-value";
    value.dataset.seriesKey = key;
    value.dataset.deviceId = device.id;
    value.dataset.metric = metric;
    value.dataset.phase = phase;
    value.setAttribute("aria-label", `Livewert ${device.name} ${definition.label} ${PHASE_LABELS[phase]}`);
    label.append(checkbox, marker, name, value);
    return label;
  }

  function createDisclosure(label, expanded, listener) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "legend-disclosure";
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-expanded", String(expanded));
    button.textContent = expanded ? "▾" : "▸";
    button.addEventListener("click", listener);
    return button;
  }

  function toggleExpanded(key) {
    if (state.expanded.has(key)) state.expanded.delete(key);
    else state.expanded.add(key);
    saveState();
    renderLegend();
  }

  function selectionChanged() {
    saveState();
    renderLegend();
    updateChartSelection();
  }

  function applyLegendState() {
    legend.classList.toggle("hidden", !state.legendOpen);
    legendToggle.setAttribute("aria-expanded", String(state.legendOpen));
    legendToggle.setAttribute(
      "aria-label",
      state.legendOpen ? "Diagrammlegende schließen" : "Diagrammlegende öffnen",
    );
  }

  function updateLiveValues() {
    document.querySelectorAll(".legend-device-live").forEach((output) => {
      const measurement = state.latest.get(output.dataset.deviceId);
      const value = measurement?.values?.current_total ?? measurement?.values?.current_l1;
      output.textContent = Number.isFinite(value) ? formatLive(value, "current") : "–";
    });
    document.querySelectorAll(".legend-live-value").forEach((output) => {
      const measurement = state.latest.get(output.dataset.deviceId);
      const value = measurement?.values?.[`${output.dataset.metric}_${output.dataset.phase}`];
      const received = measurement ? new Date(measurement.received_at) : null;
      const device = state.devices.find((item) => item.id === output.dataset.deviceId);
      const ageSeconds = received ? Math.max(0, (Date.now() - received.getTime()) / 1000) : Infinity;
      const staleSeconds = Number(device?.stale_seconds) || 60;
      const offlineSeconds = Number(device?.offline_seconds) || 300;
      output.classList.toggle("stale", ageSeconds >= staleSeconds);
      output.classList.toggle("offline", ageSeconds >= offlineSeconds);
      if (!Number.isFinite(value) || !received) {
        output.textContent = "keine Daten";
        output.title = "Noch kein Rohwert empfangen";
      } else if (ageSeconds >= offlineSeconds) {
        output.textContent = `${formatLive(value, output.dataset.metric)} · nicht aktuell`;
        output.title = `Letzter Rohwert: ${received.toLocaleString("de-DE")}`;
      } else if (ageSeconds >= staleSeconds) {
        output.textContent = `${formatLive(value, output.dataset.metric)} · veraltet`;
        output.title = `Empfangen: ${received.toLocaleString("de-DE")}`;
      } else {
        output.textContent = formatLive(value, output.dataset.metric);
        output.title = `Rohwert empfangen: ${received.toLocaleString("de-DE")}`;
      }
    });
  }

  function formatLive(value, metric) {
    if (metric === "power" && Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)} kW`;
    const decimals = Math.abs(value) >= 100 ? 1 : 2;
    return `${Number(value).toLocaleString("de-DE", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })} ${METRICS[metric].unit}`;
  }

  function connectLive() {
    if (state.destroyed) return;
    if (state.socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(state.socket.readyState)) return;
    clearTimeout(state.reconnectTimer);
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    state.socket = new WebSocket(`${protocol}//${location.host}/api/public/live-stream`);
    setConnection("connecting", "Verbinde …");
    state.socket.addEventListener("open", () => {
      state.reconnectDelay = 1000;
      setConnection("online", "Live verbunden");
    });
    state.socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "snapshot") {
        message.data.forEach((measurement) => state.latest.set(measurement.device_id, measurement));
      } else if (message.type === "measurement") {
        state.latest.set(message.data.device_id, message.data);
      }
      updateLiveValues();
    });
    const socket = state.socket;
    state.socket.addEventListener("close", () => {
      if (state.socket !== socket) return;
      if (state.destroyed) return;
      setConnection("offline", "Verbindung getrennt");
      state.reconnectTimer = setTimeout(connectLive, state.reconnectDelay);
      state.reconnectDelay = Math.min(30000, state.reconnectDelay * 1.8);
    });
    state.socket.addEventListener("error", () => state.socket.close());
  }

  function setConnection(className, text) {
    connectionBadge.className = `connection-badge ${className}`;
    connectionBadge.querySelector("span:last-child").textContent = text;
  }

  async function openMenu() {
    try {
      const session = await fetchJson("/api/auth/session");
      window.GAAdmin.setSession(session);
      window.GAAdmin.open();
      menuButton.setAttribute("aria-expanded", "true");
    } catch {
      loginDialog.showModal();
      menuButton.setAttribute("aria-expanded", "true");
      loginForm.elements.username.focus();
    }
  }

  async function submitLogin(event) {
    event.preventDefault();
    const error = document.querySelector("#loginError");
    error.textContent = "";
    try {
      const payload = Object.fromEntries(new FormData(loginForm));
      const session = await fetchJson("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      window.GAAdmin.setSession(session);
      loginDialog.close();
      loginForm.reset();
      window.GAAdmin.open();
    } catch (exception) {
      error.textContent = exception.message;
    }
  }

  function showPublicError(error) {
    setConnection("offline", "Daten nicht erreichbar");
    console.error(error);
  }

  legendToggle.addEventListener("click", () => {
    state.legendOpen = !state.legendOpen;
    applyLegendState();
  });
  legend.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true });
  document.querySelector("#zoomReset").addEventListener("click", () => chart.resetZoom());
  menuButton.addEventListener("click", openMenu);
  loginForm.addEventListener("submit", submitLogin);
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });
  loginDialog.addEventListener("close", () => menuButton.setAttribute("aria-expanded", "false"));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.querySelector("#adminDrawer").classList.contains("hidden")) {
      window.GAAdmin.close();
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadHistory({ force: true }).catch(showPublicError);
  });
  window.addEventListener(
    "pagehide",
    () => {
      state.destroyed = true;
      clearTimeout(state.reconnectTimer);
      clearInterval(state.historyTimer);
      clearInterval(state.liveTimer);
      state.socket?.close();
      chart.destroy();
    },
    { once: true },
  );

  applyLegendState();
  Promise.all([loadDevices(), fetchJson("/api/public/live")])
    .then(([, live]) => {
      live.measurements.forEach((measurement) => state.latest.set(measurement.device_id, measurement));
      updateLiveValues();
      return loadHistory({ force: true });
    })
    .catch(showPublicError);
  connectLive();
  state.liveTimer = setInterval(updateLiveValues, 1000);
  const historyInterval = Math.max(50, Number(window.GA_TEST_HISTORY_INTERVAL_MS) || 10_000);
  state.historyTimer = setInterval(() => loadHistory().catch(showPublicError), historyInterval);

  window.GAApp = {
    initialized: true,
    fetchJson,
    loadDevices,
    loadHistory,
    getSelection: () => new Set(state.selected),
    getVisibleSeriesCount: () => chart.activeItems().filter((item) => item.points.length).length,
    getHistoryRefreshCount: () => state.historyRefreshCount,
  };
})();
