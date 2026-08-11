#!/usr/bin/env python3
"""Build report-ready evidence from tracker, network, and comm logs."""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


TRACKER_PACKET_RE = re.compile(
    r"trk,seq=(?P<seq>\d+),pan=(?P<pan>-?\d+(?:\.\d+)?),"
    r"tilt=(?P<tilt>-?\d+(?:\.\d+)?),sun_pan=(?P<sun_pan>-?\d+(?:\.\d+)?),"
    r"sun_tilt=(?P<sun_tilt>-?\d+(?:\.\d+)?),err=(?P<err>-?\d+(?:\.\d+)?),"
    r"(?:state|st)=(?P<state>[A-Za-z0-9_]+)"
)


@dataclass
class TrackerRow:
    timestamp: str
    seq: int | None
    valid: bool
    gap: int
    voltage_mv: float | None
    current_ma: float | None
    power_mw: float | None
    tracker_state: str
    pan_deg: float | None
    tilt_deg: float | None
    sun_pan_deg: float | None
    sun_tilt_deg: float | None
    error_deg: float | None
    raw_line: str


@dataclass
class BridgeRow:
    timestamp: str
    seq: int | None
    gap: int
    frame_ok: bool
    payload_bytes: int | None
    frame_bytes: int | None
    frame_bits: int | None
    qpsk_symbols: int | None
    ofdm_symbols: int | None
    pad_q: int | None
    tx_samples: int | None
    cp_samples: int | None
    pilot_bins: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build tracker system evidence report.")
    parser.add_argument("--dashboard-log", type=Path, default=Path("proje2/data/solar_live_dashboard_ldr_servo_log.csv"))
    parser.add_argument("--bridge-log", type=Path, default=Path("proje1/data/ldr_tracker_udp_comm_bridge_servo_log.csv"))
    parser.add_argument("--ab-metrics", type=Path, default=Path("proje3/data/solar_tracking_ab_metrics.csv"))
    parser.add_argument(
        "--fault-dashboard-log",
        type=Path,
        default=Path("proje2/data/solar_live_dashboard_ldr_fault_final.csv"),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("main_layout/reports"))
    parser.add_argument("--last", type=int, default=240, help="Use the last N tracker rows for plots.")
    return parser.parse_args()


def to_int(value: object) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def to_float(value: object) -> float | None:
    try:
        if value in ("", None):
            return None
        number = float(str(value))
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_tracker_raw(raw_line: str) -> dict[str, object]:
    match = TRACKER_PACKET_RE.search(raw_line)
    if not match:
        return {}
    values = match.groupdict()
    return {
        "seq": to_int(values.get("seq")),
        "pan": to_float(values.get("pan")),
        "tilt": to_float(values.get("tilt")),
        "sun_pan": to_float(values.get("sun_pan")),
        "sun_tilt": to_float(values.get("sun_tilt")),
        "err": to_float(values.get("err")),
        "state": values.get("state", ""),
    }


def read_dashboard_rows(path: Path) -> list[TrackerRow]:
    if not path.exists():
        return []

    rows: list[TrackerRow] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row or row[0] == "received_utc":
                continue

            raw_line = ""
            if len(row) >= 27:
                raw_line = row[26]
            elif len(row) >= 14:
                raw_line = row[13]

            parsed_raw = parse_tracker_raw(raw_line)
            is_tracker = raw_line.startswith("trk,") or bool(parsed_raw) or (len(row) >= 20 and bool(row[19]))
            if not is_tracker:
                continue

            seq = to_int(row[4]) if len(row) > 4 else None
            pan = to_float(row[20]) if len(row) > 20 else None
            tilt = to_float(row[21]) if len(row) > 21 else None
            sun_pan = to_float(row[22]) if len(row) > 22 else None
            sun_tilt = to_float(row[23]) if len(row) > 23 else None
            error = to_float(row[24]) if len(row) > 24 else None
            state = row[19] if len(row) > 19 else ""

            rows.append(
                TrackerRow(
                    timestamp=row[0],
                    seq=seq if seq is not None else parsed_raw.get("seq"),  # type: ignore[arg-type]
                    valid=(row[1] == "1") if len(row) > 1 else False,
                    gap=(to_int(row[3]) or 0) if len(row) > 3 else 0,
                    voltage_mv=to_float(row[6]) if len(row) > 6 else None,
                    current_ma=to_float(row[7]) if len(row) > 7 else None,
                    power_mw=to_float(row[8]) if len(row) > 8 else None,
                    tracker_state=state or str(parsed_raw.get("state", "")),
                    pan_deg=pan if pan is not None else parsed_raw.get("pan"),  # type: ignore[arg-type]
                    tilt_deg=tilt if tilt is not None else parsed_raw.get("tilt"),  # type: ignore[arg-type]
                    sun_pan_deg=sun_pan if sun_pan is not None else parsed_raw.get("sun_pan"),  # type: ignore[arg-type]
                    sun_tilt_deg=sun_tilt if sun_tilt is not None else parsed_raw.get("sun_tilt"),  # type: ignore[arg-type]
                    error_deg=error if error is not None else parsed_raw.get("err"),  # type: ignore[arg-type]
                    raw_line=raw_line,
                )
            )
    return rows


