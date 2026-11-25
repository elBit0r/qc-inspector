"""Preferenze di stampa e composizione dell'etichetta."""

import json
from os.path import join
from tempfile import TemporaryDirectory

import fitz
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QStyle, QVBoxLayout, QWidget,
)

from ..core import app_config
from ..core.inspection_engine import STATUS_PASS
from ..core.label_printer import (
    LABEL_FIELDS, available_label_printers, generate_label_pdf, print_label,
    render_label_pdf,
)


EXAMPLE_SETUP = {"name": "PIASTRA-01", "description": "Piastra di fissaggio"}
EXAMPLE_SUMMARY = {
    "lot": {
        "lot_code": "L-2026-001", "operator": "Mario Rossi",
        "supplier": "Fornitore esempio", "created_at": "2026-01-15",
        "lot_quantity": 250, "n_samples": 8,
    },
    "sampling_evaluation": {"status": STATUS_PASS},
}


class LabelOptionsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._saved = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        form = QFormLayout()
        self.auto_print = QCheckBox("Stampa automaticamente alla chiusura del controllo")
        form.addRow(self.auto_print)

        self.printer = QComboBox()
        self.printer.setMaximumWidth(320)
        printer_row = QHBoxLayout()
        printer_row.addWidget(self.printer)
        refresh = QPushButton("Aggiorna")
        refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh.clicked.connect(lambda: self._refresh_printers(self.printer.currentData()))
        printer_row.addWidget(refresh)
        printer_row.addStretch()
        form.addRow("Stampante CUPS", printer_row)
        self.printer_status = QLabel()
        self.printer_status.setWordWrap(True)
        form.addRow(self.printer_status)

        self.copies = QSpinBox()
        self.copies.setRange(1, 999)
        self.copies.setMaximumWidth(92)
        form.addRow("Numero di copie", self.copies)
        self.width_mm = QDoubleSpinBox()
        self.height_mm = QDoubleSpinBox()
        for title, spin in (("Larghezza", self.width_mm), ("Altezza", self.height_mm)):
            spin.setRange(*app_config.LABEL_SIZE_RANGE)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            spin.setMaximumWidth(135)
            form.addRow(title, spin)
        layout.addLayout(form)

        editor_row = QHBoxLayout()
        editor_group = QGroupBox("Contenuto etichetta")
        editor_layout = QVBoxLayout(editor_group)
        fields_row = QHBoxLayout()
        self.fields = QComboBox()
        self.fields.setAccessibleName("Campo da inserire")
        for key, label in LABEL_FIELDS.items():
            self.fields.addItem(label, key)
        fields_row.addWidget(self.fields, 1)
        insert = QPushButton("Inserisci campo")
        insert.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        insert.clicked.connect(self._insert_field)
        fields_row.addWidget(insert)
        editor_layout.addLayout(fields_row)
        markdown_help = QLabel(
            "Markdown: # Titolo · ## Sottotitolo · **grassetto** · *corsivo*\n"
            "Usa --- su una riga per inserire un separatore."
        )
        markdown_help.setTextFormat(Qt.PlainText)
        markdown_help.setWordWrap(True)
        editor_layout.addWidget(markdown_help)
        self.template = QPlainTextEdit()
        self.template.setAccessibleName("Modello di etichetta")
        editor_layout.addWidget(self.template, 1)
        reset = QPushButton("Ripristina testo predefinito")
        reset.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        reset.clicked.connect(
            lambda: self.template.setPlainText(app_config.DEFAULT_LABEL_TEMPLATE)
        )
        editor_layout.addWidget(reset, alignment=Qt.AlignLeft)
        editor_row.addWidget(editor_group, 1)

        preview_group = QGroupBox("Anteprima con dati di esempio")
        preview_layout = QVBoxLayout(preview_group)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview.setMinimumSize(280, 180)
        preview_layout.addWidget(self.preview, 1)
        editor_row.addWidget(preview_group, 1)
        layout.addLayout(editor_row, 1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.btn_save = QPushButton("Salva etichetta")
        self.btn_save.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_save.setProperty("role", "primary")
        self.btn_save.clicked.connect(self.save)
        actions.addWidget(self.btn_save)
        test_print = QPushButton("Stampa di prova")
        test_print.setIcon(QIcon.fromTheme(
            "document-print", self.style().standardIcon(QStyle.SP_FileIcon),
        ))
        test_print.clicked.connect(self._print_test_label)
        actions.addWidget(test_print)
        actions.addStretch()
        layout.addLayout(actions)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._update_preview)
        self.template.textChanged.connect(lambda: self._preview_timer.start())
        self.width_mm.valueChanged.connect(lambda: self._preview_timer.start())
        self.height_mm.valueChanged.connect(lambda: self._preview_timer.start())
        self._printers_loaded = False

        cfg = app_config.DEFAULT_CONFIG
        try:
            cfg = app_config.load_or_create_config()
            width, height, template = app_config.get_label_layout(cfg)
        except (OSError, ValueError) as exc:
            self.status.setText(f"Impossibile caricare il modello di etichetta: {exc}")
            width, height, template = app_config.get_label_layout(app_config.DEFAULT_CONFIG)

        self.printer.addItem("Seleziona una stampante", "")
        if cfg["label_printer"]:
            self.printer.addItem(cfg["label_printer"], cfg["label_printer"])
            self.printer.setCurrentIndex(1)
        self.auto_print.setChecked(cfg["label_auto_print"].upper() == "YES")
        try:
            self.copies.setValue(int(cfg["labels_qta"]))
        except ValueError:
            self.copies.setValue(int(app_config.DEFAULT_CONFIG["labels_qta"]))
        self.width_mm.setValue(width)
        self.height_mm.setValue(height)
        self.template.setPlainText(template)
        self._saved = self._values()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._printers_loaded:
            self._refresh_printers(self.printer.currentData())

    def _refresh_printers(self, selected):
        self._printers_loaded = True
        try:
            printers = available_label_printers()
            message = "" if printers else "Nessuna stampante rilevata da CUPS."
        except RuntimeError as exc:
            printers = []
            message = f"Elenco stampanti non disponibile: {exc}"
        self.printer.clear()
        self.printer.addItem("Seleziona una stampante", "")
        for printer in printers:
            self.printer.addItem(printer, printer)
        if selected and selected not in printers:
            self.printer.addItem(f"{selected} (non rilevata)", selected)
        self.printer.setCurrentIndex(max(0, self.printer.findData(selected)))
        self.printer_status.setText(message)

    def _insert_field(self):
        self.template.insertPlainText("{" + self.fields.currentData() + "}")
        self.template.setFocus()

    def _update_preview(self):
        try:
            pdf = render_label_pdf(EXAMPLE_SETUP, EXAMPLE_SUMMARY, self._values())
            with fitz.open(stream=pdf, filetype="pdf") as document:
                page = document[0]
                scale = min(280 / page.rect.width, 180 / page.rect.height)
                pixels = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                preview = QPixmap()
                preview.loadFromData(pixels.tobytes("png"), "PNG")
            self.preview.setPixmap(preview)
        except (RuntimeError, ValueError) as exc:
            self.preview.setText(str(exc))

    def _print_test_label(self):
        self.status.clear()
        cfg = self._values()
        if not cfg["label_printer"]:
            QMessageBox.warning(self, "Stampa di prova", "Seleziona una stampante CUPS.")
            self.printer.setFocus()
            return

        cfg["labels_qta"] = "1"
        try:
            with TemporaryDirectory(prefix="qc_etichetta_prova_") as directory:
                path = join(directory, "etichetta-di-prova.pdf")
                ok, error = generate_label_pdf(path, EXAMPLE_SETUP, EXAMPLE_SUMMARY, cfg)
                if ok:
                    ok, error = print_label(path, cfg)
        except OSError as exc:
            ok, error = False, str(exc)

        if ok:
            self.status.setText("Etichetta di prova inviata alla stampante.")
        else:
            QMessageBox.warning(self, "Etichetta di prova non inviata", error)

    def _values(self):
        return {
            "label_auto_print": "YES" if self.auto_print.isChecked() else "NO",
            "label_printer": self.printer.currentData(),
            "labels_qta": str(self.copies.value()),
            "label_width_mm": f"{self.width_mm.value():g}",
            "label_height_mm": f"{self.height_mm.value():g}",
            "label_template": json.dumps(self.template.toPlainText(), ensure_ascii=False),
        }

    @property
    def dirty(self):
        return self._values() != self._saved

    def save(self):
        values = self._values()
        try:
            app_config.save_options(values)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Etichetta non salvata", str(exc))
            return False
        self._saved = values
        self.status.setText("Opzioni etichetta salvate.")
        return True
