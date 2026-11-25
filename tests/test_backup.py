import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile

from PyQt5.QtWidgets import QApplication

import qc_inspector
from qc_inspector.core import app_config, backup
from qc_inspector.database import db_manager, schema_manager
from qc_inspector.ui.backup_tab import BackupTab


EXAMPLE_PDF = (Path(qc_inspector.__file__).parent / "assets" / "examples"
               / "piastra-fissaggio-esempio.pdf")


class BackupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "source.sqlite"
        self.source_pdfs = self.root / "source-pdf"
        self.target = self.root / "target.sqlite"
        self.target_pdfs = self.root / "target-pdf"
        for database, pdfs in (
            (self.source, self.source_pdfs), (self.target, self.target_pdfs)
        ):
            schema_manager.initialize_database(str(database))
            pdfs.mkdir()
        self._add_setup(
            self.source, self.source_pdfs, "Disegno", "Lotto nel backup"
        )
        (self.source_pdfs / "storico").mkdir()
        shutil.copyfile(EXAMPLE_PDF, self.source_pdfs / "storico" / "extra.PDF")
        self.archive = backup.create_backup(self.root, self.source, self.source_pdfs)

    def _add_setup(self, database, pdfs, name, lot_code):
        pdf = pdfs / f"{name}.pdf"
        shutil.copyfile(EXAMPLE_PDF, pdf)
        with patch.object(db_manager, "get_db_path", return_value=str(database)):
            sampling_class = db_manager.get_all_sampling_classes()[0]
            operator = db_manager.save_operator("Operatrice", "", "", "")
            supplier = db_manager.save_supplier("Fornitore", "", "", "", "", "")
            setup_id, _ = db_manager.save_programming_changes(
                None, name, lot_code, str(pdf), sampling_class["id"], [dict(
                    balloon_num=1, pdf_page=0, balloon_x=0.25, balloon_y=0.25,
                    control_type="dimensional", criticality="N", nominal=10.0,
                    tol_plus=0.1, tol_minus=0.1, label="Quota", description="",
                )],
            )
            revision = db_manager.get_setup(setup_id)["setup_revision_id"]
            control, = db_manager.get_revision_controls(revision)
            db_manager.save_completed_inspection(
                setup_id, revision, lot_code, 1, 1, "NORMALE",
                {key: {"n": 1, "ac": 0, "re": 1} for key in "CIN"},
                "Operatrice", operator, "Fornitore", supplier,
                [dict(control_id=control["id"], sample_num=1, value_num=10.0, pass_fail=True)],
            )
        return setup_id

    def _rows(self, database, sql):
        with closing(sqlite3.connect(database)) as conn:
            return conn.execute(sql).fetchall()

    def _assert_history(self, setup_name, lot_code):
        with patch.object(db_manager, "get_db_path", return_value=str(self.target)):
            setup, = [row for row in db_manager.get_all_setups() if row["name"] == setup_name]
            lot, = db_manager.get_lots_for_setup(setup["id"])
            self.assertEqual(lot["lot_code"], lot_code)
            revision = db_manager.get_setup_revision(lot["setup_revision_id"])
            self.assertEqual(revision["name"], setup_name)
            self.assertEqual(Path(revision["pdf_path"]).parent, self.target_pdfs)
            self.assertEqual(Path(revision["pdf_path"]).read_bytes(), EXAMPLE_PDF.read_bytes())
            measurement, = db_manager.get_measurements_for_lot(lot["id"])
            self.assertEqual(measurement["value_num"], 10.0)
            control, = db_manager.get_revision_controls(revision["id"])
            self.assertEqual(measurement["control_id"], control["id"])
        self.assertEqual(self._rows(self.target, "PRAGMA foreign_key_check"), [])

    def test_create_backup_includes_snapshot_manifest_and_all_managed_pdfs(self):
        with ZipFile(self.archive) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {
                "database.sqlite", "backup.json", "pdf/Disegno.pdf", "pdf/storico/extra.PDF",
            })
            manifest = json.loads(archive.read("backup.json"))
            self.assertEqual(manifest["setup_count"], 1)
            self.assertIsNotNone(datetime.fromisoformat(manifest["generated_at"]).tzinfo)
            self.assertEqual(archive.read("pdf/Disegno.pdf"), EXAMPLE_PDF.read_bytes())
            snapshot = archive.extract("database.sqlite", self.root / "snapshot")
        self.assertEqual(self._rows(snapshot, "SELECT name FROM setups"), [("Disegno",)])

    def test_complete_restore_replaces_database_and_pdfs_and_saves_previous_state(self):
        self._add_setup(self.target, self.target_pdfs, "Locale", "Lotto locale")
        safety = backup.restore_backup(
            self.archive, self.target, self.target_pdfs, safety_destination=self.root
        )
        self.assertEqual(self._rows(self.target, "SELECT name FROM setups"), [("Disegno",)])
        self.assertFalse((self.target_pdfs / "Locale.pdf").exists())
        self.assertTrue((self.target_pdfs / "storico" / "extra.PDF").exists())
        self._assert_history("Disegno", "Lotto nel backup")
        backup.restore_backup(safety, self.target, self.target_pdfs, safety_destination=self.root)
        self._assert_history("Locale", "Lotto locale")

    def test_merge_replace_matches_case_insensitively_and_replaces_local_history(self):
        self._add_setup(self.target, self.target_pdfs, "DISEGNO", "Lotto locale")
        resolve = Mock(return_value=("replace", ""))
        backup.restore_backup(self.archive, self.target, self.target_pdfs, resolve_conflict=resolve)
        resolve.assert_called_once_with("Disegno")
        self.assertEqual(self._rows(self.target, "SELECT name FROM setups"), [("Disegno",)])
        self._assert_history("Disegno", "Lotto nel backup")

    def test_merge_rename_preserves_both_histories_with_distinct_ids(self):
        self._add_setup(self.target, self.target_pdfs, "Disegno", "Lotto locale")
        resolve = Mock(side_effect=[("rename", "DISEGNO"), ("rename", "Importato")])
        backup.restore_backup(self.archive, self.target, self.target_pdfs, resolve_conflict=resolve)
        self.assertEqual(resolve.call_count, 2)
        self._assert_history("Disegno", "Lotto locale")
        self._assert_history("Importato", "Lotto nel backup")
        self.assertEqual(self._rows(self.target, "SELECT count(DISTINCT id) FROM setups"), [(2,)])

    def test_merge_keeps_local_pdf_when_an_archived_filename_collides(self):
        self._add_setup(self.target, self.target_pdfs, "Disegno", "Lotto locale")
        local_pdf = self.target_pdfs / "Disegno.pdf"
        local_content = local_pdf.read_bytes() + b"\n% Copia locale"
        local_pdf.write_bytes(local_content)
        backup.restore_backup(
            self.archive, self.target, self.target_pdfs,
            resolve_conflict=lambda name: ("rename", "Importato"),
        )
        self.assertEqual(local_pdf.read_bytes(), local_content)
        self._assert_history("Importato", "Lotto nel backup")

    def test_backup_includes_pdf_referenced_from_outside_managed_directory(self):
        external = self.root / "disegni-esterni"
        external.mkdir()
        database = self.root / "external.sqlite"
        schema_manager.initialize_database(str(database))
        self._add_setup(database, external, "Esterno", "Lotto con PDF esterno")
        archive = backup.create_backup(self.root, database, self.source_pdfs)
        shutil.rmtree(external)
        backup.restore_backup(archive, self.target, self.target_pdfs, safety_destination=self.root)
        self._assert_history("Esterno", "Lotto con PDF esterno")

    def test_merge_without_duplicate_preserves_existing_data_without_prompt(self):
        self._add_setup(self.target, self.target_pdfs, "Locale", "Lotto locale")
        resolve = Mock()
        backup.restore_backup(self.archive, self.target, self.target_pdfs, resolve_conflict=resolve)
        resolve.assert_not_called()
        self._assert_history("Locale", "Lotto locale")
        self._assert_history("Disegno", "Lotto nel backup")

    def test_cancelling_duplicate_keeps_database_and_pdfs_untouched(self):
        self._add_setup(self.target, self.target_pdfs, "Disegno", "Lotto locale")
        before = self.target.read_bytes()
        with self.assertRaises(backup.RestoreCancelled):
            backup.restore_backup(
                self.archive, self.target, self.target_pdfs, resolve_conflict=lambda name: None
            )
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse((self.target_pdfs / "storico").exists())

    def test_failed_full_restore_rolls_back_pdf_and_database_changes(self):
        self._add_setup(self.target, self.target_pdfs, "Locale", "Lotto locale")
        before = self.target.read_bytes()
        with patch.object(backup, "_replace_database", side_effect=sqlite3.IntegrityError):
            with self.assertRaises(sqlite3.IntegrityError):
                backup.restore_backup(
                    self.archive, self.target, self.target_pdfs, safety_destination=self.root
                )
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.target_pdfs.iterdir()), [self.target_pdfs / "Locale.pdf"])
        self._assert_history("Locale", "Lotto locale")

    def test_archive_with_unsafe_pdf_path_is_rejected_without_touching_local_data(self):
        with ZipFile(self.archive, "a") as archive:
            archive.writestr("pdf/../escaped.pdf", b"invalid")
        before = self.target.read_bytes()
        with self.assertRaisesRegex(ValueError, "Percorso non valido"):
            backup.restore_backup(
                self.archive, self.target, self.target_pdfs, safety_destination=self.root
            )
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.target_pdfs.iterdir()), [])

    def test_backup_tab_remembers_selected_destination(self):
        app = QApplication.instance() or QApplication([])
        self.addCleanup(app.processEvents)
        config = self.root / "config"
        with patch.dict(os.environ, {app_config.CONFIG_PATH_ENV: str(config)}):
            tab = BackupTab(lambda: True)
            with patch("qc_inspector.ui.backup_tab.QFileDialog.getExistingDirectory",
                       return_value=str(self.root)):
                tab._choose_destination()
            self.assertEqual(tab.destination.text(), str(self.root))
            reopened = BackupTab(lambda: True)
            self.assertEqual(reopened.destination.text(), str(self.root))
