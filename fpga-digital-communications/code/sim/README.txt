Simulation Folder
=================

Implemented simulation and reference models:

```text
shared_packet_comm_sim.py
qpsk_packet_link_sim.py
ofdm_packet_link_sim.py
tracker_packet_profile.py
tracker_packet_comm_sim.py
tracker_qpsk_packet_link_sim.py
tracker_ofdm_packet_link_sim.py
qpsk_reference_model.py
```

Generated outputs are stored under `fpga-digital-communications/data`. The simulations validate
packet framing, symbol mapping, and OFDM resource accounting; they do not claim
an over-the-air modem.
