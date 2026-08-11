#!/usr/bin/env python3
"""Small PWM reference model for the first solar/MPPT simulation step."""

from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "data" / "pwm_reference_samples.csv"


def pwm_wave(duty_cycle: float, period_ticks: int, cycles: int):
    high_ticks = round(duty_cycle * period_ticks)

    for absolute_tick in range(period_ticks * cycles):
        tick_in_period = absolute_tick % period_ticks
        pwm_out = 1 if tick_in_period < high_ticks else 0
        yield absolute_tick, tick_in_period, duty_cycle, pwm_out


def main() -> int:
    period_ticks = 100
    cycles = 3
    duty_cycles = [0.10, 0.25, 0.50, 0.75]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["absolute_tick", "tick_in_period", "duty_cycle", "pwm_out"])

        for duty_cycle in duty_cycles:
            for row in pwm_wave(duty_cycle, period_ticks, cycles):
                writer.writerow(row)

    print(f"Wrote {OUT_PATH}")
    print("PWM duty cycles:", ", ".join(f"{duty:.0%}" for duty in duty_cycles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
