#!/usr/bin/env python3
"""QPSK packet-link simulation using the shared proje3 telemetry frame."""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path

from shared_packet_comm_sim import check_frame, frame_payload, make_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "qpsk_packet_link_sim.csv"
CONSTELLATION_PATH = PROJECT_ROOT / "data" / "qpsk_packet_link_constellation.csv"

RANDOM_SEED = 21
FRAMES_PER_POINT = 500
EBN0_DB_POINTS = [0, 2, 4, 6, 8, 10, 12]

QPSK_MAP = {
    (0, 0): (1.0, 1.0),
    (0, 1): (-1.0, 1.0),
    (1, 1): (-1.0, -1.0),
    (1, 0): (1.0, -1.0),
}


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


def bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for byte in data:
        for bit_index in range(7, -1, -1):
            bits.append((byte >> bit_index) & 1)
    return bits


def bits_to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8 != 0:
        raise ValueError("bit list length must be a multiple of 8")

    output = bytearray()
    for offset in range(0, len(bits), 8):
        byte = 0
        for bit in bits[offset : offset + 8]:
            byte = (byte << 1) | (bit & 1)
        output.append(byte)
    return bytes(output)


def qpsk_modulate(bits: list[int]) -> list[tuple[float, float]]:
    if len(bits) % 2 != 0:
        bits = bits + [0]

    symbols: list[tuple[float, float]] = []
    for offset in range(0, len(bits), 2):
        symbols.append(QPSK_MAP[(bits[offset], bits[offset + 1])])
    return symbols


def qpsk_demodulate(symbols: list[tuple[float, float]]) -> list[int]:
    bits: list[int] = []
    for i_value, q_value in symbols:
        if i_value >= 0.0 and q_value >= 0.0:
            bits.extend([0, 0])
        elif i_value < 0.0 and q_value >= 0.0:
            bits.extend([0, 1])
        elif i_value < 0.0 and q_value < 0.0:
            bits.extend([1, 1])
        else:
            bits.extend([1, 0])
    return bits


def add_awgn(
    symbols: list[tuple[float, float]],
    ebn0_db: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    ebn0_linear = 10.0 ** (ebn0_db / 10.0)
    noise_sigma = math.sqrt(1.0 / (2.0 * ebn0_linear))

    return [
        (i_value + rng.gauss(0.0, noise_sigma), q_value + rng.gauss(0.0, noise_sigma))
        for i_value, q_value in symbols
    ]


def make_frame(frame_index: int) -> bytes:
    duty_raw = (frame_index * 37) % 256
    previous_duty = ((frame_index - 1) * 37) % 256 if frame_index else 0
    payload = make_payload(seq=frame_index + 1, duty_raw=duty_raw, previous_duty=previous_duty)
    return frame_payload(payload)


def simulate_point(ebn0_db: float, frames: int, rng: random.Random) -> LinkResult:
    total_bits = 0
    bit_errors = 0
    frame_errors = 0
    crc_detected_errors = 0
    undetected_errors = 0

    for frame_index in range(frames):
        tx_frame = make_frame(frame_index)
        tx_bits = bytes_to_bits(tx_frame)
        tx_symbols = qpsk_modulate(tx_bits)
        rx_symbols = add_awgn(tx_symbols, ebn0_db, rng)
        rx_bits = qpsk_demodulate(rx_symbols)[: len(tx_bits)]
        rx_frame = bits_to_bytes(rx_bits)

        errors_this_frame = sum(1 for tx_bit, rx_bit in zip(tx_bits, rx_bits) if tx_bit != rx_bit)
        valid_frame = check_frame(rx_frame)

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
    frame = make_frame(0)
    tx_bits = bytes_to_bits(frame)
    tx_symbols = qpsk_modulate(tx_bits)
    rx_symbols = add_awgn(tx_symbols[:80], 6.0, rng)

    CONSTELLATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONSTELLATION_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol_index", "tx_i", "tx_q", "rx_i", "rx_q", "ebn0_db"])
        for index, ((tx_i, tx_q), (rx_i, rx_q)) in enumerate(zip(tx_symbols[:80], rx_symbols)):
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
            ]
        )
        for result in results:
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
                ]
            )

    write_constellation_sample(rng)

    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {CONSTELLATION_PATH}")
    print("ebn0_db frames ber fer frame_errors crc_detected undetected")
    for result in results:
        print(
            f"{result.ebn0_db:>5.1f} {result.frames} {result.ber:.8f} {result.fer:.8f} "
            f"{result.frame_errors} {result.crc_detected_errors} {result.undetected_errors}"
        )

    example_frame = make_frame(0)
    print(f"example_frame_bytes={len(example_frame)}")
    print(f"example_qpsk_symbols={len(qpsk_modulate(bytes_to_bits(example_frame)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
