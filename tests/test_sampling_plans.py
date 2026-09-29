import unittest

from qc_inspector.core.sampling_plans import (
    get_default_sampling_plan,
    validate_sampling_plan,
)


class SamplingPlanValidationTests(unittest.TestCase):
    def test_default_plan_ends_with_infinity(self):
        rows = get_default_sampling_plan("NORMALE")

        validate_sampling_plan("NORMALE", rows)

        self.assertIsNone(rows[-1]["lot_max"])

    def test_finite_last_maximum_is_rejected(self):
        rows = get_default_sampling_plan("NORMALE")
        rows[-1]["lot_max"] = 999999999

        with self.assertRaisesRegex(ValueError, "infinito"):
            validate_sampling_plan("NORMALE", rows)


if __name__ == "__main__":
    unittest.main()
