#!/usr/bin/env python3
"""Receive UDP JSON solar telemetry packets and log them for the network project."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
from pathlib import Path


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Receive network-telemetry-dashboard UDP solar telemetry JSON.")
    parser.add_argument("--bind-host", default="127.0.0.1", help="UDP bind host.")
    parser.add_argument("--bind-port", type=int, default=5005, help="UDP bind port.")
    parser.add_argument("--log", type=Path, default=Path("network-telemetry-dashboard/data/solar_udp_receiver_log.csv"))
    parser.add_argument("--max-packets", type=int, help="Stop after this many packets.")
    return parser.parse_args()


def open_log(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)
    if path.stat().st_size == 0:
        writer.writerow(
            [
                "timestamp_utc",
                "sender",
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
                "raw_line",
                "source_label",
            ]
        )
    return file_handle, writer


def write_packet(writer, packet: dict[str, object], sender: str) -> None:
    writer.writerow(
        [
            packet.get("timestamp_utc", ""),
            sender,
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
            packet.get("raw_line", ""),
            packet.get("source_label", ""),
        ]
    )


def main() -> int:
    configure_stdout()
    args = parse_args()
    csv_file, writer = open_log(args.log)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    count = 0

    try:
        sock.bind((args.bind_host, args.bind_port))
        print(f"Listening for UDP telemetry on {args.bind_host}:{args.bind_port}")
        print(f"Logging to {args.log}")

        while args.max_packets is None or count < args.max_packets:
            payload, address = sock.recvfrom(8192)
            sender = f"{address[0]}:{address[1]}"

            try:
                packet = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                packet = {
                    "timestamp_utc": "",
                    "valid": False,
                    "error": f"bad_json: {exc}",
                    "raw_line": payload.hex(),
                }

            write_packet(writer, packet, sender)
            csv_file.flush()

            status = "OK" if packet.get("valid") else f"BAD {packet.get('error', '')}"
            seq = packet.get("seq", "")
            power = packet.get("p_mw", "")
            print(f"{status} from={sender} seq={seq} p_mw={power}")
            count += 1
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError as exc:
        print(f"Could not receive UDP telemetry: {exc}")
        return 2
    finally:
        csv_file.close()
        sock.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
