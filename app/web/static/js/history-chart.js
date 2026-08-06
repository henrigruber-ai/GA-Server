/*
File: app/web/static/js/history-chart.js
Version: 0.3.0
Date: 2026-08-06
Purpose: Draws a responsive multi-unit canvas chart with grouped tooltips and mouse/touch zoom.
Changes:
- 0.1.0: Initial implementation.
- 0.2.0: Adds independent series, three labeled scales, gap handling, and persistent zoom.
- 0.3.0: Preserves complete timestamp/value points while merging incremental history.
*/

(() => {
  "use strict";

  const HOURS_24 = 24 * 60 * 60 * 1000;
  const MINUTE = 60 * 1000;
  const METRICS = {
    current: { label: "Strom", unit: "A" },
    voltage: { label: "Spannung", unit: "V" },
    power: { label: "Leistung", unit: "W" },
  };
  const PHASES = { l1: "L1", l2: "L2", l3: "L3", total: "Gesamt" };

  class HistoryChart {
    constructor(canvas, tooltip, options = {}) {
      this.canvas = canvas;
      this.tooltip = tooltip;
      this.context = canvas.getContext("2d");
      this.onZoomChange = options.onZoomChange || (() => {});
      this.series = [];
      this.activeSeries = new Set();
      this.frame = null;
      this.width = 0;
      this.height = 0;
      this.dpr = 1;
      this.plot = { left: 58, top: 76, right: 32, bottom: 54 };
      this.zoom = null;
      this.drag = null;
      this.pointers = new Map();
      this.touchGesture = null;
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(canvas.parentElement);
      this.onWindowResize = () => this.resize();
      this.onOrientation = () => setTimeout(() => this.resize(), 120);
      window.addEventListener("resize", this.onWindowResize, { passive: true });
      window.addEventListener("orientationchange", this.onOrientation);
      canvas.addEventListener("pointerdown", (event) => this.pointerDown(event));
      canvas.addEventListener("pointermove", (event) => this.pointerMove(event));
      canvas.addEventListener("pointerup", (event) => this.pointerUp(event));
      canvas.addEventListener("pointercancel", (event) => this.pointerUp(event));
      canvas.addEventListener("pointerleave", (event) => {
        if (event.pointerType === "mouse" && !this.drag) this.hideTooltip();
      });
      canvas.addEventListener("dblclick", () => this.resetZoom());
      this.onDocumentPointerDown = (event) => {
        if (!canvas.contains(event.target) && !tooltip.contains(event.target)) this.hideTooltip();
      };
      document.addEventListener("pointerdown", this.onDocumentPointerDown);
      this.resize();
    }

    setActiveSeries(keys) {
      this.activeSeries = new Set(keys);
      this.hideTooltip();
      this.resize();
    }

    setSeries(series) {
      this.series = (series || []).map((item) => this.normalizeSeries(item));
      this.resize();
    }

    mergeSeries(series) {
      const byKey = new Map(this.series.map((item) => [item.key, item]));
      const cutoff = Date.now() - 8 * HOURS_24;
      (series || []).forEach((incoming) => {
        const normalized = this.normalizeSeries(incoming);
        const existing = byKey.get(normalized.key);
        if (!existing) {
          byKey.set(normalized.key, normalized);
          return;
        }
        const points = new Map(
          existing.points
            .filter(([timestamp]) => timestamp >= cutoff)
            .map((point) => [point[0], point]),
        );
        normalized.points.forEach((point) => points.set(point[0], point));
        byKey.set(normalized.key, {
          ...existing,
          ...normalized,
          points: [...points.values()].sort((left, right) => left[0] - right[0]),
        });
      });
      this.series = [...byKey.values()];
      this.requestDraw();
    }

    normalizeSeries(item) {
      return {
        ...item,
        points: (item.points || [])
          .map(([time, value]) => [new Date(time).getTime(), Number(value)])
          .filter(([time, value]) => Number.isFinite(time) && Number.isFinite(value)),
      };
    }

    activeItems() {
      return this.series.filter((item) => this.activeSeries.has(item.key));
    }

    activeMetrics() {
      const present = new Set(this.activeItems().map((item) => item.metric));
      return Object.keys(METRICS).filter((metric) => present.has(metric));
    }

    resize() {
      const rectangle = this.canvas.getBoundingClientRect();
      this.width = Math.max(1, rectangle.width);
      this.height = Math.max(1, rectangle.height);
      this.dpr = Math.min(window.devicePixelRatio || 1, 3);
      const pixelWidth = Math.round(this.width * this.dpr);
      const pixelHeight = Math.round(this.height * this.dpr);
      if (this.canvas.width !== pixelWidth || this.canvas.height !== pixelHeight) {
        this.canvas.width = pixelWidth;
        this.canvas.height = pixelHeight;
      }
      this.context.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      const metrics = this.activeMetrics();
      const compact = this.width < 620 || this.height < 500;
      this.plot = {
        left: compact ? 48 : 66,
        top: compact ? 66 : 72,
        right: Math.max(compact ? 14 : 28, (metrics.length - 1) * (compact ? 42 : 58)),
        bottom: compact ? 48 : 58,
      };
      this.requestDraw();
    }

    requestDraw() {
      if (this.frame !== null) return;
      this.frame = requestAnimationFrame(() => {
        this.frame = null;
        this.draw();
      });
    }

    timeBounds() {
      if (this.zoom) return { start: this.zoom.start, end: this.zoom.end };
      const end = Date.now();
      return { start: end - HOURS_24, end };
    }

    metricBounds(metric, time) {
      const values = [];
      for (const item of this.activeItems()) {
        if (item.metric !== metric) continue;
        for (const [timestamp, value] of item.points) {
          if (timestamp >= time.start && timestamp <= time.end) values.push(value);
        }
      }
      if (!values.length) return { minimum: 0, maximum: 1 };
      let minimum = Math.min(...values);
      let maximum = Math.max(...values);
      if (metric !== "power") minimum = Math.max(0, minimum);
      if (minimum === maximum) {
        const margin = Math.max(1, Math.abs(maximum) * 0.1);
        minimum -= margin;
        maximum += margin;
      } else {
        const margin = (maximum - minimum) * 0.1;
        minimum -= margin;
        maximum += margin;
      }
      return { minimum, maximum };
    }

    draw() {
      const context = this.context;
      context.clearRect(0, 0, this.width, this.height);
      const time = this.timeBounds();
      const metrics = this.activeMetrics();
      const bounds = Object.fromEntries(metrics.map((metric) => [metric, this.metricBounds(metric, time)]));
      const plotWidth = this.width - this.plot.left - this.plot.right;
      const plotHeight = this.height - this.plot.top - this.plot.bottom;
      if (plotWidth <= 10 || plotHeight <= 10) return;
      this.drawTimeGrid(time, plotWidth, plotHeight);
      metrics.forEach((metric, index) =>
        this.drawAxis(metric, bounds[metric], index, metrics.length, plotHeight),
      );
      let lineCount = 0;
      for (const item of this.activeItems()) {
        const points = item.points.filter(
          ([timestamp]) => timestamp >= time.start && timestamp <= time.end,
        );
        if (!points.length) continue;
        lineCount += 1;
        context.beginPath();
        context.lineWidth = 2;
        context.strokeStyle = item.color;
        context.setLineDash(item.dash || []);
        context.lineJoin = "round";
        context.lineCap = "round";
        let previousTime = null;
        points.forEach(([timestamp, value]) => {
          const x = this.xFor(timestamp, time, plotWidth);
          const y = this.yFor(value, bounds[item.metric], plotHeight);
          if (previousTime === null || timestamp - previousTime > 2.5 * MINUTE) context.moveTo(x, y);
          else context.lineTo(x, y);
          previousTime = timestamp;
        });
        context.stroke();
      }
      context.setLineDash([]);
      if (!lineCount) this.drawEmptyState(plotWidth, plotHeight);
      if (this.drag) this.drawSelectionRectangle();
    }

    drawTimeGrid(time, plotWidth, plotHeight) {
      const context = this.context;
      const horizontalLines = this.height < 500 ? 3 : 5;
      for (let index = 0; index <= horizontalLines; index += 1) {
        const y = this.plot.top + (index / horizontalLines) * plotHeight;
        context.beginPath();
        context.strokeStyle = "rgba(171,207,226,.13)";
        context.lineWidth = 1;
        context.moveTo(this.plot.left, y);
        context.lineTo(this.plot.left + plotWidth, y);
        context.stroke();
      }
      const desiredLabels = this.width < 420 ? 3 : this.width < 900 ? 5 : 9;
      context.font = `${Math.max(10, Math.min(12, this.width / 110))}px system-ui`;
      context.textBaseline = "top";
      for (let index = 0; index <= desiredLabels; index += 1) {
        const ratio = index / desiredLabels;
        const x = this.plot.left + ratio * plotWidth;
        const timestamp = new Date(time.start + ratio * (time.end - time.start));
        context.beginPath();
        context.strokeStyle = "rgba(171,207,226,.08)";
        context.moveTo(x, this.plot.top);
        context.lineTo(x, this.plot.top + plotHeight);
        context.stroke();
        context.fillStyle = "rgba(192,216,228,.64)";
        context.textAlign = index === 0 ? "left" : index === desiredLabels ? "right" : "center";
        context.fillText(
          timestamp.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }),
          x,
          this.plot.top + plotHeight + 10,
        );
      }
    }

    drawAxis(metric, bounds, index, count, plotHeight) {
      const context = this.context;
      const ticks = this.height < 500 ? 3 : 5;
      const leftSide = index === 0;
      const x = leftSide
        ? this.plot.left - 8
        : this.width - this.plot.right + 8 + (index - 1) * (this.width < 620 ? 40 : 56);
      context.font = `${this.width < 620 ? 9 : 11}px system-ui`;
      context.textAlign = leftSide ? "right" : "left";
      context.textBaseline = "middle";
      context.fillStyle = index === 0 ? "rgba(210,231,240,.72)" : "rgba(186,216,229,.62)";
      for (let tick = 0; tick <= ticks; tick += 1) {
        const ratio = tick / ticks;
        const value = bounds.maximum - ratio * (bounds.maximum - bounds.minimum);
        context.fillText(this.formatAxis(value, metric), x, this.plot.top + ratio * plotHeight);
      }
      context.font = `700 ${this.width < 620 ? 9 : 11}px system-ui`;
      context.textBaseline = "alphabetic";
      const title = `${METRICS[metric].label} · ${this.axisUnit(bounds, metric)}`;
      if (leftSide) {
        context.textAlign = "left";
        context.fillText(title, this.plot.left, this.plot.top - 13);
      } else {
        context.textAlign = "left";
        context.fillText(
          count > 2 ? this.axisUnit(bounds, metric) : title,
          x,
          this.plot.top - 13,
        );
      }
    }

    axisUnit(bounds, metric) {
      return metric === "power" && Math.max(Math.abs(bounds.minimum), Math.abs(bounds.maximum)) >= 1000
        ? "kW"
        : METRICS[metric].unit;
    }

    drawEmptyState(plotWidth, plotHeight) {
      const context = this.context;
      context.fillStyle = "rgba(192,216,228,.58)";
      context.font = "14px system-ui";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(
        this.activeSeries.size
          ? "Keine Minutenwerte für die gewählten Reihen"
          : "Datenreihen in der Legende auswählen",
        this.plot.left + plotWidth / 2,
        this.plot.top + plotHeight / 2,
      );
    }

    drawSelectionRectangle() {
      const context = this.context;
      const left = Math.min(this.drag.startX, this.drag.currentX);
      const right = Math.max(this.drag.startX, this.drag.currentX);
      context.fillStyle = "rgba(33,212,167,.13)";
      context.strokeStyle = "rgba(92,239,201,.8)";
      context.lineWidth = 1;
      context.fillRect(left, this.plot.top, right - left, this.height - this.plot.top - this.plot.bottom);
      context.strokeRect(left, this.plot.top, right - left, this.height - this.plot.top - this.plot.bottom);
    }

    xFor(timestamp, time, width) {
      return this.plot.left + ((timestamp - time.start) / (time.end - time.start)) * width;
    }

    yFor(value, bounds, height) {
      return this.plot.top + (1 - (value - bounds.minimum) / (bounds.maximum - bounds.minimum)) * height;
    }

    formatAxis(value, metric) {
      if (metric === "power" && Math.abs(value) >= 1000) return (value / 1000).toFixed(1);
      const absolute = Math.abs(value);
      if (absolute >= 100) return value.toFixed(0);
      if (absolute >= 10) return value.toFixed(1);
      return value.toFixed(2);
    }

    formatValue(value, metric) {
      if (metric === "power" && Math.abs(value) >= 1000) {
        return `${(value / 1000).toLocaleString("de-DE", { maximumFractionDigits: 2 })} kW`;
      }
      return `${Number(value).toLocaleString("de-DE", {
        maximumFractionDigits: Math.abs(value) >= 100 ? 1 : 2,
      })} ${METRICS[metric].unit}`;
    }

    pointerDown(event) {
      if (event.button !== 0 && event.pointerType === "mouse") return;
      const point = this.eventPoint(event);
      if (!this.inPlot(point.x, point.y)) return;
      try {
        this.canvas.setPointerCapture?.(event.pointerId);
      } catch {
        // Synthetic events and older touch engines may not expose an active capture target.
      }
      if (event.pointerType === "touch") {
        this.pointers.set(event.pointerId, point);
        this.beginTouchGesture();
        this.hideTooltip();
      } else {
        this.drag = { startX: point.x, currentX: point.x };
        this.hideTooltip();
        this.requestDraw();
      }
    }

    pointerMove(event) {
      const point = this.eventPoint(event);
      if (event.pointerType === "touch" && this.pointers.has(event.pointerId)) {
        this.pointers.set(event.pointerId, point);
        this.updateTouchGesture();
        return;
      }
      if (this.drag) {
        this.drag.currentX = this.clampX(point.x);
        this.requestDraw();
      } else if (event.pointerType === "mouse") {
        this.showTooltip(event);
      }
    }

    pointerUp(event) {
      if (event.pointerType === "touch") {
        this.pointers.delete(event.pointerId);
        this.beginTouchGesture();
        return;
      }
      if (!this.drag) return;
      const drag = this.drag;
      this.drag = null;
      if (Math.abs(drag.currentX - drag.startX) >= 8) {
        const time = this.timeBounds();
        const width = this.width - this.plot.left - this.plot.right;
        const first = time.start + ((this.clampX(drag.startX) - this.plot.left) / width) * (time.end - time.start);
        const second = time.start + ((this.clampX(drag.currentX) - this.plot.left) / width) * (time.end - time.start);
        this.setZoom(Math.min(first, second), Math.max(first, second));
      } else {
        this.showTooltip(event);
      }
      this.requestDraw();
    }

    beginTouchGesture() {
      const points = [...this.pointers.values()];
      const time = this.timeBounds();
      if (points.length >= 2) {
        this.touchGesture = {
          kind: "pinch",
          distance: Math.max(1, Math.abs(points[1].x - points[0].x)),
          center: (points[0].x + points[1].x) / 2,
          start: time.start,
          end: time.end,
        };
      } else if (points.length === 1) {
        this.touchGesture = {
          kind: "pan",
          x: points[0].x,
          start: time.start,
          end: time.end,
        };
      } else {
        this.touchGesture = null;
      }
    }

    updateTouchGesture() {
      const points = [...this.pointers.values()];
      const gesture = this.touchGesture;
      const width = this.width - this.plot.left - this.plot.right;
      if (!gesture || width <= 0) return;
      if (gesture.kind === "pinch" && points.length >= 2) {
        const distance = Math.max(1, Math.abs(points[1].x - points[0].x));
        const center = (points[0].x + points[1].x) / 2;
        const originalSpan = gesture.end - gesture.start;
        const span = Math.max(60_000, Math.min(HOURS_24, originalSpan * (gesture.distance / distance)));
        const ratio = (gesture.center - this.plot.left) / width;
        const anchor = gesture.start + ratio * originalSpan;
        const centerShift = ((center - gesture.center) / width) * originalSpan;
        this.setZoom(anchor - ratio * span - centerShift, anchor + (1 - ratio) * span - centerShift);
      } else if (gesture.kind === "pan" && points.length === 1 && this.zoom) {
        const delta = ((points[0].x - gesture.x) / width) * (gesture.end - gesture.start);
        this.setZoom(gesture.start - delta, gesture.end - delta);
      }
    }

    setZoom(start, end) {
      const span = Math.max(60_000, Math.min(HOURS_24, end - start));
      const now = Date.now();
      let boundedEnd = Math.min(now, end);
      let boundedStart = boundedEnd - span;
      const earliest = now - 8 * 24 * 60 * 60 * 1000;
      if (boundedStart < earliest) {
        boundedStart = earliest;
        boundedEnd = earliest + span;
      }
      this.zoom = { start: boundedStart, end: boundedEnd };
      this.onZoomChange(true);
      this.hideTooltip();
      this.requestDraw();
    }

    resetZoom() {
      this.zoom = null;
      this.onZoomChange(false);
      this.hideTooltip();
      this.requestDraw();
    }

    eventPoint(event) {
      const rectangle = this.canvas.getBoundingClientRect();
      return { x: event.clientX - rectangle.left, y: event.clientY - rectangle.top };
    }

    clampX(x) {
      return Math.max(this.plot.left, Math.min(this.width - this.plot.right, x));
    }

    inPlot(x, y) {
      return (
        x >= this.plot.left &&
        x <= this.width - this.plot.right &&
        y >= this.plot.top &&
        y <= this.height - this.plot.bottom
      );
    }

    showTooltip(event) {
      const point = this.eventPoint(event);
      const plotWidth = this.width - this.plot.left - this.plot.right;
      if (!this.inPlot(point.x, point.y)) {
        this.hideTooltip();
        return;
      }
      const time = this.timeBounds();
      const target = time.start + ((point.x - this.plot.left) / plotWidth) * (time.end - time.start);
      const groups = new Map();
      let selectedTime = null;
      const maximumDistance = (time.end - time.start) / Math.max(48, plotWidth / 8);
      for (const item of this.activeItems()) {
        if (!item.points.length) continue;
        const nearest = item.points.reduce((best, candidate) =>
          Math.abs(candidate[0] - target) < Math.abs(best[0] - target) ? candidate : best,
        );
        if (Math.abs(nearest[0] - target) > maximumDistance) continue;
        if (!groups.has(item.device_id)) groups.set(item.device_id, { name: item.name, rows: [] });
        groups.get(item.device_id).rows.push({ item, value: nearest[1] });
        selectedTime = nearest[0];
      }
      if (!groups.size) {
        this.hideTooltip();
        return;
      }
      this.tooltip.replaceChildren();
      const title = document.createElement("div");
      title.className = "tooltip-time";
      title.textContent = new Date(selectedTime).toLocaleString("de-DE", {
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
      this.tooltip.append(title);
      groups.forEach((group) => {
        const heading = document.createElement("strong");
        heading.className = "tooltip-device";
        heading.textContent = group.name;
        this.tooltip.append(heading);
        group.rows.forEach(({ item, value }) => {
          const row = document.createElement("div");
          row.className = "tooltip-row";
          const marker = document.createElement("span");
          marker.className = `series-marker phase-${item.phase}`;
          marker.style.setProperty("--series-color", item.color);
          const name = document.createElement("span");
          name.textContent = `${METRICS[item.metric].label} · ${PHASES[item.phase]}`;
          const output = document.createElement("strong");
          output.textContent = this.formatValue(value, item.metric);
          row.append(marker, name, output);
          this.tooltip.append(row);
        });
      });
      this.tooltip.classList.remove("hidden");
      const tooltipWidth = this.tooltip.offsetWidth;
      const tooltipHeight = this.tooltip.offsetHeight;
      this.tooltip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - tooltipWidth - 8)}px`;
      this.tooltip.style.top = `${Math.max(
        8,
        Math.min(event.clientY - tooltipHeight - 12, window.innerHeight - tooltipHeight - 8),
      )}px`;
    }

    hideTooltip() {
      this.tooltip.classList.add("hidden");
    }

    destroy() {
      this.resizeObserver.disconnect();
      window.removeEventListener("resize", this.onWindowResize);
      window.removeEventListener("orientationchange", this.onOrientation);
      document.removeEventListener("pointerdown", this.onDocumentPointerDown);
      if (this.frame !== null) cancelAnimationFrame(this.frame);
    }
  }

  window.GAHistoryChart = HistoryChart;
})();
