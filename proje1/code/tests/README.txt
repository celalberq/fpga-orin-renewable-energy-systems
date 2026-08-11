Proje1 Automated Regression Tests
=================================

Run from the repository root:

  python -m unittest discover -s proje1/code/tests -p "test_*.py" -v

Coverage includes the CRC-8 check value, frame integrity and corruption
detection, final 161-byte unified telemetry profile, sequence-gap handling,
and noiseless QPSK/OFDM reference-model round trips. Hardware and measured
evidence remain in `proje1/docs` and `proje1/data`.
