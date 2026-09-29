import unittest
from datetime import datetime

from qc_inspector.core.sampling_plans import recommend_sampling_profile


class SamplingRecommendationTests(unittest.TestCase):
    reference_date = datetime(2026, 9, 4, 12, 0, 0)
    rules = {
        "history_validity_days": 730,
        "extended_passes_required": 1,
        "normal_passes_required": 2,
        "fail_resets_extended": 1,
        "derogation_counts_positive": 0,
    }

    @staticmethod
    def _lot(day: int, profile: str, result: str = "PASS") -> dict:
        return {
            "id": day,
            "closed": 1,
            "cancelled": 0,
            "sampling_profile": profile,
            "result": result,
            "created_at": f"2026-08-{day:02d}T10:00:00",
        }

    def _recommend(self, *lots: dict) -> str:
        return recommend_sampling_profile(
            list(lots), self.rules, self.reference_date
        )["profile"]

    def test_later_extended_pass_overrides_old_reduced_pass(self):
        profile = self._recommend(
            self._lot(1, "RIDOTTO"),
            self._lot(2, "ESTESO"),
        )

        self.assertEqual(profile, "NORMALE")

    def test_later_single_normal_pass_overrides_old_reduced_pass(self):
        profile = self._recommend(
            self._lot(1, "RIDOTTO"),
            self._lot(2, "NORMALE"),
        )

        self.assertEqual(profile, "NORMALE")

    def test_only_trailing_normal_passes_count_towards_reduced(self):
        profile = self._recommend(
            self._lot(1, "NORMALE"),
            self._lot(2, "ESTESO"),
            self._lot(3, "NORMALE"),
        )

        self.assertEqual(profile, "NORMALE")

    def test_two_trailing_normal_passes_recommend_reduced(self):
        profile = self._recommend(
            self._lot(1, "RIDOTTO"),
            self._lot(2, "NORMALE"),
            self._lot(3, "NORMALE"),
        )

        self.assertEqual(profile, "RIDOTTO")


if __name__ == "__main__":
    unittest.main()
