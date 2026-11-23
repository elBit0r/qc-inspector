import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import qc_inspector
from qc_inspector.database import db_manager, schema_manager


EXAMPLE_PDF = (Path(qc_inspector.__file__).parent / "assets" / "examples"
               / "piastra-fissaggio-esempio.pdf")


class ExampleSetupTests(unittest.TestCase):
    def test_new_database_gets_one_example_with_five_revision_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = str(root / "qc.sqlite")
            pdf_dir = root / "pdf"
            with patch.object(schema_manager, "get_pdf_dir", return_value=str(pdf_dir)), \
                    patch.object(db_manager, "get_db_path", return_value=database):
                schema_manager.initialize_database(database, example_pdf=EXAMPLE_PDF)
                schema_manager.initialize_database(database, example_pdf=EXAMPLE_PDF)
                setup, = db_manager.get_all_setups()
                self.assertTrue(setup["name"].startswith("PF-001"))
                stored_pdf = Path(setup["pdf_path"])
                self.assertEqual(stored_pdf.parent, pdf_dir)
                self.assertEqual(stored_pdf.read_bytes(), EXAMPLE_PDF.read_bytes())
                controls = db_manager.get_revision_controls(setup["setup_revision_id"])
                self.assertEqual([row["nominal"] for row in controls], [120, 60, 8, 10, 70])
                self.assertEqual(
                    [(row["tol_plus"], row["tol_minus"]) for row in controls],
                    [(0.20, 0.20), (0.15, 0.15), (0.10, 0.10),
                     (0.05, 0.05), (0.10, 0.10)],
                )
                self.assertEqual([row["criticality"] for row in controls], ["N", "N", "I", "C", "I"])
                operator, = db_manager.get_all_operators()
                supplier, = db_manager.get_all_suppliers()
                self.assertEqual(operator["name"], "Operatore dimostrativo")
                self.assertEqual(supplier["name"], "Fornitore dimostrativo")
                self.assertEqual(db_manager.get_lots_for_setup(setup["id"]), [])
                db_manager.delete_setup(setup["id"])
                db_manager.delete_operator(operator["id"])
                db_manager.delete_supplier(supplier["id"])
                schema_manager.initialize_database(database, example_pdf=EXAMPLE_PDF)
                self.assertEqual(db_manager.get_all_setups(), [])
                self.assertEqual(db_manager.get_all_operators(), [])
                self.assertEqual(db_manager.get_all_suppliers(), [])

    def test_existing_empty_database_is_not_seeded(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "existing.sqlite")
            schema_manager.initialize_database(database)
            with patch.object(schema_manager, "get_pdf_dir") as get_pdf_dir, \
                    patch.object(db_manager, "get_db_path", return_value=database):
                schema_manager.initialize_database(database, example_pdf=EXAMPLE_PDF)
                self.assertEqual(db_manager.get_all_setups(), [])
                self.assertEqual(db_manager.get_all_operators(), [])
                self.assertEqual(db_manager.get_all_suppliers(), [])
                get_pdf_dir.assert_not_called()


