#!/usr/bin/env python3
"""Camera-based light tracker UDP gateway for the Orin.

The default mode only estimates the brightest light target and sends telemetry.
Add --drive-servos after camera detection is stable.
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
    parser = argparse.ArgumentParser(description="Detect a bright light target with a camera and send tracker UDP.")
    parser.add_argument("--udp-host", default="127.0.0.1", help="UDP destination host.")
    parser.add_argument("--udp-port", type=int, default=5013, help="UDP destination port.")
    parser.add_argument("--interval", type=float, default=0.25, help="Seconds between packets.")
    parser.add_argument("--max-packets", type=int, help="Stop after this many packets.")
    parser.add_argument("--source-label", default="Orin CSI camera solar tracker", help="Dashboard source label.")
    parser.add_argument("--log", type=Path, default=Path("solar-tracker-bess/data/camera_light_tracker_udp_log.csv"))

    parser.add_argument("--synthetic", action="store_true", help="Use a synthetic moving light target instead of camera.")
    parser.add_argument("--camera", choices=["csi", "usb"], default="csi", help="Camera input type.")
    parser.add_argument(
        "--camera-mount",
        choices=["moving", "fixed"],
        default="moving",
        help="Whether the camera moves with the panel or is fixed to the base.",
    )
    parser.add_argument("--camera-id", type=int, default=0, help="CSI sensor id or USB camera index.")
    parser.add_argument("--width", type=int, default=640, help="Capture width.")
    parser.add_argument("--height", type=int, default=480, help="Capture height.")
    parser.add_argument("--framerate", type=int, default=30, help="Camera framerate.")
    parser.add_argument("--flip-method", type=int, default=0, help="CSI nvvidconv flip method.")
    parser.add_argument("--threshold-min", type=int, default=180, help="Minimum brightness threshold, 0-255.")
    parser.add_argument("--threshold-percentile", type=float, default=99.5, help="Bright-pixel percentile threshold.")
    parser.add_argument("--min-area-px", type=int, default=6, help="Minimum bright target area in pixels.")
    parser.add_argument("--preview", action="store_true", help="Show camera preview window on the Orin desktop.")

    parser.add_argument("--pan-min", type=float, default=70.0, help="Minimum safe pan angle.")
    parser.add_argument("--pan-max", type=float, default=110.0, help="Maximum safe pan angle.")
    parser.add_argument("--tilt-min", type=float, default=80.0, help="Minimum safe tilt angle.")
    parser.add_argument("--tilt-max", type=float, default=100.0, help="Maximum safe tilt angle.")
    parser.add_argument("--pan-start", type=float, default=90.0, help="Initial pan angle.")
    parser.add_argument("--tilt-start", type=float, default=90.0, help="Initial tilt angle.")
    parser.add_argument("--control-gain", type=float, default=12.0, help="Camera normalized error to servo angle gain.")
    parser.add_argument("--pan-gain", type=float, help="Override servo gain for the pan axis.")
    parser.add_argument("--tilt-gain", type=float, help="Override servo gain for the tilt axis.")
    parser.add_argument("--invert-x", action="store_true", help="Invert camera X error before pan control.")
    parser.add_argument("--invert-y", action="store_true", help="Invert camera Y error before tilt control.")
    parser.add_argument("--disable-pan", action="store_true", help="Hold pan angle while reporting camera X error.")
    parser.add_argument("--disable-tilt", action="store_true", help="Hold tilt angle while reporting camera Y error.")
    parser.add_argument(
        "--pan-only",
        action="store_true",
        help="Track and drive pan only; hold tilt in software and release its PCA9685 channel.",
    )
    parser.add_argument("--lock-error-deg", type=float, default=5.0, help="Error threshold for locked state.")
    parser.add_argument("--camera-pan-fov-deg", type=float, default=62.0, help="Approximate camera horizontal FOV.")
    parser.add_argument("--camera-tilt-fov-deg", type=float, default=49.0, help="Approximate camera vertical FOV.")
    parser.add_argument("--max-pan-step", type=float, default=2.0, help="Maximum pan change per packet for a fixed camera.")
    parser.add_argument("--max-tilt-step", type=float, default=2.0, help="Maximum tilt change per packet for a fixed camera.")

    parser.add_argument("--ina-enable", action="store_true", help="Use real INA226 values for v/i/p.")
    parser.add_argument("--ina-bus", type=int, default=7, help="INA226 I2C bus.")
    parser.add_argument("--ina-addr", type=lambda value: int(value, 0), default=0x44, help="INA226 address.")
    parser.add_argument("--shunt-ohms", type=float, default=0.1, help="INA226 shunt resistor value.")

    parser.add_argument("--drive-servos", action="store_true", help="Drive real PCA9685 servos.")
    parser.add_argument("--disable-pan-servo", action="store_true", help="Do not send PWM to the pan servo.")
    parser.add_argument("--disable-tilt-servo", action="store_true", help="Do not send PWM to the tilt servo.")
    parser.add_argument("--pca-bus", type=int, default=7, help="PCA9685 I2C bus.")
    parser.add_argument("--pca-addr", type=lambda value: int(value, 0), default=0x40, help="PCA9685 address.")
    parser.add_argument("--pan-channel", type=int, default=15, help="Pan servo channel.")
    parser.add_argument("--tilt-channel", type=int, default=12, help="Tilt servo channel.")
    parser.add_argument("--min-pulse-us", type=float, default=600.0, help="Pulse width for 0 degrees.")
    parser.add_argument("--max-pulse-us", type=float, default=2400.0, help="Pulse width for 180 degrees.")
    args = parser.parse_args()
    if args.pan_only:
        args.disable_tilt = True
        args.disable_tilt_servo = True
    return args


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
                "detected",
                "confidence",
                "target_x_px",
                "target_y_px",
                "x_error",
                "y_error",
                "pan_deg",
                "tilt_deg",
                "target_pan_deg",
                "target_tilt_deg",
                "track_error_deg",
                "state",
                "v_mv",
                "i_ma",
                "p_mw",
                "servo_enabled",
                "camera_mode",
                "udp_host",
                "udp_port",
                "raw_line",
            ]
        )
    return file_handle, writer


def csi_pipeline(sensor_id: int, width: int, height: int, framerate: int, flip_method: int) -> str:
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width=(int){width}, height=(int){height}, "
        f"format=(string)NV12, framerate=(fraction){framerate}/1 ! "
        f"nvvidconv flip-method={flip_method} ! "
        "video/x-raw, format=(string)BGRx ! "
        "videoconvert ! video/x-raw, format=(string)BGR ! appsink drop=1"
    )


def open_camera(args: argparse.Namespace):
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - target hardware dependency
        raise SystemExit("OpenCV is required on Orin. Try: python3 -c 'import cv2; print(cv2.__version__)'") from exc

    if args.camera == "csi":
        cap = cv2.VideoCapture(
            csi_pipeline(args.camera_id, args.width, args.height, args.framerate, args.flip_method),
            cv2.CAP_GSTREAMER,
        )
    else:
        cap = cv2.VideoCapture(args.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, args.framerate)

    if not cap.isOpened():
        raise SystemExit("Could not open camera. Check CSI ribbon orientation, camera id, and Jetson camera setup.")
    return cv2, cap


def synthetic_detection(seq: int, width: int, height: int) -> dict[str, Any]:
    phase = seq * 0.17
    x = (0.5 + 0.34 * math.sin(phase)) * width
    y = (0.5 + 0.26 * math.sin(0.7 * phase + 0.8)) * height
    return {
        "detected": True,
        "target_x_px": x,
        "target_y_px": y,
        "frame_w": width,
        "frame_h": height,
        "confidence": 0.92,
        "brightness_max": 255,
        "area_px": 80,
        "mode": "synthetic",
    }


def detect_bright_target(cv2: Any, frame: Any, args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np  # type: ignore

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    threshold = max(args.threshold_min, float(np.percentile(blurred, args.threshold_percentile)))
    mask = blurred >= threshold
    y_indices, x_indices = np.nonzero(mask)
    height, width = gray.shape[:2]
    if len(x_indices) < args.min_area_px:
        return {
            "detected": False,
            "target_x_px": None,
            "target_y_px": None,
            "frame_w": width,
            "frame_h": height,
            "confidence": 0.0,
            "brightness_max": int(blurred.max()),
            "area_px": int(len(x_indices)),
            "mode": args.camera,
        }

    cx = float(x_indices.mean())
    cy = float(y_indices.mean())
    max_brightness = int(blurred.max())
    area_px = int(len(x_indices))
    area_confidence = min(1.0, area_px / max(1.0, width * height * 0.015))
    brightness_confidence = max(0.0, min(1.0, (max_brightness - args.threshold_min) / max(1.0, 255 - args.threshold_min)))
    confidence = max(0.05, min(1.0, 0.45 * area_confidence + 0.55 * brightness_confidence))

    return {
        "detected": True,
        "target_x_px": cx,
        "target_y_px": cy,
        "frame_w": width,
        "frame_h": height,
        "confidence": confidence,
        "brightness_max": max_brightness,
        "area_px": area_px,
        "mode": args.camera,
    }


def detection_to_errors(detection: dict[str, Any]) -> tuple[float, float]:
    if not detection.get("detected"):
        return 0.0, 0.0
    width = max(1.0, float(detection["frame_w"]))
    height = max(1.0, float(detection["frame_h"]))
    x = float(detection["target_x_px"])
    y = float(detection["target_y_px"])
    x_error = clamp((x - width / 2.0) / (width / 2.0), -1.0, 1.0)
    y_error = clamp((height / 2.0 - y) / (height / 2.0), -1.0, 1.0)
    return x_error, y_error


def target_angle(
    current: float,
    center: float,
    normalized_error: float,
    fov_deg: float,
    minimum: float,
    maximum: float,
    disabled: bool,
    camera_mount: str,
) -> float:
    if disabled:
        return current
    reference = center if camera_mount == "fixed" else current
    return clamp(reference + normalized_error * (fov_deg / 2.0), minimum, maximum)


def controlled_angle(
    current: float,
    target: float,
    normalized_error: float,
    gain: float,
    max_step: float,
    minimum: float,
    maximum: float,
    disabled: bool,
    camera_mount: str,
) -> float:
    if disabled:
        return current
    if camera_mount == "fixed":
        delta = clamp(target - current, -max_step, max_step)
    else:
        delta = gain * normalized_error
    return clamp(current + delta, minimum, maximum)


def simulated_power(track_error_deg: float) -> tuple[float, float, float]:
    alignment = max(0.0, math.cos(math.radians(min(89.0, track_error_deg))))
    power_mw = 1600.0 * alignment * alignment
    voltage_mv = 4200.0 + 1100.0 * alignment
    current_ma = power_mw / max(1.0, voltage_mv / 1000.0)
    return voltage_mv, current_ma, power_mw


def make_packet(
    seq: int,
    args: argparse.Namespace,
    pan: float,
    tilt: float,
    target_pan: float,
    target_tilt: float,
    x_error: float,
    y_error: float,
    detection: dict[str, Any],
    sensor_values: tuple[float, float, float],
    servo_enabled: bool,
) -> dict[str, Any]:
    v_mv, i_ma, p_mw = sensor_values
    pan_servo_enabled, tilt_servo_enabled, servo_mode = servo_axis_status(
        servo_enabled,
        args.disable_pan_servo,
        args.disable_tilt_servo,
    )
    track_error = math.hypot(target_pan - pan, target_tilt - tilt)
    detected = bool(detection.get("detected"))
    state = "locked" if detected and track_error <= args.lock_error_deg else "seeking" if detected else "lost"
    pan_pct = int(round(100.0 * (pan - args.pan_min) / max(1.0, args.pan_max - args.pan_min)))
    raw_line = (
        f"cvtrk,seq={seq:05d},det={int(detected)},conf={float(detection['confidence']):.2f},"
        f"x={x_error:+.3f},y={y_error:+.3f},pan={pan:05.1f},tilt={tilt:05.1f},"
        f"target={target_pan:05.1f}/{target_tilt:05.1f},err={track_error:04.1f},st={state}"
    )
    return {
        "schema": "solar.telemetry.v1",
        "schema_variant": "orin.camera_tracker.v1",
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
        "mppt": "cv",
        "mppt_label": "CV Tracking",
        "mppt_reason": "Camera estimates the brightest light direction for the solar tracker.",
        "fault": 0,
        "fault_label": "OK",
        "fault_reason": "No protection flag active in camera tracker mode.",
        "fault_severity": "normal",
        "chk": "",
        "computed_chk": "",
        "raw_line": raw_line,
        "tracker": {
            "state": state,
            "reason": (
                "Camera target is within the configured tracking error threshold."
                if state == "locked"
                else "Camera sees a bright target and the panel is still moving toward it."
                if state == "seeking"
                else "Camera did not find a reliable bright target."
            ),
            "pan_deg": round(pan, 3),
            "tilt_deg": round(tilt, 3),
            "sun_pan_deg": round(target_pan, 3),
            "sun_tilt_deg": round(target_tilt, 3),
            "track_error_deg": round(track_error, 3),
            "lr_error": round(x_error, 5),
            "tb_error": round(y_error, 5),
            "servo_enabled": servo_enabled,
            "pan_servo_enabled": pan_servo_enabled,
            "tilt_servo_enabled": tilt_servo_enabled,
            "servo_mode": servo_mode,
        },
        "vision": {
            "mode": detection.get("mode", "camera"),
            "camera_mount": args.camera_mount,
            "detected": detected,
            "confidence": round(float(detection.get("confidence", 0.0)), 4),
            "target_x_px": None if detection.get("target_x_px") is None else round(float(detection["target_x_px"]), 2),
            "target_y_px": None if detection.get("target_y_px") is None else round(float(detection["target_y_px"]), 2),
            "x_error": round(x_error, 5),
            "y_error": round(y_error, 5),
            "frame_w": int(detection.get("frame_w", args.width)),
            "frame_h": int(detection.get("frame_h", args.height)),
            "brightness_max": int(detection.get("brightness_max", 0)),
            "area_px": int(detection.get("area_px", 0)),
        },
    }


def write_log(writer, packet: dict[str, Any], udp_host: str, udp_port: int) -> None:
    tracker = packet.get("tracker", {})
    vision = packet.get("vision", {})
    writer.writerow(
        [
            packet.get("timestamp_utc", ""),
            packet.get("seq", ""),
            int(bool(vision.get("detected", False))),
            vision.get("confidence", ""),
            vision.get("target_x_px", ""),
            vision.get("target_y_px", ""),
            vision.get("x_error", ""),
            vision.get("y_error", ""),
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
            vision.get("mode", ""),
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
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("--width and --height must be positive")
    if args.control_gain < 0:
        raise SystemExit("--control-gain must be nonnegative")
    if args.max_pan_step <= 0 or args.max_tilt_step <= 0:
        raise SystemExit("--max-pan-step and --max-tilt-step must be positive")
    for value, name in ((args.pan_gain, "--pan-gain"), (args.tilt_gain, "--tilt-gain")):
        if value is not None and value < 0:
            raise SystemExit(f"{name} must be nonnegative")
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

    cv2 = None
    cap = None
    ina_bus = None
    ina_sensor = None
    pca_bus = None
    pca = None
    pan = clamp(args.pan_start, args.pan_min, args.pan_max)
    tilt = clamp(args.tilt_start, args.tilt_min, args.tilt_max)
    pan_gain = args.control_gain if args.pan_gain is None else args.pan_gain
    tilt_gain = args.control_gain if args.tilt_gain is None else args.tilt_gain

    try:
        if not args.synthetic:
            cv2, cap = open_camera(args)
            print(
                f"Camera opened: {args.camera} id={args.camera_id} "
                f"{args.width}x{args.height}@{args.framerate} mount={args.camera_mount}"
            )
        else:
            print(f"Synthetic camera target enabled: {args.width}x{args.height}")

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
            print("Servo output is OFF; camera detection only.")

        seq = 0
        while args.max_packets is None or seq < args.max_packets:
            if args.synthetic:
                detection = synthetic_detection(seq, args.width, args.height)
                frame = None
            else:
                ok, frame = cap.read()
                if not ok:
                    raise SystemExit("Camera read failed.")
                detection = detect_bright_target(cv2, frame, args)

            x_error, y_error = detection_to_errors(detection)
            if args.invert_x:
                x_error = -x_error
            if args.invert_y:
                y_error = -y_error

            target_pan = target_angle(
                pan,
                args.pan_start,
                x_error,
                args.camera_pan_fov_deg,
                args.pan_min,
                args.pan_max,
                args.disable_pan,
                args.camera_mount,
            )
            target_tilt = target_angle(
                tilt,
                args.tilt_start,
                y_error,
                args.camera_tilt_fov_deg,
                args.tilt_min,
                args.tilt_max,
                args.disable_tilt,
                args.camera_mount,
            )

            if detection.get("detected"):
                pan = controlled_angle(
                    pan,
                    target_pan,
                    x_error,
                    pan_gain,
                    args.max_pan_step,
                    args.pan_min,
                    args.pan_max,
                    args.disable_pan,
                    args.camera_mount,
                )
                tilt = controlled_angle(
                    tilt,
                    target_tilt,
                    y_error,
                    tilt_gain,
                    args.max_tilt_step,
                    args.tilt_min,
                    args.tilt_max,
                    args.disable_tilt,
                    args.camera_mount,
                )

            track_error = math.hypot(target_pan - pan, target_tilt - tilt)
            if args.ina_enable and ina_sensor is not None:
                snapshot = ina_sensor.read_snapshot()
                sensor_values = (
                    float(snapshot["bus_mv"]),
                    float(snapshot["current_ma"]),
                    float(snapshot["power_mw"]),
                )
            else:
                sensor_values = simulated_power(track_error)

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
                target_pan,
                target_tilt,
                x_error,
                y_error,
                detection,
                sensor_values,
                args.drive_servos,
            )
            payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
            sock.sendto(payload, (args.udp_host, args.udp_port))
            write_log(writer, packet, args.udp_host, args.udp_port)
            csv_file.flush()

            vision = packet["vision"]
            tracker = packet["tracker"]
            print(
                f"{packet['timestamp_utc']} udp->{args.udp_host}:{args.udp_port} "
                f"seq={seq:05d} det={int(vision['detected'])} conf={vision['confidence']:.2f} "
                f"x={vision['x_error']:+.2f} y={vision['y_error']:+.2f} "
                f"pan={tracker['pan_deg']:.1f} tilt={tracker['tilt_deg']:.1f} "
                f"err={tracker['track_error_deg']:.1f} state={tracker['state']} p={packet['p_mw']}mW"
            )

            if args.preview and frame is not None:
                cv2.circle(frame, (int(vision["target_x_px"] or 0), int(vision["target_y_px"] or 0)), 12, (0, 255, 0), 2)
                cv2.imshow("camera_light_tracker", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            seq += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        csv_file.close()
        sock.close()
        if cap is not None:
            cap.release()
        if cv2 is not None and args.preview:
            cv2.destroyAllWindows()
        if ina_bus is not None:
            ina_bus.close()
        if pca_bus is not None:
            pca_bus.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
