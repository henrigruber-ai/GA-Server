/*
File: app/web/static/js/control.js
Version: 0.3.0
Date: 2026-08-06
Purpose: Renders the protected Tasmota plug overview and confirmation-driven controls.
*/

(() => {
  "use strict";

  const state = {
    active: false,
    container: null,
    csrf: null,
    devices: new Map(),
    socket: null,
    reconnectTimer: null,
    reconnectDelay: 1000,
    ageTimer: null,
  };

  async function request(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (state.csrf && options.method && options.method !== "GET") {
      headers["X-CSRF-Token"] = state.csrf;
    }
    const response = await fetch(url, { credentials: "same-origin", ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error(detail?.message || detail || `HTTP ${response.status}`);
    }
    return payload;
  }

  async function render(container, csrf) {
    destroy();
    state.active = true;
    state.container = container;
    state.csrf = csrf;
    container.innerHTML = '<p class="muted">Steckdosen werden geladen …</p>';
    const snapshot = await request("/api/admin/control/devices");
    applySnapshot(snapshot);
    renderCards();
    connect();
    state.ageTimer = setInterval(updateAges, 1000);
  }

  function applySnapshot(snapshot) {
    state.devices.clear();
    (snapshot.devices || []).forEach((device) => state.devices.set(device.id, device));
  }

  function renderCards() {
    if (!state.container) return;
    state.container.replaceChildren();
    const title = document.createElement("div");
    title.className = "admin-titlebar";
    title.innerHTML = `
      <div>
        <p class="eyebrow">${state.devices.size} aktiv</p>
        <h3>Steckdosen-Übersicht</h3>
      </div>`;
    state.container.append(title);
    if (!state.devices.size) {
      const empty = document.createElement("section");
      empty.className = "plug-empty";
      empty.innerHTML = `
        <p>Noch keine Steckdosen eingerichtet.</p>
        <button class="primary-button" type="button">Gerät hinzufügen</button>`;
      empty.querySelector("button").addEventListener("click", () => window.GAAdmin.showPanel("devices"));
      state.container.append(empty);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "plug-grid";
    state.devices.forEach((device) => grid.append(createCard(device)));
    state.container.append(grid);
  }

  function createCard(device) {
    const control = device.control || {};
    const live = device.live;
    const current = live?.values?.current_total ?? live?.values?.current_l1;
    const power = live?.values?.power_total ?? live?.values?.power_l1;
    const card = document.createElement("article");
    card.className = "plug-card";
    card.dataset.deviceId = device.id;
    card.innerHTML = `
      <header class="plug-header">
        <div>
          <p class="eyebrow">Tasmota · Relais ${device.relay_index}</p>
          <h4></h4>
        </div>
        <span class="plug-online"></span>
      </header>
      <dl class="plug-values">
        <div><dt>Strom</dt><dd data-live-current>${formatCurrent(current)}</dd></div>
        <div><dt>Leistung</dt><dd data-live-power>${formatPower(power)}</dd></div>
        <div><dt>Messwert</dt><dd data-live-age>${formatAge(live?.received_at)}</dd></div>
        <div><dt>Relais</dt><dd data-relay-state>${relayLabel(control)}</dd></div>
      </dl>
      <div class="plug-control"></div>
      <p class="plug-error" role="status"></p>`;
    card.querySelector("h4").textContent = device.name;
    const online = card.querySelector(".plug-online");
    online.className = `plug-online ${control.online ? "online" : "offline"}`;
    online.textContent = control.online ? "● Online" : "○ Nicht erreichbar";
    const error = card.querySelector(".plug-error");
    error.textContent = errorLabel(control.last_error);

    const holder = card.querySelector(".plug-control");
    if (!device.controllable) {
      holder.innerHTML = '<span class="plug-readonly">Nur Messung und Status</span>';
      return card;
    }
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "power-switch";
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-label", `${device.name} ein- oder ausschalten`);
    toggle.setAttribute("aria-checked", String(control.confirmed_state === true));
    toggle.disabled = !control.online || control.pending || control.confirmed_state === null;
    toggle.innerHTML = `
      <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
      <span class="switch-label">${relayLabel(control)}</span>`;
    toggle.addEventListener("click", () => requestPower(device.id, control.confirmed_state !== true));
    holder.append(toggle);
    return card;
  }

  async function requestPower(deviceId, desiredState) {
    const device = state.devices.get(deviceId);
    if (!device || device.control?.pending) return;
    device.control = {
      ...device.control,
      pending: true,
      desired_state: desiredState,
      last_error: null,
    };
    renderCards();
    try {
      const response = await request(`/api/admin/control/devices/${deviceId}/power`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: desiredState ? "on" : "off" }),
      });
      device.control = response.control;
      renderCards();
    } catch (error) {
      device.control = { ...device.control, pending: false, last_error: error.message };
      renderCards();
    }
  }

  function connect() {
    if (!state.active) return;
    if (state.socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(state.socket.readyState)) return;
    clearTimeout(state.reconnectTimer);
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${location.host}/api/admin/control-stream`);
    state.socket = socket;
    socket.addEventListener("open", () => {
      state.reconnectDelay = 1000;
    });
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "snapshot") {
        applySnapshot(message.data);
      } else if (message.type === "device_state") {
        const device = state.devices.get(message.device_id);
        if (device) device.control = message.state;
      } else if (message.type === "device_measurement") {
        const device = state.devices.get(message.device_id);
        if (device) device.live = message.data;
      } else {
        return;
      }
      renderCards();
    });
    socket.addEventListener("close", () => {
      if (state.socket !== socket || !state.active) return;
      state.socket = null;
      state.reconnectTimer = setTimeout(connect, state.reconnectDelay);
      state.reconnectDelay = Math.min(30_000, state.reconnectDelay * 1.8);
    });
    socket.addEventListener("error", () => socket.close());
  }

  function relayLabel(control) {
    if (control.pending) {
      return control.desired_state ? "Wird eingeschaltet …" : "Wird ausgeschaltet …";
    }
    if (control.confirmed_state === true) return "Eingeschaltet";
    if (control.confirmed_state === false) return "Ausgeschaltet";
    return control.online ? "Zustand wird ermittelt" : "Nicht erreichbar";
  }

  function errorLabel(error) {
    const labels = {
      confirmation_timeout: "Schalten nicht bestätigt",
      confirmation_conflict: "Schalten nicht bestätigt: abweichender Gerätezustand",
      device_offline: "Gerät ist nicht erreichbar",
    };
    return labels[error] || error || "";
  }

  function formatCurrent(value) {
    return Number.isFinite(value)
      ? `${Number(value).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 3 })} A`
      : "–";
  }

  function formatPower(value) {
    if (!Number.isFinite(value)) return "–";
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(2)} kW`;
    return `${Number(value).toLocaleString("de-DE", { maximumFractionDigits: 1 })} W`;
  }

  function formatAge(timestamp) {
    if (!timestamp) return "Noch kein Messwert";
    const age = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
    if (age < 2) return "gerade eben";
    if (age < 60) return `vor ${age} s`;
    return `vor ${Math.floor(age / 60)} min`;
  }

  function updateAges() {
    state.devices.forEach((device) => {
      const output = state.container?.querySelector(
        `.plug-card[data-device-id="${CSS.escape(device.id)}"] [data-live-age]`,
      );
      if (output) output.textContent = formatAge(device.live?.received_at);
    });
  }

  function destroy() {
    state.active = false;
    clearTimeout(state.reconnectTimer);
    clearInterval(state.ageTimer);
    state.reconnectTimer = null;
    state.ageTimer = null;
    if (state.socket) {
      const socket = state.socket;
      state.socket = null;
      socket.close();
    }
    state.devices.clear();
  }

  window.GAControl = { render, destroy };
})();
