import unittest
from types import SimpleNamespace

from PyQt5.QtWidgets import QStyle

from qc_inspector.ui.inspection_window import InspectionWindow
from qc_inspector.ui.programming_window import ProgrammingWindow


class _ControlRecorder:
    def setText(self, value):
        self.text = value

    def setIcon(self, value):
        self.icon = value

    def setToolTip(self, value):
        self.tooltip = value


class _StyleRecorder:
    @staticmethod
    def standardIcon(value):
        return value


class FullscreenControlTests(unittest.TestCase):
    def test_fullscreen_controls_follow_window_state(self):
        cases = (
            (ProgrammingWindow, "act_fullscreen"),
            (InspectionWindow, "btn_fullscreen"),
        )
        for window_class, control_attribute in cases:
            for fullscreen, expected_text, expected_icon in (
                (False, "Schermo intero", QStyle.SP_TitleBarMaxButton),
                (True, "Esci da schermo intero", QStyle.SP_TitleBarNormalButton),
            ):
                with self.subTest(
                        window=window_class.__name__, fullscreen=fullscreen):
                    control = _ControlRecorder()
                    window = SimpleNamespace(
                        isFullScreen=lambda: fullscreen,
                        style=lambda: _StyleRecorder(),
                    )
                    setattr(window, control_attribute, control)

                    window_class._update_fullscreen_control(window)

                    self.assertEqual(control.text, expected_text)
                    self.assertEqual(control.icon, expected_icon)
                    self.assertEqual(control.tooltip, f"{expected_text} (F11)")

    def test_toggle_enters_fullscreen_and_restores_maximized(self):
        for window_class in (ProgrammingWindow, InspectionWindow):
            for fullscreen, expected_call in (
                    (False, "fullscreen"), (True, "maximized")):
                with self.subTest(
                        window=window_class.__name__, fullscreen=fullscreen):
                    calls = []
                    window = SimpleNamespace(
                        isFullScreen=lambda: fullscreen,
                        showFullScreen=lambda: calls.append("fullscreen"),
                        showMaximized=lambda: calls.append("maximized"),
                        _update_fullscreen_control=lambda: calls.append("update"),
                    )

                    window_class._toggle_fullscreen(window)

                    self.assertEqual(calls, [expected_call, "update"])


if __name__ == "__main__":
    unittest.main()
