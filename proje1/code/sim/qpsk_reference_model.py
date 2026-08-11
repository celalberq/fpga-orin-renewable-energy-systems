#!/usr/bin/env python3
"""QPSK loopback reference model for the first digital communication step."""

from __future__ import annotations

import csv
import random
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "qpsk_loopback_symbols.csv"

QPSK_MAP = {
    (0, 0): (1, 1),
    (0, 1): (-1, 1),
    (1, 1): (-1, -1),
    (1, 0): (1, -1),
}


def demap_symbol(i_value: int, q_value: int) -> tuple[int, int]:
    if i_value >= 0 and q_value >= 0:
        return 0, 0
    if i_value < 0 and q_value >= 0:
        return 0, 1
    if i_value < 0 and q_value < 0:
        return 1, 1
    return 1, 0


def main() -> int:
    random.seed(7)
    bit_count = 128
    bits = [random.randint(0, 1) for _ in range(bit_count)]
    decoded_bits = []
    rows = []

    for symbol_index in range(0, bit_count, 2):
        pair = (bits[symbol_index], bits[symbol_index + 1])
        i_value, q_value = QPSK_MAP[pair]
        demapped = demap_symbol(i_value, q_value)
        decoded_bits.extend(demapped)
        rows.append([symbol_index // 2, pair[0], pair[1], i_value, q_value, demapped[0], demapped[1]])

    bit_errors = sum(1 for sent, received in zip(bits, decoded_bits) if sent != received)
    ber = bit_errors / bit_count

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol_index", "bit0", "bit1", "i", "q", "decoded_bit0", "decoded_bit1"])
        writer.writerows(rows)

    print(f"Wrote {OUT_PATH}")
    print(f"symbols={len(rows)} bits={bit_count} bit_errors={bit_errors} ber={ber:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
