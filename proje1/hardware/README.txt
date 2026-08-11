Proje1 Hardware Assets
======================

This layer reuses the Nexys Video board and UART connection proven by the
shared platform. Project-specific XDC files are stored under `constraints/`.

```text
constraints/  Nexys Video builds from CRC loopback through tracker batch frame
pin_maps/     I/O planning notes; no separate communication daughterboard used
```

Validated top: `tracker_frame_qpsk_ofdm_batch_top` on
`xc7a200tsbg484-1`.
