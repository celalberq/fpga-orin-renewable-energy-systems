from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "proje2" / "code" / "pc_app"))
sys.path.insert(0, str(ROOT / "proje2" / "code" / "sim"))

import parser_reference_model as parser_model  # noqa: E402
import solar_live_dashboard as dashboard  # noqa: E402
import solar_reliability_proxy as proxy  # noqa: E402


class ReliabilityProxyTests(unittest.TestCase):
    def test_every_n_rule_and_injection_window(self) -> None:
        self.assertTrue(proxy.should_apply(3, 3))
        self.assertFalse(proxy.should_apply(3, 4))
        self.assertTrue(proxy.should_apply(2, 4, inject_first=4))
        self.assertFalse(proxy.should_apply(2, 6, inject_first=4))
        self.assertFalse(proxy.should_apply(0, 10))

    def test_gap_corruption_and_backward_sequence(self) -> None:
        prepared, seq = proxy.prepare_packet({"seq": 12, "valid": True}, 9, False)
        self.assertEqual(seq, 12)
        self.assertEqual(prepared["seq_gap"], 2)
        self.assertTrue(prepared["valid"])

        corrupt, _ = proxy.prepare_packet({"seq": 13, "valid": True}, 12, True)
        self.assertFalse(corrupt["valid"])
        self.assertEqual(corrupt["error"], "proxy_injected_corruption")

        duplicate, _ = proxy.prepare_packet({"seq": 13, "valid": True}, 13, False)
        self.assertFalse(duplicate["valid"])
        self.assertEqual(duplicate["seq_gap"], -1)


class DashboardStateTests(unittest.TestCase):
    def test_healthy_warning_recovered_and_stale_states(self) -> None:
        state = dashboard.DashboardState(max_history=10, recovery_window=3)

        with patch.object(dashboard.time, "monotonic", return_value=100.0):
            state.add_packet({"seq": 1, "valid": True, "seq_gap": 0})
            self.assertEqual(state.snapshot(5.0)["link"]["state"], "healthy")

        with patch.object(dashboard.time, "monotonic", return_value=101.0):
            state.add_packet({"seq": 2, "valid": False, "seq_gap": 1})
            self.assertEqual(state.snapshot(5.0)["link"]["state"], "warning")

        for seq, now_s in ((3, 102.0), (4, 103.0), (5, 104.0)):
            with patch.object(dashboard.time, "monotonic", return_value=now_s):
                state.add_packet({"seq": seq, "valid": True, "seq_gap": 0})

        with patch.object(dashboard.time, "monotonic", return_value=104.1):
            recovered = state.snapshot(5.0)
        self.assertEqual(recovered["link"]["state"], "recovered")
        self.assertEqual(recovered["link"]["invalid_packets"], 1)
        self.assertEqual(recovered["link"]["sequence_gaps"], 1)

        with patch.object(dashboard.time, "monotonic", return_value=110.0):
            self.assertEqual(state.snapshot(5.0)["link"]["state"], "stale")


class BessModelTests(unittest.TestCase):
    def test_real_charge_and_discharge_energy_integration(self) -> None:
        model = dashboard.BessModel(
            capacity_wh=10.0,
            initial_soc_pct=50.0,
            load_w=0.0,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
        )

        with patch.object(dashboard.time, "monotonic", return_value=0.0):
            first = model.enrich(
                {"valid": True, "bess_measurement_mode": "real", "bess_state": "charging", "bess_power_w": 1.0}
            )
        self.assertEqual(first["bess_energy_wh"], 5.0)

        with patch.object(dashboard.time, "monotonic", return_value=5.0):
            charged = model.enrich(
                {"valid": True, "bess_measurement_mode": "real", "bess_state": "charging", "bess_power_w": 1.0}
            )
        self.assertAlmostEqual(charged["bess_energy_wh"], 5.0014, places=4)
        self.assertEqual(charged["bess_load_w"], 0.0)

        with patch.object(dashboard.time, "monotonic", return_value=10.0):
            discharged = model.enrich(
                {"valid": True, "bess_measurement_mode": "real", "bess_state": "discharging", "bess_power_w": -2.0}
            )
        self.assertAlmostEqual(discharged["bess_energy_wh"], 4.9986, places=4)
        self.assertEqual(discharged["bess_load_w"], 2.0)


class ParserReferenceTests(unittest.TestCase):
    def test_sample_udp_frame_metadata(self) -> None:
        metadata = parser_model.parse_frame(bytes.fromhex(parser_model.SAMPLE_FRAME_HEX))
        self.assertEqual(metadata["ethertype"], "0x0800")
        self.assertEqual(metadata["ip_version"], 4)
        self.assertEqual(metadata["ip_protocol"], 17)
        self.assertEqual(metadata["source_ip"], "192.168.1.10")
        self.assertEqual(metadata["destination_ip"], "192.168.1.20")
        self.assertEqual(metadata["source_port"], 1234)
        self.assertEqual(metadata["destination_port"], 5678)
        self.assertEqual(metadata["alert_flag"], "none")


if __name__ == "__main__":
    unittest.main()
