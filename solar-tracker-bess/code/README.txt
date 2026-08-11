Solar Tracker and BESS Renewable-Control Code
=============================

Implemented code is organized as:

```text
hdl/       PWM, MCP3208 SPI, solar packet, MPPT demo, and four-LDR UART tops
sim/       PWM reference model
orin_app/  INA226, PCA9685, camera fallback, and real LDR tracker applications
pc_app/    UART monitor/logger and fixed-versus-tracking analyzer
tests/     Servo-safety, UDP-contract, and A/B analyzer tests
```

Primary live application: `orin_app/ldr_servo_tracker.py`.
