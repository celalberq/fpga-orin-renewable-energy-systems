#!/usr/bin/env python3
"""Bridge proje3 solar UART packets to a UDP JSON telemetry stream."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

try:
    import serial
    from serial.tools import list_ports as serial_list_ports
except ImportError:  # pragma: no cover
    serial = None
    serial_list_ports = None


VALID_MPPT = {"hd": 0, "up": 1, "dn": 2}


def mppt_label(code: str) -> str:
    labels = {
        "up": "Power increased",
        "dn": "Power decreased",
        "hd": "Hold",
    }
    return labels.get(code, "Unknown")


def mppt_reason(code: str) -> str:
    reasons = {
        "up": "Last perturbation improved estimated power.",
        "dn": "Last perturbation reduced estimated power.",
        "hd": "Estimated power is steady at the current duty.",
    }
    return reasons.get(code, "MPPT state is not recognized.")


def fault_label_and_reason(fault: int, duty_raw: int, duty_pct: int, power_mw: int) -> tuple[str, str, str]:
    if not fault:
        return "OK", "No protection flag active.", "normal"

    if duty_raw >= 0xF0:
        return (
            "FAULT",
            "High duty demo protection active: raw duty is at or above 0xF0.",
            "critical",
        )

    return (
        "FAULT",
        "FPGA protection flag active. In the auto-MPPT build this can be the demo fault switch "
        f"or another protection source at duty={duty_pct}% and power={power_mw / 1000:.2f} W.",
        "critical",
    )


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
            "pyserial is required for live UART. Install it with: "
            "python -m pip install -r main_layout/tools/requirements.txt"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate proje3 solar telemetry and forward it as UDP JSON for proje2."
    )
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    parser.add_argument("--port", default="COM6", help="Serial port for Nexys Video J13.")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud rate.")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial timeout in seconds.")
    parser.add_argument("--line", help="Process one p3 packet line instead of opening serial.")
    parser.add_argument("--replay-file", type=Path, help="Replay p3 lines from a text or CSV log.")
    parser.add_argument("--udp-host", default="127.0.0.1", help="UDP destination host.")
    parser.add_argument("--udp-port", type=int, default=5005, help="UDP destination port.")
    parser.add_argument("--no-send", action="store_true", help="Validate/log packets without sending UDP.")
    parser.add_argument("--max-lines", type=int, help="Stop after this many valid input lines.")
    parser.add_argument("--log", type=Path, default=Path("proje2/data/solar_udp_gateway_log.csv"))
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


def result_to_json(result: PacketResult, timestamp_utc: str) -> dict[str, object]:
    fields = result.fields
    packet: dict[str, object] = {
        "schema": "solar.telemetry.v1",
        "source_project": "proje3",
        "network_project": "proje2",
        "timestamp_utc": timestamp_utc,
        "valid": result.valid,
        "error": result.error,
        "seq_gap": result.seq_gap,
        "raw_line": result.raw_line,
        "computed_chk": result.computed_chk,
    }

    if fields:
        seq = int(fields["seq"])
        duty_raw = int(fields["raw"], 16)
        duty_pct = int(fields["d_pct"])
        voltage_mv = int(fields["v_mv"])
        current_ma = int(fields["i_ma"])
        power_mw = int(fields["p_mw"])
        mppt = fields["mppt"]
        fault = int(fields["f"])
        fault_label, fault_reason, fault_severity = fault_label_and_reason(
            fault, duty_raw, duty_pct, power_mw
        )

        packet.update(
            {
                "seq": seq,
                "raw": fields["raw"].upper(),
                "d_pct": duty_pct,
                "v_mv": voltage_mv,
                "i_ma": current_ma,
                "p_mw": power_mw,
                "mppt": mppt,
                "mppt_label": mppt_label(mppt),
                "mppt_reason": mppt_reason(mppt),
                "fault": fault,
                "fault_label": fault_label,
                "fault_reason": fault_reason,
                "fault_severity": fault_severity,
                "chk": fields["chk"].upper(),
            }
        )

    return packet


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
                "seq",
                "d_pct",
                "v_mv",
                "i_ma",
                "p_mw",
                "mppt",
                "fault",
                "chk",
                "computed_chk",
                "udp_host",
                "udp_port",
                "raw_line",
            ]
        )
    return file_handle, writer


def write_log(writer, packet: dict[str, object], udp_host: str, udp_port: int) -> None:
    writer.writerow(
        [
            packet.get("timestamp_utc", ""),
            int(bool(packet.get("valid", False))),
            packet.get("error", ""),
            "" if packet.get("seq_gap") is None else packet.get("seq_gap"),
            packet.get("seq", ""),
            packet.get("d_pct", ""),
            packet.get("v_mv", ""),
            packet.get("i_ma", ""),
            packet.get("p_mw", ""),
            packet.get("mppt", ""),
            packet.get("fault", ""),
            packet.get("chk", ""),
            packet.get("computed_chk", ""),
            udp_host,
            udp_port,
            packet.get("raw_line", ""),
        ]
    )


def replay_lines(path: Path) -> Iterable[str]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_line = row.get("raw_line", "").strip()
                if raw_line:
                    yield raw_line
        return

    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def serial_lines(port: str, baud: int, timeout: float) -> Iterable[str]:
    require_pyserial()
    with serial.Serial(port, baud, timeout=timeout) as ser:
        print(f"Listening on {port} at {baud} baud.")
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                yield line


def input_lines(args: argparse.Namespace) -> Iterable[str]:
    if args.line:
        yield args.line.strip()
    elif args.replay_file:
        yield from replay_lines(args.replay_file)
    else:
        yield from serial_lines(args.port, args.baud, args.timeout)


def main() -> int:
    configure_stdout()
    args = parse_args()

    if args.list_ports:
        show_ports()
        return 0

    csv_file, writer = open_log(args.log)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    previous_seq: Optional[int] = None
    processed = 0

    try:
        for line in input_lines(args):
            result = parse_packet(line, previous_seq)
            timestamp = datetime.now(timezone.utc).isoformat()
            packet = result_to_json(result, timestamp)
            payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")

            if not args.no_send:
                sock.sendto(payload, (args.udp_host, args.udp_port))

            write_log(writer, packet, args.udp_host, args.udp_port)
            csv_file.flush()

            if "seq" in result.fields and result.fields["seq"].isdigit():
                previous_seq = int(result.fields["seq"])

            status = "OK" if result.valid else f"BAD {result.error}"
            action = "logged" if args.no_send else f"udp->{args.udp_host}:{args.udp_port}"
            print(f"{timestamp} {status} {action} {line}")
            processed += 1

            if args.max_lines is not None and processed >= args.max_lines:
                break
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError as exc:
        print(f"Network/serial error: {exc}")
        return 2
    finally:
        csv_file.close()
        sock.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
