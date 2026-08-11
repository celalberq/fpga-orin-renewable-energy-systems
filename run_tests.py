#!/usr/bin/env python3
"""Run all hardware-independent repository regressions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

COMMANDS = [
    [sys.executable, "-m", "unittest", "discover", "-s", "proje1/code/tests", "-p", "test_*.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "proje2/code/tests", "-p", "test_*.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "proje3/code/tests", "-p", "test_*.py", "-v"],
    [sys.executable, "proje3/code/orin_app/test_ldr_servo_tracker.py"],
    [sys.executable, "proje3/code/pc_app/test_ldr_uart_monitor.py"],
    [sys.executable, "proje1/code/pc_app/tracker_udp_comm_bridge.py", "--self-test"],
]


def main() -> int:
    for command in COMMANDS:
        print(f"\n> {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    print("\nAll hardware-independent regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
