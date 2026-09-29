"""Gestione delle anagrafiche e dei piani di campionamento."""

import sqlite3

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QCheckBox, QComboBox, QFrame, QGroupBox, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QFileDialog,
    QPushButton, QSpinBox, QStyledItemDelegate, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView, QStyle,
)

from ..database import db_manager as db
from ..core import app_config
from ..core.audio_feedback import MeasurementSoundPlayer
from ..core.sampling_plans import (
    SAMPLING_PLAN_COLUMNS,
    SAMPLING_PLAN_DESCRIPTIONS,
    SAMPLING_PLAN_LABELS,
    SAMPLING_PLANS,
    validate_sampling_plan,
    validate_sampling_plans,
)


class RecordDialog(QDialog):
    """Dialogo essenziale per creare o modificare un record anagrafico."""

    def __init__(self, title: str, fields: list[tuple[str, str]],
                 record: dict | None = None, required_keys: tuple[str, ...] = ("name",),
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog { background:#f4f6f8; }
            QLineEdit, QTextEdit {
                background:white; border:1px solid #b7c1cb;
                border-radius:4px; padding:6px;
            }
            QLineEdit:focus, QTextEdit:focus { border:2px solid #2f75b5; }
            QPushButton { min-height:28px; padding:2px 14px; }
            QPushButton[role="primary"] {
                color:white; background:#2f75b5; border:1px solid #28669d;
                border-radius:4px; font-weight:bold;
            }
        """)
        self.fields = fields
        self._inputs = {}
        self._required_keys = required_keys

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for key, label in fields:
            if key == "notes":
                editor = QTextEdit()
                editor.setFixedHeight(80)
            else:
                editor = QLineEdit()
            editor.setText(str((record or {}).get(key) or ""))
            self._inputs[key] = editor
            form.addRow(
                f"{label}{'*' if key in self._required_keys else ''}:", editor
            )
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Save).setIcon(
            self.style().standardIcon(QStyle.SP_DialogSaveButton)
        )
        buttons.button(QDialogButtonBox.Cancel).setIcon(
            self.style().standardIcon(QStyle.SP_DialogCancelButton)
        )
        buttons.button(QDialogButtonBox.Save).setProperty("role", "primary")
        buttons.button(QDialogButtonBox.Save).setIcon(
            self.style().standardIcon(QStyle.SP_DialogSaveButton)
        )
        buttons.button(QDialogButtonBox.Cancel).setIcon(
            self.style().standardIcon(QStyle.SP_DialogCancelButton)
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        for key in self._required_keys:
            if not self.value(key):
                label = next(label for field, label in self.fields if field == key)
                QMessageBox.warning(
                    self, "Dato obbligatorio", f"Inserisci {label.lower()}."
                )
                return
        self.accept()

    def value(self, key: str) -> str:
        editor = self._inputs[key]
        if isinstance(editor, QTextEdit):
            return editor.toPlainText().strip()
        return editor.text().strip()


class SamplingClassDialog(QDialog):
    """Crea o modifica una classe e le sue regole di piano automatico."""

    def __init__(self, title: str, record: dict | None = None, parent=None):
        super().__init__(parent)
        record = record or {}
        self.setWindowTitle(title)
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        identity_group = QGroupBox("Classe di collaudo")
        identity_form = QFormLayout(identity_group)
        self.txt_code = QLineEdit(str(record.get("code") or ""))
        self.txt_description = QLineEdit(
            str(record.get("description") or "")
        )
        identity_form.addRow("Codice Classe*:", self.txt_code)
        identity_form.addRow("Descrizione Classe*:", self.txt_description)
        layout.addWidget(identity_group)

        rules_group = QGroupBox("Regole del piano suggerito")
        rules_form = QFormLayout(rules_group)
        self.spn_validity_days = QSpinBox()
        self.spn_validity_days.setRange(1, 36500)
        self.spn_validity_days.setSuffix(" giorni")
        self.spn_validity_days.setValue(
            int(record.get("history_validity_days") or 730)
        )
        rules_form.addRow("Validità dello storico*:", self.spn_validity_days)

        self.spn_extended_passes = QSpinBox()
        self.spn_extended_passes.setRange(1, 99)
        self.spn_extended_passes.setValue(
            int(record.get("extended_passes_required") or 1)
        )
        rules_form.addRow(
            "PASS Estesi per passare a Normale*:",
            self.spn_extended_passes,
        )

        self.spn_normal_passes = QSpinBox()
        self.spn_normal_passes.setRange(1, 99)
        self.spn_normal_passes.setValue(
            int(record.get("normal_passes_required") or 2)
        )
        rules_form.addRow(
            "PASS Normali per passare a Ridotto*:",
            self.spn_normal_passes,
        )

        self.chk_fail_reset = QCheckBox(
            "Un esito non positivo riporta il suggerimento a Esteso"
        )
        self.chk_fail_reset.setChecked(
            bool(record.get("fail_resets_extended", 1))
        )
        rules_form.addRow("Dopo esito negativo:", self.chk_fail_reset)

        self.chk_derogation_positive = QCheckBox(
            "Considera positivo un lotto accettato in deroga"
        )
        self.chk_derogation_positive.setChecked(
            bool(record.get("derogation_counts_positive", 0))
        )
        rules_form.addRow("Deroghe:", self.chk_derogation_positive)
        layout.addWidget(rules_group)

        note = QLabel(
            "Il piano viene soltanto suggerito: l'operatore può sempre "
            "sceglierne uno diverso prima di avviare il controllo."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#52616e;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        if not self.txt_code.text().strip():
            QMessageBox.warning(self, "Dato obbligatorio", "Inserisci il codice classe.")
            return
        if not self.txt_description.text().strip():
            QMessageBox.warning(
                self, "Dato obbligatorio", "Inserisci la descrizione classe."
            )
            return
        self.accept()

    def values(self) -> dict:
        return {
            "code": self.txt_code.text().strip(),
            "description": self.txt_description.text().strip(),
            "history_validity_days": self.spn_validity_days.value(),
            "extended_passes_required": self.spn_extended_passes.value(),
            "normal_passes_required": self.spn_normal_passes.value(),
            "fail_resets_extended": self.chk_fail_reset.isChecked(),
            "derogation_counts_positive": (
                self.chk_derogation_positive.isChecked()
            ),
        }


class RegistryTab(QWidget):
    """Tabella CRUD riutilizzata dalle anagrafiche."""

    records_changed = pyqtSignal()

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.records = []
        self.required_keys = ("name",)
        if kind == "operator":
            self.title = "operatore"
            self.fields = [
                ("name", "Nome e cognome"), ("email", "E-mail"),
                ("phone", "Telefono"), ("notes", "Note"),
            ]
        elif kind == "supplier":
            self.title = "fornitore"
            self.fields = [
                ("name", "Ragione sociale"),
                ("vat_code", "Partita IVA / Codice fiscale"),
                ("contact", "Referente"), ("email", "E-mail"),
                ("phone", "Telefono"), ("notes", "Note"),
            ]
        elif kind == "sampling_class":
            self.title = "classe di campionamento"
            self.fields = [
                ("code", "Codice Classe"),
                ("description", "Descrizione Classe"),
            ]
            self.required_keys = ("code", "description")
        else:
            raise ValueError(f"Configurazione sconosciuta: {kind}")
        self.description = {
            "operator": "Gestisci gli operatori selezionabili durante il collaudo.",
            "supplier": "Gestisci i fornitori associabili ai lotti in ingresso.",
            "sampling_class": (
                "Definisci le classi di collaudo e i relativi piani di campionamento."
            ),
        }[kind]
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        description = QLabel(self.description)
        description.setObjectName("sectionDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        add_label = (
            "Nuova classe" if self.kind == "sampling_class"
            else f"Nuovo {self.title}"
        )
        add_button = QPushButton(add_label)
        add_button.setProperty("role", "primary")
        add_button.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        add_button.clicked.connect(self._add)
        actions.addWidget(add_button)
        edit_button = QPushButton("Modifica")
        edit_button.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        )
        edit_button.clicked.connect(self._edit)
        actions.addWidget(edit_button)
        delete_button = QPushButton("Elimina")
        delete_button.setProperty("role", "danger")
        delete_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        delete_button.clicked.connect(self._delete)
        actions.addWidget(delete_button)
        actions.addStretch()
        self.summary_label = QLabel()
        self.summary_label.setObjectName("recordCount")
        actions.addWidget(self.summary_label)
        layout.addLayout(actions)

        self.table = QTableWidget(0, len(self.fields))
        self.table.setObjectName("registryTable")
        self.table.setHorizontalHeaderLabels([label for _, label in self.fields])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.doubleClicked.connect(self._edit)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def refresh(self):
        if self.kind == "operator":
            self.records = db.get_all_operators()
        elif self.kind == "supplier":
            self.records = db.get_all_suppliers()
        else:
            self.records = db.get_all_sampling_classes()
        self.table.setRowCount(len(self.records))
        record_count = len(self.records)
        self.summary_label.setText(
            "1 elemento" if record_count == 1 else f"{record_count} elementi"
        )
        for row, record in enumerate(self.records):
            for column, (key, _) in enumerate(self.fields):
                item = QTableWidgetItem(str(record.get(key) or ""))
                item.setData(Qt.UserRole, record["id"])
                self.table.setItem(row, column, item)

    def _selected_record(self) -> dict | None:
        row = self.table.currentRow()
        return self.records[row] if 0 <= row < len(self.records) else None

    def _add(self):
        self._open_dialog(None)

    def _edit(self, *_):
        record = self._selected_record()
        if not record:
            QMessageBox.information(self, "Selezione", "Seleziona una riga da modificare.")
            return
        self._open_dialog(record)

    def _open_dialog(self, record: dict | None):
        action = (
            "Modifica" if record
            else ("Nuova" if self.kind == "sampling_class" else "Nuovo")
        )
        if self.kind == "sampling_class":
            dialog = SamplingClassDialog(
                f"{action} {self.title}", record, self
            )
        else:
            dialog = RecordDialog(
                f"{action} {self.title}", self.fields, record,
                self.required_keys, self,
            )
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            values = (
                dialog.values()
                if self.kind == "sampling_class"
                else {key: dialog.value(key) for key, _ in self.fields}
            )
            if self.kind == "operator":
                db.save_operator(**values, operator_id=record["id"] if record else None)
            elif self.kind == "supplier":
                db.save_supplier(**values, supplier_id=record["id"] if record else None)
            else:
                db.save_sampling_class(
                    **values,
                    sampling_class_id=record["id"] if record else None,
                )
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Dato duplicato",
                "Esiste già una classe con questo codice."
                if self.kind == "sampling_class"
                else "Esiste già un record con questo nome."
            )
            return
        self.refresh()
        self.records_changed.emit()

    def _delete(self):
        record = self._selected_record()
        if not record:
            QMessageBox.information(self, "Selezione", "Seleziona una riga da eliminare.")
            return
        record_label = record.get("name") or record.get("code") or ""
        if self.kind == "sampling_class":
            if record.get("is_default"):
                QMessageBox.warning(
                    self,
                    "Classe predefinita",
                    f"La classe “{record_label}” è la classe di campionamento "
                    "predefinita e non può essere eliminata.",
                )
                return
            linked_setups = db.get_sampling_class_setups(record["id"])
            if linked_setups:
                setup_labels = []
                for setup in linked_setups:
                    label = setup["name"]
                    if setup.get("description"):
                        label += f" — {setup['description']}"
                    setup_labels.append(label)
                has_more = len(setup_labels) > 10
                visible_labels = setup_labels[:10]
                if has_more:
                    visible_labels.append(
                        f"… e altri {len(setup_labels) - 10} setup"
                    )
                message = QMessageBox(self)
                message.setIcon(QMessageBox.Warning)
                message.setWindowTitle("Classe utilizzata")
                message.setText(
                    f"La classe “{record_label}” non può essere eliminata perché "
                    f"è associata a {len(linked_setups)} setup."
                )
                message.setInformativeText(
                    "Setup vincolati:\n• " + "\n• ".join(visible_labels)
                    + "\n\nModifica prima la Classe di Collaudo dei setup indicati."
                )
                if has_more:
                    message.setDetailedText("\n".join(setup_labels))
                message.exec_()
                return
        history_note = (
            "\nVerranno eliminati anche i piani Esteso, Normale e Ridotto associati."
            if self.kind == "sampling_class"
            else "\nI controlli già registrati manterranno il nome salvato."
        )
        reply = QMessageBox.question(
            self, "Conferma eliminazione",
            f"Eliminare {self.title} “{record_label}”?{history_note}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if self.kind == "operator":
                db.delete_operator(record["id"])
            elif self.kind == "supplier":
                db.delete_supplier(record["id"])
            else:
                db.delete_sampling_class(record["id"])
        except ValueError as exc:
            QMessageBox.warning(self, "Eliminazione non consentita", str(exc))
            return
        self.refresh()
        self.records_changed.emit()


class IntegerItemDelegate(QStyledItemDelegate):
    """Editor che accetta esclusivamente numeri interi non negativi."""

    _POSITIVE_COLUMNS = {0, 1, 2, 5, 8}

    def createEditor(self, parent, option, index):
        editor = QSpinBox(parent)
        editor.setRange(
            1 if index.column() in self._POSITIVE_COLUMNS else 0,
            999999999,
        )
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor, index):
        editor.setValue(int(index.model().data(index) or 0))

    def setModelData(self, editor, model, index):
        editor.interpretText()
        model.setData(index, str(editor.value()), Qt.EditRole)


class SamplingPlansTab(QWidget):
    """Modifica e salva i tre piani della classe di campionamento selezionata."""

    _AC_TO_RE_COLUMNS = {3: 4, 6: 7, 9: 10}
    _RE_COLUMNS = frozenset(_AC_TO_RE_COLUMNS.values())

    _CRITICALITY_STYLES = (
        ("C", "CRITICA", "#fdecec", "#b54848"),
        ("I", "IMPORTANTE", "#fff4df", "#c58b2a"),
        ("N", "NORMALE", "#edf5ed", "#5b8f62"),
    )
    _CRITICALITY_TOOLTIPS = {
        "C": (
            "Misura Critica\n"
            "Quota il cui mancato rispetto compromette la funzionalità,\n"
            "la sicurezza o l'intercambiabilità del pezzo; richiede controllo\n"
            "dimensionale al 100% e tolleranze strette."
        ),
        "I": (
            "Misura Importante\n"
            "Quota che influisce sull'accoppiamento o sulle prestazioni del\n"
            "componente ma con margine di tolleranza maggiore rispetto alla\n"
            "critica; controllo a campionamento."
        ),
        "N": (
            "Misura Normale\n"
            "Quota di riferimento generale, senza impatto diretto su\n"
            "funzionalità o accoppiamenti; tolleranza secondo norma generale\n"
            "e controllo occasionale."
        ),
    }
    _COLUMN_COLORS = {
        2: QColor("#fdecec"), 3: QColor("#fdecec"), 4: QColor("#fdecec"),
        5: QColor("#fff4df"), 6: QColor("#fff4df"), 7: QColor("#fff4df"),
        8: QColor("#edf5ed"), 9: QColor("#edf5ed"), 10: QColor("#edf5ed"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = True
        self._current_class_id = None
        self.dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        class_row = QHBoxLayout()
        class_label = QLabel("<b>Classe di campionamento:</b>")
        class_row.addWidget(class_label)
        self.cmb_sampling_class = QComboBox()
        self.cmb_sampling_class.setMinimumWidth(420)
        self.cmb_sampling_class.setToolTip(
            "Seleziona la classe di cui visualizzare e modificare i tre piani."
        )
        class_row.addWidget(self.cmb_sampling_class, 1)
        layout.addLayout(class_row)

        info = QLabel(
            "n = pezzi da controllare · Ac = non conformi accettabili · "
            "Re = soglia di rifiuto calcolata automaticamente come Ac + 1."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        legend_title = QLabel(
            "<b>Criticità delle misure</b> — ogni colore identifica il gruppo "
            "di colonne n / Ac / Re della relativa criticità:"
        )
        legend_title.setWordWrap(True)
        layout.addWidget(legend_title)

        legend = QHBoxLayout()
        for code, name, background, border in self._CRITICALITY_STYLES:
            badge = QLabel(f"<b>{code} = {name}</b>")
            badge.setAlignment(Qt.AlignCenter)
            badge.setToolTip(self._CRITICALITY_TOOLTIPS[code])
            badge.setStyleSheet(
                f"background:{background}; border:2px solid {border}; "
                "border-radius:4px; padding:7px;"
            )
            legend.addWidget(badge, 1)
        layout.addLayout(legend)

        actions = QHBoxLayout()
        self.btn_add = QPushButton("Aggiungi riga")
        self.btn_add.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.btn_add.clicked.connect(self._add_row)
        actions.addWidget(self.btn_add)

        self.btn_delete = QPushButton("Elimina riga")
        self.btn_delete.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_delete.clicked.connect(self._delete_row)
        actions.addWidget(self.btn_delete)

        self.chk_infinite = QCheckBox("Lotto max infinito (∞) sull'ultima riga")
        self.chk_infinite.toggled.connect(self._on_infinite_toggled)
        actions.addWidget(self.chk_infinite)
        actions.addStretch()

        self.btn_save = QPushButton("Salva tabelle")
        self.btn_save.setProperty("role", "primary")
        self.btn_save.setIcon(
            self.style().standardIcon(QStyle.SP_DialogSaveButton)
        )
        self.btn_save.clicked.connect(self.save)
        self.btn_save.setEnabled(False)
        actions.addWidget(self.btn_save)
        layout.addLayout(actions)

        self.profile_tabs = QTabWidget()
        self.tables = {}
        self.validation_labels = {}
        for profile in ("ESTESO", "NORMALE", "RIDOTTO"):
            page = QWidget()
            page_layout = QVBoxLayout(page)

            profile_header = QHBoxLayout()
            description = QLabel(SAMPLING_PLAN_DESCRIPTIONS[profile])
            description.setWordWrap(True)
            profile_header.addWidget(description, 1)
            restore_button = QPushButton("Ripristina predefiniti")
            restore_button.setIcon(
                self.style().standardIcon(QStyle.SP_BrowserReload)
            )
            restore_button.clicked.connect(
                lambda _checked=False, selected=profile:
                self._restore_defaults(selected)
            )
            profile_header.addWidget(restore_button)
            page_layout.addLayout(profile_header)

            table = self._build_table(profile, [])
            self.tables[profile] = table
            page_layout.addWidget(table)

            validation_label = QLabel()
            validation_label.setWordWrap(True)
            self.validation_labels[profile] = validation_label
            page_layout.addWidget(validation_label)
            self.profile_tabs.addTab(page, profile)

        self.profile_tabs.currentChanged.connect(self._sync_infinite_checkbox)
        layout.addWidget(self.profile_tabs)

        note = QLabel(
            "Ogni modifica viene verificata subito. Salva tabelle registra i "
            "tre piani della classe selezionata soltanto se sono tutti validi."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "background:#fff8dc; border:1px solid #e0cf8a; padding:6px;"
        )
        layout.addWidget(note)
        self._loading = False
        self.cmb_sampling_class.currentIndexChanged.connect(
            self._on_sampling_class_changed
        )
        self.refresh_classes()

    def selected_class_id(self) -> int | None:
        return self.cmb_sampling_class.currentData()

    def refresh_classes(self):
        """Aggiorna il menu senza perdere modifiche della classe ancora presente."""
        classes = db.get_all_sampling_classes()
        previous_id = self._current_class_id
        self.cmb_sampling_class.blockSignals(True)
        self.cmb_sampling_class.clear()
        for sampling_class in classes:
            self.cmb_sampling_class.addItem(
                f"{sampling_class['code']} — {sampling_class['description']}",
                sampling_class["id"],
            )
        target_index = self.cmb_sampling_class.findData(previous_id)
        if target_index < 0 and self.cmb_sampling_class.count():
            target_index = 0
        self.cmb_sampling_class.setCurrentIndex(target_index)
        self.cmb_sampling_class.blockSignals(False)

        selected_id = self.selected_class_id()
        if previous_id == selected_id and previous_id is not None:
            return
        self._load_sampling_class(selected_id)

    def _on_sampling_class_changed(self, *_):
        selected_id = self.selected_class_id()
        if selected_id == self._current_class_id:
            return
        if self.dirty:
            reply = QMessageBox.question(
                self,
                "Modifiche non salvate",
                "La classe corrente contiene modifiche non salvate.",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply == QMessageBox.Save:
                if not self.save(self._current_class_id):
                    self._restore_class_selection()
                    return
            elif reply == QMessageBox.Cancel:
                self._restore_class_selection()
                return
        self._load_sampling_class(selected_id)

    def _restore_class_selection(self):
        self.cmb_sampling_class.blockSignals(True)
        self.cmb_sampling_class.setCurrentIndex(
            self.cmb_sampling_class.findData(self._current_class_id)
        )
        self.cmb_sampling_class.blockSignals(False)

    def _load_sampling_class(self, sampling_class_id: int | None):
        plans = (
            db.get_sampling_plans(sampling_class_id)
            if sampling_class_id is not None
            else {profile: [] for profile in SAMPLING_PLANS}
        )
        self._loading = True
        try:
            for profile, table in self.tables.items():
                table.blockSignals(True)
                table.setRowCount(len(plans[profile]))
                for row_index, row in enumerate(plans[profile]):
                    values = [row[column] for column in SAMPLING_PLAN_COLUMNS]
                    self._populate_row(table, row_index, values)
                table.blockSignals(False)
        finally:
            self._loading = False
        self._current_class_id = sampling_class_id
        self.dirty = False
        self.profile_tabs.setEnabled(sampling_class_id is not None)
        self.btn_add.setEnabled(sampling_class_id is not None)
        self.btn_delete.setEnabled(sampling_class_id is not None)
        self.btn_save.setEnabled(False)
        self._sync_infinite_checkbox()
        for profile in self.tables:
            if sampling_class_id is None:
                self.validation_labels[profile].setText(
                    "Crea una classe di campionamento per configurare i piani."
                )
                self.validation_labels[profile].setStyleSheet(
                    "color:#6b5a00; background:#fff8dc; padding:5px;"
                )
            else:
                self._refresh_validation(profile)

    def _build_table(self, profile: str, rows: list[dict]) -> QTableWidget:
        table = QTableWidget(len(rows), len(SAMPLING_PLAN_LABELS))
        table.setHorizontalHeaderLabels(SAMPLING_PLAN_LABELS)
        metric_names = ("n: pezzi da controllare", "Ac: limite di accettazione",
                        "Re: limite di rifiuto")
        for group_index, (_, name, background, _) in enumerate(
            self._CRITICALITY_STYLES
        ):
            for metric_index, metric_name in enumerate(metric_names):
                column = 2 + group_index * 3 + metric_index
                header_item = table.horizontalHeaderItem(column)
                header_item.setBackground(QColor(background))
                header_item.setToolTip(
                    f"Misure {name} — {metric_name}"
                )
        table.setItemDelegate(IntegerItemDelegate(table))
        table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        for row_index, row in enumerate(rows):
            values = [row[column] for column in SAMPLING_PLAN_COLUMNS]
            self._populate_row(table, row_index, values)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(54)
        table.resizeRowsToContents()
        table.itemChanged.connect(
            lambda item, selected=profile:
            self._on_table_changed(selected, item)
        )
        return table

    def _populate_row(self, table: QTableWidget, row: int, values):
        values = list(values)
        for ac_column, re_column in self._AC_TO_RE_COLUMNS.items():
            values[re_column] = int(values[ac_column]) + 1
        for column, value in enumerate(values):
            text = "∞" if column == 1 and value is None else str(value)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            if column in self._COLUMN_COLORS:
                item.setBackground(self._COLUMN_COLORS[column])
            if column in self._RE_COLUMNS:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setForeground(QColor("#52616d"))
                item.setToolTip("Valore calcolato automaticamente: Re = Ac + 1")
            elif text == "∞":
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, column, item)

    def _active_profile(self) -> str:
        return self.profile_tabs.tabText(self.profile_tabs.currentIndex())

    def _active_table(self) -> QTableWidget:
        return self.tables[self._active_profile()]

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self.dirty = True
        self.btn_save.setEnabled(True)

    def _on_table_changed(self, profile: str, item: QTableWidgetItem):
        if self._loading:
            return
        re_column = self._AC_TO_RE_COLUMNS.get(item.column())
        if re_column is not None:
            try:
                rejection = int(item.text().strip()) + 1
            except ValueError:
                rejection = None
            if rejection is not None:
                table = self.tables[profile]
                re_item = table.item(item.row(), re_column)
                table.blockSignals(True)
                try:
                    re_item.setText(str(rejection))
                finally:
                    table.blockSignals(False)
        self._mark_dirty()
        self._refresh_validation(profile)

    def _table_payload(self, profile: str) -> list[dict]:
        table = self.tables[profile]
        rows = []
        for row_index in range(table.rowCount()):
            row = {}
            for column, key in enumerate(SAMPLING_PLAN_COLUMNS):
                item = table.item(row_index, column)
                text = item.text().strip() if item else ""
                row[key] = None if column == 1 and text == "∞" else int(text)
            for ac_column, re_column in self._AC_TO_RE_COLUMNS.items():
                ac_key = SAMPLING_PLAN_COLUMNS[ac_column]
                re_key = SAMPLING_PLAN_COLUMNS[re_column]
                row[re_key] = row[ac_key] + 1
            rows.append(row)
        return rows

    def _refresh_validation(self, profile: str, show_dialog: bool = False) -> bool:
        try:
            validate_sampling_plan(profile, self._table_payload(profile))
        except (TypeError, ValueError) as exc:
            message = str(exc)
            label = self.validation_labels[profile]
            label.setText(f"⚠ {message}")
            label.setStyleSheet(
                "color:#8b1a1a; background:#fdecec; border:1px solid #d99; "
                "padding:5px;"
            )
            if show_dialog:
                QMessageBox.warning(self, "Piano non valido", message)
            return False
        label = self.validation_labels[profile]
        label.setText(
            "✓ Piano valido: intervalli continui e ultima fascia infinita."
        )
        label.setStyleSheet(
            "color:#245b2a; background:#edf5ed; border:1px solid #9c9; "
            "padding:5px;"
        )
        return True

    def _sync_infinite_checkbox(self, *_):
        table = self._active_table()
        has_rows = table.rowCount() > 0
        infinite = has_rows and table.item(table.rowCount() - 1, 1).text() == "∞"
        self.chk_infinite.blockSignals(True)
        self.chk_infinite.setEnabled(has_rows)
        self.chk_infinite.setChecked(infinite)
        self.chk_infinite.blockSignals(False)

    def _on_infinite_toggled(self, checked: bool):
        if self._loading:
            return
        table = self._active_table()
        if not table.rowCount():
            return
        item = table.item(table.rowCount() - 1, 1)
        if checked:
            item.setText("∞")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        else:
            lot_min = int(table.item(table.rowCount() - 1, 0).text())
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setText(str(lot_min))
        self._mark_dirty()
        self._refresh_validation(self._active_profile())

    def _add_row(self):
        table = self._active_table()
        last_row = table.rowCount() - 1
        was_infinite = last_row >= 0 and table.item(last_row, 1).text() == "∞"
        if last_row < 0:
            values = [1, None, 1, 0, 1, 1, 0, 1, 1, 0, 1]
        else:
            lot_min = int(table.item(last_row, 0).text())
            lot_max_text = table.item(last_row, 1).text()
            if was_infinite:
                table.item(last_row, 1).setFlags(
                    table.item(last_row, 1).flags() | Qt.ItemIsEditable
                )
                table.item(last_row, 1).setText(str(lot_min))
                next_min = lot_min + 1
            else:
                next_min = int(lot_max_text) + 1
            metrics = [int(table.item(last_row, col).text()) for col in range(2, 11)]
            values = [next_min, None if was_infinite else next_min, *metrics]
        new_row = table.rowCount()
        table.insertRow(new_row)
        self._populate_row(table, new_row, values)
        table.selectRow(new_row)
        self._sync_infinite_checkbox()
        self._mark_dirty()
        self._refresh_validation(self._active_profile())

    def _delete_row(self):
        table = self._active_table()
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Selezione", "Seleziona la riga da eliminare."
            )
            return
        if table.rowCount() == 1:
            QMessageBox.warning(
                self, "Piano non valido", "Ogni piano deve contenere almeno una riga."
            )
            return

        table.removeRow(row)
        table.selectRow(min(row, table.rowCount() - 1))
        self._sync_infinite_checkbox()
        self._mark_dirty()
        self._refresh_validation(self._active_profile(), show_dialog=True)

    def _restore_defaults(self, profile: str):
        reply = QMessageBox.question(
            self,
            f"Ripristina {profile}",
            f"Ripristinare il piano {profile} con i valori originali?\n"
            "Le modifiche saranno registrate solo premendo Salva tabelle.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        table = self.tables[profile]
        table.blockSignals(True)
        try:
            defaults = db.get_sampling_plan_defaults(profile)
            table.setRowCount(len(defaults))
            for row_index, row in enumerate(defaults):
                values = [row[column] for column in SAMPLING_PLAN_COLUMNS]
                self._populate_row(table, row_index, values)
        finally:
            table.blockSignals(False)
        if profile == self._active_profile():
            self._sync_infinite_checkbox()
        self._mark_dirty()
        self._refresh_validation(profile)

    def _plans_payload(self) -> dict[str, list[dict]]:
        return {profile: self._table_payload(profile) for profile in self.tables}

    def save(self, sampling_class_id: int | None = None) -> bool:
        sampling_class_id = sampling_class_id or self._current_class_id
        if sampling_class_id is None:
            QMessageBox.warning(
                self, "Classe mancante",
                "Seleziona una classe di campionamento."
            )
            return False
        try:
            plans = self._plans_payload()
            validate_sampling_plans(plans)
            db.save_sampling_plans(sampling_class_id, plans)
        except (TypeError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Piani non validi", str(exc))
            return False
        self.dirty = False
        self.btn_save.setEnabled(False)
        QMessageBox.information(
            self, "Campionamento",
            "I tre piani della classe di campionamento sono stati salvati."
        )
        return True


class OptionsTab(QWidget):
    """Preferenze applicative salvate nel file di configurazione."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._saved = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        form = QFormLayout()
        self.label_enable = QCheckBox("Proponi la stampa dell'etichetta a fine controllo")
        self.audio_enable = QCheckBox("Abilita i suoni PASS/FAIL durante il controllo")
        self.audio_enable.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        self.label_printer = QLineEdit()
        self.labels_qta = QSpinBox()
        self.labels_qta.setRange(1, 999)
        self.decimal_separator = QComboBox()
        self.decimal_separator.addItem("Punto (.)", ".")
        self.decimal_separator.addItem("Virgola (,)", ",")
        form.addRow("Stampa etichette:", self.label_enable)
        form.addRow("Nome stampante CUPS:", self.label_printer)
        form.addRow("Copie etichetta:", self.labels_qta)
        form.addRow("Separatore decimale:", self.decimal_separator)
        form.addRow("Feedback audio:", self.audio_enable)
        self.audio_files = {}
        self._audio_preview = MeasurementSoundPlayer(self)
        self.audio_status = QLabel()
        self.audio_status.setWordWrap(True)
        self._audio_preview.error_occurred.connect(self.audio_status.setText)
        self._audio_preview.playback_started.connect(
            lambda: self.audio_status.setText("Riproduzione avviata. Se non senti il suono, verifica volume e uscita audio della VM.")
        )
        for key, label, passed in (("audio_pass_file", "Suono PASS:", True),
                                   ("audio_fail_file", "Suono FAIL:", False)):
            row = QHBoxLayout()
            field = QLineEdit()
            field.setPlaceholderText("Suono predefinito (campo vuoto)")
            self.audio_files[key] = field
            row.addWidget(field, 1)
            for text, icon, callback in (
                ("Sfoglia…", QStyle.SP_DialogOpenButton,
                 lambda _=False, f=field: self._choose_audio(f)),
                ("Predefinito", QStyle.SP_DialogResetButton,
                 lambda _=False, f=field: f.clear()),
                ("Prova", QStyle.SP_MediaPlay,
                 lambda _=False, f=field, p=passed: self._test_audio(p, f.text().strip())),
            ):
                button = QPushButton(text)
                button.setIcon(self.style().standardIcon(icon))
                button.clicked.connect(callback)
                row.addWidget(button)
            form.addRow(label, row)
        form.addRow("Prova audio:", self.audio_status)
        self.report_footer_text = QLineEdit()
        self.report_footer_text.setPlaceholderText("Es. Nome azienda (facoltativo)")
        form.addRow("Testo footer report:", self.report_footer_text)
        self.paths = {}
        for key, label in (("db_path", "Database:"), ("pdf_dir", "Cartella PDF:")):
            field = QLineEdit()
            field.setReadOnly(True)
            self.paths[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        info = QLabel("Le modifiche vengono applicate con Salva opzioni. "
                      "Riapri le finestre già aperte per aggiornare la visualizzazione dei numeri.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.btn_save = QPushButton("Salva opzioni")
        self.btn_save.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_save.setProperty("role", "primary")
        self.btn_save.clicked.connect(self.save)
        layout.addWidget(self.btn_save, alignment=Qt.AlignLeft)
        layout.addStretch()
        try:
            cfg = app_config.load_or_create_config()
            for key, field in self.audio_files.items():
                field.setText(cfg.get(key, ""))
            self.label_printer.setText(cfg["label_printer"])
            self.report_footer_text.setText(cfg["report_footer_text"])
            self.labels_qta.setValue(int(cfg["labels_qta"]))
            self.label_enable.setChecked(
                cfg["label_enable"].upper() in {"YES", "Y", "TRUE", "1", "ON"}
            )
            self.audio_enable.setChecked(
                cfg["audio_enable"].strip().upper() in {"YES", "Y", "TRUE", "1", "ON"}
            )
            self.decimal_separator.setCurrentIndex(1 if cfg["decimal_separator"] == "," else 0)
            for key, field in self.paths.items():
                field.setText(cfg[key])
            self._saved = self._values()
            self.status.setText(f"File opzioni: {app_config.get_options_path()}")
        except (OSError, ValueError) as exc:
            self.status.setText(f"Impossibile caricare le opzioni: {exc}")
            self.btn_save.setEnabled(False)

    def _choose_audio(self, field):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Scegli file audio", field.text(),
            "Audio (*.wav *.oga *.ogg *.mp3 *.flac);;Tutti i file (*)"
        )
        if filename:
            field.setText(filename)

    def _test_audio(self, passed, filename):
        self.audio_status.setText("Avvio della prova audio…")
        self._audio_preview.play_file(passed, filename)

    def hideEvent(self, event):
        self._audio_preview.stop()
        super().hideEvent(event)

    def _values(self):
        return {
            **{key: field.text().strip() for key, field in self.audio_files.items()},
            "label_printer": self.label_printer.text().strip(),
            "labels_qta": str(self.labels_qta.value()),
            "label_enable": "YES" if self.label_enable.isChecked() else "NO",
            "audio_enable": "YES" if self.audio_enable.isChecked() else "NO",
            "report_footer_text": self.report_footer_text.text().strip(),
            "decimal_separator": self.decimal_separator.currentData(),
        }

    @property
    def dirty(self):
        return self._saved is not None and self._values() != self._saved

    def save(self):
        try:
            values = self._values()
            app_config.save_options(values)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Opzioni non salvate", str(exc))
            return False
        self._saved = values
        self.status.setText("Opzioni salvate.")
        return True


class MasterDataWindow(QMainWindow):
    """Finestra Configurazione con registri, classi e piani di campionamento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QC Inspector — Configurazione")
        self.resize(1240, 720)
        self.setMinimumSize(980, 620)

        central = QWidget()
        central.setObjectName("masterDataRoot")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        central.setStyleSheet("""
            QWidget#masterDataRoot { background:#f4f6f8; }
            QFrame#masterDataHeader {
                background:#1f4e78; border-radius:8px;
            }
            QLabel#sectionDescription { color:#52616e; font-size:10pt; }
            QLabel#recordCount {
                color:#5f6f7d; background:#eef2f5; border:1px solid #d8dee5;
                border-radius:10px; padding:3px 10px;
            }
            QTabWidget::pane {
                background:white; border:1px solid #d8dee5;
                border-radius:7px; top:-1px;
            }
            QTabBar::tab {
                background:#e8edf2; color:#435363; border:1px solid #d1d9e0;
                border-bottom:none; padding:10px 18px; margin-right:2px;
                font-weight:600;
            }
            QTabBar::tab:selected { background:white; color:#1f4e78; }
            QTabBar::tab:hover:!selected { background:#f1f4f7; }
            QPushButton {
                min-height:30px; padding:2px 13px; border:1px solid #b7c1cb;
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
            QComboBox, QSpinBox {
                min-height:28px; background:white; border:1px solid #b7c1cb;
                border-radius:4px; padding:0 7px;
            }
            QComboBox:focus, QSpinBox:focus { border:2px solid #2f75b5; }
            QTableWidget#registryTable {
                background:white; alternate-background-color:#f6f8fa;
                border:1px solid #d8dee5; border-radius:5px;
                selection-background-color:#dcecf8;
                selection-color:#173c5e;
            }
            QTableWidget#registryTable QHeaderView::section {
                background:#e9edf2; color:#2f3b48; border:none;
                border-right:1px solid #d4dbe2; border-bottom:1px solid #c9d2db;
                padding:7px; font-weight:bold;
            }
        """)

        header = QFrame()
        header.setObjectName("masterDataHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Configurazione")
        title.setStyleSheet("color:white; font-size:17px; font-weight:bold;")
        info = QLabel(
            "Gestisci operatori, fornitori, classi di collaudo e piani di "
            "campionamento. I campi contrassegnati con * sono obbligatori."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#e6eef5; font-size:10pt;")
        header_layout.addWidget(title)
        header_layout.addWidget(info)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(RegistryTab("operator"), "Operatori")
        self.tabs.addTab(RegistryTab("supplier"), "Fornitori")
        self.sampling_class_tab = RegistryTab("sampling_class")
        self.tabs.addTab(self.sampling_class_tab, "Classi di campionamento")
        self.sampling_tab = SamplingPlansTab()
        self.tabs.addTab(self.sampling_tab, "Campionamento")
        self.options_tab = OptionsTab()
        self.tabs.addTab(self.options_tab, "Opzioni")
        self.sampling_class_tab.records_changed.connect(
            self.sampling_tab.refresh_classes
        )
        layout.addWidget(self.tabs)

    def closeEvent(self, event):
        if not self.sampling_tab.dirty and not self.options_tab.dirty:
            event.accept()
            return
        reply = QMessageBox.question(
            self,
            "Modifiche non salvate",
            "La configurazione contiene modifiche non salvate.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            for tab in (self.sampling_tab, self.options_tab):
                if tab.dirty and not tab.save():
                    event.ignore()
                    return
            event.accept()
        elif reply == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()
