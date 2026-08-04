/*
File: app/web/static/js/app.js
Version: 0.1.0
Date: 2026-08-03
Purpose: Coordinates public devices, graph controls, live WebSocket updates, and authentication entry.
Changes:
- 0.1.0: Initial implementation.
*/

(() => {
  "use strict";

  const state = {
    devices: [],
    latest: new Map(),
    metric: localStorage.getItem("ga.metric") || "power",
    phase: localStorage.getItem("ga.phase") || "total",
    visible: new Set(JSON.parse(localStorage.getItem("ga.visibleDevices") || "[]")),
    socket: null,
    reconnectDelay: 1000,
    reconnectTimer: null,
  };

  const canvas = document.querySelector("#historyCanvas");
  const tooltip = document.querySelector("#tooltip");
  const chart = new window.GAHistoryChart(canvas, tooltip);
  const metricControls = document.querySelector("#metricControls");
  const phaseControls = document.querySelector("#phaseControls");
  const legend = document.querySelector("#deviceLegend");
  const legendRows = document.querySelector("#legendRows");
  const legendToggle = document.querySelector("#legendToggle");
  const menuButton = document.querySelector("#menuButton");
  const loginDialog = document.querySelector("#loginDialog");
  const loginForm = document.querySelector("#loginForm");
  const connectionBadge = document.querySelector("#connectionBadge");

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  async function loadDevices() {
    state.devices = await fetchJson("/api/public/devices");
    if (!state.visible.size) state.devices.forEach((device) => state.visible.add(device.id));
    const existing = new Set(state.devices.map((device) => device.id));
    state.visible = new Set([...state.visible].filter((id) => existing.has(id)));
    renderLegend();
    renderLiveCards();
    chart.setVisibleDevices(state.visible);
  }

  async function loadHistory() {
    const query = new URLSearchParams({
      metric: state.metric,
      phase: state.phase,
      max_points: String(window.innerWidth < 700 ? 720 : 1440),
    });
    const data = await fetchJson(`/api/public/history?${query}`);
    chart.setSelection(state.metric, state.phase);
    chart.setSeries(data.series || []);
  }

  function renderLegend() {
    legendRows.replaceChildren();
    document.querySelector("#legendCount").textContent = String(state.devices.length);
    state.devices.forEach((device) => {
      const label = document.createElement("label");
      label.className = "legend-row";
      label.title = device.name;
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.visible.has(device.id);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.visible.add(device.id);
        else state.visible.delete(device.id);
        localStorage.setItem("ga.visibleDevices", JSON.stringify([...state.visible]));
        chart.setVisibleDevices(state.visible);
        renderLiveCards();
      });
      const name = document.createElement("span");
      name.className = "legend-name";
      name.textContent = device.name + (device.has_data ? "" : " · keine Daten");
      const indicator = document.createElement("span");
      indicator.className = `device-state ${device.status}`;
      indicator.title = device.status;
      const color = document.createElement("span");
      color.className = "legend-color";
      color.style.backgroundColor = device.color;
      name.prepend(color, " ");
      label.append(checkbox, name, indicator);
      legendRows.append(label);
    });
  }

  function valueFor(measurement) {
    return measurement?.values?.[`${state.metric}_${state.phase}`];
  }

  function renderLiveCards() {
    const container = document.querySelector("#liveCards");
    container.replaceChildren();
    const unit = { current: "A", voltage: "V", power: "W" }[state.metric];
    state.devices
      .filter((device) => state.visible.has(device.id))
      .slice(0, 8)
      .forEach((device) => {
        const measurement = state.latest.get(device.id);
        const value = valueFor(measurement);
        const card = document.createElement("div");
        card.className = "live-card";
        const name = document.createElement("span");
        name.className = "live-card-name";
        name.textContent = device.name;
        const meta = document.createElement("span");
        meta.className = "live-card-meta";
        meta.textContent = measurement ? new Date(measurement.received_at).toLocaleTimeString("de-DE") : "keine Daten";
        const current = document.createElement("strong");
        current.className = "live-card-value";
        current.style.color = device.color;
        current.textContent = Number.isFinite(value) ? `${formatLive(value)} ${unit}` : "–";
        card.append(name, current, meta);
        container.append(card);
      });
  }

  function formatLive(value) {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)}k`;
    return Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2);
  }

  function updateControls() {
    metricControls.querySelectorAll("button").forEach((button) => {
      button.classList.toggle("active", button.dataset.metric === state.metric);
    });
    phaseControls.querySelectorAll("button").forEach((button) => {
      const unavailable = state.metric === "voltage" && button.dataset.phase === "total";
      button.disabled = unavailable;
      button.classList.toggle("active", button.dataset.phase === state.phase);
    });
  }

  function selectMetric(metric) {
    state.metric = metric;
    if (metric === "voltage" && state.phase === "total") state.phase = "l1";
    localStorage.setItem("ga.metric", state.metric);
    localStorage.setItem("ga.phase", state.phase);
    updateControls();
    renderLiveCards();
    loadHistory().catch(showPublicError);
  }

  function selectPhase(phase) {
    if (state.metric === "voltage" && phase === "total") return;
    state.phase = phase;
    localStorage.setItem("ga.phase", state.phase);
    updateControls();
    renderLiveCards();
    loadHistory().catch(showPublicError);
  }

  function connectLive() {
    clearTimeout(state.reconnectTimer);
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    state.socket = new WebSocket(`${protocol}//${location.host}/api/public/live-stream`);
    setConnection("connecting", "Verbinde …");
    state.socket.addEventListener("open", () => {
      state.reconnectDelay = 1000;
      setConnection("online", "Live verbunden");
    });
    state.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "snapshot") {
        message.data.forEach((measurement) => state.latest.set(measurement.device_id, measurement));
      }
      if (message.type === "measurement") state.latest.set(message.data.device_id, message.data);
      renderLiveCards();
    });
    state.socket.addEventListener("close", () => {
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

  metricControls.addEventListener("click", (event) => {
    const button = event.target.closest("[data-metric]");
    if (button) selectMetric(button.dataset.metric);
  });
  phaseControls.addEventListener("click", (event) => {
    const button = event.target.closest("[data-phase]");
    if (button) selectPhase(button.dataset.phase);
  });
  legendToggle.addEventListener("click", () => {
    const collapsed = legend.classList.toggle("collapsed");
    legendToggle.setAttribute("aria-expanded", String(!collapsed));
    chart.resize();
  });
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

  updateControls();
  Promise.all([loadDevices(), fetchJson("/api/public/live")])
    .then(([, live]) => {
      live.measurements.forEach((measurement) => state.latest.set(measurement.device_id, measurement));
      renderLiveCards();
      return loadHistory();
    })
    .catch(showPublicError);
  connectLive();
  setInterval(() => loadHistory().catch(showPublicError), 60000);
  setInterval(() => loadDevices().catch(showPublicError), 60000);

  window.GAApp = { fetchJson, loadDevices, loadHistory };
})();
