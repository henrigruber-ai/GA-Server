/*
File: app/web/static/js/history-chart.js
Version: 0.1.0
Date: 2026-08-03
Purpose: Draws the responsive rolling 24-hour multi-device canvas graph with mouse and touch detail.
Changes:
- 0.1.0: Initial implementation.
*/

(() => {
  "use strict";

  const HOURS_24 = 24 * 60 * 60 * 1000;
  const METRIC_LABELS = {
    current: ["Strom", "A"],
    voltage: ["Spannung", "V"],
    power: ["Leistung", "W"],
  };

  class HistoryChart {
    constructor(canvas, tooltip) {
      this.canvas = canvas;
      this.tooltip = tooltip;
      this.context = canvas.getContext("2d");
      this.series = [];
      this.visibleDevices = new Set();
      this.metric = "power";
      this.phase = "total";
      this.frame = null;
      this.width = 0;
      this.height = 0;
      this.dpr = 1;
      this.plot = { left: 60, top: 94, right: 20, bottom: 66 };
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(canvas.parentElement);
      window.addEventListener("resize", () => this.resize(), { passive: true });
      window.addEventListener("orientationchange", () => setTimeout(() => this.resize(), 120));
      canvas.addEventListener("pointermove", (event) => this.showTooltip(event));
      canvas.addEventListener("pointerdown", (event) => this.showTooltip(event));
      canvas.addEventListener("pointerleave", () => this.hideTooltip());
      document.addEventListener("pointerdown", (event) => {
        if (!canvas.contains(event.target) && !tooltip.contains(event.target)) this.hideTooltip();
      });
      this.resize();
    }

    setSelection(metric, phase) {
      this.metric = metric;
      this.phase = phase;
      this.hideTooltip();
      this.requestDraw();
    }

    setVisibleDevices(ids) {
      this.visibleDevices = new Set(ids);
      this.requestDraw();
    }

    setSeries(series) {
      this.series = (series || []).map((item) => ({
        ...item,
        points: (item.points || [])
          .map(([time, value]) => [new Date(time).getTime(), Number(value)])
          .filter(([time, value]) => Number.isFinite(time) && Number.isFinite(value)),
      }));
      this.requestDraw();
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
      const compact = this.width < 620 || this.height < 520;
      this.plot = {
        left: compact ? 45 : 64,
        top: compact ? 112 : 94,
        right: compact ? 12 : 28,
        bottom: compact ? 128 : 64,
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

    bounds() {
      const end = Date.now();
      const start = end - HOURS_24;
      const values = [];
      for (const item of this.series) {
        if (!this.visibleDevices.has(item.device_id)) continue;
        for (const [time, value] of item.points) {
          if (time >= start && time <= end) values.push(value);
        }
      }
      if (!values.length) return { start, end, minimum: 0, maximum: 1 };
      let minimum = Math.min(...values);
      let maximum = Math.max(...values);
      if (this.metric !== "power") minimum = Math.max(0, minimum);
      if (minimum === maximum) {
        const margin = Math.max(1, Math.abs(maximum) * 0.1);
        minimum -= margin;
        maximum += margin;
      } else {
        const margin = (maximum - minimum) * 0.1;
        minimum -= margin;
        maximum += margin;
      }
      return { start, end, minimum, maximum };
    }

    draw() {
      const context = this.context;
      context.clearRect(0, 0, this.width, this.height);
      const bounds = this.bounds();
      const plotWidth = this.width - this.plot.left - this.plot.right;
      const plotHeight = this.height - this.plot.top - this.plot.bottom;
      if (plotWidth <= 10 || plotHeight <= 10) return;
      this.drawGrid(bounds, plotWidth, plotHeight);
      let lineCount = 0;
      for (const item of this.series) {
        if (!this.visibleDevices.has(item.device_id)) continue;
        const points = item.points.filter(([time]) => time >= bounds.start && time <= bounds.end);
        if (!points.length) continue;
        lineCount += 1;
        context.beginPath();
        context.lineWidth = 2;
        context.strokeStyle = item.color;
        context.lineJoin = "round";
        context.lineCap = "round";
        points.forEach(([time, value], index) => {
          const x = this.xFor(time, bounds, plotWidth);
          const y = this.yFor(value, bounds, plotHeight);
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        context.stroke();
      }
      if (!lineCount) this.drawEmptyState(plotWidth, plotHeight);
    }

    drawGrid(bounds, plotWidth, plotHeight) {
      const context = this.context;
      const horizontalLines = this.height < 520 ? 3 : 5;
      context.font = `${Math.max(10, Math.min(13, this.width / 110))}px system-ui`;
      context.textBaseline = "middle";
      for (let index = 0; index <= horizontalLines; index += 1) {
        const ratio = index / horizontalLines;
        const y = this.plot.top + ratio * plotHeight;
        const value = bounds.maximum - ratio * (bounds.maximum - bounds.minimum);
        context.beginPath();
        context.strokeStyle = "rgba(171,207,226,.13)";
        context.lineWidth = 1;
        context.moveTo(this.plot.left, y);
        context.lineTo(this.plot.left + plotWidth, y);
        context.stroke();
        context.fillStyle = "rgba(192,216,228,.64)";
        context.textAlign = "right";
        context.fillText(this.formatValue(value), this.plot.left - 9, y);
      }
      const desiredLabels = this.width < 420 ? 4 : this.width < 900 ? 6 : 10;
      context.textBaseline = "top";
      for (let index = 0; index <= desiredLabels; index += 1) {
        const ratio = index / desiredLabels;
        const x = this.plot.left + ratio * plotWidth;
        const time = new Date(bounds.start + ratio * (bounds.end - bounds.start));
        context.beginPath();
        context.strokeStyle = "rgba(171,207,226,.08)";
        context.moveTo(x, this.plot.top);
        context.lineTo(x, this.plot.top + plotHeight);
        context.stroke();
        context.fillStyle = "rgba(192,216,228,.58)";
        context.textAlign = index === 0 ? "left" : index === desiredLabels ? "right" : "center";
        context.fillText(
          time.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }),
          x,
          this.plot.top + plotHeight + 12,
        );
      }
      context.fillStyle = "rgba(239,248,252,.8)";
      context.textAlign = "left";
      context.textBaseline = "alphabetic";
      context.font = `600 ${this.width < 500 ? 11 : 13}px system-ui`;
      const [label, unit] = METRIC_LABELS[this.metric];
      context.fillText(`${label} ${this.phase.toUpperCase()} · ${unit}`, this.plot.left, this.plot.top - 14);
    }

    drawEmptyState(plotWidth, plotHeight) {
      const context = this.context;
      context.fillStyle = "rgba(192,216,228,.52)";
      context.font = "14px system-ui";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(
        "Noch keine Minutenwerte für diese Auswahl",
        this.plot.left + plotWidth / 2,
        this.plot.top + plotHeight / 2,
      );
    }

    xFor(time, bounds, width) {
      return this.plot.left + ((time - bounds.start) / (bounds.end - bounds.start)) * width;
    }

    yFor(value, bounds, height) {
      return (
        this.plot.top +
        (1 - (value - bounds.minimum) / (bounds.maximum - bounds.minimum)) * height
      );
    }

    formatValue(value) {
      const absolute = Math.abs(value);
      if (absolute >= 1000) return `${(value / 1000).toFixed(1)}k`;
      if (absolute >= 100) return value.toFixed(0);
      if (absolute >= 10) return value.toFixed(1);
      return value.toFixed(2);
    }

    showTooltip(event) {
      const rectangle = this.canvas.getBoundingClientRect();
      const pointerX = event.clientX - rectangle.left;
      const plotWidth = this.width - this.plot.left - this.plot.right;
      if (pointerX < this.plot.left || pointerX > this.plot.left + plotWidth) {
        this.hideTooltip();
        return;
      }
      const bounds = this.bounds();
      const targetTime =
        bounds.start + ((pointerX - this.plot.left) / plotWidth) * (bounds.end - bounds.start);
      const rows = [];
      let selectedTime = null;
      const maximumDistance = (bounds.end - bounds.start) / Math.max(48, plotWidth / 8);
      for (const item of this.series) {
        if (!this.visibleDevices.has(item.device_id) || !item.points.length) continue;
        const nearest = item.points.reduce((best, point) =>
          Math.abs(point[0] - targetTime) < Math.abs(best[0] - targetTime) ? point : best,
        );
        if (Math.abs(nearest[0] - targetTime) <= maximumDistance) {
          rows.push({ name: item.name, color: item.color, value: nearest[1] });
          selectedTime = nearest[0];
        }
      }
      if (!rows.length) {
        this.hideTooltip();
        return;
      }
      const unit = METRIC_LABELS[this.metric][1];
      this.tooltip.replaceChildren();
      const title = document.createElement("div");
      title.className = "tooltip-time";
      title.textContent = new Date(selectedTime).toLocaleString("de-DE", {
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
      this.tooltip.append(title);
      rows.forEach((row) => {
        const element = document.createElement("div");
        element.className = "tooltip-row";
        const name = document.createElement("span");
        name.textContent = row.name;
        name.style.color = row.color;
        const value = document.createElement("strong");
        value.textContent = `${this.formatValue(row.value)} ${unit}`;
        element.append(name, value);
        this.tooltip.append(element);
      });
      this.tooltip.classList.remove("hidden");
      const tooltipWidth = this.tooltip.offsetWidth;
      const tooltipHeight = this.tooltip.offsetHeight;
      this.tooltip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - tooltipWidth - 8)}px`;
      this.tooltip.style.top = `${Math.max(8, Math.min(event.clientY - tooltipHeight - 12, window.innerHeight - tooltipHeight - 8))}px`;
    }

    hideTooltip() {
      this.tooltip.classList.add("hidden");
    }
  }

  window.GAHistoryChart = HistoryChart;
})();
