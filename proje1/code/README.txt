Proje1 Communication Code
=========================

Implemented code is organized as:

```text
hdl/      Synthesizable CRC, QPSK, OFDM-accounting, and UART modules
sim/      Python reference models and packet-link simulations
pc_app/   Live unified UDP-to-communication-profile bridge
tests/    Test index and expected-output notes
```

Current simulation focus:

```text
sim/shared_packet_comm_sim.py
sim/qpsk_packet_link_sim.py
sim/ofdm_packet_link_sim.py
sim/tracker_packet_profile.py
sim/tracker_packet_comm_sim.py
sim/tracker_qpsk_packet_link_sim.py
sim/tracker_ofdm_packet_link_sim.py
```

The tracker simulations use the current proje3 Orin tracker/INA226 telemetry
packet as the payload, so proje1 now protects the same data used by proje2 and
proje3.
