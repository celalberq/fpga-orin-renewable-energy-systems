Solar Tracker and BESS Hardware Assets
======================

The implemented hardware combines Nexys Video, MCP3208, four KY-018 sensors,
PCA9685, two servos, a small panel, INA226, protected 1S cell, TP4056, and an
L9110 fan load.

```text
constraints/  Nexys Video PWM, packet, MPPT, real-sensing, and LDR UART XDCs
pin_maps/     Pointer to current wiring and I/O records
```

The authoritative as-built wiring, connector table, power boundaries, BESS mode
table, and BOM are in `system-integration/final_hardware_wiring_2026_08_11.md`.
Dated validation detail remains in `solar-tracker-bess/docs/board_test_17_*` through
`board_test_25_*`.
