import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtWidgets import QApplication, QPushButton

from qc_inspector import main


class ManualLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with (
            patch.object(main, "get_all_setups", return_value=[]),
            patch.object(main.LauncherWindow, "_refresh_recent_table"),
            patch.object(main.LauncherWindow, "_refresh_supplier_chart"),
        ):
            self.window = main.LauncherWindow()
        self.addCleanup(self.window.deleteLater)
        self.button = next(
            button for button in self.window.findChildren(QPushButton)
            if button.text() == "Manuale d’uso"
        )

    def test_installed_button_opens_pdf_beside_executable(self):
        with tempfile.TemporaryDirectory(prefix="qc install ") as directory:
            executable = Path(directory) / "qc-inspector"
            manual = executable.with_name("Manuale_operativo_QC_Inspector.pdf")
            manual.touch()
            with (
                patch.object(main.sys, "frozen", True, create=True),
                patch.object(main.sys, "executable", str(executable)),
                patch.object(main, "_open_pdf", return_value=True) as open_url,
            ):
                self.button.click()

            open_url.assert_called_once_with(str(manual))

    def test_missing_pdf_has_a_user_visible_error(self):
        with tempfile.TemporaryDirectory() as directory:
            manual = Path(directory) / "missing.pdf"
            with (
                patch.object(main, "_manual_path", return_value=str(manual)),
                patch.object(main.QMessageBox, "warning") as warning,
                patch.object(main, "_open_pdf") as open_url,
            ):
                self.button.click()

            open_url.assert_not_called()
            self.assertIn(str(manual), warning.call_args.args[2])

    def test_unavailable_pdf_reader_shows_the_file_path(self):
        with tempfile.TemporaryDirectory() as directory:
            manual = Path(directory) / "manual.pdf"
            manual.touch()
            with (
                patch.object(main, "_manual_path", return_value=str(manual)),
                patch.object(main.QMessageBox, "warning") as warning,
                patch.object(main, "_open_pdf", return_value=False),
            ):
                self.button.click()

            self.assertIn(str(manual), warning.call_args.args[2])
