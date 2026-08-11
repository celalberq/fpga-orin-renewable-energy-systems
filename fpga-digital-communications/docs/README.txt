FPGA Digital Communications Verification Records
===========================

Simulation records use the `comm_test_*` prefix. Live Nexys Video records use
the `board_test_*` prefix. Together they validate CRC framing, QPSK mapping,
OFDM resource accounting, and the tracker/BESS communication profile.

Current docs:

```text
comm_test_01_shared_packet_framing.txt
comm_test_02_qpsk_packet_link.txt
comm_test_03_ofdm_packet_framing.txt
comm_test_04_tracker_packet_framing.txt
comm_test_05_tracker_qpsk_packet_link.txt
comm_test_06_tracker_ofdm_packet_link.txt
comm_test_07_tracker_udp_comm_bridge.txt
board_test_01_comm_frame_loopback.txt
board_test_02_qpsk_loopback.txt
board_test_03_qpsk_channel_model.txt
board_test_04_ofdm_resource_grid_counter.txt
board_test_05_ofdm_cp_grid_sequencer.txt
board_test_06_tracker_ofdm_resource_grid_counter.txt
board_test_07_tracker_ofdm_payload_placer.txt
board_test_08_tracker_frame_encoder.txt
board_test_09_tracker_frame_ofdm_pipeline.txt
board_test_10_tracker_frame_qpsk_ofdm_batch.txt
digital_comm_strengthening_plan.txt
```
