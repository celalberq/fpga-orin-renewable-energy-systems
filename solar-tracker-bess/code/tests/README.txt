Code Tests
==========

Run from the workspace root:

```text
python -m unittest discover -s solar-tracker-bess/code/tests -p "test_*.py"
```

Current coverage:

```text
test_pan_only_servo_safety.py
  - --pan-only argument normalization
  - disabled tilt channel release
  - per-axis actuator telemetry

test_solar_tracking_ab_analyzer.py
  - fixed-versus-tracking power/energy gain
  - long log-gap exclusion

test_ldr_tracker_udp_contract.py
  - unified tracker/BESS JSON and compact-frame contract fields
  - signed BESS telemetry compatibility
```
