#!/usr/bin/env python3
"""Software-only solar tracker loop with UDP dashboard telemetry.

This is the no-mechanics path: it simulates four LDRs and a pan/tilt control
loop now, then can drive the PCA9685 later with --drive-servos.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ina226_reader import REG_CONFIG, REG_DIE_ID, REG_MANUFACTURER_ID, Ina226, SMBus
except (ImportError, SystemExit):  # pragma: no cover - target hardware dependency
    REG_CONFIG = REG_DIE_ID = REG_MANUFACTURER_ID = 0
    Ina226 = None  # type: ignore
    SMBus = None  # type: ignore

try:
    from pca9685_servo_test import MODE1, Pca9685, set_servo_angle
except ImportError:  # pragma: no cover - optional actuator dependency
    MODE1 = 0
    Pca9685 = None  # type: ignore
    set_servo_angle = None  # type: ignore


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a software solar-tracking loop and send UDP dashboard packets."
    )
    parser.add_argument("--udp-host", default="127.0.0.1", help="UDP destination host.")
    parser.add_argument("--udp-port", type=int, default=5011, help="UDP destination port.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between packets.")
    parser.add_argument("--max-packets", type=int, help="Stop after this many packets.")
    parser.add_argument("--source-label", default="Orin software solar tracker", help="Dashboard source label.")
    parser.add_argument("--log", type=Path, default=Path("solar-tracker-bess/data/tracker_softloop_udp_gateway_log.csv"))

    parser.add_argument("--pan-min", type=float, default=35.0, help="Minimum safe pan angle.")
    parser.add_argument("--pan-max", type=float, default=145.0, help="Maximum safe pan angle.")
    parser.add_argument("--tilt-min", type=float, default=55.0, help="Minimum safe tilt angle.")
    parser.add_argument("--tilt-max", type=float, default=125.0, help="Maximum safe tilt angle.")
    parser.add_argument("--pan-start", type=float, default=90.0, help="Initial simulated pan angle.")
    parser.add_argument("--tilt-start", type=float, default=90.0, help="Initial simulated tilt angle.")
    parser.add_argument("--control-gain", type=float, default=18.0, help="LDR balance to angle gain.")
    parser.add_argument("--lock-error-deg", type=float, default=6.0, help="Error threshold for locked state.")

    parser.add_argument("--sun-pan-center", type=float, default=90.0, help="Virtual sun pan center.")
    parser.add_argument("--sun-pan-span", type=float, default=42.0, help="Virtual sun pan motion amplitude.")
    parser.add_argument("--sun-tilt-center", type=float, default=88.0, help="Virtual sun tilt center.")
    parser.add_argument("--sun-tilt-span", type=float, default=20.0, help="Virtual sun tilt motion amplitude.")
    parser.add_argument("--sun-period", type=float, default=70.0, help="Seconds per virtual sun cycle.")
    parser.add_argument("--irradiance-wm2", type=float, default=850.0, help="Virtual light strength.")

    parser.add_argument("--ina-enable", action="store_true", help="Use real INA226 values for v/i/p.")
    parser.add_argument("--ina-bus", type=int, default=7, help="INA226 I2C bus.")
    parser.add_argument("--ina-addr", type=lambda value: int(value, 0), default=0x44, help="INA226 address.")
    parser.add_argument("--shunt-ohms", type=float, default=0.1, help="INA226 shunt resistor value.")

    parser.add_argument("--drive-servos", action="store_true", help="Drive real PCA9685 servos too.")
    parser.add_argument("--disable-pan-servo", action="store_true", help="Do not send PWM to the pan servo.")
    parser.add_argument("--disable-tilt-servo", action="store_true", help="Do not send PWM to the tilt servo.")
    parser.add_argument("--pca-bus", type=int, default=7, help="PCA9685 I2C bus.")
    parser.add_argument("--pca-addr", type=lambda value: int(value, 0), default=0x40, help="PCA9685 address.")
    parser.add_argument("--pan-channel", type=int, default=15, help="Pan servo channel.")
    parser.add_argument("--tilt-channel", type=int, default=12, help="Tilt servo channel.")
    parser.add_argument("--min-pulse-us", type=float, default=600.0, help="Pulse width for 0 degrees.")
    parser.add_argument("--max-pulse-us", type=float, default=2400.0, help="Pulse width for 180 degrees.")
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def servo_axis_status(
    servo_enabled: bool,
    disable_pan_servo: bool,
    disable_tilt_servo: bool,
) -> tuple[bool, bool, str]:
    pan_enabled = servo_enabled and not disable_pan_servo
    tilt_enabled = servo_enabled and not disable_tilt_servo
    if pan_enabled and tilt_enabled:
        mode = "pan+tilt"
    elif pan_enabled:
        mode = "pan-only"
    elif tilt_enabled:
        mode = "tilt-only"
    else:
        mode = "software"
    return pan_enabled, tilt_enabled, mode


def release_disabled_servo_channels(pca: Pca9685, args: argparse.Namespace) -> None:
    if args.disable_pan_servo:
        pca.release(args.pan_channel)
        print(f"channel={args.pan_channel} pan PWM released")
    if args.disable_tilt_servo:
        pca.release(args.tilt_channel)
        print(f"channel={args.tilt_channel} tilt PWM released")


def open_log(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)
    if path.stat().st_size == 0:
        writer.writerow(
            [
                "timestamp_utc",
                "seq",
                "pan_deg",
                "tilt_deg",
                "sun_pan_deg",
                "sun_tilt_deg",
                "track_error_deg",
                "state",
                "v_mv",
                "i_ma",
                "p_mw",
                "servo_enabled",
                "udp_host",
                "udp_port",
                "raw_line",
            ]
        )
    return file_handle, writer


def virtual_sun(t_s: float, args: argparse.Namespace) -> tuple[float, float]:
    phase = 2.0 * math.pi * (t_s % args.sun_period) / args.sun_period
    sun_pan = args.sun_pan_center + args.sun_pan_span * math.sin(phase)
    sun_tilt = args.sun_tilt_center + args.sun_tilt_span * math.sin(0.73 * phase + 0.8)
    return sun_pan, sun_tilt


def simulate_ldr(panel_pan: float, panel_tilt: float, sun_pan: float, sun_tilt: float) -> dict[str, int]:
    pan_error = sun_pan - panel_pan
    tilt_error = sun_tilt - panel_tilt
    angular_error = math.hypot(pan_error, tilt_error)

    base = 900.0 + 3000.0 * max(0.0, math.cos(math.radians(min(89.0, angular_error))))
    lr = clamp(pan_error / 45.0, -1.0, 1.0)
    tb = clamp(tilt_error / 35.0, -1.0, 1.0)

    tl = base * (1.0 - 0.18 * lr + 0.18 * tb)
    tr = base * (1.0 + 0.18 * lr + 0.18 * tb)
    bl = base * (1.0 - 0.18 * lr - 0.18 * tb)
    br = base * (1.0 + 0.18 * lr - 0.18 * tb)
    return {
        "tl": int(clamp(tl, 0.0, 4095.0)),
        "tr": int(clamp(tr, 0.0, 4095.0)),
        "bl": int(clamp(bl, 0.0, 4095.0)),
        "br": int(clamp(br, 0.0, 4095.0)),
    }


def ldr_balance(ldr: dict[str, int]) -> tuple[float, float]:
    total = max(1.0, float(sum(ldr.values())))
    left = ldr["tl"] + ldr["bl"]
    right = ldr["tr"] + ldr["br"]
    top = ldr["tl"] + ldr["tr"]
    bottom = ldr["bl"] + ldr["br"]
    return (right - left) / total, (top - bottom) / total


def simulated_power(panel_pan: float, panel_tilt: float, sun_pan: float, sun_tilt: float, irradiance: float) -> tuple[float, float, float]:
    angular_error = math.hypot(sun_pan - panel_pan, sun_tilt - panel_tilt)
    alignment = max(0.0, math.cos(math.radians(min(89.0, angular_error))))
    power_mw = 1800.0 * (irradiance / 850.0) * alignment * alignment
    voltage_mv = 4200.0 + 1200.0 * alignment
    current_ma = power_mw / max(1.0, voltage_mv / 1000.0)
    return voltage_mv, current_ma, power_mw


def make_packet(
    seq: int,
    args: argparse.Namespace,
    pan: float,
    tilt: float,
    sun_pan: float,
    sun_tilt: float,
    ldr: dict[str, int],
    lr_error: float,
    tb_error: float,
    sensor_values: tuple[float, float, float],
    servo_enabled: bool,
) -> dict[str, Any]:
    v_mv, i_ma, p_mw = sensor_values
    pan_servo_enabled, tilt_servo_enabled, servo_mode = servo_axis_status(
        servo_enabled,
        args.disable_pan_servo,
        args.disable_tilt_servo,
    )
    track_error = math.hypot(sun_pan - pan, sun_tilt - tilt)
    state = "locked" if track_error <= args.lock_error_deg else "seeking"
    pan_span = max(1.0, args.pan_max - args.pan_min)
    pan_pct = int(round(100.0 * (pan - args.pan_min) / pan_span))
    raw_line = (
        f"trk,seq={seq:05d},pan={pan:06.2f},tilt={tilt:06.2f},"
        f"sun_pan={sun_pan:06.2f},sun_tilt={sun_tilt:06.2f},"
        f"err={track_error:05.2f},state={state},"
        f"ldr={ldr['tl']:04d}/{ldr['tr']:04d}/{ldr['bl']:04d}/{ldr['br']:04d}"
    )
    return {
        "schema": "solar.telemetry.v1",
        "schema_variant": "orin.tracker_softloop.v1",
        "source_project": "solar-tracker-bess",
        "network_project": "network-telemetry-dashboard",
        "source_label": args.source_label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "valid": True,
        "error": "",
        "seq_gap": 0,
        "seq": seq,
        "raw": "00",
        "d_pct": int(clamp(pan_pct, 0, 100)),
        "v_mv": round(v_mv, 3),
        "i_ma": round(i_ma, 3),
        "p_mw": round(p_mw, 3),
        "mppt": "trk",
        "mppt_label": "Tracking",
        "mppt_reason": "Software LDR loop is steering the panel toward maximum light.",
        "fault": 0,
        "fault_label": "OK",
        "fault_reason": "No protection flag active in software tracker mode.",
        "fault_severity": "normal",
        "chk": "",
        "computed_chk": "",
        "raw_line": raw_line,
        "tracker": {
            "state": state,
            "reason": (
                "Panel is within the configured tracking error threshold."
                if state == "locked"
                else "Panel is still moving toward the virtual light source."
            ),
            "pan_deg": round(pan, 3),
            "tilt_deg": round(tilt, 3),
            "sun_pan_deg": round(sun_pan, 3),
            "sun_tilt_deg": round(sun_tilt, 3),
            "track_error_deg": round(track_error, 3),
            "lr_error": round(lr_error, 5),
            "tb_error": round(tb_error, 5),
            "ldr": ldr,
            "servo_enabled": servo_enabled,
            "pan_servo_enabled": pan_servo_enabled,
            "tilt_servo_enabled": tilt_servo_enabled,
            "servo_mode": servo_mode,
        },
    }


def write_log(writer, packet: dict[str, Any], udp_host: str, udp_port: int) -> None:
    tracker = packet.get("tracker", {})
    if not isinstance(tracker, dict):
        tracker = {}
    writer.writerow(
        [
            packet.get("timestamp_utc", ""),
            packet.get("seq", ""),
            tracker.get("pan_deg", ""),
            tracker.get("tilt_deg", ""),
            tracker.get("sun_pan_deg", ""),
            tracker.get("sun_tilt_deg", ""),
            tracker.get("track_error_deg", ""),
            tracker.get("state", ""),
            packet.get("v_mv", ""),
            packet.get("i_ma", ""),
            packet.get("p_mw", ""),
            int(bool(tracker.get("servo_enabled", False))),
            udp_host,
            udp_port,
            packet.get("raw_line", ""),
        ]
    )


def validate_args(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")
    if args.pan_min >= args.pan_max or args.tilt_min >= args.tilt_max:
        raise SystemExit("min angle must be less than max angle")
    if args.ina_enable and (SMBus is None or Ina226 is None):
        raise SystemExit("INA226 mode needs ina226_reader.py and smbus/smbus2 on the Orin")
    if args.drive_servos and (SMBus is None or Pca9685 is None or set_servo_angle is None):
        raise SystemExit("servo mode needs pca9685_servo_test.py and smbus/smbus2 on the Orin")
    for channel in (args.pan_channel, args.tilt_channel):
        if channel < 0 or channel > 15:
            raise SystemExit("servo channels must be 0-15")
    if args.drive_servos and args.disable_pan_servo and args.disable_tilt_servo:
        raise SystemExit("servo output requested, but both servo axes are disabled")


def main() -> int:
    configure_stdout()
    args = parse_args()
    validate_args(args)

    csv_file, writer = open_log(args.log)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    pan = clamp(args.pan_start, args.pan_min, args.pan_max)
    tilt = clamp(args.tilt_start, args.tilt_min, args.tilt_max)
    start_s = time.monotonic()

    ina_bus = None
    ina_sensor = None
    pca_bus = None
    pca = None

    try:
        if args.ina_enable:
            ina_bus = SMBus(args.ina_bus)
            ina_sensor = Ina226(ina_bus, args.ina_addr, args.shunt_ohms)
            config = ina_sensor.read_u16(REG_CONFIG)
            manufacturer_id = ina_sensor.read_u16(REG_MANUFACTURER_ID)
            die_id = ina_sensor.read_u16(REG_DIE_ID)
            print(f"INA226 addr=0x{args.ina_addr:02X} bus={args.ina_bus}")
            print(f"config=0x{config:04X} manufacturer_id=0x{manufacturer_id:04X} die_id=0x{die_id:04X}")

        if args.drive_servos:
            pca_bus = SMBus(args.pca_bus)
            pca = Pca9685(pca_bus, args.pca_addr, 50.0)
            mode1_before = pca.read_u8(MODE1)
            pca.begin()
            release_disabled_servo_channels(pca, args)
            mode1_after = pca.read_u8(MODE1)
            print(
                f"PCA9685 addr=0x{args.pca_addr:02X} bus={args.pca_bus} "
                f"mode1_before=0x{mode1_before:02X} mode1_after=0x{mode1_after:02X}"
            )

        print(f"Sending UDP to {args.udp_host}:{args.udp_port}")
        print(f"Logging to {args.log}")
        if args.drive_servos:
            disabled_axes = [
                name
                for name, disabled in (("pan", args.disable_pan_servo), ("tilt", args.disable_tilt_servo))
                if disabled
            ]
            suffix = "" if not disabled_axes else f" ({'/'.join(disabled_axes)} servo disabled)"
            print(f"Servo output is ON{suffix}")
        else:
            print("Servo output is OFF; software-only tracking.")

        seq = 0
        while args.max_packets is None or seq < args.max_packets:
            t_s = time.monotonic() - start_s
            sun_pan, sun_tilt = virtual_sun(t_s, args)
            ldr = simulate_ldr(pan, tilt, sun_pan, sun_tilt)
            lr_error, tb_error = ldr_balance(ldr)

            pan = clamp(pan + args.control_gain * lr_error, args.pan_min, args.pan_max)
            tilt = clamp(tilt + args.control_gain * tb_error, args.tilt_min, args.tilt_max)

            if args.ina_enable and ina_sensor is not None:
                snapshot = ina_sensor.read_snapshot()
                sensor_values = (
                    float(snapshot["bus_mv"]),
                    float(snapshot["current_ma"]),
                    float(snapshot["power_mw"]),
                )
            else:
                sensor_values = simulated_power(pan, tilt, sun_pan, sun_tilt, args.irradiance_wm2)

            if args.drive_servos and pca is not None and set_servo_angle is not None:
                if not args.disable_pan_servo:
                    set_servo_angle(pca, args.pan_channel, pan, args.min_pulse_us, args.max_pulse_us, 0.0)
                if not args.disable_tilt_servo:
                    set_servo_angle(pca, args.tilt_channel, tilt, args.min_pulse_us, args.max_pulse_us, 0.0)

            packet = make_packet(
                seq,
                args,
                pan,
                tilt,
                sun_pan,
                sun_tilt,
                ldr,
                lr_error,
                tb_error,
                sensor_values,
                args.drive_servos,
            )
            payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
            sock.sendto(payload, (args.udp_host, args.udp_port))
            write_log(writer, packet, args.udp_host, args.udp_port)
            csv_file.flush()
            tracker = packet["tracker"]
            print(
                f"{packet['timestamp_utc']} udp->{args.udp_host}:{args.udp_port} "
                f"seq={seq:05d} pan={tracker['pan_deg']:.1f} tilt={tracker['tilt_deg']:.1f} "
                f"err={tracker['track_error_deg']:.1f} state={tracker['state']} "
                f"p={packet['p_mw']}mW"
            )
            seq += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        csv_file.close()
        sock.close()
        if ina_bus is not None:
            ina_bus.close()
        if pca_bus is not None:
            pca_bus.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
