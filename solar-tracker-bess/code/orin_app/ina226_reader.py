#!/usr/bin/env python3
"""Read INA226 voltage/current telemetry over I2C on Orin/PC Linux."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import time
from pathlib import Path

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover - depends on target Linux image
    try:
        from smbus import SMBus  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "smbus2 or smbus is required.\n"
            "On Orin, try:\n"
            "  sudo apt install -y i2c-tools python3-smbus\n"
            "or:\n"
            "  python3 -m pip install smbus2"
        ) from exc


REG_CONFIG = 0x00
REG_SHUNT_VOLTAGE = 0x01
REG_BUS_VOLTAGE = 0x02
REG_POWER = 0x03
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05
REG_MANUFACTURER_ID = 0xFE
REG_DIE_ID = 0xFF


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read INA226 telemetry over I2C.")
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number. Jetson Orin header pins 3/5 are often i2c-7 on JetPack 6.")
    parser.add_argument("--addr", type=lambda value: int(value, 0), default=0x40, help="INA226 I2C address, usually 0x40.")
    parser.add_argument("--shunt-ohms", type=float, default=0.1, help="On-module shunt resistor value. R100 means 0.1 ohm.")
    parser.add_argument(
        "--bus-voltage-scale",
        type=float,
        default=1.0,
        help="Optional calibration multiplier applied to the INA226 bus-voltage reading.",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between readings.")
    parser.add_argument("--count", type=int, default=0, help="Number of readings; 0 runs forever.")
    parser.add_argument("--log", type=Path, default=Path("solar-tracker-bess/data/ina226_orin_log.csv"))
    parser.add_argument("--id-only", action="store_true", help="Only read ID/config registers and exit.")
    return parser.parse_args()


def swap_word(raw: int) -> int:
    return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class Ina226:
    def __init__(
        self,
        bus: SMBus,
        address: int,
        shunt_ohms: float,
        bus_voltage_scale: float = 1.0,
    ) -> None:
        self.bus = bus
        self.address = address
        self.shunt_ohms = shunt_ohms
        self.bus_voltage_scale = bus_voltage_scale

    def read_u16(self, register: int) -> int:
        return swap_word(self.bus.read_word_data(self.address, register))

    def read_i16(self, register: int) -> int:
        return signed16(self.read_u16(register))

    def read_snapshot(self) -> dict[str, float | int | str]:
        shunt_raw = self.read_i16(REG_SHUNT_VOLTAGE)
        bus_raw = self.read_u16(REG_BUS_VOLTAGE)
        shunt_uv = shunt_raw * 2.5
        bus_mv = bus_raw * 1.25 * self.bus_voltage_scale
        current_ma = (shunt_uv / 1_000_000.0 / self.shunt_ohms) * 1000.0
        power_mw = (bus_mv / 1000.0) * current_ma
        return {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "bus_mv": round(bus_mv, 3),
            "shunt_uv": round(shunt_uv, 3),
            "current_ma": round(current_ma, 3),
            "power_mw": round(power_mw, 3),
            "shunt_raw": shunt_raw,
            "bus_raw": bus_raw,
        }


def main() -> int:
    args = parse_args()
    if args.shunt_ohms <= 0:
        raise SystemExit("--shunt-ohms must be positive")
    if args.bus_voltage_scale <= 0:
        raise SystemExit("--bus-voltage-scale must be positive")

    args.log.parent.mkdir(parents=True, exist_ok=True)

    with SMBus(args.bus) as bus:
        sensor = Ina226(bus, args.addr, args.shunt_ohms, args.bus_voltage_scale)

        config = sensor.read_u16(REG_CONFIG)
        manufacturer_id = sensor.read_u16(REG_MANUFACTURER_ID)
        die_id = sensor.read_u16(REG_DIE_ID)
        print(f"INA226 addr=0x{args.addr:02X} bus={args.bus}")
        print(f"config=0x{config:04X} manufacturer_id=0x{manufacturer_id:04X} die_id=0x{die_id:04X}")

        if args.id_only:
            return 0

        with args.log.open("a", newline="", encoding="utf-8") as log_file:
            fieldnames = [
                "timestamp_utc",
                "bus_mv",
                "shunt_uv",
                "current_ma",
                "power_mw",
                "shunt_raw",
                "bus_raw",
            ]
            writer = csv.DictWriter(log_file, fieldnames=fieldnames)
            if log_file.tell() == 0:
                writer.writeheader()

            reads = 0
            while args.count == 0 or reads < args.count:
                packet = sensor.read_snapshot()
                writer.writerow(packet)
                log_file.flush()
                print(
                    f"{packet['timestamp_utc']} "
                    f"bus={packet['bus_mv']}mV "
                    f"shunt={packet['shunt_uv']}uV "
                    f"current={packet['current_ma']}mA "
                    f"power={packet['power_mw']}mW"
                )
                reads += 1
                time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
