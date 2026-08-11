#!/usr/bin/env python3
"""Drive one servo from the Orin through a PCA9685 I2C PWM board."""

from __future__ import annotations

import argparse
import sys
import time

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover - depends on target Linux image
    try:
        from smbus import SMBus  # type: ignore
    except ImportError:  # pragma: no cover
        SMBus = None  # type: ignore


MODE1 = 0x00
MODE2 = 0x01
PRESCALE = 0xFE
LED0_ON_L = 0x06

MODE1_RESTART = 0x80
MODE1_SLEEP = 0x10
MODE1_AI = 0x20
MODE2_OUTDRV = 0x04


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PCA9685 servo bring-up for Orin Nano Super.")
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number. Current Orin header test used bus 7.")
    parser.add_argument("--addr", type=lambda value: int(value, 0), default=0x40, help="PCA9685 I2C address, usually 0x40.")
    parser.add_argument("--channel", type=int, default=0, help="Servo channel, 0-15.")
    parser.add_argument("--freq-hz", type=float, default=50.0, help="Servo PWM frequency.")
    parser.add_argument("--min-pulse-us", type=float, default=600.0, help="Pulse width for 0 degrees.")
    parser.add_argument("--max-pulse-us", type=float, default=2400.0, help="Pulse width for 180 degrees.")
    parser.add_argument("--angle", type=float, default=90.0, help="Angle to set when not sweeping.")
    parser.add_argument("--sweep", action="store_true", help="Sweep between min/max angles.")
    parser.add_argument("--min-angle", type=float, default=30.0, help="Sweep minimum angle.")
    parser.add_argument("--max-angle", type=float, default=150.0, help="Sweep maximum angle.")
    parser.add_argument("--step", type=float, default=10.0, help="Sweep angle step.")
    parser.add_argument("--cycles", type=int, default=1, help="Sweep cycles.")
    parser.add_argument("--settle", type=float, default=0.35, help="Seconds to wait after each position.")
    parser.add_argument("--release", action="store_true", help="Turn PWM off after the command.")
    return parser.parse_args()


def require_smbus() -> None:
    if SMBus is None:
        raise SystemExit(
            "smbus2 or smbus is required.\n"
            "On Orin, install with:\n"
            "  sudo apt install -y python3-smbus i2c-tools\n"
            "or:\n"
            "  python3 -m pip install smbus2"
        )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class Pca9685:
    def __init__(self, bus: SMBus, address: int, freq_hz: float) -> None:
        self.bus = bus
        self.address = address
        self.freq_hz = freq_hz

    def write_u8(self, register: int, value: int) -> None:
        self.bus.write_byte_data(self.address, register, value & 0xFF)

    def read_u8(self, register: int) -> int:
        return self.bus.read_byte_data(self.address, register)

    def begin(self) -> None:
        self.write_u8(MODE1, MODE1_AI)
        self.write_u8(MODE2, MODE2_OUTDRV)
        self.set_pwm_frequency(self.freq_hz)

    def set_pwm_frequency(self, freq_hz: float) -> None:
        if freq_hz <= 0:
            raise ValueError("freq_hz must be positive")

        prescale_value = round(25_000_000.0 / (4096.0 * freq_hz) - 1.0)
        prescale_value = int(clamp(prescale_value, 3, 255))

        old_mode = self.read_u8(MODE1)
        sleep_mode = (old_mode & ~MODE1_RESTART) | MODE1_SLEEP
        self.write_u8(MODE1, sleep_mode)
        self.write_u8(PRESCALE, prescale_value)
        self.write_u8(MODE1, old_mode)
        time.sleep(0.005)
        self.write_u8(MODE1, old_mode | MODE1_RESTART | MODE1_AI)

    def set_pwm(self, channel: int, on_count: int, off_count: int) -> None:
        if channel < 0 or channel > 15:
            raise ValueError("channel must be 0-15")

        base = LED0_ON_L + 4 * channel
        values = [
            on_count & 0xFF,
            (on_count >> 8) & 0x0F,
            off_count & 0xFF,
            (off_count >> 8) & 0x0F,
        ]
        for offset, value in enumerate(values):
            self.write_u8(base + offset, value)

    def release(self, channel: int) -> None:
        self.set_pwm(channel, 0, 0)


def angle_to_pulse_us(angle: float, min_pulse_us: float, max_pulse_us: float) -> float:
    angle = clamp(angle, 0.0, 180.0)
    return min_pulse_us + (angle / 180.0) * (max_pulse_us - min_pulse_us)


def pulse_us_to_count(pulse_us: float, freq_hz: float) -> int:
    period_us = 1_000_000.0 / freq_hz
    return int(round(clamp(pulse_us, 0.0, period_us) * 4096.0 / period_us))


def set_servo_angle(
    pca: Pca9685,
    channel: int,
    angle: float,
    min_pulse_us: float,
    max_pulse_us: float,
    settle_s: float,
) -> None:
    pulse_us = angle_to_pulse_us(angle, min_pulse_us, max_pulse_us)
    off_count = pulse_us_to_count(pulse_us, pca.freq_hz)
    pca.set_pwm(channel, 0, off_count)
    print(f"channel={channel} angle={angle:.1f} pulse={pulse_us:.1f}us count={off_count}")
    time.sleep(max(0.0, settle_s))


def sweep_angles(min_angle: float, max_angle: float, step: float, cycles: int) -> list[float]:
    if step <= 0:
        raise ValueError("--step must be positive")

    min_angle = clamp(min_angle, 0.0, 180.0)
    max_angle = clamp(max_angle, 0.0, 180.0)
    if min_angle > max_angle:
        min_angle, max_angle = max_angle, min_angle

    upward = []
    angle = min_angle
    while angle <= max_angle + 1e-9:
        upward.append(round(angle, 3))
        angle += step

    downward = list(reversed(upward[1:-1]))
    pattern = upward + downward
    return pattern * max(1, cycles)


def main() -> int:
    configure_stdout()
    args = parse_args()
    require_smbus()

    if args.channel < 0 or args.channel > 15:
        raise SystemExit("--channel must be 0-15")
    if args.min_pulse_us <= 0 or args.max_pulse_us <= args.min_pulse_us:
        raise SystemExit("--max-pulse-us must be greater than --min-pulse-us")

    with SMBus(args.bus) as bus:
        pca = Pca9685(bus, args.addr, args.freq_hz)
        mode1_before = pca.read_u8(MODE1)
        pca.begin()
        mode1_after = pca.read_u8(MODE1)
        print(f"PCA9685 addr=0x{args.addr:02X} bus={args.bus} mode1_before=0x{mode1_before:02X} mode1_after=0x{mode1_after:02X}")

        if args.sweep:
            for angle in sweep_angles(args.min_angle, args.max_angle, args.step, args.cycles):
                set_servo_angle(
                    pca,
                    args.channel,
                    angle,
                    args.min_pulse_us,
                    args.max_pulse_us,
                    args.settle,
                )
        else:
            set_servo_angle(
                pca,
                args.channel,
                args.angle,
                args.min_pulse_us,
                args.max_pulse_us,
                args.settle,
            )

        if args.release:
            pca.release(args.channel)
            print(f"channel={args.channel} released")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
