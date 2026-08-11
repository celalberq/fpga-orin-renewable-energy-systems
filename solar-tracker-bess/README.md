# Solar Tracker and BESS

## FPGA/Jetson Two-Axis Solar Tracker and Bidirectional BESS Telemetry Prototype

## Purpose

Build a low-voltage renewable prototype in which the Nexys Video samples four
LDRs and panel voltage, the Jetson Orin performs calibrated two-axis tracking,
the PCA9685 drives the physical mount, and the INA226 measures signed battery
charge/discharge telemetry.

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
Jetson Orin Nano Super: installed and used as the live tracker/sensor gateway
```

## Validation Records

```text
docs/board_test_01_pwm_uart.txt
docs/board_test_02_scaled_telemetry.txt
docs/board_test_03_shared_packet_v1.txt
docs/board_test_04_auto_mppt_uart_dashboard.txt
docs/board_test_05_real_sensing_mcp3208.txt
docs/board_test_06_real_solar_voltage_mcp3208.txt
docs/board_test_07_ina226_orin_i2c.txt
docs/board_test_08_orin_ina226_udp_dashboard.txt
docs/board_test_09_pca9685_servo_orin_i2c.txt
docs/board_test_10_pan_tilt_servo_orin_i2c.txt
docs/board_test_11_software_tracker_udp.txt
docs/board_test_12_servo_tracker_udp.txt
docs/board_test_13_mounted_panel_integrated_demo.txt
docs/board_test_14_camera_light_tracker_udp.txt
docs/board_test_15_pan_only_camera_tracker.txt
docs/board_test_16_fixed_vs_pan_tracking_power.txt
docs/board_test_17_ky018_mcp3208_ldr_uart.txt
docs/board_test_18_replacement_pan_tilt_mechanism.txt
docs/board_test_19_ldr_servo_tracker_orin.txt
docs/board_test_20_ldr_tracker_udp_dashboard.txt
docs/board_test_21_ldr_shading_fault_detection.txt
docs/board_test_22_real_bess_ina226_discharge.txt
docs/board_test_23_real_bess_charge_udp_dashboard.txt
docs/board_test_24_unified_tracker_bess_discharge.txt
docs/board_test_25_unified_tracker_bess_bidirectional_demo.txt
```

## Vivado Top Module

```text
solar_ldr_uart_top
```

## Validated Results

```text
Auto MPPT UART/dashboard test: LIVE PASS
MCP3208 real solar voltage sensing: LIVE PASS
INA226 Orin I2C real current/power sensing: LIVE PASS
Orin INA226 UDP dashboard feed: LIVE PASS
PCA9685 Orin servo control: LIVE PASS
Replacement 3D pan/tilt mechanism through PCA9685: LIVE PASS
Software tracker UDP dashboard: LIVE PASS
Pan-only USB camera tracker recovery mode: READY FOR LIVE TEST
Fixed vs LDR-tracking weak-light load-power comparison: LIVE PASS (+24.141%)
Four KY-018 plus MCP3208 panel-voltage UART test: LIVE PASS
Nexys LDR UART directly on Orin /dev/ttyUSB0: LIVE PASS
Calibrated fixed-sensor absolute LDR tracker: LIVE PASS
Real LDR tracker through servo/UDP/comm/dashboard path: LIVE PASS (60/60)
Locked-state panel shading/fault detection: LIVE PASS (120/120, recovered)
Real INA226 BESS fan-load discharge: LIVE PASS (approximately -0.683 W)
Real TP4056/INA226 supervised charging: LIVE PASS (+0.895 to +0.908 W)
Unified tracker/panel/BESS dashboard path: LIVE PASS (60/60, 0 gaps)
Unified edited evidence video: ACCEPTED
Continuous tracker+BESS demo: LIVE PASS (368/368, 0 gaps)
Continuous BESS sequence: idle -> charging -> idle -> discharging -> idle
```

## Scope Boundary

Panel power is an indoor weak-light estimate across a known 1k-ohm
load. USB-C supplies the supervised TP4056 charge test; this does not claim
solar battery charging or simultaneous charge/load power sharing.
