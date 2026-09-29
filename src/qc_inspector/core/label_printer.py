"""
label_printer.py
Generazione etichetta PDF e stampa su stampante configurata.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Dict, Tuple

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ..core.inspection_engine import (
    STATUS_PASS, STATUS_DEROGATION,
)
from ..core.app_config import load_or_create_config


def generate_label_pdf(label_path: str, setup: Dict, summary: Dict) -> Tuple[bool, str]:
    try:
        page_size = (105 * mm, 60 * mm)
        c = canvas.Canvas(label_path, pagesize=page_size)
        w, h = page_size

        lot = summary["lot"]
        lot_status = summary["sampling_evaluation"]["status"]
        result_text = "PASS" if lot_status == STATUS_PASS else "FAIL"
        if lot_status == STATUS_DEROGATION:
            result_text = "ACCETTATO\nIN DEROGA"

        y = h - 6 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(4 * mm, y, f"QC Inspector  -  {setup.get('name', '-')}")
        y -= 5 * mm

        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.line(4 * mm, y, w - 4 * mm, y)
        y -= 3 * mm

        # Blocco tabellare principale in stile template HTML
        box_x = 4 * mm
        box_y = 17 * mm
        box_w = w - 8 * mm
        box_h = 26 * mm
        c.setLineWidth(1.2)
        c.rect(box_x, box_y, box_w, box_h)

        # Griglia 2 colonne solo per i dati principali (parte alta del box)
        split_x = box_x + (box_w * 0.58)
        info_top = box_y + box_h
        info_bottom = box_y + 7.5 * mm
        c.line(split_x, info_bottom, split_x, info_top)
        c.line(box_x, info_bottom, box_x + box_w, info_bottom)

        c.setFont("Helvetica", 8)
        left_y = box_y + box_h - 4.5 * mm
        c.drawString(box_x + 2 * mm, left_y, f"Lotto: {lot.get('lot_code', '-')}")
        left_y -= 4.3 * mm
        c.drawString(box_x + 2 * mm, left_y, f"Operatore: {lot.get('operator') or '-'}")
        left_y -= 4.3 * mm
        c.drawString(box_x + 2 * mm, left_y, f"Data: {(lot.get('created_at') or datetime.now().isoformat())[:10]}")
        left_y -= 4.3 * mm
        c.drawString(box_x + 2 * mm, left_y, f"Campioni: {lot.get('n_samples', '-')}")

        desc = (setup.get("description") or "-").strip()
        if len(desc) > 56:
            desc = desc[:53] + "..."
        c.setFont("Helvetica", 8)
        c.drawString(box_x + 2 * mm, box_y + 3 * mm, f"Descrizione: {desc}")

        # Box RESULT stile "cartellino"
        res_w = 30 * mm
        res_h = 12 * mm
        res_x = w - res_w - 4 * mm
        res_y = 3 * mm
        c.setStrokeColor(colors.black)
        c.setFillColor(colors.white)
        c.setLineWidth(1.2)
        c.rect(res_x, res_y, res_w, res_h, fill=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(res_x + res_w / 2, res_y + res_h - 3.8 * mm, "RESULT")
        if "\n" in result_text:
            first_line, second_line = result_text.split("\n", 1)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(res_x + res_w / 2, res_y + 4.4 * mm, first_line)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(res_x + res_w / 2, res_y + 1.3 * mm, second_line)
        else:
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(res_x + res_w / 2, res_y + 2.6 * mm, result_text)
        c.setFillColor(colors.black)

        c.showPage()
        c.save()
        return True, ""
    except Exception as e:
        return False, str(e)


def print_label(label_path: str) -> Tuple[bool, str]:
    cfg = load_or_create_config()
    printer = cfg.get("label_printer", "Zebra-ZPL")
    qta_raw = cfg.get("labels_qta", "2")
    try:
        qta = max(1, int(qta_raw))
    except ValueError:
        qta = 2

    try:
        proc = subprocess.run(
            ["lp", "-d", printer, "-n", str(qta), label_path],
            capture_output=True,
            text=True,
            check=False
        )
    except FileNotFoundError:
        return False, "Comando 'lp' non disponibile nel sistema."
    except Exception as e:
        return False, str(e)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err or f"Errore stampa (exit code {proc.returncode})"
    return True, ""
