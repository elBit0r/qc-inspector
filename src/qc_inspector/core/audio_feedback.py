"""Riproduzione asincrona dei segnali audio delle misure."""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable

from PyQt5.QtCore import QObject, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

from .app_config import get_app_root, is_audio_enabled, load_or_create_config, _resolve_config_path


class MeasurementSoundPlayer(QObject):
    """Mantiene precaricati i suoni PASS/FAIL e li riproduce senza bloccare."""

    error_occurred = pyqtSignal(str)
    playback_started = pyqtSignal()

    def __init__(
            self, parent=None, asset_root: str | None = None,
            player_factory: Callable | None = None):
        super().__init__(parent)
        # PyInstaller conserva gli asset nel bundle, non accanto all'eseguibile.
        root = asset_root or (
            sys._MEIPASS if getattr(sys, "frozen", False) else get_app_root()
        )
        self._root = root
        self._factory = player_factory or QMediaPlayer
        self._paths = {}
        self.last_error = ""
        factory = self._factory
        self._players: dict[bool, QMediaPlayer] = {}

        for pass_fail, filename in ((True, "pass.oga"), (False, "error.oga")):
            path = os.path.join(root, "assets", "audio", filename)
            if not os.path.isfile(path):
                continue
            player = factory(self)
            self._connect_player(player)
            player.setVolume(80)
            player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self._players[pass_fail] = player
            self._paths[pass_fail] = path

    def _fail(self, message: str) -> bool:
        self.last_error = message
        logging.getLogger(__name__).warning(message)
        self.error_occurred.emit(message)
        return False

    def _connect_player(self, player):
        if hasattr(player, "error"):
            player.error.connect(lambda code: self._fail(
                "Riproduzione audio non riuscita: " + player.errorString()
            ) if code else None)
            player.stateChanged.connect(
                lambda state: self.playback_started.emit()
                if state == QMediaPlayer.PlayingState else None
            )

    def stop(self):
        for player in self._players.values():
            player.stop()

    def play_file(self, pass_fail: bool, filename: str = "") -> bool:
        """Prova anche file non ancora salvati; vuoto usa il suono incluso."""
        try:
            self.stop()
            self.last_error = ""
            path = (_resolve_config_path(filename) if filename else os.path.join(
                self._root, "assets", "audio", "pass.oga" if pass_fail else "error.oga"
            ))
            if not os.path.isfile(path):
                return self._fail(f"File audio non trovato: {path}")
            with open(path, "rb"):
                pass
            player = self._players.get(pass_fail)
            if player is None:
                player = self._factory(self)
                self._connect_player(player)
                player.setVolume(80)
                self._players[pass_fail] = player
            if hasattr(player, "isAvailable") and not player.isAvailable():
                return self._fail("Backend audio Qt non disponibile. Verifica i plugin "
                                  "Qt Multimedia e GStreamer installati.")
            if self._paths.get(pass_fail) != path:
                player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
                self._paths[pass_fail] = path
            player.setPosition(0)
            player.play()
            return not bool(self.last_error)
        except (RuntimeError, OSError) as exc:
            return self._fail(f"Impossibile riprodurre il file audio: {exc}")

    def play(self, pass_fail: bool) -> bool:
        """Rilegge le preferenze; gli errori audio non interrompono il controllo."""
        try:
            self.stop()
            if not is_audio_enabled():
                return False
            cfg = load_or_create_config()
            key = "audio_pass_file" if pass_fail else "audio_fail_file"
            return self.play_file(bool(pass_fail), cfg.get(key, "").strip())
        except (RuntimeError, OSError) as exc:
            return self._fail(f"Impossibile leggere le opzioni audio: {exc}")
