import unittest
from types import SimpleNamespace

from ldr_servo_tracker import (
    AltAzSequencer,
    DominantAxisSelector,
    FixedSensorMapper,
    LdrSample,
    ShadingDetector,
    SequentialAxisSelector,
    StableDirection,
    altaz_pan_error,
    axis_can_move,
    input_fault_status,
    make_udp_packet,
    panel_load_measurement,
    parse_packet,
    select_control_axes,
    step_from_error,
    step_toward_target,
)


class LdrServoTrackerTests(unittest.TestCase):
    def test_parse_packet_and_errors(self):
        sample = parse_packet("ldr,seq=00042,pv=02900,tl=1000,tr=2000,bl=1000,br=2000")
        self.assertEqual(sample.seq, 42)
        self.assertAlmostEqual(sample.normalized_errors()[0], 1 / 3)
        self.assertAlmostEqual(sample.normalized_errors()[1], 0.0)

    def test_four_direction_signs(self):
        left = LdrSample(1, 1000, 2000, 1000, 2000, 1000)
        right = LdrSample(2, 1000, 1000, 2000, 1000, 2000)
        up = LdrSample(3, 1000, 2000, 2000, 1000, 1000)
        down = LdrSample(4, 1000, 1000, 1000, 2000, 2000)
        self.assertLess(left.normalized_errors()[0], 0)
        self.assertGreater(right.normalized_errors()[0], 0)
        self.assertLess(up.normalized_errors()[1], 0)
        self.assertGreater(down.normalized_errors()[1], 0)

    def test_stable_direction_requires_two_samples(self):
        gate = StableDirection(2)
        self.assertEqual(gate.update(0.02, 0.007), 0)
        self.assertEqual(gate.update(0.02, 0.007), 1)
        self.assertEqual(gate.update(0.0, 0.007), 0)

    def test_step_is_bounded(self):
        self.assertEqual(step_from_error(0.005, 0.007, 100, 0.25, 1.0), 0.0)
        self.assertAlmostEqual(step_from_error(0.01, 0.007, 100, 0.25, 1.0), 0.3)
        self.assertEqual(step_from_error(-0.10, 0.007, 100, 0.25, 1.0), -1.0)
        self.assertEqual(step_toward_target(0.5, 1.0, 0.5, 3.0), 0.0)
        self.assertEqual(step_toward_target(20.0, 1.0, 0.5, 3.0), 3.0)

    def test_altaz_aligns_pan_before_tilt(self):
        self.assertEqual(
            select_control_axes(0.02, 0.03, 0.007, "altaz"),
            (True, False, "align-pan"),
        )
        self.assertEqual(
            select_control_axes(0.001, 0.03, 0.007, "altaz"),
            (False, True, "track-tilt"),
        )
        self.assertEqual(
            select_control_axes(0.001, -0.001, 0.007, "altaz"),
            (False, False, "locked"),
        )

    def test_altaz_hysteresis_keeps_tilt_active(self):
        sequencer = AltAzSequencer(0.02, 0.04, 15.0, 25.0, min_tilt_samples=1)
        self.assertEqual(sequencer.select(0.03, 0.05, 0.007), (True, False, "align-pan"))
        self.assertEqual(sequencer.select(0.015, 0.05, 0.007), (False, True, "track-tilt"))
        self.assertEqual(sequencer.select(0.03, 0.04, 0.007), (False, True, "track-tilt"))
        self.assertEqual(sequencer.select(0.05, 0.04, 0.007), (True, False, "align-pan"))

    def test_altaz_uses_error_vector_angle(self):
        sequencer = AltAzSequencer(0.02, 0.04, 15.0, 25.0)
        self.assertEqual(
            sequencer.select(-0.06, 0.64, 0.007),
            (False, True, "track-tilt"),
        )
        sequencer.phase = "align-pan"
        self.assertEqual(
            sequencer.select(0.14, 0.25, 0.007),
            (True, False, "align-pan"),
        )

    def test_altaz_pan_direction_for_all_quadrants(self):
        deadband = 0.007
        self.assertLess(altaz_pan_error(-0.2, 0.2, deadband), 0)   # lower-left
        self.assertGreater(altaz_pan_error(0.2, 0.2, deadband), 0)  # lower-right
        self.assertGreater(altaz_pan_error(-0.2, -0.2, deadband), 0)  # top-left
        self.assertLess(altaz_pan_error(0.2, -0.2, deadband), 0)    # top-right

    def test_altaz_pan_cannot_starve_tilt(self):
        sequencer = AltAzSequencer(
            0.02,
            0.04,
            15.0,
            25.0,
            max_pan_samples=3,
            min_tilt_samples=3,
        )
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (True, False, "align-pan"))
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (True, False, "align-pan"))
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (True, False, "align-pan"))
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (False, True, "track-tilt"))
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (False, True, "track-tilt"))
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (False, True, "track-tilt"))
        self.assertEqual(sequencer.select(0.2, -0.2, 0.007), (True, False, "align-pan"))

    def test_dominant_axis_uses_hysteresis(self):
        selector = DominantAxisSelector(0.05)
        self.assertEqual(selector.select(0.20, 0.10, 0.007), (True, False, "track-pan"))
        self.assertEqual(selector.select(0.20, 0.24, 0.007), (True, False, "track-pan"))
        self.assertEqual(selector.select(0.20, 0.26, 0.007), (False, True, "track-tilt"))
        self.assertEqual(selector.select(0.30, 0.26, 0.007), (False, True, "track-tilt"))
        self.assertEqual(selector.select(0.32, 0.26, 0.007), (True, False, "track-pan"))

    def test_dominant_axis_hands_off_at_limit(self):
        selector = DominantAxisSelector(0.05)
        self.assertEqual(
            selector.select(0.50, 0.20, 0.007, pan_available=False),
            (False, True, "track-tilt"),
        )
        self.assertFalse(axis_can_move(170.0, 0.2, 10.0, 170.0, 0.007))
        self.assertTrue(axis_can_move(170.0, -0.2, 10.0, 170.0, 0.007))

    def test_sequential_axis_commits_until_corrected(self):
        selector = SequentialAxisSelector()
        self.assertEqual(selector.select(0.20, 0.40, 0.007), (False, True, "track-tilt"))
        self.assertEqual(selector.select(0.50, 0.30, 0.007), (False, True, "track-tilt"))
        self.assertEqual(selector.select(0.50, -0.02, 0.007), (True, False, "track-pan"))
        self.assertEqual(selector.select(0.30, -0.10, 0.007), (True, False, "track-pan"))

    def test_sequential_axis_reacquires_after_lock(self):
        selector = SequentialAxisSelector()
        self.assertEqual(selector.select(0.0, 0.0, 0.007), (False, False, "locked"))
        self.assertEqual(selector.select(0.10, 0.02, 0.007), (True, False, "track-pan"))

    def test_sequential_axis_does_not_call_limits_locked(self):
        selector = SequentialAxisSelector()
        self.assertEqual(
            selector.select(0.50, 0.20, 0.007, False, False),
            (False, False, "blocked-limits"),
        )
        self.assertEqual(
            selector.select(-0.50, 0.20, 0.007, True, False),
            (True, False, "track-pan"),
        )

    def test_fixed_sensor_center_targets_servo_centers(self):
        mapper = FixedSensorMapper(90, 90, 10, 170, 10, 170, 120, 0.015, 0.05, 1, -1)
        self.assertEqual(mapper.targets(0.005, -0.005), (90, 90))

    def test_fixed_sensor_maps_all_quadrants(self):
        mapper = FixedSensorMapper(90, 90, 10, 170, 10, 170, 120, 0.015, 0.05, 1, -1)
        bottom_right = mapper.targets(0.3, 0.3)
        bottom_left = mapper.targets(-0.3, 0.3)
        top_right = mapper.targets(0.3, -0.3)
        top_left = mapper.targets(-0.3, -0.3)
        self.assertGreater(bottom_right[0], 90)
        self.assertLess(bottom_left[0], 90)
        self.assertLess(top_right[0], 90)
        self.assertGreater(top_left[0], 90)
        self.assertLess(bottom_right[1], 90)
        self.assertGreater(top_right[1], 90)

    def test_cartesian_can_drive_both_axes(self):
        self.assertEqual(
            select_control_axes(0.02, 0.03, 0.007, "cartesian"),
            (True, True, "cartesian"),
        )

    def test_panel_load_measurement(self):
        voltage_mv, current_ma, power_mw = panel_load_measurement(100.0, 1000.0)
        self.assertEqual(voltage_mv, 100.0)
        self.assertAlmostEqual(current_ma, 0.1)
        self.assertAlmostEqual(power_mw, 0.01)

    def test_udp_packet_matches_shared_tracker_contract(self):
        args = SimpleNamespace(
            pan_min=10.0,
            pan_max=170.0,
            source_label="test LDR tracker",
            sensor_mount="fixed",
        )
        sample = LdrSample(42, 100, 2100, 1800, 1700, 1600)
        packet = make_udp_packet(
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

        self.assertEqual(packet["schema_variant"], "orin.ldr_tracker.v1")
        self.assertEqual(packet["power_source"], "mcp3208-1000-ohm-load-estimate")
        self.assertEqual(packet["tracker"]["state"], "locked")
        self.assertEqual(packet["tracker"]["servo_mode"], "pan+tilt")
        self.assertEqual(packet["tracker"]["ldr"]["tl"], 2100)
        self.assertEqual(packet["light_sensor"]["panel_mv"], 100)

    def test_input_faults_identify_rail_and_low_light(self):
        near_zero = LdrSample(1, 100, 3, 1000, 1000, 1000)
        saturated = LdrSample(2, 100, 3950, 1000, 1000, 1000)
        low_light = LdrSample(3, 100, 100, 100, 100, 100)

        self.assertEqual(input_fault_status(near_zero, 1000, 5, 3900).label, "Sensor Fault")
        self.assertEqual(
            input_fault_status(saturated, 1000, 5, 3900).label,
            "Sensor Saturation",
        )
        self.assertEqual(input_fault_status(low_light, 1000, 5, 3900).label, "Low Light")

    def test_shading_detector_requires_sustained_drop_and_recovery(self):
        detector = ShadingDetector(3, 0.5, 2, 2)
        sample = LdrSample(1, 100, 1000, 1000, 1000, 1000)

        for _ in range(3):
            status = detector.update(sample, 10.0, "locked")
            self.assertFalse(status.active)
            self.assertEqual(status.label, "Learning")

        self.assertFalse(detector.update(sample, 4.0, "locked").active)
        status = detector.update(sample, 4.0, "locked")
        self.assertTrue(status.active)
        self.assertEqual(status.label, "Shading")

        self.assertTrue(detector.update(sample, 10.0, "locked").active)
        status = detector.update(sample, 10.0, "locked")
        self.assertFalse(status.active)
        self.assertEqual(status.label, "OK")

    def test_shading_detector_does_not_learn_while_seeking(self):
        detector = ShadingDetector(2, 0.5, 2, 2)
        sample = LdrSample(1, 100, 1000, 1000, 1000, 1000)

        detector.update(sample, 10.0, "track-pan")
        detector.update(sample, 10.0, "track-tilt")

        self.assertIsNone(detector.baseline)
        self.assertEqual(detector.learning, [])
        self.assertEqual(detector.update(sample, 10.0, "track-pan").label, "Standby")


if __name__ == "__main__":
    unittest.main()
