#!/usr/bin/env python3
"""Bridge live Orin tracker UDP packets into the fpga-digital-communications comm frame profile.

This tool keeps the three projects tied together:
  solar-tracker-bess sends rich tracker/INA226 JSON.
  fpga-digital-communications converts it into a compact protected telemetry frame profile.
  network-telemetry-dashboard can still receive the original JSON through UDP forwarding.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREAMBLE = bytes([0xA5, 0x5A])
CRC8_POLY = 0x07
DATA_SUBCARRIERS = 48
PILOT_SUBCARRIERS = 4
FFT_SIZE = 64
CP_LEN = 16


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


def frame_payload(payload: str) -> bytes:
    payload_bytes = payload.encode("ascii")
    if len(payload_bytes) > 255:
        raise ValueError("payload too long for one-byte length field")
    header_and_payload = bytes([len(payload_bytes)]) + payload_bytes
    return PREAMBLE + header_and_payload + bytes([crc8(header_and_payload)])


def check_frame(frame: bytes) -> bool:
    if len(frame) < 4 or frame[:2] != PREAMBLE:
        return False
    payload_len = frame[2]
    expected_len = len(PREAMBLE) + 1 + payload_len + 1
    return len(frame) == expected_len and crc8(frame[2:-1]) == frame[-1]


def clamp_int(value: Any, low: int = 0, high: int = 99999) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 0
    return max(low, min(high, number))


def clamp_signed_int(value: Any, magnitude: int = 99999) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 0
    return max(-magnitude, min(magnitude, number))


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(low, min(high, number))


def compact_state(state: Any) -> str:
    text = str(state).lower()
    if text.startswith("lock"):
        return "lock"
    return "seek"


def compact_source(packet: dict[str, Any]) -> str:
    source = str(
        packet.get("power_source", packet.get("source", packet.get("source_label", "")))
    ).lower()
    if "mcp" in source or "panel" in source:
        return "mcp"
    if "ina" in source or packet.get("v_mv") is not None:
        return "ina"
    return "sim"


def make_compact_payload(packet: dict[str, Any]) -> str:
    is_real_bess = packet.get("bess_measurement_mode") == "real" or ".bess." in str(
        packet.get("schema_variant", "")
    )
    tracker = packet.get("tracker", {})
    if not isinstance(tracker, dict):
        tracker = {}

    if is_real_bess and tracker:
        battery = packet.get("battery", {})
        if not isinstance(battery, dict):
            battery = {}
        seq = clamp_int(packet.get("seq"), 0, 99999)
        pan = clamp_float(tracker.get("pan_deg"), 0.0, 999.9)
        tilt = clamp_float(tracker.get("tilt_deg"), 0.0, 999.9)
        sun_pan = clamp_float(tracker.get("sun_pan_deg"), 0.0, 999.9)
        sun_tilt = clamp_float(tracker.get("sun_tilt_deg"), 0.0, 999.9)
        error_deg = clamp_float(tracker.get("track_error_deg"), 0.0, 999.9)
        state = compact_state(tracker.get("state", "seek"))
        panel_voltage_mv = clamp_int(packet.get("v_mv"))
        panel_power_mw = clamp_int(packet.get("p_mw"))
        battery_voltage_mv = clamp_int(float(battery.get("voltage_v", 0) or 0) * 1000.0)
        battery_current_ma = clamp_signed_int(float(battery.get("current_a", 0) or 0) * 1000.0)
        battery_power_mw = clamp_signed_int(float(battery.get("power_w", 0) or 0) * 1000.0)
        bess_state = {
            "charging": "chg",
            "discharging": "dis",
            "idle": "idl",
        }.get(str(packet.get("bess_state", "")).lower(), "unk")
        actuator = "hw" if bool(tracker.get("servo_enabled", False)) else "sw"
        return (
            f"mix,seq={seq:05d},pan={pan:05.1f},tilt={tilt:05.1f},"
            f"sun_pan={sun_pan:05.1f},sun_tilt={sun_tilt:05.1f},"
            f"err={error_deg:05.1f},st={state},"
            f"pv_mv={panel_voltage_mv:05d},pp_mw={panel_power_mw:05d},"
            f"bv_mv={battery_voltage_mv:05d},bi_ma={battery_current_ma:+06d},"
            f"bp_mw={battery_power_mw:+06d},bs={bess_state},act={actuator}"
        )

    if is_real_bess:
        seq = clamp_int(packet.get("seq"), 0, 99999)
        voltage_mv = clamp_int(packet.get("v_mv"))
        current_ma = clamp_signed_int(packet.get("i_ma"))
        power_mw = clamp_signed_int(packet.get("p_mw"))
        state = {
            "charging": "chg",
            "discharging": "dis",
            "idle": "idl",
        }.get(str(packet.get("bess_state", "")).lower(), "unk")
        source = compact_source(packet)
        return (
            f"bss,seq={seq:05d},v_mv={voltage_mv:05d},"
            f"i_ma={current_ma:+06d},p_mw={power_mw:+06d},"
            f"st={state},src={source}"
        )

    seq = clamp_int(packet.get("seq"), 0, 99999)
    pan = clamp_float(tracker.get("pan_deg"), 0.0, 999.9)
    tilt = clamp_float(tracker.get("tilt_deg"), 0.0, 999.9)
    sun_pan = clamp_float(tracker.get("sun_pan_deg"), 0.0, 999.9)
    sun_tilt = clamp_float(tracker.get("sun_tilt_deg"), 0.0, 999.9)
    error_deg = clamp_float(tracker.get("track_error_deg"), 0.0, 999.9)
    state = compact_state(tracker.get("state", "seek"))
    voltage_mv = clamp_int(packet.get("v_mv"))
    current_ma = clamp_int(packet.get("i_ma"))
    power_mw = clamp_int(packet.get("p_mw"))
    source = compact_source(packet)
    actuator = "hw" if bool(tracker.get("servo_enabled", False)) else "sw"

    return (
        f"trk,seq={seq:05d},"
        f"pan={pan:05.1f},tilt={tilt:05.1f},"
        f"sun_pan={sun_pan:05.1f},sun_tilt={sun_tilt:05.1f},"
        f"err={error_deg:05.1f},st={state},"
        f"v_mv={voltage_mv:05d},i_ma={current_ma:05d},"
        f"p_mw={power_mw:05d},src={source},act={actuator}"
    )


def comm_profile(frame: bytes) -> dict[str, int]:
    frame_bits = len(frame) * 8
    qpsk_symbols = math.ceil(frame_bits / 2)
    ofdm_symbols = math.ceil(qpsk_symbols / DATA_SUBCARRIERS)
    data_slots = ofdm_symbols * DATA_SUBCARRIERS
    pad_q = data_slots - qpsk_symbols

    return {
        "frame_bytes": len(frame),
        "frame_bits": frame_bits,
        "qpsk_symbols": qpsk_symbols,
        "ofdm_symbols": ofdm_symbols,
        "pad_q": pad_q,
        "tx_samples": ofdm_symbols * (FFT_SIZE + CP_LEN),
        "fft_samples": ofdm_symbols * FFT_SIZE,
        "cp_samples": ofdm_symbols * CP_LEN,
        "pilot_bins": ofdm_symbols * PILOT_SUBCARRIERS,
    }


def digital_comm_status(payload: str, line: str, frame_ok: bool, profile: dict[str, int], gap: int) -> dict[str, Any]:
    return {
        "layer": "CRC/QPSK/OFDM",
        "frame_ok": bool(frame_ok),
        "bridge_gap": gap,
        "payload_bytes": len(payload.encode("ascii")),
        "frame_bytes": profile["frame_bytes"],
        "frame_bits": profile["frame_bits"],
        "qpsk_symbols": profile["qpsk_symbols"],
        "ofdm_symbols": profile["ofdm_symbols"],
        "pad_q": profile["pad_q"],
        "tx_samples": profile["tx_samples"],
        "fft_samples": profile["fft_samples"],
        "cp_samples": profile["cp_samples"],
        "pilot_bins": profile["pilot_bins"],
        "compact_payload": payload,
        "status_line": line,
    }


def forward_packet_with_comm(packet: dict[str, Any], payload: str, line: str, frame_ok: bool, profile: dict[str, int], gap: int) -> bytes:
    enriched = dict(packet)
    enriched["digital_comm"] = digital_comm_status(payload, line, frame_ok, profile, gap)
    return json.dumps(enriched, separators=(",", ":")).encode("utf-8")


def status_line(packet: dict[str, Any], frame_ok: bool, profile: dict[str, int], gap: int) -> str:
    seq = clamp_int(packet.get("seq"), 0, 99999)
    return (
        f"p1br,seq={seq:05d},frame_b={profile['frame_bytes']:05d},"
        f"bits={profile['frame_bits']:05d},qpsk={profile['qpsk_symbols']:05d},"
        f"ofdm={profile['ofdm_symbols']:03d},pad_q={profile['pad_q']:05d},"
        f"gap={gap},ok={int(frame_ok)}"
    )


def sample_packet() -> dict[str, Any]:
    return {
        "source": "Orin INA226 real solar sensor",
        "seq": 23,
        "v_mv": 5506,
        "i_ma": 421,
        "p_mw": 2318,
        "tracker": {
            "pan_deg": 124.9,
            "tilt_deg": 102.6,
            "sun_pan_deg": 127.0,
            "sun_tilt_deg": 102.8,
            "track_error_deg": 2.1,
            "state": "locked",
            "servo_enabled": False,
        },
    }


def write_csv_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp_utc",
                "seq",
                "gap",
                "frame_ok",
                "payload_bytes",
                "frame_bytes",
                "frame_bits",
                "qpsk_symbols",
                "ofdm_symbols",
                "pad_q",
                "tx_samples",
                "fft_samples",
                "cp_samples",
                "pilot_bins",
                "compact_payload",
            ]
        )


def append_log(path: Path, packet: dict[str, Any], payload: str, frame_ok: bool, profile: dict[str, int], gap: int) -> None:
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                clamp_int(packet.get("seq"), 0, 99999),
                gap,
                int(frame_ok),
                len(payload.encode("ascii")),
                profile["frame_bytes"],
                profile["frame_bits"],
                profile["qpsk_symbols"],
                profile["ofdm_symbols"],
                profile["pad_q"],
                profile["tx_samples"],
                profile["fft_samples"],
                profile["cp_samples"],
                profile["pilot_bins"],
                payload,
            ]
        )


def process_packet(packet: dict[str, Any], previous_seq: int | None) -> tuple[str, str, bool, dict[str, int], int]:
    payload = make_compact_payload(packet)
    frame = frame_payload(payload)
    frame_ok = check_frame(frame)
    profile = comm_profile(frame)

    seq = clamp_int(packet.get("seq"), 0, 99999)
    gap = 0
    if previous_seq is not None:
        expected = (previous_seq + 1) % 100000
        if seq != expected:
            gap = 1

    return payload, status_line(packet, frame_ok, profile, gap), frame_ok, profile, gap


def run_self_test() -> int:
    payload, line, frame_ok, profile, gap = process_packet(sample_packet(), previous_seq=None)
    forwarded = json.loads(forward_packet_with_comm(sample_packet(), payload, line, frame_ok, profile, gap).decode("utf-8"))
    print(payload)
    print(line)
    print(f"payload_bytes={len(payload.encode('ascii'))}")
    print(f"frame_ok={int(frame_ok)} gap={gap}")
    print(f"forwarded_digital_comm={forwarded['digital_comm']['layer']}")
    print(
        "expected_tracker_ofdm="
        f"frame_b=00133 bits=01064 qpsk=00532 ofdm=012 pad_q=00044"
    )
    return 0 if frame_ok and profile["frame_bytes"] == 133 else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Convert live Orin tracker UDP JSON into fpga-digital-communications comm frame profiles.")
    parser.add_argument("--bind-host", default="0.0.0.0", help="UDP host to listen on.")
    parser.add_argument("--bind-port", type=int, default=5013, help="UDP port to listen on.")
    parser.add_argument("--forward-host", default="127.0.0.1", help="Optional dashboard UDP forward host.")
    parser.add_argument("--forward-port", type=int, default=5011, help="Optional dashboard UDP forward port.")
    parser.add_argument("--no-forward", action="store_true", help="Do not forward original JSON to dashboard.")
    parser.add_argument("--log", type=Path, default=Path("fpga-digital-communications/data/tracker_udp_comm_bridge_log.csv"))
    parser.add_argument("--max-packets", type=int, help="Stop after this many valid or invalid received packets.")
    parser.add_argument("--self-test", action="store_true", help="Run a local sample packet conversion and exit.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    write_csv_header(args.log)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind_host, args.bind_port))

    forward_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Listening for Orin tracker UDP JSON on {args.bind_host}:{args.bind_port}")
    if args.no_forward:
        print("Dashboard forwarding disabled.")
    else:
        print(f"Forwarding original JSON to {args.forward_host}:{args.forward_port}")
    print(f"Logging to {args.log}")

    previous_seq: int | None = None
    received = 0

    try:
        while args.max_packets is None or received < args.max_packets:
            data, source = sock.recvfrom(65535)
            received += 1

            try:
                packet = json.loads(data.decode("utf-8"))
                if not isinstance(packet, dict):
                    raise ValueError("top-level packet is not a JSON object")
                payload, line, frame_ok, profile, gap = process_packet(packet, previous_seq)
                previous_seq = clamp_int(packet.get("seq"), 0, 99999)
                append_log(args.log, packet, payload, frame_ok, profile, gap)
                print(f"OK from={source[0]}:{source[1]} {line}")
            except Exception as exc:  # noqa: BLE001 - keep logging alive for lab work
                print(f"BAD from={source[0]}:{source[1]} error={exc}")
                payload = ""
                line = ""
                frame_ok = False
                profile = {}
                gap = 0

            if not args.no_forward:
                if payload and profile:
                    forward_payload = forward_packet_with_comm(packet, payload, line, frame_ok, profile, gap)
                else:
                    forward_payload = data
                forward_sock.sendto(forward_payload, (args.forward_host, args.forward_port))
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()
        forward_sock.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
