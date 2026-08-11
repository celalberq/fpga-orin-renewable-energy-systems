#!/usr/bin/env python3
"""Send INA226 readings from Orin to the network-telemetry-dashboard UDP dashboard."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ina226_reader import (
    REG_CONFIG,
    REG_DIE_ID,
    REG_MANUFACTURER_ID,
    Ina226,
    SMBus,
)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read an INA226 on Orin I2C and forward readings as UDP JSON."
    )
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number. Current Orin header test used bus 7.")
    parser.add_argument("--addr", type=lambda value: int(value, 0), default=0x44, help="INA226 I2C address. Current module appeared at 0x44.")
    parser.add_argument("--shunt-ohms", type=float, default=0.1, help="On-module shunt resistor value. R100 means 0.1 ohm.")
    parser.add_argument(
        "--bus-voltage-scale",
        type=float,
        default=1.0,
        help="Optional calibration multiplier applied to the INA226 bus-voltage reading.",
    )
    parser.add_argument(
        "--mode",
        choices=("solar", "bess"),
        default="solar",
        help="Describe readings as solar-source telemetry or real battery/BESS telemetry.",
    )
    parser.add_argument(
        "--battery-capacity-ah",
        type=float,
        default=2.5,
        help="Battery capacity used for BESS metadata.",
    )
    parser.add_argument(
        "--battery-nominal-voltage",
        type=float,
        default=3.7,
        help="Battery nominal voltage used to derive BESS capacity in Wh.",
    )
    parser.add_argument(
        "--idle-current-ma",
        type=float,
        default=2.0,
        help="Absolute current below which BESS mode reports idle.",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between UDP packets.")
    parser.add_argument("--udp-host", default="127.0.0.1", help="UDP destination host.")
    parser.add_argument("--udp-port", type=int, default=5011, help="UDP destination port.")
    parser.add_argument("--source-label", help="Dashboard source label. Defaults according to --mode.")
    parser.add_argument("--max-packets", type=int, help="Stop after this many packets.")
    parser.add_argument("--id-only", action="store_true", help="Only read ID/config registers and exit.")
    parser.add_argument("--log", type=Path, default=Path("solar-tracker-bess/data/ina226_udp_gateway_log.csv"))
    return parser.parse_args()


def open_log(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)
    if path.stat().st_size == 0:
        writer.writerow(
            [
                "timestamp_utc",
                "seq",
                "bus_mv",
                "shunt_uv",
                "current_ma",
                "power_mw",
                "udp_host",
                "udp_port",
                "raw_line",
            ]
        )
    return file_handle, writer


def packet_from_snapshot(
    seq: int,
    snapshot: dict[str, float | int | str],
    source_label: str,
    mode: str = "solar",
    battery_capacity_ah: float = 2.5,
    battery_nominal_voltage: float = 3.7,
    idle_current_ma: float = 2.0,
) -> dict[str, Any]:
    bus_mv = float(snapshot["bus_mv"])
    shunt_uv = float(snapshot["shunt_uv"])
    current_ma = float(snapshot["current_ma"])
    power_mw = float(snapshot["power_mw"])
    timestamp = str(snapshot["timestamp_utc"])
    raw_prefix = "bess" if mode == "bess" else "ina226"
    raw_line = (
        f"{raw_prefix},seq={seq:05d},v_mv={bus_mv:.3f},i_ma={current_ma:.3f},"
        f"p_mw={power_mw:.3f},shunt_uv={shunt_uv:.3f}"
    )

    packet: dict[str, Any] = {
        "schema": "solar.telemetry.v1",
        "schema_variant": "orin.ina226.bess.v1" if mode == "bess" else "orin.ina226.v1",
        "source_project": "solar-tracker-bess",
        "network_project": "network-telemetry-dashboard",
        "source_label": source_label,
        "timestamp_utc": timestamp,
        "valid": True,
        "error": "",
        "seq_gap": 0,
        "seq": seq,
        "raw": "00",
        "d_pct": 0,
        "v_mv": round(bus_mv, 3),
        "i_ma": round(current_ma, 3),
        "p_mw": round(power_mw, 3),
        "mppt": "meas",
        "mppt_label": "Measured",
        "mppt_reason": "Real voltage/current/power measured by INA226 on Orin I2C.",
        "fault": 0,
        "fault_label": "OK",
        "fault_reason": "No protection flag active for this sensor-only test.",
        "fault_severity": "normal",
        "chk": "",
        "computed_chk": "",
        "raw_line": raw_line,
        "ina226": {
            "bus_mv": round(bus_mv, 3),
            "shunt_uv": round(shunt_uv, 3),
            "current_ma": round(current_ma, 3),
            "power_mw": round(power_mw, 3),
            "shunt_raw": snapshot["shunt_raw"],
            "bus_raw": snapshot["bus_raw"],
        },
    }

    if mode == "bess":
        if current_ma > idle_current_ma:
            bess_state = "charging"
            bess_reason = "Measured battery current is positive; the cell is charging."
        elif current_ma < -idle_current_ma:
            bess_state = "discharging"
            bess_reason = "Measured battery current is negative; the connected load is discharging the cell."
        else:
            bess_state = "idle"
            bess_reason = "Measured battery current is within the configured idle threshold."

        capacity_wh = battery_capacity_ah * battery_nominal_voltage
        packet.update(
            {
                "bess_measurement_mode": "real",
                "bess_state": bess_state,
                "bess_reason": bess_reason,
                "bess_power_w": round(power_mw / 1000.0, 6),
                "bess_load_w": round(max(0.0, -power_mw / 1000.0), 6),
                "bess_capacity_wh": round(capacity_wh, 3),
                "mppt": "bess",
                "mppt_label": "Battery",
                "mppt_reason": "Real battery voltage, signed current, and signed power measured by INA226.",
                "battery": {
                    "measurement_mode": "real",
                    "voltage_v": round(bus_mv / 1000.0, 6),
                    "current_a": round(current_ma / 1000.0, 6),
                    "power_w": round(power_mw / 1000.0, 6),
                    "capacity_ah": round(battery_capacity_ah, 3),
                    "nominal_voltage_v": round(battery_nominal_voltage, 3),
                    "capacity_wh": round(capacity_wh, 3),
                },
            }
        )

    return packet


def write_log(writer, packet: dict[str, Any], udp_host: str, udp_port: int) -> None:
    ina = packet.get("ina226", {})
    if not isinstance(ina, dict):
        ina = {}
    writer.writerow(
        [
            packet.get("timestamp_utc", ""),
            packet.get("seq", ""),
            ina.get("bus_mv", ""),
            ina.get("shunt_uv", ""),
            ina.get("current_ma", ""),
            ina.get("power_mw", ""),
            udp_host,
            udp_port,
            packet.get("raw_line", ""),
        ]
    )


def main() -> int:
    configure_stdout()
    args = parse_args()
    if args.shunt_ohms <= 0:
        raise SystemExit("--shunt-ohms must be positive")
    if args.bus_voltage_scale <= 0:
        raise SystemExit("--bus-voltage-scale must be positive")
    if args.battery_capacity_ah <= 0:
        raise SystemExit("--battery-capacity-ah must be positive")
    if args.battery_nominal_voltage <= 0:
        raise SystemExit("--battery-nominal-voltage must be positive")
    if args.idle_current_ma < 0:
        raise SystemExit("--idle-current-ma must not be negative")

    source_label = args.source_label or (
        "Orin real INA226 battery BESS" if args.mode == "bess" else "Orin INA226 real solar sensor"
    )

    csv_file, writer = open_log(args.log)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        with SMBus(args.bus) as bus:
            sensor = Ina226(
                bus,
                args.addr,
                args.shunt_ohms,
                args.bus_voltage_scale,
            )
            config = sensor.read_u16(REG_CONFIG)
            manufacturer_id = sensor.read_u16(REG_MANUFACTURER_ID)
            die_id = sensor.read_u16(REG_DIE_ID)
            print(f"INA226 addr=0x{args.addr:02X} bus={args.bus}")
            print(f"config=0x{config:04X} manufacturer_id=0x{manufacturer_id:04X} die_id=0x{die_id:04X}")

            if args.id_only:
                return 0

            print(f"Sending UDP to {args.udp_host}:{args.udp_port}")
            print(f"Logging to {args.log}")
            seq = 0
            while args.max_packets is None or seq < args.max_packets:
                snapshot = sensor.read_snapshot()
                packet = packet_from_snapshot(
                    seq,
                    snapshot,
                    source_label,
                    mode=args.mode,
                    battery_capacity_ah=args.battery_capacity_ah,
                    battery_nominal_voltage=args.battery_nominal_voltage,
                    idle_current_ma=args.idle_current_ma,
                )
                payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
                sock.sendto(payload, (args.udp_host, args.udp_port))
                write_log(writer, packet, args.udp_host, args.udp_port)
                csv_file.flush()

                print(
                    f"{packet['timestamp_utc']} udp->{args.udp_host}:{args.udp_port} "
                    f"seq={seq:05d} v={packet['v_mv']}mV "
                    f"i={packet['i_ma']}mA p={packet['p_mw']}mW"
                    + (f" state={packet['bess_state']}" if args.mode == "bess" else "")
                )
                seq += 1
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        csv_file.close()
        sock.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
