# FPGA Digital Communications

## Renewable Telemetry Framing and QPSK/OFDM Resource Pipeline

## Purpose

Turn the live tracker/panel/BESS payload into a deterministic CRC frame and
validate QPSK mapping plus OFDM resource, pilot, padding, and cyclic-prefix
accounting in simulation, on the Nexys Video, and through the live PC bridge.

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
Jetson Orin Nano Super: installed and supplies live tracker/BESS telemetry
```

## Validation Records

```text
docs/comm_test_01_shared_packet_framing.txt
docs/board_test_01_comm_frame_loopback.txt
docs/comm_test_02_qpsk_packet_link.txt
docs/board_test_02_qpsk_loopback.txt
docs/board_test_03_qpsk_channel_model.txt
docs/comm_test_03_ofdm_packet_framing.txt
docs/comm_test_04_tracker_packet_framing.txt
docs/comm_test_05_tracker_qpsk_packet_link.txt
docs/comm_test_06_tracker_ofdm_packet_link.txt
docs/comm_test_07_tracker_udp_comm_bridge.txt
docs/board_test_04_ofdm_resource_grid_counter.txt
docs/board_test_05_ofdm_cp_grid_sequencer.txt
docs/board_test_06_tracker_ofdm_resource_grid_counter.txt
docs/board_test_07_tracker_ofdm_payload_placer.txt
docs/board_test_08_tracker_frame_encoder.txt
docs/board_test_09_tracker_frame_ofdm_pipeline.txt
docs/board_test_10_tracker_frame_qpsk_ofdm_batch.txt
```

## Simulation and Bridge Software

```text
code/sim/shared_packet_comm_sim.py
code/sim/qpsk_packet_link_sim.py
code/sim/ofdm_packet_link_sim.py
code/sim/tracker_packet_profile.py
code/sim/tracker_packet_comm_sim.py
code/sim/tracker_qpsk_packet_link_sim.py
code/sim/tracker_ofdm_packet_link_sim.py
code/pc_app/tracker_udp_comm_bridge.py
```

## FPGA Board Build

```text
Top module:
  tracker_frame_qpsk_ofdm_batch_top

Vivado part code:
  xc7a200tsbg484-1

HDL sources:
  code/hdl/uart_tx.v
  code/hdl/crc8_byte.v
  code/hdl/qpsk_mapper.v
  code/hdl/tracker_payload_rom.v
  code/hdl/tracker_frame_qpsk_ofdm_batch_top.v

Constraints:
  hardware/constraints/nexys_video_tracker_frame_qpsk_ofdm_batch.xdc
```

## Validated Results

```text
Tracker-only profile: 129-byte payload, 133-byte frame, 532 QPSK, 12 OFDM
Unified live profile: 157-byte payload, 161-byte frame, 644 QPSK, 14 OFDM
Final continuous demo: 368/368 CRC-valid frames, 0 sequence gaps
```

## Scope Boundary

This is communication framing, modulation/resource accounting, and
FPGA pipeline validation. It is not a complete over-the-air RF modem.
