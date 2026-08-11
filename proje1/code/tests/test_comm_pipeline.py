from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "proje1" / "code" / "pc_app"))
sys.path.insert(0, str(ROOT / "proje1" / "code" / "sim"))

import ofdm_packet_link_sim as ofdm  # noqa: E402
import qpsk_packet_link_sim as qpsk  # noqa: E402
import tracker_udp_comm_bridge as bridge  # noqa: E402


class FrameTests(unittest.TestCase):
    def test_crc8_standard_check_value(self) -> None:
        self.assertEqual(bridge.crc8(b"123456789"), 0xF4)

    def test_frame_round_trip_and_tamper_detection(self) -> None:
        frame = bridge.frame_payload("solar,seq=00042")
        self.assertTrue(bridge.check_frame(frame))

        damaged = bytearray(frame)
        damaged[5] ^= 0x01
        self.assertFalse(bridge.check_frame(bytes(damaged)))

    def test_final_unified_packet_profile(self) -> None:
        packet = {
            "seq": 367,
            "schema_variant": "solar.tracker.bess.v1",
            "bess_measurement_mode": "real",
            "v_mv": 100,
            "p_mw": 1,
            "bess_state": "charging",
            "tracker": {
                "pan_deg": 44.9,
                "tilt_deg": 59.2,
                "sun_pan_deg": 41.1,
                "sun_tilt_deg": 60.1,
                "track_error_deg": 3.9,
                "state": "locked",
                "servo_enabled": True,
            },
            "battery": {
                "voltage_v": 3.84,
                "current_a": 0.236,
                "power_w": 0.908,
            },
        }

        payload, line, frame_ok, profile, gap = bridge.process_packet(packet, previous_seq=365)

        self.assertTrue(frame_ok)
        self.assertEqual(gap, 1)
        self.assertEqual(len(payload.encode("ascii")), 157)
        self.assertIn("bi_ma=+00236", payload)
        self.assertIn("bp_mw=+00908", payload)
        self.assertEqual(profile["frame_bytes"], 161)
        self.assertEqual(profile["frame_bits"], 1288)
        self.assertEqual(profile["qpsk_symbols"], 644)
        self.assertEqual(profile["ofdm_symbols"], 14)
        self.assertEqual(profile["pad_q"], 28)
        self.assertIn("gap=1,ok=1", line)

    def test_sequence_wrap_is_not_a_gap(self) -> None:
        packet = bridge.sample_packet()
        packet["seq"] = 0
        *_, gap = bridge.process_packet(packet, previous_seq=99999)
        self.assertEqual(gap, 0)


class ModemReferenceTests(unittest.TestCase):
    def test_qpsk_noiseless_round_trip(self) -> None:
        frame = qpsk.make_frame(7)
        bits = qpsk.bytes_to_bits(frame)
        recovered = qpsk.bits_to_bytes(qpsk.qpsk_demodulate(qpsk.qpsk_modulate(bits)))
        self.assertEqual(recovered, frame)

    def test_ofdm_noiseless_round_trip(self) -> None:
        frame = qpsk.make_frame(9)
        recovered = ofdm.receive_ofdm(ofdm.transmit_ofdm(frame))
        self.assertEqual(recovered, frame)


if __name__ == "__main__":
    unittest.main()
