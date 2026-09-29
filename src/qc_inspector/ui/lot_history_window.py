"""
lot_history_window.py
Finestra storico lotti: selezione setup, elenco lotti e rigenerazione report PDF.
"""

from PyQt5.QtCore import Qt, QDate, QRectF
from PyQt5.QtGui import QColor, QBrush, QPainter, QPen, QFont
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QTableWidget, QTableWidgetItem,
    QPushButton, QFileDialog, QMessageBox, QHeaderView, QStyle,
    QDialog, QDialogButtonBox, QFormLayout, QDateEdit, QCompleter,
    QTabWidget, QFrame, QGridLayout, QSizePolicy
)

from ..database import db_manager as db
from ..core.report_generator import generate_report, generate_global_supplier_report


class BarChartWidget(QWidget):
    """Grafico a barre leggero, senza dipendenze esterne."""

    def __init__(self, title: str, value_suffix: str = "",
                 maximum: float | None = None, color: str = "#2f78b7",
                 parent=None):
        super().__init__(parent)
        self._title = title
        self._value_suffix = value_suffix
        self._maximum = maximum
        self._color = QColor(color)
        self._values: list[tuple[str, float]] = []
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, values: list[tuple[str, float]]):
        self._values = values[-10:]
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#e0e5ea")))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6
        )
        painter.setPen(QPen(self.palette().text().color()))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(
            QRectF(8, 5, self.width() - 16, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._title,
        )

        chart = QRectF(42, 34, max(10, self.width() - 54), max(20, self.height() - 68))
        painter.setPen(QPen(QColor("#9aa5ad")))
        painter.drawLine(chart.bottomLeft(), chart.bottomRight())
        painter.drawLine(chart.bottomLeft(), chart.topLeft())

        if not self._values:
            painter.setPen(QPen(QColor("#777777")))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(chart, Qt.AlignCenter, "Nessun dato disponibile")
            return

        maximum = self._maximum or max(value for _, value in self._values) or 1.0
        slot_width = chart.width() / len(self._values)
        bar_width = min(42.0, slot_width * 0.58)
        painter.setFont(QFont("Arial", 8))
        for index, (label, value) in enumerate(self._values):
            height = chart.height() * value / maximum
            x = chart.left() + index * slot_width + (slot_width - bar_width) / 2
            bar = QRectF(x, chart.bottom() - height, bar_width, height)
            painter.fillRect(bar, self._color if value > 0 else QColor("#b8c0c6"))
            painter.setPen(QPen(self.palette().text().color()))
            value_text = f"{value:.1f}{self._value_suffix}" if self._value_suffix else f"{value:g}"
            painter.drawText(
                QRectF(x - 8, max(chart.top(), bar.top() - 18), bar_width + 16, 16),
                Qt.AlignCenter, value_text,
            )
            short_label = label if len(label) <= 10 else f"{label[:9]}…"
            painter.drawText(
                QRectF(chart.left() + index * slot_width, chart.bottom() + 3, slot_width, 18),
                Qt.AlignHCenter | Qt.AlignTop, short_label,
            )


class LotHistoryWindow(QMainWindow):
    """Finestra per consultare i lotti di un setup e rigenerare report."""

    @staticmethod
    def _empty_statistics() -> dict:
        return {
            "totals": {
                "lots": 0, "complete_lots": 0, "lot_quantity": 0,
                "inspected_samples": 0, "conforming_samples": 0,
                "failed_samples": 0, "derogated_samples": 0,
                "sample_conformity_percent": 0.0,
                "lot_conformity_percent": 0.0,
            },
            "by_lot": {},
            "fail_by_control": [],
            "dimensional_controls": [],
        }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setups: list[dict] = []
        self._lots: list[dict] = []
        self._statistics: dict = self._empty_statistics()
        self.setWindowTitle("QC Inspector - Storico lotti")
        self.resize(1280, 820)
        self.setMinimumSize(980, 650)
        self._build_ui()
        self._load_setups()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("historyRoot")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        central.setStyleSheet("""
            QWidget#historyRoot { background:#f4f6f8; }
            QFrame#historyHeader { background:#1f4e78; border-radius:8px; }
            QFrame#filterCard {
                background:white; border:1px solid #d8dee5;
                border-radius:7px;
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
            QComboBox, QDateEdit {
                min-height:30px; background:white; border:1px solid #b7c1cb;
                border-radius:4px; padding:0 8px;
            }
            QComboBox:focus, QDateEdit:focus { border:2px solid #2f75b5; }
            QTableWidget {
                background:white; alternate-background-color:#f6f8fa;
                border:1px solid #d8dee5; border-radius:6px;
                selection-background-color:#dcecf8;
                selection-color:#173c5e;
            }
            QHeaderView::section {
                background:#e9edf2; color:#2f3b48; border:none;
                border-right:1px solid #d4dbe2; border-bottom:1px solid #c9d2db;
                padding:7px; font-weight:bold;
            }
            QFrame#metricCard {
                background:#f8fafb; border:1px solid #d8dee5;
                border-radius:6px;
            }
            QWidget#chartCard {
                background:white; border:1px solid #e0e5ea;
                border-radius:6px;
            }
            QLabel#lotCount {
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
            QPushButton:disabled { color:#9aa5ae; background:#edf0f2; }
        """)

        header_frame = QFrame()
        header_frame.setObjectName("historyHeader")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Storico lotti e statistiche")
        title.setStyleSheet("color:white; font-size:17px; font-weight:bold;")
        intro = QLabel(
            "Consulta i controlli eseguiti, analizza qualità e misure e "
            "rigenera i report PDF."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#e6eef5; font-size:10pt;")
        header_layout.addWidget(title)
        header_layout.addWidget(intro)
        layout.addWidget(header_frame)

        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        top = QHBoxLayout(filter_card)
        top.setContentsMargins(12, 10, 12, 10)
        top.setSpacing(10)
        top.addWidget(QLabel("<b>Setup:</b>"))

        self.cmb_setup = QComboBox()
        self.cmb_setup.setMinimumWidth(360)
        self.cmb_setup.setEditable(True)
        self.cmb_setup.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_setup.lineEdit().setPlaceholderText(
            "Digita per cercare un setup…"
        )
        self.cmb_setup.lineEdit().textEdited.connect(self._on_setup_search_edited)
        self.cmb_setup.currentIndexChanged.connect(self._on_setup_changed)
        top.addWidget(self.cmb_setup)
        top.addStretch()

        self.btn_refresh = QPushButton("Aggiorna")
        self.btn_refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_refresh.clicked.connect(self._refresh_lots)
        top.addWidget(self.btn_refresh)

        layout.addWidget(filter_card)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        overview_page = QWidget()
        overview_layout = QVBoxLayout(overview_page)
        overview_layout.setContentsMargins(4, 8, 4, 4)

        self.tbl_lots = QTableWidget(0, 12)
        self.tbl_lots.setHorizontalHeaderLabels([
            "Data",
            "Operatore",
            "Cod. Lotto",
            "Rev.",
            "Q.tà lotto",
            "Piano",
            "Controllati",
            "PASS",
            "FAIL",
            "Deroghe",
            "Esito",
            "Stato",
        ])
        self.tbl_lots.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_lots.setSelectionMode(QTableWidget.SingleSelection)
        self.tbl_lots.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_lots.setAlternatingRowColors(True)
        self.tbl_lots.setShowGrid(False)
        self.tbl_lots.verticalHeader().setVisible(False)
        self.tbl_lots.verticalHeader().setDefaultSectionSize(32)
        self.tbl_lots.itemSelectionChanged.connect(self._update_actions)
        header = self.tbl_lots.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for column in range(12):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_lots.setMinimumHeight(250)
        overview_layout.addWidget(self.tbl_lots)

        metrics_layout = QGridLayout()
        metrics_layout.setHorizontalSpacing(8)
        self.metric_values = {}
        metric_definitions = [
            ("lots", "Lotti validi"),
            ("quantity", "Q.tà totale lotti"),
            ("samples", "Pezzi controllati"),
            ("sample_rate", "Campioni conformi"),
            ("lot_rate", "Lotti conformi"),
        ]
        for column, (key, title) in enumerate(metric_definitions):
            frame = QFrame()
            frame.setObjectName("metricCard")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(8, 5, 8, 5)
            caption = QLabel(title)
            caption.setStyleSheet("color:#666; font-size:9pt;")
            value_label = QLabel("—")
            value_label.setFont(QFont("Arial", 15, QFont.Bold))
            frame_layout.addWidget(caption)
            frame_layout.addWidget(value_label)
            self.metric_values[key] = value_label
            metrics_layout.addWidget(frame, 0, column)
        overview_layout.addLayout(metrics_layout)

        charts_layout = QHBoxLayout()
        self.chart_lot_conformity = BarChartWidget(
            "Conformità campioni per lotto", "%", maximum=100.0
        )
        self.chart_lot_conformity.setObjectName("chartCard")
        charts_layout.addWidget(self.chart_lot_conformity)
        self.chart_control_failures = BarChartWidget(
            "FAIL per balloon", color="#c34b43"
        )
        self.chart_control_failures.setObjectName("chartCard")
        charts_layout.addWidget(self.chart_control_failures)
        overview_layout.addLayout(charts_layout)
        self.tabs.addTab(overview_page, "Lotti e statistiche")

        details_page = QWidget()
        details_layout = QVBoxLayout(details_page)
        details_info = QLabel(
            "Statistiche delle misure dimensionali dei lotti chiusi e non annullati."
        )
        details_info.setStyleSheet("color:#52616e; font-size:10pt;")
        details_layout.addWidget(details_info)
        self.tbl_dimensions = QTableWidget(0, 9)
        self.tbl_dimensions.setHorizontalHeaderLabels([
            "Balloon", "Descrizione", "Nominale", "Misure",
            "Media", "Minimo", "Massimo", "Dev. standard", "FAIL",
        ])
        self.tbl_dimensions.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_dimensions.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_dimensions.setAlternatingRowColors(True)
        self.tbl_dimensions.setShowGrid(False)
        self.tbl_dimensions.verticalHeader().setVisible(False)
        self.tbl_dimensions.verticalHeader().setDefaultSectionSize(32)
        dimensions_header = self.tbl_dimensions.horizontalHeader()
        dimensions_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        dimensions_header.setSectionResizeMode(1, QHeaderView.Stretch)
        details_layout.addWidget(self.tbl_dimensions)
        self.tabs.addTab(details_page, "Dettaglio quote")
        layout.addWidget(self.tabs)

        bottom = QHBoxLayout()
        self.lbl_count = QLabel("Lotti: 0")
        self.lbl_count.setObjectName("lotCount")
        bottom.addWidget(self.lbl_count)
        bottom.addStretch()

        self.btn_global_report = QPushButton("Stampa Report Globale")
        self.btn_global_report.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        )
        self.btn_global_report.clicked.connect(self._on_global_report)
        bottom.addWidget(self.btn_global_report)

        self.btn_report = QPushButton("Rigenera report PDF")
        self.btn_report.setProperty("role", "primary")
        self.btn_report.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_report.clicked.connect(self._on_regenerate_report)
        self.btn_report.setEnabled(False)
        bottom.addWidget(self.btn_report)

        layout.addLayout(bottom)
        self.statusBar().setStyleSheet(
            "QStatusBar { background:#eef2f5; color:#52616e; "
            "border-top:1px solid #d8dee5; }"
        )
        self.statusBar().showMessage("Seleziona un setup per consultare lo storico lotti")

    def _on_global_report(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Periodo report globale fornitori")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "Seleziona il periodo da analizzare. Verranno considerati tutti i "
            "setup e soltanto i lotti completati e non annullati."
        ))

        form = QFormLayout()
        today = QDate.currentDate()
        start_date = QDate(today.year(), today.month(), 1)
        date_from = QDateEdit(start_date)
        date_from.setCalendarPopup(True)
        date_from.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data inizio:", date_from)
        date_to = QDateEdit(today)
        date_to.setCalendarPopup(True)
        date_to.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data fine:", date_to)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Genera report PDF")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QDialog.Accepted:
            return

        if date_from.date() > date_to.date():
            QMessageBox.warning(
                self, "Periodo non valido",
                "La data di inizio non può essere successiva alla data di fine."
            )
            return

        start_iso = date_from.date().toString("yyyy-MM-dd")
        end_iso = date_to.date().toString("yyyy-MM-dd")
        statistics = db.get_supplier_quality_statistics(start_iso, end_iso)
        if statistics["totals"]["lots"] == 0:
            QMessageBox.information(
                self, "Report globale",
                "Nel periodo selezionato non risultano lotti completi e non annullati."
            )
            return

        default_name = f"report_fornitori_{start_iso}_{end_iso}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva report globale fornitori", default_name, "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            generate_global_supplier_report(path, statistics)
        except Exception as error:
            QMessageBox.critical(
                self, "Errore",
                f"Errore generazione report globale:\n{error}"
            )
            return
        QMessageBox.information(
            self, "Report globale",
            f"Report globale fornitori salvato:\n{path}"
        )
        self.statusBar().showMessage(f"Report globale salvato: {path}")

    def _load_setups(self):
        self._setups = db.get_all_setups()
        self.cmb_setup.blockSignals(True)
        self.cmb_setup.clear()
        for setup in self._setups:
            self.cmb_setup.addItem(setup["name"], setup["id"])
        completer = QCompleter(self.cmb_setup.model(), self.cmb_setup)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setMaxVisibleItems(12)
        self.cmb_setup.setCompleter(completer)
        self.cmb_setup.blockSignals(False)

        if self._setups:
            self.cmb_setup.setCurrentIndex(0)
            self._refresh_lots()
        else:
            self._lots = []
            self._statistics = self._empty_statistics()
            self._populate_table()
            self._populate_statistics()
            self.statusBar().showMessage("Nessun setup salvato")

    def _on_setup_changed(self, index: int):
        if index >= 0:
            self._refresh_lots()

    def _on_setup_search_edited(self, _text: str):
        if self.cmb_setup.currentIndex() >= 0:
            return
        self._lots = []
        self._statistics = self._empty_statistics()
        self._populate_table()
        self._populate_statistics()
        self.statusBar().showMessage(
            "Digita il nome e seleziona un setup dai risultati"
        )

    def _refresh_lots(self):
        setup_id = self.cmb_setup.currentData()
        if setup_id is None:
            self._lots = []
            self._statistics = self._empty_statistics()
        else:
            self._lots = db.get_lot_history_for_setup(int(setup_id))
            self._statistics = db.get_setup_quality_statistics(int(setup_id))
        self._populate_table()
        self._populate_statistics()

    def _populate_table(self):
        self.tbl_lots.setRowCount(0)
        for lot in self._lots:
            row = self.tbl_lots.rowCount()
            self.tbl_lots.insertRow(row)
            lot_statistics = self._statistics["by_lot"].get(lot["id"], {})
            values = [
                self._format_datetime(lot.get("created_at")),
                lot.get("operator") or "—",
                lot.get("lot_code") or "—",
                str(lot.get("setup_version_number") or "—"),
                self._format_integer(lot.get("lot_quantity")),
                (lot.get("sampling_profile") or "—").title(),
                self._format_stat_count(lot_statistics, "inspected"),
                self._format_stat_count(lot_statistics, "pass"),
                self._format_stat_count(lot_statistics, "fail"),
                self._format_stat_count(lot_statistics, "derogated"),
                lot.get("result") or "—",
                lot.get("state") or "—",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter if col >= 3 else Qt.AlignVCenter | Qt.AlignLeft)
                if col == 0:
                    item.setData(Qt.UserRole, lot["id"])
                self._apply_item_style(item, col, lot)
                self.tbl_lots.setItem(row, col, item)

        self.lbl_count.setText(f"Lotti: {len(self._lots)}")
        self._update_actions()
        if self._lots:
            self.statusBar().showMessage("Storico lotti caricato")
        else:
            self.statusBar().showMessage("Nessun lotto per il setup selezionato")

    def _apply_item_style(self, item: QTableWidgetItem, col: int, lot: dict):
        if col == 10:
            result = lot.get("result")
            if result == "PASS":
                item.setForeground(QBrush(QColor("#155724")))
                item.setBackground(QBrush(QColor("#d4edda")))
            elif result == "FAIL":
                item.setForeground(QBrush(QColor("#721c24")))
                item.setBackground(QBrush(QColor("#f8d7da")))
            elif result == "ACCETTATO IN DEROGA":
                item.setForeground(QBrush(QColor("#7a4b00")))
                item.setBackground(QBrush(QColor("#fff3cd")))
            elif result == "INCOMPLETO":
                item.setForeground(QBrush(QColor("#7a4b00")))
                item.setBackground(QBrush(QColor("#fff3cd")))
        elif col == 11 and lot.get("state") == "ANNULLATO":
            item.setForeground(QBrush(QColor("#555555")))
            item.setBackground(QBrush(QColor("#eeeeee")))

    def _populate_statistics(self):
        totals = self._statistics["totals"]
        self.metric_values["lots"].setText(
            f"{totals['complete_lots']} / {totals['lots']}"
        )
        self.metric_values["lots"].setToolTip(
            "Lotti completi / lotti chiusi e non annullati"
        )
        self.metric_values["quantity"].setText(
            self._format_integer(totals["lot_quantity"])
        )
        self.metric_values["samples"].setText(
            self._format_integer(totals["inspected_samples"])
        )
        self.metric_values["sample_rate"].setText(
            f"{totals['sample_conformity_percent']:.1f}%"
        )
        self.metric_values["lot_rate"].setText(
            f"{totals['lot_conformity_percent']:.1f}%"
        )

        lot_values = []
        for lot in reversed(self._lots):
            lot_statistics = self._statistics["by_lot"].get(lot["id"])
            if lot_statistics and lot_statistics["inspected"]:
                lot_values.append((
                    str(lot.get("lot_code") or lot["id"]),
                    float(lot_statistics["conformity_percent"]),
                ))
        self.chart_lot_conformity.set_values(lot_values)
        self.chart_control_failures.set_values([
            (f"B{item['balloon_num']}", float(item["fail_count"]))
            for item in self._statistics["fail_by_control"][:10]
        ])

        dimensions = self._statistics["dimensional_controls"]
        self.tbl_dimensions.setRowCount(len(dimensions))
        for row, item in enumerate(dimensions):
            nominal = item.get("nominal")
            values = [
                str(item["balloon_num"]),
                item["label"],
                self._format_decimal(nominal),
                str(item["count"]),
                self._format_decimal(item["average"]),
                self._format_decimal(item["minimum"]),
                self._format_decimal(item["maximum"]),
                self._format_decimal(item["std_dev"]),
                f"{item['fail_count']} ({item['fail_percent']:.1f}%)",
            ]
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                table_item.setTextAlignment(
                    Qt.AlignVCenter | (Qt.AlignLeft if column == 1 else Qt.AlignCenter)
                )
                self.tbl_dimensions.setItem(row, column, table_item)

    @staticmethod
    def _format_stat_count(statistics: dict, key: str) -> str:
        return str(statistics[key]) if statistics else "—"

    @staticmethod
    def _format_integer(value) -> str:
        return f"{int(value or 0):,}".replace(",", ".")

    @staticmethod
    def _format_decimal(value) -> str:
        if value is None:
            return "—"
        return f"{float(value):.3f}".replace(".", ",")

    def _selected_lot(self) -> dict | None:
        selected = self.tbl_lots.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        id_item = self.tbl_lots.item(row, 0)
        if id_item is None:
            return None
        lot_id = id_item.data(Qt.UserRole)
        return next((lot for lot in self._lots if lot["id"] == lot_id), None)

    def _update_actions(self):
        self.btn_report.setEnabled(self._selected_lot() is not None)

    def _on_regenerate_report(self):
        lot = self._selected_lot()
        if not lot:
            return

        if not lot.get("is_complete"):
            QMessageBox.warning(
                self,
                "Report non disponibile",
                "Il lotto selezionato non ha tutte le misure previste."
            )
            return

        report_data = db.get_lot_report_data(lot["id"])
        if not report_data:
            QMessageBox.critical(
                self,
                "Errore",
                "Impossibile recuperare i dati del lotto selezionato."
            )
            return

        setup = report_data["setup"]
        default_name = self._default_report_name(setup, lot)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva report",
            default_name,
            "PDF (*.pdf)"
        )
        if not path:
            return

        try:
            generate_report(
                path,
                report_data["setup"],
                report_data["controls"],
                report_data["summary"]
            )
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore generazione report:\n{e}")
            return

        QMessageBox.information(self, "Report", f"Report salvato:\n{path}")
        self.statusBar().showMessage(f"Report rigenerato: {path}")

    @staticmethod
    def _default_report_name(setup: dict, lot: dict) -> str:
        def safe_part(text: str) -> str:
            cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
            return cleaned.strip("_") or "valore"

        setup_name = safe_part(str(setup.get("name") or "setup"))
        lot_code = safe_part(str(lot.get("lot_code") or "lotto"))
        return f"{setup_name}_{lot_code}.pdf"

    @staticmethod
    def _format_datetime(value: str | None) -> str:
        if not value:
            return "—"
        return value[:19].replace("T", " ")
