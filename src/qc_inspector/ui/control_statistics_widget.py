"""Riepilogo statistico delle misure dimensionali del controllo corrente."""

import math
import statistics

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget

from ..core.app_config import format_decimal
from ..core.inspection_engine import get_control_limits


class ControlStatisticsWidget(QWidget):
    """Scala delle tolleranze e stime Cp/Cpk sui valori registrati."""

    def __init__(self, control, n_samples, parent=None):
        super().__init__(parent)
        self.lower, self.upper = get_control_limits(control)
        self.nominal = control.get("nominal")
        self.n_samples = n_samples
        self.values = {}
        self.mean = self.cp = self.cpk = None
        self.setMinimumWidth(340)
        self.setFixedHeight(158)
        self.setAccessibleName("Media e capacità del controllo")
        self.set_measurement(0, None)

    def set_measurement(self, sample_num, value):
        if value is not None and math.isfinite(value):
            self.values[sample_num] = float(value)
        else:
            self.values.pop(sample_num, None)
        values = list(self.values.values())
        self.mean = statistics.mean(values) if values else None
        deviation = statistics.stdev(values) if len(values) >= 2 else None
        self.cp = self.cpk = None
        reason = "Dati insufficienti: servono almeno 10 misure per Cp e Cpk."
        if not self.valid_limits:
            reason = "Limiti di tolleranza non validi."
        elif len(values) >= 10:
            if deviation > 0:
                self.cp = (self.upper - self.lower) / (6 * deviation)
                self.cpk = min(self.upper - self.mean, self.mean - self.lower) / (3 * deviation)
                reason = "Deviazione standard campionaria (n − 1)."
            else:
                reason = "Deviazione standard nulla: indici non calcolabili."
        def formatted(value):
            return format_decimal(value) if value is not None else "—"

        self.setToolTip(
            f"Min: {formatted(min(values) if values else None)}\n"
            f"Max: {formatted(max(values) if values else None)}\n"
            f"Media: {formatted(self.mean)}\n"
            f"σ: {formatted(deviation)}\n\n"
            "Stime sui campioni inseriti, inclusi FAIL e deroghe.\n"
            "σ: deviazione standard campionaria (n − 1).\n"
            "Meno di 10 misure: dati insufficienti; 10–19: preliminare; da 20: visualizzazione normale.\n"
            "L'interpretazione richiede un processo stabile e dati normalmente distribuiti.\n"
            "Cp = (USL − LSL) / (6s); Cpk = min(USL − media, media − LSL) / (3s).\n"
            + reason
        )
        self.update()

    @property
    def valid_limits(self):
        return all(value is not None and math.isfinite(value)
                   for value in (self.lower, self.upper, self.nominal)) and self.upper > self.lower

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font())
        left, right, bar_y = 42.0, self.width() - 42.0, 60.0
        ink = QColor("#435363")
        painter.setPen(ink)

        def caption(x, y, text, width=100):
            painter.drawText(QRectF(x - width / 2, y, width, 20), Qt.AlignCenter, text)

        def number(value):
            return format_decimal(value) if value is not None else "—"

        # Le tre etichette restano separate anche con tolleranze asimmetriche.
        for x, label, value in ((left, "LSL", self.lower),
                                ((left + right) / 2, "NOM", self.nominal),
                                (right, "USL", self.upper)):
            caption(x, 0, label)
            caption(x, 21, number(value))

        if self.valid_limits:
            def position(value):
                fraction = (value - self.lower) / (self.upper - self.lower)
                return left + max(0, min(1, fraction)) * (right - left)

            painter.setPen(QPen(QColor("#b8d6c3"), 6))
            painter.drawLine(QPointF(left, bar_y), QPointF(right, bar_y))
            painter.setPen(QPen(ink, 1.5))
            nominal_x = position(self.nominal)
            for x in (left, nominal_x, right):
                painter.drawLine(QPointF(x, bar_y - 7), QPointF(x, bar_y + 7))
            # Collega l'etichetta NOM alla sua posizione reale sulla scala.
            painter.setPen(QPen(QColor("#a5afb8"), 1, Qt.DotLine))
            painter.drawLine(QPointF((left + right) / 2, 42), QPointF(nominal_x, 51))
            if self.mean is not None:
                x = position(self.mean)
                outside = self.mean < self.lower or self.mean > self.upper
                color = QColor("#b71c1c" if outside else "#23649a")
                painter.setPen(color)
                painter.setBrush(color)
                painter.drawPolygon(QPolygonF([
                    QPointF(x, bar_y + 9), QPointF(x - 6, bar_y + 18),
                    QPointF(x + 6, bar_y + 18),
                ]))
                if outside:
                    caption(x + (-20 if self.mean < self.lower else 20), 61,
                            "←" if self.mean < self.lower else "→", 25)
        painter.setPen(ink)
        caption(self.width() / 2, 83, f"Media: {number(self.mean)}", self.width())
        cp = format_decimal(self.cp, 2) if self.cp is not None else "—"
        cpk = format_decimal(self.cpk, 2) if self.cpk is not None else "—"
        caption(self.width() / 2, 108,
                f"Misure: {len(self.values)}/{self.n_samples}    Cp: {cp}    Cpk: {cpk}",
                self.width())
        if len(self.values) < 20:
            painter.setPen(QColor("#8a6500"))
            status = ("Dati insufficienti" if len(self.values) < 10
                      else "Preliminare")
            caption(self.width() / 2, 132, f"Cp / Cpk: {status}", self.width())
        painter.end()
