PC App Folder
=============

These PC utilities support UART bring-up and evidence analysis. Live tracking
control now runs on the Jetson Orin.

Current scripts:

```text
solar_packet_logger.py
solar_tracking_ab_analyzer.py
ldr_uart_monitor.py
```

Run:

```text
python solar-tracker-bess/code/pc_app/solar_packet_logger.py --port COM6 --baud 115200 --log solar-tracker-bess/data/solar_packet_v1_log.csv
```

Compare fixed-panel and pan-tracking camera/INA226 logs:

```text
python solar-tracker-bess/code/pc_app/solar_tracking_ab_analyzer.py --fixed-log solar-tracker-bess/data/solar_fixed_pan_ina226.csv --tracking-log solar-tracker-bess/data/solar_tracking_pan_ina226.csv
```

Monitor the panel plus four KY-018 FPGA test:

```text
python solar-tracker-bess/code/pc_app/ldr_uart_monitor.py --port COM6 --baud 115200
```
