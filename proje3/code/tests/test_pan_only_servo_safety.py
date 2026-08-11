from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ORIN_APP = Path(__file__).resolve().parents[1] / "orin_app"
sys.path.insert(0, str(ORIN_APP))

import camera_light_tracker_udp_gateway as camera_tracker  # noqa: E402
import tracker_softloop_udp_gateway as soft_tracker  # noqa: E402


class FakePca9685:
    def __init__(self) -> None:
        self.released_channels: list[int] = []

    def release(self, channel: int) -> None:
        self.released_channels.append(channel)


class PanOnlyServoSafetyTests(unittest.TestCase):
    def test_pan_only_flag_holds_and_releases_tilt(self) -> None:
        with patch.object(sys, "argv", ["camera_light_tracker_udp_gateway.py", "--pan-only"]):
            args = camera_tracker.parse_args()

        self.assertTrue(args.disable_tilt)
        self.assertTrue(args.disable_tilt_servo)
        self.assertFalse(args.disable_pan)
        self.assertFalse(args.disable_pan_servo)

    def test_camera_tracker_releases_only_tilt_channel(self) -> None:
        pca = FakePca9685()
        args = argparse.Namespace(
            disable_pan_servo=False,
            disable_tilt_servo=True,
            pan_channel=15,
            tilt_channel=12,
        )

        camera_tracker.release_disabled_servo_channels(pca, args)

        self.assertEqual(pca.released_channels, [12])

    def test_soft_tracker_releases_only_tilt_channel(self) -> None:
        pca = FakePca9685()
        args = argparse.Namespace(
            disable_pan_servo=False,
            disable_tilt_servo=True,
            pan_channel=15,
            tilt_channel=12,
        )

        soft_tracker.release_disabled_servo_channels(pca, args)

        self.assertEqual(pca.released_channels, [12])

    def test_camera_packet_reports_pan_only_actuator(self) -> None:
        args = argparse.Namespace(
            lock_error_deg=5.0,
            pan_min=70.0,
            pan_max=110.0,
            source_label="test camera tracker",
            width=640,
            height=480,
            disable_pan_servo=False,
            disable_tilt_servo=True,
            camera_mount="fixed",
        )
        detection = {
            "detected": True,
            "confidence": 1.0,
            "target_x_px": 320.0,
            "target_y_px": 240.0,
            "frame_w": 640,
            "frame_h": 480,
            "brightness_max": 255,
            "area_px": 100,
            "mode": "synthetic",
        }

        packet = camera_tracker.make_packet(
            0,
            args,
            90.0,
            90.0,
            90.0,
            90.0,
            0.0,
            0.0,
            detection,
            (5000.0, 100.0, 500.0),
            True,
        )

        tracker = packet["tracker"]
        self.assertTrue(tracker["servo_enabled"])
        self.assertTrue(tracker["pan_servo_enabled"])
        self.assertFalse(tracker["tilt_servo_enabled"])
        self.assertEqual(tracker["servo_mode"], "pan-only")
        self.assertEqual(packet["vision"]["camera_mount"], "fixed")

    def test_fixed_camera_maps_error_to_absolute_pan_target(self) -> None:
        target = camera_tracker.target_angle(
            current=94.0,
            center=90.0,
            normalized_error=0.5,
            fov_deg=40.0,
            minimum=70.0,
            maximum=110.0,
            disabled=False,
            camera_mount="fixed",
        )

        self.assertEqual(target, 100.0)

    def test_fixed_camera_approaches_target_without_integrating_to_limit(self) -> None:
        pan = 90.0
        for _ in range(20):
            pan = camera_tracker.controlled_angle(
                current=pan,
                target=100.0,
                normalized_error=0.5,
                gain=12.0,
                max_step=2.0,
                minimum=70.0,
                maximum=110.0,
                disabled=False,
                camera_mount="fixed",
            )

        self.assertEqual(pan, 100.0)


if __name__ == "__main__":
    unittest.main()
