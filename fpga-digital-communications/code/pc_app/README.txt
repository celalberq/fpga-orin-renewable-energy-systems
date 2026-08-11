PC App Folder
=============

The PC bridge receives Orin unified UDP JSON, constructs and validates the
compact CRC frame, calculates QPSK/OFDM resource counts, forwards the original
JSON to the dashboard, and logs one row per packet.

```text
tracker_udp_comm_bridge.py
```

Final result: 368/368 CRC-valid frames and zero sequence gaps in
`fpga-digital-communications/data/unified_tracker_bess_bidirectional_demo_bridge.csv`.
