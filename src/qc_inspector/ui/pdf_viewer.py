"""
pdf_viewer.py
Widget PyQt5 per visualizzare un PDF tecnico con overlay di pallinature.
Supporta: zoom, pan, aggiunta/rimozione balloon, modalità view/edit.
"""

import fitz  # PyMuPDF
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QLabel, QSizePolicy,
    QRubberBand
)
from PyQt5.QtCore import (
    Qt, QPoint, QRect, QSize, pyqtSignal, QPointF
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QBrush, QColor, QFont,
    QWheelEvent, QMouseEvent, QImage
)
from typing import List, Dict, Optional


BALLOON_RADIUS = 12
BALLOON_BORDER = 2
COLOR_DEFAULT  = QColor(30, 120, 200)
COLOR_PASS     = QColor(34, 139, 34)
COLOR_FAIL     = QColor(200, 40, 40)
COLOR_DEROGATION = QColor(230, 145, 25)
COLOR_SELECTED = QColor(255, 165, 0)


class PdfViewerWidget(QWidget):
    """
    Widget principale che mostra il PDF e permette di posizionare balloon.

    Segnali emessi:
      balloon_added(x_rel, y_rel, page)                — coordinate relative [0,1]
      balloon_clicked(balloon_id)                      — id del balloon nel DB
      balloon_deleted(balloon_id)
      balloon_moved(balloon_id, x_rel, y_rel, page)    — nuova posizione
    """

    balloon_added   = pyqtSignal(float, float, int)
    balloon_clicked = pyqtSignal(int)
    balloon_deleted = pyqtSignal(int)
    balloon_moved   = pyqtSignal(int, float, float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc: Optional[fitz.Document] = None
        self._page_index = 0
        self._zoom = 1.0
        self._zoom_min = 0.25
        self._zoom_max = 4.0
        self._pan_origin = QPoint()
        self._panning = False
        self._offset = QPoint(0, 0)

        self._pixmap: Optional[QPixmap] = None
        self._base_w = 0
        self._base_h = 0

        # Lista balloon: dict con id, balloon_num, x_rel, y_rel, page,
        #                control_type, pass_fail (None/True/False o stato testuale)
        self._balloons: List[Dict] = []
        self._selected_balloon_id: Optional[int] = None
        self._drag_balloon_id: Optional[int] = None
        self._drag_start_pos = QPoint()
        self._balloon_dragging = False

        self._edit_mode = False   # True = programmazione, False = solo visualizzazione
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 300)

    # ─── Proprietà pubbliche ──────────────────────────────────────────────────

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool):
        self._edit_mode = value
        if value:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    @property
    def current_page(self) -> int:
        return self._page_index

    @property
    def total_pages(self) -> int:
        return len(self._doc) if self._doc else 0

    # ─── Caricamento PDF ─────────────────────────────────────────────────────

    @staticmethod
    def validate_pdf(path: str) -> bool:
        """Verifica apertura e presenza di almeno una pagina senza cambiare viewer."""
        document = None
        try:
            document = fitz.open(path)
            return len(document) > 0
        except Exception:
            return False
        finally:
            if document is not None:
                document.close()

    def load_pdf(self, path: str, page: int = 0) -> bool:
        candidate = None
        old_state = (
            self._doc, self._page_index, self._zoom, self._offset,
            self._pixmap, self._base_w, self._base_h,
        )
        try:
            candidate = fitz.open(path)
            if len(candidate) == 0:
                raise ValueError("Il PDF non contiene pagine")
            self._doc = candidate
            self._page_index = max(0, min(page, len(self._doc) - 1))
            self._zoom = 1.0
            self._offset = QPoint(0, 0)
            self._render_page()
            old_doc = old_state[0]
            if old_doc is not None and old_doc is not candidate:
                old_doc.close()
            self.update()
            return True
        except Exception as e:
            if candidate is not None:
                candidate.close()
            (self._doc, self._page_index, self._zoom, self._offset,
             self._pixmap, self._base_w, self._base_h) = old_state
            print(f"Errore caricamento PDF: {e}")
            return False

    def clear_pdf(self):
        """Rimuove documento, rendering e balloon dal viewer."""
        if self._doc is not None:
            self._doc.close()
        self._doc = None
        self._page_index = 0
        self._zoom = 1.0
        self._offset = QPoint(0, 0)
        self._pixmap = None
        self._base_w = 0
        self._base_h = 0
        self._balloons = []
        self._selected_balloon_id = None
        self._drag_balloon_id = None
        self._balloon_dragging = False
        self.update()

    def set_page(self, page: int):
        if self._doc and 0 <= page < len(self._doc):
            self._page_index = page
            self._render_page()
            self.update()

    def _render_page(self):
        if not self._doc:
            return
        page = self._doc[self._page_index]
        dpi = 150
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height,
                     pix.stride, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(img)
        self._base_w = self._pixmap.width()
        self._base_h = self._pixmap.height()

    # ─── Gestione balloon ────────────────────────────────────────────────────

    def load_balloons(self, balloons: List[Dict]):
        """
        Carica lista balloon dal DB.
        Ogni elemento: {id, balloon_num, balloon_x, balloon_y, pdf_page,
                        control_type, pass_fail=None/True/False/stato testuale}
        """
        self._balloons = [dict(b) for b in balloons]
        self._drag_balloon_id = None
        self._balloon_dragging = False
        self.update()

    def update_balloon_result(self, control_id: int, pass_fail):
        """Aggiorna lo stato PASS/FAIL/DEROGA di un balloon."""
        for b in self._balloons:
            if b["id"] == control_id:
                b["pass_fail"] = pass_fail
                break
        self.update()

    def reset_results(self):
        """Rimuove tutti i risultati (per nuova sessione di collaudo)."""
        for b in self._balloons:
            b["pass_fail"] = None
        self.update()

    def select_balloon(self, balloon_id: Optional[int]):
        self._selected_balloon_id = balloon_id
        self.update()

    # ─── Coordinate helpers ──────────────────────────────────────────────────

    def _widget_to_rel(self, wx: int, wy: int):
        """Converte coordinate widget → coordinate relative alla pagina [0,1]."""
        if not self._pixmap:
            return 0.0, 0.0
        scaled_w = int(self._base_w * self._zoom)
        scaled_h = int(self._base_h * self._zoom)
        ox = (self.width()  - scaled_w) // 2 + self._offset.x()
        oy = (self.height() - scaled_h) // 2 + self._offset.y()
        rx = (wx - ox) / scaled_w
        ry = (wy - oy) / scaled_h
        return rx, ry

    def _rel_to_widget(self, rx: float, ry: float):
        """Converte coordinate relative [0,1] → coordinate widget."""
        if not self._pixmap:
            return 0, 0
        scaled_w = int(self._base_w * self._zoom)
        scaled_h = int(self._base_h * self._zoom)
        ox = (self.width()  - scaled_w) // 2 + self._offset.x()
        oy = (self.height() - scaled_h) // 2 + self._offset.y()
        wx = int(rx * scaled_w) + ox
        wy = int(ry * scaled_h) + oy
        return wx, wy

    def _find_balloon_at(self, wx: int, wy: int) -> Optional[Dict]:
        """Trova il balloon sotto il cursore (considera solo pagina corrente)."""
        for b in reversed(self._balloons):
            if b.get("pdf_page", 0) != self._page_index:
                continue
            bx, by = self._rel_to_widget(b["balloon_x"], b["balloon_y"])
            dist = ((wx - bx) ** 2 + (wy - by) ** 2) ** 0.5
            if dist <= BALLOON_RADIUS + 4:
                return b
        return None

    # ─── Events ──────────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = max(self._zoom_min, min(self._zoom_max, self._zoom * factor))
        self._zoom = new_zoom
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._drag_balloon_id = None
            self._balloon_dragging = False
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.RightButton:
            b = self._find_balloon_at(event.x(), event.y())
            if b and self._edit_mode:
                self.balloon_deleted.emit(b["id"])
            return

        if event.button() == Qt.LeftButton:
            b = self._find_balloon_at(event.x(), event.y())
            if b:
                self._selected_balloon_id = b["id"]
                self.balloon_clicked.emit(b["id"])
                if (self._edit_mode
                        and self._selected_balloon_id == b["id"]):
                    self._drag_balloon_id = b["id"]
                    self._drag_start_pos = event.pos()
                    self._balloon_dragging = False
                self.update()
                return

            if self._edit_mode:
                rx, ry = self._widget_to_rel(event.x(), event.y())
                if 0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0:
                    self.balloon_added.emit(rx, ry, self._page_index)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            self._offset += delta
            self.update()
        elif self._edit_mode and self._drag_balloon_id is not None:
            if not self._balloon_dragging:
                distance = (event.pos() - self._drag_start_pos).manhattanLength()
                self._balloon_dragging = distance >= 4
            if self._balloon_dragging:
                rx, ry = self._widget_to_rel(event.x(), event.y())
                rx = max(0.0, min(1.0, rx))
                ry = max(0.0, min(1.0, ry))
                for balloon in self._balloons:
                    if balloon["id"] == self._drag_balloon_id:
                        balloon["balloon_x"] = rx
                        balloon["balloon_y"] = ry
                        break
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
        else:
            b = self._find_balloon_at(event.x(), event.y())
            if b:
                self.setCursor(
                    Qt.OpenHandCursor if self._edit_mode
                    else Qt.PointingHandCursor
                )
            elif self._edit_mode:
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CrossCursor if self._edit_mode else Qt.ArrowCursor)
            return

        if event.button() == Qt.LeftButton and self._drag_balloon_id is not None:
            moved_balloon = next(
                (balloon for balloon in self._balloons
                 if balloon["id"] == self._drag_balloon_id),
                None,
            )
            if self._balloon_dragging and moved_balloon is not None:
                self.balloon_moved.emit(
                    moved_balloon["id"],
                    moved_balloon["balloon_x"],
                    moved_balloon["balloon_y"],
                    self._page_index,
                )
            self._drag_balloon_id = None
            self._balloon_dragging = False
            hover_balloon = self._find_balloon_at(event.x(), event.y())
            self.setCursor(
                Qt.OpenHandCursor if hover_balloon else Qt.CrossCursor
            )

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Doppio click → reset zoom e pan."""
        if event.button() == Qt.LeftButton and not self._find_balloon_at(event.x(), event.y()):
            self._zoom = 1.0
            self._offset = QPoint(0, 0)
            self.update()

    # ─── Paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Sfondo
        painter.fillRect(self.rect(), QColor(60, 60, 65))

        if not self._pixmap:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Nessun PDF caricato\nClicca 'Carica PDF' per iniziare")
            return

        # PDF
        scaled_w = int(self._base_w * self._zoom)
        scaled_h = int(self._base_h * self._zoom)
        ox = (self.width()  - scaled_w) // 2 + self._offset.x()
        oy = (self.height() - scaled_h) // 2 + self._offset.y()

        scaled = self._pixmap.scaled(scaled_w, scaled_h,
                                     Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
        painter.drawPixmap(ox, oy, scaled)

        # Bordo pagina
        painter.setPen(QPen(QColor(100, 100, 110), 1))
        painter.drawRect(ox, oy, scaled_w, scaled_h)

        # Balloon
        for b in self._balloons:
            if b.get("pdf_page", 0) != self._page_index:
                continue
            bx, by = self._rel_to_widget(b["balloon_x"], b["balloon_y"])
            self._draw_balloon(painter, bx, by, b)

        # Info zoom
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Monospace", 9))
        painter.drawText(8, self.height() - 8,
                         f"Zoom {self._zoom * 100:.0f}%  |  "
                         f"Pag. {self._page_index + 1}/{self.total_pages}  |  "
                         f"{'[EDIT]' if self._edit_mode else '[VIEW]'}")

    def _draw_balloon(self, painter: QPainter, cx: int, cy: int, b: Dict):
        r = BALLOON_RADIUS
        is_selected = (b["id"] == self._selected_balloon_id)
        pf = b.get("pass_fail")

        if is_selected:
            fill = COLOR_SELECTED
        elif pf is True or pf == "PASS":
            fill = COLOR_PASS
        elif pf == "ACCETTATO IN DEROGA":
            fill = COLOR_DEROGATION
        elif pf is False or pf == "FAIL":
            fill = COLOR_FAIL
        else:
            fill = COLOR_DEFAULT

        # Ombra leggera
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
        painter.drawEllipse(cx - r + 2, cy - r + 2, r * 2, r * 2)

        # Cerchio principale
        pen = QPen(Qt.white if not is_selected else QColor(255, 200, 0),
                   BALLOON_BORDER + (1 if is_selected else 0))
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Numero
        painter.setPen(Qt.white)
        font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(font)
        text = str(b["balloon_num"])
        painter.drawText(
            cx - r, cy - r, r * 2, r * 2,
            Qt.AlignCenter, text
        )

        # Tipo controllo (piccolo indicatore)
        ctrl_type = b.get("control_type", "dimensional")
        indicator_color = QColor(255, 255, 150) if ctrl_type == "yesno" else QColor(150, 220, 255)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(indicator_color))
        painter.drawEllipse(cx + r - 6, cy - r, 6, 6)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()
