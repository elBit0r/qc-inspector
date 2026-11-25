"""Scheda Configurazione per la creazione e il ripristino dei backup."""

from pathlib import Path

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..core.app_config import get_db_path, get_pdf_dir, load_or_create_config, save_options
from ..core.backup import RestoreCancelled, create_backup, restore_backup


class BackupTab(QWidget):
    restored = pyqtSignal()

    def __init__(self, can_restore, parent=None):
        super().__init__(parent)
        self._can_restore = can_restore

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Cartella di destinazione del backup"))
        location = QHBoxLayout()
        self.destination = QLineEdit(load_or_create_config()["backup_dir"])
        self.destination.setReadOnly(True)
        self.destination.setPlaceholderText("Scegli una cartella")
        browse = QPushButton("Sfoglia…")
        browse.clicked.connect(self._choose_destination)
        location.addWidget(self.destination, 1)
        location.addWidget(browse)
        layout.addLayout(location)

        actions = QHBoxLayout()
        backup = QPushButton("Esegui backup")
        backup.clicked.connect(self._create)
        restore = QPushButton("Ripristina backup…")
        restore.clicked.connect(self._restore)
        actions.addWidget(backup)
        actions.addWidget(restore)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()

    def _choose_destination(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Cartella di destinazione del backup", self.destination.text()
        )
        if not directory:
            return
        try:
            save_options({"backup_dir": directory})
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Cartella di backup", str(exc))
            return
        self.destination.setText(directory)

    def _get_destination(self) -> Path | None:
        if not self.destination.text():
            self._choose_destination()
        if self.destination.text():
            return Path(self.destination.text()).expanduser()
        return None

    def _create(self):
        destination = self._get_destination()
        if destination is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            archive = create_backup(destination, Path(get_db_path()), Path(get_pdf_dir()))
        except Exception as exc:
            error = str(exc)
        else:
            error = None
        finally:
            QApplication.restoreOverrideCursor()
        if error is None:
            QMessageBox.information(self, "Backup creato", f"Archivio salvato in\n{archive}")
        else:
            QMessageBox.critical(self, "Errore di backup", error)

    def _resolve_conflict(self, name: str) -> tuple[str, str] | None:
        QApplication.restoreOverrideCursor()
        try:
            dialog = QMessageBox(QMessageBox.Question, "Setup duplicato",
                                 f"Il setup «{name}» esiste già.", parent=self)
            dialog.setTextFormat(Qt.PlainText)
            dialog.setInformativeText(
                "Sostituendo il setup verranno sostituiti anche i lotti "
                "e le misurazioni locali associati."
            )
            replace = dialog.addButton("Sostituisci", QMessageBox.DestructiveRole)
            rename = dialog.addButton("Rinomina", QMessageBox.ActionRole)
            cancel = dialog.addButton(QMessageBox.Cancel)
            dialog.setDefaultButton(cancel)
            dialog.exec_()
            if dialog.clickedButton() is replace:
                return "replace", ""
            if dialog.clickedButton() is rename:
                new_name, ok = QInputDialog.getText(
                    self, "Rinomina setup", "Nome univoco per il setup importato",
                    text=f"{name} (backup)",
                )
                if ok:
                    return "rename", new_name
            return None
        finally:
            QApplication.setOverrideCursor(Qt.WaitCursor)

    def _restore(self):
        if not self._can_restore():
            return
        archive, _ = QFileDialog.getOpenFileName(
            self, "Apri un backup", self.destination.text(), "Archivi di backup (*.zip)"
        )
        if not archive:
            return
        dialog = QMessageBox(QMessageBox.Question, "Ripristina backup",
                             "Scegli come ripristinare i dati.", parent=self)
        merge = dialog.addButton("Aggiungi ai dati esistenti", QMessageBox.ActionRole)
        complete = dialog.addButton("Ripristino completo", QMessageBox.DestructiveRole)
        cancel = dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(cancel)
        dialog.exec_()
        selected = dialog.clickedButton()
        options = {}
        if selected is merge:
            options["resolve_conflict"] = self._resolve_conflict
        elif selected is complete:
            if QMessageBox.question(
                self, "Conferma ripristino completo",
                "Il ripristino completo sostituirà database e PDF locali. "
                "Verrà creato un backup dei dati correnti. Assicurati che "
                "nessun altro utente stia usando questi dati. Continuare?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            destination = self._get_destination()
            if destination is None:
                return
            options["safety_destination"] = destination
        else:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            safety = restore_backup(
                Path(archive), Path(get_db_path()), Path(get_pdf_dir()), **options
            )
        except RestoreCancelled:
            return
        except Exception as exc:
            error = str(exc)
        else:
            error = None
        finally:
            QApplication.restoreOverrideCursor()
        if error is not None:
            QMessageBox.critical(self, "Errore di ripristino", error)
            return
        self.restored.emit()
        message = "Ripristino completato."
        if safety:
            message += f"\nCopia di sicurezza salvata in\n{safety}"
        QMessageBox.information(self, "Ripristino completato", message)
