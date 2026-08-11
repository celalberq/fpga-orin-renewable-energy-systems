#!/usr/bin/env python3
"""Shared tracker payload profile for fpga-digital-communications communication simulations."""

from __future__ import annotations

import math

from shared_packet_comm_sim import check_frame, frame_payload


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def virtual_sun(seq: int) -> tuple[float, float]:
    phase = 2.0 * math.pi * (seq % 70) / 70.0
    sun_pan = 90.0 + 42.0 * math.sin(phase)
    sun_tilt = 88.0 + 20.0 * math.sin(0.73 * phase + 0.8)
    return sun_pan, sun_tilt


def tracker_state(seq: int) -> dict[str, float | int | str]:
    sun_pan, sun_tilt = virtual_sun(seq)
    settle = min(1.0, seq / 24.0)
    sweep = 0.55 * math.sin(seq / 5.0)

    pan = 90.0 + (sun_pan - 90.0) * settle + sweep
    tilt = 90.0 + (sun_tilt - 90.0) * settle - 0.35 * math.cos(seq / 6.0)
    pan = clamp(pan, 35.0, 145.0)
    tilt = clamp(tilt, 55.0, 125.0)

    error_deg = math.hypot(sun_pan - pan, sun_tilt - tilt)
    locked = error_deg <= 10.0
    alignment = max(0.0, math.cos(math.radians(min(89.0, error_deg))))

    # Keep the same scale as the Orin dashboard tests: real indoor INA226 values
    # can be tiny, but the communication layer should still preserve fields.
    voltage_mv = int(round(10.0 + 5500.0 * alignment))
    current_ma = int(round(1.0 + 420.0 * alignment))
    power_mw = int(round((voltage_mv / 1000.0) * current_ma))

    return {
        "seq": seq,
        "pan": pan,
        "tilt": tilt,
        "sun_pan": sun_pan,
        "sun_tilt": sun_tilt,
        "error_deg": error_deg,
        "state": "lock" if locked else "seek",
        "voltage_mv": voltage_mv,
        "current_ma": current_ma,
        "power_mw": power_mw,
    }


def make_tracker_payload(seq: int) -> str:
    state = tracker_state(seq)
    return (
        f"trk,seq={seq:05d},"
        f"pan={float(state['pan']):05.1f},tilt={float(state['tilt']):05.1f},"
        f"sun_pan={float(state['sun_pan']):05.1f},sun_tilt={float(state['sun_tilt']):05.1f},"
        f"err={float(state['error_deg']):05.1f},st={state['state']},"
        f"v_mv={int(state['voltage_mv']):05d},i_ma={int(state['current_ma']):05d},"
        f"p_mw={int(state['power_mw']):05d},src=ina,act=sw"
    )


def make_tracker_frame(seq: int) -> bytes:
    return frame_payload(make_tracker_payload(seq))


def tracker_frame_ok(frame: bytes) -> bool:
    return check_frame(frame)


def main() -> int:
    payload = make_tracker_payload(23)
    frame = make_tracker_frame(23)
    print(payload)
    print(f"payload_bytes={len(payload.encode('ascii'))}")
    print(f"frame_bytes={len(frame)}")
    print(f"frame_ok={int(tracker_frame_ok(frame))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
