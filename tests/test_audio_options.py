import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtWidgets import QApplication
from qc_inspector.core import app_config, audio_feedback
from qc_inspector.ui.master_data_window import OptionsTab
from test_audio_feedback import _FakePlayer


class AudioOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'qc.conf'
        self.config_patch = patch.object(app_config, 'get_config_path', return_value=str(self.config))
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        app_config.load_or_create_config()
        _FakePlayer.instances = []

    def options(self):
        return {key: app_config.DEFAULT_CONFIG[key] for key in (
            'label_printer', 'labels_qta', 'label_enable', 'audio_enable',
            'decimal_separator', 'report_footer_text', 'audio_pass_file', 'audio_fail_file')}

    def test_save_paths_and_reject_missing_file_without_changing_config(self):
        audio = self.root / 'custom.wav'
        audio.write_bytes(b'test')
        values = self.options()
        values['audio_pass_file'] = 'custom.wav'
        app_config.save_options(values)
        self.assertEqual(app_config.load_or_create_config()['audio_pass_file'], 'custom.wav')
        before = self.config.read_bytes()
        values['audio_fail_file'] = 'absent.wav'
        with self.assertRaises(ValueError):
            app_config.save_options(values)
        self.assertEqual(self.config.read_bytes(), before)

    def test_system_options_override_only_editable_keys(self):
        options_file = self.root / 'qc.options.conf'
        self.config.write_text(
            'label_printer = Legacy\n'
            'db_path = /var/qc-inspector/original.sqlite\n'
            'pdf_dir = /var/qc-inspector/pdf\n'
        )
        options_file.write_text(
            'label_printer = Reparto QC\n'
            'db_path = /tmp/untrusted.sqlite\n'
        )
        with patch.object(app_config, 'get_options_path', return_value=str(options_file)):
            cfg = app_config.load_or_create_config()
            self.assertEqual(cfg['label_printer'], 'Reparto QC')
            self.assertEqual(cfg['db_path'], '/var/qc-inspector/original.sqlite')
            base_before = self.config.read_bytes()
            values = self.options()
            values['label_printer'] = 'Nuova stampante'
            app_config.save_options(values)
            self.assertEqual(self.config.read_bytes(), base_before)
            self.assertEqual(
                app_config.load_or_create_config()['label_printer'],
                'Nuova stampante',
            )

    def test_save_options_rejects_symlink_without_touching_target(self):
        target = self.root / 'target'
        target.write_text('unchanged')
        options_file = self.root / 'qc.options.conf'
        options_file.symlink_to(target)
        with patch.object(app_config, 'get_options_path', return_value=str(options_file)):
            with self.assertRaisesRegex(OSError, 'non è un file regolare'):
                app_config.save_options(self.options())
        self.assertEqual(target.read_text(), 'unchanged')

    def test_existing_player_uses_changed_options_and_returns_to_default(self):
        audio = self.root / 'custom.wav'
        audio.touch()
        player = audio_feedback.MeasurementSoundPlayer(player_factory=_FakePlayer)
        values = self.options()
        values['audio_pass_file'] = str(audio)
        app_config.save_options(values)
        self.assertTrue(player.play(True))
        self.assertEqual(player._players[True].media_path, str(audio))
        values['audio_pass_file'] = ''
        app_config.save_options(values)
        self.assertTrue(player.play(True))
        self.assertTrue(player._players[True].media_path.endswith('assets/audio/pass.oga'))

    def test_preview_reports_missing_file_and_unavailable_backend(self):
        player = audio_feedback.MeasurementSoundPlayer(player_factory=_FakePlayer)
        errors = []
        player.error_occurred.connect(errors.append)
        self.assertFalse(player.play_file(True, str(self.root / 'absent.wav')))
        self.assertIn('non trovato', errors[-1])
        player._players[True].isAvailable = lambda: False
        self.assertFalse(player.play_file(True))
        self.assertIn('Backend audio Qt', errors[-1])

    def test_options_dirty_save_and_unsaved_preview(self):
        with patch('qc_inspector.ui.master_data_window.MeasurementSoundPlayer') as factory:
            tab = OptionsTab()
            self.addCleanup(tab.deleteLater)
            self.assertFalse(tab.dirty)
            audio = self.root / 'custom.wav'
            audio.touch()
            tab.audio_files['audio_pass_file'].setText(str(audio))
            self.assertTrue(tab.dirty)
            tab._test_audio(True, str(audio))
            factory.return_value.play_file.assert_called_once_with(True, str(audio))
            self.assertEqual(app_config.load_or_create_config()['audio_pass_file'], '')
            self.assertTrue(tab.save())
            self.assertFalse(tab.dirty)
            self.assertEqual(app_config.load_or_create_config()['audio_pass_file'], str(audio))


class ConfigurationPathTests(unittest.TestCase):
    def test_source_install_uses_xdg_config_and_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(
                app_config.os.environ,
                {
                    'XDG_CONFIG_HOME': str(root / 'config'),
                    'XDG_DATA_HOME': str(root / 'data'),
                },
                clear=True,
            ), patch.object(sys, 'frozen', False, create=True):
                config_path = app_config.get_config_path()
                cfg = app_config.load_or_create_config()

            self.assertEqual(
                config_path,
                str(root / 'config' / 'qc-inspector' / 'qc_inspector.conf'),
            )
            self.assertEqual(
                cfg['db_path'],
                str(root / 'data' / 'qc-inspector' / 'qc_database.sqlite'),
            )
            self.assertEqual(
                cfg['pdf_dir'],
                str(root / 'data' / 'qc-inspector' / 'pdf'),
            )
