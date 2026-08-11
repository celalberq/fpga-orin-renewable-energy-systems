Network Telemetry Dashboard Network and Dashboard Code
=================================

Implemented code is organized as:

```text
pc_app/   UDP gateway/receiver, live dashboard, reliability proxy, analyzer
sim/      Stored-frame parser reference model
hdl/      Reserved network-HDL scope; only baseline constraints are present
tests/    Test index and expected parser outputs
```

Validated path: Orin UDP 5013 -> FPGA Digital Communications bridge -> dashboard UDP 5011 ->
browser dashboard on HTTP 8085.
