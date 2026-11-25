import unittest
from math import nextafter
from unittest.mock import patch

from qc_inspector.core.inspection_engine import (
    STATUS_DEROGATION,
    STATUS_FAIL,
    STATUS_PASS,
    evaluate_dimensional,
    evaluate_sampling_lot,
    get_control_limits,
)


class DimensionalEvaluationTests(unittest.TestCase):
    def setUp(self):
        separator = patch(
            "qc_inspector.core.app_config.get_decimal_separator", return_value=","
        )
        separator.start()
        self.addCleanup(separator.stop)

    def test_inclusive_asymmetric_limits_and_adjacent_values(self):
        for value, expected in (
            (0.5, (True, "PASS  (-0,200)")),
            (0.8, (True, "PASS  (+0,100)")),
            (nextafter(0.5, 0), (False, "FAIL  (-0,200  — sotto il minimo 0,500)")),
            (nextafter(0.8, 1), (False, "FAIL  (+0,100  — sopra il massimo 0,800)")),
        ):
            with self.subTest(value=value):
                self.assertEqual(evaluate_dimensional(value, 0.7, 0.1, 0.2), expected)

    def test_negative_nominal_measurements_and_tolerances(self):
        for value, expected in (
            (-0.8, True),
            (-0.5, True),
            (-0.801, False),
            (nextafter(-0.5, 0), False),
        ):
            with self.subTest(value=value):
                passed, _ = evaluate_dimensional(value, -0.7, -0.2, -0.1)
                self.assertEqual(passed, expected)

    def test_zero_tolerance_requires_exact_match(self):
        self.assertTrue(evaluate_dimensional(0.3, 0.3, 0, 0)[0])
        self.assertFalse(evaluate_dimensional(nextafter(0.3, 1), 0.3, 0, 0)[0])

    def test_small_nominal_shift_is_preserved_in_limits(self):
        self.assertFalse(evaluate_dimensional(-1.0, 5e-324, 1.0, 1.0)[0])

    def test_display_limits_are_returned_as_floats(self):
        limits = get_control_limits(dict(
            control_type="dimensional", nominal=0.7, tol_plus=0.1, tol_minus=0.2
        ))
        self.assertEqual(limits, (0.5, 0.8))
        self.assertTrue(all(isinstance(limit, float) for limit in limits))


class SamplingLotEvaluationTests(unittest.TestCase):
    @staticmethod
    def _lot(n=2, ac=1, re=2):
        lot = {"n_samples": n}
        for prefix in ("critical", "important", "normal"):
            lot[f"{prefix}_n"] = n
            lot[f"{prefix}_ac"] = ac
            lot[f"{prefix}_re"] = re
        return lot

    @staticmethod
    def _control(control_id):
        return {"id": control_id, "criticality": "N"}

    @staticmethod
    def _measurement(control_id, sample_num, passed, derogated=False):
        return {
            "control_id": control_id,
            "sample_num": sample_num,
            "pass_fail": passed,
            "accepted_in_derogation": derogated,
        }

    def test_multiple_failed_measures_on_one_piece_count_once(self):
        controls = [self._control(1), self._control(2)]
        measurements = [
            self._measurement(1, 1, False),
            self._measurement(2, 1, False),
            self._measurement(1, 2, True),
            self._measurement(2, 2, True),
        ]

        result = evaluate_sampling_lot(self._lot(), controls, measurements)

        self.assertEqual(result["by_criticality"]["N"]["defective"], 1)
        self.assertEqual(result["status"], STATUS_PASS)

    def test_open_failure_within_ac_produces_pass(self):
        controls = [self._control(1)]
        measurements = [
            self._measurement(1, 1, False),
            self._measurement(1, 2, True),
        ]

        result = evaluate_sampling_lot(self._lot(), controls, measurements)

        self.assertEqual(result["status"], STATUS_PASS)

    def test_derogated_failure_within_ac_still_produces_pass(self):
        controls = [self._control(1)]
        measurements = [
            self._measurement(1, 1, False, derogated=True),
            self._measurement(1, 2, True),
        ]

        result = evaluate_sampling_lot(self._lot(), controls, measurements)

        self.assertEqual(result["status"], STATUS_PASS)

    def test_reaching_re_with_open_failure_produces_fail(self):
        controls = [self._control(1)]
        measurements = [
            self._measurement(1, 1, False, derogated=True),
            self._measurement(1, 2, False),
        ]

        result = evaluate_sampling_lot(self._lot(), controls, measurements)

        self.assertEqual(result["status"], STATUS_FAIL)

    def test_reaching_re_with_all_failures_derogated_produces_derogation(self):
        controls = [self._control(1)]
        measurements = [
            self._measurement(1, 1, False, derogated=True),
            self._measurement(1, 2, False, derogated=True),
        ]

        result = evaluate_sampling_lot(self._lot(), controls, measurements)

        self.assertEqual(result["status"], STATUS_DEROGATION)

    def test_reaching_re_rejects_before_control_is_complete(self):
        controls = [self._control(1)]
        measurements = [
            self._measurement(1, 1, False),
            self._measurement(1, 2, False),
        ]

        result = evaluate_sampling_lot(
            self._lot(n=3, ac=1, re=2), controls, measurements
        )

        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], STATUS_FAIL)

    def test_out_of_range_measurement_does_not_complete_control(self):
        controls = [self._control(1)]
        measurements = [
            self._measurement(1, 1, True),
            self._measurement(1, 3, True),
        ]

        result = evaluate_sampling_lot(self._lot(n=2), controls, measurements)

        self.assertEqual(result["completed_total"], 1)
        self.assertEqual(result["expected_total"], 2)
        self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
