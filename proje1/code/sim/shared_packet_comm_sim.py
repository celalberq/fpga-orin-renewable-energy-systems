#!/usr/bin/env python3
"""Digital communication framing simulation using the shared proje3 telemetry packet."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "shared_packet_comm_sim.csv"

PREAMBLE = bytes([0xA5, 0x5A])
CRC8_POLY = 0x07
RANDOM_SEED = 13


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


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ CRC8_POLY) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def fpga_packet_checksum(
    seq: int,
    duty_raw: int,
    duty_pct: int,
    voltage_mv: int,
    current_ma: int,
    power_mw: int,
    mppt_code: int,
    fault: int,
) -> int:
    chk = 0
    for value in (seq, duty_pct, voltage_mv, current_ma, power_mw):
        chk ^= value & 0xFF
        chk ^= (value >> 8) & 0xFF
    chk ^= duty_raw & 0xFF
    chk ^= mppt_code & 0x03
    chk ^= fault & 0x01
    return chk & 0xFF


def make_payload(seq: int, duty_raw: int, previous_duty: int) -> str:
    duty_pct = duty_raw * 100 // 255
    voltage_mv = 12000 + duty_raw * 20
    current_ma = 500 + duty_raw * 6
    power_mw = voltage_mv * current_ma // 1000
    fault = 1 if duty_raw >= 0xF0 else 0

    if duty_raw > previous_duty:
        mppt = "up"
        mppt_code = 1
    elif duty_raw < previous_duty:
        mppt = "dn"
        mppt_code = 2
    else:
        mppt = "hd"
        mppt_code = 0

    chk = fpga_packet_checksum(seq, duty_raw, duty_pct, voltage_mv, current_ma, power_mw, mppt_code, fault)

    return (
        f"p3,seq={seq:05d},d_pct={duty_pct:05d},v_mv={voltage_mv:05d},"
        f"i_ma={current_ma:05d},p_mw={power_mw:05d},mppt={mppt},"
        f"f={fault},chk={chk:02X},raw={duty_raw:02X}"
    )


def frame_payload(payload: str) -> bytes:
    payload_bytes = payload.encode("ascii")
    if len(payload_bytes) > 255:
        raise ValueError("payload too long for one-byte length field")
    header_and_payload = bytes([len(payload_bytes)]) + payload_bytes
    return PREAMBLE + header_and_payload + bytes([crc8(header_and_payload)])


def flip_bits(data: bytes, bit_error_probability: float, rng: random.Random) -> tuple[bytes, int]:
    output = bytearray(data)
    bit_errors = 0

    for byte_index in range(len(output)):
        mask = 0
        for bit_index in range(8):
            if rng.random() < bit_error_probability:
                mask ^= 1 << bit_index
                bit_errors += 1
        output[byte_index] ^= mask

    return bytes(output), bit_errors


def check_frame(received: bytes) -> bool:
    if len(received) < len(PREAMBLE) + 2:
        return False

    if received[:2] != PREAMBLE:
        return False

    payload_len = received[2]
    expected_len = len(PREAMBLE) + 1 + payload_len + 1
    if len(received) != expected_len:
        return False

    crc_region = received[2:-1]
    received_crc = received[-1]
    return crc8(crc_region) == received_crc


def run_simulation(target_ber: float, frames: int, rng: random.Random) -> SimulationResult:
    bits_sent = 0
    bit_errors = 0
    corrupted_frames = 0
    crc_detected_errors = 0
    undetected_errors = 0
    previous_duty = 0

    for frame_index in range(frames):
        duty_raw = (frame_index * 37) % 256
        payload = make_payload(seq=frame_index + 1, duty_raw=duty_raw, previous_duty=previous_duty)
        sent = frame_payload(payload)
        received, frame_bit_errors = flip_bits(sent, target_ber, rng)

        bits_sent += len(sent) * 8
        bit_errors += frame_bit_errors

        frame_corrupted = received != sent
        frame_accepted = check_frame(received)

        if frame_corrupted:
            corrupted_frames += 1
            if frame_accepted:
                undetected_errors += 1
            else:
                crc_detected_errors += 1

        previous_duty = duty_raw

    return SimulationResult(
        target_ber=target_ber,
        frames=frames,
        bits_sent=bits_sent,
        bit_errors=bit_errors,
        corrupted_frames=corrupted_frames,
        crc_detected_errors=crc_detected_errors,
        undetected_errors=undetected_errors,
    )


def main() -> int:
    rng = random.Random(RANDOM_SEED)
    frames = 1000
    target_bers = [0.0, 1e-5, 1e-4, 1e-3, 1e-2]
    results = [run_simulation(target_ber, frames, rng) for target_ber in target_bers]

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

    print(f"Wrote {OUT_PATH}")
    print("target_ber frames measured_ber frame_errors crc_detected undetected")
    for result in results:
        print(
            f"{result.target_ber:.5g} {result.frames} {result.measured_ber:.8f} "
            f"{result.corrupted_frames} {result.crc_detected_errors} {result.undetected_errors}"
        )

    example = make_payload(seq=1, duty_raw=0x80, previous_duty=0x00)
    print(f"example_payload={example}")
    print(f"example_frame_crc=0x{frame_payload(example)[-1]:02X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
