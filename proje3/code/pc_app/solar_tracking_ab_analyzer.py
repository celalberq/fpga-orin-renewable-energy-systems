#!/usr/bin/env python3
"""Compare fixed-panel and tracking solar-power logs."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    timestamp: datetime
    voltage_mv: float
    current_ma: float
    power_mw: float
    track_error_deg: float | None
    detected: bool
    locked: bool


@dataclass(frozen=True)
class Summary:
    samples: int
    active_duration_s: float
    voltage_mean_mv: float
    current_mean_ma: float
    power_mean_mw: float
    power_median_mw: float
    power_min_mw: float
    power_max_mw: float
    power_stdev_mw: float
    energy_mwh: float
    detection_pct: float
    locked_pct: float
    track_error_mean_deg: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare fixed and solar-tracking power logs.")
    parser.add_argument("--fixed-log", type=Path, required=True)
    parser.add_argument("--tracking-log", type=Path, required=True)
    parser.add_argument("--discard-seconds", type=float, default=3.0, help="Discard startup time from each log.")
    parser.add_argument("--max-gap-seconds", type=float, default=2.0, help="Do not integrate across longer log gaps.")
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument(
        "--panel-load-ohms",
        type=float,
        help=(
            "Estimate load current and power from the MCP3208 panel_mv field and "
            "this known resistive load; ignore INA226 measurement fields."
        ),
    )
    parser.add_argument("--out", type=Path, default=Path("proje3/data/solar_tracking_ab_summary.txt"))
    parser.add_argument("--csv-out", type=Path, default=Path("proje3/data/solar_tracking_ab_metrics.csv"))
    return parser.parse_args()


def to_float(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def to_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "locked"}


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def read_samples(path: Path, panel_load_ohms: float | None = None) -> list[Sample]:
    if not path.exists():
        raise SystemExit(f"Log not found: {path}")

    samples: list[Sample] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            timestamp = parse_timestamp(row.get("timestamp_utc", ""))
            if panel_load_ohms is None:
                voltage_mv = to_float(row.get("v_mv"))
                current_ma = to_float(row.get("i_ma"))
                power_mw = to_float(row.get("p_mw"))
            else:
                voltage_mv = to_float(row.get("panel_mv"))
                if voltage_mv is None:
                    current_ma = power_mw = None
                else:
                    current_ma = voltage_mv / panel_load_ohms
                    power_mw = voltage_mv * voltage_mv / (1000.0 * panel_load_ohms)
            if timestamp is None or voltage_mv is None or current_ma is None or power_mw is None:
                continue
            samples.append(
                Sample(
                    timestamp=timestamp,
                    voltage_mv=voltage_mv,
                    current_ma=current_ma,
                    power_mw=power_mw,
                    track_error_deg=to_float(row.get("track_error_deg")),
                    detected=to_bool(row.get("detected")),
                    locked=str(row.get("state", "")).lower().startswith("lock"),
                )
            )
    return sorted(samples, key=lambda sample: sample.timestamp)


def discard_startup(samples: list[Sample], seconds: float) -> list[Sample]:
    if not samples or seconds <= 0:
        return samples
    cutoff = samples[0].timestamp.timestamp() + seconds
    return [sample for sample in samples if sample.timestamp.timestamp() >= cutoff]


def summarize(samples: list[Sample], max_gap_seconds: float) -> Summary:
    power = [sample.power_mw for sample in samples]
    voltage = [sample.voltage_mv for sample in samples]
    current = [sample.current_ma for sample in samples]
    errors = [sample.track_error_deg for sample in samples if sample.track_error_deg is not None]

    active_duration_s = 0.0
    energy_mwh = 0.0
    for previous, current_sample in zip(samples, samples[1:]):
        delta_s = (current_sample.timestamp - previous.timestamp).total_seconds()
        if delta_s <= 0 or delta_s > max_gap_seconds:
            continue
        active_duration_s += delta_s
        energy_mwh += ((previous.power_mw + current_sample.power_mw) / 2.0) * delta_s / 3600.0

    return Summary(
        samples=len(samples),
        active_duration_s=active_duration_s,
        voltage_mean_mv=statistics.fmean(voltage),
        current_mean_ma=statistics.fmean(current),
        power_mean_mw=statistics.fmean(power),
        power_median_mw=statistics.median(power),
        power_min_mw=min(power),
        power_max_mw=max(power),
        power_stdev_mw=statistics.pstdev(power),
        energy_mwh=energy_mwh,
        detection_pct=100.0 * sum(sample.detected for sample in samples) / len(samples),
        locked_pct=100.0 * sum(sample.locked for sample in samples) / len(samples),
        track_error_mean_deg=statistics.fmean(errors) if errors else None,
    )


def percent_change(new_value: float, baseline: float) -> float | None:
    if abs(baseline) < 1e-9:
        return None
    return 100.0 * (new_value - baseline) / abs(baseline)


def comparison_metrics(fixed: Summary, tracking: Summary) -> list[tuple[str, str, str]]:
    power_gain = percent_change(tracking.power_mean_mw, fixed.power_mean_mw)
    energy_gain = percent_change(tracking.energy_mwh, fixed.energy_mwh)
    return [
        ("samples", str(fixed.samples), str(tracking.samples)),
        ("active_duration_s", f"{fixed.active_duration_s:.3f}", f"{tracking.active_duration_s:.3f}"),
        ("voltage_mean_mv", f"{fixed.voltage_mean_mv:.3f}", f"{tracking.voltage_mean_mv:.3f}"),
        ("current_mean_ma", f"{fixed.current_mean_ma:.3f}", f"{tracking.current_mean_ma:.3f}"),
        ("power_mean_mw", f"{fixed.power_mean_mw:.3f}", f"{tracking.power_mean_mw:.3f}"),
        ("power_median_mw", f"{fixed.power_median_mw:.3f}", f"{tracking.power_median_mw:.3f}"),
        ("power_min_mw", f"{fixed.power_min_mw:.3f}", f"{tracking.power_min_mw:.3f}"),
        ("power_max_mw", f"{fixed.power_max_mw:.3f}", f"{tracking.power_max_mw:.3f}"),
        ("power_stdev_mw", f"{fixed.power_stdev_mw:.3f}", f"{tracking.power_stdev_mw:.3f}"),
        ("energy_mwh", f"{fixed.energy_mwh:.6f}", f"{tracking.energy_mwh:.6f}"),
        ("detection_pct", f"{fixed.detection_pct:.3f}", f"{tracking.detection_pct:.3f}"),
        ("locked_pct", f"{fixed.locked_pct:.3f}", f"{tracking.locked_pct:.3f}"),
        (
            "track_error_mean_deg",
            "n/a" if fixed.track_error_mean_deg is None else f"{fixed.track_error_mean_deg:.3f}",
            "n/a" if tracking.track_error_mean_deg is None else f"{tracking.track_error_mean_deg:.3f}",
        ),
        ("power_gain_pct", "baseline", "n/a" if power_gain is None else f"{power_gain:.3f}"),
        ("energy_gain_pct", "baseline", "n/a" if energy_gain is None else f"{energy_gain:.3f}"),
    ]


def write_csv(path: Path, metrics: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "fixed", "tracking"])
        writer.writerows(metrics)


def write_summary(
    path: Path,
    fixed_log: Path,
    tracking_log: Path,
    metrics: list[tuple[str, str, str]],
    fixed: Summary,
    tracking: Summary,
    power_source: str,
) -> None:
    lookup = {name: (fixed_value, tracking_value) for name, fixed_value, tracking_value in metrics}
    warnings = []
    if fixed.power_mean_mw <= 0 or tracking.power_mean_mw <= 0:
        warnings.append("Mean power is non-positive; verify the load, wiring, and illumination.")
    duration_ratio = min(fixed.active_duration_s, tracking.active_duration_s) / max(
        1e-9, max(fixed.active_duration_s, tracking.active_duration_s)
    )
    if duration_ratio < 0.8:
        warnings.append("Active run durations differ by more than 20%; repeat with matched durations.")
    if fixed.power_stdev_mw > abs(fixed.power_mean_mw) * 0.2:
        warnings.append("Fixed-run power varied by more than 20%; the light source may not have been stable.")

    lines = [
        "Solar Tracking A/B Evidence Summary",
        "====================================",
        "",
        f"Fixed log: {fixed_log}",
        f"Tracking log: {tracking_log}",
        f"Power source: {power_source}",
        "",
        "Result",
        "------",
        "",
        f"Fixed mean power: {lookup['power_mean_mw'][0]} mW",
        f"Tracking mean power: {lookup['power_mean_mw'][1]} mW",
        f"Tracking mean-power gain: {lookup['power_gain_pct'][1]}%",
        f"Fixed integrated energy: {lookup['energy_mwh'][0]} mWh",
        f"Tracking integrated energy: {lookup['energy_mwh'][1]} mWh",
        f"Tracking energy gain: {lookup['energy_gain_pct'][1]}%",
        "",
        "Quality",
        "-------",
        "",
        f"Fixed samples/duration: {fixed.samples} / {fixed.active_duration_s:.1f} s",
        f"Tracking samples/duration: {tracking.samples} / {tracking.active_duration_s:.1f} s",
        f"Tracking detection/locked: {tracking.detection_pct:.1f}% / {tracking.locked_pct:.1f}%",
    ]
    if warnings:
        lines.extend(["", "Warnings", "--------", ""] + [f"- {warning}" for warning in warnings])
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.discard_seconds < 0 or args.max_gap_seconds <= 0 or args.min_samples < 2:
        raise SystemExit("Invalid analysis limits")
    if args.panel_load_ohms is not None and args.panel_load_ohms <= 0:
        raise SystemExit("--panel-load-ohms must be positive")

    fixed_samples = discard_startup(
        read_samples(args.fixed_log, args.panel_load_ohms), args.discard_seconds
    )
    tracking_samples = discard_startup(
        read_samples(args.tracking_log, args.panel_load_ohms), args.discard_seconds
    )
    if len(fixed_samples) < args.min_samples:
        raise SystemExit(f"Fixed log has only {len(fixed_samples)} usable samples; need {args.min_samples}")
    if len(tracking_samples) < args.min_samples:
        raise SystemExit(f"Tracking log has only {len(tracking_samples)} usable samples; need {args.min_samples}")

    fixed = summarize(fixed_samples, args.max_gap_seconds)
    tracking = summarize(tracking_samples, args.max_gap_seconds)
    metrics = comparison_metrics(fixed, tracking)
    write_csv(args.csv_out, metrics)
    power_source = (
        f"MCP3208 panel voltage with {args.panel_load_ohms:g}-ohm resistive-load estimate"
        if args.panel_load_ohms is not None
        else "INA226 voltage/current measurement"
    )
    write_summary(
        args.out,
        args.fixed_log,
        args.tracking_log,
        metrics,
        fixed,
        tracking,
        power_source,
    )
    print(args.out.read_text(encoding="utf-8"))
    print(f"Wrote {args.csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
