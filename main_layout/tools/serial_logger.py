#!/usr/bin/env python3
"""Shared UART logger for Nexys Video bring-up and later project telemetry."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import serial
    from serial.tools import list_ports as serial_list_ports
except ImportError:  # pragma: no cover - useful message on a fresh PC
    serial = None
    serial_list_ports = None


def require_pyserial() -> None:
    if serial is None or serial_list_ports is None:
        raise SystemExit(
            "pyserial is required. Install it with: python -m pip install -r main_layout/tools/requirements.txt"
        )


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log UART text lines to the console and optional CSV.")
    parser.add_argument("--list-ports", action="store_true", help="List available serial ports and exit.")
    parser.add_argument("--port", help="Serial port, for example COM3 on Windows.")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud rate.")
    parser.add_argument("--timeout", type=float, default=1.0, help="Read timeout in seconds.")
    parser.add_argument("--encoding", default="utf-8", help="Text encoding for received bytes.")
    parser.add_argument("--log", type=Path, help="Optional CSV log output path.")
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


def open_csv(path: Optional[Path]):
    if path is None:
        return None, None

    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)

    if path.stat().st_size == 0:
        writer.writerow(["timestamp_utc", "port", "baud", "line"])

    return file_handle, writer


def main() -> int:
    configure_stdout()
    args = parse_args()

    if args.list_ports:
        show_ports()
        return 0

    if not args.port:
        raise SystemExit("Use --port COMx, or run --list-ports first.")

    require_pyserial()

    csv_file, writer = open_csv(args.log)
    line_count = 0

    try:
        with serial.Serial(args.port, args.baud, timeout=args.timeout) as ser:
            print(f"Listening on {args.port} at {args.baud} baud. Press Ctrl+C to stop.")

            while args.max_lines is None or line_count < args.max_lines:
                raw = ser.readline()
                if not raw:
                    continue

                text = raw.decode(args.encoding, errors="replace").rstrip("\r\n")
                timestamp = datetime.now(timezone.utc).isoformat()
                print(f"{timestamp} {text}")

                if writer is not None:
                    writer.writerow([timestamp, args.port, args.baud, text])
                    csv_file.flush()

                line_count += 1
    except KeyboardInterrupt:
        print("\nStopped.")
    except serial.SerialException as exc:
        print(f"Could not open {args.port}: {exc}")
        print("Run this to see the current port name:")
        print("  python main_layout/tools/serial_logger.py --list-ports")
        return 2
    finally:
        if csv_file is not None:
            csv_file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
