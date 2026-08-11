#!/usr/bin/env python3
"""Stored-frame parser reference model for the first network project step."""

from __future__ import annotations

import csv
import socket
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "network_parser_metadata.csv"

SAMPLE_FRAME_HEX = """
02 11 22 33 44 55
02 aa bb cc dd ee
08 00
45 00 00 20 00 01 00 00 40 11 00 00 c0 a8 01 0a c0 a8 01 14
04 d2 16 2e 00 0c 00 00
de ad be ef
"""


def mac_addr(raw: bytes) -> str:
    return ":".join(f"{byte:02x}" for byte in raw)


def ipv4_addr(raw: bytes) -> str:
    return socket.inet_ntoa(raw)


def parse_frame(frame: bytes) -> dict[str, object]:
    ethertype = int.from_bytes(frame[12:14], "big")
    metadata: dict[str, object] = {
        "packet_length": len(frame),
        "destination_mac": mac_addr(frame[0:6]),
        "source_mac": mac_addr(frame[6:12]),
        "ethertype": f"0x{ethertype:04x}",
    }

    if ethertype != 0x0800:
        metadata["alert_flag"] = "unsupported_ethertype"
        return metadata

    ip_start = 14
    version_ihl = frame[ip_start]
    ihl_bytes = (version_ihl & 0x0F) * 4
    protocol = frame[ip_start + 9]
    total_length = int.from_bytes(frame[ip_start + 2 : ip_start + 4], "big")

    metadata.update(
        {
            "ip_version": version_ihl >> 4,
            "ip_header_bytes": ihl_bytes,
            "ip_total_length": total_length,
            "ip_protocol": protocol,
            "source_ip": ipv4_addr(frame[ip_start + 12 : ip_start + 16]),
            "destination_ip": ipv4_addr(frame[ip_start + 16 : ip_start + 20]),
        }
    )

    if protocol in (6, 17):
        l4_start = ip_start + ihl_bytes
        metadata["source_port"] = int.from_bytes(frame[l4_start : l4_start + 2], "big")
        metadata["destination_port"] = int.from_bytes(frame[l4_start + 2 : l4_start + 4], "big")
    else:
        metadata["source_port"] = ""
        metadata["destination_port"] = ""

    metadata["alert_flag"] = "none"
    return metadata


def main() -> int:
    frame = bytes.fromhex(SAMPLE_FRAME_HEX)
    metadata = parse_frame(frame)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(metadata.keys()))
        writer.writeheader()
        writer.writerow(metadata)

    print(f"Wrote {OUT_PATH}")
    for key, value in metadata.items():
        print(f"{key}={value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
