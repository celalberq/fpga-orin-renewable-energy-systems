Network Telemetry Dashboard Automated Regression Tests
=================================

Run from the repository root:

  python -m unittest discover -s network-telemetry-dashboard/code/tests -p "test_*.py" -v

Coverage includes controlled every-N fault injection, sequence gaps and
duplicates, dashboard healthy/warning/recovered/stale state transitions,
signed real-BESS energy integration, and Ethernet/IPv4/UDP parsing. Measured
clean/degraded/recovered evidence remains under `network-telemetry-dashboard/docs` and `network-telemetry-dashboard/data`.
