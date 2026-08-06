/*
File: app/web/static/js/admin.js
Version: 0.3.0
Date: 2026-08-06
Purpose: Renders authenticated device, plug, MQTT, storage, system, user, and version administration.
Changes:
- 0.1.0: Initial implementation.
- 0.3.0: Adds device-type-aware forms and the protected plug navigation entry.
*/

(() => {
  "use strict";

  const state = { csrf: null, panel: "overview", devices: [], deleteDevice: null };
  const drawer = document.querySelector("#adminDrawer");
  const content = document.querySelector("#adminContent");
  const navigation = document.querySelector("#adminNav");
  const deviceDialog = document.querySelector("#deviceDialog");
  const deviceForm = document.querySelector("#deviceForm");
  const confirmDialog = document.querySelector("#confirmDialog");
  const confirmForm = document.querySelector("#confirmForm");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function request(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (state.csrf && options.method && options.method !== "GET") headers["X-CSRF-Token"] = state.csrf;
    const response = await fetch(url, { credentials: "same-origin", ...options, headers });
    if (response.status === 401) {
      close();
      document.querySelector("#loginDialog").showModal();
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  function setSession(session) {
    state.csrf = session.csrf_token;
  }

  function open() {
    drawer.classList.remove("hidden");
    drawer.setAttribute("aria-hidden", "false");
    document.querySelector("#menuButton").setAttribute("aria-expanded", "true");
    showPanel(state.panel);
  }

  function close() {
    window.GAControl.destroy();
    drawer.classList.add("hidden");
    drawer.setAttribute("aria-hidden", "true");
    document.querySelector("#menuButton").setAttribute("aria-expanded", "false");
  }

  async function showPanel(panel) {
    state.panel = panel;
    if (panel !== "plugs") window.GAControl.destroy();
    navigation.querySelectorAll("[data-panel]").forEach((button) => {
      button.classList.toggle("active", button.dataset.panel === panel);
    });
    content.innerHTML = '<p class="muted">Lade Daten …</p>';
    try {
      if (panel === "overview") await renderOverview();
      if (panel === "plugs") await window.GAControl.render(content, state.csrf);
      if (panel === "devices") await renderDevices();
      if (panel === "mqtt") await renderMqtt();
      if (panel === "storage") await renderStorage();
      if (panel === "system") await renderSystem();
      if (panel === "users") await renderUsers();
      if (panel === "versions") await renderVersions();
      content.focus();
    } catch (error) {
      content.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`;
    }
  }

  async function renderOverview() {
    const [system, storage] = await Promise.all([request("/api/admin/system"), request("/api/admin/storage")]);
    content.innerHTML = `
      <div class="admin-titlebar"><h3>Übersicht</h3></div>
      <div class="card-grid">
        ${infoCard("Anwendung", {
          Version: system.version,
          Laufzeit: formatDuration(system.uptime_seconds),
          Datenbank: system.database_ok ? "bereit" : "Fehler",
          MQTT: system.mqtt_connected ? "verbunden" : "nicht verbunden",
        })}
        ${infoCard("Messstellen", {
          "Aktive Geräte": system.active_devices,
          "WebSocket-Clients": system.websocket_connections,
          "Letztes MQTT": formatDate(system.mqtt_last_message),
        })}
        ${infoCard("Speicher", {
          "Minutenzeilen": storage.measurement_rows,
          "SQLite gesamt": formatBytes(storage.storage.total_bytes),
          "Freier Datenträger": formatBytes(storage.storage.free_bytes),
        })}
      </div>`;
  }

  async function renderDevices() {
    state.devices = await request("/api/admin/devices");
    content.innerHTML = `
      <div class="admin-titlebar">
        <div><p class="eyebrow">${state.devices.length} konfiguriert</p><h3>Geräte</h3></div>
        <button class="plus-button" id="addDevice" type="button" aria-label="Gerät hinzufügen">+</button>
      </div>
      <div class="card-grid" id="deviceCards"></div>`;
    const cards = content.querySelector("#deviceCards");
    state.devices.forEach((device) => {
      const card = document.createElement("article");
      card.className = "device-card";
      card.innerHTML = `
        <h4><span class="legend-color" style="background:${escapeHtml(device.color)}"></span>
          ${escapeHtml(device.name)}</h4>
        <dl class="key-value">
          <dt>Status</dt><dd>${escapeHtml(device.status)}${device.enabled ? "" : " · deaktiviert"}</dd>
          <dt>Geräte-ID</dt><dd>${escapeHtml(device.technical_device_id)}</dd>
          <dt>Geräteart</dt><dd>${device.device_type === "tasmota_plug" ? "Tasmota-Steckdose" : "Shelly Pro 3EM"}</dd>
          <dt>Topic</dt><dd>${escapeHtml(device.mqtt_topic_prefix)}${device.device_type === "tasmota_plug" ? "" : "/status/em:0"}</dd>
          <dt>Letzte Nachricht</dt><dd>${formatDate(device.last_seen_at)}</dd>
          <dt>Steuerbar</dt><dd>${device.controllable ? "ja" : "nein"}</dd>
        </dl>
        <div class="device-actions">
          <button class="secondary-button" type="button" data-edit="${device.id}">Bearbeiten</button>
          <button class="danger-button" type="button" data-delete="${device.id}">Entfernen</button>
        </div>`;
      cards.append(card);
    });
    content.querySelector("#addDevice").addEventListener("click", () => openDeviceDialog());
    content.querySelectorAll("[data-edit]").forEach((button) => {
      button.addEventListener("click", () =>
        openDeviceDialog(state.devices.find((device) => device.id === button.dataset.edit)),
      );
    });
    content.querySelectorAll("[data-delete]").forEach((button) => {
      button.addEventListener("click", () =>
        openConfirmDialog(state.devices.find((device) => device.id === button.dataset.delete)),
      );
    });
  }

  function openDeviceDialog(device = null) {
    deviceForm.reset();
    document.querySelector("#deviceError").textContent = "";
    document.querySelector("#deviceDialogTitle").textContent = device ? "Gerät bearbeiten" : "Gerät hinzufügen";
    if (device) {
      Object.entries(device).forEach(([key, value]) => {
        if (!deviceForm.elements[key]) return;
        if (deviceForm.elements[key].type === "checkbox") deviceForm.elements[key].checked = Boolean(value);
        else deviceForm.elements[key].value = value ?? "";
      });
    } else {
      deviceForm.elements.id.value = "";
      deviceForm.elements.enabled.checked = true;
      deviceForm.elements.device_type.value = "shelly_pro_3em";
      deviceForm.elements.relay_index.value = "1";
    }
    updateDeviceTypeFields();
    deviceDialog.showModal();
  }

  function updateDeviceTypeFields() {
    const tasmota = deviceForm.elements.device_type.value === "tasmota_plug";
    document.querySelector("#deviceTopicLabel").textContent = tasmota
      ? "MQTT-Gerätetopic"
      : "MQTT-Topic-Präfix";
    document.querySelector("#deviceTopicHelp").textContent = tasmota
      ? "Nur das nackte Topic, zum Beispiel id139_bauwagen"
      : "Zum Beispiel ga/devices/werkstatt";
    deviceForm.elements.controllable.disabled = !tasmota;
    if (!tasmota) deviceForm.elements.controllable.checked = false;
    deviceForm.elements.relay_index.disabled = !tasmota;
  }

  async function submitDevice(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(deviceForm));
    const id = data.id;
    delete data.id;
    data.enabled = deviceForm.elements.enabled.checked;
    data.controllable = deviceForm.elements.controllable.checked;
    data.sort_order = Number(data.sort_order || 0);
    data.relay_index = Number(data.relay_index || 1);
    try {
      const result = await request(id ? `/api/admin/devices/${id}` : "/api/admin/devices", {
        method: id ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      deviceDialog.close();
      showToast("Gerät gespeichert.");
      await renderDevices();
      window.GAApp.loadDevices();
      window.GAApp.loadHistory();
    } catch (error) {
      document.querySelector("#deviceError").textContent = error.message;
    }
  }

  function openConfirmDialog(device) {
    state.deleteDevice = device;
    confirmForm.reset();
    document.querySelector("#confirmError").textContent = "";
    document.querySelector("#confirmDeviceName").textContent = device.name;
    confirmDialog.showModal();
  }

  async function submitDelete(event) {
    event.preventDefault();
    try {
      await request(`/api/admin/devices/${state.deleteDevice.id}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmation: confirmForm.elements.confirmation.value,
          delete_history: confirmForm.elements.delete_history.checked,
        }),
      });
      confirmDialog.close();
      showToast("Gerät wurde entfernt.");
      await renderDevices();
      window.GAApp.loadDevices();
      window.GAApp.loadHistory();
    } catch (error) {
      document.querySelector("#confirmError").textContent = error.message;
    }
  }

  async function renderMqtt() {
    const mqtt = await request("/api/admin/mqtt");
    content.innerHTML = `
      <div class="admin-titlebar"><h3>MQTT-Einstellungen</h3></div>
      <div class="card-grid">
        ${infoCard("Öffentlicher TLS-Endpunkt", {
          Hostname: mqtt.public_hostname,
          Port: mqtt.public_tls_port,
          TLS: "erforderlich",
          "Website (nicht MQTT)": document.body.dataset.publicSite,
        })}
        ${infoCard("Interne Verbindung", {
          Broker: mqtt.broker_hostname,
          Port: mqtt.internal_port,
          ClientID: mqtt.server_client_id,
          Passwort: mqtt.password_configured ? "konfiguriert" : "nicht konfiguriert",
        })}
      </div>
      <h4>Topic-Struktur</h4>
      <pre class="code-block">${escapeHtml(mqtt.topic_status)}\n${escapeHtml(mqtt.topic_online)}</pre>
      <p class="muted">${escapeHtml(mqtt.note)}</p>`;
  }

  async function renderStorage() {
    const storage = await request("/api/admin/storage");
    content.innerHTML = `
      <div class="admin-titlebar">
        <h3>Datenspeicher</h3>
        <button class="secondary-button" id="runCleanup" type="button">Bereinigung prüfen</button>
      </div>
      <div class="card-grid">
        ${infoCard("SQLite", {
          "Hauptdatei": formatBytes(storage.storage.database_bytes),
          WAL: formatBytes(storage.storage.wal_bytes),
          SHM: formatBytes(storage.storage.shm_bytes),
          Gesamt: formatBytes(storage.storage.total_bytes),
          Maximum: formatBytes(storage.storage.max_bytes),
        })}
        ${infoCard("Aufbewahrung", {
          "Minutenzeilen": storage.measurement_rows,
          Ältester: formatDate(storage.oldest),
          Neuester: formatDate(storage.newest),
          "Freier Speicher": formatBytes(storage.storage.free_bytes),
          "Backup-Aufbewahrung": `${storage.backup_retention_days} Tage`,
        })}
      </div>
      <h4>Letzte Bereinigung</h4>
      <pre class="code-block">${escapeHtml(JSON.stringify(storage.last_cleanup || "Noch keine", null, 2))}</pre>`;
    content.querySelector("#runCleanup").addEventListener("click", async () => {
      await request("/api/admin/storage/cleanup", { method: "POST" });
      showToast("Bereinigung wurde ausgeführt.");
      renderStorage();
    });
  }

  async function renderSystem() {
    const system = await request("/api/admin/system");
    content.innerHTML = `
      <div class="admin-titlebar"><h3>Systemstatus</h3></div>
      <div class="card-grid">
        ${infoCard("Prozess", {
          Version: system.version,
          Gestartet: formatDate(system.started_at),
          Laufzeit: formatDuration(system.uptime_seconds),
          Datenbank: system.database_ok ? "bereit" : "Fehler",
        })}
        ${infoCard("Verbindungen", {
          "MQTT initialisiert": system.mqtt_initialized ? "ja" : "nein",
          "MQTT verbunden": system.mqtt_connected ? "ja" : "nein",
          "Letzte MQTT-Nachricht": formatDate(system.mqtt_last_message),
          WebSockets: system.websocket_connections,
          "Aktive Geräte": system.active_devices,
        })}
      </div>`;
  }

  async function renderUsers() {
    const users = await request("/api/admin/users");
    content.innerHTML = `
      <div class="admin-titlebar"><h3>Benutzer</h3></div>
      <div class="card-grid">
        ${users
          .map((user) =>
            infoCard(user.username, {
              Status: user.enabled ? "aktiv" : "deaktiviert",
              Angelegt: formatDate(user.created_at),
              Aktualisiert: formatDate(user.updated_at),
              Hinweis: "Passwörter werden nie angezeigt.",
            }),
          )
          .join("")}
      </div>
      <p class="muted">Weitere Benutzer können über POST /api/admin/users oder die Betreiber-CLI verwaltet werden.</p>`;
  }

  async function renderVersions() {
    const versions = await request("/api/admin/versions");
    content.innerHTML = `
      <div class="admin-titlebar"><h3>Versionshistorie</h3></div>
      <pre class="version-history">${escapeHtml(versions.history)}</pre>`;
  }

  function infoCard(title, values) {
    return `<article class="info-card"><h4>${escapeHtml(title)}</h4><dl class="key-value">
      ${Object.entries(values)
        .map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`)
        .join("")}
    </dl></article>`;
  }

  function formatDate(value) {
    return value ? new Date(value).toLocaleString("de-DE") : "–";
  }

  function formatBytes(value) {
    if (!Number.isFinite(Number(value))) return "–";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = Number(value);
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit += 1;
    }
    return `${size.toFixed(unit ? 1 : 0)} ${units[unit]}`;
  }

  function formatDuration(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  }

  function showToast(message, duration = 4000) {
    const toast = document.querySelector("#toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), duration);
  }

  navigation.addEventListener("click", (event) => {
    const button = event.target.closest("[data-panel]");
    if (button) showPanel(button.dataset.panel);
  });
  document.querySelector("#adminClose").addEventListener("click", close);
  document.querySelector("#logoutButton").addEventListener("click", async () => {
    await request("/api/auth/logout", { method: "POST" });
    state.csrf = null;
    close();
    showToast("Abgemeldet.");
  });
  drawer.addEventListener("pointerdown", (event) => {
    if (event.target === drawer) close();
  });
  deviceForm.elements.device_type.addEventListener("change", updateDeviceTypeFields);
  deviceForm.addEventListener("submit", submitDevice);
  confirmForm.addEventListener("submit", submitDelete);

  window.GAAdmin = { setSession, open, close, showPanel };
})();
