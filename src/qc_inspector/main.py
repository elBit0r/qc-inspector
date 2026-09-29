"""
main.py
Punto di avvio di QC Inspector.
Mostra la schermata di selezione delle funzioni principali.
"""

import os
import sys
from datetime import date, timedelta
from importlib import metadata

# Consente anche Run di questo file da PyCharm, senza installare il package.
if not __package__ and not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSplitter, QToolButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QComboBox, QPushButton, QScrollArea, QToolTip, QSizePolicy, QStyle,
    QDialog, QTextBrowser
)
from PyQt5.QtCore import Qt, QSize, QEvent, QRectF, QUrl
from PyQt5.QtGui import (
    QFont, QColor, QPalette, QIcon, QBrush, QPainter, QPen
)

from qc_inspector import __version__
from qc_inspector.core.single_instance import SingleInstanceGuard
from qc_inspector.core.startup_checks import check_runtime_access, permission_error_message
from qc_inspector.database.schema_manager import initialize_database
from qc_inspector.database.db_manager import (
    get_all_setups, get_recent_lot_history,
    get_supplier_quality_statistics,
)
from qc_inspector.ui.programming_window import ProgrammingWindow, SetupOpenDialog
from qc_inspector.ui.inspection_window import InspectionStartDialog, InspectionWindow
from qc_inspector.ui.lot_history_window import LotHistoryWindow
from qc_inspector.ui.master_data_window import MasterDataWindow


app_version = __version__


