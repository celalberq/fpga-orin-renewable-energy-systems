HDL Folder
==========

Planned HDL modules for solar-tracker-bess solar:

```text
pwm_generator
adc_spi_reader
sample_filter
power_calculator
mppt_perturb_observe
fault_protection
telemetry_uart
top_solar_mppt
```

Current board build:

```text
Top module:
  solar_mppt_auto_uart_top

Vivado part code:
  xc7a200tsbg484-1

Current MPPT state source:
  estimated power movement compared with previous packet

Current fault source:
  SW7 demo fault input or high duty protection when raw duty >= 0xF0
```

Next real-sensing build:

```text
Top module:
  solar_real_sense_uart_top

Vivado part code:
  xc7a200tsbg484-1

HDL sources:
  uart_tx.v
  mcp3208_reader.v
  solar_real_sense_uart_top.v

Constraints:
  solar-tracker-bess/hardware/constraints/nexys_video_solar_real_sense_uart.xdc

Status:
  HDL added, board test pending until MCP3208/current-sense parts arrive.
```

Real-sensing stage 01:

```text
MCP3208 CH0:
  voltage divider input

MCP3208 CH1:
  calibrated analog current-sense input later

Packet compatibility:
  keeps the same p3 UART format used by the gateway/dashboard.
```

Four-LDR bring-up build:

```text
Top module:
  solar_ldr_uart_top

HDL sources:
  uart_tx.v
  mcp3208_reader.v
  solar_ldr_uart_top.v

Constraints:
  solar-tracker-bess/hardware/constraints/nexys_video_solar_ldr_uart.xdc

MCP3208 channels:
  CH0 panel voltage divider
  CH1 grounded
  CH2 top-left KY-018
  CH3 top-right KY-018
  CH4 bottom-left KY-018
  CH5 bottom-right KY-018

UART packet:
  ldr,seq=00001,pv=01665,tl=1117,tr=1200,bl=1300,br=1400
```