def read_bridge_rows(path: Path) -> list[BridgeRow]:
    if not path.exists():
        return []

    rows: list[BridgeRow] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                BridgeRow(
                    timestamp=row.get("timestamp_utc", ""),
                    seq=to_int(row.get("seq")),
                    gap=to_int(row.get("gap")) or 0,
                    frame_ok=row.get("frame_ok") == "1",
                    payload_bytes=to_int(row.get("payload_bytes")),
                    frame_bytes=to_int(row.get("frame_bytes")),
                    frame_bits=to_int(row.get("frame_bits")),
                    qpsk_symbols=to_int(row.get("qpsk_symbols")),
                    ofdm_symbols=to_int(row.get("ofdm_symbols")),
                    pad_q=to_int(row.get("pad_q")),
                    tx_samples=to_int(row.get("tx_samples")),
                    cp_samples=to_int(row.get("cp_samples")),
                    pilot_bins=to_int(row.get("pilot_bins")),
                )
            )
    return rows


def values(rows: Iterable[object], attr: str) -> list[float]:
    result = []
    for row in rows:
        value = getattr(row, attr)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result.append(float(value))
    return result


def avg(numbers: list[float]) -> float | None:
    return sum(numbers) / len(numbers) if numbers else None


def fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def duration_seconds(timestamps: list[str]) -> float | None:
    parsed = [stamp for stamp in (parse_time(item) for item in timestamps) if stamp is not None]
    if len(parsed) < 2:
        return None
    return (max(parsed) - min(parsed)).total_seconds()


def tracker_rows_for_bridge_window(tracker_rows: list[TrackerRow], bridge_rows: list[BridgeRow]) -> list[TrackerRow]:
    bridge_times = [stamp for stamp in (parse_time(row.timestamp) for row in bridge_rows) if stamp is not None]
    if not bridge_times:
        return []

    start = min(bridge_times).timestamp() - 2.0
    end = max(bridge_times).timestamp() + 2.0
    aligned = []
    for row in tracker_rows:
        timestamp = parse_time(row.timestamp)
        if timestamp is None:
            continue
        if start <= timestamp.timestamp() <= end:
            aligned.append(row)
    return aligned


def unique_value(rows: list[object], attr: str) -> object:
    found = sorted({getattr(row, attr) for row in rows if getattr(row, attr) is not None})
    if len(found) == 1:
        return found[0]
    if not found:
        return None
    return "/".join(str(item) for item in found)


