Nexys Video Constraint Files
============================

Use these files in Vivado with:

```text
Add Sources -> Add or create constraints -> Add Files
```

Do not add XDC files as Verilog/design sources.

For the first LED/switch test, add:

```text
nexys_video_led_switch.xdc
```

Top module expected by this XDC:

```text
led_switch_top
```

Expected top-level ports:

```text
clk
cpu_resetn
sw[7:0]
led[7:0]
```

If Vivado says bitstream failed because of unconstrained logical ports, the XDC was not added,
was disabled, or the HDL top-level port names do not match these names.
