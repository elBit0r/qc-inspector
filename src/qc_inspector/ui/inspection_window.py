"""
inspection_window.py
Finestra di controllo: registra misure per campione o per controllo, mostra PASS/FAIL in tempo reale.
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QGroupBox, QFormLayout,
    QFileDialog, QMessageBox, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QFrame, QProgressBar,
    QDialog, QDialogButtonBox, QCheckBox, QTextEdit, QCompleter,
    QSizePolicy, QStyle, QShortcut,
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor, QFont, QBrush, QIcon, QPixmap, QKeySequence

from ..ui.pdf_viewer import PdfViewerWidget
from ..ui.decimal_spinbox import DecimalSpinBox
from ..ui.control_statistics_widget import ControlStatisticsWidget
from ..database import db_manager as db
from ..core.inspection_engine import (
    evaluate_control, get_measurement_status,
    get_control_status, format_tolerance,
    get_expected_measurement_count, evaluate_sampling_lot,
    STATUS_EMPTY, STATUS_PASS, STATUS_DEROGATION, STATUS_INCOMPLETE,
)
from ..core.sampling_plans import recommend_sampling_profile
from ..core.report_generator import generate_report
from ..core.label_printer import generate_label_pdf, print_label, load_or_create_config
from ..core.audio_feedback import MeasurementSoundPlayer


PASS_COLOR = QColor(200, 240, 200)
FAIL_COLOR = QColor(255, 200, 200)
NEUTRAL_COLOR = QColor(245, 245, 245)

CRITICALITY_LABELS = {
    "C": "C — CRITICA",
    "I": "I — IMPORTANTE",
    "N": "N — NORMALE",
}
CRITICALITY_COLORS = {
    "C": "#b71c1c",
    "I": "#b26a00",
    "N": "#455a64",
}


def format_criticality(control: dict) -> str:
    return CRITICALITY_LABELS.get(
        control.get("criticality", "N"), CRITICALITY_LABELS["N"]
    )


class DerogationDialog(QDialog):
    """Conferma insieme tutte le misure selezionate per la deroga."""

    def __init__(self, operator: str, rows: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accettazione in deroga")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        info = QLabel(
            "Le misure elencate restano tecnicamente FAIL. La motivazione e "
            "il responsabile saranno applicati a tutte le deroghe selezionate."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(
            ["Campione", "Rif.", "Controllo", "Misura"]
        )
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        for index, row in enumerate(rows):
            for column, value in enumerate(row.derogation_summary()):
                table.setItem(index, column, QTableWidgetItem(str(value)))
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.resizeRowsToContents()
        table.setMaximumHeight(min(260, 58 + len(rows) * 30))
        layout.addWidget(table)

        form = QFormLayout()
        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText(
            "Es.: La misura fuori tolleranza non implica problemi funzionali."
        )
        self.txt_reason.setFixedHeight(90)
        form.addRow("Motivazione*:", self.txt_reason)

        self.txt_authorized_by = QLineEdit()
        self.txt_authorized_by.setPlaceholderText("Nome del responsabile")
        form.addRow("Autorizzato da*:", self.txt_authorized_by)
        form.addRow("Registrato da:", QLabel(operator))
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.txt_reason.textChanged.connect(self._update_ok_state)
        self.txt_authorized_by.textChanged.connect(self._update_ok_state)
        self._update_ok_state()

    def _update_ok_state(self):
        enabled = bool(
            self.txt_reason.toPlainText().strip()
            and self.txt_authorized_by.text().strip()
        )
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(enabled)

    @property
    def reason(self) -> str:
        return self.txt_reason.toPlainText().strip()

    @property
    def authorized_by(self) -> str:
        return self.txt_authorized_by.text().strip()


class SampleControlRow(QWidget):
    """Una riga di misurazione per un controllo e un campione specifico."""

    measurement_saved = pyqtSignal(int, object, object, bool)  # control_id, val_num, val_bool, pass
    advance_requested = pyqtSignal()

    def __init__(self, control: dict, sample_num: int, parent=None,
                 compact: bool = False):
        super().__init__(parent)
        self._control = control
        self._sample_num = sample_num
        self._compact = compact
        self._pass_fail: bool | None = None
        self._last_evaluated_value: float | None = None
        self._derogated = False
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        if self._compact:
            self.setObjectName(
                "measurementRowEven"
                if self._sample_num % 2 == 0 else "measurementRowOdd"
            )
            self.setMinimumHeight(42)
            layout.setContentsMargins(10, 4, 10, 4)
            layout.setSpacing(10)
        else:
            layout.setContentsMargins(6, 4, 6, 4)
            layout.setSpacing(8)

        if self._compact:
            lbl_sample = QLabel(f"Campione {self._sample_num}")
            lbl_sample.setFont(QFont("Arial", 11, QFont.Bold))
            lbl_sample.setFixedWidth(110)
            layout.addWidget(lbl_sample)
        else:
            # Balloon number
            lbl_balloon = QLabel(f"[{self._control['balloon_num']}]")
            lbl_balloon.setFont(QFont("Arial", 11, QFont.Bold))
            lbl_balloon.setFixedWidth(36)
            layout.addWidget(lbl_balloon)

            # Descrizione e note controllo
            desc = self._control.get("label") or "(senza etichetta)"
            notes = (self._control.get("description") or "").strip()
            desc_box = QWidget()
            desc_layout = QVBoxLayout(desc_box)
            desc_layout.setContentsMargins(0, 0, 0, 0)
            desc_layout.setSpacing(1)
            lbl_desc = QLabel(desc)
            lbl_desc.setWordWrap(False)
            desc_layout.addWidget(lbl_desc)
            criticality = self._control.get("criticality", "N")
            lbl_criticality = QLabel(
                f"Criticità: {format_criticality(self._control)}"
            )
            lbl_criticality.setStyleSheet(
                f"color: {CRITICALITY_COLORS.get(criticality, '#455a64')}; "
                "font-size: 9pt; font-weight: bold;"
            )
            desc_layout.addWidget(lbl_criticality)
            if notes:
                lbl_notes = QLabel(f"Note: {notes}")
                lbl_notes.setWordWrap(True)
                lbl_notes.setStyleSheet("color: #666; font-size: 9pt;")
                desc_layout.addWidget(lbl_notes)
                desc_box.setToolTip(notes)
            desc_box.setFixedWidth(180)
            layout.addWidget(desc_box)

        # Quota nominale
        if self._control["control_type"] == "dimensional":
            if not self._compact:
                tol_str = format_tolerance(
                    self._control["nominal"],
                    self._control["tol_plus"],
                    self._control["tol_minus"]
                )
                lbl_nom = QLabel(tol_str)
                lbl_nom.setStyleSheet("color: #444; font-size: 11pt;")
                lbl_nom.setFixedWidth(180)
                layout.addWidget(lbl_nom)

            # Input misura
            self.input = DecimalSpinBox()
            self.input.setRange(-9999, 9999)
            self.input.setDecimals(3)
            self.input.setSuffix(" mm")
            self.input.setFixedWidth(140 if self._compact else 120)
            self.input.setMinimumHeight(30)
            self._pending_timer = QTimer(self)
            self._pending_timer.setSingleShot(True)
            self._pending_timer.timeout.connect(self._on_value_changed)
            self.input.valueChanged.connect(self._on_value_input_changed)
            self.input.editingFinished.connect(self._on_value_editing_finished)
            self.input.lineEdit().returnPressed.connect(self._on_value_confirmed)
            layout.addWidget(self.input)

        else:  # yesno
            if not self._compact:
                lbl_nom = QLabel("Presenza / verifica")
                lbl_nom.setStyleSheet("color: #444; font-size: 11pt;")
                lbl_nom.setFixedWidth(180)
                layout.addWidget(lbl_nom)

            self.btn_si = QPushButton("Sì")
            self.btn_si.setFixedWidth(65 if self._compact else 50)
            self.btn_si.setMinimumHeight(30)
            self.btn_si.setCheckable(True)
            self.btn_si.clicked.connect(lambda: self._on_yesno(True))
            layout.addWidget(self.btn_si)

            self.btn_no = QPushButton("No")
            self.btn_no.setFixedWidth(65 if self._compact else 50)
            self.btn_no.setMinimumHeight(30)
            self.btn_no.setCheckable(True)
            self.btn_no.clicked.connect(lambda: self._on_yesno(False))
            layout.addWidget(self.btn_no)

        # Risultato PASS/FAIL
        self.lbl_result = QLabel("—")
        if self._compact:
            self.lbl_result.setMinimumWidth(150)
            self.lbl_result.setMaximumWidth(260)
            self.lbl_result.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Preferred
            )
        else:
            self.lbl_result.setFixedWidth(180)
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setStyleSheet(
            "border:1px solid #cbd3db; border-radius:4px; padding:4px 8px; "
            "background:#f7f9fa; color:#607080;"
        )
        layout.addWidget(self.lbl_result, 1 if self._compact else 0)

        self.chk_derogation = QCheckBox("Accetta in deroga")
        self.chk_derogation.setFixedWidth(150)
        self.chk_derogation.setVisible(False)
        self.chk_derogation.setToolTip(
            "La deroga verrà confermata insieme alle altre quando salvi il controllo."
        )
        layout.addWidget(self.chk_derogation)
        if not self._compact:
            layout.addStretch()

    def _on_value_input_changed(self):
        # Debounce per evitare scritture DB ad ogni singolo step.
        self._pending_timer.start(300)

    def _on_value_editing_finished(self):
        # Flush immediato quando l'utente conclude l'edit.
        if self._pending_timer.isActive():
            self._pending_timer.stop()
            self._on_value_changed()

    def _on_value_changed(self):
        value = self.input.value()
        pass_fail, msg = evaluate_control(self._control, value, None)
        self._last_evaluated_value = value
        self._set_result(pass_fail, msg)
        self.measurement_saved.emit(self._control["id"], value, None, pass_fail)
        return pass_fail

    def _on_value_confirmed(self):
        """Conferma con Invio e avanza soltanto se la misura e valida."""
        if self._pending_timer.isActive():
            self._pending_timer.stop()
        value = self.input.value()
        if self._last_evaluated_value != value:
            pass_fail = self._on_value_changed()
        else:
            pass_fail = self._pass_fail
        if pass_fail:
            QTimer.singleShot(0, self.advance_requested.emit)

    def _on_yesno(self, answer: bool):
        pass_fail, msg = evaluate_control(self._control, None, answer)
        self._set_result(pass_fail, msg)
        self.measurement_saved.emit(self._control["id"], None, answer, pass_fail)
        # Stile pulsanti
        self.btn_si.setChecked(answer)
        self.btn_no.setChecked(not answer)
        if pass_fail:
            QTimer.singleShot(0, self.advance_requested.emit)

    def focus_measurement_input(self):
        """Porta il focus all'input principale della riga."""
        if hasattr(self, "input"):
            self.input.setFocus()
            self.input.selectAll()
        else:
            self.btn_si.setFocus()

    def _set_result(self, pass_fail: bool, msg: str):
        self._pass_fail = pass_fail
        self._derogated = False
        self.lbl_result.setText("PASS" if pass_fail else "FAIL")
        color = "#1a8a1a" if pass_fail else "#cc0000"
        bg = "#e8f5e9" if pass_fail else "#ffebee"
        self.lbl_result.setStyleSheet(
            f"border: 1px solid {color}; border-radius: 3px; "
            f"padding: 2px 6px; color: {color}; background: {bg}; font-weight: bold;"
        )
        self.chk_derogation.setText("Accetta in deroga")
        self.chk_derogation.setEnabled(True)
        self.chk_derogation.setChecked(False)
        self.chk_derogation.setVisible(not pass_fail)

    def set_derogated(self, derogated: bool):
        self._derogated = derogated
        if derogated:
            self.lbl_result.setText("FAIL — DEROGA")
            self.lbl_result.setStyleSheet(
                "border: 1px solid #b26a00; border-radius: 3px; "
                "padding: 2px 6px; color: #7a4b00; background: #fff3cd; "
                "font-weight: bold;"
            )
            self.chk_derogation.setText("Accettata in deroga")
            self.chk_derogation.setChecked(True)
            self.chk_derogation.setEnabled(False)
            self.chk_derogation.setVisible(True)
        else:
            self._set_result(False, "FAIL")

    def is_derogation_selected(self) -> bool:
        return (
            self._pass_fail is False
            and not self._derogated
            and self.chk_derogation.isVisible()
            and self.chk_derogation.isChecked()
        )

    def derogation_summary(self) -> tuple:
        if self._control["control_type"] == "dimensional":
            value = f"{self.input.value():.3f} mm"
        else:
            value = "Sì" if self.btn_si.isChecked() else "No"
        return (
            self._sample_num,
            self._control["balloon_num"],
            self._control.get("label") or "(senza etichetta)",
            value,
        )

    def reset(self):
        self._pass_fail = None
        self._derogated = False
        self.lbl_result.setText("—")
        self.lbl_result.setStyleSheet(
            "border:1px solid #cbd3db; border-radius:4px; padding:4px 8px; "
            "background:#f7f9fa; color:#607080;"
        )
        self.chk_derogation.setChecked(False)
        self.chk_derogation.setVisible(False)
        if hasattr(self, "input"):
            self.input.setValue(0)
            self._last_evaluated_value = None


