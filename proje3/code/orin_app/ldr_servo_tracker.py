#!/usr/bin/env python3
"""Track a light source using Nexys/MCP3208 LDR packets and PCA9685 servos."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import socket
import statistics
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import serial
except ImportError:  # pragma: no cover - depends on target image
    serial = None

from pca9685_servo_test import MODE1, Pca9685, SMBus, require_smbus, set_servo_angle

try:
    from ina226_reader import REG_CONFIG, REG_DIE_ID, REG_MANUFACTURER_ID, Ina226
except (ImportError, SystemExit):  # pragma: no cover - target hardware dependency
    REG_CONFIG = REG_DIE_ID = REG_MANUFACTURER_ID = 0
    Ina226 = None  # type: ignore


PACKET_RE = re.compile(
    r"^ldr,seq=(\d{5}),pv=(\d{5}),tl=(\d{4}),tr=(\d{4}),bl=(\d{4}),br=(\d{4})$"
)


@dataclass(frozen=True)
class LdrSample:
    seq: int
    panel_mv: int
    tl: int
    tr: int
    bl: int
    br: int

    @property
    def total(self) -> int:
        return self.tl + self.tr + self.bl + self.br

    def normalized_errors(self) -> tuple[float, float]:
        if self.total <= 0:
            return 0.0, 0.0
        horizontal = ((self.tr + self.br) - (self.tl + self.bl)) / self.total
        vertical = ((self.bl + self.br) - (self.tl + self.tr)) / self.total
        return horizontal, vertical


@dataclass(frozen=True)
class FaultStatus:
    active: bool
    label: str
    reason: str
    severity: str = "normal"


OK_STATUS = FaultStatus(False, "OK", "Sensors and panel response are normal.")


def input_fault_status(
    sample: LdrSample,
    min_total: int,
    low_count: int,
    high_count: int,
) -> FaultStatus:
    channels = {"TL": sample.tl, "TR": sample.tr, "BL": sample.bl, "BR": sample.br}
    low = [name for name, value in channels.items() if value <= low_count]
    high = [name for name, value in channels.items() if value >= high_count]
    if low:
        return FaultStatus(
            True,
            "Sensor Fault",
            f"LDR channel near zero: {','.join(low)}.",
            "critical",
        )
    if high:
        return FaultStatus(
            True,
            "Sensor Saturation",
            f"LDR channel near ADC rail: {','.join(high)}.",
            "critical",
        )
    if sample.total < min_total:
        return FaultStatus(
            True,
            "Low Light",
            f"Combined LDR count {sample.total} is below {min_total}; motion is held.",
            "warning",
        )
    return OK_STATUS


class ShadingDetector:
    def __init__(
        self,
        learn_samples: int,
        drop_ratio: float,
        trigger_samples: int,
        recovery_samples: int,
    ) -> None:
        self.learn_samples = learn_samples
        self.drop_ratio = drop_ratio
        self.trigger_samples = trigger_samples
        self.recovery_samples = recovery_samples
        self.learning: list[float] = []
        self.baseline: float | None = None
        self.low_count = 0
        self.good_count = 0
        self.active = False

    def update(self, sample: LdrSample, power_mw: float, tracker_state: str) -> FaultStatus:
        if tracker_state != "locked" or power_mw <= 0:
            self.low_count = 0
            self.good_count = 0
            return FaultStatus(
                False,
                "Standby",
                "Shading detection waits for a locked tracker and positive power.",
            )

        performance = power_mw / max(1.0, float(sample.total))
        if self.baseline is None:
            self.learning.append(performance)
            if len(self.learning) >= self.learn_samples:
                self.baseline = statistics.median(self.learning)
            return FaultStatus(
                False,
                "Learning",
                f"Learning locked-state shading baseline ({len(self.learning)}/{self.learn_samples}).",
            )

        ratio = performance / max(self.baseline, 1e-15)
        if ratio < self.drop_ratio:
            self.low_count += 1
            self.good_count = 0
        else:
            self.low_count = 0
            self.good_count += 1
            if ratio >= 0.8:
                self.baseline = 0.98 * self.baseline + 0.02 * performance

        if self.low_count >= self.trigger_samples:
            self.active = True
        if self.active and self.good_count >= self.recovery_samples:
            self.active = False

        if self.active:
            return FaultStatus(
                True,
                "Shading",
                f"Panel power per LDR count fell to {ratio * 100:.1f}% of baseline.",
                "warning",
            )
        return FaultStatus(
            False,
            "OK",
            f"Panel response is {ratio * 100:.1f}% of the learned baseline.",
        )


class StableDirection:
    def __init__(self, required_samples: int) -> None:
        self.required_samples = max(1, required_samples)
        self.last_sign = 0
        self.count = 0

    def update(self, error: float, deadband: float) -> int:
        sign = 1 if error > deadband else -1 if error < -deadband else 0
        if sign == 0:
            self.last_sign = 0
            self.count = 0
            return 0
        if sign == self.last_sign:
            self.count += 1
        else:
            self.last_sign = sign
            self.count = 1
        return sign if self.count >= self.required_samples else 0


class AltAzSequencer:
    def __init__(
        self,
        align_deadband: float,
        realign_deadband: float,
        align_angle_deg: float,
        realign_angle_deg: float,
        max_pan_samples: int = 8,
        min_tilt_samples: int = 6,
    ) -> None:
        if align_deadband <= 0 or realign_deadband < align_deadband:
            raise ValueError("realign deadband must be at least the align deadband")
        if align_angle_deg <= 0 or realign_angle_deg < align_angle_deg:
            raise ValueError("realign angle must be at least the align angle")
        if max_pan_samples < 1 or min_tilt_samples < 1:
            raise ValueError("pan and tilt phase sample counts must be positive")
        self.align_deadband = align_deadband
        self.realign_deadband = realign_deadband
        self.align_angle_deg = align_angle_deg
        self.realign_angle_deg = realign_angle_deg
        self.max_pan_samples = max_pan_samples
        self.min_tilt_samples = min_tilt_samples
        self.phase = "align-pan"
        self.pan_samples = 0
        self.tilt_samples = 0

    def _select_pan(self) -> tuple[bool, bool, str]:
        if self.phase != "align-pan":
            self.pan_samples = 0
        self.phase = "align-pan"
        self.pan_samples += 1
        self.tilt_samples = 0
        return True, False, self.phase

    def _select_tilt(self) -> tuple[bool, bool, str]:
        if self.phase != "track-tilt":
            self.tilt_samples = 0
        self.phase = "track-tilt"
        self.tilt_samples += 1
        self.pan_samples = 0
        return False, True, self.phase

    def _select_locked(self) -> tuple[bool, bool, str]:
        self.phase = "locked"
        self.pan_samples = 0
        self.tilt_samples = 0
        return False, False, self.phase

    def select(self, horizontal: float, vertical: float, lock_deadband: float) -> tuple[bool, bool, str]:
        error_angle_deg = math.degrees(math.atan2(abs(horizontal), abs(vertical)))
        remain_aligned = (
            abs(horizontal) <= self.realign_deadband
            or error_angle_deg <= self.realign_angle_deg
        )
        enter_aligned = (
            abs(horizontal) <= self.align_deadband
            or error_angle_deg <= self.align_angle_deg
        )

        vertical_active = abs(vertical) > lock_deadband
        if not vertical_active:
            if abs(horizontal) <= lock_deadband:
                return self._select_locked()
            return self._select_pan()

        if self.phase == "track-tilt":
            if self.tilt_samples < self.min_tilt_samples or remain_aligned:
                return self._select_tilt()
            return self._select_pan()

        if not enter_aligned:
            if self.phase == "align-pan" and self.pan_samples >= self.max_pan_samples:
                return self._select_tilt()
            return self._select_pan()
        return self._select_tilt()


class DominantAxisSelector:
    def __init__(self, switch_margin: float) -> None:
        if switch_margin < 0:
            raise ValueError("axis switch margin cannot be negative")
        self.switch_margin = switch_margin
        self.active_axis: str | None = None

    def select(
        self,
        pan_error: float,
        tilt_error: float,
        deadband: float,
        pan_available: bool = True,
        tilt_available: bool = True,
    ) -> tuple[bool, bool, str]:
        pan_active = abs(pan_error) > deadband and pan_available
        tilt_active = abs(tilt_error) > deadband and tilt_available

        if not pan_active and not tilt_active:
            self.active_axis = None
            return False, False, "locked"
        if pan_active and not tilt_active:
            self.active_axis = "pan"
            return True, False, "track-pan"
        if tilt_active and not pan_active:
            self.active_axis = "tilt"
            return False, True, "track-tilt"

        pan_magnitude = abs(pan_error)
        tilt_magnitude = abs(tilt_error)
        if self.active_axis == "pan":
            if tilt_magnitude > pan_magnitude + self.switch_margin:
                self.active_axis = "tilt"
        elif self.active_axis == "tilt":
            if pan_magnitude > tilt_magnitude + self.switch_margin:
                self.active_axis = "pan"
        else:
            self.active_axis = "pan" if pan_magnitude >= tilt_magnitude else "tilt"

        if self.active_axis == "pan":
            return True, False, "track-pan"
        return False, True, "track-tilt"


class SequentialAxisSelector:
    def __init__(self) -> None:
        self.active_axis: str | None = None
        self.active_sign = 0

    @staticmethod
    def _sign(error: float, deadband: float) -> int:
        return 1 if error > deadband else -1 if error < -deadband else 0

    def _start(self, axis: str, error: float, deadband: float) -> tuple[bool, bool, str]:
        self.active_axis = axis
        self.active_sign = self._sign(error, deadband)
        if axis == "pan":
            return True, False, "track-pan"
        return False, True, "track-tilt"

    def _reset(self) -> None:
        self.active_axis = None
        self.active_sign = 0

    def select(
        self,
        pan_error: float,
        tilt_error: float,
        deadband: float,
        pan_available: bool = True,
        tilt_available: bool = True,
    ) -> tuple[bool, bool, str]:
        pan_sign = self._sign(pan_error, deadband)
        tilt_sign = self._sign(tilt_error, deadband)
        if pan_sign == 0 and tilt_sign == 0:
            self._reset()
            return False, False, "locked"

        errors = {"pan": pan_error, "tilt": tilt_error}
        signs = {"pan": pan_sign, "tilt": tilt_sign}
        available = {"pan": pan_available, "tilt": tilt_available}

        if self.active_axis is not None:
            active = self.active_axis
            active_corrected = signs[active] == 0 or signs[active] != self.active_sign
            if not active_corrected and available[active]:
                if active == "pan":
                    return True, False, "track-pan"
                return False, True, "track-tilt"

            other = "tilt" if active == "pan" else "pan"
            self._reset()
            if signs[other] != 0 and available[other]:
                return self._start(other, errors[other], deadband)

        candidates = [
            axis
            for axis in ("pan", "tilt")
            if signs[axis] != 0 and available[axis]
        ]
        if not candidates:
            self._reset()
            return False, False, "blocked-limits"

        first_axis = max(candidates, key=lambda axis: abs(errors[axis]))
        return self._start(first_axis, errors[first_axis], deadband)


class FixedSensorMapper:
    def __init__(
        self,
        pan_center: float,
        tilt_center: float,
        pan_min: float,
        pan_max: float,
        tilt_min: float,
        tilt_max: float,
        tilt_gain: float,
        center_deadband: float,
        hemisphere_deadband: float,
        pan_orientation: float,
        tilt_orientation: float,
    ) -> None:
        self.pan_center = pan_center
        self.tilt_center = tilt_center
        self.pan_min = pan_min
        self.pan_max = pan_max
        self.tilt_min = tilt_min
        self.tilt_max = tilt_max
        self.tilt_gain = tilt_gain
        self.center_deadband = center_deadband
        self.hemisphere_deadband = hemisphere_deadband
        self.pan_orientation = pan_orientation
        self.tilt_orientation = tilt_orientation
        self.hemisphere = 1.0

    def targets(self, horizontal: float, vertical: float) -> tuple[float, float]:
        radial_error = math.hypot(horizontal, vertical)
        if radial_error <= self.center_deadband:
            return self.pan_center, self.tilt_center

        if vertical > self.hemisphere_deadband:
            self.hemisphere = 1.0
        elif vertical < -self.hemisphere_deadband:
            self.hemisphere = -1.0

        azimuth_offset = math.degrees(math.atan2(abs(horizontal), abs(vertical)))
        horizontal_sign = 1.0 if horizontal >= 0 else -1.0
        pan_target = self.pan_center + (
            horizontal_sign * self.hemisphere * azimuth_offset * self.pan_orientation
        )

        tilt_offset = self.tilt_gain * radial_error
        tilt_target = self.tilt_center + (
            self.hemisphere * tilt_offset * self.tilt_orientation
        )
        return (
            clamp(pan_target, self.pan_min, self.pan_max),
            clamp(tilt_target, self.tilt_min, self.tilt_max),
        )


def parse_packet(line: str) -> LdrSample:
    match = PACKET_RE.fullmatch(line.strip())
    if match is None:
        raise ValueError("unexpected packet")
    seq, panel_mv, tl, tr, bl, br = map(int, match.groups())
    if panel_mv > 18300:
        raise ValueError("panel voltage outside 0..18300mV")
    if any(value > 4095 for value in (tl, tr, bl, br)):
        raise ValueError("LDR count outside 0..4095")
    return LdrSample(seq, panel_mv, tl, tr, bl, br)


def step_from_error(
    error: float,
    deadband: float,
    gain: float,
    min_step: float,
    max_step: float,
) -> float:
    if abs(error) <= deadband:
        return 0.0
    magnitude = gain * (abs(error) - deadband)
    magnitude = max(min_step, min(max_step, magnitude))
    return math.copysign(magnitude, error)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def altaz_pan_error(horizontal: float, vertical: float, deadband: float) -> float:
    """Choose the azimuth direction for the light's upper/lower hemisphere."""
    if vertical < -deadband:
        return -horizontal
    return horizontal


