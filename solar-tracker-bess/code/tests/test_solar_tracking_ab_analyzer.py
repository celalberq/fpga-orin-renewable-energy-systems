from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PC_APP = Path(__file__).resolve().parents[1] / "pc_app"
sys.path.insert(0, str(PC_APP))

import solar_tracking_ab_analyzer as analyzer  # noqa: E402


def write_log(path: Path, power_mw: float) -> None:
    start = datetime(2026, 8, 7, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp_utc",
                "v_mv",
                "i_ma",
                "p_mw",
                "track_error_deg",
                "detected",
                "state",
            ],
        )
        writer.writeheader()
        for index in range(5):
            writer.writerow(
                {
                    "timestamp_utc": (start + timedelta(seconds=index)).isoformat(),
                    "v_mv": 5000,
                    "i_ma": power_mw / 5.0,
                    "p_mw": power_mw,
                    "track_error_deg": 2.0,
                    "detected": 1,
                    "state": "locked",
                }
            )


def write_panel_voltage_log(path: Path, panel_mv: float) -> None:
    start = datetime(2026, 8, 7, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp_utc", "panel_mv", "track_error_deg", "detected", "state"],
        )
        writer.writeheader()
        for index in range(5):
            writer.writerow(
                {
                    "timestamp_utc": (start + timedelta(seconds=index)).isoformat(),
                    "panel_mv": panel_mv,
                    "track_error_deg": 2.0,
                    "detected": 1,
                    "state": "locked",
                }
            )


class SolarTrackingAbAnalyzerTests(unittest.TestCase):
    def test_constant_power_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixed_path = Path(temp_dir) / "fixed.csv"
            tracking_path = Path(temp_dir) / "tracking.csv"
            write_log(fixed_path, 100.0)
            write_log(tracking_path, 120.0)

            fixed = analyzer.summarize(analyzer.read_samples(fixed_path), 2.0)
            tracking = analyzer.summarize(analyzer.read_samples(tracking_path), 2.0)
            metrics = {name: value for name, _, value in analyzer.comparison_metrics(fixed, tracking)}

            self.assertAlmostEqual(fixed.energy_mwh, 100.0 * 4.0 / 3600.0)
            self.assertAlmostEqual(tracking.energy_mwh, 120.0 * 4.0 / 3600.0)
            self.assertEqual(metrics["power_gain_pct"], "20.000")
            self.assertEqual(metrics["energy_gain_pct"], "20.000")

    def test_long_gap_is_not_integrated(self) -> None:
        start = datetime(2026, 8, 7, tzinfo=timezone.utc)
        samples = [
            analyzer.Sample(start, 5000.0, 20.0, 100.0, 1.0, True, True),
            analyzer.Sample(start + timedelta(seconds=1), 5000.0, 20.0, 100.0, 1.0, True, True),
            analyzer.Sample(start + timedelta(seconds=10), 5000.0, 20.0, 100.0, 1.0, True, True),
        ]

        summary = analyzer.summarize(samples, 2.0)

        self.assertEqual(summary.active_duration_s, 1.0)
        self.assertAlmostEqual(summary.energy_mwh, 100.0 / 3600.0)

    def test_known_load_power_from_panel_voltage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixed_path = Path(temp_dir) / "fixed.csv"
            tracking_path = Path(temp_dir) / "tracking.csv"
            write_panel_voltage_log(fixed_path, 100.0)
            write_panel_voltage_log(tracking_path, 120.0)

            fixed = analyzer.summarize(analyzer.read_samples(fixed_path, 1000.0), 2.0)
            tracking = analyzer.summarize(analyzer.read_samples(tracking_path, 1000.0), 2.0)
            metrics = {name: value for name, _, value in analyzer.comparison_metrics(fixed, tracking)}

            self.assertAlmostEqual(fixed.current_mean_ma, 0.1)
            self.assertAlmostEqual(fixed.power_mean_mw, 0.01)
            self.assertAlmostEqual(tracking.power_mean_mw, 0.0144)
            self.assertEqual(metrics["power_gain_pct"], "44.000")


if __name__ == "__main__":
    unittest.main()
