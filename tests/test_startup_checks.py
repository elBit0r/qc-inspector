import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qc_inspector.core import app_config, startup_checks
from qc_inspector import main as entry


class StartupAccessTests(unittest.TestCase):
    def test_writable_paths_preserve_files_and_remove_probes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'qc.conf'
            database = root / 'data' / 'qc.sqlite'
            database.parent.mkdir()
            database.write_bytes(b'unchanged')
            config.write_text('db_path = data/qc.sqlite\npdf_dir = pdf\n')
            with patch.object(app_config, 'get_config_path', return_value=str(config)), \
                    patch.object(startup_checks, 'get_config_path', return_value=str(config)):
                startup_checks.check_runtime_access()
            self.assertEqual(database.read_bytes(), b'unchanged')
            self.assertTrue((root / 'pdf').is_dir())
            self.assertFalse(list(root.rglob('.qc-access-*')))

    def test_directory_denied_is_reported_before_loading_config(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(startup_checks, 'get_config_path', return_value=directory + '/qc.conf'), \
                patch.object(startup_checks.os, 'access', return_value=False), \
                patch.object(startup_checks, 'get_db_path') as database:
            with self.assertRaisesRegex(PermissionError, directory):
                startup_checks.check_runtime_access()
            database.assert_not_called()

    def test_read_only_file_open_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qc.conf'
            path.touch()
            with patch('builtins.open', side_effect=PermissionError(str(path))):
                with self.assertRaises(PermissionError):
                    startup_checks._check_file(str(path))

    def test_split_system_config_requires_read_only_base_and_writable_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'etc' / 'qc.conf'
            options = root / 'var' / 'qc.options.conf'
            database = root / 'var' / 'qc.sqlite'
            pdf_dir = root / 'var' / 'pdf'
            config.parent.mkdir()
            options.parent.mkdir()
            config.write_text('db_path = /unused\npdf_dir = /unused\n')
            options.touch()
            database.touch()
            with patch.object(startup_checks, 'get_config_path', return_value=str(config)), \
                    patch.object(startup_checks, 'get_options_path', return_value=str(options)), \
                    patch.object(startup_checks, 'get_db_path', return_value=str(database)), \
                    patch.object(startup_checks, 'get_pdf_dir', return_value=str(pdf_dir)):
                startup_checks.check_runtime_access()
            self.assertEqual(config.read_text(), 'db_path = /unused\npdf_dir = /unused\n')
            self.assertFalse(list(root.rglob('.qc-access-*')))

    @unittest.skipUnless(os.name == 'posix', 'Gruppi POSIX')
    def test_missing_active_group_shows_instruction_but_member_does_not(self):
        with patch('grp.getgrnam', return_value=SimpleNamespace(gr_gid=12345)), \
                patch.object(startup_checks.os, 'getegid', return_value=123), \
                patch.object(startup_checks.os, 'getgroups', return_value=[]):
            text = startup_checks.permission_error_message(PermissionError('/test'))
            self.assertIn('sudo usermod -aG qc-inspector', text)
            self.assertIn('/test', text)
            with patch.object(startup_checks.os, 'getgroups', return_value=[12345]):
                text = startup_checks.permission_error_message(PermissionError('/test'))
                self.assertNotIn('usermod', text)


class StartupFlowTests(unittest.TestCase):
    def run_startup(self, access_error=None, database_error=None, acquired=True, socket_error=''):
        with ExitStack() as stack:
            stack.enter_context(patch.object(entry, 'QApplication'))
            guard = stack.enter_context(patch.object(entry, 'SingleInstanceGuard'))
            guard.return_value.try_acquire.return_value = acquired
            guard.return_value.last_error = socket_error
            access = stack.enter_context(patch.object(entry, 'check_runtime_access', side_effect=access_error))
            database = stack.enter_context(patch.object(entry, 'initialize_database', side_effect=database_error))
            dialog = stack.enter_context(patch.object(entry.QMessageBox, 'critical'))
            launcher = stack.enter_context(patch.object(entry, 'LauncherWindow'))
            with self.assertRaises(SystemExit) as result:
                entry.main()
            launcher.assert_not_called()
            return result.exception.code, dialog.call_args, access.called, database.called

    def test_permission_failure_blocks_database_and_launcher(self):
        code, dialog, _, db_called = self.run_startup(access_error=PermissionError('/test'))
        self.assertEqual(code, 1)
        self.assertFalse(db_called)
        self.assertIn('Permessi insufficienti', dialog.args[1])

    def test_database_failure_shows_error(self):
        code, dialog, _, _ = self.run_startup(database_error=RuntimeError('Schema non supportato'))
        self.assertEqual(code, 1)
        self.assertIn('Schema non supportato', dialog.args[2])

    def test_existing_instance_exits_successfully_without_checks(self):
        code, dialog, checked, _ = self.run_startup(acquired=False)
        self.assertEqual(code, 0)
        self.assertIsNone(dialog)
        self.assertFalse(checked)

    def test_socket_failure_shows_error(self):
        code, dialog, checked, _ = self.run_startup(acquired=False, socket_error='Access denied')
        self.assertEqual(code, 1)
        self.assertIn('Access denied', dialog.args[2])
        self.assertFalse(checked)
