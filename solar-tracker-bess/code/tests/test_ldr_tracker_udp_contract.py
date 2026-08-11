from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


WORKSPACE = Path(__file__).resolve().parents[3]
ORIN_APP = WORKSPACE / "solar-tracker-bess" / "code" / "orin_app"
COMMUNICATION_PC_APP = WORKSPACE / "fpga-digital-communications" / "code" / "pc_app"
sys.path.insert(0, str(ORIN_APP))
sys.path.insert(0, str(COMMUNICATION_PC_APP))

import ldr_servo_tracker as ldr_tracker  # noqa: E402
import tracker_udp_comm_bridge as bridge  # noqa: E402


class LdrTrackerUdpContractTests(unittest.TestCase):
    def test_real_ldr_packet_crosses_shared_comm_bridge(self) -> None:
        args = SimpleNamespace(
            pan_min=10.0,
            pan_max=170.0,
            source_label="Orin four-LDR solar tracker",
            sensor_mount="fixed",
        )
        sample = ldr_tracker.LdrSample(42, 100, 2100, 1800, 1700, 1600)
        packet = ldr_tracker.make_udp_packet(
            7,
            "2026-08-08T15:00:00+00:00",
            args,
            sample,
            -0.1,
            0.2,
            57.0,
            124.0,
            57.5,
            123.5,
            0.707,
            "locked",
            100.0,
            0.1,
            0.01,
            "mcp3208-1000-ohm-load-estimate",
            True,
        )

        payload, line, frame_ok, profile, gap = bridge.process_packet(packet, None)
        forwarded = json.loads(
            bridge.forward_packet_with_comm(packet, payload, line, frame_ok, profile, gap)
        )

        self.assertTrue(frame_ok)
        self.assertEqual(profile["frame_bytes"], 133)
        self.assertEqual(profile["qpsk_symbols"], 532)
        self.assertEqual(profile["ofdm_symbols"], 12)
        self.assertIn("src=mcp", payload)
        self.assertEqual(forwarded["digital_comm"]["layer"], "CRC/QPSK/OFDM")


if __name__ == "__main__":
    unittest.main()
