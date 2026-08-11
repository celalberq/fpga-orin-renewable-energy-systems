#!/usr/bin/env python3
"""Live SCADA-style dashboard for UDP solar telemetry."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Solar and BESS Telemetry Dashboard</title>
  <style>
    :root {
      --bg: #f4f6f7;
      --panel: #ffffff;
      --ink: #18212a;
      --muted: #66717c;
      --line: #d6dde3;
      --green: #138a4b;
      --amber: #b46b00;
      --red: #b42318;
      --blue: #1f5f99;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Segoe UI, Arial, sans-serif;
      letter-spacing: 0;
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      background: #16212c;
      color: #fff;
      border-bottom: 1px solid #0f1720;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 16px auto 24px;
    }
    .status-line {
      display: grid;
      grid-template-columns: 1.2fr 1fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      min-width: 0;
    }
    .label {
      color: var(--muted);
      font-size: 12px;
      line-height: 18px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .value {
      font-size: 24px;
      line-height: 32px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }
    .comm-value {
      font-size: 20px;
      line-height: 26px;
      white-space: nowrap;
      overflow-wrap: normal;
    }
    .small-value {
      font-size: 15px;
      line-height: 22px;
      font-weight: 650;
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }
    .detail {
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
      min-height: 32px;
      overflow-wrap: anywhere;
    }
    .ok { color: var(--green); }
    .warn { color: var(--amber); }
    .bad { color: var(--red); }
    .chart-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .chart-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 650;
    }
    canvas {
      width: 100%;
      height: 280px;
      display: block;
      border: 1px solid var(--line);
      background: #fbfcfd;
    }
    .packet {
      font-family: Consolas, monospace;
      font-size: 13px;
      line-height: 18px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    @media (max-width: 900px) {
      .status-line { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      canvas { height: 220px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Solar and BESS Telemetry Dashboard</h1>
    <div id="connection" class="small-value warn">waiting</div>
  </header>
  <main>
    <section class="status-line">
      <div class="panel">
        <div class="label">Source</div>
        <div id="source" class="small-value">Nexys Video auto-MPPT -> UDP gateway</div>
      </div>
      <div class="panel">
        <div class="label">Last packet UTC</div>
        <div id="lastTime" class="small-value">-</div>
      </div>
      <div class="panel">
        <div class="label">Sequence / gaps / bad</div>
        <div id="seqStatus" class="small-value">-</div>
      </div>
    </section>

    <section class="metrics">
      <div class="panel"><div class="label">Power</div><div id="power" class="value">-</div></div>
      <div class="panel"><div class="label">Duty</div><div id="duty" class="value">-</div></div>
      <div class="panel"><div class="label">Voltage</div><div id="voltage" class="value">-</div></div>
      <div class="panel"><div class="label">Current</div><div id="current" class="value">-</div></div>
      <div class="panel"><div class="label">MPPT Status</div><div id="mppt" class="value">-</div><div id="mpptReason" class="detail"></div></div>
      <div class="panel"><div class="label">Protection</div><div id="fault" class="value">-</div><div id="faultReason" class="detail"></div></div>
    </section>

    <section class="metrics">
      <div class="panel"><div class="label">BESS SoC</div><div id="bessSoc" class="value">-</div></div>
      <div class="panel"><div class="label">Battery Power</div><div id="bessPower" class="value">-</div></div>
      <div class="panel"><div class="label">BESS Load</div><div id="bessLoad" class="value">-</div></div>
      <div class="panel"><div class="label">BESS State</div><div id="bessState" class="value">-</div><div id="bessReason" class="detail"></div></div>
      <div class="panel"><div class="label">Stored Energy</div><div id="bessEnergy" class="value">-</div></div>
      <div class="panel"><div class="label">Capacity</div><div id="bessCapacity" class="value">-</div></div>
    </section>

    <section class="metrics">
      <div class="panel"><div class="label">Link State</div><div id="linkState" class="value">-</div><div id="linkReason" class="detail"></div></div>
      <div class="panel"><div class="label">Packet Rate</div><div id="packetRate" class="value">-</div></div>
      <div class="panel"><div class="label">Valid Packets</div><div id="validPackets" class="value">-</div></div>
      <div class="panel"><div class="label">Invalid Packets</div><div id="invalidPackets" class="value">-</div></div>
      <div class="panel"><div class="label">Sequence Gaps</div><div id="sequenceGaps" class="value">-</div></div>
      <div class="panel"><div class="label">Digital Comm Layer</div><div id="commLayer" class="value comm-value">-</div><div id="commDetail" class="detail">Waiting for proje1 bridge metadata.</div></div>
    </section>

    <section class="metrics">
      <div class="panel"><div class="label">Tracker State</div><div id="trackerState" class="value">-</div><div id="trackerReason" class="detail"></div></div>
      <div class="panel"><div class="label">Panel Angles</div><div id="trackerPanel" class="value">-</div></div>
      <div class="panel"><div class="label">Light Direction</div><div id="trackerSun" class="value">-</div></div>
      <div class="panel"><div class="label">Tracking Error</div><div id="trackerError" class="value">-</div></div>
      <div class="panel"><div class="label">LDR Balance</div><div id="trackerBalance" class="small-value">-</div></div>
      <div class="panel"><div class="label">Actuator</div><div id="trackerActuator" class="value">-</div><div id="trackerActuatorReason" class="detail">Waiting for tracker mode.</div></div>
    </section>

    <section class="metrics">
      <div class="panel"><div class="label">Vision Mode</div><div id="visionMode" class="value">-</div><div id="visionReason" class="detail"></div></div>
      <div class="panel"><div class="label">Vision Detection</div><div id="visionDetected" class="value">-</div></div>
      <div class="panel"><div class="label">Vision Confidence</div><div id="visionConfidence" class="value">-</div></div>
      <div class="panel"><div class="label">Target Pixel</div><div id="visionTarget" class="value">-</div></div>
      <div class="panel"><div class="label">Target Offset</div><div id="visionOffset" class="small-value">-</div></div>
      <div class="panel"><div class="label">Frame / Bright Area</div><div id="visionFrame" class="small-value">-</div></div>
    </section>

    <section class="chart-panel">
      <div class="chart-head">
        <h2>Measured Power Trend</h2>
        <div class="label">green: power magnitude, auto-scaled</div>
      </div>
      <canvas id="powerTrend" width="1100" height="240"></canvas>
    </section>

    <section class="chart-panel">
      <div class="chart-head">
        <h2>Duty and BESS SoC Trend</h2>
        <div class="label">blue: duty %, amber: BESS SoC %, fixed 0-100 scale</div>
      </div>
      <canvas id="percentTrend" width="1100" height="240"></canvas>
    </section>

    <section class="chart-panel">
      <div class="chart-head">
        <h2>Latest Raw Packet</h2>
        <div id="packetStatus" class="label">-</div>
      </div>
      <div id="rawPacket" class="packet">waiting for telemetry...</div>
    </section>
  </main>
  <script>
    function text(id, value) {
      document.getElementById(id).textContent = value;
    }
    function setClass(id, cls) {
      const node = document.getElementById(id);
      node.className = node.className.replace(/\\b(ok|warn|bad)\\b/g, "").trim() + " " + cls;
    }
    function formatPowerFromMw(value) {
      if (value === undefined || value === null || value === "") return "-";
      const mw = Number(value);
      if (!Number.isFinite(mw)) return "-";
      const absMw = Math.abs(mw);
      if (absMw < 1000) {
        const digits = absMw < 1 ? 3 : absMw < 10 ? 2 : absMw < 100 ? 1 : 0;
        return mw.toFixed(digits) + " mW";
      }
      return (mw / 1000).toFixed(2) + " W";
    }
    function formatDeg(value) {
      if (value === undefined || value === null || value === "") return "-";
      const deg = Number(value);
      if (!Number.isFinite(deg)) return "-";
      return deg.toFixed(1) + "°";
    }
    function drawGrid(ctx, w, h) {
      ctx.strokeStyle = "#d6dde3";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const y = 24 + i * ((h - 48) / 4);
        ctx.beginPath();
        ctx.moveTo(44, y);
        ctx.lineTo(w - 16, y);
        ctx.stroke();
      }
    }
    function drawPowerTrend(history) {
      const canvas = document.getElementById("powerTrend");
      const ctx = canvas.getContext("2d");
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#fbfcfd";
      ctx.fillRect(0, 0, w, h);
      drawGrid(ctx, w, h);
      ctx.fillStyle = "#66717c";
      ctx.font = "12px Segoe UI, Arial";
      ctx.fillText("0 W", 14, h - 24);
      if (!history || history.length < 2) {
        ctx.fillText("waiting for packets", 48, 48);
        return;
      }
      const points = history.slice(-120);
      const maxPowerMw = Math.max(0.001, ...points.map(p => Math.abs(Number(p.p_mw || 0))));
      const xFor = i => 44 + i * ((w - 60) / Math.max(1, points.length - 1));
      const yPower = p => h - 24 - (Math.abs(Number(p.p_mw || 0)) / maxPowerMw) * (h - 52);
      ctx.strokeStyle = "#138a4b";
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = xFor(i);
        const y = yPower(p);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.fillStyle = "#18212a";
      ctx.fillText("max " + formatPowerFromMw(maxPowerMw), 52, 22);
    }
    function drawPercentTrend(history) {
      const canvas = document.getElementById("percentTrend");
      const ctx = canvas.getContext("2d");
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#fbfcfd";
      ctx.fillRect(0, 0, w, h);
      drawGrid(ctx, w, h);
      ctx.fillStyle = "#66717c";
      ctx.font = "12px Segoe UI, Arial";
      ctx.fillText("100%", 8, 30);
      ctx.fillText("0%", 20, h - 24);
      if (!history || history.length < 2) {
        ctx.fillText("waiting for packets", 48, 48);
        return;
      }
      const points = history.slice(-120);
      const xFor = i => 44 + i * ((w - 60) / Math.max(1, points.length - 1));
      const yPct = value => h - 24 - (Math.max(0, Math.min(100, Number(value || 0))) / 100) * (h - 52);
      ctx.strokeStyle = "#1f5f99";
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = xFor(i);
        const y = yPct(p.d_pct);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.strokeStyle = "#b46b00";
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = xFor(i);
        const y = yPct(p.bess_soc_pct);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
    async function refresh() {
      try {
        const response = await fetch("/api/state", {cache: "no-store"});
        const state = await response.json();
        const latest = state.latest || {};
        const age = Number(state.age_s);
        const connected = Boolean(state.connected);
        text("connection", connected ? "live" : "waiting");
        setClass("connection", connected ? "ok" : "warn");
        text("source", latest.source_label || latest.source || "Nexys Video auto-MPPT -> UDP gateway");
        text("lastTime", latest.timestamp_utc || "-");
        text("seqStatus", "seq=" + (latest.seq ?? "-") + " gaps=" + state.sequence_gaps + " bad=" + state.invalid_packets);
        text("power", formatPowerFromMw(latest.p_mw));
        text("duty", latest.d_pct === undefined ? "-" : latest.d_pct + "%");
        text("voltage", latest.v_mv === undefined ? "-" : (Number(latest.v_mv) / 1000).toFixed(2) + " V");
        text("current", latest.i_ma === undefined ? "-" : (Number(latest.i_ma) / 1000).toFixed(2) + " A");
        text("mppt", latest.mppt_label || latest.mppt || "-");
        text("mpptReason", latest.mppt_reason || "");
        text("fault", latest.fault_label || (latest.fault === 1 ? "FAULT" : latest.fault === 0 ? "OK" : "-"));
        text("faultReason", latest.fault_reason || "");
        setClass("fault", latest.fault === 1 ? "bad" : "ok");
        text("bessSoc", latest.bess_soc_pct === undefined ? "-" : Number(latest.bess_soc_pct).toFixed(1) + "%");
        text("bessPower", latest.bess_power_w === undefined ? "-" : Number(latest.bess_power_w).toFixed(2) + " W");
        text("bessLoad", latest.bess_load_w === undefined ? "-" : Number(latest.bess_load_w).toFixed(1) + " W");
        text("bessState", latest.bess_state || "-");
        text("bessReason", latest.bess_reason || "");
        text("bessEnergy", latest.bess_energy_wh === undefined ? "-" : Number(latest.bess_energy_wh).toFixed(2) + " Wh");
        text("bessCapacity", latest.bess_capacity_wh === undefined ? "-" : Number(latest.bess_capacity_wh).toFixed(2) + " Wh");
        setClass("bessState", latest.bess_state === "charging" ? "ok" : latest.bess_state === "discharging" ? "warn" : "warn");
        const link = state.link || {};
        text("linkState", link.state || "-");
        text("linkReason", link.reason || "");
        text("packetRate", link.packet_rate_hz === undefined ? "-" : Number(link.packet_rate_hz).toFixed(2) + " Hz");
        text("validPackets", link.valid_packets ?? "-");
        text("invalidPackets", link.invalid_packets ?? "-");
        text("sequenceGaps", link.sequence_gaps ?? "-");
        setClass("linkState", link.state === "healthy" || link.state === "recovered" ? "ok" : link.state === "warning" || link.state === "waiting" ? "warn" : "bad");
        const comm = latest.digital_comm || {};
        text("commLayer", comm.layer || "raw UDP");
        if (comm.layer) {
          text("commDetail", comm.frame_bytes + "B frame | " + comm.qpsk_symbols + " QPSK | " + comm.ofdm_symbols + " OFDM | gap " + (comm.bridge_gap ?? 0));
          setClass("commLayer", comm.frame_ok === true && Number(comm.bridge_gap || 0) === 0 ? "ok" : comm.frame_ok === false ? "bad" : "warn");
        } else {
          text("commDetail", "No proje1 bridge metadata in this packet.");
          setClass("commLayer", "warn");
        }
        const tracker = latest.tracker || {};
        text("trackerState", tracker.state || "-");
        text("trackerReason", tracker.reason || "");
        setClass("trackerState", tracker.state === "locked" ? "ok" : tracker.state === "seeking" ? "warn" : "bad");
        text("trackerPanel", tracker.pan_deg === undefined ? "-" : formatDeg(tracker.pan_deg) + " / " + formatDeg(tracker.tilt_deg));
        text("trackerSun", tracker.sun_pan_deg === undefined ? "-" : formatDeg(tracker.sun_pan_deg) + " / " + formatDeg(tracker.sun_tilt_deg));
        text("trackerError", tracker.track_error_deg === undefined ? "-" : formatDeg(tracker.track_error_deg));
        text("trackerBalance", tracker.lr_error === undefined ? "-" : "LR " + Number(tracker.lr_error).toFixed(3) + "  TB " + Number(tracker.tb_error).toFixed(3));
        const servoMode = tracker.servo_mode || (tracker.servo_enabled === true ? "pan+tilt" : "software");
        const actuatorLabel = servoMode === "pan-only" ? "servo (pan only)" : servoMode === "tilt-only" ? "servo (tilt only)" : tracker.servo_enabled === true ? "servo" : tracker.state ? "software" : "-";
        const actuatorReason = servoMode === "pan-only"
          ? "PCA9685 is driving pan; tilt PWM is released."
          : servoMode === "tilt-only"
            ? "PCA9685 is driving tilt; pan PWM is released."
            : tracker.servo_enabled === true
              ? "PCA9685 is driving physical pan/tilt servos."
              : tracker.state
                ? "Angles are computed in software only."
                : "Waiting for tracker mode.";
        text("trackerActuator", actuatorLabel);
        text("trackerActuatorReason", actuatorReason);
        const vision = latest.vision || {};
        const hasVision = Object.keys(vision).length > 0;
        text("visionMode", hasVision ? (vision.mode || "camera") + (vision.camera_mount ? " / " + vision.camera_mount : "") : "-");
        text("visionReason", hasVision ? "Camera/light-source estimate is included in this packet." : "No camera telemetry in this packet.");
        text("visionDetected", hasVision ? (vision.detected ? "yes" : "no") : "-");
        setClass("visionDetected", hasVision ? (vision.detected ? "ok" : "warn") : "warn");
        text("visionConfidence", hasVision && vision.confidence !== undefined ? (Number(vision.confidence) * 100).toFixed(0) + "%" : "-");
        text("visionTarget", hasVision && vision.target_x_px !== null && vision.target_x_px !== undefined ? Number(vision.target_x_px).toFixed(0) + " / " + Number(vision.target_y_px).toFixed(0) : "-");
        text("visionOffset", hasVision && vision.x_error !== undefined ? "X " + Number(vision.x_error).toFixed(3) + "  Y " + Number(vision.y_error).toFixed(3) : "-");
        text("visionFrame", hasVision ? (vision.frame_w || "-") + "x" + (vision.frame_h || "-") + " | area " + (vision.area_px ?? "-") : "-");
        if (hasVision) {
          text("trackerBalance", "CV X " + Number(vision.x_error || 0).toFixed(3) + "  Y " + Number(vision.y_error || 0).toFixed(3));
        }
        text("packetStatus", latest.valid === false ? "invalid" : connected ? "valid" : "waiting");
        text("rawPacket", latest.raw_line || "waiting for telemetry...");
        drawPowerTrend(state.history || []);
        drawPercentTrend(state.history || []);
      } catch (error) {
        text("connection", "server unavailable");
        setClass("connection", "bad");
      }
    }
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""


class BessModel:
    def __init__(
        self,
        capacity_wh: float,
        initial_soc_pct: float,
        load_w: float,
        charge_efficiency: float,
        discharge_efficiency: float,
    ) -> None:
        self.capacity_wh = max(1.0, capacity_wh)
        self.energy_wh = self.capacity_wh * min(100.0, max(0.0, initial_soc_pct)) / 100.0
        self.load_w = max(0.0, load_w)
        self.charge_efficiency = min(1.0, max(0.1, charge_efficiency))
        self.discharge_efficiency = min(1.0, max(0.1, discharge_efficiency))
        self.last_update_s: float | None = None

    def enrich(self, packet: dict[str, Any]) -> dict[str, Any]:
        now_s = time.monotonic()
        dt_s = 0.0 if self.last_update_s is None else max(0.0, min(5.0, now_s - self.last_update_s))
        self.last_update_s = now_s

        if packet.get("bess_measurement_mode") == "real" and packet.get("valid", False):
            measured_capacity_wh = float(packet.get("bess_capacity_wh", self.capacity_wh) or self.capacity_wh)
            if measured_capacity_wh > 0 and measured_capacity_wh != self.capacity_wh:
                soc_fraction = self.energy_wh / self.capacity_wh
                self.capacity_wh = measured_capacity_wh
                self.energy_wh = self.capacity_wh * soc_fraction

            battery = packet.get("battery", {})
            if not isinstance(battery, dict):
                battery = {}
            bess_power_w = float(
                packet.get(
                    "bess_power_w",
                    battery.get("power_w", float(packet.get("p_mw", 0) or 0) / 1000.0),
                )
                or 0
            )
            bess_state = str(packet.get("bess_state", "idle"))
            if bess_state == "charging":
                delta_wh = bess_power_w * self.charge_efficiency * dt_s / 3600.0
            elif bess_state == "discharging":
                delta_wh = bess_power_w * dt_s / (3600.0 * self.discharge_efficiency)
            else:
                delta_wh = 0.0

            self.energy_wh = min(self.capacity_wh, max(0.0, self.energy_wh + delta_wh))
            packet["bess_soc_pct"] = round((self.energy_wh / self.capacity_wh) * 100.0, 3)
            packet["bess_power_w"] = round(bess_power_w, 6)
            packet["bess_load_w"] = round(max(0.0, -bess_power_w), 6)
            packet["bess_energy_wh"] = round(self.energy_wh, 4)
            packet["bess_capacity_wh"] = round(self.capacity_wh, 3)
            packet["bess_soc_basis"] = "Integrated real power from the configured initial SoC."
            return packet

        solar_w = float(packet.get("p_mw", 0) or 0) / 1000.0 if packet.get("valid", False) else 0.0
        net_w = solar_w - self.load_w

        if net_w > 0.05:
            bess_state = "charging"
            bess_power_w = net_w
            delta_wh = bess_power_w * self.charge_efficiency * dt_s / 3600.0
            bess_reason = "Solar power is above the simulated load, so surplus energy charges the battery."
        elif net_w < -0.05:
            bess_state = "discharging"
            bess_power_w = net_w
            delta_wh = bess_power_w * dt_s / (3600.0 * self.discharge_efficiency)
            bess_reason = "Solar power is below the simulated load, so the battery covers the deficit."
        else:
            bess_state = "idle"
            bess_power_w = 0.0
            delta_wh = 0.0
            bess_reason = "Solar power is approximately equal to the simulated load."

        self.energy_wh = min(self.capacity_wh, max(0.0, self.energy_wh + delta_wh))
        soc_pct = (self.energy_wh / self.capacity_wh) * 100.0

        packet["bess_soc_pct"] = round(soc_pct, 3)
        packet["bess_power_w"] = round(bess_power_w, 3)
        packet["bess_load_w"] = round(self.load_w, 3)
        packet["bess_state"] = bess_state
        packet["bess_reason"] = bess_reason
        packet["bess_energy_wh"] = round(self.energy_wh, 4)
        packet["bess_capacity_wh"] = round(self.capacity_wh, 3)
        return packet


class DashboardState:
    def __init__(self, max_history: int, recovery_window: int) -> None:
        self.lock = threading.Lock()
        self.history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self.recovery_window = max(3, recovery_window)
        self.latest: dict[str, Any] = {}
        self.first_receive_monotonic: float | None = None
        self.last_receive_monotonic: float | None = None
        self.total_packets = 0
        self.valid_packets = 0
        self.invalid_packets = 0
        self.sequence_gaps = 0

    def add_packet(self, packet: dict[str, Any]) -> None:
        with self.lock:
            now_s = time.monotonic()
            if self.first_receive_monotonic is None:
                self.first_receive_monotonic = now_s
            self.total_packets += 1
            if packet.get("valid", False):
                self.valid_packets += 1
            else:
                self.invalid_packets += 1
            gap = packet.get("seq_gap")
            if isinstance(gap, int) and gap > 0:
                self.sequence_gaps += gap
            self.latest = packet
            self.history.append(packet)
            self.last_receive_monotonic = now_s

    def snapshot(self, stale_after_s: float) -> dict[str, Any]:
        with self.lock:
            if self.last_receive_monotonic is None:
                age_s = None
                connected = False
            else:
                age_s = time.monotonic() - self.last_receive_monotonic
                connected = age_s <= stale_after_s
            if self.first_receive_monotonic is None:
                packet_rate_hz = 0.0
            else:
                elapsed_s = max(1.0, time.monotonic() - self.first_receive_monotonic)
                packet_rate_hz = self.total_packets / elapsed_s
            recent_packets = list(self.history)[-self.recovery_window :]
            recent_invalid_packets = sum(1 for packet in recent_packets if not packet.get("valid", False))
            recent_sequence_gaps = sum(
                gap for packet in recent_packets if isinstance((gap := packet.get("seq_gap")), int) and gap > 0
            )
            if self.total_packets == 0:
                link_state = "waiting"
                link_reason = "No packets received yet."
            elif not connected:
                link_state = "stale"
                link_reason = "No recent packet has arrived within the dashboard timeout."
            elif recent_invalid_packets > 0 or recent_sequence_gaps > 0:
                link_state = "warning"
                link_reason = (
                    "Recent telemetry contains invalid packets or sequence gaps "
                    f"within the last {len(recent_packets)} packets."
                )
            elif self.invalid_packets > 0 or self.sequence_gaps > 0:
                link_state = "recovered"
                link_reason = (
                    "Earlier packet faults were observed, but the recent telemetry "
                    f"window is clean for {len(recent_packets)} packets."
                )
            else:
                link_state = "healthy"
                link_reason = "Packets are arriving with valid checksum and no sequence gaps."
            return {
                "connected": connected,
                "age_s": age_s,
                "invalid_packets": self.invalid_packets,
                "sequence_gaps": self.sequence_gaps,
                "link": {
                    "state": link_state,
                    "reason": link_reason,
                    "packet_rate_hz": round(packet_rate_hz, 3),
                    "total_packets": self.total_packets,
                    "valid_packets": self.valid_packets,
                    "invalid_packets": self.invalid_packets,
                    "sequence_gaps": self.sequence_gaps,
                    "recent_packets": len(recent_packets),
                    "recent_invalid_packets": recent_invalid_packets,
                    "recent_sequence_gaps": recent_sequence_gaps,
                    "recovery_window": self.recovery_window,
                },
                "latest": self.latest,
                "history": list(self.history),
            }


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live dashboard for proje2 UDP solar telemetry.")
    parser.add_argument("--udp-host", default="127.0.0.1", help="UDP bind host.")
    parser.add_argument("--udp-port", type=int, default=5006, help="UDP bind port.")
    parser.add_argument("--http-host", default="127.0.0.1", help="HTTP dashboard host.")
    parser.add_argument("--http-port", type=int, default=8080, help="HTTP dashboard port.")
    parser.add_argument("--log", type=Path, default=Path("proje2/data/solar_live_dashboard_log.csv"))
    parser.add_argument("--history", type=int, default=240, help="Maximum packets kept for the chart.")
    parser.add_argument("--stale-after", type=float, default=5.0, help="Seconds before dashboard shows waiting.")
    parser.add_argument("--recovery-window", type=int, default=20, help="Clean recent packets needed for recovered link state.")
    parser.add_argument("--bess-capacity-wh", type=float, default=50.0, help="Simulated BESS capacity.")
    parser.add_argument("--bess-initial-soc", type=float, default=55.0, help="Initial BESS state of charge.")
    parser.add_argument("--bess-load-w", type=float, default=10.0, help="Simulated load supplied by solar/BESS.")
    parser.add_argument("--bess-charge-eff", type=float, default=0.95, help="Charge efficiency.")
    parser.add_argument("--bess-discharge-eff", type=float, default=0.95, help="Discharge efficiency.")
    return parser.parse_args()


def open_log(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)
    if path.stat().st_size == 0:
        writer.writerow(
            [
                "received_utc",
                "valid",
                "error",
                "seq_gap",
                "seq",
                "d_pct",
                "v_mv",
                "i_ma",
                "p_mw",
                "mppt",
                "fault",
                "fault_label",
                "fault_reason",
                "fault_severity",
                "chk",
                "computed_chk",
                "bess_soc_pct",
                "bess_power_w",
                "bess_load_w",
                "bess_state",
                "bess_energy_wh",
                "bess_capacity_wh",
                "tracker_state",
                "tracker_pan_deg",
                "tracker_tilt_deg",
                "tracker_sun_pan_deg",
                "tracker_sun_tilt_deg",
                "tracker_error_deg",
                "tracker_servo_enabled",
                "vision_mode",
                "vision_detected",
                "vision_confidence",
                "vision_target_x_px",
                "vision_target_y_px",
                "vision_x_error",
                "vision_y_error",
                "vision_frame_w",
                "vision_frame_h",
                "vision_brightness_max",
                "vision_area_px",
                "comm_layer",
                "comm_frame_ok",
                "comm_bridge_gap",
                "comm_payload_bytes",
                "comm_frame_bytes",
                "comm_frame_bits",
                "comm_qpsk_symbols",
                "comm_ofdm_symbols",
                "comm_pad_q",
                "comm_tx_samples",
                "comm_cp_samples",
                "comm_pilot_bins",
                "comm_status_line",
                "raw_line",
                "source_label",
            ]
        )
    return file_handle, writer


def write_log(writer, packet: dict[str, Any]) -> None:
    tracker = packet.get("tracker", {})
    if not isinstance(tracker, dict):
        tracker = {}
    comm = packet.get("digital_comm", {})
    if not isinstance(comm, dict):
        comm = {}
    vision = packet.get("vision", {})
    if not isinstance(vision, dict):
        vision = {}
    writer.writerow(
        [
            datetime.now(timezone.utc).isoformat(),
            int(bool(packet.get("valid", False))),
            packet.get("error", ""),
            "" if packet.get("seq_gap") is None else packet.get("seq_gap"),
            packet.get("seq", ""),
            packet.get("d_pct", ""),
            packet.get("v_mv", ""),
            packet.get("i_ma", ""),
            packet.get("p_mw", ""),
            packet.get("mppt", ""),
            packet.get("fault", ""),
            packet.get("fault_label", ""),
            packet.get("fault_reason", ""),
            packet.get("fault_severity", ""),
            packet.get("chk", ""),
            packet.get("computed_chk", ""),
            packet.get("bess_soc_pct", ""),
            packet.get("bess_power_w", ""),
            packet.get("bess_load_w", ""),
            packet.get("bess_state", ""),
            packet.get("bess_energy_wh", ""),
            packet.get("bess_capacity_wh", ""),
            tracker.get("state", ""),
            tracker.get("pan_deg", ""),
            tracker.get("tilt_deg", ""),
            tracker.get("sun_pan_deg", ""),
            tracker.get("sun_tilt_deg", ""),
            tracker.get("track_error_deg", ""),
            "" if "servo_enabled" not in tracker else int(bool(tracker.get("servo_enabled"))),
            vision.get("mode", ""),
            "" if "detected" not in vision else int(bool(vision.get("detected"))),
            vision.get("confidence", ""),
            vision.get("target_x_px", ""),
            vision.get("target_y_px", ""),
            vision.get("x_error", ""),
            vision.get("y_error", ""),
            vision.get("frame_w", ""),
            vision.get("frame_h", ""),
            vision.get("brightness_max", ""),
            vision.get("area_px", ""),
            comm.get("layer", ""),
            "" if "frame_ok" not in comm else int(bool(comm.get("frame_ok"))),
            comm.get("bridge_gap", ""),
            comm.get("payload_bytes", ""),
            comm.get("frame_bytes", ""),
            comm.get("frame_bits", ""),
            comm.get("qpsk_symbols", ""),
            comm.get("ofdm_symbols", ""),
            comm.get("pad_q", ""),
            comm.get("tx_samples", ""),
            comm.get("cp_samples", ""),
            comm.get("pilot_bins", ""),
            comm.get("status_line", ""),
            packet.get("raw_line", ""),
            packet.get("source_label", ""),
        ]
    )


def udp_worker(host: str, port: int, state: DashboardState, log_path: Path, bess_model: BessModel) -> None:
    csv_file, writer = open_log(log_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
        print(f"UDP dashboard input listening on {host}:{port}")
        while True:
            payload, _address = sock.recvfrom(8192)
            try:
                packet = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                packet = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "valid": False,
                    "error": f"bad_json: {exc}",
                    "raw_line": payload.hex(),
                }
            packet = bess_model.enrich(packet)
            state.add_packet(packet)
            write_log(writer, packet)
            csv_file.flush()
    finally:
        csv_file.close()
        sock.close()


def make_handler(state: DashboardState, stale_after_s: float):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path.startswith("/?"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode("utf-8"))
                return

            if self.path == "/api/state":
                payload = json.dumps(state.snapshot(stale_after_s), separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return DashboardHandler


def main() -> int:
    configure_stdout()
    args = parse_args()
    state = DashboardState(args.history, args.recovery_window)
    bess_model = BessModel(
        capacity_wh=args.bess_capacity_wh,
        initial_soc_pct=args.bess_initial_soc,
        load_w=args.bess_load_w,
        charge_efficiency=args.bess_charge_eff,
        discharge_efficiency=args.bess_discharge_eff,
    )

    udp_thread = threading.Thread(
        target=udp_worker,
        args=(args.udp_host, args.udp_port, state, args.log, bess_model),
        daemon=True,
    )
    udp_thread.start()

    handler = make_handler(state, args.stale_after)
    server = ThreadingHTTPServer((args.http_host, args.http_port), handler)

    print(f"Dashboard URL: http://{args.http_host}:{args.http_port}")
    print(f"Send gateway UDP to {args.udp_host}:{args.udp_port}")
    print(f"BESS model: {args.bess_capacity_wh:.1f} Wh, load {args.bess_load_w:.1f} W")
    print(f"Logging to {args.log}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