class SamplePanel(QScrollArea):
    """Pannello con tutti i controlli per un campione."""

    all_done = pyqtSignal()
    measurement_updated = pyqtSignal(int, int, object, object, bool)

    def __init__(self, controls: list, sample_num: int,
                 lot_id: int, operator: str, parent=None):
        super().__init__(parent)
        self._controls = controls
        self._sample_num = sample_num
        self._lot_id = lot_id
        self._operator = operator
        self._rows: list[SampleControlRow] = []
        self._completed_control_ids: set[int] = set()
        self._all_done_emitted = False
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        container.setObjectName("samplePanel")
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(16, 14, 16, 14)

        # Header
        hdr = QLabel(f"Campione n° {self._sample_num}")
        hdr.setFont(QFont("Arial", 13, QFont.Bold))
        layout.addWidget(hdr)

        # Header colonne
        col_hdr = QHBoxLayout()
        for text, w in [("Ref.", 36), ("Descrizione", 180),
                        ("Nominale / Tolleranza", 180), ("Misura", 120),
                        ("", 80), ("Esito", 160)]:
            lbl = QLabel(text)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("color: #888; font-size: 10pt; font-weight: bold;")
            col_hdr.addWidget(lbl)
        col_hdr.addStretch()
        layout.addLayout(col_hdr)

        # Separatore
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        layout.addWidget(sep)

        # Righe controllo
        for row_index, ctrl in enumerate(self._controls):
            row = SampleControlRow(ctrl, self._sample_num)
            row.setObjectName(
                "measurementRowEven" if row_index % 2 else "measurementRowOdd"
            )
            row.measurement_saved.connect(self._on_measurement)
            row.advance_requested.connect(
                lambda index=row_index: self._focus_next_row(index)
            )
            self._rows.append(row)
            layout.addWidget(row)

        layout.addStretch()

        self.setWidget(container)
        self.setWidgetResizable(True)

    def _focus_next_row(self, current_index: int):
        next_index = current_index + 1
        if next_index >= len(self._rows):
            return
        next_row = self._rows[next_index]
        self.ensureWidgetVisible(next_row)
        next_row.focus_measurement_input()

    def _on_measurement(self, control_id: int, val_num,
                        val_bool, pass_fail: bool):
        self._completed_control_ids.add(control_id)
        self.measurement_updated.emit(
            self._sample_num, control_id, val_num, val_bool, pass_fail
        )
        if (not self._all_done_emitted
                and len(self._completed_control_ids) >= len(self._controls)):
            self._all_done_emitted = True
            self.all_done.emit()

    def get_pass_count(self) -> tuple[int, int]:
        completed = [
            row for row in self._rows if row._pass_fail is not None
        ]
        return sum(1 for row in completed if row._pass_fail), len(completed)


