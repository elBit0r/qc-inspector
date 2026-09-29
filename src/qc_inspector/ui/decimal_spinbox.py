"""
decimal_spinbox.py
QDoubleSpinBox con separatore decimale configurabile da qc_inspector.conf.
"""

from PyQt5.QtGui import QValidator
from PyQt5.QtWidgets import QDoubleSpinBox

from ..core.app_config import format_decimal, get_decimal_separator, parse_decimal


class DecimalSpinBox(QDoubleSpinBox):
    """Spinbox numerica che mostra il separatore decimale configurato."""

    def textFromValue(self, value: float) -> str:
        return format_decimal(value, self.decimals())

    def valueFromText(self, text: str) -> float:
        cleaned = self._clean_text(text)
        if cleaned in {"", "+", "-", ".", ",", "+.", "-.", "+,", "-,"}:
            return 0.0
        return parse_decimal(cleaned)

    def validate(self, text: str, pos: int):
        cleaned = self._clean_text(text)
        if cleaned in {"", "+", "-", ".", ",", "+.", "-.", "+,", "-,"}:
            return QValidator.Intermediate, text, pos
        try:
            parse_decimal(cleaned)
        except ValueError:
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos

    def fixup(self, text: str) -> str:
        cleaned = self._clean_text(text)
        try:
            value = parse_decimal(cleaned)
        except ValueError:
            value = self.value()
        fixed = format_decimal(value, self.decimals())
        suffix = self.suffix()
        return f"{fixed}{suffix}" if suffix else fixed

    def _clean_text(self, text: str) -> str:
        cleaned = text.strip()
        suffix = self.suffix()
        if suffix and cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
        configured_sep = get_decimal_separator()
        other_sep = "," if configured_sep == "." else "."
        return cleaned.replace(other_sep, ".").replace(configured_sep, ".")
