import unittest
from types import SimpleNamespace

from qc_inspector.ui.programming_window import ProgrammingWindow


class ProgrammingTemporaryIdTests(unittest.TestCase):
    def test_temporary_ids_are_monotonic_and_never_reused(self):
        window_state = SimpleNamespace(_next_temp_control_id=-1)

        first = ProgrammingWindow._allocate_temp_control_id(window_state)
        second = ProgrammingWindow._allocate_temp_control_id(window_state)
        # La cancellazione o rinumerazione dei balloon non modifica il contatore.
        third = ProgrammingWindow._allocate_temp_control_id(window_state)

        self.assertEqual((first, second, third), (-1, -2, -3))
        self.assertEqual(len({first, second, third}), 3)


if __name__ == "__main__":
    unittest.main()
