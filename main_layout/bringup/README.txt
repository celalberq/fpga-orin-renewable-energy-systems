Nexys Video Basic Bring-Up Code
===============================

Purpose:

```text
Prove the Nexys Video board works before project-specific HDL.
```

Build order:

```text
1. led_switch_no_reset_top.v
   Use with nexys_video_led_switch_no_reset.xdc.
   Result:
     Switches SW0-SW7 drive LEDs LD0-LD7.
   Use this as the simplest first proof after programming works.

2. led_switch_top.v
   Use with nexys_video_led_switch.xdc.
   Result:
     Switches SW0-SW7 drive LEDs LD0-LD7.
     CPU reset can force all LEDs off.

3. uart_hello_no_reset_top.v + uart_tx.v
   Use with nexys_video_uart_hello_no_reset.xdc.
   Result:
     LED0 blinks about once every 0.5 seconds.
     LEDs LD1-LD7 follow SW0-SW6.
     FPGA sends this UART line about twice per second:
       project=bringup,board=nexys_video,status=ok
   Use this if terminal output is blank and you want visible proof that the UART design is running.

4. uart_hello_top.v + uart_tx.v
   Use with nexys_video_uart_hello.xdc.
   Result:
     Switches still drive LEDs.
     FPGA sends this UART line once per second:
       project=bringup,board=nexys_video,status=ok

5. serial_logger.py
   Use from the PC to capture UART text into a CSV file.
```

Vivado notes:

```text
Board:
  Digilent Nexys Video 410-316

FPGA part:
  xc7a200tsbg484-1

Clock:
  100 MHz sysclk on port clk

Reset:
  cpu_resetn is active low

UART:
  115200 baud, 8 data bits, no parity, 1 stop bit

UART direction note:
  V18 / uart_tx_in is data from the PC/FT232R into the FPGA.
  AA19 / uart_rx_out is data from the FPGA into the PC/FT232R.
  Therefore the FPGA hello-world transmitter drives uart_rx_out.
```

Suggested Vivado steps:

```text
LED/switch test:
  1. Create RTL project.
  2. Add main_layout/bringup/hdl/led_switch_no_reset_top.v.
  3. Add main_layout/bringup/constraints/nexys_video_led_switch_no_reset.xdc as a constraint source.
  4. Set led_switch_no_reset_top as top.
  5. Synthesize, implement, generate bitstream, program board.

UART hello test:
  1. Create RTL project.
  2. Add main_layout/bringup/hdl/uart_tx.v.
  3. Add main_layout/bringup/hdl/uart_hello_no_reset_top.v.
  4. Add main_layout/bringup/constraints/nexys_video_uart_hello_no_reset.xdc.
  5. Set uart_hello_no_reset_top as top.
  6. Synthesize, implement, generate bitstream, program board.
```

PC logger command:

```text
python main_layout/tools/serial_logger.py --list-ports
python main_layout/tools/serial_logger.py --port COM3 --baud 115200 --log data/bringup_uart_log.csv
```

Change COM3 to the port shown on your PC.

Safety rule:

```text
Do not connect external sensors, solar modules, converters, or Ethernet experiments until this bring-up stage works.
```
