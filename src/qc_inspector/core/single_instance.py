"""
Single-instance guard for QC Inspector.

Uses a per-user Qt local server so the same system user cannot run multiple
instances, while different users on the same machine remain independent.
"""

import os

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceGuard(QObject):
    """Prevent multiple app instances for the current system user."""

    activation_requested = pyqtSignal()

    def __init__(self, app_id: str, parent: QObject | None = None):
        super().__init__(parent)
        self._server_name = self._build_server_name(app_id)
        self._server: QLocalServer | None = None
        self.last_error = ""

    @property
    def server_name(self) -> str:
        return self._server_name

    def try_acquire(self) -> bool:
        """Return True when this process owns the single-instance server."""
        if self._listen():
            return True

        if self._notify_existing_instance():
            self.last_error = ""
            return False

        # A previous crashed process can leave a stale socket behind.
        QLocalServer.removeServer(self._server_name)
        return self._listen()

    def notify_existing_and_quit(self) -> bool:
        """Notify the already-running instance, if reachable."""
        return self._notify_existing_instance()

    def _listen(self) -> bool:
        self._server = QLocalServer(self)
        if not self._server.listen(self._server_name):
            self.last_error = self._server.errorString()
            self._server.deleteLater()
            self._server = None
            return False

        self.last_error = ""
        self._server.newConnection.connect(self._handle_new_connection)
        return True

    def _handle_new_connection(self):
        if self._server is None:
            return

        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.readyRead.connect(lambda sock=socket: self._handle_message(sock))
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self._handle_message(socket)

    def _handle_message(self, socket: QLocalSocket):
        message = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
        if message == "activate":
            self.activation_requested.emit()

        socket.disconnectFromServer()

    def _notify_existing_instance(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._server_name)
        if not socket.waitForConnected(250):
            socket.abort()
            return False

        socket.write(b"activate")
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True

    @staticmethod
    def _build_server_name(app_id: str) -> str:
        try:
            user_id = os.getuid()
        except AttributeError:
            user_id = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"

        return f"{app_id}-{user_id}"