class SequentialControlPanel(QScrollArea):
    """Pannello con tutti i campioni per uno specifico controllo."""

    all_done = pyqtSignal()
    measurement_updated = pyqtSignal(int, int, object, object, bool)

    def __init__(self, control: dict, n_samples: int,
                 lot_id: int, operator: str, parent=None):
        super().__init__(parent)
        self._control = control
        self._n_samples = n_samples
        self._lot_id = lot_id
        self._operator = operator
        self._rows: list[SampleControlRow] = []
        self._completed_sample_nums: set[int] = set()
        self._all_done_emitted = False
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        container.setObjectName("samplePanel")
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 14, 16, 14)

        summary = QFrame()
        summary.setObjectName("controlSummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(14, 11, 14, 11)
        summary_layout.setSpacing(4)

        title_row = QHBoxLayout()
        hdr = QLabel(f"Controllo {self._control['balloon_num']}")
        hdr.setFont(QFont("Arial", 14, QFont.Bold))
        title_row.addWidget(hdr)
        title_row.addStretch()

        desc = self._control.get("label") or "(senza etichetta)"
        lbl_desc = QLabel(desc)
        lbl_desc.setFont(QFont("Arial", 12, QFont.Bold))

        criticality = self._control.get("criticality", "N")
        lbl_criticality = QLabel(
            format_criticality(self._control)
        )
        lbl_criticality.setStyleSheet(
            f"color:{CRITICALITY_COLORS.get(criticality, '#455a64')}; "
            f"background:white; border:1px solid "
            f"{CRITICALITY_COLORS.get(criticality, '#455a64')}; "
            "border-radius:10px; padding:3px 10px; font-size:9pt; "
            "font-weight:bold;"
        )
        title_row.addWidget(lbl_criticality)
        summary_layout.addLayout(title_row)
        summary_layout.addWidget(lbl_desc)

        notes = (self._control.get("description") or "").strip()
        if notes:
            lbl_notes = QLabel(f"Note: {notes}")
            lbl_notes.setWordWrap(True)
            lbl_notes.setStyleSheet("color:#657483; font-size:9pt;")
            summary_layout.addWidget(lbl_notes)

        if self._control["control_type"] == "dimensional":
            info = format_tolerance(
                self._control["nominal"],
                self._control["tol_plus"],
                self._control["tol_minus"]
            )
        else:
            info = "Presenza / verifica"
        lbl_info = QLabel(info)
        lbl_info.setStyleSheet(
            "color:#263746; font-size:11pt; font-weight:bold;"
        )
        summary_layout.addWidget(lbl_info)
        self.statistics_widget = None
        if self._control["control_type"] == "dimensional":
            self.statistics_widget = ControlStatisticsWidget(self._control, self._n_samples)
            summary_layout.addWidget(self.statistics_widget)
        layout.addWidget(summary)

        column_header = QFrame()
        column_header.setObjectName("measurementHeader")
        col_hdr = QHBoxLayout(column_header)
        col_hdr.setContentsMargins(10, 7, 10, 7)
        col_hdr.setSpacing(10)
        for text, width in [("Campione", 110), ("Misura", 140)]:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setStyleSheet(
                "color:#536372; font-size:9pt; font-weight:bold;"
            )
            col_hdr.addWidget(lbl)
        lbl_result_header = QLabel("Esito")
        lbl_result_header.setAlignment(Qt.AlignCenter)
        lbl_result_header.setStyleSheet(
            "color:#536372; font-size:9pt; font-weight:bold;"
        )
        col_hdr.addWidget(lbl_result_header, 1)
        layout.addWidget(column_header)

        for sample_num in range(1, self._n_samples + 1):
            row = SampleControlRow(self._control, sample_num, compact=True)
            row.measurement_saved.connect(
                lambda control_id, val_num, val_bool, pass_fail, sample=sample_num:
                self._on_measurement(sample, control_id, val_num, val_bool, pass_fail)
            )
            row.advance_requested.connect(
                lambda index=sample_num - 1: self._focus_next_row(index)
            )
            self._rows.append(row)
            layout.addWidget(row)

        layout.addStretch()
        self.setWidget(container)
        self.setWidgetResizable(True)

    def _focus_next_row(self, current_index: int):
        next_index = current_index + 1
        if next_index >= len(self._rows):
            return
        next_row = self._rows[next_index]
        self.ensureWidgetVisible(next_row)
        next_row.focus_measurement_input()

    def _on_measurement(self, sample_num: int, control_id: int, val_num,
                        val_bool, pass_fail: bool):
        if self.statistics_widget is not None:
            self.statistics_widget.set_measurement(sample_num, val_num)
        self._completed_sample_nums.add(sample_num)
        self.measurement_updated.emit(
            sample_num, control_id, val_num, val_bool, pass_fail
        )
        if (not self._all_done_emitted
                and len(self._completed_sample_nums) >= self._n_samples):
            self._all_done_emitted = True
            self.all_done.emit()

class InspectionStartDialog(QDialog):
    """Raccoglie tutti i dati necessari prima di creare il lotto."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sampling_requirements: dict = {}
        self._profile_override_pair = None
        self._last_profile_pair = None
        self.setWindowTitle("Avvia controllo")
        self.setMinimumWidth(980)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        self.setStyleSheet("""
            QDialog { background: #f4f6f8; }
            QGroupBox {
                background: white;
                border: 1px solid #d8dee5;
                border-radius: 7px;
                margin-top: 10px;
                padding: 12px 10px 8px 10px;
                font-weight: bold;
                color: #263746;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }
            QLineEdit, QComboBox, QSpinBox {
                min-height: 28px;
                background: white;
                border: 1px solid #b7c1cb;
                border-radius: 4px;
                padding: 0 7px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 2px solid #2f75b5;
            }
        """)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background:#1f4e78; border-radius:8px; padding:4px; }"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Avvia nuovo controllo")
        title.setStyleSheet("color:white; font-size:17px; font-weight:bold;")
        intro = QLabel(
            "Seleziona il lotto e il piano: la quantità da controllare "
            "viene calcolata automaticamente."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#e6eef5; font-size:10pt;")
        header_layout.addWidget(title)
        header_layout.addWidget(intro)
        layout.addWidget(header)

        lot_group = QGroupBox("Dati del lotto")
        form = QFormLayout(lot_group)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(9)
        self.cmb_setup = QComboBox()
        self.cmb_setup.setEditable(True)
        self.cmb_setup.setInsertPolicy(QComboBox.NoInsert)
        setups = db.get_all_setups()
        self._setups_by_id = {setup["id"]: setup for setup in setups}
        for setup in setups:
            self.cmb_setup.addItem(setup["name"], setup["id"])
        self.cmb_setup.setCurrentIndex(-1)
        self.cmb_setup.lineEdit().setPlaceholderText(
            "Digita per cercare un setup…"
        )
        setup_completer = QCompleter(self.cmb_setup.model(), self.cmb_setup)
        setup_completer.setCaseSensitivity(Qt.CaseInsensitive)
        setup_completer.setFilterMode(Qt.MatchContains)
        setup_completer.setCompletionMode(QCompleter.PopupCompletion)
        setup_completer.setMaxVisibleItems(12)
        self.cmb_setup.setCompleter(setup_completer)
        self.cmb_setup.currentIndexChanged.connect(
            self._update_sampling_quantity
        )
        self.cmb_setup.currentIndexChanged.connect(self._update_setup_details)
        form.addRow("Carica il setup*:", self.cmb_setup)

        self.txt_setup_description = QLineEdit()
        self.txt_setup_description.setReadOnly(True)
        self.txt_setup_description.setPlaceholderText(
            "La descrizione del setup apparirà qui"
        )
        form.addRow("Descrizione:", self.txt_setup_description)

        self.txt_sampling_class = QLineEdit()
        self.txt_sampling_class.setReadOnly(True)
        self.txt_sampling_class.setPlaceholderText(
            "La classe associata al setup apparirà qui"
        )
        form.addRow("Classe di collaudo:", self.txt_sampling_class)

        self.cmb_supplier = QComboBox()
        self.cmb_supplier.setEditable(True)
        self.cmb_supplier.setInsertPolicy(QComboBox.NoInsert)
        for supplier in db.get_all_suppliers():
            self.cmb_supplier.addItem(supplier["name"], supplier["id"])
        self.cmb_supplier.setCurrentIndex(-1)
        self.cmb_supplier.lineEdit().setPlaceholderText(
            "Digita per cercare un fornitore…"
        )
        supplier_completer = QCompleter(
            self.cmb_supplier.model(), self.cmb_supplier
        )
        supplier_completer.setCaseSensitivity(Qt.CaseInsensitive)
        supplier_completer.setFilterMode(Qt.MatchContains)
        supplier_completer.setCompletionMode(QCompleter.PopupCompletion)
        supplier_completer.setMaxVisibleItems(12)
        self.cmb_supplier.setCompleter(supplier_completer)
        form.addRow("Fonitore*:", self.cmb_supplier)

        self.txt_lot_code = QLineEdit()
        self.txt_lot_code.setPlaceholderText("Numero o codice del lotto")
        form.addRow("N° lotto*:", self.txt_lot_code)

        self.spn_lot_quantity = QSpinBox()
        self.spn_lot_quantity.setRange(1, 999999999)
        self.spn_lot_quantity.setValue(100)
        self.spn_lot_quantity.valueChanged.connect(self._update_percentage)
        self.spn_lot_quantity.valueChanged.connect(
            self._update_sampling_quantity
        )
        form.addRow("Q.tà del lotto*:", self.spn_lot_quantity)
        layout.addWidget(lot_group)

        history_group = QGroupBox("Controlli precedenti")
        history_layout = QVBoxLayout(history_group)
        history_layout.setSpacing(6)
        self.lbl_previous_inspections = QLabel()
        self.lbl_previous_inspections.setWordWrap(True)
        self.lbl_previous_inspections.setStyleSheet(
            "font-weight:normal; color:#435363;"
        )
        self.lbl_previous_inspections.setMaximumHeight(42)
        self.lbl_previous_inspections.setAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )
        history_layout.addWidget(self.lbl_previous_inspections)

        self.tbl_previous_inspections = QTableWidget(0, 4)
        self.tbl_previous_inspections.setHorizontalHeaderLabels(
            ["Data", "Lotto", "Esito", "Stato"]
        )
        self.tbl_previous_inspections.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.tbl_previous_inspections.setSelectionMode(
            QTableWidget.NoSelection
        )
        self.tbl_previous_inspections.setFocusPolicy(Qt.NoFocus)
        self.tbl_previous_inspections.setAlternatingRowColors(True)
        self.tbl_previous_inspections.verticalHeader().setVisible(False)
        self.tbl_previous_inspections.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.tbl_previous_inspections.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.tbl_previous_inspections.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.tbl_previous_inspections.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.tbl_previous_inspections.setMaximumHeight(176)
        history_layout.addWidget(self.tbl_previous_inspections)
        details_layout = QHBoxLayout()
        details_layout.setSpacing(12)
        details_layout.addWidget(history_group, 3)

        self.cmb_setup.currentIndexChanged.connect(
            self._update_previous_inspections
        )
        self.cmb_supplier.currentIndexChanged.connect(
            self._update_previous_inspections
        )

        sampling_group = QGroupBox("Piano di campionamento")
        sampling_form = QFormLayout(sampling_group)
        sampling_form.setHorizontalSpacing(18)
        sampling_form.setVerticalSpacing(9)

        self.cmb_sampling_profile = QComboBox()
        self._sampling_colors = {
            "ESTESO": ("#f9ddd2", "#8a2f0b", "#cf6840"),
            "NORMALE": ("#dcecf8", "#174a78", "#4b88b7"),
            "RIDOTTO": ("#dff0e3", "#245d2c", "#619b69"),
        }
        for profile, label in (
            ("ESTESO", "Esteso — controllo più ampio"),
            ("NORMALE", "Normale — piano standard"),
            ("RIDOTTO", "Ridotto — controllo ridotto"),
        ):
            background, foreground, _ = self._sampling_colors[profile]
            swatch = QPixmap(14, 14)
            swatch.fill(QColor(background))
            self.cmb_sampling_profile.addItem(QIcon(swatch), label, profile)
            index = self.cmb_sampling_profile.count() - 1
            self.cmb_sampling_profile.setItemData(
                index, QColor(background), Qt.BackgroundRole
            )
            self.cmb_sampling_profile.setItemData(
                index, QColor(foreground), Qt.ForegroundRole
            )
        self.cmb_sampling_profile.setCurrentIndex(1)
        self.cmb_sampling_profile.currentIndexChanged.connect(
            self._on_sampling_profile_changed
        )
        self.cmb_sampling_profile.activated.connect(
            self._on_sampling_profile_manually_selected
        )
        sampling_form.addRow("Tipo di piano*:", self.cmb_sampling_profile)

        self.lbl_profile_recommendation = QLabel(
            "Seleziona setup e fornitore per calcolare il piano suggerito."
        )
        self.lbl_profile_recommendation.setWordWrap(True)
        self.lbl_profile_recommendation.setStyleSheet(
            "color:#52616e; background:#eef2f5; border:1px solid #d8dee5; "
            "border-radius:4px; padding:5px;"
        )
        sampling_form.addRow("Piano Suggerito:", self.lbl_profile_recommendation)

        self.spn_samples = QSpinBox()
        self.spn_samples.setRange(1, 999999999)
        self.spn_samples.setReadOnly(True)
        self.spn_samples.setButtonSymbols(QSpinBox.NoButtons)
        self.spn_samples.setToolTip(
            "Valore calcolato automaticamente dal piano di campionamento."
        )
        self.spn_samples.setValue(1)
        self.spn_samples.valueChanged.connect(self._update_sequential_state)
        self.spn_samples.valueChanged.connect(self._update_percentage)
        sampling_form.addRow("Q.tà da controllare:", self.spn_samples)

        calculation_widget = QWidget()
        calculation_layout = QVBoxLayout(calculation_widget)
        calculation_layout.setContentsMargins(0, 0, 0, 0)
        calculation_layout.setSpacing(7)

        calculation_title = QLabel("Calcolo applicato")
        calculation_title.setStyleSheet("font-weight:bold; color:#263746;")
        calculation_layout.addWidget(calculation_title)

        self.lbl_sampling_interval = QLabel()
        self.lbl_sampling_interval.setWordWrap(True)
        self.lbl_sampling_interval.setAlignment(Qt.AlignVCenter)
        calculation_layout.addWidget(self.lbl_sampling_interval)

        cards_layout = QHBoxLayout()
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(7)
        self._sampling_cards = {}
        card_styles = {
            "C": ("CRITICA", "#fdecec", "#8b1a1a", "#d99a9a"),
            "I": ("IMPORTANTE", "#fff4df", "#6b4a0b", "#dfbd76"),
            "N": ("NORMALE", "#edf5ed", "#245b2a", "#9bc39f"),
        }
        for criticality in ("C", "I", "N"):
            title_text, background, foreground, border = card_styles[criticality]
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background:{background}; border:1px solid {border}; "
                "border-radius:5px; } "
                f"QLabel {{ border:none; color:{foreground}; background:transparent; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(3)
            card_title = QLabel(title_text)
            card_title.setAlignment(Qt.AlignCenter)
            card_title.setStyleSheet("font-weight:bold;")
            card_value = QLabel("—")
            card_value.setAlignment(Qt.AlignCenter)
            card_value.setMinimumHeight(20)
            card_value.setStyleSheet("font-size:9pt;")
            card_layout.addWidget(card_title)
            card_layout.addWidget(card_value)
            cards_layout.addWidget(card, 1)
            self._sampling_cards[criticality] = card_value
        calculation_layout.addLayout(cards_layout)
        sampling_form.addRow(calculation_widget)

        self.lbl_percentage = QLabel()
        self.lbl_percentage.setAlignment(Qt.AlignCenter)
        self.lbl_percentage.setStyleSheet(
            "font-weight:bold; color:#1a5c1a; padding:7px; "
            "background:#e8f5e8; border:1px solid #bedcbe; border-radius:5px;"
        )
        sampling_form.addRow("", self.lbl_percentage)
        details_layout.addWidget(sampling_group, 4)
        layout.addLayout(details_layout)

        execution_group = QGroupBox("Esecuzione")
        execution_form = QFormLayout(execution_group)
        execution_form.setHorizontalSpacing(18)
        execution_form.setVerticalSpacing(9)
        self.chk_sequential = QCheckBox("Inserimento controllo per controllo")
        self.chk_sequential.setToolTip(
            "Disponibile quando la quantità da controllare è maggiore di 2."
        )
        self._sequential_preference = True
        self.chk_sequential.setChecked(True)
        self.chk_sequential.toggled.connect(
            self._remember_sequential_preference
        )
        execution_form.addRow("Modalità inserimento:", self.chk_sequential)

        self.cmb_operator = QComboBox()
        self.cmb_operator.addItem("Seleziona operatore…", None)
        for operator in db.get_all_operators():
            self.cmb_operator.addItem(operator["name"], operator["id"])
        execution_form.addRow("Nome operatore*:", self.cmb_operator)
        layout.addWidget(execution_group)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText("Avvia controllo")
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._sampling_valid = False
        self._apply_sampling_profile_style()
        self._update_setup_details()
        self._update_sampling_quantity()
        self._update_previous_inspections()
        self._update_sequential_state()
        self._update_percentage()

    def _selected_sampling_profile(self) -> str:
        return self.cmb_sampling_profile.currentData() or "NORMALE"

    def _on_sampling_profile_changed(self, *_):
        self._apply_sampling_profile_style()
        self._update_sampling_quantity()

    def _on_sampling_profile_manually_selected(self, *_):
        pair = (self.cmb_setup.currentData(), self.cmb_supplier.currentData())
        if None not in pair:
            self._profile_override_pair = pair
            self.lbl_profile_recommendation.setText(
                "Scelta manuale dell'operatore: il piano non verrà "
                "sovrascritto dai ricalcoli."
            )
            self.lbl_profile_recommendation.setStyleSheet(
                "color:#664d03; background:#fff3cd; border:1px solid #dfbd76; "
                "border-radius:4px; padding:5px;"
            )

    def _apply_sampling_profile_style(self):
        profile = self._selected_sampling_profile()
        background, foreground, border = self._sampling_colors[profile]
        self.cmb_sampling_profile.setStyleSheet(
            "QComboBox {"
            f"background:{background}; color:{foreground}; "
            f"border:2px solid {border}; font-weight:bold;"
            "}"
            "QComboBox::drop-down { border:0; width:28px; }"
        )

    def _set_sampling_result(
            self, text: str, valid: bool, requirements: dict | None = None,
            present_criticalities: set | None = None):
        self._sampling_valid = valid
        color = "#155724" if valid else "#8b1a1a"
        background = "#e8f5e8" if valid else "#fdecec"
        self.lbl_sampling_interval.setText(text)
        self.lbl_sampling_interval.setStyleSheet(
            f"color:{color}; background:{background}; padding:5px; "
            "border-radius:4px;"
        )
        requirements = requirements or {}
        present_criticalities = present_criticalities or set()
        for criticality, label in self._sampling_cards.items():
            requirement = requirements.get(criticality)
            if requirement is None:
                label.setText("—")
            elif criticality not in present_criticalities:
                label.setText("Non presente nel setup")
            else:
                label.setText(
                    f"n = {requirement['n']} · "
                    f"Ac = {requirement['ac']} · Re = {requirement['re']}"
                )

    def _update_setup_details(self, *_):
        setup = self._setups_by_id.get(self.cmb_setup.currentData())
        if setup is None:
            self.txt_setup_description.clear()
            self.txt_sampling_class.clear()
            return
        self.txt_setup_description.setText(setup.get("description") or "—")
        class_code = setup.get("sampling_class_code") or "—"
        class_description = setup.get("sampling_class_description") or ""
        class_text = (
            f"{class_code} — {class_description}"
            if class_description else class_code
        )
        self.txt_sampling_class.setText(class_text)

    def _update_previous_inspections(self, *_):
        setup_id = self.cmb_setup.currentData()
        supplier_id = self.cmb_supplier.currentData()
        self.tbl_previous_inspections.setRowCount(0)

        if setup_id is None or supplier_id is None:
            self.lbl_profile_recommendation.setText(
                "Seleziona setup e fornitore per calcolare il piano suggerito."
            )
            self.lbl_previous_inspections.setText(
                "Seleziona setup e fornitore per verificare lo storico."
            )
            self.tbl_previous_inspections.setVisible(False)
            return

        supplier_name = self.cmb_supplier.currentText().strip().casefold()
        matching_lots = []
        for lot in db.get_lot_history_for_setup(int(setup_id)):
            same_supplier_id = lot.get("supplier_id") == supplier_id
            same_legacy_name = (
                lot.get("supplier_id") is None
                and supplier_name
                and str(lot.get("supplier") or "").strip().casefold()
                == supplier_name
            )
            if same_supplier_id or same_legacy_name:
                matching_lots.append(lot)

        self._apply_recommended_sampling_profile(
            int(setup_id), supplier_id, matching_lots
        )

        if not matching_lots:
            self.lbl_previous_inspections.setText(
                "Nessun controllo precedente per questo setup e fornitore."
            )
            self.tbl_previous_inspections.setVisible(False)
            return

        completed_count = sum(
            1 for lot in matching_lots
            if lot.get("closed") and not lot.get("cancelled")
        )
        visible_lots = matching_lots[:5]
        self.lbl_previous_inspections.setText(
            f"{len(matching_lots)} controlli registrati · "
            f"{completed_count} conclusi · ultimi {len(visible_lots)}:"
        )
        self.tbl_previous_inspections.setVisible(True)
        self.tbl_previous_inspections.setRowCount(len(visible_lots))
        for row, lot in enumerate(visible_lots):
            values = (
                self._format_history_datetime(lot.get("created_at")),
                lot.get("lot_code") or "—",
                lot.get("result") or "—",
                lot.get("state") or "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    Qt.AlignVCenter | (
                        Qt.AlignLeft if column == 1 else Qt.AlignHCenter
                    )
                )
                if column == 2:
                    self._style_history_result(item, lot.get("result"))
                elif column == 3 and lot.get("state") == "ANNULLATO":
                    item.setForeground(QBrush(QColor("#555555")))
                    item.setBackground(QBrush(QColor("#eeeeee")))
                self.tbl_previous_inspections.setItem(row, column, item)

        self.tbl_previous_inspections.resizeRowsToContents()

    def _apply_recommended_sampling_profile(
            self, setup_id: int, supplier_id: int,
            matching_lots: list[dict]):
        pair = (setup_id, supplier_id)
        if pair != self._last_profile_pair:
            self._last_profile_pair = pair
            self._profile_override_pair = None

        setup = self._setups_by_id.get(setup_id) or {}
        recommendation = recommend_sampling_profile(matching_lots, setup)
        suggested_profile = recommendation["profile"]
        suggested_index = self.cmb_sampling_profile.findData(suggested_profile)
        manual_override = self._profile_override_pair == pair
        if not manual_override and suggested_index >= 0:
            self.cmb_sampling_profile.setCurrentIndex(suggested_index)

        last_date = recommendation.get("last_date")
        date_text = (
            f" · Ultimo controllo: {last_date.strftime('%d/%m/%Y')}"
            if last_date is not None else ""
        )
        if manual_override:
            text = (
                f"Scelta manuale: {self._selected_sampling_profile()} · "
                f"Suggerito: {suggested_profile} — "
                f"{recommendation['reason']}{date_text}"
            )
            colors = ("#664d03", "#fff3cd", "#dfbd76")
        else:
            text = (
                f"{recommendation['reason']}{date_text}"
            )
            colors = ("#174a78", "#e8f1f8", "#9fc1dc")
        foreground, background, border = colors
        self.lbl_profile_recommendation.setText(text)
        self.lbl_profile_recommendation.setStyleSheet(
            f"color:{foreground}; background:{background}; "
            f"border:1px solid {border}; border-radius:4px; padding:5px;"
        )

    @staticmethod
    def _format_history_datetime(value) -> str:
        if not value:
            return "—"
        text = str(value)
        if len(text) >= 16:
            return f"{text[8:10]}/{text[5:7]}/{text[:4]} {text[11:16]}"
        return text

    @staticmethod
    def _style_history_result(item: QTableWidgetItem, result: str):
        colors = {
            "PASS": ("#155724", "#d4edda"),
            "FAIL": ("#721c24", "#f8d7da"),
            "ACCETTATO IN DEROGA": ("#7a4b00", "#fff3cd"),
            "INCOMPLETO": ("#7a4b00", "#fff3cd"),
        }
        foreground, background = colors.get(
            result, ("#435363", "#f4f6f8")
        )
        item.setForeground(QBrush(QColor(foreground)))
        item.setBackground(QBrush(QColor(background)))

    def _update_sampling_quantity(self, *_):
        self._sampling_requirements = {}
        profile = self._selected_sampling_profile()
        lot_quantity = self.spn_lot_quantity.value()
        setup_id = self.cmb_setup.currentData()
        if setup_id is None:
            self.spn_samples.setValue(1)
            self._set_sampling_result(
                "Seleziona un setup per calcolare la quantità da controllare.",
                False,
            )
            return

        selected_setup = self._setups_by_id.get(int(setup_id)) or {}
        controls = db.get_revision_controls(
            selected_setup.get("setup_revision_id")
        )
        if not controls:
            self.spn_samples.setValue(1)
            self._set_sampling_result(
                "Il setup selezionato non contiene controlli configurati.", False
            )
            return

        criticalities = {
            control.get("criticality") or "N" for control in controls
        }

        setup = db.get_setup(int(setup_id))
        sampling_class_id = (setup or {}).get("sampling_class_id")
        if sampling_class_id is None:
            self.spn_samples.setValue(1)
            self._set_sampling_result(
                "Il setup non ha una Classe di Collaudo associata.", False
            )
            return

        if lot_quantity == 1:
            self._sampling_requirements = {
                criticality: {"n": 1, "ac": 0, "re": 1}
                for criticality in ("C", "I", "N")
            }
            self.spn_samples.setValue(1)
            self._set_sampling_result(
                "Lotto unitario: controllo dell'intero lotto",
                True,
                self._sampling_requirements,
                criticalities,
            )
            return

        plan_row = db.get_sampling_plan_for_quantity(
            profile, lot_quantity, sampling_class_id
        )
        if plan_row is None:
            self.spn_samples.setValue(1)
            self._set_sampling_result(
                f"{profile}: nessun intervallo configurato per un lotto di "
                f"{lot_quantity} pezzi.",
                False,
            )
            return

        prefix_by_criticality = {
            "C": "critical", "I": "important", "N": "normal",
        }
        requirements = {}
        for criticality, prefix in prefix_by_criticality.items():
            planned_n = int(plan_row[f"{prefix}_n"])
            sample_n = min(planned_n, lot_quantity)
            acceptance = int(plan_row[f"{prefix}_ac"])
            rejection = int(plan_row[f"{prefix}_re"])
            if sample_n < rejection:
                rejection = sample_n
                acceptance = min(acceptance, rejection - 1)
            requirements[criticality] = {
                "n": sample_n,
                "ac": acceptance,
                "re": rejection,
            }

        self._sampling_requirements = requirements
        samples = max(
            requirements[criticality]["n"] for criticality in criticalities
        )
        self.spn_samples.setValue(samples)

        lot_max = plan_row.get("lot_max")
        range_text = f"{plan_row['lot_min']}–{'∞' if lot_max is None else lot_max}"
        self._set_sampling_result(
            f"Intervallo lotto applicato: {range_text} pezzi",
            True,
            requirements,
            criticalities,
        )

    def _update_sequential_state(self):
        enabled = self.spn_samples.value() > 2
        self.chk_sequential.blockSignals(True)
        self.chk_sequential.setEnabled(enabled)
        self.chk_sequential.setChecked(
            self._sequential_preference if enabled else False
        )
        self.chk_sequential.blockSignals(False)

    def _remember_sequential_preference(self, checked: bool):
        if self.chk_sequential.isEnabled():
            self._sequential_preference = checked

    def _update_percentage(self):
        percentage = (
            self.spn_samples.value() / self.spn_lot_quantity.value() * 100
        )
        text = f"{percentage:.2f}".rstrip("0").rstrip(".")
        self.lbl_percentage.setText(f"Percentuale di controllo: {text}%")

    def _validate_and_accept(self):
        setup_id = self._selected_setup_id()
        if setup_id is None:
            QMessageBox.warning(self, "Dati mancanti", "Seleziona il setup.")
            return
        setup = self._setups_by_id.get(setup_id) or {}
        if not db.get_revision_controls(setup.get("setup_revision_id")):
            QMessageBox.warning(
                self, "Setup non valido",
                "Il setup selezionato non contiene controlli configurati."
            )
            return
        self._update_sampling_quantity()
        if not self._sampling_valid:
            QMessageBox.warning(
                self, "Piano non valido",
                "Non è possibile calcolare la quantità da controllare con il "
                "piano selezionato. Verifica i piani in Configurazione."
            )
            return
        if self._selected_supplier_id() is None:
            QMessageBox.warning(self, "Dati mancanti", "Seleziona il fornitore.")
            return
        if not self.txt_lot_code.text().strip():
            QMessageBox.warning(self, "Dati mancanti", "Inserisci il numero del lotto.")
            return
        if self.spn_samples.value() > self.spn_lot_quantity.value():
            QMessageBox.warning(
                self, "Quantità non valida",
                "La quantità da controllare non può superare la quantità del lotto."
            )
            return
        if self.cmb_operator.currentData() is None:
            QMessageBox.warning(self, "Dati mancanti", "Seleziona l'operatore.")
            return
        self.accept()

    def _selected_setup_id(self):
        return self._selected_combo_data(self.cmb_setup)

    def _selected_supplier_id(self):
        return self._selected_combo_data(self.cmb_supplier)

    @staticmethod
    def _selected_combo_data(combo: QComboBox):
        current_data = combo.currentData()
        if current_data is not None:
            return current_data
        typed_text = combo.currentText().strip().casefold()
        for index in range(combo.count()):
            if combo.itemText(index).strip().casefold() == typed_text:
                combo.setCurrentIndex(index)
                return combo.itemData(index)
        return None

    def inspection_data(self) -> dict:
        setup = self._setups_by_id.get(self._selected_setup_id()) or {}
        return {
            "setup_id": self._selected_setup_id(),
            "setup_revision_id": setup.get("setup_revision_id"),
            "supplier": self.cmb_supplier.currentText().strip(),
            "supplier_id": self._selected_supplier_id(),
            "lot_code": self.txt_lot_code.text().strip(),
            "lot_quantity": self.spn_lot_quantity.value(),
            "n_samples": self.spn_samples.value(),
            "sampling_profile": self._selected_sampling_profile(),
            "sequential": self.chk_sequential.isChecked(),
            "operator": self.cmb_operator.currentText().strip(),
            "operator_id": self.cmb_operator.currentData(),
            "sampling_requirements": {
                criticality: dict(values)
                for criticality, values in self._sampling_requirements.items()
            },
        }


class InspectionWindow(QMainWindow):
    """Finestra principale di controllo."""

    def __init__(self, parent=None, setup_id: int | None = None,
                 startup_data: dict | None = None):
        super().__init__(parent)
        self._setup_id = setup_id
        self._setup_revision_id: int | None = None
        self._setup: dict = {}
        self._lot_id: int | None = None
        self._controls: list = []
        self._draft_measurements: dict[tuple[int, int], dict] = {}
        self._n_samples = 1
        self._current_sample = 1
        self._sequential_mode = False
        self._completed_sample_nums: set[int] = set()
        self._completed_sequence_control_ids: set[int] = set()
        self._inspection_running = False
        self._operator = ""
        self._operator_id = None
        self._supplier = ""
        self._supplier_id = None
        self._lot_code = ""
        self._lot_quantity = 1
        self._sampling_profile = ""
        self._sampling_requirements: dict = {}
        self._allow_close = False
        self._measurement_sound = MeasurementSoundPlayer(self)
        self.setWindowTitle("QC Inspector — Controllo")
        self.setFont(QFont("Arial", 11))
        self.resize(1280, 800)
        self._build_ui()
        if startup_data:
            self._apply_startup_data(startup_data)
            self._on_start_inspection()
        elif setup_id:
            self._load_setup(setup_id)

    def _apply_startup_data(self, data: dict):
        self._load_setup(data["setup_id"], data.get("setup_revision_id"))
        self._lot_code = data["lot_code"]
        self._lot_quantity = data["lot_quantity"]
        self._n_samples = data["n_samples"]
        self._sampling_profile = data["sampling_profile"]
        self._sampling_requirements = {
            criticality: dict(values)
            for criticality, values in data.get(
                "sampling_requirements", {}
            ).items()
        }
        self._sequential_mode = data["sequential"]
        self._operator = data["operator"]
        self._operator_id = data.get("operator_id")
        self._supplier = data["supplier"]
        self._supplier_id = data.get("supplier_id")
        self.lbl_lot_code.setText(self._lot_code)
        self.lbl_lot_quantity.setText(str(self._lot_quantity))
        self.lbl_samples.setText(self._sampling_counts_text())
        self.lbl_sampling_profile.setText(self._sampling_profile.title())
        self.lbl_operator.setText(self._operator)
        self.lbl_supplier.setText(self._supplier)

    # ─── Build UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("inspectionRoot")
        central.setStyleSheet("""
            QWidget#inspectionRoot { background:#e9edf2; }
            QWidget#controlPane { background:#f4f6f8; }
            QSplitter::handle { background:#c7d0d9; width:6px; }
            QFrame#navigationCard, QFrame#controlSummary,
            QFrame#inspectionFooter {
                background:white; border:1px solid #d4dce4;
                border-radius:7px;
            }
            QFrame#measurementHeader {
                background:#e8edf2; border:1px solid #d4dce4;
                border-radius:4px;
            }
            QWidget#samplePanel { background:#f7f9fb; }
            QWidget#measurementRowOdd {
                background:white; border-bottom:1px solid #e1e6eb;
            }
            QWidget#measurementRowEven {
                background:#f1f5f8; border-bottom:1px solid #e1e6eb;
            }
            QTabWidget::pane {
                background:#f7f9fb; border:1px solid #cfd8e1;
                border-radius:5px;
            }
            QTabBar::tab {
                background:#e3e8ed; color:#435363; border:1px solid #c9d2db;
                padding:7px 13px; margin-right:2px;
            }
            QTabBar::tab:selected {
                background:white; color:#174a78; border-bottom-color:white;
                font-weight:bold;
            }
            QTabBar::tab:hover { background:#edf3f7; }
            QProgressBar {
                min-height:18px; border:1px solid #c6d0da;
                border-radius:5px; background:#eef2f5; text-align:center;
                color:#263746; font-weight:bold;
            }
            QProgressBar::chunk { background:#2f75b5; border-radius:4px; }
            QScrollBar:vertical { width:12px; background:#edf1f4; }
            QScrollBar::handle:vertical {
                background:#aab7c3; border-radius:5px; min-height:28px;
            }
        """)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Info bar
        main_layout.addWidget(self._build_info_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)

        # PDF viewer (sola lettura)
        self.viewer = PdfViewerWidget()
        self.viewer.edit_mode = False
        self.viewer.balloon_clicked.connect(self._on_balloon_clicked)
        splitter.addWidget(self.viewer)

        # Pannello destra: tab campioni + sommario
        right_panel = QWidget()
        right_panel.setObjectName("controlPane")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 10, 12, 10)
        right_layout.setSpacing(9)

        # Navigazione campioni
        nav_box = QFrame()
        nav_box.setObjectName("navigationCard")
        nav_layout = QVBoxLayout(nav_box)
        nav_layout.setContentsMargins(12, 9, 12, 9)
        nav_layout.setSpacing(7)
        nav_top = QHBoxLayout()

        self.lbl_sample_info = QLabel("Campione: —")
        self.lbl_sample_info.setFont(QFont("Arial", 12, QFont.Bold))
        self.lbl_sample_info.setStyleSheet("color:#263746;")
        nav_top.addWidget(self.lbl_sample_info)

        nav_top.addStretch()

        self.btn_prev_sample = QPushButton("Precedente")
        self.btn_prev_sample.setIcon(
            self.style().standardIcon(QStyle.SP_ArrowBack)
        )
        self.btn_prev_sample.setMinimumHeight(30)
        self.btn_prev_sample.clicked.connect(self._go_to_previous_panel)
        nav_top.addWidget(self.btn_prev_sample)

        self.btn_next_sample = QPushButton("Successivo")
        self.btn_next_sample.setIcon(
            self.style().standardIcon(QStyle.SP_ArrowForward)
        )
        self.btn_next_sample.setMinimumHeight(30)
        self.btn_next_sample.clicked.connect(self._go_to_next_panel)
        nav_top.addWidget(self.btn_next_sample)
        nav_layout.addLayout(nav_top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        nav_layout.addWidget(self.progress)

        right_layout.addWidget(nav_box)

        # Area campioni (stack)
        self.sample_stack = QTabWidget()
        self.sample_stack.setTabPosition(QTabWidget.North)
        self.sample_stack.setDocumentMode(True)
        self.sample_stack.setUsesScrollButtons(True)
        self.sample_stack.currentChanged.connect(self._on_panel_changed)
        right_layout.addWidget(self.sample_stack)

        # Bottoni finali
        footer = QFrame()
        footer.setObjectName("inspectionFooter")
        btn_row = QHBoxLayout(footer)
        btn_row.setContentsMargins(10, 8, 10, 8)
        btn_row.setSpacing(10)

        self.lbl_lot_result = QLabel("In attesa di misure")
        self.lbl_lot_result.setFont(QFont("Arial", 11, QFont.Bold))
        self.lbl_lot_result.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.lbl_lot_result.setMinimumHeight(38)
        self.lbl_lot_result.setWordWrap(True)
        self.lbl_lot_result.setStyleSheet(
            "color:#536372; background:#eef2f5; border:1px solid #cbd4dc; "
            "border-radius:5px; padding:5px 12px;"
        )
        btn_row.addWidget(self.lbl_lot_result, 1)

        self.btn_report = QPushButton("Salva controllo / Genera report")
        self.btn_report.setIcon(
            self.style().standardIcon(QStyle.SP_DialogSaveButton)
        )
        self.btn_report.setMinimumWidth(285)
        self.btn_report.setMinimumHeight(42)
        self.btn_report.setStyleSheet(
            "QPushButton { background:#1a7abf; color:white; padding:8px 16px; "
            "border-radius:4px; font-weight:bold; font-size:12pt; }"
            "QPushButton:hover { background:#1560a0; }"
            "QPushButton:disabled { background:#c4ccd3; color:#f5f7f8; }"
        )
        self.btn_report.clicked.connect(self._on_generate_report)
        self.btn_report.setEnabled(False)
        btn_row.addWidget(self.btn_report)

        right_layout.addWidget(footer)

        right_panel.setMinimumWidth(500)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([760, 520])

        main_layout.addWidget(splitter)
        self.statusBar().showMessage("Pronto — Seleziona un setup per iniziare il controllo")

    def _build_info_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("inspectionHeader")
        bar.setFixedHeight(88)
        bar.setStyleSheet("""
            QFrame#inspectionHeader {
                background:#f8fafb; border-bottom:1px solid #c8d1da;
            }
            QFrame#infoChip {
                background:white; border:1px solid #d5dde5;
                border-radius:5px;
            }
            QLabel#chipTitle { color:#6a7885; font-size:8pt; }
            QLabel#chipValue {
                color:#263746; font-size:10pt; font-weight:bold;
            }
        """)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        mode_label = QLabel("CONTROLLO QUALITÀ")
        mode_label.setStyleSheet(
            "color:#2f75b5; font-size:9pt; font-weight:bold;"
        )
        top_row.addWidget(mode_label)
        setup_title = QLabel("Setup")
        setup_title.setStyleSheet("color:#697887;")
        top_row.addWidget(setup_title)
        self.lbl_setup_name = QLabel("—")
        self.lbl_setup_name.setFont(QFont("Arial", 12, QFont.Bold))
        self.lbl_setup_name.setStyleSheet("color:#1f3346;")
        top_row.addWidget(self.lbl_setup_name)

        separator = QLabel("•")
        separator.setStyleSheet("color:#9aa7b3;")
        top_row.addWidget(separator)
        lot_title = QLabel("Lotto")
        lot_title.setStyleSheet("color:#697887;")
        top_row.addWidget(lot_title)
        self.lbl_lot_code = QLabel("—")
        self.lbl_lot_code.setFont(QFont("Arial", 11, QFont.Bold))
        self.lbl_lot_code.setStyleSheet("color:#1f3346;")
        top_row.addWidget(self.lbl_lot_code)
        top_row.addStretch()

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setMinimumHeight(31)
        self.btn_fullscreen.setStyleSheet(
            "QPushButton { background:#eef2f5; color:#263746; padding:4px 10px; "
            "border:1px solid #c8d1da; border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:white; }"
        )
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        top_row.addWidget(self.btn_fullscreen)

        self._fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self._fullscreen_shortcut.activated.connect(self._toggle_fullscreen)
        self._fullscreen_escape_shortcut = QShortcut(
            QKeySequence(Qt.Key_Escape), self
        )
        self._fullscreen_escape_shortcut.activated.connect(
            self._exit_fullscreen
        )
        self._update_fullscreen_control()

        self.btn_start = QPushButton("Avvia Controllo")
        self.btn_start.setIcon(
            self.style().standardIcon(QStyle.SP_MediaPlay)
        )
        self.btn_start.setMinimumHeight(31)
        self.btn_start.setStyleSheet(
            "QPushButton { background:#2e7d32; color:white; padding:4px 12px; "
            "border-radius:4px; font-weight:bold; font-size:10pt; }"
            "QPushButton:disabled { background:#bdbdbd; color:#f5f5f5; }"
        )
        self.btn_start.clicked.connect(self._on_start_or_cancel_inspection)
        self.btn_start.setEnabled(False)
        top_row.addWidget(self.btn_start)

        self.lbl_page = QLabel("Pagina: —")
        self.lbl_page.setStyleSheet("color:#536372; font-weight:bold;")
        top_row.addWidget(self.lbl_page)

        btn_prev_p = QPushButton()
        btn_prev_p.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        btn_prev_p.setFixedWidth(28)
        btn_prev_p.clicked.connect(lambda: self._change_page(-1))
        top_row.addWidget(btn_prev_p)

        btn_next_p = QPushButton()
        btn_next_p.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        btn_next_p.setFixedWidth(28)
        btn_next_p.clicked.connect(lambda: self._change_page(1))
        top_row.addWidget(btn_next_p)
        layout.addLayout(top_row)

        details_row = QHBoxLayout()
        details_row.setSpacing(7)

        def add_info_chip(title: str, maximum_width: int = 0) -> QLabel:
            chip = QFrame()
            chip.setObjectName("infoChip")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 3, 8, 3)
            chip_layout.setSpacing(6)
            title_label = QLabel(title)
            title_label.setObjectName("chipTitle")
            value_label = QLabel("—")
            value_label.setObjectName("chipValue")
            if maximum_width:
                value_label.setMaximumWidth(maximum_width)
            chip_layout.addWidget(title_label)
            chip_layout.addWidget(value_label)
            details_row.addWidget(chip)
            return value_label

        self.lbl_supplier = add_info_chip("Fornitore", 220)
        self.lbl_lot_quantity = add_info_chip("Quantità lotto")
        self.lbl_samples = add_info_chip("Campionamento")
        self.lbl_sampling_profile = add_info_chip("Piano")
        self.lbl_operator = add_info_chip("Operatore", 190)
        details_row.addStretch()
        layout.addLayout(details_row)

        return bar

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
        if not hasattr(self, "btn_fullscreen"):
            return
        fullscreen = self.isFullScreen()
        text = "Esci da schermo intero" if fullscreen else "Schermo intero"
        icon = (
            QStyle.SP_TitleBarNormalButton
            if fullscreen else QStyle.SP_TitleBarMaxButton
        )
        self.btn_fullscreen.setText(text)
        self.btn_fullscreen.setIcon(self.style().standardIcon(icon))
        self.btn_fullscreen.setToolTip(f"{text} (F11)")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._update_fullscreen_control()

    # ─── Caricamento ─────────────────────────────────────────────────────────

    def _load_setup(self, setup_id: int, revision_id: int | None = None):
        current_setup = db.get_setup(setup_id)
        if not current_setup:
            return
        revision_id = revision_id or current_setup.get("setup_revision_id")
        setup = db.get_setup_revision(revision_id) if revision_id else None
        if not setup:
            QMessageBox.critical(
                self, "Setup non disponibile",
                "Non è disponibile una revisione valida del setup selezionato."
            )
            return
        self._setup_id = setup_id
        self._setup_revision_id = int(revision_id)
        self._setup = setup
        self._controls = db.get_revision_controls(self._setup_revision_id)
        revision_text = f"Rev. {setup['version_number']}"
        self.lbl_setup_name.setText(f"{setup['name']} — {revision_text}")

        if self.viewer.load_pdf(setup["pdf_path"]):
            self._update_page_label()

        # Mostra balloon in modalità view
        balloon_data = [dict(c, pass_fail=None) for c in self._controls]
        self.viewer.load_balloons(balloon_data)

        self.setWindowTitle(
            f"QC Inspector — Controllo  |  {setup['name']} {revision_text}  |  "
            f"{len(self._controls)} controlli"
        )
        self.statusBar().showMessage(
            f"Setup '{setup['name']}' {revision_text} caricato — "
            "inserisci il codice lotto e avvia il controllo"
        )

    def _on_start_or_cancel_inspection(self):
        if self._inspection_running:
            if self._confirm_cancel_inspection():
                self._allow_close = True
                self.close()
            return

        self._on_start_inspection()

    def _confirm_cancel_inspection(self) -> bool:
        reply = QMessageBox.question(
            self,
            "Annullare il controllo",
            "Il controllo è ancora in corso. Vuoi interromperlo?\n\n"
            "Tutti i dati e le misure inseriti saranno persi. "
            "Il controllo non verrà salvato nello storico.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False
        self._draft_measurements.clear()
        self._inspection_running = False
        return True

    def closeEvent(self, event):
        if self._allow_close or not self._inspection_running:
            event.accept()
            return
        if self._confirm_cancel_inspection():
            self._allow_close = True
            event.accept()
        else:
            event.ignore()

    def _on_start_inspection(self):
        if not self._setup_id or not self._setup_revision_id:
            QMessageBox.warning(self, "Controllo", "Carica prima un setup.")
            return
        lot_code = self._lot_code
        if not lot_code:
            QMessageBox.warning(self, "Controllo", "Inserisci il codice lotto.")
            return
        if not self._controls:
            QMessageBox.warning(self, "Controllo",
                                "Il setup non ha controlli configurati.")
            return

        self._completed_sample_nums.clear()
        self._completed_sequence_control_ids.clear()
        self._draft_measurements.clear()
        self._lot_id = None

        self._build_sample_panels()
        self._go_to_panel(0)
        self._update_report_button_state()
        self._inspection_running = True
        self.btn_start.setText("Interrompere Controllo")
        self.btn_start.setIcon(
            self.style().standardIcon(QStyle.SP_MediaStop)
        )
        self.btn_start.setEnabled(True)
        self.btn_start.setStyleSheet(
            "QPushButton { background:#ef6c00; color:white; padding:4px 12px; "
            "border-radius:4px; font-weight:bold; font-size:10pt; }"
        )
        self._update_lot_result()
        self.statusBar().showMessage(
            f"Controllo avviato — Lotto '{lot_code}'  |  Piano "
            f"{self._sampling_profile}  |  {self._sampling_counts_text()}  |  "
            f"Modalità {'sequenziale' if self._sequential_mode else 'per campione'}"
        )

    def _build_sample_panels(self):
        self.sample_stack.clear()
        self.sample_stack.setMinimumWidth(460)
        self.progress.setValue(0)

        if self._sequential_mode:
            self.progress.setMaximum(len(self._controls))
            self.progress.setFormat("%v / %m controlli completati")
            for ctrl in self._controls:
                control_samples = self._control_sample_count(ctrl)
                panel = SequentialControlPanel(
                    ctrl, control_samples, self._lot_id, self._operator
                )
                panel.all_done.connect(
                    lambda control_id=ctrl["id"]:
                    self._on_sequential_control_done(control_id)
                )
                panel.measurement_updated.connect(
                    self._on_sequential_control_updated
                )
                self.sample_stack.addTab(
                    panel, f"Controllo {ctrl['balloon_num']}"
                )
            return

        self.progress.setMaximum(self._n_samples)
        self.progress.setFormat("%v / %m campioni completati")
        for i in range(1, self._n_samples + 1):
            applicable_controls = [
                control for control in self._controls
                if i <= self._control_sample_count(control)
            ]
            panel = SamplePanel(
                applicable_controls, i, self._lot_id, self._operator
            )
            panel.all_done.connect(lambda s=i: self._on_sample_done(s))
            panel.measurement_updated.connect(self._on_sample_measurement_updated)
            self.sample_stack.addTab(panel, f"Campione {i}")

    def _go_to_panel(self, index: int):
        if not (0 <= index < self.sample_stack.count()):
            return
        self.sample_stack.setCurrentIndex(index)
        self._update_panel_navigation(index)

    def _on_panel_changed(self, index: int):
        if index >= 0:
            self._update_panel_navigation(index)

    def _update_panel_navigation(self, index: int):
        total = self.sample_stack.count()
        if not (0 <= index < total):
            return

        if self._sequential_mode:
            ctrl = self._controls[index]
            self.lbl_sample_info.setText(
                f"Controllo: {ctrl['balloon_num']}  |  {index + 1} / {total}"
            )
            self.viewer.select_balloon(ctrl["id"])
            ctrl_page = ctrl.get("pdf_page", 0)
            if ctrl_page != self.viewer.current_page:
                self.viewer.set_page(ctrl_page)
                self._update_page_label()
        else:
            self._current_sample = index + 1
            self.lbl_sample_info.setText(
                f"Campione: {self._current_sample} / {self._n_samples}"
            )

        self.btn_prev_sample.setEnabled(index > 0)
        self.btn_next_sample.setEnabled(index < total - 1)
        if not self._sequential_mode:
            self._refresh_sample_balloons(self._current_sample)

    def _go_to_previous_panel(self):
        self._go_to_panel(self.sample_stack.currentIndex() - 1)

    def _go_to_next_panel(self):
        self._go_to_panel(self.sample_stack.currentIndex() + 1)

    def _on_sample_done(self, sample_num: int):
        self._completed_sample_nums.add(sample_num)
        self.progress.setValue(len(self._completed_sample_nums))
        if sample_num == self._current_sample:
            self._refresh_sample_balloons(sample_num)
        # Aggiorna esito lotto
        self._update_lot_result()
        self._update_report_button_state()

    def _refresh_sample_balloons(self, sample_num: int):
        self.viewer.reset_results()
        for measurement in self._draft_measurements.values():
            if measurement["sample_num"] == sample_num:
                self.viewer.update_balloon_result(
                    measurement["control_id"],
                    get_measurement_status(measurement),
                )

    def _store_draft_measurement(
            self, sample_num: int, control_id: int, value_num,
            value_bool, pass_fail: bool):
        self._draft_measurements[(control_id, sample_num)] = {
            "control_id": control_id,
            "sample_num": sample_num,
            "value_num": value_num,
            "value_bool": value_bool,
            "pass_fail": bool(pass_fail),
            "accepted_in_derogation": False,
            "recorded_at": datetime.now().isoformat(),
        }
        self._measurement_sound.play(pass_fail)

    def _on_sample_measurement_updated(
            self, sample_num: int, control_id: int, value_num,
            value_bool, pass_fail: bool):
        self._store_draft_measurement(
            sample_num, control_id, value_num, value_bool, pass_fail
        )
        if sample_num == self._current_sample:
            self._refresh_sample_balloons(sample_num)
        self._update_lot_result()
        self._update_report_button_state()

    def _on_sequential_control_done(self, control_id: int):
        self._completed_sequence_control_ids.add(control_id)
        self.progress.setValue(len(self._completed_sequence_control_ids))
        self._update_report_button_state()

    def _on_sequential_control_updated(
            self, sample_num: int, control_id: int, value_num,
            value_bool, pass_fail: bool):
        self._store_draft_measurement(
            sample_num, control_id, value_num, value_bool, pass_fail
        )
        control = next(
            (item for item in self._controls if item["id"] == control_id), None
        )
        if control is None:
            return
        measurements = [
            m for m in self._draft_measurements.values()
            if m["control_id"] == control_id
        ]
        if len(measurements) >= self._control_sample_count(control):
            self.viewer.update_balloon_result(
                control_id,
                get_control_status(measurements),
            )
        self._update_lot_result()
        self._update_report_button_state()

    def _update_lot_result(self):
        evaluation = evaluate_sampling_lot(
            self._draft_lot(), self._controls,
            list(self._draft_measurements.values()),
        )
        status = evaluation["status"]
        msg = evaluation["message"]
        details = []
        for criticality in ("C", "I", "N"):
            result = evaluation["by_criticality"][criticality]
            if result["controls"]:
                details.append(
                    f"{criticality}: {result['defective']} dif. / "
                    f"Ac {result['ac']} / Re {result['re']}"
                )
        if details:
            msg += "  |  " + " · ".join(details)
        if status == STATUS_EMPTY:
            color, bg, border = "#536372", "#eef2f5", "#cbd4dc"
        elif status == STATUS_PASS:
            color, bg, border = "#1a8a1a", "#e8f5e9", "#1a8a1a"
        elif status == STATUS_DEROGATION:
            color, bg, border = "#7a4b00", "#fff3cd", "#b26a00"
        elif status == STATUS_INCOMPLETE:
            color, bg, border = "#174a78", "#dcecf8", "#2f75b5"
        else:
            color, bg, border = "#cc0000", "#ffebee", "#cc0000"
        self.lbl_lot_result.setText(msg)
        self.lbl_lot_result.setStyleSheet(
            f"color:{color}; background:{bg}; border:1px solid {border}; "
            "border-radius:5px; padding:5px 12px;"
        )

    def _expected_measurement_count(self) -> int:
        return get_expected_measurement_count(self._draft_lot(), self._controls)

    def _is_lot_complete(self) -> bool:
        return bool(evaluate_sampling_lot(
            self._draft_lot(), self._controls,
            list(self._draft_measurements.values()),
        )["complete"])

    def _update_report_button_state(self):
        self.btn_report.setEnabled(self._is_lot_complete())

    def _control_sample_count(self, control: dict) -> int:
        criticality = control.get("criticality") or "N"
        requirement = self._sampling_requirements.get(criticality)
        if requirement:
            return int(requirement["n"])
        return self._n_samples

    def _sampling_counts_text(self) -> str:
        parts = []
        active_criticalities = {
            control.get("criticality") or "N" for control in self._controls
        }
        for criticality in ("C", "I", "N"):
            requirement = self._sampling_requirements.get(criticality)
            if requirement and criticality in active_criticalities:
                parts.append(f"{criticality}:{requirement['n']}")
        return " · ".join(parts) if parts else str(self._n_samples)

    def _draft_lot(self) -> dict:
        lot = {"n_samples": self._n_samples}
        for criticality, prefix in (
                ("C", "critical"), ("I", "important"), ("N", "normal")):
            requirement = self._sampling_requirements.get(criticality) or {
                "n": self._n_samples, "ac": 0, "re": 1,
            }
            lot[f"{prefix}_n"] = int(requirement["n"])
            lot[f"{prefix}_ac"] = int(requirement["ac"])
            lot[f"{prefix}_re"] = int(requirement["re"])
        return lot

    def _finish_completed_inspection(self, message: str):
        self._inspection_running = False
        self._allow_close = True
        self.btn_report.setEnabled(False)
        self.btn_start.setEnabled(False)
        QMessageBox.information(self, "Controllo concluso", message)
        self.close()

    # ─── Balloon click ───────────────────────────────────────────────────────

    def _on_balloon_clicked(self, balloon_id: int):
        if self._sequential_mode:
            for index, ctrl in enumerate(self._controls):
                if ctrl["id"] == balloon_id:
                    self._go_to_panel(index)
                    return

        # Salta al tab del campione corrente e scrolla al controllo
        ctrl = next(
            (control for control in self._controls
             if control["id"] == balloon_id),
            None,
        )
        if ctrl:
            panel = self.sample_stack.currentWidget()
            if isinstance(panel, SamplePanel):
                for row in panel._rows:
                    if row._control["id"] == balloon_id:
                        panel.ensureWidgetVisible(row)
                        break

    # ─── Report ──────────────────────────────────────────────────────────────

    def _selected_derogation_rows(self) -> list[SampleControlRow]:
        rows = []
        for index in range(self.sample_stack.count()):
            panel = self.sample_stack.widget(index)
            rows.extend(
                row for row in getattr(panel, "_rows", [])
                if row.is_derogation_selected()
            )
        return rows

    def _on_generate_report(self):
        sampling_evaluation = evaluate_sampling_lot(
            self._draft_lot(), self._controls,
            list(self._draft_measurements.values()),
        )
        if not sampling_evaluation["complete"]:
            completed = sampling_evaluation["completed_total"]
            expected = sampling_evaluation["expected_total"]
            QMessageBox.warning(
                self,
                "Report non disponibile",
                "Completa tutte le misure prima di generare il report.\n"
                f"Misure registrate: {completed}/{expected}"
            )
            self._update_report_button_state()
            return
        derogation_rows = self._selected_derogation_rows()
        derogation_data = None
        if derogation_rows:
            dialog = DerogationDialog(self._operator, derogation_rows, self)
            if dialog.exec_() != QDialog.Accepted:
                return
            derogation_data = (dialog.reason, dialog.authorized_by)

        measurements = [dict(item) for item in self._draft_measurements.values()]
        if derogation_rows:
            selected = {
                (row._control["id"], row._sample_num)
                for row in derogation_rows
            }
            derogation_at = datetime.now().isoformat()
            for measurement in measurements:
                key = (measurement["control_id"], measurement["sample_num"])
                if key in selected:
                    measurement.update({
                        "accepted_in_derogation": True,
                        "derogation_reason": derogation_data[0],
                        "derogation_authorized_by": derogation_data[1],
                        "derogation_accepted_by": self._operator,
                        "derogation_at": derogation_at,
                    })

        try:
            self._lot_id = db.save_completed_inspection(
                setup_id=self._setup_id,
                setup_revision_id=self._setup_revision_id,
                lot_code=self._lot_code,
                lot_quantity=self._lot_quantity,
                n_samples=self._n_samples,
                sampling_profile=self._sampling_profile,
                sampling_requirements=self._sampling_requirements,
                operator=self._operator,
                operator_id=self._operator_id,
                supplier=self._supplier,
                supplier_id=self._supplier_id,
                measurements=measurements,
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Salvataggio non riuscito",
                "Il controllo non è stato salvato. I dati restano disponibili "
                f"nella finestra.\n\nDettaglio: {exc}",
            )
            return

        self._draft_measurements = {
            (item["control_id"], item["sample_num"]): item
            for item in measurements
        }
        for row in derogation_rows:
            row.set_derogated(True)
        self._inspection_running = False
        self.btn_report.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.statusBar().showMessage(
            f"Controllo salvato nello storico — lotto '{self._lot_code}'"
        )

        setup = self._setup
        setup_name = str(setup.get("name") or "setup")
        lot_code = str(self._lot_code or "lotto")

        def _safe_part(text: str) -> str:
            cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
            return cleaned.strip("_") or "valore"

        report_path = ""
        report_question = QMessageBox.question(
            self, "Controllo salvato",
            "Il controllo è stato salvato nello storico.\n\n"
            "Vuoi generare ora il report PDF?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        messages = ["Il controllo è stato salvato nello storico."]
        if report_question == QMessageBox.Yes:
            default_name = (
                f"{_safe_part(setup_name)}_{_safe_part(lot_code)}.pdf"
            )
            report_path, _ = QFileDialog.getSaveFileName(
                self, "Salva report", default_name, "PDF (*.pdf)"
            )
            if report_path:
                try:
                    report_data = db.get_lot_report_data(self._lot_id)
                    if not report_data:
                        raise ValueError("Dati del controllo non disponibili")
                    generate_report(
                        report_path, report_data["setup"],
                        report_data["controls"], report_data["summary"],
                    )
                    messages.append(f"Report salvato:\n{report_path}")
                except Exception as exc:
                    QMessageBox.warning(
                        self, "Report non generato",
                        "Il controllo è già salvato, ma il report non è stato "
                        f"generato. Potrai riprovare dallo storico.\n\n{exc}",
                    )
                    report_path = ""
            else:
                messages.append(
                    "Report non generato: potrà essere creato dallo storico."
                )
        else:
            messages.append(
                "Report non generato: potrà essere creato dallo storico."
            )

        cfg = load_or_create_config()
        label_enable = str(cfg.get("label_enable", "YES")).strip().upper()
        labels_enabled = label_enable in {"YES", "Y", "TRUE", "1", "ON"}
        if labels_enabled:
            print_question = QMessageBox.question(
                self, "Etichetta",
                "Vuoi stampare ora l'etichetta del controllo salvato?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if print_question == QMessageBox.Yes:
                if report_path:
                    label_path = report_path.rsplit(".", 1)[0] + "_etichetta.pdf"
                else:
                    import tempfile
                    temporary = tempfile.NamedTemporaryFile(
                        prefix="qc_etichetta_", suffix=".pdf", delete=False
                    )
                    label_path = temporary.name
                    temporary.close()
                summary = db.get_lot_summary(self._lot_id)
                ok_lbl, err_lbl = generate_label_pdf(label_path, setup, summary)
                if not ok_lbl:
                    QMessageBox.warning(
                        self, "Etichetta",
                        "Il controllo è salvato, ma l'etichetta non è stata "
                        f"generata:\n{err_lbl}"
                    )
                else:
                    ok_prn, err_prn = print_label(label_path)
                    if not ok_prn:
                        QMessageBox.warning(
                            self, "Etichetta non stampata",
                            "Il controllo è salvato e l'etichetta è stata "
                            f"generata in:\n{label_path}\n\n{err_prn}",
                        )
                    else:
                        messages.append("Etichetta stampata.")

        self._finish_completed_inspection("\n\n".join(messages))

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _change_page(self, delta: int):
        new_page = self.viewer.current_page + delta
        if 0 <= new_page < self.viewer.total_pages:
            self.viewer.set_page(new_page)
            self._update_page_label()

    def _update_page_label(self):
        self.lbl_page.setText(
            f"Pagina: {self.viewer.current_page + 1}/{self.viewer.total_pages}"
        )
