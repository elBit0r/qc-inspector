import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qc_inspector.core import app_config
from qc_inspector.ui.programming_window import ProgrammingWindow


class PdfImportTests(unittest.TestCase):
    def test_private_source_becomes_group_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source.write_bytes(b"synthetic PDF fixture")
            source.chmod(0o600)
            target_dir = root / "shared"
            with patch("qc_inspector.ui.programming_window.get_pdf_dir", return_value=str(target_dir)):
                target = Path(ProgrammingWindow._store_pdf_in_hash_path(ProgrammingWindow, str(source)))
                self.assertEqual(target.read_bytes(), source.read_bytes())
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
                self.assertEqual(target.stat().st_gid, target_dir.stat().st_gid)
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o600)
                self.assertEqual(list(target_dir.iterdir()), [target])
                before = target.stat().st_ino
                ProgrammingWindow._store_pdf_in_hash_path(ProgrammingWindow, str(source))
                self.assertEqual(target.stat().st_ino, before)

    def test_failed_copy_leaves_no_partial_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source.write_bytes(b"fixture")
            target = root / "shared"
            with patch("qc_inspector.ui.programming_window.get_pdf_dir", return_value=str(target)), patch(
                "qc_inspector.ui.programming_window.shutil.copyfileobj", side_effect=OSError("disk full")
            ), self.assertRaises(OSError):
                ProgrammingWindow._store_pdf_in_hash_path(ProgrammingWindow, str(source))
            self.assertEqual(list(target.iterdir()), [])

    def test_symlink_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source.write_bytes(b"fixture")
            shared = root / "shared"
            shared.mkdir()
            target = shared / (ProgrammingWindow._sha256_file(str(source)) + ".pdf")
            target.symlink_to(source)
            with patch("qc_inspector.ui.programming_window.get_pdf_dir", return_value=str(shared)):
                with self.assertRaisesRegex(ValueError, "simbolico"):
                    ProgrammingWindow._store_pdf_in_hash_path(ProgrammingWindow, str(source))
            self.assertEqual(source.read_bytes(), b"fixture")


class LegacyPrinterTests(unittest.TestCase):
    def test_legacy_printer_is_preserved_across_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.conf"
            config.write_text("printername = Legacy\n", encoding="utf-8")
            with patch.dict(os.environ, {"QC_INSPECTOR_CONFIG": str(config)}):
                for _ in range(2):
                    self.assertEqual(app_config.load_or_create_config()["label_printer"], "Legacy")
                config.write_text("printername = Legacy\nlabel_printer = Modern\n", encoding="utf-8")
                self.assertEqual(app_config.load_or_create_config()["label_printer"], "Modern")
