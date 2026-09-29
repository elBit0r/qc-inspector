"""
programming_window.py
Finestra di programmazione: carica PDF, posiziona balloon, definisce controlli.
"""

import hashlib
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QTextEdit, QGroupBox, QFormLayout, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QSpinBox, QTabWidget,
    QToolBar, QAction, QSizePolicy, QFrame, QStyle, QDialog,
    QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QShortcut,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QEvent
from PyQt5.QtGui import QIcon, QFont, QColor, QKeySequence

from ..ui.pdf_viewer import PdfViewerWidget
from ..ui.decimal_spinbox import DecimalSpinBox
from ..database import db_manager as db
from ..core.inspection_engine import format_tolerance
from ..core.app_config import get_pdf_dir


class TimestampTableWidgetItem(QTableWidgetItem):
    """Data mostrata in formato italiano e ordinata tramite valore ISO."""

    def __init__(self, text: str, sort_value: str):
        super().__init__(text)
        self._sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, TimestampTableWidgetItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


class SetupOpenDialog(QDialog):
    """Selezione ricercabile di un setup salvato."""

    def __init__(self, setups: list[dict], parent=None,
                 current_setup_id: int | None = None):
        super().__init__(parent)
        self._setups = setups
        self._current_setup_id = current_setup_id
        self.selected_setup_id: int | None = None
        self.create_new_setup = False
        self.deleted_setup_ids: set[int] = set()
        self.setWindowTitle("Gestione setup")
        self.resize(900, 560)
        self.setMinimumSize(720, 460)
        self._build_ui()
        self._populate_table(setups)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        self.setStyleSheet("""
            QDialog { background:#f4f6f8; }
            QFrame#setupHeader {
                background:#1f4e78; border-radius:8px;
            }
            QFrame#searchCard {
                background:white; border:1px solid #d8dee5;
                border-radius:7px;
            }
            QLineEdit {
                min-height:30px; background:white; border:1px solid #b7c1cb;
                border-radius:4px; padding:0 9px;
            }
            QLineEdit:focus { border:2px solid #2f75b5; }
            QTableWidget {
                background:white; alternate-background-color:#f6f8fa;
                border:1px solid #d8dee5; border-radius:6px;
                selection-background-color:#dcecf8;
                selection-color:#173c5e;
            }
            QHeaderView::section {
                background:#e9edf2; color:#2f3b48; border:none;
                border-right:1px solid #d4dbe2; border-bottom:1px solid #c9d2db;
                padding:8px; font-weight:bold;
            }
            QLabel#resultCount {
                color:#5f6f7d; background:#eef2f5; border:1px solid #d8dee5;
                border-radius:10px; padding:3px 10px;
            }
            QPushButton {
                min-height:30px; padding:2px 14px; border:1px solid #b7c1cb;
                border-radius:4px; background:#f8fafb; color:#263746;
            }
            QPushButton:hover { background:#edf2f6; border-color:#8496a6; }
            QPushButton[role="primary"] {
                color:white; background:#2f75b5; border-color:#28669d;
                font-weight:bold;
            }
            QPushButton[role="primary"]:hover { background:#28689f; }
            QPushButton[role="danger"] {
                color:#8b1a1a; background:#fff5f5; border-color:#d8a0a0;
            }
            QPushButton[role="danger"]:hover { background:#fde8e8; }
            QPushButton:disabled { color:#9aa5ae; background:#edf0f2; }
        """)

        header = QFrame()
        header.setObjectName("setupHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Gestione setup")
        title.setStyleSheet("color:white; font-size:17px; font-weight:bold;")
        intro = QLabel(
            "Cerca e apri un setup esistente oppure avvia una nuova "
            "programmazione."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#e6eef5; font-size:10pt;")
        header_layout.addWidget(title)
        header_layout.addWidget(intro)
        layout.addWidget(header)

        search_card = QFrame()
        search_card.setObjectName("searchCard")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(12, 10, 12, 10)
        search_layout.setSpacing(10)
        search_label = QLabel("<b>Cerca per codice:</b>")
        search_layout.addWidget(search_label)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Digita il nome del setup…")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.textChanged.connect(self._filter_table)
        search_layout.addWidget(self.txt_search)
        layout.addWidget(search_card)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Codice", "Descrizione", "Classe di Collaudo", "Ultima modifica"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_open_button)
        self.table.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.table)

        self.lbl_result_count = QLabel()
        self.lbl_result_count.setObjectName("resultCount")
        count_layout = QHBoxLayout()
        count_layout.addStretch()
        count_layout.addWidget(self.lbl_result_count)
        layout.addLayout(count_layout)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Open | QDialogButtonBox.Cancel
        )
        self.btn_open = self.buttons.button(QDialogButtonBox.Open)
        self.btn_open.setText("Apri")
        self.btn_open.setIcon(
            self.style().standardIcon(QStyle.SP_DialogOpenButton)
        )
        self.btn_open.setProperty("role", "primary")
        self.btn_open.setEnabled(False)
        self.btn_new = self.buttons.addButton(
            "Nuovo setup", QDialogButtonBox.ActionRole
        )
        self.btn_new.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.btn_new.clicked.connect(self._create_new)
        self.btn_delete = self.buttons.addButton(
            "Elimina setup", QDialogButtonBox.ActionRole
        )
        self.btn_delete.setProperty("role", "danger")
        self.btn_delete.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_selected)
        cancel_button = self.buttons.button(QDialogButtonBox.Cancel)
        cancel_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogCancelButton)
        )
        self.buttons.accepted.connect(self._open_selected)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.txt_search.setFocus()

    def _populate_table(self, setups: list[dict]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for setup in setups:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(setup.get("name") or "")
            name_item.setData(Qt.UserRole, setup["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(
                row, 1, QTableWidgetItem(setup.get("description") or "—")
            )
            self.table.setItem(
                row, 2,
                QTableWidgetItem(setup.get("sampling_class_code") or "—"),
            )
            updated_at = setup.get("updated_at") or ""
            self.table.setItem(row, 3, TimestampTableWidgetItem(
                self._format_timestamp(updated_at), updated_at
            ))

        self.table.setSortingEnabled(True)
        self.lbl_result_count.setText(f"{len(setups)} setup trovati")
        if setups:
            self.table.selectRow(0)

    @staticmethod
    def _format_timestamp(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value

    def _filter_table(self, text: str):
        search = text.strip().casefold()
        visible_rows = 0
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            matches = search in name_item.text().casefold()
            self.table.setRowHidden(row, not matches)
            if matches:
                visible_rows += 1

        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                self.table.selectRow(row)
                break
        self.lbl_result_count.setText(f"{visible_rows} setup trovati")
        self._update_open_button()

    def _update_open_button(self):
        has_selection = bool(self.table.selectedItems())
        self.btn_open.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)

    def _delete_selected(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        name_item = self.table.item(row, 0)
        setup_id = name_item.data(Qt.UserRole)
        setup_name = name_item.text()
        try:
            lots = db.get_lots_for_setup(setup_id)
            controls = db.get_controls_for_setup(setup_id)
        except Exception as exc:
            QMessageBox.critical(
                self, "Errore eliminazione",
                f"Impossibile verificare il setup.\n\nDettaglio: {exc}",
            )
            return
        if lots:
            QMessageBox.warning(
                self,
                "Eliminazione non consentita",
                "Il setup è collegato a controlli salvati nello storico e "
                "non può essere eliminato.\n\n"
                "Puoi modificarlo: i controlli già salvati continueranno a "
                "usare la propria revisione immutabile.",
            )
            return

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Elimina setup")
        dialog.setText(f"Eliminare definitivamente il setup '{setup_name}'?")
        details = f"Saranno eliminati {len(controls)} controlli configurati."
        if setup_id == self._current_setup_id:
            details += " Il setup è attualmente aperto in Programmazione."
        dialog.setInformativeText(details)
        delete_button = dialog.addButton(
            "Elimina definitivamente", QMessageBox.DestructiveRole
        )
        delete_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        cancel_button = dialog.addButton(QMessageBox.Cancel)
        cancel_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogCancelButton)
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec_()
        if dialog.clickedButton() is not delete_button:
            return
        try:
            db.delete_setup(setup_id)
        except Exception as exc:
            QMessageBox.critical(
                self, "Errore eliminazione",
                f"Il setup non è stato eliminato.\n\nDettaglio: {exc}",
            )
            return

        self.deleted_setup_ids.add(setup_id)
        self._setups = db.get_all_setups()
        self._populate_table(self._setups)
        self._filter_table(self.txt_search.text())
        QMessageBox.information(
            self, "Setup eliminato", f"Il setup '{setup_name}' è stato eliminato."
        )

    def _open_selected(self, *_args):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        self.selected_setup_id = self.table.item(row, 0).data(Qt.UserRole)
        self.accept()

    def _create_new(self):
        self.selected_setup_id = None
        self.create_new_setup = True
        self.accept()


class ControlFormWidget(QGroupBox):
    """Form per definire un singolo controllo."""

    dirty_changed = pyqtSignal(bool)
    apply_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Definizione controllo", parent)
        self._control_id: int | None = None
        self._setup_id: int | None = None
        self._balloon_num: int = 0
        self._balloon_x: float = 0
        self._balloon_y: float = 0
        self._pdf_page: int = 0
        self._locked_control_type: str | None = None
        self._saved_control_state = None
        self._control_dirty = False
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout()
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.lbl_balloon = QLabel("—")
        self.lbl_balloon.setObjectName("balloonNumber")
        self.lbl_balloon.setFont(QFont("Arial", 11, QFont.Bold))
        layout.addRow("Balloon n°:", self.lbl_balloon)

        self.cmb_type = QComboBox()
        self.cmb_type.addItem("Dimensionale", "dimensional")
        self.cmb_type.addItem("Sì / No", "yesno")
        self.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        layout.addRow("Tipo:", self.cmb_type)

        self.cmb_criticality = QComboBox()
        self.cmb_criticality.addItem("C — CRITICA", "C")
        self.cmb_criticality.addItem("I — IMPORTANTE", "I")
        self.cmb_criticality.addItem("N — NORMALE", "N")
        criticality_colors = {
            "C": (QColor("#f8d7da"), QColor("#842029")),
            "I": (QColor("#fff3cd"), QColor("#664d03")),
            "N": (QColor("#d1e7dd"), QColor("#0f5132")),
        }
        for index in range(self.cmb_criticality.count()):
            background, foreground = criticality_colors[
                self.cmb_criticality.itemData(index)
            ]
            self.cmb_criticality.setItemData(
                index, background, Qt.BackgroundRole
            )
            self.cmb_criticality.setItemData(
                index, foreground, Qt.ForegroundRole
            )
        self.cmb_criticality.currentIndexChanged.connect(
            self._update_criticality_style
        )
        self.cmb_criticality.setCurrentIndex(2)
        self._update_criticality_style()
        layout.addRow("Criticità:", self.cmb_criticality)

        self.txt_label = QLineEdit()
        self.txt_label.setPlaceholderText("es. Diametro foro Ø25")
        layout.addRow("Descrizione:", self.txt_label)

        # Sezione dimensionale
        self.grp_dim = QGroupBox("Quota")
        self.grp_dim.setObjectName("quotaGroup")
        dim_layout = QFormLayout()
        dim_layout.setContentsMargins(12, 16, 12, 12)
        dim_layout.setHorizontalSpacing(12)
        dim_layout.setVerticalSpacing(8)
        dim_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.spn_nominal = DecimalSpinBox()
        self.spn_nominal.setRange(-9999, 9999)
        self.spn_nominal.setDecimals(3)
        self.spn_nominal.setSuffix(" mm")
        dim_layout.addRow("Nominale:", self.spn_nominal)

        self.spn_tol_plus = DecimalSpinBox()
        self.spn_tol_plus.setRange(0, 99)
        self.spn_tol_plus.setDecimals(3)
        self.spn_tol_plus.setValue(0.05)
        self.spn_tol_plus.setSuffix(" mm")
        dim_layout.addRow("Tolleranza +:", self.spn_tol_plus)

        self.spn_tol_minus = DecimalSpinBox()
        self.spn_tol_minus.setRange(0, 99)
        self.spn_tol_minus.setDecimals(3)
        self.spn_tol_minus.setValue(0.05)
        self.spn_tol_minus.setSuffix(" mm")
        dim_layout.addRow("Tolleranza −:", self.spn_tol_minus)

        self.grp_dim.setLayout(dim_layout)
        layout.addRow(self.grp_dim)

        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Note aggiuntive (opzionale)")
        self.txt_notes.setMaximumHeight(60)
        layout.addRow("Note:", self.txt_notes)

        self.btn_save = QPushButton("Applica controllo")
        self.btn_save.setIcon(
            self.style().standardIcon(QStyle.SP_DialogApplyButton)
        )
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setStyleSheet(
            "QPushButton { background:#1a7abf; color:white; padding:6px 12px; "
            "border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:#1560a0; }"
        )
        self.btn_save.clicked.connect(self.apply_requested.emit)
        layout.addRow(self.btn_save)

        self.setLayout(layout)
        self._on_type_changed(0)

        self.cmb_type.currentIndexChanged.connect(self._update_dirty_state)
        self.cmb_criticality.currentIndexChanged.connect(
            self._update_dirty_state
        )
        self.txt_label.textChanged.connect(self._update_dirty_state)
        self.spn_nominal.valueChanged.connect(self._update_dirty_state)
        self.spn_tol_plus.valueChanged.connect(self._update_dirty_state)
        self.spn_tol_minus.valueChanged.connect(self._update_dirty_state)
        self.txt_notes.textChanged.connect(self._update_dirty_state)

    @property
    def control_id(self) -> int | None:
        return self._control_id

    @property
    def balloon_num(self) -> int:
        return self._balloon_num

    @property
    def is_dirty(self) -> bool:
        return self._control_dirty

    def _current_control_state(self):
        ctrl_type = self._locked_control_type or self.cmb_type.currentData()
        nominal = tol_plus = tol_minus = None
        if ctrl_type == "dimensional":
            nominal = self.spn_nominal.value()
            tol_plus = self.spn_tol_plus.value()
            tol_minus = self.spn_tol_minus.value()
        return (
            self._balloon_num,
            ctrl_type,
            self.cmb_criticality.currentData(),
            self.txt_label.text().strip(),
            nominal,
            tol_plus,
            tol_minus,
            self.txt_notes.toPlainText().strip(),
        )

    def _update_dirty_state(self, *_args):
        dirty = (
            self._balloon_num != 0
            and self._current_control_state() != self._saved_control_state
        )
        if dirty != self._control_dirty:
            self._control_dirty = dirty
            self.dirty_changed.emit(dirty)

    def _mark_control_saved(self):
        self._saved_control_state = self._current_control_state()
        self._update_dirty_state()

    def reset_form(self):
        """Azzera selezione e stato modifiche del controllo corrente."""
        self._control_id = None
        self._setup_id = None
        self._balloon_num = 0
        self._balloon_x = 0
        self._balloon_y = 0
        self._pdf_page = 0
        self._locked_control_type = None
        self.lbl_balloon.setText("—")
        self.cmb_type.setEnabled(True)
        self.cmb_type.setCurrentIndex(0)
        self.cmb_criticality.setCurrentIndex(2)
        self.txt_label.clear()
        self.spn_nominal.setValue(0)
        self.spn_tol_plus.setValue(0.05)
        self.spn_tol_minus.setValue(0.05)
        self.txt_notes.clear()
        self._mark_control_saved()

    def _on_type_changed(self, index):
        is_dim = (self.cmb_type.currentData() == "dimensional")
        self.grp_dim.setVisible(is_dim)

    def _update_criticality_style(self, _index: int = -1):
        """Colora il selettore in base alla criticità corrente."""
        colors = {
            "C": ("#f8d7da", "#842029", "#dc3545"),
            "I": ("#fff3cd", "#664d03", "#e0a800"),
            "N": ("#d1e7dd", "#0f5132", "#198754"),
        }
        background, foreground, border = colors.get(
            self.cmb_criticality.currentData(), colors["N"]
        )
        self.cmb_criticality.setStyleSheet(
            "QComboBox {"
            f"background:{background}; color:{foreground}; "
            f"border:2px solid {border}; font-weight:bold;"
            "}"
            "QComboBox QAbstractItemView {"
            "background:white; selection-background-color:#dcecf8; "
            "selection-color:#173c5e; font-weight:bold;"
            "}"
        )

    def load_control(self, control: dict):
        """Popola il form con un controllo del modello di lavoro."""
        self._control_id = control["id"]
        self._balloon_num = control["balloon_num"]
        self._balloon_x = control["balloon_x"]
        self._balloon_y = control["balloon_y"]
        self._pdf_page = control.get("pdf_page", 0)

        self.lbl_balloon.setText(str(control["balloon_num"]))
        idx = 0 if control["control_type"] == "dimensional" else 1
        self.cmb_type.setCurrentIndex(idx)
        persisted = int(control["id"]) > 0
        self._locked_control_type = control["control_type"] if persisted else None
        self.cmb_type.setEnabled(not persisted)

        criticality = control.get("criticality", "N")
        criticality_index = self.cmb_criticality.findData(criticality)
        self.cmb_criticality.setCurrentIndex(
            criticality_index if criticality_index >= 0 else 2
        )

        self.txt_label.setText(control.get("label") or "")
        if control["control_type"] == "dimensional":
            nominal = control.get("nominal")
            tol_plus = control.get("tol_plus")
            tol_minus = control.get("tol_minus")
            self.spn_nominal.setValue(0 if nominal is None else nominal)
            self.spn_tol_plus.setValue(0.05 if tol_plus is None else tol_plus)
            self.spn_tol_minus.setValue(0.05 if tol_minus is None else tol_minus)
        self.txt_notes.setPlainText(control.get("description") or "")
        self._mark_control_saved()

    def set_new_balloon(self, setup_id: int | None, control_id: int,
                        balloon_num: int, x: float, y: float, page: int):
        """Prepara il form per un nuovo balloon."""
        self._control_id = control_id
        self._setup_id = setup_id
        self._balloon_num = balloon_num
        self._balloon_x = x
        self._balloon_y = y
        self._pdf_page = page

        self.lbl_balloon.setText(str(balloon_num))
        self.cmb_type.setCurrentIndex(0)
        self._locked_control_type = None
        self.cmb_type.setEnabled(True)
        self.cmb_criticality.setCurrentIndex(2)
        self.txt_label.clear()
        self.spn_nominal.setValue(0)
        self.spn_tol_plus.setValue(0.05)
        self.spn_tol_minus.setValue(0.05)
        self.txt_notes.clear()
        self._saved_control_state = None
        self._update_dirty_state()

    def control_payload(self) -> dict | None:
        """Restituisce i dati correnti pronti per il salvataggio transazionale."""
        if self._balloon_num == 0:
            return None
        ctrl_type = self._locked_control_type or self.cmb_type.currentData()
        label = self.txt_label.text().strip()
        notes = self.txt_notes.toPlainText().strip()
        nominal = tol_plus = tol_minus = None
        if ctrl_type == "dimensional":
            nominal   = self.spn_nominal.value()
            tol_plus  = self.spn_tol_plus.value()
            tol_minus = self.spn_tol_minus.value()
        return {
            "id": self._control_id,
            "balloon_num": self._balloon_num,
            "balloon_x": self._balloon_x,
            "balloon_y": self._balloon_y,
            "pdf_page": self._pdf_page,
            "control_type": ctrl_type,
            "criticality": self.cmb_criticality.currentData(),
            "label": label,
            "nominal": nominal,
            "tol_plus": tol_plus,
            "tol_minus": tol_minus,
            "description": notes,
        }

    def mark_applied(self):
        """Marca i valori correnti come applicati al modello in memoria."""
        self._mark_control_saved()

    def set_balloon_position(
            self, control_id: int, x: float, y: float, page: int):
        """Aggiorna le coordinate senza alterare i valori del form."""
        if self._control_id != control_id:
            return
        self._balloon_x = x
        self._balloon_y = y
        self._pdf_page = page


class ControlListWidget(QGroupBox):
    """Lista dei controlli configurati per il setup corrente."""

    control_selected = pyqtSignal(int)  # control_id
    control_delete_requested = pyqtSignal(int)
    control_move_requested = pyqtSignal(int, int)  # control_id, direzione

    def __init__(self, parent=None):
        super().__init__("Controlli configurati", parent)
        self._controls: list = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(10)
        self.lst = QListWidget()
        self.lst.setAlternatingRowColors(True)
        self.lst.setSpacing(2)
        self.lst.itemClicked.connect(self._on_item_clicked)
        self.lst.currentRowChanged.connect(self._update_move_buttons)
        layout.addWidget(self.lst)

        btn_row = QHBoxLayout()
        self.btn_up = QPushButton("Sposta su")
        self.btn_up.setMinimumHeight(32)
        self.btn_up.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        self.btn_up.clicked.connect(lambda: self._on_move(-1))
        btn_row.addWidget(self.btn_up)

        self.btn_down = QPushButton("Sposta giù")
        self.btn_down.setMinimumHeight(32)
        self.btn_down.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.btn_down.clicked.connect(lambda: self._on_move(1))
        btn_row.addWidget(self.btn_down)

        btn_row.addStretch()
        self.btn_del = QPushButton("Elimina selezionato")
        self.btn_del.setMinimumHeight(32)
        self.btn_del.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_del.setStyleSheet("QPushButton { color:#c00; }")
        self.btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_del)
        layout.addLayout(btn_row)

        self.setLayout(layout)
        self._update_move_buttons()

    def set_controls(self, controls: list[dict]):
        self._controls = [dict(control) for control in controls]
        self.lst.clear()
        for c in self._controls:
            type_icon = "📏" if c["control_type"] == "dimensional" else "✓"
            criticality = c.get("criticality", "N")
            if c["control_type"] == "dimensional":
                if c["nominal"] is None or c["tol_plus"] is None or c["tol_minus"] is None:
                    detail = "  Quota incompleta"
                else:
                    detail = f"  {format_tolerance(c['nominal'], c['tol_plus'], c['tol_minus'])}"
            else:
                detail = "  Sì/No"
            label = c.get("label") or "(senza etichetta)"
            text = (
                f"[{c['balloon_num']}] [{criticality}] "
                f"{type_icon} {label}{detail}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, c["id"])
            self.lst.addItem(item)
        self._update_move_buttons()

    def select_control(self, control_id: int | None):
        self.lst.clearSelection()
        if control_id is None:
            return
        for index in range(self.lst.count()):
            item = self.lst.item(index)
            if item.data(Qt.UserRole) == control_id:
                self.lst.setCurrentItem(item)
                return

    def _on_item_clicked(self, item: QListWidgetItem):
        ctrl_id = item.data(Qt.UserRole)
        self.control_selected.emit(ctrl_id)

    def _on_delete(self):
        item = self.lst.currentItem()
        if not item:
            return
        ctrl_id = item.data(Qt.UserRole)
        self.control_delete_requested.emit(ctrl_id)

    def _on_move(self, direction: int):
        item = self.lst.currentItem()
        if item is None or direction not in {-1, 1}:
            return
        self.control_move_requested.emit(item.data(Qt.UserRole), direction)

    def _update_move_buttons(self, _row: int = -1):
        row = self.lst.currentRow()
        self.btn_up.setEnabled(row > 0)
        self.btn_down.setEnabled(0 <= row < self.lst.count() - 1)


class ProgrammingWindow(QMainWindow):
    """Finestra principale della modalità programmazione."""

    setup_saved = pyqtSignal(int)  # setup_id

    def __init__(self, parent=None, setup_id: int | None = None):
        super().__init__(parent)
        self._setup_id: int | None = None
        self._pdf_path: str | None = None
        self._saved_setup_state = ("", "", None, None)
        self._working_controls: list[dict] = []
        self._saved_controls_state = ()
        self._setup_fields_dirty = False
        self._control_dirty = False
        self._pending_control_deletions: set[int] = set()
        self._next_temp_control_id = -1
        self._setup_dirty = False
        self.setWindowTitle("QC Inspector — Programmazione")
        self.setFont(QFont("Arial", 11))
        self.resize(1280, 800)
        self._build_ui()
        if setup_id:
            self._load_existing_setup(setup_id)

    # ─── Build UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("programmingRoot")
        central.setStyleSheet("""
            QWidget#programmingRoot { background:#e9edf2; }
            QWidget#programmingRightPanel { background:#f4f6f8; }
            QSplitter::handle { background:#c9d2db; width:6px; }
            QSplitter::handle:hover { background:#8eabc3; }
            QGroupBox {
                background:white; border:1px solid #d8dee5;
                border-radius:7px; margin-top:10px;
                color:#24445f; font-weight:bold;
            }
            QGroupBox::title {
                subcontrol-origin:margin; left:12px; padding:0 5px;
            }
            QGroupBox#quotaGroup {
                background:#f7f9fb; border-color:#dce3e9;
                color:#4b5f70;
            }
            QLineEdit, QComboBox, QTextEdit, QAbstractSpinBox {
                min-height:30px; background:white; color:#263746;
                border:1px solid #b7c1cb; border-radius:4px;
                padding:0 8px; font-weight:normal;
            }
            QTextEdit { padding:6px 8px; }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus,
            QAbstractSpinBox:focus { border:2px solid #2f75b5; }
            QLabel#balloonNumber {
                color:#1f4e78; background:#e8f1f8;
                border:1px solid #bdd2e3; border-radius:12px;
                min-width:26px; min-height:26px; qproperty-alignment:AlignCenter;
            }
            QListWidget {
                background:white; alternate-background-color:#f6f8fa;
                border:1px solid #d8dee5; border-radius:5px;
                padding:4px; font-weight:normal;
            }
            QListWidget::item { min-height:30px; padding:3px 6px; }
            QListWidget::item:selected {
                background:#dcecf8; color:#173c5e; border-radius:3px;
            }
        """)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        self._build_toolbar()

        # Setup info bar
        info_bar = self._build_info_bar()
        main_layout.addWidget(info_bar)

        # Splitter principale
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)

        # PDF viewer
        self.viewer = PdfViewerWidget()
        self.viewer.edit_mode = True
        self.viewer.balloon_added.connect(self._on_balloon_added)
        self.viewer.balloon_clicked.connect(self._on_balloon_clicked)
        self.viewer.balloon_deleted.connect(self._on_balloon_deleted)
        self.viewer.balloon_moved.connect(self._on_balloon_moved)
        splitter.addWidget(self.viewer)

        # Pannello destra
        right_panel = QWidget()
        right_panel.setObjectName("programmingRightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 10, 12, 12)
        right_layout.setSpacing(10)

        self.ctrl_form = ControlFormWidget()
        self.ctrl_form.dirty_changed.connect(self._on_control_dirty_changed)
        self.ctrl_form.apply_requested.connect(self._on_apply_control)
        right_layout.addWidget(self.ctrl_form, 0)

        self.ctrl_list = ControlListWidget()
        self.ctrl_list.control_selected.connect(self._on_control_selected_from_list)
        self.ctrl_list.control_delete_requested.connect(self._on_balloon_deleted)
        self.ctrl_list.control_move_requested.connect(
            self._on_control_move_requested
        )
        right_layout.addWidget(self.ctrl_list, 1)

        controls_minimum_width = 470
        right_panel.setMinimumWidth(controls_minimum_width)
        splitter.addWidget(right_panel)
        # Il pannello controlli parte dalla sua larghezza minima; ogni spazio
        # aggiuntivo della finestra viene assegnato al disegno. Lo splitter
        # resta trascinabile per allargare manualmente il pannello destro.
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([
            max(1, self.width() - controls_minimum_width - splitter.handleWidth()),
            controls_minimum_width,
        ])

        main_layout.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Pronto — Carica un PDF per iniziare")

    def _build_toolbar(self):
        tb = QToolBar("Principale")
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.setStyleSheet("""
            QToolBar { background:white; border-bottom:1px solid #d8dee5; spacing:5px; padding:4px 8px; }
            QToolButton { min-height:30px; padding:2px 7px; }
        """)
        self.addToolBar(tb)
        style = self.style()

        act_new = QAction(style.standardIcon(QStyle.SP_FileIcon), "Nuovo setup", self)
        act_new.triggered.connect(self._on_new_setup)
        tb.addAction(act_new)

        act_open = QAction(style.standardIcon(QStyle.SP_DialogOpenButton), "Gestione setup", self)
        act_open.triggered.connect(self._on_open_setup)
        tb.addAction(act_open)

        self.act_save = QAction(
            style.standardIcon(QStyle.SP_DialogSaveButton), "Salva setup", self
        )
        self.act_save.setEnabled(False)
        self.act_save.triggered.connect(self._on_save_setup)
        tb.addAction(self.act_save)

        tb.addSeparator()

        act_pdf = QAction(style.standardIcon(QStyle.SP_DriveFDIcon), "Carica PDF", self)
        act_pdf.triggered.connect(self._on_load_pdf)
        tb.addAction(act_pdf)

        tb.addSeparator()

        lbl_help = QLabel(
            "  Clic: aggiungi/seleziona  ·  Trascina: sposta  ·  "
            "Tasto destro: elimina  ·  Rotella: zoom  ·  Tasto centrale: pan"
        )
        lbl_help.setStyleSheet("color:#627384; font-size:9pt; padding-left:6px;")
        tb.addWidget(lbl_help)

        tb.addSeparator()
        self.act_fullscreen = QAction(self)
        self.act_fullscreen.setShortcut(QKeySequence("F11"))
        self.act_fullscreen.triggered.connect(self._toggle_fullscreen)
        tb.addAction(self.act_fullscreen)

        self._fullscreen_escape_shortcut = QShortcut(
            QKeySequence(Qt.Key_Escape), self
        )
        self._fullscreen_escape_shortcut.activated.connect(
            self._exit_fullscreen
        )
        self._update_fullscreen_control()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()
        self._update_fullscreen_control()

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
            self._update_fullscreen_control()

    def _update_fullscreen_control(self):
        if not hasattr(self, "act_fullscreen"):
            return
        fullscreen = self.isFullScreen()
        text = "Esci da schermo intero" if fullscreen else "Schermo intero"
        icon = (
            QStyle.SP_TitleBarNormalButton
            if fullscreen else QStyle.SP_TitleBarMaxButton
        )
        self.act_fullscreen.setText(text)
        self.act_fullscreen.setIcon(self.style().standardIcon(icon))
        self.act_fullscreen.setToolTip(f"{text} (F11)")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._update_fullscreen_control()

    def _build_info_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("programmingHeader")
        bar.setFixedHeight(112)
        bar.setStyleSheet("""
            QFrame#programmingHeader {
                background:#1f4e78; border:none; border-bottom:1px solid #173b5c;
            }
            QLabel#programmingTitle { color:white; font-size:13pt; font-weight:bold; }
            QLabel#fieldLabel { color:#dce8f2; font-size:9pt; font-weight:bold; }
            QLabel#pdfPath { color:#d9e5ef; font-style:italic; }
            QLabel#pageLabel { color:white; font-weight:bold; }
            QLineEdit, QComboBox {
                min-height:30px; background:white; border:1px solid #b8c9d8;
                border-radius:4px; padding:0 8px; color:#263746;
            }
            QPushButton {
                background:#f2f6f9; border:1px solid #b8c9d8;
                border-radius:4px; min-width:32px; min-height:30px;
            }
            QPushButton:hover { background:white; }
        """)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        title = QLabel("PROGRAMMAZIONE SETUP")
        title.setObjectName("programmingTitle")
        top_row.addWidget(title)
        top_row.addSpacing(14)
        self.lbl_pdf_path = QLabel("PDF: nessun documento caricato")
        self.lbl_pdf_path.setObjectName("pdfPath")
        self.lbl_pdf_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top_row.addWidget(self.lbl_pdf_path, 1)
        self.lbl_page = QLabel("Pagina: —")
        self.lbl_page.setObjectName("pageLabel")
        top_row.addWidget(self.lbl_page)

        btn_prev = QPushButton()
        btn_prev.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        btn_prev.setToolTip("Pagina precedente")
        btn_prev.clicked.connect(lambda: self._change_page(-1))
        top_row.addWidget(btn_prev)

        btn_next = QPushButton()
        btn_next.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        btn_next.setToolTip("Pagina successiva")
        btn_next.clicked.connect(lambda: self._change_page(1))
        top_row.addWidget(btn_next)
        layout.addLayout(top_row)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(12)

        def add_field(label_text, widget, stretch):
            field = QVBoxLayout()
            field.setSpacing(2)
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            field.addWidget(label)
            field.addWidget(widget)
            fields_row.addLayout(field, stretch)

        self.txt_setup_name = QLineEdit()
        self.txt_setup_name.setPlaceholderText("Nome setup (es. Flangia_A2024)")
        add_field("NOME SETUP", self.txt_setup_name, 3)

        self.txt_setup_desc = QLineEdit()
        self.txt_setup_desc.setPlaceholderText("Descrizione opzionale")
        add_field("DESCRIZIONE", self.txt_setup_desc, 4)

        self.cmb_sampling_class = QComboBox()
        self.cmb_sampling_class.addItem("Seleziona classe…", None)
        for sampling_class in db.get_all_sampling_classes():
            self.cmb_sampling_class.addItem(
                f"{sampling_class['code']} — {sampling_class['description']}",
                sampling_class["id"],
            )
        self.cmb_sampling_class.setMinimumWidth(230)
        add_field("CLASSE DI COLLAUDO *", self.cmb_sampling_class, 3)
        layout.addLayout(fields_row)

        self.txt_setup_name.textChanged.connect(self._update_setup_dirty_state)
        self.txt_setup_desc.textChanged.connect(self._update_setup_dirty_state)
        self.cmb_sampling_class.currentIndexChanged.connect(
            self._update_setup_dirty_state
        )

        return bar

    @staticmethod
    def _sha256_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _store_pdf_in_hash_path(self, source_path: str) -> str:
        source = Path(source_path)
        pdf_hash = self._sha256_file(str(source))
        target_dir = Path(get_pdf_dir())
        target_path = target_dir / f"{pdf_hash}.pdf"
        target_dir.mkdir(parents=True, exist_ok=True)
        if target_path.is_symlink():
            raise ValueError("Il PDF di destinazione non può essere un link simbolico.")
        if target_path.exists() and not target_path.is_file():
            raise ValueError("Destinazione PDF non valida.")
        if not target_path.exists():
            fd, temporary_path = tempfile.mkstemp(prefix=".import-", dir=target_dir)
            try:
                with os.fdopen(fd, "wb") as destination, source.open("rb") as origin:
                    shutil.copyfileobj(origin, destination)
                    destination.flush()
                    os.fsync(destination.fileno())
                    if self._sha256_file(temporary_path) != pdf_hash:
                        raise ValueError("Il PDF sorgente è cambiato durante la copia.")
                    directory_gid = target_dir.stat().st_gid
                    if os.fstat(destination.fileno()).st_gid != directory_gid:
                        os.fchown(destination.fileno(), -1, directory_gid)
                    os.fchmod(destination.fileno(), 0o640)
                # Pubblica il file completo senza sovrascrivere import concorrenti.
                try:
                    os.link(temporary_path, target_path)
                except FileExistsError:
                    if target_path.is_symlink() or not target_path.is_file():
                        raise ValueError("Destinazione PDF non valida.")
            finally:
                os.unlink(temporary_path)
        return str(target_path)

    # ─── Azioni toolbar ──────────────────────────────────────────────────────

    def _current_setup_state(self) -> tuple[str, str, str | None, int | None]:
        return (
            self.txt_setup_name.text().strip(),
            self.txt_setup_desc.text().strip(),
            self._pdf_path,
            self.cmb_sampling_class.currentData(),
        )

    def _update_setup_dirty_state(self, *_args):
        self._setup_fields_dirty = (
            self._current_setup_state() != self._saved_setup_state
        )
        self._refresh_dirty_state()

    def _on_control_dirty_changed(self, dirty: bool):
        self._control_dirty = dirty
        self._refresh_dirty_state()

    @staticmethod
    def _controls_state(controls: list[dict]) -> tuple:
        fields = (
            "id", "balloon_num", "balloon_x", "balloon_y", "pdf_page",
            "control_type", "criticality", "label", "nominal", "tol_plus",
            "tol_minus", "description",
        )
        return tuple(
            tuple(control.get(field) for field in fields)
            for control in sorted(
                controls,
                key=lambda item: (int(item.get("balloon_num") or 0),
                                  int(item.get("id") or 0)),
            )
        )

    def _refresh_dirty_state(self):
        self._setup_dirty = (
            self._setup_fields_dirty
            or self._control_dirty
            or self._controls_state(self._working_controls)
               != self._saved_controls_state
        )
        self.act_save.setEnabled(self._setup_dirty)

    def _mark_setup_saved(self):
        self._saved_setup_state = self._current_setup_state()
        self._saved_controls_state = self._controls_state(self._working_controls)
        self._update_setup_dirty_state()

    def _confirm_discard_setup_changes(self) -> bool:
        if not self._setup_dirty:
            return True
        reply = QMessageBox.question(
            self,
            "Modifiche non salvate",
            "Il setup contiene modifiche non salvate.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            return self._save_programming_changes(show_confirmation=False)
        return reply == QMessageBox.Discard

    def _on_new_setup(self):
        if not self._confirm_discard_setup_changes():
            return
        self._reset_to_new_setup()

    def _reset_to_new_setup(self):
        """Riporta la finestra allo stato iniziale senza chiedere conferma."""
        self._setup_id = None
        self._pdf_path = None
        self.txt_setup_name.clear()
        self.txt_setup_desc.clear()
        self.cmb_sampling_class.setCurrentIndex(0)
        self.lbl_pdf_path.setText("(nessun PDF)")
        self._working_controls = []
        self.viewer.clear_pdf()
        self.lbl_page.setText("Pagina: —")
        self.ctrl_list.lst.clear()
        self.ctrl_form.reset_form()
        self._pending_control_deletions.clear()
        self._mark_setup_saved()
        self.statusBar().showMessage("Nuovo setup — Carica un PDF per iniziare")

    def _on_open_setup(self):
        setups = db.get_all_setups()
        if not setups:
            QMessageBox.information(self, "Gestione setup", "Nessun setup salvato.")
            return
        dialog = SetupOpenDialog(
            setups, self, current_setup_id=self._setup_id
        )
        result = dialog.exec_()
        if self._setup_id in dialog.deleted_setup_ids:
            self._reset_to_new_setup()
        if result != QDialog.Accepted:
            return
        if dialog.create_new_setup:
            self._on_new_setup()
        elif dialog.selected_setup_id is not None:
            if self._confirm_discard_setup_changes():
                self._load_existing_setup(dialog.selected_setup_id)

    def _on_save_setup(self):
        self._save_programming_changes(show_confirmation=True)

    def _on_apply_control(self) -> bool:
        if self.ctrl_form.control_payload() is None:
            QMessageBox.warning(
                self, "Attenzione", "Seleziona prima un balloon sul disegno."
            )
            return False
        payload = self.ctrl_form.control_payload()
        control_id = self.ctrl_form.control_id
        for index, control in enumerate(self._working_controls):
            if control["id"] == control_id:
                payload["id"] = control_id
                payload["pass_fail"] = None
                self._working_controls[index] = payload
                break
        else:
            QMessageBox.warning(
                self, "Attenzione", "Il controllo corrente non è più disponibile."
            )
            return False
        self.ctrl_form.mark_applied()
        self._refresh_controls()
        self.viewer.select_balloon(control_id)
        self.ctrl_list.select_control(control_id)
        self._refresh_dirty_state()
        self.statusBar().showMessage(
            "Controllo applicato — premi 'Salva setup' per salvarlo"
        )
        return True

    def _save_programming_changes(self, show_confirmation: bool) -> bool:
        name = self.txt_setup_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Salva", "Inserisci un nome per il setup.")
            return False
        if not self._pdf_path:
            QMessageBox.warning(self, "Salva", "Carica prima un file PDF.")
            return False
        sampling_class_id = self.cmb_sampling_class.currentData()
        if sampling_class_id is None:
            QMessageBox.warning(
                self, "Salva", "Seleziona la Classe di Collaudo del setup."
            )
            return False

        desc = self.txt_setup_desc.text().strip()
        setup_was_new = self._setup_id is None
        selected_balloon_num = self.ctrl_form.balloon_num
        if self.ctrl_form.is_dirty and not self._on_apply_control():
            return False
        if not any(
            control.get("criticality", "N") == "C"
            for control in self._working_controls
        ):
            QMessageBox.warning(
                self,
                "Criticità obbligatoria",
                "Il setup deve contenere almeno un controllo con criticità "
                "C — CRITICA.",
            )
            return False
        try:
            setup_id, saved_controls = db.save_programming_changes(
                self._setup_id, name, desc, self._pdf_path,
                sampling_class_id,
                controls=self._working_controls,
                deleted_control_ids=sorted(self._pending_control_deletions),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Errore di salvataggio",
                "Nessuna modifica è stata salvata.\n\n"
                f"Dettaglio: {exc}",
            )
            return False

        self._setup_id = setup_id
        self._pending_control_deletions.clear()
        self._working_controls = saved_controls

        self.setup_saved.emit(self._setup_id)
        self._mark_setup_saved()
        self._refresh_controls()
        selected = next(
            (control for control in self._working_controls
             if control["balloon_num"] == selected_balloon_num),
            None,
        )
        if selected:
            self.ctrl_form.load_control(selected)
            self.viewer.select_balloon(selected["id"])
            self.ctrl_list.select_control(selected["id"])
        else:
            self.ctrl_form.reset_form()
        self._refresh_dirty_state()
        if show_confirmation:
            if setup_was_new:
                message = f"Setup '{name}' salvato (ID: {self._setup_id})."
            else:
                message = f"Setup '{name}' aggiornato."
            QMessageBox.information(self, "Salva", message)
        self.statusBar().showMessage(f"Setup '{name}' salvato — ID {self._setup_id}")
        return True

    def _on_load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona disegno tecnico", "", "PDF (*.pdf)"
        )
        if not path:
            return

        try:
            stored_pdf_path = self._store_pdf_in_hash_path(path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Errore",
                f"Impossibile copiare il PDF nella directory configurata:\n{e}"
            )
            return

        short = stored_pdf_path.split("/")[-1]
        if not self.viewer.validate_pdf(stored_pdf_path):
            QMessageBox.critical(self, "Errore", "Il file selezionato non è un PDF valido.")
            return
        replace_controls = False
        if stored_pdf_path != self._pdf_path and self._working_controls:
            handling = self._ask_pdf_controls_handling()
            if handling is None:
                return
            replace_controls = handling == "reset"
        if self.viewer.load_pdf(stored_pdf_path):
            if replace_controls:
                self._pending_control_deletions.update(
                    int(control["id"])
                    for control in self._working_controls
                    if int(control.get("id") or 0) > 0
                )
                self._working_controls = []
                self.ctrl_form.reset_form()
                self._refresh_controls()
            self._pdf_path = stored_pdf_path
            self.lbl_pdf_path.setText(short)
            self._update_setup_dirty_state()
            self._update_page_label()
            self.statusBar().showMessage(f"PDF caricato: {short}")
        else:
            QMessageBox.critical(self, "Errore", "Impossibile aprire il PDF.")

    def _ask_pdf_controls_handling(self) -> str | None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Sostituzione PDF")
        dialog.setText("Il setup contiene già dei controlli.")
        dialog.setInformativeText(
            "Vuoi mantenerli sul nuovo PDF oppure eliminarli dal modello?"
        )
        keep_button = dialog.addButton(
            "Mantieni controlli", QMessageBox.AcceptRole
        )
        keep_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogApplyButton)
        )
        reset_button = dialog.addButton(
            "Elimina controlli", QMessageBox.DestructiveRole
        )
        reset_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        cancel_button = dialog.addButton(QMessageBox.Cancel)
        cancel_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogCancelButton)
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec_()
        if dialog.clickedButton() is keep_button:
            return "keep"
        if dialog.clickedButton() is reset_button:
            return "reset"
        return None

    def _change_page(self, delta: int):
        if not self.viewer.total_pages:
            return
        new_page = self.viewer.current_page + delta
        if 0 <= new_page < self.viewer.total_pages:
            self.viewer.set_page(new_page)
            self._update_page_label()

    def _update_page_label(self):
        self.lbl_page.setText(
            f"Pagina: {self.viewer.current_page + 1}/{self.viewer.total_pages}"
        )

    # ─── Balloon handlers ────────────────────────────────────────────────────

    def _next_available_balloon_num(self) -> int:
        used = {
            int(b["balloon_num"])
            for b in self.viewer._balloons
            if b.get("balloon_num") is not None
        }
        num = 1
        while num in used:
            num += 1
        return num

    def _allocate_temp_control_id(self) -> int:
        """Restituisce un ID negativo univoco nella vita della finestra."""
        control_id = self._next_temp_control_id
        self._next_temp_control_id -= 1
        return control_id

    def _on_balloon_added(self, x: float, y: float, page: int):
        if not self._confirm_control_transition():
            return
        name = self.txt_setup_name.text().strip()
        if not name or not self._pdf_path:
            QMessageBox.warning(
                self, "Setup incompleto",
                "Inserisci nome setup e carica il PDF prima di aggiungere balloon."
            )
            return

        balloon_num = self._next_available_balloon_num()
        temp_id = self._allocate_temp_control_id()
        self.ctrl_form.set_new_balloon(
            self._setup_id, temp_id, balloon_num, x, y, page
        )

        # Aggiungi balloon temporaneo nel viewer
        temp = {
            "id": temp_id,
            "balloon_num": balloon_num,
            "balloon_x": x,
            "balloon_y": y,
            "pdf_page": page,
            "control_type": "dimensional",
            "criticality": "N",
            "label": "",
            "nominal": 0.0,
            "tol_plus": 0.05,
            "tol_minus": 0.05,
            "description": "",
            "pass_fail": None
        }
        # Aggiorna la lista locale
        self._working_controls.append(temp)
        self._refresh_controls()
        self.viewer.select_balloon(temp_id)
        self.ctrl_list.select_control(temp_id)
        self._refresh_dirty_state()

        self.statusBar().showMessage(
            f"Balloon {balloon_num} aggiunto — compila e clicca 'Applica controllo'"
        )

    def _on_balloon_clicked(self, balloon_id: int):
        if balloon_id == self.ctrl_form.control_id:
            return
        if not self._confirm_control_transition():
            self._restore_current_control_selection()
            return
        ctrl = next(
            (control for control in self._working_controls
             if control["id"] == balloon_id),
            None,
        )
        if ctrl:
            self.ctrl_form.load_control(ctrl)
            self.viewer.select_balloon(balloon_id)
            self.ctrl_list.select_control(balloon_id)

    def _on_balloon_moved(
            self, balloon_id: int, x: float, y: float, page: int):
        control = next(
            (control for control in self._working_controls
             if control["id"] == balloon_id),
            None,
        )
        if control is None:
            return
        control["balloon_x"] = x
        control["balloon_y"] = y
        control["pdf_page"] = page
        self.ctrl_form.set_balloon_position(balloon_id, x, y, page)
        self.viewer.select_balloon(balloon_id)
        self.ctrl_list.select_control(balloon_id)
        self._refresh_dirty_state()
        self.statusBar().showMessage(
            f"Balloon {control['balloon_num']} spostato — "
            "premi 'Salva setup' per confermare"
        )

    def _current_control_has_unsaved_changes(self) -> bool:
        return self.ctrl_form.is_dirty

    def _confirm_control_transition(self) -> bool:
        if not self._current_control_has_unsaved_changes():
            return True
        reply = QMessageBox.question(
            self,
            "Controllo non applicato",
            "Il controllo corrente contiene modifiche non applicate.",
            QMessageBox.Apply | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Apply:
            return self._on_apply_control()
        if reply == QMessageBox.Discard:
            current = next(
                (control for control in self._working_controls
                 if control["id"] == self.ctrl_form.control_id),
                None,
            )
            if current:
                self.ctrl_form.load_control(current)
            else:
                self.ctrl_form.reset_form()
            self._refresh_dirty_state()
            return True
        return False

    def _restore_current_control_selection(self):
        control_id = self.ctrl_form.control_id
        self.viewer.select_balloon(control_id)
        self.ctrl_list.select_control(control_id)

    def _on_balloon_deleted(self, balloon_id: int):
        if balloon_id < 0:
            # Rimuovi temporaneo
            self._working_controls = [
                control for control in self._working_controls
                if control["id"] != balloon_id
            ]
            if self.ctrl_form.control_id == balloon_id:
                self.ctrl_form.reset_form()
            self._refresh_controls()
            self._refresh_dirty_state()
            return

        reply = QMessageBox.question(
            self, "Elimina controllo",
            "Eliminare questo controllo?\n\n"
            "L'eliminazione verrà applicata con 'Salva setup'. "
            "Le revisioni e le misure storiche resteranno disponibili.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._pending_control_deletions.add(balloon_id)
            self._working_controls = [
                control for control in self._working_controls
                if control["id"] != balloon_id
            ]
            if self.ctrl_form.control_id == balloon_id:
                self.ctrl_form.reset_form()
            self._refresh_controls()
            self._refresh_dirty_state()
            self.statusBar().showMessage(
                "Eliminazione in attesa — premi 'Salva setup' per confermare"
            )

    def _on_control_move_requested(self, control_id: int, direction: int):
        if direction not in {-1, 1}:
            return
        if not self._confirm_control_transition():
            self._restore_current_control_selection()
            return

        ordered_controls = sorted(
            self._working_controls,
            key=lambda control: (
                int(control.get("balloon_num") or 0),
                int(control.get("id") or 0),
            ),
        )
        current_index = next(
            (index for index, control in enumerate(ordered_controls)
             if control["id"] == control_id),
            None,
        )
        if current_index is None:
            return
        target_index = current_index + direction
        if not 0 <= target_index < len(ordered_controls):
            return

        ordered_controls[current_index], ordered_controls[target_index] = (
            ordered_controls[target_index], ordered_controls[current_index]
        )
        for balloon_num, control in enumerate(ordered_controls, start=1):
            control["balloon_num"] = balloon_num
        self._working_controls = ordered_controls

        selected_control = next(
            control for control in self._working_controls
            if control["id"] == control_id
        )
        self.ctrl_form.load_control(selected_control)
        self._refresh_controls()
        self.viewer.select_balloon(control_id)
        self.ctrl_list.select_control(control_id)
        self._refresh_dirty_state()
        direction_text = "sopra" if direction < 0 else "sotto"
        self.statusBar().showMessage(
            f"Controllo spostato {direction_text} — "
            "premi 'Salva setup' per confermare"
        )

    def _on_control_selected_from_list(self, control_id: int):
        if control_id == self.ctrl_form.control_id:
            return
        if not self._confirm_control_transition():
            self._restore_current_control_selection()
            return
        ctrl = next(
            (control for control in self._working_controls
             if control["id"] == control_id),
            None,
        )
        if ctrl:
            self.ctrl_form.load_control(ctrl)
            self.viewer.select_balloon(control_id)
            self.ctrl_list.select_control(control_id)
            # Vai alla pagina del controllo se diversa
            if ctrl.get("pdf_page", 0) != self.viewer.current_page:
                self.viewer.set_page(ctrl.get("pdf_page", 0))
                self._update_page_label()

    # ─── Caricamento setup esistente ─────────────────────────────────────────

    def _load_existing_setup(self, setup_id: int) -> bool:
        setup = db.get_setup(setup_id)
        if not setup:
            QMessageBox.critical(self, "Errore", "Setup non trovato.")
            return False
        class_index = self.cmb_sampling_class.findData(
            setup.get("sampling_class_id")
        )
        if class_index < 0:
            QMessageBox.critical(
                self,
                "Classe di Collaudo non disponibile",
                "La classe associata al setup non è presente in Configurazione.",
            )
            return False
        controls = db.get_controls_for_setup(setup_id)
        if not self.viewer.load_pdf(setup["pdf_path"]):
            QMessageBox.critical(
                self,
                "Errore PDF",
                "Impossibile aprire il PDF associato al setup.\n\n"
                "Il setup corrente non è stato sostituito.",
            )
            return False
        self._setup_id = setup_id
        self._pdf_path = setup["pdf_path"]
        self.txt_setup_name.setText(setup["name"])
        self.txt_setup_desc.setText(setup.get("description") or "")
        self.cmb_sampling_class.setCurrentIndex(class_index)
        self.lbl_pdf_path.setText(setup["pdf_path"].split("/")[-1])
        self.ctrl_form.reset_form()
        self._pending_control_deletions.clear()
        self._working_controls = controls
        self._update_page_label()

        self._refresh_controls()
        self._mark_setup_saved()
        self.statusBar().showMessage(f"Setup '{setup['name']}' caricato — ID {setup_id}")
        return True

    def _refresh_controls(self):
        controls = [dict(control) for control in self._working_controls]
        # Aggiungi pass_fail=None per la visualizzazione
        for c in controls:
            c["pass_fail"] = None
        self.viewer.load_balloons(controls)
        self.ctrl_list.set_controls(controls)
        count = len(controls)
        self.setWindowTitle(
            f"QC Inspector — Programmazione  |  {self.txt_setup_name.text()}  |  {count} controlli"
        )

    def closeEvent(self, event):
        if not self._setup_dirty:
            event.accept()
            return
        reply = QMessageBox.question(
            self,
            "Chiudere Programmazione",
            "Il setup contiene modifiche non salvate.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            if self._save_programming_changes(show_confirmation=False):
                event.accept()
            else:
                event.ignore()
        elif reply == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()
