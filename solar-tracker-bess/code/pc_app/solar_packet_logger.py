#!/usr/bin/env python3
"""Parse and log solar-tracker-bess shared telemetry packet v1 from UART."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import serial
    from serial.tools import list_ports as serial_list_ports
except ImportError:  # pragma: no cover
    serial = None
    serial_list_ports = None


VALID_MPPT = {"up": 1, "dn": 2, "hd": 0}


@dataclass
class PacketResult:
    raw_line: str
    valid: bool
    error: str
    fields: dict[str, str]
    computed_chk: Optional[str]
    seq_gap: Optional[int]


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def require_pyserial() -> None:
    if serial is None or serial_list_ports is None:
        raise SystemExit(
            "pyserial is required. Install it with: python -m pip install -r system-integration/tools/requirements.txt"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse solar-tracker-bess shared packet v1 telemetry from UART.")
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    parser.add_argument("--port", default="COM6", help="Serial port, usually COM6 for Nexys Video J13.")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud rate.")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds.")
    parser.add_argument("--log", type=Path, default=Path("solar-tracker-bess/data/solar_packet_v1_log.csv"))
    parser.add_argument("--max-lines", type=int, help="Stop after this many received lines.")
    return parser.parse_args()


def show_ports() -> None:
    require_pyserial()
    ports = list(serial_list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return

    for port in ports:
        print(f"{port.device}: {port.description}")


def parse_fields(line: str) -> dict[str, str]:
    parts = line.strip().split(",")
    fields: dict[str, str] = {}

    if not parts or parts[0] != "p3":
        raise ValueError("missing p3 prefix")

    fields["project"] = parts[0]
    for part in parts[1:]:
        if "=" not in part:
            raise ValueError(f"bad field: {part}")
        key, value = part.split("=", 1)
        fields[key] = value

    return fields


def require_int(fields: dict[str, str], key: str, min_value: int, max_value: int) -> int:
    if key not in fields:
        raise ValueError(f"missing {key}")

    text = fields[key]
    if not text.isdigit():
        raise ValueError(f"{key} is not decimal: {text}")

    value = int(text)
    if value < min_value or value > max_value:
        raise ValueError(f"{key} out of range: {value}")

    return value


def require_hex_byte(fields: dict[str, str], key: str) -> int:
    if key not in fields:
        raise ValueError(f"missing {key}")

    text = fields[key].upper()
    if len(text) != 2 or any(ch not in "0123456789ABCDEF" for ch in text):
        raise ValueError(f"{key} is not a hex byte: {fields[key]}")

    return int(text, 16)


def compute_checksum(
    seq: int,
    duty_raw: int,
    duty_pct: int,
    voltage_mv: int,
    current_ma: int,
    power_mw: int,
    mppt: str,
    fault: int,
) -> str:
    chk = 0
    chk ^= duty_raw & 0xFF
    for value in (seq, duty_pct, voltage_mv, current_ma, power_mw):
        chk ^= value & 0xFF
        chk ^= (value >> 8) & 0xFF
    chk ^= VALID_MPPT[mppt] & 0x03
    chk ^= fault & 0x01
    return f"{chk:02X}"


def parse_packet(line: str, previous_seq: Optional[int]) -> PacketResult:
    try:
        fields = parse_fields(line)

        seq = require_int(fields, "seq", 0, 99999)
        duty_raw = require_hex_byte(fields, "raw")
        duty_pct = require_int(fields, "d_pct", 0, 100)
        voltage_mv = require_int(fields, "v_mv", 0, 99999)
        current_ma = require_int(fields, "i_ma", 0, 99999)
        power_mw = require_int(fields, "p_mw", 0, 99999)
        fault = require_int(fields, "f", 0, 1)

        mppt = fields.get("mppt")
        if mppt not in VALID_MPPT:
            raise ValueError(f"bad mppt: {mppt}")

        received_chk = fields.get("chk", "").upper()
        if len(received_chk) != 2 or any(ch not in "0123456789ABCDEF" for ch in received_chk):
            raise ValueError(f"bad chk: {received_chk}")

        computed_chk = compute_checksum(seq, duty_raw, duty_pct, voltage_mv, current_ma, power_mw, mppt, fault)
        checksum_ok = received_chk == computed_chk

        seq_gap = None
        if previous_seq is not None:
            seq_gap = seq - previous_seq - 1

        valid = checksum_ok and (seq_gap is None or seq_gap >= 0)
        error = ""
        if not checksum_ok:
            error = f"checksum mismatch expected {computed_chk}"
        elif seq_gap is not None and seq_gap < 0:
            error = "sequence went backward or wrapped"

        return PacketResult(line, valid, error, fields, computed_chk, seq_gap)
    except ValueError as exc:
        return PacketResult(line, False, str(exc), {}, None, None)


def open_log(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)

    if path.stat().st_size == 0:
        writer.writerow(
            [
                "timestamp_utc",
                "valid",
                "error",
                "seq_gap",
                "project",
                "seq",
                "raw",
                "d_pct",
                "v_mv",
                "i_ma",
                "p_mw",
                "mppt",
                "f",
                "chk",
                "computed_chk",
                "raw_line",
            ]
        )

    return file_handle, writer


def write_result(writer, timestamp: str, result: PacketResult) -> None:
    fields = result.fields
    writer.writerow(
        [
            timestamp,
            int(result.valid),
            result.error,
            "" if result.seq_gap is None else result.seq_gap,
            fields.get("project", ""),
            fields.get("seq", ""),
            fields.get("raw", ""),
            fields.get("d_pct", ""),
            fields.get("v_mv", ""),
            fields.get("i_ma", ""),
            fields.get("p_mw", ""),
            fields.get("mppt", ""),
            fields.get("f", ""),
            fields.get("chk", ""),
            result.computed_chk or "",
            result.raw_line,
        ]
    )


def main() -> int:
    configure_stdout()
    args = parse_args()

    if args.list_ports:
        show_ports()
        return 0

    require_pyserial()
    csv_file, writer = open_log(args.log)
    previous_seq: Optional[int] = None
    line_count = 0

    try:
        with serial.Serial(args.port, args.baud, timeout=args.timeout) as ser:
            print(f"Listening on {args.port} at {args.baud} baud.")
            print(f"Logging to {args.log}")

            while args.max_lines is None or line_count < args.max_lines:
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                result = parse_packet(line, previous_seq)
                timestamp = datetime.now(timezone.utc).isoformat()
                write_result(writer, timestamp, result)
                csv_file.flush()

                if "seq" in result.fields and result.fields["seq"].isdigit():
                    previous_seq = int(result.fields["seq"])

                status = "OK" if result.valid else f"BAD {result.error}"
                gap = "" if result.seq_gap in (None, 0) else f" gap={result.seq_gap}"
                print(f"{timestamp} {status}{gap} {line}")
                line_count += 1
    except KeyboardInterrupt:
        print("\nStopped.")
    except serial.SerialException as exc:
        print(f"Could not open {args.port}: {exc}")
        print("Run with --list-ports to confirm the current COM port.")
        return 2
    finally:
        csv_file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
