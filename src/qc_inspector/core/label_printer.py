"""Generazione delle etichette PDF e invio alla coda CUPS."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, Spacer

from .app_config import get_label_layout, load_or_create_config
from .inspection_engine import STATUS_DEROGATION, STATUS_PASS


LABEL_FIELDS = {
    "setup": "Setup",
    "lotto": "Lotto",
    "operatore": "Operatore",
    "fornitore": "Fornitore",
    "data": "Data",
    "quantita": "Quantità lotto",
    "campioni": "Numero di campioni",
    "descrizione": "Descrizione",
    "esito": "Esito",
}

INLINE_FORMAT = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")
FIELD_PATTERN = re.compile(r"\{([a-z_]+)\}")


def _label_paragraph(text: str, values: dict) -> str:
    def replace_field(match):
        value = values.get(match[1], match[0])
        if value is None or value == "":
            return "-"
        return "<br/>".join(escape(line) for line in str(value).splitlines())

    def format_span(match):
        span = match[0]
        if span.startswith("**"):
            return f"<b>{span[2:-2]}</b>"
        return f"<i>{span[1:-1]}</i>"

    markup = INLINE_FORMAT.sub(format_span, escape(text))
    return FIELD_PATTERN.sub(replace_field, markup)


def _label_blocks(template: str, values: dict):
    body = ParagraphStyle("Etichetta", fontName="Helvetica", fontSize=11, leading=13.75)
    headings = {
        "#": ParagraphStyle("Titolo", parent=body, fontName="Helvetica-Bold",
                            fontSize=17, leading=21),
        "##": ParagraphStyle("Sottotitolo", parent=body, fontName="Helvetica-Bold",
                             fontSize=14, leading=17.5),
    }
    for line in template.splitlines():
        line = line.strip()
        if not line:
            yield Spacer(1, 6)
        elif line == "---":
            yield HRFlowable(thickness=0.6, color=colors.black, spaceBefore=0, spaceAfter=0)
        else:
            marker, _, text = line.partition(" ")
            if marker in headings and text.strip():
                yield Paragraph(_label_paragraph(text, values), headings[marker])
            else:
                yield Paragraph(_label_paragraph(line, values), body)


def render_label_pdf(setup: dict, summary: dict, cfg: dict) -> bytes:
    width_mm, height_mm, template = get_label_layout(cfg)
    width, height = width_mm * mm, height_mm * mm
    lot = summary["lot"]
    result = {
        STATUS_PASS: "PASS",
        STATUS_DEROGATION: "ACCETTATO IN DEROGA",
    }.get(summary["sampling_evaluation"]["status"], "FAIL")
    values = {
        "setup": setup.get("name"),
        "lotto": lot.get("lot_code"),
        "operatore": lot.get("operator"),
        "fornitore": lot.get("supplier"),
        "data": (lot.get("created_at") or datetime.now().isoformat())[:10],
        "quantita": lot.get("lot_quantity"),
        "campioni": lot.get("n_samples"),
        "descrizione": setup.get("description"),
        "esito": result,
    }

    margin = min(4 * mm, width / 10, height / 10)
    usable_width = width - 2 * margin
    usable_height = height - 2 * margin
    blocks = list(_label_blocks(template, values))
    content_height = sum(block.wrap(usable_width, usable_height)[1] for block in blocks)
    scale = min(1, usable_height / max(1, content_height))

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height))
    pdf.translate(margin, height - margin)
    pdf.scale(scale, scale)
    y = 0
    for block in blocks:
        _, block_height = block.wrap(usable_width / scale, usable_height / scale)
        y -= block_height
        block.drawOn(pdf, 0, y)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def generate_label_pdf(label_path: str, setup: dict, summary: dict,
                       cfg: dict | None = None) -> tuple[bool, str]:
    try:
        data = render_label_pdf(setup, summary, cfg if cfg is not None else load_or_create_config())
        with open(label_path, "wb") as output:
            output.write(data)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def available_label_printers() -> list[str]:
    try:
        result = subprocess.run(
            ["lpstat", "-e"], capture_output=True, text=True, check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(detail.strip()) from exc
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def print_label(label_path: str, cfg: dict | None = None) -> tuple[bool, str]:
    cfg = cfg if cfg is not None else load_or_create_config()
    printer = cfg.get("label_printer", "Zebra-ZPL")
    try:
        copies = max(1, min(999, int(cfg.get("labels_qta", "2"))))
    except (TypeError, ValueError):
        copies = 2

    if not printer:
        return False, "Seleziona una stampante in Configurazione → Etichetta."
    try:
        width, height, _ = get_label_layout(cfg)
        proc = subprocess.run(
            ["lp", "-d", printer, "-n", str(copies),
             "-o", f"media=Custom.{width:g}x{height:g}mm",
             "-o", "print-scaling=none", "--", label_path],
            capture_output=True, text=True, check=False, timeout=15,
        )
    except FileNotFoundError:
        return False, "Comando 'lp' non disponibile nel sistema."
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, str(exc)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err or f"Errore stampa (exit code {proc.returncode})"
    return True, ""
