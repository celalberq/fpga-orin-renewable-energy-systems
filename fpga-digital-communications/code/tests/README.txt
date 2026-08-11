FPGA Digital Communications Automated Regression Tests
=================================

Run from the repository root:

  python -m unittest discover -s fpga-digital-communications/code/tests -p "test_*.py" -v

Coverage includes the CRC-8 check value, frame integrity and corruption
detection, final 161-byte unified telemetry profile, sequence-gap handling,
and noiseless QPSK/OFDM reference-model round trips. Hardware and measured
evidence remain in `fpga-digital-communications/docs` and `fpga-digital-communications/data`.
