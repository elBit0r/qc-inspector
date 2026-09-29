import unittest

from qc_inspector.core.inspection_engine import (
    STATUS_DEROGATION,
    STATUS_FAIL,
    STATUS_PASS,
    evaluate_sampling_lot,
)


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
