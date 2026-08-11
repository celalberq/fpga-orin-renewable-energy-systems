PC App Folder
=============

These are the implemented PC-side transport, observability, and reliability
tools used by the integrated project:

```text
solar_telemetry_udp_gateway.py
  Reads or replays the solar-tracker-bess p3 solar packet, validates checksum/sequence,
  wraps it as JSON, sends UDP, and logs CSV.

solar_telemetry_udp_receiver.py
  Receives UDP JSON telemetry and logs it for the network project.

solar_live_dashboard.py
  Receives UDP JSON telemetry, serves a local browser dashboard, plots power,
  duty, and BESS SoC trend, simulates battery charge/discharge for solar packets,
  uses signed measured battery power for real BESS packets, shows link health,
  and logs data.

solar_reliability_proxy.py
  Receives Orin/dashboard UDP JSON telemetry, optionally injects packet loss,
  corruption, duplicates, and delay, recomputes sequence gaps, forwards packets
  to the dashboard, and logs reliability events.

reliability_evidence_analyzer.py
  Summarizes clean, degraded, and recovered reliability evidence.
```
