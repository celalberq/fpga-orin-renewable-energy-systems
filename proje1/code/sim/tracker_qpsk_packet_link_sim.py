#!/usr/bin/env python3
"""QPSK packet-link simulation using the Orin tracker telemetry frame."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

from qpsk_packet_link_sim import (
    add_awgn,
    bits_to_bytes,
    bytes_to_bits,
    qpsk_demodulate,
    qpsk_modulate,
)
from tracker_packet_profile import make_tracker_frame, tracker_frame_ok


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "tracker_qpsk_packet_link_sim.csv"
CONSTELLATION_PATH = PROJECT_ROOT / "data" / "tracker_qpsk_packet_link_constellation.csv"

RANDOM_SEED = 43
FRAMES_PER_POINT = 350
EBN0_DB_POINTS = [0, 2, 4, 6, 8, 10, 12]


@dataclass
class LinkResult:
    ebn0_db: float
    frames: int
    bits: int
    bit_errors: int
    frame_errors: int
    crc_detected_errors: int
    undetected_errors: int

    @property
    def ber(self) -> float:
        return self.bit_errors / self.bits if self.bits else 0.0

    @property
    def fer(self) -> float:
        return self.frame_errors / self.frames if self.frames else 0.0


def simulate_point(ebn0_db: float, frames: int, rng: random.Random) -> LinkResult:
    total_bits = 0
    bit_errors = 0
    frame_errors = 0
    crc_detected_errors = 0
    undetected_errors = 0

    for seq in range(frames):
        tx_frame = make_tracker_frame(seq)
        tx_bits = bytes_to_bits(tx_frame)
        tx_symbols = qpsk_modulate(tx_bits)
        rx_symbols = add_awgn(tx_symbols, ebn0_db, rng)
        rx_bits = qpsk_demodulate(rx_symbols)[: len(tx_bits)]
        rx_frame = bits_to_bytes(rx_bits)

        errors_this_frame = sum(1 for tx_bit, rx_bit in zip(tx_bits, rx_bits) if tx_bit != rx_bit)
        valid_frame = tracker_frame_ok(rx_frame)

        total_bits += len(tx_bits)
        bit_errors += errors_this_frame

        if not valid_frame:
            frame_errors += 1
            if errors_this_frame:
                crc_detected_errors += 1
        elif errors_this_frame:
            undetected_errors += 1

    return LinkResult(
        ebn0_db=ebn0_db,
        frames=frames,
        bits=total_bits,
        bit_errors=bit_errors,
        frame_errors=frame_errors,
        crc_detected_errors=crc_detected_errors,
        undetected_errors=undetected_errors,
    )


def write_constellation_sample(rng: random.Random) -> None:
    frame = make_tracker_frame(23)
    tx_bits = bytes_to_bits(frame)
    tx_symbols = qpsk_modulate(tx_bits)
    rx_symbols = add_awgn(tx_symbols[:120], 6.0, rng)

    CONSTELLATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONSTELLATION_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol_index", "tx_i", "tx_q", "rx_i", "rx_q", "ebn0_db"])
        for index, ((tx_i, tx_q), (rx_i, rx_q)) in enumerate(zip(tx_symbols[:120], rx_symbols)):
            writer.writerow([index, tx_i, tx_q, f"{rx_i:.6f}", f"{rx_q:.6f}", 6.0])


def main() -> int:
    rng = random.Random(RANDOM_SEED)
    results = [simulate_point(ebn0_db, FRAMES_PER_POINT, rng) for ebn0_db in EBN0_DB_POINTS]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "ebn0_db",
                "frames",
                "bits",
                "bit_errors",
                "ber",
                "frame_errors",
                "fer",
                "crc_detected_errors",
                "undetected_errors",
                "frame_bytes",
                "qpsk_symbols",
            ]
        )
        for result in results:
            frame_bytes = len(make_tracker_frame(23))
            writer.writerow(
                [
                    result.ebn0_db,
                    result.frames,
                    result.bits,
                    result.bit_errors,
                    f"{result.ber:.8f}",
                    result.frame_errors,
                    f"{result.fer:.8f}",
                    result.crc_detected_errors,
                    result.undetected_errors,
                    frame_bytes,
                    frame_bytes * 4,
                ]
            )

    write_constellation_sample(rng)

    example_frame = make_tracker_frame(23)
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {CONSTELLATION_PATH}")
    print("ebn0_db frames ber fer frame_errors crc_detected undetected")
    for result in results:
        print(
            f"{result.ebn0_db:>5.1f} {result.frames} {result.ber:.8f} {result.fer:.8f} "
            f"{result.frame_errors} {result.crc_detected_errors} {result.undetected_errors}"
        )
    print(f"example_frame_bytes={len(example_frame)}")
    print(f"example_qpsk_symbols={len(qpsk_modulate(bytes_to_bits(example_frame)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
