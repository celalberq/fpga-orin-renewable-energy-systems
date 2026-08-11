HDL Folder
==========

Implemented and explored HDL modules for Proje1 digital communication:

```text
comm_frame_loopback_top
crc8_byte
uart_tx
qpsk_mapper
qpsk_demapper
qpsk_loopback_top
qpsk_channel_model_top
ofdm_resource_grid_counter_top
ofdm_cp_grid_sequencer_top
tracker_ofdm_resource_grid_counter_top
tracker_ofdm_payload_placer_top
tracker_frame_encoder_top
tracker_payload_rom
tracker_frame_ofdm_pipeline_top
tracker_frame_qpsk_ofdm_batch_top
```

The list above reflects files currently present. QAM, a complete OFDM
IFFT/FFT modem, and an RF link remain optional extensions rather than validated
deliverables.

Current board build:

```text
Top module:
  tracker_frame_qpsk_ofdm_batch_top

Sources:
  uart_tx.v
  crc8_byte.v
  qpsk_mapper.v
  tracker_payload_rom.v
  tracker_frame_qpsk_ofdm_batch_top.v
```