def read_ab_metrics(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []

    result: list[tuple[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            metric = row.get("metric", "")
            fixed = row.get("fixed", "")
            tracking = row.get("tracking", "")
            if metric == "power_mean_mw":
                result.extend(
                    [
                        ("ab_fixed_mean_power_mw", fixed),
                        ("ab_tracking_mean_power_mw", tracking),
                    ]
                )
            elif metric == "energy_mwh":
                result.extend(
                    [
                        ("ab_fixed_energy_mwh", fixed),
                        ("ab_tracking_energy_mwh", tracking),
                    ]
                )
            elif metric == "power_gain_pct":
                result.append(("ab_power_gain_pct", tracking))
            elif metric == "energy_gain_pct":
                result.append(("ab_energy_gain_pct", tracking))
            elif metric == "locked_pct":
                result.append(("ab_tracking_locked_pct", tracking))
    return result


def read_fault_metrics(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("valid") == "1"]

    labels = [row.get("fault_label", "") for row in rows]
    first_shading_index = next((index for index, label in enumerate(labels) if label == "Shading"), None)
    recovery_row = None
    if first_shading_index is not None:
        recovery_row = next(
            (row for row in rows[first_shading_index + 1 :] if row.get("fault_label") == "OK"),
            None,
        )

    def first_seq(label: str) -> str:
        row = next((item for item in rows if item.get("fault_label") == label), None)
        return row.get("seq", "n/a") if row else "n/a"

    return [
        ("fault_valid_rows", str(len(rows))),
        ("fault_sequence_gaps", str(sum(to_int(row.get("seq_gap")) or 0 for row in rows))),
        ("fault_learning_first_seq", first_seq("Learning")),
        ("fault_ok_first_seq", first_seq("OK")),
        ("fault_shading_first_seq", first_seq("Shading")),
        ("fault_shading_rows", str(labels.count("Shading"))),
        ("fault_recovery_seq", recovery_row.get("seq", "n/a") if recovery_row else "n/a"),
        ("fault_recovered", "yes" if recovery_row else "no"),
    ]


def metric_rows(tracker_rows: list[TrackerRow], bridge_rows: list[BridgeRow]) -> list[tuple[str, str]]:
    valid_tracker = [row for row in tracker_rows if row.valid]
    locked_tracker = [row for row in valid_tracker if row.tracker_state.lower().startswith("lock")]
    errors = values(valid_tracker, "error_deg")
    power = values(valid_tracker, "power_mw")
    pan = values(valid_tracker, "pan_deg")
    tilt = values(valid_tracker, "tilt_deg")
    frame_ok = [row for row in bridge_rows if row.frame_ok]

    first_error = errors[0] if errors else None
    last_error = errors[-1] if errors else None
    error_delta = (first_error - last_error) if first_error is not None and last_error is not None else None
    best_error_row = min(
        (row for row in valid_tracker if row.error_deg is not None),
        key=lambda row: row.error_deg if row.error_deg is not None else float("inf"),
        default=None,
    )
    under_10_deg_rows = [row for row in valid_tracker if row.error_deg is not None and row.error_deg <= 10.0]

    return [
        ("tracker_rows", str(len(tracker_rows))),
        ("tracker_valid_rows", str(len(valid_tracker))),
        ("tracker_sequence_gaps", str(sum(row.gap for row in valid_tracker))),
        ("tracker_duration_seconds", fmt(duration_seconds([row.timestamp for row in valid_tracker]), 1)),
        ("tracking_locked_rows", str(len(locked_tracker))),
        ("tracking_locked_pct", fmt((100.0 * len(locked_tracker) / len(valid_tracker)) if valid_tracker else None, 1)),
        ("tracking_under_10deg_rows", str(len(under_10_deg_rows))),
        ("tracking_error_first_deg", fmt(first_error, 3)),
        ("tracking_error_last_deg", fmt(last_error, 3)),
        ("tracking_error_reduction_deg", fmt(error_delta, 3)),
        ("tracking_error_best_deg", fmt(best_error_row.error_deg if best_error_row else None, 3)),
        ("tracking_error_best_seq", fmt(best_error_row.seq if best_error_row else None)),
        ("tracking_error_min_deg", fmt(min(errors) if errors else None, 3)),
        ("tracking_error_max_deg", fmt(max(errors) if errors else None, 3)),
        ("tracking_error_avg_deg", fmt(avg(errors), 3)),
        ("power_max_mw", fmt(max(power) if power else None, 3)),
        ("power_avg_mw", fmt(avg(power), 3)),
        ("pan_min_deg", fmt(min(pan) if pan else None, 3)),
        ("pan_max_deg", fmt(max(pan) if pan else None, 3)),
        ("tilt_min_deg", fmt(min(tilt) if tilt else None, 3)),
        ("tilt_max_deg", fmt(max(tilt) if tilt else None, 3)),
        ("bridge_rows", str(len(bridge_rows))),
        ("bridge_frame_ok_rows", str(len(frame_ok))),
        ("bridge_sequence_gaps", str(sum(row.gap for row in bridge_rows))),
        ("payload_bytes", fmt(unique_value(frame_ok, "payload_bytes"))),
        ("frame_bytes", fmt(unique_value(frame_ok, "frame_bytes"))),
        ("frame_bits", fmt(unique_value(frame_ok, "frame_bits"))),
        ("qpsk_symbols", fmt(unique_value(frame_ok, "qpsk_symbols"))),
        ("ofdm_symbols", fmt(unique_value(frame_ok, "ofdm_symbols"))),
        ("qpsk_pad_symbols", fmt(unique_value(frame_ok, "pad_q"))),
        ("ofdm_tx_samples", fmt(unique_value(frame_ok, "tx_samples"))),
        ("ofdm_cp_samples", fmt(unique_value(frame_ok, "cp_samples"))),
        ("ofdm_pilot_bins", fmt(unique_value(frame_ok, "pilot_bins"))),
    ]


def write_metrics_csv(path: Path, metrics: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows(metrics)


def write_summary(path: Path, metrics: list[tuple[str, str]], board_test_10_passed: bool) -> None:
    lookup = dict(metrics)
    lines = [
        "Tracker System Evidence Summary",
        "===============================",
        "",
        "Purpose",
        "-------",
        "",
        "Summarize the current integrated renewable-energy tracker evidence across proje3, proje2, and proje1.",
        "",
        "Integrated Path",
        "---------------",
        "",
        "Nexys/MCP3208 LDR sensing -> Orin tracker/PCA9685 actuation -> proje1 compact CRC frame/QPSK/OFDM profile -> proje2 UDP dashboard.",
        "",
        "Key Results",
        "-----------",
        "",
        f"Tracker valid dashboard rows: {lookup.get('tracker_valid_rows', 'n/a')}",
        f"Tracker sequence gaps: {lookup.get('tracker_sequence_gaps', 'n/a')}",
        f"Tracker locked rows: {lookup.get('tracking_locked_rows', 'n/a')} ({lookup.get('tracking_locked_pct', 'n/a')}%)",
        f"Tracking error best/avg/max deg: {lookup.get('tracking_error_best_deg', 'n/a')} / {lookup.get('tracking_error_avg_deg', 'n/a')} / {lookup.get('tracking_error_max_deg', 'n/a')}",
        f"Best tracking sequence: {lookup.get('tracking_error_best_seq', 'n/a')}",
        f"Bridge frame OK rows: {lookup.get('bridge_frame_ok_rows', 'n/a')}",
        f"Bridge sequence gaps: {lookup.get('bridge_sequence_gaps', 'n/a')}",
        f"Board Test 10 tracker QPSK/OFDM batch: {'PASS' if board_test_10_passed else 'not marked pass'}",
        "",
        "Renewable Tracking Evidence",
        "---------------------------",
        "",
        f"Fixed mean load power: {lookup.get('ab_fixed_mean_power_mw', 'n/a')} mW",
        f"Tracking mean load power: {lookup.get('ab_tracking_mean_power_mw', 'n/a')} mW",
        f"Tracking mean-power gain: {lookup.get('ab_power_gain_pct', 'n/a')}%",
        f"Tracking energy gain: {lookup.get('ab_energy_gain_pct', 'n/a')}%",
        f"Tracking locked samples: {lookup.get('ab_tracking_locked_pct', 'n/a')}%",
        "",
        "Shading Detection Evidence",
        "--------------------------",
        "",
        f"Fault-test valid dashboard rows: {lookup.get('fault_valid_rows', 'n/a')}",
        f"Fault-test sequence gaps: {lookup.get('fault_sequence_gaps', 'n/a')}",
        f"Learning started at sequence: {lookup.get('fault_learning_first_seq', 'n/a')}",
        f"Baseline ready at sequence: {lookup.get('fault_ok_first_seq', 'n/a')}",
        f"Shading detected at sequence: {lookup.get('fault_shading_first_seq', 'n/a')}",
        f"Dashboard shading samples: {lookup.get('fault_shading_rows', 'n/a')}",
        f"Recovered to OK at sequence: {lookup.get('fault_recovery_seq', 'n/a')}",
        "",
        "Digital Communication Profile",
        "-----------------------------",
        "",
        f"Payload bytes: {lookup.get('payload_bytes', 'n/a')}",
        f"Frame bytes: {lookup.get('frame_bytes', 'n/a')}",
        f"Frame bits: {lookup.get('frame_bits', 'n/a')}",
        f"QPSK symbols: {lookup.get('qpsk_symbols', 'n/a')}",
        f"OFDM symbols: {lookup.get('ofdm_symbols', 'n/a')}",
        f"QPSK padding symbols: {lookup.get('qpsk_pad_symbols', 'n/a')}",
        f"OFDM TX samples: {lookup.get('ofdm_tx_samples', 'n/a')}",
        f"OFDM CP samples: {lookup.get('ofdm_cp_samples', 'n/a')}",
        f"OFDM pilot bins: {lookup.get('ofdm_pilot_bins', 'n/a')}",
        "",
        "Artifacts",
        "---------",
        "",
        "tracker_system_evidence_metrics.csv",
        "tracker_error_deg.svg",
        "tracker_power_mw.svg",
        "tracker_angles_deg.svg",
        "comm_profile_bar.svg",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def svg_escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_line_svg(path: Path, title: str, series: list[tuple[str, list[float | None], str]]) -> None:
    width, height = 900, 360
    left, right, top, bottom = 64, 20, 36, 48
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_len = max((len(points) for _, points, _ in series), default=0)
    finite_values = [
        float(value)
        for _, points, _ in series
        for value in points
        if isinstance(value, (int, float)) and not math.isnan(float(value))
    ]

    if max_len < 2 or not finite_values:
        path.write_text(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"120\"><text x=\"20\" y=\"60\">No data</text></svg>\n",
            encoding="utf-8",
        )
        return

    y_min = min(finite_values)
    y_max = max(finite_values)
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    pad = (y_max - y_min) * 0.08
    y_min -= pad
    y_max += pad

    def point_xy(index: int, value: float) -> tuple[float, float]:
        x = left + (index / max(1, max_len - 1)) * plot_w
        y = top + (1.0 - ((value - y_min) / (y_max - y_min))) * plot_h
        return x, y

    parts = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>",
        f"<text x=\"{left}\" y=\"24\" font-family=\"Segoe UI, Arial\" font-size=\"18\" font-weight=\"700\">{svg_escape(title)}</text>",
        f"<line x1=\"{left}\" y1=\"{top + plot_h}\" x2=\"{left + plot_w}\" y2=\"{top + plot_h}\" stroke=\"#8a96a3\"/>",
        f"<line x1=\"{left}\" y1=\"{top}\" x2=\"{left}\" y2=\"{top + plot_h}\" stroke=\"#8a96a3\"/>",
    ]

    for tick in range(5):
        y = top + (tick / 4) * plot_h
        value = y_max - (tick / 4) * (y_max - y_min)
        parts.append(f"<line x1=\"{left}\" y1=\"{y:.1f}\" x2=\"{left + plot_w}\" y2=\"{y:.1f}\" stroke=\"#edf1f4\"/>")
        parts.append(f"<text x=\"12\" y=\"{y + 4:.1f}\" font-family=\"Segoe UI, Arial\" font-size=\"12\" fill=\"#66717c\">{value:.2f}</text>")

    legend_x = left
    for name, points, color in series:
        current: list[str] = []
        for index, value in enumerate(points):
            if value is None:
                continue
            x, y = point_xy(index, float(value))
            current.append(f"{x:.1f},{y:.1f}")
        if len(current) >= 2:
            parts.append(f"<polyline points=\"{' '.join(current)}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2.5\"/>")
        parts.append(f"<rect x=\"{legend_x}\" y=\"{height - 24}\" width=\"12\" height=\"12\" fill=\"{color}\"/>")
        parts.append(f"<text x=\"{legend_x + 18}\" y=\"{height - 14}\" font-family=\"Segoe UI, Arial\" font-size=\"12\">{svg_escape(name)}</text>")
        legend_x += 140

    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_bar_svg(path: Path, title: str, bars: list[tuple[str, float]], color: str = "#1f5f99") -> None:
    width, height = 900, 360
    left, right, top, bottom = 86, 28, 42, 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max((value for _, value in bars), default=1.0)
    if max_value <= 0:
        max_value = 1.0
    bar_w = plot_w / max(1, len(bars)) * 0.62
    step = plot_w / max(1, len(bars))

    parts = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>",
        f"<text x=\"{left}\" y=\"26\" font-family=\"Segoe UI, Arial\" font-size=\"18\" font-weight=\"700\">{svg_escape(title)}</text>",
        f"<line x1=\"{left}\" y1=\"{top + plot_h}\" x2=\"{left + plot_w}\" y2=\"{top + plot_h}\" stroke=\"#8a96a3\"/>",
        f"<line x1=\"{left}\" y1=\"{top}\" x2=\"{left}\" y2=\"{top + plot_h}\" stroke=\"#8a96a3\"/>",
    ]
    for index, (name, value) in enumerate(bars):
        bar_h = (value / max_value) * plot_h
        x = left + index * step + (step - bar_w) / 2
        y = top + plot_h - bar_h
        parts.append(f"<rect x=\"{x:.1f}\" y=\"{y:.1f}\" width=\"{bar_w:.1f}\" height=\"{bar_h:.1f}\" fill=\"{color}\"/>")
        parts.append(f"<text x=\"{x + bar_w / 2:.1f}\" y=\"{y - 6:.1f}\" text-anchor=\"middle\" font-family=\"Segoe UI, Arial\" font-size=\"12\">{value:.0f}</text>")
        parts.append(f"<text x=\"{x + bar_w / 2:.1f}\" y=\"{top + plot_h + 18}\" text-anchor=\"middle\" font-family=\"Segoe UI, Arial\" font-size=\"12\">{svg_escape(name)}</text>")
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def maybe_float_metric(metrics: list[tuple[str, str]], key: str) -> float:
    lookup = dict(metrics)
    try:
        return float(lookup[key])
    except (KeyError, ValueError):
        return 0.0


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tracker_rows = read_dashboard_rows(args.dashboard_log)
    bridge_rows = read_bridge_rows(args.bridge_log)
    aligned_tracker = tracker_rows_for_bridge_window(tracker_rows, bridge_rows)
    evidence_tracker = aligned_tracker if aligned_tracker else tracker_rows[-args.last :]
    recent_tracker = evidence_tracker[-args.last :]
    metrics = metric_rows(evidence_tracker, bridge_rows)
    metrics.extend(read_ab_metrics(args.ab_metrics))
    metrics.extend(read_fault_metrics(args.fault_dashboard_log))

    board_doc = Path("proje1/docs/board_test_10_tracker_frame_qpsk_ofdm_batch.txt")
    board_test_10_passed = board_doc.exists() and "PASS on Nexys Video" in board_doc.read_text(encoding="utf-8")

    write_metrics_csv(out_dir / "tracker_system_evidence_metrics.csv", metrics)
    write_summary(out_dir / "tracker_system_evidence_summary.txt", metrics, board_test_10_passed)
    write_line_svg(
        out_dir / "tracker_error_deg.svg",
        "Tracker Error (deg)",
        [("tracking error", [row.error_deg for row in recent_tracker], "#1f5f99")],
    )
    write_line_svg(
        out_dir / "tracker_power_mw.svg",
        "Solar Power Measurement (mW)",
        [("power", [row.power_mw for row in recent_tracker], "#138a4b")],
    )
    write_line_svg(
        out_dir / "tracker_angles_deg.svg",
        "Tracker and Light Angles (deg)",
        [
            ("pan", [row.pan_deg for row in recent_tracker], "#1f5f99"),
            ("tilt", [row.tilt_deg for row in recent_tracker], "#138a4b"),
            ("sun pan", [row.sun_pan_deg for row in recent_tracker], "#b46b00"),
            ("sun tilt", [row.sun_tilt_deg for row in recent_tracker], "#b42318"),
        ],
    )
    write_bar_svg(
        out_dir / "comm_profile_bar.svg",
        "Digital Communication Frame/OFDM Profile",
        [
            ("payload B", maybe_float_metric(metrics, "payload_bytes")),
            ("frame B", maybe_float_metric(metrics, "frame_bytes")),
            ("frame bits", maybe_float_metric(metrics, "frame_bits")),
            ("QPSK", maybe_float_metric(metrics, "qpsk_symbols")),
            ("OFDM sym", maybe_float_metric(metrics, "ofdm_symbols")),
            ("pad Q", maybe_float_metric(metrics, "qpsk_pad_symbols")),
            ("CP", maybe_float_metric(metrics, "ofdm_cp_samples")),
            ("pilots", maybe_float_metric(metrics, "ofdm_pilot_bins")),
        ],
        "#1f5f99",
    )

    print(f"Wrote {out_dir / 'tracker_system_evidence_summary.txt'}")
    print(f"Wrote {out_dir / 'tracker_system_evidence_metrics.csv'}")
    print(f"Wrote {out_dir / 'tracker_error_deg.svg'}")
    print(f"Wrote {out_dir / 'tracker_power_mw.svg'}")
    print(f"Wrote {out_dir / 'tracker_angles_deg.svg'}")
    print(f"Wrote {out_dir / 'comm_profile_bar.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
