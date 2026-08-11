#!/usr/bin/env python3
"""CRC/framing simulation using the Orin solar-tracker telemetry payload."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

from shared_packet_comm_sim import flip_bits
from tracker_packet_profile import make_tracker_frame, make_tracker_payload, tracker_frame_ok


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "tracker_packet_comm_sim.csv"
EXAMPLES_PATH = PROJECT_ROOT / "data" / "tracker_packet_examples.csv"

RANDOM_SEED = 41
FRAMES = 1000
TARGET_BERS = [0.0, 1e-5, 1e-4, 1e-3, 1e-2]


@dataclass
class SimulationResult:
    target_ber: float
    frames: int
    bits_sent: int
    bit_errors: int
    corrupted_frames: int
    crc_detected_errors: int
    undetected_errors: int

    @property
    def measured_ber(self) -> float:
        return self.bit_errors / self.bits_sent if self.bits_sent else 0.0

    @property
    def frame_error_rate(self) -> float:
        return self.corrupted_frames / self.frames if self.frames else 0.0


def run_simulation(target_ber: float, frames: int, rng: random.Random) -> SimulationResult:
    bits_sent = 0
    bit_errors = 0
    corrupted_frames = 0
    crc_detected_errors = 0
    undetected_errors = 0

    for seq in range(frames):
        sent = make_tracker_frame(seq)
        received, frame_bit_errors = flip_bits(sent, target_ber, rng)
        bits_sent += len(sent) * 8
        bit_errors += frame_bit_errors

        frame_corrupted = received != sent
        frame_accepted = tracker_frame_ok(received)
        if frame_corrupted:
            corrupted_frames += 1
            if frame_accepted:
                undetected_errors += 1
            else:
                crc_detected_errors += 1

    return SimulationResult(
        target_ber=target_ber,
        frames=frames,
        bits_sent=bits_sent,
        bit_errors=bit_errors,
        corrupted_frames=corrupted_frames,
        crc_detected_errors=crc_detected_errors,
        undetected_errors=undetected_errors,
    )


def write_examples() -> None:
    EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EXAMPLES_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["seq", "payload", "payload_bytes", "frame_bytes"])
        for seq in [0, 12, 23, 35, 52]:
            payload = make_tracker_payload(seq)
            frame = make_tracker_frame(seq)
            writer.writerow([seq, payload, len(payload.encode("ascii")), len(frame)])


def main() -> int:
    rng = random.Random(RANDOM_SEED)
    results = [run_simulation(target_ber, FRAMES, rng) for target_ber in TARGET_BERS]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "target_ber",
                "frames",
                "bits_sent",
                "bit_errors",
                "measured_ber",
                "corrupted_frames",
                "frame_error_rate",
                "crc_detected_errors",
                "undetected_errors",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.target_ber,
                    result.frames,
                    result.bits_sent,
                    result.bit_errors,
                    f"{result.measured_ber:.8f}",
                    result.corrupted_frames,
                    f"{result.frame_error_rate:.8f}",
                    result.crc_detected_errors,
                    result.undetected_errors,
                ]
            )

    write_examples()

    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {EXAMPLES_PATH}")
    print("target_ber frames measured_ber frame_errors crc_detected undetected")
    for result in results:
        print(
            f"{result.target_ber:.5g} {result.frames} {result.measured_ber:.8f} "
            f"{result.corrupted_frames} {result.crc_detected_errors} {result.undetected_errors}"
        )

    example = make_tracker_payload(23)
    print(f"example_payload={example}")
    print(f"example_payload_bytes={len(example.encode('ascii'))}")
    print(f"example_frame_bytes={len(make_tracker_frame(23))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
