#!/usr/bin/env python3
"""Monitor the panel and four-KY-018 FPGA bring-up packet."""

from __future__ import annotations

import argparse
import re

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None


LINE_RE = re.compile(
    r"^ldr,seq=(\d{5}),pv=(\d{5}),tl=(\d{4}),tr=(\d{4}),bl=(\d{4}),br=(\d{4})$"
)


def parse_line(line: str) -> dict[str, int]:
    match = LINE_RE.fullmatch(line.strip())
    if match is None:
        raise ValueError("unexpected packet")
    names = ("seq", "pv", "tl", "tr", "bl", "br")
    values = {name: int(value) for name, value in zip(names, match.groups())}
    if values["pv"] > 18300:
        raise ValueError("panel voltage outside 0..18300 mV")
    if any(values[name] > 4095 for name in ("tl", "tr", "bl", "br")):
        raise ValueError("LDR count outside 0..4095")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--max-lines", type=int)
    args = parser.parse_args()

    if serial is None:
        raise SystemExit("pyserial is required: python -m pip install pyserial")

    received = 0
    with serial.Serial(args.port, args.baud, timeout=1.0) as device:
        print(f"Listening on {args.port} at {args.baud} baud. Press Ctrl+C to stop.")
        while args.max_lines is None or received < args.max_lines:
            raw = device.readline().decode("ascii", errors="replace").strip()
            if not raw:
                continue
            try:
                sample = parse_line(raw)
            except ValueError as exc:
                print(f"BAD {exc}: {raw}")
                continue

            left = sample["tl"] + sample["bl"]
            right = sample["tr"] + sample["br"]
            top = sample["tl"] + sample["tr"]
            bottom = sample["bl"] + sample["br"]
            print(
                f"seq={sample['seq']:05d} panel={sample['pv'] / 1000:.3f}V "
                f"TL={sample['tl']:4d} TR={sample['tr']:4d} "
                f"BL={sample['bl']:4d} BR={sample['br']:4d} "
                f"right-left={right-left:+5d} bottom-top={bottom-top:+5d}"
            )
            received += 1


if __name__ == "__main__":
    main()
