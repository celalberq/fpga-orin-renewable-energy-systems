#!/usr/bin/env python3
"""OFDM packet-link simulation using the shared solar-tracker-bess telemetry frame."""

from __future__ import annotations

import cmath
import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path

from qpsk_packet_link_sim import bits_to_bytes, bytes_to_bits, make_frame
from shared_packet_comm_sim import check_frame


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "ofdm_packet_link_sim.csv"
GRID_PATH = PROJECT_ROOT / "data" / "ofdm_resource_grid_example.csv"

RANDOM_SEED = 34
FRAMES_PER_POINT = 120
EBN0_DB_POINTS = [0, 2, 4, 6, 8, 10, 12, 14]

FFT_SIZE = 64
CP_LEN = 16
PILOT_CARRIERS = [-21, -7, 7, 21]
ACTIVE_CARRIERS = list(range(-26, 0)) + list(range(1, 27))
DATA_CARRIERS = [carrier for carrier in ACTIVE_CARRIERS if carrier not in PILOT_CARRIERS]

FRAME_BYTES = 87
FRAME_BITS = FRAME_BYTES * 8
QPSK_BITS_PER_SYMBOL = 2
DATA_QPSK_PER_OFDM = len(DATA_CARRIERS)
OFDM_SYMBOLS_PER_PACKET = math.ceil((FRAME_BITS / QPSK_BITS_PER_SYMBOL) / DATA_QPSK_PER_OFDM)
QPSK_SYMBOL_CAPACITY = OFDM_SYMBOLS_PER_PACKET * DATA_QPSK_PER_OFDM
PAD_QPSK_SYMBOLS = QPSK_SYMBOL_CAPACITY - (FRAME_BITS // QPSK_BITS_PER_SYMBOL)
PAD_BITS = PAD_QPSK_SYMBOLS * QPSK_BITS_PER_SYMBOL

IFFT_TWIDDLES = [
    [cmath.exp(2j * math.pi * k * n / FFT_SIZE) / FFT_SIZE for k in range(FFT_SIZE)]
    for n in range(FFT_SIZE)
]
FFT_TWIDDLES = [
    [cmath.exp(-2j * math.pi * k * n / FFT_SIZE) for n in range(FFT_SIZE)]
    for k in range(FFT_SIZE)
]


@dataclass
class OfdmResult:
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


def signed_to_bin(carrier: int) -> int:
    return carrier % FFT_SIZE


def qpsk_map_pair(bit0: int, bit1: int) -> complex:
    if bit0 == 0 and bit1 == 0:
        return complex(1.0, 1.0)
    if bit0 == 0 and bit1 == 1:
        return complex(-1.0, 1.0)
    if bit0 == 1 and bit1 == 1:
        return complex(-1.0, -1.0)
    return complex(1.0, -1.0)


def qpsk_demap_symbol(symbol: complex) -> list[int]:
    if symbol.real >= 0.0 and symbol.imag >= 0.0:
        return [0, 0]
    if symbol.real < 0.0 and symbol.imag >= 0.0:
        return [0, 1]
    if symbol.real < 0.0 and symbol.imag < 0.0:
        return [1, 1]
    return [1, 0]


def bits_to_qpsk(bits: list[int]) -> list[complex]:
    if len(bits) % 2 != 0:
        bits = bits + [0]

    return [qpsk_map_pair(bits[index], bits[index + 1]) for index in range(0, len(bits), 2)]


def ifft64(freq_bins: list[complex]) -> list[complex]:
    return [sum(freq_bins[k] * IFFT_TWIDDLES[n][k] for k in range(FFT_SIZE)) for n in range(FFT_SIZE)]


def fft64(time_samples: list[complex]) -> list[complex]:
    return [sum(time_samples[n] * FFT_TWIDDLES[k][n] for n in range(FFT_SIZE)) for k in range(FFT_SIZE)]


def build_ofdm_symbols(frame: bytes) -> list[list[complex]]:
    qpsk_symbols = bits_to_qpsk(bytes_to_bits(frame))
    qpsk_symbols.extend([complex(1.0, 1.0)] * PAD_QPSK_SYMBOLS)

    ofdm_grids: list[list[complex]] = []
    cursor = 0

    for symbol_index in range(OFDM_SYMBOLS_PER_PACKET):
        grid = [0j] * FFT_SIZE

        for pilot_index, carrier in enumerate(PILOT_CARRIERS):
            pilot_value = 1.0 if (symbol_index + pilot_index) % 2 == 0 else -1.0
            grid[signed_to_bin(carrier)] = complex(pilot_value, 0.0)

        for carrier in DATA_CARRIERS:
            grid[signed_to_bin(carrier)] = qpsk_symbols[cursor]
            cursor += 1

        ofdm_grids.append(grid)

    return ofdm_grids


def transmit_ofdm(frame: bytes) -> list[complex]:
    samples: list[complex] = []

    for grid in build_ofdm_symbols(frame):
        time_symbol = ifft64(grid)
        samples.extend(time_symbol[-CP_LEN:])
        samples.extend(time_symbol)

    return samples


def add_awgn(samples: list[complex], ebn0_db: float, rng: random.Random) -> list[complex]:
    avg_power = sum(abs(sample) ** 2 for sample in samples) / len(samples)
    ebn0_linear = 10.0 ** (ebn0_db / 10.0)
    noise_sigma = math.sqrt(avg_power / (2.0 * ebn0_linear))

    return [
        complex(
            sample.real + rng.gauss(0.0, noise_sigma),
            sample.imag + rng.gauss(0.0, noise_sigma),
        )
        for sample in samples
    ]


def receive_ofdm(samples: list[complex]) -> bytes:
    rx_bits: list[int] = []
    symbol_len = FFT_SIZE + CP_LEN

    for symbol_index in range(OFDM_SYMBOLS_PER_PACKET):
        start = symbol_index * symbol_len
        without_cp = samples[start + CP_LEN : start + symbol_len]
        freq_bins = fft64(without_cp)

        for carrier in DATA_CARRIERS:
            rx_bits.extend(qpsk_demap_symbol(freq_bins[signed_to_bin(carrier)]))

    return bits_to_bytes(rx_bits[:FRAME_BITS])


def simulate_point(ebn0_db: float, frames: int, rng: random.Random) -> OfdmResult:
    total_bits = 0
    bit_errors = 0
    frame_errors = 0
    crc_detected_errors = 0
    undetected_errors = 0

    for frame_index in range(frames):
        tx_frame = make_frame(frame_index)
        tx_bits = bytes_to_bits(tx_frame)
        tx_samples = transmit_ofdm(tx_frame)
        rx_samples = add_awgn(tx_samples, ebn0_db, rng)
        rx_frame = receive_ofdm(rx_samples)
        rx_bits = bytes_to_bits(rx_frame)

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

    return OfdmResult(
        ebn0_db=ebn0_db,
        frames=frames,
        bits=total_bits,
        bit_errors=bit_errors,
        frame_errors=frame_errors,
        crc_detected_errors=crc_detected_errors,
        undetected_errors=undetected_errors,
    )


def write_resource_grid_example() -> None:
    grid = build_ofdm_symbols(make_frame(0))[0]

    GRID_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GRID_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ofdm_symbol", "carrier", "fft_bin", "role", "i", "q"])

        for carrier in ACTIVE_CARRIERS:
            role = "pilot" if carrier in PILOT_CARRIERS else "data"
            value = grid[signed_to_bin(carrier)]
            writer.writerow([0, carrier, signed_to_bin(carrier), role, f"{value.real:.1f}", f"{value.imag:.1f}"])


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
                "fft_size",
                "cp_len",
                "data_subcarriers",
                "pilot_subcarriers",
                "ofdm_symbols_per_packet",
                "pad_bits",
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
                    FFT_SIZE,
                    CP_LEN,
                    len(DATA_CARRIERS),
                    len(PILOT_CARRIERS),
                    OFDM_SYMBOLS_PER_PACKET,
                    PAD_BITS,
                ]
            )

    write_resource_grid_example()

    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {GRID_PATH}")
    print("ebn0_db frames ber fer frame_errors crc_detected undetected")
    for result in results:
        print(
            f"{result.ebn0_db:>5.1f} {result.frames} {result.ber:.8f} {result.fer:.8f} "
            f"{result.frame_errors} {result.crc_detected_errors} {result.undetected_errors}"
        )

    print(f"frame_bytes={FRAME_BYTES}")
    print(f"frame_bits={FRAME_BITS}")
    print(f"fft_size={FFT_SIZE}")
    print(f"cp_len={CP_LEN}")
    print(f"data_subcarriers={len(DATA_CARRIERS)}")
    print(f"pilot_subcarriers={len(PILOT_CARRIERS)}")
    print(f"ofdm_symbols_per_packet={OFDM_SYMBOLS_PER_PACKET}")
    print(f"pad_bits={PAD_BITS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
