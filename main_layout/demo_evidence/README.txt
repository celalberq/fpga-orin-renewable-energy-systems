Demo Evidence Package
=====================

Purpose
-------

Collect the current proof that the three summer project parts work as one
integrated renewable-energy telemetry platform.

This folder is for report writing, CV bullets, demo recording, and quick
recovery when the system needs to be run again.

Current Demo Claim
------------------

```text
An Orin Nano based solar tracker uses four real KY-018 light sensors read by a
Nexys Video and MCP3208, drives a prototype-mounted solar panel through a real
PCA9685 pan/tilt servo mechanism, and measures a protected 1S battery through an
INA226. One mixed UDP packet carries tracker, panel, and signed battery telemetry
through a proje1 CRC/QPSK/OFDM communication bridge to the proje2 dashboard. A
single continuous 368-packet demonstration validates tracking while the BESS
transitions idle -> charging -> idle -> discharging -> idle; separate focused
tests validate the electrical measurements, shading detection, and recovery.
```

Current Integrated Path
-----------------------

```text
proje3 Nexys/MCP3208 LDR and panel sensing / Orin tracker / PCA9685 servos
  + INA226 real BESS voltage, signed current, and signed power
  -> UDP JSON to PC port 5013
  -> proje1 tracker_udp_comm_bridge.py
  -> compact CRC frame + QPSK/OFDM metadata
  -> forwarded UDP JSON to PC port 5011
  -> proje2 live dashboard
```

Current FPGA Proof Path
-----------------------

```text
Nexys Video / xc7a200tsbg484-1
  -> tracker_frame_qpsk_ofdm_batch_top
  -> tracker payload ROM
  -> CRC-8 frame
  -> QPSK symbol category counters
  -> OFDM data/pilot/null/CP placement counters
  -> UART J13
```

Best Evidence Files
-------------------

```text
main_layout/demo_evidence/video/tracker_subsystem_integrated_demo_2026-08-10.mp4
main_layout/demo_evidence/video/unified_tracker_bess_integrated_demo_2026-08-11_edited.mp4
main_layout/demo_evidence/video/unified_tracker_bess_bidirectional_final_demo_2026-08-11.mp4
main_layout/demo_evidence/video/README.txt
main_layout/demo_evidence/final_report/fpga_orin_solar_bess_final_report_2026_08_11.docx
main_layout/demo_evidence/final_report/fpga_orin_solar_bess_final_report_2026_08_11.pdf
main_layout/demo_evidence/final_presentation/fpga_orin_solar_bess_final_presentation_2026_08_11.pptx
main_layout/demo_evidence/bess_bidirectional_demo_runbook.txt
main_layout/demo_evidence/one_page_project_report_2026_08_11.txt
main_layout/demo_evidence/final_system_architecture_2026_08_11.md
main_layout/reports/tracker_system_evidence_summary.txt
main_layout/reports/tracker_system_evidence_metrics.csv
main_layout/reports/tracker_error_deg.svg
main_layout/reports/tracker_power_mw.svg
main_layout/reports/tracker_angles_deg.svg
main_layout/reports/comm_profile_bar.svg
proje2/data/solar_reliability_bridge_evidence_summary.txt

proje1/docs/board_test_10_tracker_frame_qpsk_ofdm_batch.txt
proje1/docs/comm_test_07_tracker_udp_comm_bridge.txt
proje2/docs/network_test_08_tracker_bridge_dashboard_status.txt
proje2/docs/network_test_09_tracker_bridge_reliability_warning_recovery.txt
proje2/docs/network_test_10_camera_tracker_dashboard.txt
proje3/docs/board_test_11_software_tracker_udp.txt
proje3/docs/board_test_12_servo_tracker_udp.txt
proje3/docs/board_test_13_mounted_panel_integrated_demo.txt
proje3/docs/board_test_14_camera_light_tracker_udp.txt
proje3/docs/board_test_16_fixed_vs_pan_tracking_power.txt
proje3/docs/board_test_20_ldr_tracker_udp_dashboard.txt
proje3/docs/board_test_21_ldr_shading_fault_detection.txt
proje3/docs/board_test_22_real_bess_ina226_discharge.txt
proje3/docs/board_test_23_real_bess_charge_udp_dashboard.txt
proje3/docs/board_test_24_unified_tracker_bess_discharge.txt
proje3/docs/board_test_25_unified_tracker_bess_bidirectional_demo.txt

proje1/data/unified_tracker_bess_final_demo_bridge.csv
proje2/data/unified_tracker_bess_final_demo_dashboard.csv
```