def axis_can_move(angle: float, error: float, low: float, high: float, deadband: float) -> bool:
    if error > deadband:
        return angle < high
    if error < -deadband:
        return angle > low
    return False


def step_toward_target(error_deg: float, deadband_deg: float, min_step: float, max_step: float) -> float:
    if abs(error_deg) <= deadband_deg:
        return 0.0
    magnitude = min(max_step, max(min_step, abs(error_deg)))
    return math.copysign(magnitude, error_deg)


LOG_FIELDS = [
    "timestamp_utc",
    "seq",
    "ldr_seq",
    "detected",
    "panel_mv",
    "tl",
    "tr",
    "bl",
    "br",
    "h_error_pct",
    "v_error_pct",
    "pan_deg",
    "tilt_deg",
    "target_pan_deg",
    "target_tilt_deg",
    "track_error_deg",
    "state",
    "v_mv",
    "i_ma",
    "p_mw",
    "power_source",
    "battery_v_mv",
    "battery_i_ma",
    "battery_p_mw",
    "bess_state",
    "fault_label",
    "fault_reason",
    "fault_severity",
    "servo_enabled",
    "sensor_mount",
]


def open_tracker_log(path: Path, overwrite: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "a"
    handle = path.open(mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
    if handle.tell() == 0:
        writer.writeheader()
    return handle, writer


def save_calibration(path: Path, horizontal: float, vertical: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "h_center": horizontal,
                "v_center": vertical,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_calibration(path: Path) -> tuple[float, float]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return float(payload["h_center"]), float(payload["v_center"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid calibration file {path}: {exc}") from exc


def panel_load_measurement(panel_mv: float, load_ohms: float) -> tuple[float, float, float]:
    """Estimate resistive-load current and power from measured panel voltage."""
    current_ma = panel_mv / load_ohms
    power_mw = panel_mv * panel_mv / (1000.0 * load_ohms)
    return panel_mv, current_ma, power_mw


def make_udp_packet(
    seq: int,
    timestamp_utc: str,
    args: argparse.Namespace,
    sample: LdrSample,
    h_error: float,
    v_error: float,
    pan_angle: float,
    tilt_angle: float,
    target_pan: float | None,
    target_tilt: float | None,
    track_error_deg: float,
    state: str,
    voltage_mv: float,
    current_ma: float,
    power_mw: float,
    power_source: str,
    servo_enabled: bool,
    fault_status: FaultStatus = OK_STATUS,
    battery_snapshot: dict[str, float | int | str] | None = None,
) -> dict[str, object]:
    sun_pan = pan_angle if target_pan is None else target_pan
    sun_tilt = tilt_angle if target_tilt is None else target_tilt
    pan_span = max(1.0, args.pan_max - args.pan_min)
    pan_pct = int(round(100.0 * (pan_angle - args.pan_min) / pan_span))
    raw_line = (
        f"ldrtrk,seq={seq:05d},pan={pan_angle:06.2f},tilt={tilt_angle:06.2f},"
        f"sun_pan={sun_pan:06.2f},sun_tilt={sun_tilt:06.2f},"
        f"err={track_error_deg:05.2f},state={state}"
    )
    ldr = {"tl": sample.tl, "tr": sample.tr, "bl": sample.bl, "br": sample.br}
    packet: dict[str, object] = {
        "schema": "solar.telemetry.v1",
        "schema_variant": "orin.ldr_tracker.bess.v1" if battery_snapshot is not None else "orin.ldr_tracker.v1",
        "source_project": "proje3",
        "network_project": "proje2",
        "source_label": args.source_label,
        "timestamp_utc": timestamp_utc,
        "valid": True,
        "error": "",
        "seq_gap": 0,
        "seq": seq,
        "raw": "00",
        "d_pct": int(clamp(pan_pct, 0, 100)),
        "v_mv": round(voltage_mv, 6),
        "i_ma": round(current_ma, 6),
        "p_mw": round(power_mw, 6),
        "power_source": power_source,
        "mppt": "trk",
        "mppt_label": "Tracking",
        "mppt_reason": "Four stationary LDRs estimate the absolute light direction.",
        "fault": int(fault_status.active),
        "fault_label": fault_status.label,
        "fault_reason": fault_status.reason,
        "fault_severity": fault_status.severity,
        "chk": "",
        "computed_chk": "",
        "raw_line": raw_line,
        "tracker": {
            "state": state,
            "reason": (
                "Panel is within the absolute target deadband."
                if state == "locked"
                else "Panel is moving toward the LDR absolute target."
            ),
            "pan_deg": round(pan_angle, 3),
            "tilt_deg": round(tilt_angle, 3),
            "sun_pan_deg": round(sun_pan, 3),
            "sun_tilt_deg": round(sun_tilt, 3),
            "track_error_deg": round(track_error_deg, 3),
            "lr_error": round(h_error, 6),
            "tb_error": round(v_error, 6),
            "ldr": ldr,
            "servo_enabled": servo_enabled,
            "pan_servo_enabled": servo_enabled,
            "tilt_servo_enabled": servo_enabled,
            "servo_mode": "pan+tilt" if servo_enabled else "software",
            "sensor_mount": args.sensor_mount,
        },
        "light_sensor": {
            "mode": "four-ldr-mcp3208",
            "mount": args.sensor_mount,
            "panel_mv": sample.panel_mv,
            "h_error": round(h_error, 6),
            "v_error": round(v_error, 6),
            **ldr,
        },
    }

    if battery_snapshot is not None:
        battery_mv = float(battery_snapshot["bus_mv"])
        battery_current_ma = float(battery_snapshot["current_ma"])
        battery_power_mw = float(battery_snapshot["power_mw"])
        if battery_current_ma > args.bess_idle_current_ma:
            bess_state = "charging"
            bess_reason = "Measured battery current is positive; the cell is charging."
        elif battery_current_ma < -args.bess_idle_current_ma:
            bess_state = "discharging"
            bess_reason = "Measured battery current is negative; the connected load is discharging the cell."
        else:
            bess_state = "idle"
            bess_reason = "Measured battery current is within the configured idle threshold."
        capacity_wh = args.battery_capacity_ah * args.battery_nominal_voltage
        packet.update(
            {
                "raw_line": (
                    f"{raw_line},bv_mv={battery_mv:.1f},bi_ma={battery_current_ma:.1f},"
                    f"bp_mw={battery_power_mw:.1f},bs={bess_state}"
                ),
                "bess_measurement_mode": "real",
                "bess_state": bess_state,
                "bess_reason": bess_reason,
                "bess_power_w": round(battery_power_mw / 1000.0, 6),
                "bess_load_w": round(max(0.0, -battery_power_mw / 1000.0), 6),
                "bess_capacity_wh": round(capacity_wh, 3),
                "battery": {
                    "measurement_mode": "real",
                    "voltage_v": round(battery_mv / 1000.0, 6),
                    "current_a": round(battery_current_ma / 1000.0, 6),
                    "power_w": round(battery_power_mw / 1000.0, 6),
                    "capacity_ah": round(args.battery_capacity_ah, 3),
                    "nominal_voltage_v": round(args.battery_nominal_voltage, 3),
                    "capacity_wh": round(capacity_wh, 3),
                    "shunt_uv": battery_snapshot["shunt_uv"],
                    "shunt_raw": battery_snapshot["shunt_raw"],
                    "bus_raw": battery_snapshot["bus_raw"],
                },
            }
        )

    return packet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--serial-timeout", type=float, default=2.0)
    parser.add_argument("--max-packets", type=int)
    parser.add_argument("--calibration-samples", type=int, default=20)
    parser.add_argument("--calibration-in", type=Path, help="Reuse saved center calibration.")
    parser.add_argument("--calibration-out", type=Path, help="Save newly measured center calibration.")
    parser.add_argument("--calibrate-only", action="store_true", help="Calibrate, optionally save, and exit.")
    parser.add_argument("--deadband", type=float, default=0.007, help="Normalized axis deadband.")
    parser.add_argument(
        "--pan-align-deadband",
        type=float,
        default=0.02,
        help="Horizontal error below which alt-az control may start tilt.",
    )
    parser.add_argument(
        "--pan-realign-deadband",
        type=float,
        default=0.04,
        help="Horizontal error above which tilt returns to pan alignment.",
    )
    parser.add_argument(
        "--pan-align-angle-deg",
        type=float,
        default=15.0,
        help="Error-vector angle to the tilt plane at which tilt may start.",
    )
    parser.add_argument(
        "--pan-realign-angle-deg",
        type=float,
        default=25.0,
        help="Error-vector angle at which tilt returns to pan alignment.",
    )
    parser.add_argument(
        "--max-pan-phase-samples",
        type=int,
        default=8,
        help="Maximum consecutive pan samples before alt-az control gives tilt a turn.",
    )
    parser.add_argument(
        "--min-tilt-phase-samples",
        type=int,
        default=6,
        help="Minimum consecutive tilt samples before alt-az control may return to pan.",
    )
    parser.add_argument("--stable-samples", type=int, default=2)
    parser.add_argument("--gain", type=float, default=100.0, help="Degrees per normalized error above deadband.")
    parser.add_argument("--min-step", type=float, default=0.25)
    parser.add_argument("--max-step", type=float, default=1.0)
    parser.add_argument("--min-total-counts", type=int, default=1000)
    parser.add_argument("--saturation-count", type=int, default=4000)
    parser.add_argument("--sensor-fault-low-count", type=int, default=5)
    parser.add_argument("--sensor-fault-high-count", type=int, default=3900)
    parser.add_argument("--shading-learn-samples", type=int, default=8)
    parser.add_argument("--shading-drop-ratio", type=float, default=0.5)
    parser.add_argument("--shading-trigger-samples", type=int, default=3)
    parser.add_argument("--shading-recovery-samples", type=int, default=3)
    parser.add_argument(
        "--sensor-mount",
        choices=("fixed", "moving"),
        default="fixed",
        help="Use absolute targets for fixed LDRs or feedback control for moving LDRs.",
    )
    parser.add_argument(
        "--control-mode",
        choices=("sequential", "dominant", "altaz", "cartesian"),
        default="sequential",
        help="Choose latched sequential, dominant-axis, alt-az, or Cartesian control.",
    )
    parser.add_argument(
        "--axis-switch-margin",
        type=float,
        default=0.05,
        help="Normalized error advantage required to switch axes in dominant mode.",
    )
    parser.add_argument(
        "--fixed-tilt-gain",
        type=float,
        default=120.0,
        help="Servo degrees of tilt offset per normalized radial LDR error.",
    )
    parser.add_argument(
        "--fixed-center-deadband",
        type=float,
        default=0.015,
        help="Radial LDR error treated as the absolute center in fixed-sensor mode.",
    )
    parser.add_argument(
        "--fixed-hemisphere-deadband",
        type=float,
        default=0.05,
        help="Vertical error needed to change fixed-sensor pan/tilt representation.",
    )
    parser.add_argument(
        "--target-deadband-deg",
        type=float,
        default=1.0,
        help="Allowed servo-angle error around a fixed-sensor absolute target.",
    )
    parser.add_argument("--drive-servos", action="store_true", help="Enable real PCA9685 output.")
    parser.add_argument("--bus", type=int, default=7)
    parser.add_argument("--addr", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--pan-channel", type=int, default=15)
    parser.add_argument("--tilt-channel", type=int, default=12)
    parser.add_argument("--pan-start", type=float, default=90.0)
    parser.add_argument("--tilt-start", type=float, default=90.0)
    parser.add_argument("--pan-min", type=float, default=85.0)
    parser.add_argument("--pan-max", type=float, default=95.0)
    parser.add_argument("--tilt-min", type=float, default=85.0)
    parser.add_argument("--tilt-max", type=float, default=95.0)
    parser.add_argument("--invert-pan", action="store_true")
    parser.add_argument("--invert-tilt", action="store_true")
    parser.add_argument("--min-pulse-us", type=float, default=600.0)
    parser.add_argument("--max-pulse-us", type=float, default=2400.0)
    parser.add_argument("--hold-on-exit", action="store_true", help="Do not release PWM when stopping.")
    parser.add_argument("--disable-tracking", action="store_true", help="Hold start angles while still logging sensors.")
    parser.add_argument("--ina-enable", action="store_true", help="Read real voltage/current/power from INA226.")
    parser.add_argument("--ina-addr", type=lambda value: int(value, 0), default=0x44)
    parser.add_argument("--shunt-ohms", type=float, default=0.1)
    parser.add_argument(
        "--ina-role",
        choices=("panel", "bess"),
        default="panel",
        help="Use INA226 for top-level panel power or nested signed battery telemetry.",
    )
    parser.add_argument(
        "--ina-bus-voltage-scale",
        type=float,
        default=1.0,
        help="Calibration multiplier applied to INA226 bus voltage.",
    )
    parser.add_argument("--battery-capacity-ah", type=float, default=2.5)
    parser.add_argument("--battery-nominal-voltage", type=float, default=3.7)
    parser.add_argument("--bess-idle-current-ma", type=float, default=2.0)
    parser.add_argument(
        "--panel-load-ohms",
        type=float,
        help="Estimate current/power from MCP3208 panel voltage and a known resistive load.",
    )
    parser.add_argument("--udp-host", help="Optional tracker UDP destination host.")
    parser.add_argument("--udp-port", type=int, default=5013)
    parser.add_argument("--source-label", default="Orin four-LDR solar tracker")
    parser.add_argument("--log", type=Path, help="Write LDR, servo, and optional INA226 data to CSV.")
    parser.add_argument("--overwrite-log", action="store_true", help="Replace an existing CSV log.")
    return parser.parse_args()


def require_serial() -> None:
    if serial is None:
        raise SystemExit("pyserial is required: sudo apt install -y python3-serial")


def read_valid_sample(
    port,
    min_total: int,
    saturation_count: int,
    accept_fault_samples: bool = False,
) -> LdrSample | None:
    raw = port.readline().decode("ascii", errors="replace").strip()
    if not raw or not raw.startswith("ldr,"):
        return None
    try:
        sample = parse_packet(raw)
    except ValueError as exc:
        print(f"SKIP {exc}: {raw}")
        return None
    if sample.total < min_total:
        if accept_fault_samples:
            return sample
        print(f"SKIP low light seq={sample.seq:05d} total={sample.total}")
        return None
    if max(sample.tl, sample.tr, sample.bl, sample.br) >= saturation_count:
        if accept_fault_samples:
            return sample
        print(f"SKIP saturation seq={sample.seq:05d}")
        return None
    return sample


def calibrate(port, count: int, min_total: int, saturation_count: int) -> tuple[float, float]:
    horizontal: list[float] = []
    vertical: list[float] = []
    print(f"Keep the lamp centered and still: collecting {count} calibration samples.")
    while len(horizontal) < count:
        sample = read_valid_sample(port, min_total, saturation_count)
        if sample is None:
            continue
        h_error, v_error = sample.normalized_errors()
        horizontal.append(h_error)
        vertical.append(v_error)
        print(
            f"CAL {len(horizontal):02d}/{count:02d} seq={sample.seq:05d} "
            f"h={h_error * 100:+.3f}% v={v_error * 100:+.3f}%"
        )
    h_center = statistics.mean(horizontal)
    v_center = statistics.mean(vertical)
    h_std = statistics.pstdev(horizontal)
    v_std = statistics.pstdev(vertical)
    print(
        f"CAL DONE h_center={h_center * 100:+.3f}% v_center={v_center * 100:+.3f}% "
        f"h_std={h_std * 100:.3f}% v_std={v_std * 100:.3f}%"
    )
    if h_std > 0.003 or v_std > 0.003:
        print("WARNING calibration moved more than expected; repeat if tracking drifts.")
    return h_center, v_center


def axis_label(horizontal: float, vertical: float, deadband: float) -> str:
    horizontal_label = "right" if horizontal > deadband else "left" if horizontal < -deadband else "center-x"
    vertical_label = "down" if vertical > deadband else "up" if vertical < -deadband else "center-y"
    return f"{horizontal_label}/{vertical_label}"


def select_control_axes(
    horizontal: float,
    vertical: float,
    deadband: float,
    control_mode: str,
) -> tuple[bool, bool, str]:
    if control_mode == "altaz":
        if abs(horizontal) > deadband:
            return True, False, "align-pan"
        if abs(vertical) > deadband:
            return False, True, "track-tilt"
        return False, False, "locked"
    return (
        abs(horizontal) > deadband,
        abs(vertical) > deadband,
        "cartesian",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args()
    require_serial()
    if args.calibration_samples < 1:
        raise SystemExit("--calibration-samples must be positive")
    if args.deadband <= 0 or args.max_step <= 0 or args.min_step <= 0:
        raise SystemExit("deadband and step values must be positive")
    if args.fixed_tilt_gain <= 0 or args.fixed_center_deadband <= 0:
        raise SystemExit("fixed-sensor gain and center deadband must be positive")
    if args.fixed_hemisphere_deadband < 0 or args.target_deadband_deg <= 0:
        raise SystemExit("fixed-sensor hemisphere and target deadbands are invalid")
    if not 0 < args.shading_drop_ratio < 1:
        raise SystemExit("--shading-drop-ratio must be between 0 and 1")
    if min(
        args.shading_learn_samples,
        args.shading_trigger_samples,
        args.shading_recovery_samples,
    ) < 1:
        raise SystemExit("shading sample counts must be positive")
    if not 0 <= args.sensor_fault_low_count < args.sensor_fault_high_count <= 4095:
        raise SystemExit("invalid LDR sensor fault thresholds")
    if args.pan_channel == args.tilt_channel:
        raise SystemExit("pan and tilt channels must be different")
    if args.shunt_ohms <= 0:
        raise SystemExit("--shunt-ohms must be positive")
    if args.ina_bus_voltage_scale <= 0:
        raise SystemExit("--ina-bus-voltage-scale must be positive")
    if args.battery_capacity_ah <= 0 or args.battery_nominal_voltage <= 0:
        raise SystemExit("battery capacity and nominal voltage must be positive")
    if args.bess_idle_current_ma < 0:
        raise SystemExit("--bess-idle-current-ma must not be negative")
    if args.panel_load_ohms is not None and args.panel_load_ohms <= 0:
        raise SystemExit("--panel-load-ohms must be positive")
    if args.udp_port < 1 or args.udp_port > 65535:
        raise SystemExit("--udp-port must be in 1..65535")
    if args.ina_enable and Ina226 is None:
        raise SystemExit("INA226 mode needs ina226_reader.py and smbus/smbus2 on the Orin")

    pan_angle = clamp(args.pan_start, args.pan_min, args.pan_max)
    tilt_angle = clamp(args.tilt_start, args.tilt_min, args.tilt_max)
    pan_orientation = -1.0 if args.invert_pan else 1.0
    tilt_orientation = -1.0 if args.invert_tilt else 1.0
    pan_gate = StableDirection(args.stable_samples)
    tilt_gate = StableDirection(args.stable_samples)
    fixed_selector = SequentialAxisSelector()
    shading_detector = ShadingDetector(
        args.shading_learn_samples,
        args.shading_drop_ratio,
        args.shading_trigger_samples,
        args.shading_recovery_samples,
    )
    fixed_mapper = FixedSensorMapper(
        args.pan_start,
        args.tilt_start,
        args.pan_min,
        args.pan_max,
        args.tilt_min,
        args.tilt_max,
        args.fixed_tilt_gain,
        args.fixed_center_deadband,
        args.fixed_hemisphere_deadband,
        pan_orientation,
        tilt_orientation,
    )
    try:
        altaz_sequencer = AltAzSequencer(
            args.pan_align_deadband,
            args.pan_realign_deadband,
            args.pan_align_angle_deg,
            args.pan_realign_angle_deg,
            args.max_pan_phase_samples,
            args.min_tilt_phase_samples,
        )
        dominant_selector = DominantAxisSelector(args.axis_switch_margin)
        sequential_selector = SequentialAxisSelector()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    pca = None
    ina = None

    with ExitStack() as stack:
        port = stack.enter_context(serial.Serial(args.port, args.baud, timeout=args.serial_timeout))
        udp_sock = None
        if args.udp_host is not None:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            stack.callback(udp_sock.close)
        if args.drive_servos or args.ina_enable:
            require_smbus()
            bus = stack.enter_context(SMBus(args.bus))
        if args.drive_servos:
            pca = Pca9685(bus, args.addr, 50.0)
            mode1_before = pca.read_u8(MODE1)
            pca.begin()
            print(f"PCA9685 addr=0x{args.addr:02X} bus={args.bus} mode1_before=0x{mode1_before:02X}")
            set_servo_angle(pca, args.pan_channel, pan_angle, args.min_pulse_us, args.max_pulse_us, 0.0)
            set_servo_angle(pca, args.tilt_channel, tilt_angle, args.min_pulse_us, args.max_pulse_us, 0.5)
        else:
            print("DRY RUN: servo output is OFF")
        if args.ina_enable:
            ina = Ina226(bus, args.ina_addr, args.shunt_ohms, args.ina_bus_voltage_scale)
            config = ina.read_u16(REG_CONFIG)
            manufacturer_id = ina.read_u16(REG_MANUFACTURER_ID)
            die_id = ina.read_u16(REG_DIE_ID)
            print(
                f"INA226 addr=0x{args.ina_addr:02X} bus={args.bus} "
                f"config=0x{config:04X} manufacturer_id=0x{manufacturer_id:04X} "
                f"die_id=0x{die_id:04X}"
            )
        if udp_sock is not None:
            print(f"Sending UDP to {args.udp_host}:{args.udp_port}")

        log_handle = None
        log_writer = None
        if args.log is not None:
            log_handle, log_writer = open_tracker_log(args.log, args.overwrite_log)
            stack.callback(log_handle.close)
            print(f"Logging to {args.log}")

        try:
            if args.calibration_in is not None:
                h_center, v_center = load_calibration(args.calibration_in)
                print(
                    f"CAL LOADED h_center={h_center * 100:+.3f}% "
                    f"v_center={v_center * 100:+.3f}% from {args.calibration_in}"
                )
            else:
                h_center, v_center = calibrate(
                    port,
                    args.calibration_samples,
                    args.min_total_counts,
                    args.saturation_count,
                )
                if args.calibration_out is not None:
                    save_calibration(args.calibration_out, h_center, v_center)
                    print(f"Saved calibration to {args.calibration_out}")
            if args.calibrate_only:
                return 0

            accepted = 0
            while args.max_packets is None or accepted < args.max_packets:
                sample = read_valid_sample(
                    port,
                    args.min_total_counts,
                    args.saturation_count,
                    accept_fault_samples=True,
                )
                if sample is None:
                    continue
                h_raw, v_raw = sample.normalized_errors()
                h_error = h_raw - h_center
                v_error = v_raw - v_center
                input_fault = input_fault_status(
                    sample,
                    args.min_total_counts,
                    args.sensor_fault_low_count,
                    args.sensor_fault_high_count,
                )

                target_pan = None
                target_tilt = None
                fixed_mode = args.sensor_mount == "fixed"
                if input_fault.active:
                    target_pan = pan_angle
                    target_tilt = tilt_angle
                    pan_error = tilt_error = 0.0
                    use_pan = use_tilt = False
                    phase = "sensor-hold"
                elif fixed_mode:
                    target_pan, target_tilt = fixed_mapper.targets(h_error, v_error)
                    pan_error = target_pan - pan_angle
                    tilt_error = target_tilt - tilt_angle
                    pan_available = axis_can_move(
                        pan_angle,
                        pan_error,
                        args.pan_min,
                        args.pan_max,
                        args.target_deadband_deg,
                    )
                    tilt_available = axis_can_move(
                        tilt_angle,
                        tilt_error,
                        args.tilt_min,
                        args.tilt_max,
                        args.target_deadband_deg,
                    )
                    use_pan, use_tilt, phase = fixed_selector.select(
                        pan_error,
                        tilt_error,
                        args.target_deadband_deg,
                        pan_available,
                        tilt_available,
                    )
                elif args.control_mode in ("sequential", "dominant", "altaz"):
                    pan_error = altaz_pan_error(h_error, v_error, args.deadband)
                    tilt_error = v_error
                else:
                    pan_error = h_error
                    tilt_error = v_error

                if not fixed_mode and args.control_mode in ("sequential", "dominant"):
                    pan_available = axis_can_move(
                        pan_angle,
                        pan_error * pan_orientation,
                        args.pan_min,
                        args.pan_max,
                        args.deadband,
                    )
                    tilt_available = axis_can_move(
                        tilt_angle,
                        v_error * tilt_orientation,
                        args.tilt_min,
                        args.tilt_max,
                        args.deadband,
                    )
                    if args.control_mode == "sequential":
                        use_pan, use_tilt, phase = sequential_selector.select(
                            pan_error,
                            v_error,
                            args.deadband,
                            pan_available,
                            tilt_available,
                        )
                    else:
                        use_pan, use_tilt, phase = dominant_selector.select(
                            pan_error,
                            v_error,
                            args.deadband,
                            pan_available,
                            tilt_available,
                        )
                elif not fixed_mode and args.control_mode == "altaz":
                    use_pan, use_tilt, phase = altaz_sequencer.select(
                        h_error, v_error, args.deadband
                    )
                elif not fixed_mode:
                    use_pan, use_tilt, phase = select_control_axes(
                        h_error, v_error, args.deadband, args.control_mode
                    )
                if args.disable_tracking:
                    use_pan = False
                    use_tilt = False
                    phase = "fixed-hold"
                if input_fault.active:
                    use_pan = False
                    use_tilt = False
                    phase = "sensor-hold"
                control_deadband = args.target_deadband_deg if fixed_mode else args.deadband
                pan_sign = pan_gate.update(pan_error if use_pan else 0.0, control_deadband)
                tilt_sign = tilt_gate.update(tilt_error if use_tilt else 0.0, control_deadband)
                pan_delta = 0.0
                tilt_delta = 0.0
                if pan_sign:
                    if fixed_mode:
                        pan_delta = step_toward_target(
                            pan_error, args.target_deadband_deg, args.min_step, args.max_step
                        )
                    else:
                        pan_delta = step_from_error(
                            pan_error, args.deadband, args.gain, args.min_step, args.max_step
                        ) * pan_orientation
                if tilt_sign:
                    if fixed_mode:
                        tilt_delta = step_toward_target(
                            tilt_error, args.target_deadband_deg, args.min_step, args.max_step
                        )
                    else:
                        tilt_delta = step_from_error(
                            v_error, args.deadband, args.gain, args.min_step, args.max_step
                        ) * tilt_orientation

                new_pan = clamp(pan_angle + pan_delta, args.pan_min, args.pan_max)
                new_tilt = clamp(tilt_angle + tilt_delta, args.tilt_min, args.tilt_max)
                if pca is not None and (new_pan != pan_angle or new_tilt != tilt_angle):
                    set_servo_angle(pca, args.pan_channel, new_pan, args.min_pulse_us, args.max_pulse_us, 0.0)
                    set_servo_angle(pca, args.tilt_channel, new_tilt, args.min_pulse_us, args.max_pulse_us, 0.0)
                pan_angle = new_pan
                tilt_angle = new_tilt
                accepted += 1
                battery_snapshot = None
                if ina is not None:
                    snapshot = ina.read_snapshot()
                    timestamp_utc = str(snapshot["timestamp_utc"])
                    if args.ina_role == "bess":
                        battery_snapshot = snapshot
                        voltage_mv = float(sample.panel_mv)
                        current_ma = power_mw = 0.0
                        power_source = "mcp3208-voltage-only"
                    else:
                        voltage_mv = float(snapshot["bus_mv"])
                        current_ma = float(snapshot["current_ma"])
                        power_mw = float(snapshot["power_mw"])
                        power_source = "ina226"
                else:
                    timestamp_utc = datetime.now(timezone.utc).isoformat()
                    voltage_mv = float(sample.panel_mv)
                    current_ma = power_mw = 0.0
                    power_source = "mcp3208-voltage-only"

                if args.panel_load_ohms is not None:
                    voltage_mv, current_ma, power_mw = panel_load_measurement(
                        float(sample.panel_mv), args.panel_load_ohms
                    )
                    power_source = f"mcp3208-{args.panel_load_ohms:g}-ohm-load-estimate"

                if target_pan is not None and target_tilt is not None:
                    track_error_deg = math.hypot(target_pan - pan_angle, target_tilt - tilt_angle)
                else:
                    track_error_deg = math.hypot(h_error, v_error) * 100.0

                shading_status = shading_detector.update(sample, power_mw, phase)
                fault_status = input_fault if input_fault.active else shading_status

                if log_writer is not None and log_handle is not None:
                    log_writer.writerow(
                        {
                            "timestamp_utc": timestamp_utc,
                            "seq": accepted - 1,
                            "ldr_seq": sample.seq,
                            "detected": 1,
                            "panel_mv": sample.panel_mv,
                            "tl": sample.tl,
                            "tr": sample.tr,
                            "bl": sample.bl,
                            "br": sample.br,
                            "h_error_pct": round(h_error * 100.0, 6),
                            "v_error_pct": round(v_error * 100.0, 6),
                            "pan_deg": round(pan_angle, 6),
                            "tilt_deg": round(tilt_angle, 6),
                            "target_pan_deg": "" if target_pan is None else round(target_pan, 6),
                            "target_tilt_deg": "" if target_tilt is None else round(target_tilt, 6),
                            "track_error_deg": round(track_error_deg, 6),
                            "state": phase,
                            "v_mv": "" if voltage_mv is None else voltage_mv,
                            "i_ma": "" if current_ma is None else current_ma,
                            "p_mw": "" if power_mw is None else power_mw,
                            "power_source": power_source,
                            "battery_v_mv": "" if battery_snapshot is None else battery_snapshot["bus_mv"],
                            "battery_i_ma": "" if battery_snapshot is None else battery_snapshot["current_ma"],
                            "battery_p_mw": "" if battery_snapshot is None else battery_snapshot["power_mw"],
                            "bess_state": "" if battery_snapshot is None else (
                                "charging"
                                if float(battery_snapshot["current_ma"]) > args.bess_idle_current_ma
                                else "discharging"
                                if float(battery_snapshot["current_ma"]) < -args.bess_idle_current_ma
                                else "idle"
                            ),
                            "fault_label": fault_status.label,
                            "fault_reason": fault_status.reason,
                            "fault_severity": fault_status.severity,
                            "servo_enabled": int(pca is not None and not args.disable_tracking),
                            "sensor_mount": args.sensor_mount,
                        }
                    )
                    log_handle.flush()
                servo_enabled = pca is not None and not args.disable_tracking
                if udp_sock is not None:
                    packet = make_udp_packet(
                        accepted - 1,
                        timestamp_utc,
                        args,
                        sample,
                        h_error,
                        v_error,
                        pan_angle,
                        tilt_angle,
                        target_pan,
                        target_tilt,
                        track_error_deg,
                        phase,
                        voltage_mv,
                        current_ma,
                        power_mw,
                        power_source,
                        servo_enabled,
                        fault_status,
                        battery_snapshot,
                    )
                    payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
                    udp_sock.sendto(payload, (args.udp_host, args.udp_port))
                target_text = (
                    f" target={target_pan:.1f}/{target_tilt:.1f}"
                    if target_pan is not None and target_tilt is not None
                    else ""
                )
                bess_text = (
                    ""
                    if battery_snapshot is None
                    else (
                        f"bess={float(battery_snapshot['bus_mv']) / 1000:.3f}V/"
                        f"{float(battery_snapshot['current_ma']):+.1f}mA/"
                        f"{float(battery_snapshot['power_mw']):+.1f}mW "
                    )
                )
                print(
                    f"seq={sample.seq:05d} pv={sample.panel_mv / 1000:.3f}V "
                    f"h={h_error * 100:+.3f}% v={v_error * 100:+.3f}% "
                    f"dir={axis_label(h_error, v_error, args.deadband)} "
                    f"phase={phase} "
                    f"pan={pan_angle:.2f} tilt={tilt_angle:.2f} "
                    f"mount={args.sensor_mount}{target_text} "
                    f"p={'n/a' if power_mw is None else f'{power_mw:.3f}mW'} "
                    f"{bess_text}"
                    f"fault={fault_status.label} "
                    f"drive={'on' if pca is not None else 'off'}"
                )
        except KeyboardInterrupt:
            print("Stopped by user.")
        finally:
            if pca is not None and not args.hold_on_exit:
                pca.release(args.pan_channel)
                pca.release(args.tilt_channel)
                print(f"Released PCA9685 channels {args.pan_channel} and {args.tilt_channel}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
