Proje2 Automated Regression Tests
=================================

Run from the repository root:

  python -m unittest discover -s proje2/code/tests -p "test_*.py" -v

Coverage includes controlled every-N fault injection, sequence gaps and
duplicates, dashboard healthy/warning/recovered/stale state transitions,
signed real-BESS energy integration, and Ethernet/IPv4/UDP parsing. Measured
clean/degraded/recovered evidence remains under `proje2/docs` and `proje2/data`.