Current Headline Metrics
------------------------

```text
Continuous dashboard rows: 368 valid, 0 bad, 0 gaps
Continuous bridge frames: 368/368 CRC-valid, 0 gaps
Continuous BESS states: idle 191, charging 44, discharging 133
Continuous tracker locked samples: 213
Best observed tracking error: 0.012 deg
Fixed vs tracking mean-power gain: 24.141%
Fixed vs tracking energy gain: 24.229%
Shading test: 120 valid packets, 0 gaps
Shading detected at seq 61 and recovered to OK at seq 78

Earlier software-tracker aggregate:
Tracker valid dashboard rows: 573
Tracker sequence gaps: 0
Tracker locked rows: 110
Best tracking error: 2.817 deg
Bridge frame OK rows: 575
Bridge sequence gaps: 0
Mounted-panel demo dashboard packets: 114 valid, 0 bad, 0 gaps
Mounted-panel demo final tracker state: locked, about 3.2 deg error

Reliability proxy injected drops/corruption:
  dropped packets: 4
  corrupted packets: 3
  dashboard invalid packets: 3
  dashboard total sequence gaps: 4
  recent recovery window: 10 clean packets, 0 invalid, 0 gaps

Payload bytes: 129
Frame bytes: 133
Frame bits: 1064
QPSK symbols: 532
OFDM symbols: 12
QPSK padding symbols: 44
OFDM TX samples: 960
OFDM CP samples: 192
OFDM pilot bins: 48

Real BESS discharge: approximately 2.954 V, -231 mA, and -0.683 W
Real BESS charge: 3.835-3.842 V, +233 to +236 mA, +0.895 to +0.908 W
Earlier unified tracker+BESS baseline: 60/60 valid mixed frames, 0 gaps
Unified mixed payload/frame: 157/161 bytes
Unified mixed QPSK/OFDM profile: 644 QPSK symbols, 14 OFDM symbols
Unified demo BESS power: -0.636 to -0.638 W
Bidirectional demo: idle/charge/idle/discharge/idle in one continuous run
Bidirectional demo BESS charge/discharge: approximately +0.83 W / -0.64 W
Final valid idle cell voltage: 3.499-3.502 V
```

What This Proves
----------------

```text
proje3:
  Renewable energy source/sensor/control layer exists.
  Four real LDR sensors provide an absolute two-axis light target.
  Orin reads the Nexys UART stream, controls the tracker, and publishes telemetry.
  Orin can drive physical pan/tilt servos through PCA9685.
  Tracking improved estimated weak-light load power by 24.141% in the A/B run.
  Sustained panel shading is detected and clears automatically after recovery.
  A protected real 1S battery is measured during supervised charge and fan-load
  discharge, with current direction preserved end to end.
  Solar panel is mounted on the moving tracker using a prototype cardboard
  adapter/base and elastic-band stabilization.

proje1:
  Live renewable tracker, panel, and BESS telemetry is turned into a
  deterministic digital-comm frame.
  CRC, QPSK sizing, OFDM sizing, pilots, padding, and CP accounting are proven.
  Nexys Video validates the key packet pipeline on real FPGA hardware.

proje2:
  UDP network transport, packet validation, gap tracking, and dashboard
  observability are working with live data.
  Reliability warning and recovered-state evidence are proven through a proxy
  that injects packet drops/corruption after the proje1 bridge.
```

Known Limitation
----------------

```text
The pan/tilt mechanism, panel mount, fixed LDR cross, and battery wiring remain
prototype-grade. The available handheld LED is too weak for useful panel-current
resolution, so panel power is estimated from MCP3208 voltage across a known
1k-ohm load. The INA226 is instead used on the battery path, where it resolves
real charge and discharge current. The temporary mechanical battery connections
are suitable only for supervised bench tests, and the TP4056 has no validated
simultaneous charge/load power path. The initial approximately 0.63 V INA226 bus
reading in the continuous demo came from an open monitored path and is excluded
from battery-voltage claims.
```
