import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import qc_inspector
from qc_inspector.core.audio_feedback import MeasurementSoundPlayer
from qc_inspector.ui.inspection_window import InspectionWindow


class _FakePlayer:
    instances = []

    def __init__(self, _parent):
        self.volume = None
        self.media_path = None
        self.position = None
        self.stop_count = 0
        self.play_count = 0
        self.instances.append(self)

    def setVolume(self, volume):
        self.volume = volume

    def setMedia(self, media):
        self.media_path = media.canonicalUrl().toLocalFile()

    def stop(self):
        self.stop_count += 1

    def setPosition(self, position):
        self.position = position

    def play(self):
        self.play_count += 1


class _SoundRecorder:
    def __init__(self):
        self.results = []

    def play(self, pass_fail):
        self.results.append(pass_fail)


class AudioFeedbackTests(unittest.TestCase):
    def setUp(self):
        _FakePlayer.instances = []

    def test_player_loads_and_plays_pass_and_fail_asynchronously(self):
        package_root = str(Path(qc_inspector.__file__).resolve().parent)
        sounds = MeasurementSoundPlayer(
            asset_root=package_root, player_factory=_FakePlayer
        )

        self.assertEqual(len(_FakePlayer.instances), 2)
        self.assertEqual(
            {Path(player.media_path).name for player in _FakePlayer.instances},
            {"pass.oga", "error.oga"},
        )
        with patch('qc_inspector.core.audio_feedback.is_audio_enabled',
                   return_value=True), \
                patch('qc_inspector.core.audio_feedback.load_or_create_config',
                      return_value={'audio_pass_file': '', 'audio_fail_file': ''}):
            self.assertTrue(sounds.play(True))
            self.assertTrue(sounds.play(False))
        self.assertEqual(sum(p.play_count for p in _FakePlayer.instances), 2)
        self.assertTrue(all(p.volume == 80 for p in _FakePlayer.instances))
        self.assertTrue(all(p.position == 0 for p in _FakePlayer.instances))

    def test_missing_audio_files_do_not_interrupt_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            sounds = MeasurementSoundPlayer(
                asset_root=directory, player_factory=_FakePlayer
            )
            with patch('qc_inspector.core.audio_feedback.is_audio_enabled',
                       return_value=True), \
                    patch('qc_inspector.core.audio_feedback.load_or_create_config',
                          return_value={'audio_pass_file': '', 'audio_fail_file': ''}):
                self.assertFalse(sounds.play(True))
                self.assertFalse(sounds.play(False))

    def test_frozen_player_loads_assets_from_bundle_not_executable_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            executable_dir = Path(directory)
            bundle = executable_dir / "_internal"
            audio_dir = bundle / "assets" / "audio"
            audio_dir.mkdir(parents=True)
            for filename in ("pass.oga", "error.oga"):
                (audio_dir / filename).touch()
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "_MEIPASS", str(bundle), create=True), \
                    patch.object(sys, "executable", str(executable_dir / "qc-inspector")):
                sounds = MeasurementSoundPlayer(player_factory=_FakePlayer)

            self.assertEqual(len(_FakePlayer.instances), 2)
            self.assertEqual(
                {Path(player.media_path) for player in _FakePlayer.instances},
                {audio_dir / "pass.oga", audio_dir / "error.oga"},
            )
            self.assertEqual(len(sounds._players), 2)

    def test_development_player_loads_default_project_assets(self):
        with patch.object(sys, "frozen", False, create=True):
            sounds = MeasurementSoundPlayer(player_factory=_FakePlayer)
        audio_dir = Path(qc_inspector.__file__).resolve().parent / "assets" / "audio"
        self.assertEqual(
            {Path(player.media_path) for player in _FakePlayer.instances},
            {audio_dir / "pass.oga", audio_dir / "error.oga"},
        )
        self.assertEqual(len(sounds._players), 2)

    def test_storing_measurement_triggers_matching_sound(self):
        sound = _SoundRecorder()
        window = SimpleNamespace(
            _draft_measurements={}, _measurement_sound=sound
        )

        InspectionWindow._store_draft_measurement(
            window, 1, 10, 12.5, None, True
        )
        InspectionWindow._store_draft_measurement(
            window, 2, 10, 13.0, None, False
        )

        self.assertEqual(sound.results, [True, False])
        self.assertTrue(window._draft_measurements[(10, 1)]["pass_fail"])
        self.assertFalse(window._draft_measurements[(10, 2)]["pass_fail"])


if __name__ == "__main__":
    unittest.main()
