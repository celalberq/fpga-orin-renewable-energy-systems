#!/usr/bin/env python3
"""Drive two pan/tilt servos through a PCA9685 from the Orin."""

from __future__ import annotations

import argparse
import sys
import time

from pca9685_servo_test import (
    MODE1,
    Pca9685,
    SMBus,
    configure_stdout,
    require_smbus,
    set_servo_angle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Two-servo pan/tilt bring-up for the solar tracker.")
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number.")
    parser.add_argument("--addr", type=lambda value: int(value, 0), default=0x40, help="PCA9685 I2C address.")
    parser.add_argument("--pan-channel", type=int, default=0, help="Pan servo channel.")
    parser.add_argument("--tilt-channel", type=int, default=1, help="Tilt servo channel.")
    parser.add_argument("--pan-center", type=float, default=90.0, help="Pan center angle.")
    parser.add_argument("--tilt-center", type=float, default=90.0, help="Tilt center angle.")
    parser.add_argument("--pan-min", type=float, default=60.0, help="Safe pan sweep minimum.")
    parser.add_argument("--pan-max", type=float, default=120.0, help="Safe pan sweep maximum.")
    parser.add_argument("--tilt-min", type=float, default=70.0, help="Safe tilt sweep minimum.")
    parser.add_argument("--tilt-max", type=float, default=110.0, help="Safe tilt sweep maximum.")
    parser.add_argument("--step", type=float, default=10.0, help="Sweep step in degrees.")
    parser.add_argument("--settle", type=float, default=0.35, help="Seconds to wait after each position.")
    parser.add_argument("--min-pulse-us", type=float, default=600.0, help="Pulse width for 0 degrees.")
    parser.add_argument("--max-pulse-us", type=float, default=2400.0, help="Pulse width for 180 degrees.")
    parser.add_argument(
        "--mode",
        choices=["center", "pan", "tilt", "box"],
        default="center",
        help="Motion pattern to run.",
    )
    parser.add_argument("--release", action="store_true", help="Turn PWM off after the command.")
    return parser.parse_args()


def angle_range(start: float, stop: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("--step must be positive")
    if start > stop:
        start, stop = stop, start

    values: list[float] = []
    angle = start
    while angle <= stop + 1e-9:
        values.append(round(angle, 3))
        angle += step
    return values


def command_position(
    pca: Pca9685,
    pan_channel: int,
    tilt_channel: int,
    pan_angle: float,
    tilt_angle: float,
    min_pulse_us: float,
    max_pulse_us: float,
    settle_s: float,
) -> None:
    print(f"target pan={pan_angle:.1f} tilt={tilt_angle:.1f}")
    set_servo_angle(pca, pan_channel, pan_angle, min_pulse_us, max_pulse_us, 0.0)
    set_servo_angle(pca, tilt_channel, tilt_angle, min_pulse_us, max_pulse_us, settle_s)


def main() -> int:
    configure_stdout()
    args = parse_args()
    require_smbus()

    if args.pan_channel == args.tilt_channel:
        raise SystemExit("pan and tilt channels must be different")
    for channel in (args.pan_channel, args.tilt_channel):
        if channel < 0 or channel > 15:
            raise SystemExit("servo channels must be 0-15")

    with SMBus(args.bus) as bus:
        pca = Pca9685(bus, args.addr, 50.0)
        mode1_before = pca.read_u8(MODE1)
        pca.begin()
        mode1_after = pca.read_u8(MODE1)
        print(f"PCA9685 addr=0x{args.addr:02X} bus={args.bus} mode1_before=0x{mode1_before:02X} mode1_after=0x{mode1_after:02X}")

        command_position(
            pca,
            args.pan_channel,
            args.tilt_channel,
            args.pan_center,
            args.tilt_center,
            args.min_pulse_us,
            args.max_pulse_us,
            args.settle,
        )

        if args.mode == "pan":
            for pan in angle_range(args.pan_min, args.pan_max, args.step):
                command_position(
                    pca,
                    args.pan_channel,
                    args.tilt_channel,
                    pan,
                    args.tilt_center,
                    args.min_pulse_us,
                    args.max_pulse_us,
                    args.settle,
                )
        elif args.mode == "tilt":
            for tilt in angle_range(args.tilt_min, args.tilt_max, args.step):
                command_position(
                    pca,
                    args.pan_channel,
                    args.tilt_channel,
                    args.pan_center,
                    tilt,
                    args.min_pulse_us,
                    args.max_pulse_us,
                    args.settle,
                )
        elif args.mode == "box":
            corners = [
                (args.pan_min, args.tilt_min),
                (args.pan_max, args.tilt_min),
                (args.pan_max, args.tilt_max),
                (args.pan_min, args.tilt_max),
                (args.pan_center, args.tilt_center),
            ]
            for pan, tilt in corners:
                command_position(
                    pca,
                    args.pan_channel,
                    args.tilt_channel,
                    pan,
                    tilt,
                    args.min_pulse_us,
                    args.max_pulse_us,
                    args.settle,
                )

        if args.release:
            pca.release(args.pan_channel)
            pca.release(args.tilt_channel)
            print(f"channels {args.pan_channel},{args.tilt_channel} released")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