def _resource_root() -> str:
    """Directory delle risorse, compatibile con PyInstaller."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS

    return os.path.dirname(os.path.abspath(__file__))


def _app_icon_path() -> str:
    return os.path.join(_resource_root(), "main-icon.png")


def _mode_icon_path(filename: str) -> str:
    return os.path.join(
        _resource_root(),
        "assets",
        "icons",
        filename,
    )


def _manual_path() -> str:
    """Percorso del manuale incluso nei sorgenti e nelle build."""
    return os.path.join(_resource_root(), "ISTRUZIONI_USO.md")


def _legal_document_path(filename: str) -> str:
    """Trova un documento legale nel bundle o nei metadati del package."""
    bundled_path = os.path.join(_resource_root(), filename)
    if os.path.isfile(bundled_path):
        return bundled_path
    try:
        distribution = metadata.distribution("qc-inspector")
        for entry in distribution.files or ():
            if entry.name == filename and "licenses" in entry.parts:
                candidate = distribution.locate_file(entry)
                if candidate.is_file():
                    return str(candidate)
    except (metadata.PackageNotFoundError, OSError):
        pass
    return bundled_path


class SupplierQualityChartWidget(QWidget):
    """Confronto visuale della qualita campionata per fornitore."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._hit_areas: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setMinimumWidth(900)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

    @staticmethod
    def _supplier_key(item: dict) -> str:
        supplier_id = item.get("supplier_id")
        if supplier_id is not None:
            return f"id:{supplier_id}"
        return f"name:{str(item.get('supplier') or '').casefold()}"

    def set_statistics(self, current: dict, previous: dict):
        previous_by_supplier = {
            self._supplier_key(item): item
            for item in previous.get("suppliers", [])
        }
        rows = []
        for item in current.get("suppliers", []):
            row = dict(item)
            pieces = int(row.get("pieces") or 0)
            technical_nc = int(row.get("failed") or 0) + int(row.get("derogated") or 0)
            row["technical_nc_rate"] = technical_nc / pieces * 100 if pieces else 0.0
            row["nonconforming_lots"] = (
                int(row.get("lot_fail") or 0)
                + int(row.get("lot_derogated") or 0)
            )
            prior = previous_by_supplier.get(self._supplier_key(row))
            if prior and int(prior.get("pieces") or 0):
                prior_pieces = int(prior["pieces"])
                prior_rate = (
                    int(prior.get("failed") or 0)
                    + int(prior.get("derogated") or 0)
                ) / prior_pieces * 100
                difference = row["technical_nc_rate"] - prior_rate
                if difference > 0.5:
                    row["trend"] = "↑ peggiora"
                elif difference < -0.5:
                    row["trend"] = "↓ migliora"
                else:
                    row["trend"] = "→ stabile"
            else:
                row["trend"] = "nuovo periodo"
            row["limited_data"] = pieces < 30 or int(row.get("lots") or 0) < 3
            rows.append(row)

        rows.sort(key=lambda item: (
            bool(item.get("unspecified")),
            -item["technical_nc_rate"],
            -item["nonconforming_lots"],
            -int(item.get("pieces") or 0),
            str(item.get("supplier") or "").casefold(),
        ))
        self._rows = rows
        self.setMinimumHeight(max(90, 34 + len(rows) * 34))
        self.updateGeometry()
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        self._hit_areas = []

        text_color = self.palette().text().color()
        painter.setPen(QPen(text_color))
        painter.setFont(QFont("Arial", 9))
        self._draw_legend(painter, text_color)

        if not self._rows:
            painter.setPen(QPen(QColor("#777777")))
            painter.drawText(self.rect(), Qt.AlignCenter, "Nessun dato fornitore disponibile")
            return

        name_width = 170.0
        bar_left = name_width + 10.0
        bar_right = max(bar_left + 160.0, self.width() - 455.0)
        bar_width = bar_right - bar_left
        row_height = 34.0
        bar_height = 18.0

        for index, row in enumerate(self._rows):
            top = 30.0 + index * row_height
            row_rect = QRectF(0, top, self.width(), row_height)
            if index % 2:
                painter.fillRect(row_rect, QColor("#f5f7fa"))

            supplier = str(row.get("supplier") or "Fornitore non specificato")
            supplier_text = painter.fontMetrics().elidedText(
                supplier, Qt.ElideRight, int(name_width - 12)
            )
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(8, top, name_width - 12, row_height),
                Qt.AlignVCenter | Qt.AlignLeft,
                supplier_text,
            )

            bar = QRectF(bar_left, top + 8, bar_width, bar_height)
            painter.fillRect(bar, QColor("#e6eaed"))
            x = bar.left()
            segments = [
                (float(row.get("pass_rate") or 0), QColor("#2e8b57")),
                (float(row.get("derogation_rate") or 0), QColor("#e0a000")),
                (float(row.get("fail_rate") or 0), QColor("#c43c35")),
            ]
            for percentage, color in segments:
                segment_width = bar.width() * max(0.0, min(100.0, percentage)) / 100.0
                if segment_width > 0:
                    painter.fillRect(QRectF(x, bar.top(), segment_width, bar.height()), color)
                x += segment_width
            painter.setPen(QPen(QColor("#9aa5ad")))
            painter.drawRect(bar)

            technical_rate = float(row["technical_nc_rate"])
            confidence = "⚠ pochi dati" if row["limited_data"] else "dati sufficienti"
            summary = (
                f"NC {technical_rate:.1f}%  |  "
                f"{row['nonconforming_lots']}/{int(row.get('lots') or 0)} lotti  |  "
                f"n={int(row.get('pieces') or 0)}  |  {row['trend']}  |  {confidence}"
            )
            painter.setPen(QPen(QColor("#b3261e") if technical_rate else QColor("#246b3a")))
            painter.drawText(
                QRectF(bar_right + 10, top, self.width() - bar_right - 16, row_height),
                Qt.AlignVCenter | Qt.AlignLeft,
                summary,
            )

            details = row.get("details") or []
            last_date = details[-1].get("date") if details else "—"
            tooltip = (
                f"{supplier}\n"
                f"Campioni: {int(row.get('pieces') or 0)}\n"
                f"Conformi: {int(row.get('passed') or 0)} "
                f"({float(row.get('pass_rate') or 0):.1f}%)\n"
                f"Deroghe: {int(row.get('derogated') or 0)} "
                f"({float(row.get('derogation_rate') or 0):.1f}%)\n"
                f"FAIL: {int(row.get('failed') or 0)} "
                f"({float(row.get('fail_rate') or 0):.1f}%)\n"
                f"Lotti PASS/Deroga/FAIL: {int(row.get('lot_pass') or 0)}/"
                f"{int(row.get('lot_derogated') or 0)}/{int(row.get('lot_fail') or 0)}\n"
                f"Ultimo controllo: {last_date}"
            )
            self._hit_areas.append((row_rect, tooltip))

    @staticmethod
    def _draw_legend(painter: QPainter, text_color: QColor):
        entries = [
            ("Conforme", QColor("#2e8b57")),
            ("Deroga", QColor("#e0a000")),
            ("FAIL", QColor("#c43c35")),
        ]
        x = 180
        for label, color in entries:
            painter.fillRect(QRectF(x, 8, 12, 12), color)
            painter.setPen(QPen(text_color))
            painter.drawText(QRectF(x + 17, 4, 75, 20), Qt.AlignVCenter, label)
            x += 90

    def mouseMoveEvent(self, event):
        for rect, tooltip in self._hit_areas:
            if rect.contains(event.pos()):
                QToolTip.showText(event.globalPos(), tooltip, self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

class LauncherWindow(QWidget):
    """Schermata di avvio: scelta tra modalità programmazione e controllo."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("QC Inspector — Controllo dimensionale")
        self.resize(1200, 900)
        self.setMinimumSize(1050, 780)
        self._prog_win: ProgrammingWindow | None = None
        self._insp_win: InspectionWindow | None = None
        self._history_win: LotHistoryWindow | None = None
        self._master_data_win: MasterDataWindow | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        # Titolo
        title = QLabel("QC Inspector")
        title.setFont(QFont("Arial", 28, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Controllo dimensionale di particolari meccanici")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #555;")
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Bottoni modalità
        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)

        btn_prog = self._make_mode_button(
            "PROGRAMMAZIONE",
            "Crea i setup di controllo,\nposiziona i balloon e\ndefinisci quote e tolleranze",
            "#1a4a7a", "#e8f0fa", "programming.svg"
        )
        btn_prog.clicked.connect(self._open_programming)
        btn_row.addWidget(btn_prog)

        btn_insp = self._make_mode_button(
            "CONTROLLO",
            "Avvia il controllo lotto,\nregistra le misure e\ngenera il report",
            "#1a5c1a", "#e8f5e8", "inspection.svg"
        )
        btn_insp.clicked.connect(self._open_inspection)
        btn_row.addWidget(btn_insp)

        btn_history = self._make_mode_button(
            "STORICO LOTTI",
            "Consulta lotti ed esiti,\nanalizza le misure e\nrigenera i report",
            "#6b4b00", "#fff7df", "history.svg"
        )
        btn_history.clicked.connect(self._open_lot_history)
        btn_row.addWidget(btn_history)

        btn_master_data = self._make_mode_button(
            "CONFIGURAZIONE",
            "Gestisci operatori, fornitori,\nclassi e piani\ndi campionamento",
            "#5b3575", "#f4eafa", "master-data.svg"
        )
        btn_master_data.clicked.connect(self._open_master_data)
        btn_row.addWidget(btn_master_data)

        layout.addLayout(btn_row)
        layout.addSpacing(8)

        # Sommario setup salvati
        setups = get_all_setups()
        count = len(setups)
        info = QLabel(
            f"Setup salvati nel database: {count}"
            + (f"  |  Ultimo: {setups[0]['name']}" if setups else "")
        )
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #777; font-size: 10pt;")
        layout.addWidget(info)

        recent_title = QLabel("Ultimi controlli eseguiti")
        recent_title.setFont(QFont("Arial", 12, QFont.Bold))
        recent_title.setStyleSheet("color: #333;")
        layout.addWidget(recent_title)

        self._recent_table = self._build_recent_table()
        layout.addWidget(self._recent_table)
        self._refresh_recent_table()

        supplier_header = QHBoxLayout()
        supplier_title = QLabel("Qualità fornitori")
        supplier_title.setFont(QFont("Arial", 12, QFont.Bold))
        supplier_title.setStyleSheet("color: #333;")
        supplier_header.addWidget(supplier_title)
        supplier_header.addStretch()
        supplier_header.addWidget(QLabel("Periodo:"))
        self._supplier_period = QComboBox()
        self._supplier_period.addItem("Ultimi 6 mesi", 180)
        self._supplier_period.addItem("Ultimi 12 mesi", 365)
        self._supplier_period.addItem("Ultimi 24 mesi", 730)
        self._supplier_period.setCurrentIndex(1)
        self._supplier_period.currentIndexChanged.connect(
            self._refresh_supplier_chart
        )
        supplier_header.addWidget(self._supplier_period)
        layout.addLayout(supplier_header)

        self._supplier_chart = SupplierQualityChartWidget()
        supplier_scroll = QScrollArea()
        supplier_scroll.setWidget(self._supplier_chart)
        supplier_scroll.setWidgetResizable(True)
        supplier_scroll.setFixedHeight(200)
        supplier_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        supplier_scroll.setStyleSheet(
            "QScrollArea { background:white; border:1px solid #cfd6df; "
            "border-radius:6px; }"
        )
        layout.addWidget(supplier_scroll)
        self._refresh_supplier_chart()

        # Versione e manuale
        footer = QHBoxLayout()
        footer.addStretch()
        ver = QLabel(
            f"v{app_version}  —  PyQt5 + PyMuPDF + ReportLab - "
            "vgiusti@unirc.eu"
        )
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("color: #aaa; font-size: 9pt;")
        footer.addWidget(ver)
        manual_button = QPushButton("Manuale d’uso")
        manual_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogHelpButton)
        )
        manual_button.setToolTip("Apri il manuale d’uso di QC Inspector")
        manual_button.clicked.connect(self._open_user_manual)
        footer.addWidget(manual_button)
        license_button = QPushButton("Licenza")
        license_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        license_button.clicked.connect(self._open_license)
        footer.addWidget(license_button)
        footer.addStretch()
        layout.addLayout(footer)

    def _open_license(self):
        try:
            with open(
                _legal_document_path("LICENSE"), encoding="utf-8"
            ) as source:
                text = source.read()
            with open(
                _legal_document_path("NOTICE.md"), encoding="utf-8"
            ) as source:
                notice = source.read()
            with open(
                _legal_document_path("THIRD_PARTY_NOTICES.md"),
                encoding="utf-8",
            ) as source:
                third_party = source.read()
        except OSError as exc:
            QMessageBox.warning(self, "Licenza non disponibile", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Licenza AGPL v3 — QC Inspector")
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setPlainText(notice + "\n\n" + third_party + "\n\n" + text)
        layout.addWidget(browser)
        dialog.exec_()

    def _open_user_manual(self):
        manual_path = _manual_path()
        if not os.path.isfile(manual_path):
            QMessageBox.warning(
                self,
                "Manuale non disponibile",
                "Il file del manuale d’uso non è stato trovato:\n"
                f"{manual_path}",
            )
            return

        try:
            with open(manual_path, "r", encoding="utf-8") as manual_file:
                manual_text = manual_file.read()
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Manuale non disponibile",
                "Non è stato possibile leggere il manuale d’uso:\n"
                f"{exc}",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Manuale d’uso — QC Inspector")
        dialog.resize(1000, 760)
        dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        viewer = QTextBrowser(dialog)
        viewer.setOpenExternalLinks(True)
        viewer.document().setBaseUrl(
            QUrl.fromLocalFile(os.path.dirname(manual_path) + os.sep)
        )
        viewer.setMarkdown(manual_text)
        layout.addWidget(viewer)

        close_button = QPushButton("Chiudi", dialog)
        close_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogCloseButton)
        )
        close_button.clicked.connect(dialog.accept)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        dialog.exec_()

    def _build_recent_table(self) -> QTableWidget:
        columns = [
            "Data/Ora", "Codice articolo", "Descrizione", "N° lotto",
            "Q.tà lotto", "Q.tà controllo", "Operatore", "Esito",
        ]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(27)
        table.setFixedHeight(180)
        table.setStyleSheet("""
            QTableWidget {
                background: white;
                alternate-background-color: #f5f7fa;
                border: 1px solid #cfd6df;
                border-radius: 6px;
                color: #333;
            }
            QHeaderView::section {
                background: #e9edf2;
                color: #2f3b48;
                border: none;
                border-right: 1px solid #cfd6df;
                border-bottom: 1px solid #cfd6df;
                padding: 5px;
                font-weight: bold;
            }
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setMinimumSectionSize(85)
        return table

    def _refresh_recent_table(self):
        if not hasattr(self, "_recent_table"):
            return
        lots = get_recent_lot_history(6)
        self._recent_table.setRowCount(len(lots))
        for row, lot in enumerate(lots):
            lot_quantity = int(lot.get("lot_quantity") or 0)
            values = [
                self._format_datetime(lot.get("created_at")),
                lot.get("setup_name") or "—",
                lot.get("setup_description") or "—",
                lot.get("lot_code") or "—",
                str(lot_quantity) if lot_quantity > 0 else "—",
                str(lot.get("n_samples") or 0),
                lot.get("operator") or "—",
                lot.get("result") or "—",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                alignment = Qt.AlignCenter
                if column in (1, 2, 6):
                    alignment = Qt.AlignVCenter | Qt.AlignLeft
                item.setTextAlignment(alignment)
                if column == 7:
                    self._style_result_item(item, lot.get("result"))
                self._recent_table.setItem(row, column, item)

    @staticmethod
    def _format_datetime(value) -> str:
        if not value:
            return "—"
        text = str(value)
        try:
            return f"{text[8:10]}/{text[5:7]}/{text[:4]} {text[11:16]}"
        except (IndexError, TypeError):
            return text

    @staticmethod
    def _style_result_item(item: QTableWidgetItem, result: str):
        colors_by_result = {
            "PASS": ("#155724", "#d4edda"),
            "FAIL": ("#721c24", "#f8d7da"),
            "ACCETTATO IN DEROGA": ("#7a4b00", "#fff3cd"),
            "INCOMPLETO": ("#7a4b00", "#fff3cd"),
            "ANNULLATO": ("#555555", "#eeeeee"),
        }
        foreground, background = colors_by_result.get(
            result, ("#666666", "#ffffff")
        )
        item.setForeground(QBrush(QColor(foreground)))
        item.setBackground(QBrush(QColor(background)))
        item.setFont(QFont("Arial", 9, QFont.Bold))

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.ActivationChange
                and self.isActiveWindow()
                and hasattr(self, "_recent_table")):
            self._refresh_recent_table()
            self._refresh_supplier_chart()

    def _refresh_supplier_chart(self):
        if not hasattr(self, "_supplier_chart"):
            return
        days = int(self._supplier_period.currentData() or 365)
        current_end = date.today()
        current_start = current_end - timedelta(days=days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)
        current = get_supplier_quality_statistics(
            current_start.isoformat(), current_end.isoformat()
        )
        previous = get_supplier_quality_statistics(
            previous_start.isoformat(), previous_end.isoformat()
        )
        self._supplier_chart.set_statistics(current, previous)

    def closeEvent(self, event):
        windows = [
            ("Programmazione", self._prog_win),
            ("Controllo", self._insp_win),
            ("Storico lotti", self._history_win),
            ("Configurazione", self._master_data_win),
        ]
        visible = [(name, window) for name, window in windows
                   if window is not None and window.isVisible()]
        if not visible:
            event.accept()
            return

        names = ", ".join(name for name, _ in visible)
        QMessageBox.information(
            self,
            "Finestre ancora aperte",
            f"Prima di chiudere il menu, chiudi le finestre ancora aperte:\n"
            f"{names}.",
        )
        visible[0][1].raise_()
        visible[0][1].activateWindow()
        event.ignore()

    def _make_mode_button(self, title: str, desc: str,
                          border_color: str, bg_color: str,
                          icon_filename: str) -> QToolButton:
        btn = QToolButton()
        btn.setFixedSize(230, 175)
        btn.setText(f"{title}\n{desc}")
        btn.setFont(QFont("Arial", 11))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        icon_path = _mode_icon_path(icon_filename)
        if os.path.exists(icon_path):
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(54, 54))
        btn.setStyleSheet(f"""
            QToolButton {{
                background: {bg_color};
                border: 2px solid {border_color};
                border-radius: 12px;
                color: {border_color};
                font-weight: bold;
                padding: 10px;
                text-align: center;
            }}
            QToolButton:hover {{
                background: {border_color};
                color: white;
            }}
            QToolButton:pressed {{
                background: {border_color};
                color: white;
                border: 3px solid {border_color};
            }}
        """)
        return btn

    def _open_programming(self):
        if self._prog_win is None or not self._prog_win.isVisible():
            dialog = SetupOpenDialog(get_all_setups(), self)
            if dialog.exec_() != dialog.Accepted:
                return
            self._prog_win = ProgrammingWindow(
                setup_id=None if dialog.create_new_setup
                else dialog.selected_setup_id
            )
        self._prog_win.showMaximized()
        self._prog_win.raise_()
        self._prog_win.activateWindow()

    def _open_inspection(self):
        if self._insp_win is None or not self._insp_win.isVisible():
            dialog = InspectionStartDialog(self)
            if dialog.exec_() != dialog.Accepted:
                return
            self._insp_win = InspectionWindow(
                startup_data=dialog.inspection_data()
            )
        self._insp_win.showMaximized()
        self._insp_win.raise_()
        self._insp_win.activateWindow()

    def _open_lot_history(self):
        if self._history_win is None or not self._history_win.isVisible():
            self._history_win = LotHistoryWindow()
        self._history_win.showMaximized()
        self._history_win.raise_()
        self._history_win.activateWindow()

    def _open_master_data(self):
        if self._master_data_win is None or not self._master_data_win.isVisible():
            self._master_data_win = MasterDataWindow()
        self._master_data_win.showMaximized()
        self._master_data_win.raise_()
        self._master_data_win.activateWindow()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    single_instance = SingleInstanceGuard("qc-inspector", app)
    if not single_instance.try_acquire():
        if single_instance.last_error:
            QMessageBox.critical(None, "QC Inspector - Errore di avvio",
                                 "Impossibile inizializzare il controllo di istanza unica.\n\n"
                                 + single_instance.last_error)
            sys.exit(1)
        sys.exit(0)

    try:
        check_runtime_access()
        initialize_database()
    except PermissionError as exc:
        QMessageBox.critical(None, "QC Inspector - Permessi insufficienti",
                             permission_error_message(exc))
        sys.exit(1)
    except Exception as exc:
        QMessageBox.critical(None, "QC Inspector - Errore di avvio",
                             "Impossibile preparare la configurazione o il database.\n\n"
                             f"{exc}\n\nVerifica i percorsi configurati, i permessi "
                             "e la compatibilità del database.")
        sys.exit(1)
    app.setStyle("Fusion")
    icon_path = _app_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Palette neutra
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(245, 245, 248))
    palette.setColor(QPalette.WindowText, QColor(30, 30, 30))
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(240, 240, 244))
    # QComboBox e QCompleter usano il ruolo Text per le voci dei popup.
    # Impostarlo esplicitamente evita testo bianco su fondo bianco con temi
    # desktop scuri, anche se l'applicazione usa campi chiari.
    palette.setColor(QPalette.Text, QColor(30, 30, 30))
    palette.setColor(QPalette.Button, QColor(235, 235, 240))
    palette.setColor(QPalette.ButtonText, QColor(30, 30, 30))
    palette.setColor(QPalette.Highlight, QColor(26, 74, 122))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    win = LauncherWindow()
    single_instance.activation_requested.connect(
        lambda: (win.show(), win.raise_(), win.activateWindow())
    )
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
