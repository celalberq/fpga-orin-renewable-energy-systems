#!/usr/bin/env python3
"""Summarize reliability proxy and dashboard logs for report evidence."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reliability warning/recovery evidence summary.")
    parser.add_argument("--proxy-log", type=Path, default=Path("network-telemetry-dashboard/data/solar_reliability_proxy_log.csv"))
    parser.add_argument("--dashboard-log", type=Path, default=Path("network-telemetry-dashboard/data/solar_live_dashboard_reliability_bridge_log.csv"))
    parser.add_argument("--out", type=Path, default=Path("network-telemetry-dashboard/data/solar_reliability_evidence_summary.txt"))
    parser.add_argument("--recent-window", type=int, default=20)
    return parser.parse_args()


def to_int(value: object) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize(args: argparse.Namespace) -> list[str]:
    proxy_rows = read_csv(args.proxy_log)
    dashboard_rows = read_csv(args.dashboard_log)

    action_counts = Counter(row.get("action", "") for row in proxy_rows)
    forwarded_rows = [row for row in proxy_rows if row.get("action", "").startswith("forward")]
    dropped_rows = [row for row in proxy_rows if row.get("action") == "drop"]
    corrupt_rows = [row for row in proxy_rows if row.get("action") == "forward_corrupt"]
    duplicate_rows = [row for row in proxy_rows if row.get("action") == "duplicate"]
    forwarded_gaps = [to_int(row.get("seq_gap")) for row in forwarded_rows]

    dash_valid = [row for row in dashboard_rows if to_int(row.get("valid")) == 1]
    dash_invalid = [row for row in dashboard_rows if to_int(row.get("valid")) == 0]
    dash_gaps = [to_int(row.get("seq_gap")) for row in dashboard_rows]
    dash_recent = dashboard_rows[-max(3, args.recent_window) :]
    dash_recent_invalid = sum(1 for row in dash_recent if to_int(row.get("valid")) == 0)
    dash_recent_gaps = sum(gap for gap in (to_int(row.get("seq_gap")) for row in dash_recent) if gap > 0)

    if not proxy_rows:
        proxy_status = "no proxy log found"
    elif dropped_rows or corrupt_rows or duplicate_rows:
        proxy_status = "injection observed"
    else:
        proxy_status = "clean forwarding only"

    if not dashboard_rows:
        dashboard_status = "no dashboard log found"
    elif dash_invalid or any(gap > 0 for gap in dash_gaps):
        dashboard_status = "warning evidence observed"
    else:
        dashboard_status = "clean dashboard evidence"

    if dashboard_rows and (dash_invalid or any(gap > 0 for gap in dash_gaps)) and dash_recent_invalid == 0 and dash_recent_gaps == 0:
        recovery_status = "recovered recent window"
    elif dashboard_rows and (dash_invalid or any(gap > 0 for gap in dash_gaps)):
        recovery_status = "warning still active in recent window"
    elif dashboard_rows:
        recovery_status = "no fault injected in dashboard log"
    else:
        recovery_status = "no dashboard recovery data"

    lines = [
        "Reliability Evidence Summary",
        "============================",
        "",
        f"Proxy log: {args.proxy_log}",
        f"Dashboard log: {args.dashboard_log}",
        "",
        "Proxy Results",
        "-------------",
        "",
        f"Status: {proxy_status}",
        f"Proxy rows: {len(proxy_rows)}",
        f"Forwarded rows: {len(forwarded_rows)}",
        f"Dropped rows: {len(dropped_rows)}",
        f"Corrupted rows: {len(corrupt_rows)}",
        f"Duplicate rows: {len(duplicate_rows)}",
        f"Max forwarded sequence gap: {max(forwarded_gaps) if forwarded_gaps else 0}",
        "",
        "Proxy action counts:",
    ]
    for action, count in sorted(action_counts.items()):
        lines.append(f"  {action or 'unknown'}: {count}")

    lines.extend(
        [
            "",
            "Dashboard Results",
            "-----------------",
            "",
            f"Status: {dashboard_status}",
            f"Dashboard rows: {len(dashboard_rows)}",
            f"Dashboard valid rows: {len(dash_valid)}",
            f"Dashboard invalid rows: {len(dash_invalid)}",
            f"Dashboard total sequence gaps: {sum(gap for gap in dash_gaps if gap > 0)}",
            f"Recent window rows: {len(dash_recent)}",
            f"Recent invalid rows: {dash_recent_invalid}",
            f"Recent sequence gaps: {dash_recent_gaps}",
            f"Recovery status: {recovery_status}",
            "",
            "Interpretation",
            "--------------",
            "",
            "A strong demo shows proxy injection first, dashboard warning during the bad",
            "window, then a recovered dashboard state after clean packets resume.",
            "",
        ]
    )
    return lines


def main() -> int:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = summarize(args)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