class SetupRevisionTests(unittest.TestCase):
    def setUp(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._temporary_directory.name) / "qc.sqlite")
        schema_manager.initialize_database(self.db_path, create_backup=False)
        self._path_patch = patch.object(
            db_manager, "get_db_path", return_value=self.db_path
        )
        self._path_patch.start()
        connection = db_manager.get_connection()
        self.sampling_class_id = int(connection.execute(
            "SELECT id FROM sampling_classes WHERE is_default=1"
        ).fetchone()[0])
        connection.close()

    def tearDown(self):
        self._path_patch.stop()
        self._temporary_directory.cleanup()

    @staticmethod
    def _control(nominal=10.0):
        return {
            "id": None,
            "balloon_num": 1,
            "balloon_x": 0.25,
            "balloon_y": 0.25,
            "pdf_page": 0,
            "control_type": "dimensional",
            "criticality": "N",
            "label": "Quota A",
            "nominal": nominal,
            "tol_plus": 0.1,
            "tol_minus": 0.1,
            "description": "",
        }

    def _save_setup(self, name="Setup A", setup_id=None, nominal=10.0):
        return db_manager.save_programming_changes(
            setup_id, name, "Descrizione", "/tmp/disegno.pdf",
            self.sampling_class_id, [self._control(nominal)], [],
        )

    def test_invalid_measurement_payload_rolls_back(self):
        setup_id, _ = self._save_setup()
        revision_id = db_manager.get_setup(setup_id)["setup_revision_id"]
        control_id = db_manager.get_revision_controls(revision_id)[0]["id"]
        requirements = {key: {"n": 2, "ac": 0, "re": 1} for key in ("C", "I", "N")}
        valid = dict(control_id=control_id, sample_num=1, value_num=10.0,
                     value_bool=None, pass_fail=True)
        for invalid in (
            {"value_num": 20.0}, {"pass_fail": False},
            {"value_num": float("nan")}, {"value_num": float("inf")},
            {"value_num": None}, {"value_num": "10"}, {"value_num": True},
            {"value_bool": True}, {"pass_fail": "false"},
            {"accepted_in_derogation": "false"},
            {"accepted_in_derogation": True},
            {"value_num": 20.0, "pass_fail": False, "accepted_in_derogation": True},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    db_manager.save_completed_inspection(
                        setup_id, revision_id, "INVALID", 10, 2, "NORMALE",
                        requirements, "Operatore", None, "Fornitore", None,
                        [valid, dict(valid, sample_num=2, **invalid)],
                    )
                with closing(db_manager.get_connection()) as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM lots").fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0], 0)

    def test_yesno_and_complete_derogation(self):
        control = dict(self._control(), control_type="yesno", nominal=None,
                       tol_plus=None, tol_minus=None)
        setup_id, _ = db_manager.save_programming_changes(
            None, "Booleano", "", "/tmp/disegno.pdf", self.sampling_class_id,
            [control], [],
        )
        revision_id = db_manager.get_setup(setup_id)["setup_revision_id"]
        control_id = db_manager.get_revision_controls(revision_id)[0]["id"]
        requirements = {key: {"n": 1, "ac": 0, "re": 1} for key in ("C", "I", "N")}
        measurement = dict(control_id=control_id, sample_num=1, value_num=None,
                           value_bool=False, pass_fail=False,
                           accepted_in_derogation=True, derogation_reason="Motivo",
                           derogation_authorized_by="Responsabile",
                           derogation_accepted_by="Operatore",
                           derogation_at="2026-09-29T10:00:00")
        for change in ({"value_bool": "No"}, {"value_bool": 2},
                       {"value_bool": None}, {"value_num": 1},
                       {"pass_fail": True}, {"derogation_reason": " "},
                       {"derogation_at": "invalid"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                db_manager.save_completed_inspection(
                    setup_id, revision_id, "NO", 10, 1, "NORMALE", requirements,
                    "Operatore", None, "Fornitore", None, [dict(measurement, **change)],
                )
        lot_id = db_manager.save_completed_inspection(
            setup_id, revision_id, "OK", 10, 1, "NORMALE", requirements,
            "Operatore", None, "Fornitore", None, [measurement],
        )
        self.assertEqual(db_manager.get_lot(lot_id)["final_status"], "ACCETTATO IN DEROGA")

    def test_setup_names_are_unique_case_insensitively(self):
        self._save_setup("Setup A")
        with self.assertRaisesRegex(ValueError, "nome"):
            self._save_setup("setup a")

    def test_obsolete_setup_preserves_history_and_blocks_inspections(self):
        first_id, _ = self._save_setup("abc1234_rev1")
        second_id, _ = self._save_setup("abc1234_rev2")
        revision_id = db_manager.get_setup(first_id)["setup_revision_id"]
        control_id = db_manager.get_revision_controls(revision_id)[0]["id"]
        requirements = {key: {"n": 1, "ac": 0, "re": 1} for key in ("C", "I", "N")}
        measurements = [{
            "control_id": control_id,
            "sample_num": 1,
            "value_num": 10.0,
            "value_bool": None,
            "pass_fail": True,
            "accepted_in_derogation": False,
        }]

        def save(lot_code):
            return db_manager.save_completed_inspection(
                first_id, revision_id, lot_code, 10, 1, "NORMALE",
                requirements, "Operatore", None, "Fornitore", None, measurements,
            )

        lot_id = save("STORICO")
        db_manager.set_setup_obsolete(first_id, True)
        self.assertTrue(db_manager.get_setup(first_id)["is_obsolete"])
        self.assertEqual(db_manager.get_setup(first_id)["setup_revision_id"], revision_id)
        self.assertEqual({s["id"] for s in db_manager.get_all_setups()}, {first_id, second_id})
        active_setups = db_manager.get_all_setups(include_obsolete=False)
        self.assertEqual([s["id"] for s in active_setups], [second_id])
        with self.assertRaisesRegex(ValueError, "obsoleto"):
            save("BLOCCATO")

        history = db_manager.get_lot_history_for_setup(first_id)
        self.assertEqual([lot["id"] for lot in history], [lot_id])
        self.assertEqual(db_manager.get_lot_report_data(lot_id)["setup"]["id"], revision_id)

        db_manager.set_setup_obsolete(first_id, False)
        new_lot_id = save("RIATTIVATO")
        self.assertEqual(db_manager.get_lot(new_lot_id)["final_status"], "PASS")

    def test_changed_setup_creates_immutable_revision(self):
        setup_id, controls = self._save_setup(nominal=10.0)
        first_setup = db_manager.get_setup(setup_id)
        first_revision_id = first_setup["setup_revision_id"]

        changed = dict(controls[0])
        changed["nominal"] = 12.0
        db_manager.save_programming_changes(
            setup_id, "Setup A", "Descrizione", "/tmp/disegno.pdf",
            self.sampling_class_id, [changed], [],
        )

        latest_setup = db_manager.get_setup(setup_id)
        self.assertEqual(latest_setup["setup_version_number"], 2)
        self.assertNotEqual(latest_setup["setup_revision_id"], first_revision_id)
        self.assertEqual(
            db_manager.get_revision_controls(first_revision_id)[0]["nominal"],
            10.0,
        )
        self.assertEqual(
            db_manager.get_revision_controls(
                latest_setup["setup_revision_id"]
            )[0]["nominal"],
            12.0,
        )

    def test_saved_inspection_remains_bound_to_its_revision(self):
        setup_id, _ = self._save_setup(nominal=10.0)
        first_setup = db_manager.get_setup(setup_id)
        revision_id = first_setup["setup_revision_id"]
        revision_control = db_manager.get_revision_controls(revision_id)[0]
        requirements = {
            key: {"n": 1, "ac": 0, "re": 1} for key in ("C", "I", "N")
        }
        lot_id = db_manager.save_completed_inspection(
            setup_id, revision_id, "LOT-1", 100, 1, "NORMALE",
            requirements, "Operatore", None, "Fornitore", None,
            [{
                "control_id": revision_control["id"],
                "sample_num": 1,
                "value_num": 10.0,
                "value_bool": None,
                "pass_fail": True,
                "accepted_in_derogation": False,
            }],
        )

        current = db_manager.get_controls_for_setup(setup_id)[0]
        current["nominal"] = 12.0
        db_manager.save_programming_changes(
            setup_id, "Setup A", "Descrizione", "/tmp/disegno.pdf",
            self.sampling_class_id, [current], [],
        )

        report_data = db_manager.get_lot_report_data(lot_id)
        history = db_manager.get_lot_history_for_setup(setup_id)
        self.assertEqual(report_data["setup"]["id"], revision_id)
        self.assertEqual(report_data["controls"][0]["nominal"], 10.0)
        self.assertEqual(report_data["summary"]["lot"]["final_status"], "PASS")
        self.assertEqual(history[0]["setup_version_number"], 1)
        self.assertEqual(history[0]["state"], "CHIUSO")

    def test_incomplete_inspection_rolls_back_everything(self):
        setup_id, _ = self._save_setup()
        revision_id = db_manager.get_setup(setup_id)["setup_revision_id"]
        requirements = {
            key: {"n": 1, "ac": 0, "re": 1} for key in ("C", "I", "N")
        }
        with self.assertRaisesRegex(ValueError, "tutte le misure"):
            db_manager.save_completed_inspection(
                setup_id, revision_id, "INCOMPLETE", 10, 1, "NORMALE",
                requirements, "Operatore", None, "Fornitore", None, [],
            )
        connection = db_manager.get_connection()
        lot_count = connection.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
        measurement_count = connection.execute(
            "SELECT COUNT(*) FROM measurements"
        ).fetchone()[0]
        connection.close()
        self.assertEqual((lot_count, measurement_count), (0, 0))

    def test_out_of_range_measurement_rolls_back_everything(self):
        setup_id, _ = self._save_setup()
        revision_id = db_manager.get_setup(setup_id)["setup_revision_id"]
        control_id = db_manager.get_revision_controls(revision_id)[0]["id"]
        requirements = {
            key: {"n": 1, "ac": 0, "re": 1} for key in ("C", "I", "N")
        }
        measurements = [
            {
                "control_id": control_id,
                "sample_num": sample_num,
                "value_num": 10.0,
                "value_bool": None,
                "pass_fail": True,
                "accepted_in_derogation": False,
            }
            for sample_num in (1, 2)
        ]

        with self.assertRaisesRegex(ValueError, "non prevista"):
            db_manager.save_completed_inspection(
                setup_id, revision_id, "EXTRA-SAMPLE", 10, 1, "NORMALE",
                requirements, "Operatore", None, "Fornitore", None,
                measurements,
            )

        connection = db_manager.get_connection()
        lot_count = connection.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
        measurement_count = connection.execute(
            "SELECT COUNT(*) FROM measurements"
        ).fetchone()[0]
        connection.close()
        self.assertEqual((lot_count, measurement_count), (0, 0))


class MigrationTests(unittest.TestCase):
    def test_v2_migration_removes_open_and_cancelled_lots(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "legacy.sqlite")
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            schema_manager._create_new_v1(connection)
            schema_manager._migrate_v1_to_v2(connection)
            sampling_class_id = int(connection.execute(
                "SELECT id FROM sampling_classes WHERE is_default=1"
            ).fetchone()[0])
            now = "2026-01-01T10:00:00"
            setup_id = int(connection.execute(
                "INSERT INTO setups "
                "(name, description, pdf_path, sampling_class_id, "
                "created_at, updated_at) VALUES (?, '', ?, ?, ?, ?)",
                ("Legacy", "/tmp/legacy.pdf", sampling_class_id, now, now),
            ).lastrowid)
            connection.execute(
                "INSERT INTO setups "
                "(name, description, pdf_path, sampling_class_id, "
                "created_at, updated_at) VALUES (?, '', ?, ?, ?, ?)",
                ("legacy", "/tmp/legacy-duplicate.pdf", sampling_class_id,
                 now, now),
            )
            for lot_code, closed, cancelled in (
                    ("OPEN", 0, 0), ("CANCELLED", 1, 1), ("SAVED", 1, 0)):
                connection.execute(
                    "INSERT INTO lots "
                    "(setup_id, lot_code, lot_quantity, n_samples, created_at, "
                    "closed, cancelled) VALUES (?, ?, 1, 1, ?, ?, ?)",
                    (setup_id, lot_code, now, closed, cancelled),
                )
            connection.commit()
            connection.close()

            schema_manager.initialize_database(db_path, create_backup=False)
            connection = sqlite3.connect(db_path)
            rows = connection.execute(
                "SELECT lot_code FROM lots ORDER BY lot_code"
            ).fetchall()
            setup_names = connection.execute(
                "SELECT name, is_obsolete FROM setups ORDER BY id"
            ).fetchall()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            connection.close()

            self.assertEqual(version, 4)
            self.assertEqual(rows, [("SAVED",)])
            self.assertTrue(all(row[1] == 0 for row in setup_names))
            self.assertEqual(len({row[0].casefold() for row in setup_names}), 2)
            self.assertTrue(any("duplicato" in row[0] for row in setup_names))


if __name__ == "__main__":
    unittest.main()
