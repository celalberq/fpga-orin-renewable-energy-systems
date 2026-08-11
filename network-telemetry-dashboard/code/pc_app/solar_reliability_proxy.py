#!/usr/bin/env python3
"""UDP reliability proxy for solar/tracker telemetry packets.

Use this between the Orin sender and the dashboard to inject controlled packet
loss/corruption and to recompute sequence gaps for the dashboard.
"""

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


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inject UDP packet loss/corruption before the dashboard.")
    parser.add_argument("--bind-host", default="0.0.0.0", help="UDP host to receive Orin packets.")
    parser.add_argument("--bind-port", type=int, default=5012, help="UDP port to receive Orin packets.")
    parser.add_argument("--forward-host", default="127.0.0.1", help="Dashboard UDP host.")
    parser.add_argument("--forward-port", type=int, default=5011, help="Dashboard UDP port.")
    parser.add_argument("--drop-every", type=int, default=0, help="Drop every Nth packet. 0 disables.")
    parser.add_argument("--corrupt-every", type=int, default=0, help="Mark every Nth forwarded packet invalid. 0 disables.")
    parser.add_argument("--duplicate-every", type=int, default=0, help="Duplicate every Nth forwarded packet. 0 disables.")
    parser.add_argument("--inject-first", type=int, default=0, help="Apply drop/corrupt/duplicate rules only to the first N received packets. 0 applies forever.")
    parser.add_argument("--delay-ms", type=float, default=0.0, help="Delay each forwarded packet by this many ms.")
    parser.add_argument("--max-packets", type=int, help="Stop after this many received packets.")
    parser.add_argument("--log", type=Path, default=Path("network-telemetry-dashboard/data/solar_reliability_proxy_log.csv"))
    return parser.parse_args()


def should_apply(every: int, count: int, inject_first: int = 0) -> bool:
    if inject_first > 0 and count > inject_first:
        return False
    return every > 0 and count > 0 and count % every == 0


def open_log(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)
    if path.stat().st_size == 0:
        writer.writerow(
            [
                "timestamp_utc",
                "rx_count",
                "action",
                "sender",
                "seq",
                "seq_gap",
                "valid",
                "error",
                "forward_host",
                "forward_port",
                "raw_line",
            ]
        )
    return file_handle, writer


def packet_seq(packet: dict[str, Any]) -> int | None:
    seq = packet.get("seq")
    if isinstance(seq, bool):
        return None
    if isinstance(seq, int):
        return seq
    if isinstance(seq, str) and seq.isdigit():
        return int(seq)
    return None


def prepare_packet(
    packet: dict[str, Any],
    previous_forwarded_seq: int | None,
    corrupt: bool,
) -> tuple[dict[str, Any], int | None]:
    prepared = dict(packet)
    seq = packet_seq(prepared)

    if seq is None or previous_forwarded_seq is None:
        seq_gap = 0
    else:
        seq_gap = seq - previous_forwarded_seq - 1

    if seq_gap < 0:
        prepared["valid"] = False
        prepared["error"] = "proxy_detected_duplicate_or_backward_sequence"
    elif corrupt:
        prepared["valid"] = False
        prepared["error"] = "proxy_injected_corruption"

    prepared["seq_gap"] = seq_gap
    prepared["proxy"] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "seq_gap": seq_gap,
        "corrupt_injected": corrupt,
    }
    return prepared, seq


def write_log(
    writer,
    rx_count: int,
    action: str,
    sender: str,
    packet: dict[str, Any],
    forward_host: str,
    forward_port: int,
) -> None:
    writer.writerow(
        [
            datetime.now(timezone.utc).isoformat(),
            rx_count,
            action,
            sender,
            packet.get("seq", ""),
            packet.get("seq_gap", ""),
            int(bool(packet.get("valid", False))),
            packet.get("error", ""),
            forward_host,
            forward_port,
            packet.get("raw_line", ""),
        ]
    )


def send_packet(sock: socket.socket, packet: dict[str, Any], host: str, port: int, delay_ms: float) -> None:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
    sock.sendto(payload, (host, port))


def main() -> int:
    configure_stdout()
    args = parse_args()

    if args.drop_every < 0 or args.corrupt_every < 0 or args.duplicate_every < 0 or args.inject_first < 0:
        raise SystemExit("every-N and inject-first options must be >= 0")

    csv_file, writer = open_log(args.log)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    previous_forwarded_seq: int | None = None
    rx_count = 0

    try:
        rx_sock.bind((args.bind_host, args.bind_port))
        print(f"Reliability proxy listening on {args.bind_host}:{args.bind_port}")
        print(f"Forwarding to {args.forward_host}:{args.forward_port}")
        print(
            f"Rules: drop_every={args.drop_every} corrupt_every={args.corrupt_every} "
            f"duplicate_every={args.duplicate_every} inject_first={args.inject_first} delay_ms={args.delay_ms}"
        )
        print(f"Logging to {args.log}")

        while args.max_packets is None or rx_count < args.max_packets:
            payload, address = rx_sock.recvfrom(16384)
            rx_count += 1
            sender = f"{address[0]}:{address[1]}"

            try:
                packet = json.loads(payload.decode("utf-8"))
                if not isinstance(packet, dict):
                    raise ValueError("JSON payload is not an object")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                packet = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "valid": False,
                    "error": f"proxy_bad_json: {exc}",
                    "seq_gap": 0,
                    "raw_line": payload.hex(),
                }

            if should_apply(args.drop_every, rx_count, args.inject_first):
                dropped = dict(packet)
                dropped["seq_gap"] = ""
                write_log(writer, rx_count, "drop", sender, dropped, args.forward_host, args.forward_port)
                csv_file.flush()
                print(f"DROP rx={rx_count} from={sender} seq={packet.get('seq', '')}")
                continue

            corrupt = should_apply(args.corrupt_every, rx_count, args.inject_first)
            prepared, seq = prepare_packet(packet, previous_forwarded_seq, corrupt)
            send_packet(tx_sock, prepared, args.forward_host, args.forward_port, args.delay_ms)
            write_log(writer, rx_count, "forward_corrupt" if corrupt else "forward", sender, prepared, args.forward_host, args.forward_port)
            csv_file.flush()
            print(
                f"FWD rx={rx_count} seq={prepared.get('seq', '')} "
                f"gap={prepared.get('seq_gap', '')} valid={prepared.get('valid', '')} "
                f"to={args.forward_host}:{args.forward_port}"
            )

            if seq is not None:
                previous_forwarded_seq = seq

            if should_apply(args.duplicate_every, rx_count, args.inject_first):
                duplicate, _dup_seq = prepare_packet(prepared, previous_forwarded_seq, False)
                send_packet(tx_sock, duplicate, args.forward_host, args.forward_port, args.delay_ms)
                write_log(writer, rx_count, "duplicate", sender, duplicate, args.forward_host, args.forward_port)
                csv_file.flush()
                print(f"DUP rx={rx_count} seq={duplicate.get('seq', '')} valid={duplicate.get('valid', '')}")
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError as exc:
        print(f"Proxy socket error: {exc}")
        return 2
    finally:
        csv_file.close()
        rx_sock.close()
        tx_sock.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
