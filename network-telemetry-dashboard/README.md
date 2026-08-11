# Network Telemetry Dashboard

## Renewable Telemetry Transport, Reliability, and Dashboard Monitoring

## Purpose

Transport the live unified renewable packet over UDP, validate packets and
sequence continuity, expose tracker/BESS/protection state in a live dashboard,
and preserve auditable CSV evidence. A reliability proxy separately proves
warning and recovery behavior under injected drops and corruption.

## Repository Contents

```text
L1_design.txt
L2_design.txt
fpga_requirements.txt
first_tests_without_orin.txt
peripherals_costs_turkey.txt
code/
hardware/
docs/
data/
```

## Hardware Baseline

```text
FPGA: Digilent Nexys Video 410-316
Dashboard/bridge host: laptop/PC
Jetson Orin Nano Super: installed as the live sensor/tracker UDP gateway
```

## Validation Records

```text
docs/network_test_01_solar_udp_gateway.txt
docs/network_test_02_live_dashboard.txt
docs/network_test_03_bess_soc_dashboard.txt
docs/network_test_04_link_health_dashboard.txt
docs/network_test_05_orin_ina226_udp_sensor.txt
docs/network_test_06_software_tracker_udp_dashboard.txt
docs/network_test_07_tracker_reliability_proxy.txt
docs/network_test_08_tracker_bridge_dashboard_status.txt
docs/network_test_09_tracker_bridge_reliability_warning_recovery.txt
docs/network_test_10_camera_tracker_dashboard.txt
```

## Network Software

```text
code/pc_app/solar_telemetry_udp_gateway.py
code/pc_app/solar_telemetry_udp_receiver.py
code/pc_app/solar_live_dashboard.py
code/pc_app/solar_reliability_proxy.py
```

## Validated Results

```text
Use the live unified tracker/panel/BESS packet as the primary network payload.
The Orin publishes real sensor/control telemetry; the PC runs the communication
bridge, dashboard, packet validation, gap detection, and CSV evidence logger.

Final continuous run: 368/368 valid dashboard packets, 0 sequence gaps, real
idle/charging/discharging transitions, physical two-axis actuation, and
CRC/QPSK/OFDM metadata.
```

## Scope Boundary

The current implementation is a telemetry transport and observability
prototype, not an inline production firewall or deployed AI anomaly appliance.
