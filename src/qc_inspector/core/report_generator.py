"""
report_generator.py
Genera il report PDF di collaudo usando reportlab.
"""

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
from typing import List, Dict, Optional
from html import escape
import os
import tempfile
import fitz  # PyMuPDF

from ..core.inspection_engine import (
    format_tolerance, get_control_status, get_control_sample_count,
    get_measurement_status, get_control_limits,
    STATUS_PASS, STATUS_FAIL, STATUS_DEROGATION,
)
from ..core.app_config import format_decimal, load_or_create_config


# ─── Colori ──────────────────────────────────────────────────────────────────
C_PASS      = colors.HexColor("#d4edda")
C_FAIL      = colors.HexColor("#f8d7da")
C_DEROGATION= colors.HexColor("#fff3cd")
C_HEADER    = colors.HexColor("#1a4a7a")
C_SUBHEADER = colors.HexColor("#2d6fad")
C_GRAY_LIGHT= colors.HexColor("#f5f5f5")
C_GRAY      = colors.HexColor("#cccccc")
C_WHITE     = colors.white
C_BLACK     = colors.black
C_GREEN     = colors.HexColor("#155724")
C_RED       = colors.HexColor("#721c24")
C_AMBER     = colors.HexColor("#7a4b00")


def generate_global_supplier_report(output_path: str, statistics: Dict):
    """Genera il report globale di valutazione fornitori per intervallo date."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=8*mm, rightMargin=8*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title="Report globale valutazione fornitori",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "GlobalTitle", parent=styles["Title"], fontSize=17,
        textColor=C_HEADER, alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "GlobalSection", parent=styles["Heading2"], fontSize=12,
        textColor=C_HEADER, spaceBefore=5*mm, spaceAfter=2*mm,
    )
    small_style = ParagraphStyle(
        "GlobalSmall", parent=styles["BodyText"], fontSize=7, leading=9,
    )
    story = [
        Paragraph("REPORT GLOBALE — VALUTAZIONE FORNITORI", title_style),
        Paragraph(
            f"Periodo: {escape(statistics['start_date'])} — "
            f"{escape(statistics['end_date'])} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles["BodyText"],
        ),
        Spacer(1, 4*mm),
    ]

    totals = statistics["totals"]
    summary_data = [[
        "Fornitori", "Lotti", "Pezzi controllati", "PASS",
        "Accettati in deroga", "FAIL", "% PASS", "% Deroga", "% FAIL",
    ], [
        str(totals["suppliers"]), str(totals["lots"]), str(totals["pieces"]),
        str(totals["passed"]), str(totals["derogated"]), str(totals["failed"]),
        _format_percentage(totals["pass_rate"]),
        _format_percentage(totals["derogation_rate"]),
        _format_percentage(totals["fail_rate"]),
    ]]
    summary = Table(
        summary_data,
        colWidths=[24*mm, 20*mm, 34*mm, 22*mm, 40*mm, 22*mm,
                   28*mm, 28*mm, 28*mm],
    )
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("BACKGROUND", (0, 1), (-1, 1), C_GRAY_LIGHT),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.7, C_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, C_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary)
    story.append(Paragraph("Classifica fornitori", section_style))

    ranking_rows = [[
        "Pos.", "Fornitore", "Lotti", "Pezzi", "PASS", "Deroga", "FAIL",
        "% PASS", "% Deroga", "% FAIL", "Nota",
    ]]
    rank = 0
    for supplier in statistics["suppliers"]:
        if not supplier["unspecified"]:
            rank += 1
            position = str(rank)
        else:
            position = "—"
        ranking_rows.append([
            position,
            Paragraph(escape(supplier["supplier"]), small_style),
            str(supplier["lots"]), str(supplier["pieces"]),
            str(supplier["passed"]), str(supplier["derogated"]),
            str(supplier["failed"]), _format_percentage(supplier["pass_rate"]),
            _format_percentage(supplier["derogation_rate"]),
            _format_percentage(supplier["fail_rate"]),
            "Campione limitato" if supplier["limited_sample"] else "",
        ])

    ranking = Table(
        ranking_rows,
        colWidths=[12*mm, 56*mm, 16*mm, 18*mm, 18*mm, 20*mm, 18*mm,
                   23*mm, 25*mm, 23*mm, 36*mm],
        repeatRows=1,
    )
    ranking_style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_SUBHEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_GRAY_LIGHT]),
        ("BOX", (0, 0), (-1, -1), 0.7, C_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, C_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index, supplier in enumerate(statistics["suppliers"], start=1):
        if supplier["failed"]:
            ranking_style.append(("BACKGROUND", (9, row_index), (9, row_index), C_FAIL))
            ranking_style.append(("TEXTCOLOR", (9, row_index), (9, row_index), C_RED))
        if supplier["derogated"]:
            ranking_style.append(("BACKGROUND", (8, row_index), (8, row_index), C_DEROGATION))
            ranking_style.append(("TEXTCOLOR", (8, row_index), (8, row_index), C_AMBER))
    ranking.setStyle(TableStyle(ranking_style))
    story.append(ranking)

    if statistics.get("excluded_incomplete"):
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(
            f"Lotti chiusi esclusi perché privi di campioni completi: "
            f"{statistics['excluded_incomplete']}.", small_style,
        ))
    story.append(Paragraph(
        "Regola di classificazione del pezzo: FAIL se contiene almeno un FAIL "
        "aperto; in assenza di FAIL aperti, DEROGA se contiene almeno una misura "
        "accettata in deroga; altrimenti PASS. “Campione limitato” indica meno "
        "di 30 pezzi controllati.", small_style,
    ))

    for supplier in statistics["suppliers"]:
        story.append(PageBreak())
        story.append(Paragraph(
            f"Dettaglio — {escape(supplier['supplier'])}", title_style,
        ))
        detail_rows = [[
            "Data", "Setup", "Lotto", "Pezzi", "PASS", "Deroga", "FAIL", "Esito",
        ]]
        for detail in supplier["details"]:
            detail_rows.append([
                detail["date"], Paragraph(escape(detail["setup"]), small_style),
                Paragraph(escape(detail["lot_code"]), small_style),
                str(detail["pieces"]), str(detail["passed"]),
                str(detail["derogated"]), str(detail["failed"]), detail["result"],
            ])
        detail_table = Table(
            detail_rows,
            colWidths=[26*mm, 75*mm, 52*mm, 24*mm, 24*mm, 28*mm, 24*mm, 28*mm],
            repeatRows=1,
        )
        detail_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_SUBHEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_GRAY_LIGHT]),
            ("BOX", (0, 0), (-1, -1), 0.7, C_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, C_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(detail_table)

    doc.build(story)


def _format_percentage(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") + "%"


def generate_report(output_path: str, setup: Dict,
                    controls: List[Dict], summary: Dict):
    """
    Genera il report PDF di collaudo.

    Args:
        output_path: percorso file di output
        setup: dizionario setup dal DB
        controls: lista controlli del setup
        summary: dizionario da db.get_lot_summary()
    """
    # 1) Genera il report tabellare in un file temporaneo
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_report_path = tmp.name

    doc = SimpleDocTemplate(
        tmp_report_path,
        pagesize=landscape(A4),
        leftMargin=5*mm, rightMargin=5*mm,
        topMargin=5*mm, bottomMargin=12*mm,
        title=f"Report collaudo — Lotto {summary['lot']['lot_code']}"
    )

    styles = getSampleStyleSheet()
    story = []

    # ─── Intestazione ────────────────────────────────────────────────────────
    story += _build_header(setup, summary, styles)
    story.append(Spacer(1, 4*mm))
    story += _build_sampling_result(summary)
    story.append(Spacer(1, 6*mm))

    # ─── Tabella principale ──────────────────────────────────────────────────
    story += _build_main_table(controls, summary)
    story.append(Spacer(1, 6*mm))

    # ─── Esito finale ────────────────────────────────────────────────────────
    story += _build_final_result(summary)
    story.append(Spacer(1, 4*mm))

    # ─── Dettaglio deroghe ──────────────────────────────────────────────────
    story += _build_derogations(controls, summary, styles)
    if summary.get("derogated", 0):
        story.append(Spacer(1, 4*mm))

    # ─── Footer info ─────────────────────────────────────────────────────────
    story += _build_footer(summary, styles)

    doc.build(story)

    # 2) Costruisce PDF finale: setup (con balloon) + report tabellare
    try:
        _build_combined_pdf(output_path, setup, controls, summary, tmp_report_path)
    finally:
        if os.path.exists(tmp_report_path):
            os.remove(tmp_report_path)


def _build_combined_pdf(output_path: str, setup: Dict,
                        controls: List[Dict], summary: Dict,
                        report_pdf_path: str):
    setup_pdf_path = setup.get("pdf_path")
    if not setup_pdf_path or not os.path.exists(setup_pdf_path):
        # Fallback: se il PDF setup non è disponibile salva solo il report tabellare.
        report_doc = fitz.open(report_pdf_path)
        _add_page_numbers(report_doc)
        report_doc.save(output_path)
        report_doc.close()
        return

    setup_doc = fitz.open(setup_pdf_path)
    report_doc = fitz.open(report_pdf_path)
    final_doc = fitz.open()
    try:
        control_results = _build_control_result_map(controls, summary)
        _draw_balloons_on_setup_doc(setup_doc, controls, control_results)

        # Ordine richiesto: prima report tabellare, poi setup con balloon
        final_doc.insert_pdf(report_doc)
        final_doc.insert_pdf(setup_doc)
        _add_page_numbers(final_doc)
        final_doc.save(output_path)
    finally:
        report_doc.close()
        setup_doc.close()
        final_doc.close()


def _add_page_numbers(document: fitz.Document):
    """Aggiunge testo configurabile a sinistra e numerazione a destra."""
    total = len(document)
    footer_text = load_or_create_config().get("report_footer_text", "").strip()
    for number, page in enumerate(document, start=1):
        text = f"Pagina {number} di {total}"
        fontsize = 8
        width = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        # Posizione nella vista ruotata, convertita nelle coordinate native.
        point = fitz.Point(page.rect.width - 5*mm - width,
                           page.rect.height - 4*mm) * page.derotation_matrix
        page.insert_text(
            point, text, fontsize=fontsize, fontname="helv",
            color=(0.35, 0.35, 0.35), rotate=page.rotation,
        )
        if footer_text:
            # Riserva spazio alla numerazione anche con nomi azienda lunghi.
            available = page.rect.width - 15*mm - width
            text_width = fitz.get_text_length(footer_text, fontname="helv", fontsize=fontsize)
            footer_size = min(fontsize, fontsize * available / max(text_width, 1))
            if footer_size > 0:
                footer_point = fitz.Point(5*mm, page.rect.height - 4*mm) * page.derotation_matrix
                page.insert_text(
                    footer_point, footer_text, fontsize=footer_size, fontname="helv",
                    color=(0.35, 0.35, 0.35), rotate=page.rotation,
                )


def _build_control_result_map(controls: List[Dict], summary: Dict) -> Dict[int, Optional[str]]:
    measurements = summary.get("measurements", [])
    measurements_by_control: Dict[int, List[Dict]] = {}
    for measurement in measurements:
        measurements_by_control.setdefault(measurement["control_id"], []).append(measurement)

    results: Dict[int, Optional[str]] = {}
    for ctrl in controls:
        ctrl_measurements = measurements_by_control.get(ctrl["id"], [])
        if not ctrl_measurements:
            results[ctrl["id"]] = None
        else:
            results[ctrl["id"]] = get_control_status(ctrl_measurements)
    return results


def _balloon_colors(pass_fail: Optional[str]):
    if pass_fail == STATUS_PASS:
        return (
            (0.08, 0.34, 0.14),  # stroke: #155724
            (0.83, 0.93, 0.85),  # fill:   #d4edda
            (0.08, 0.34, 0.14),  # text:   #155724
        )
    if pass_fail == STATUS_DEROGATION:
        return (
            (0.48, 0.29, 0.00),  # stroke: #7a4b00
            (1.00, 0.95, 0.80),  # fill:   #fff3cd
            (0.48, 0.29, 0.00),  # text:   #7a4b00
        )
    if pass_fail == STATUS_FAIL:
        return (
            (0.45, 0.11, 0.14),  # stroke: #721c24
            (0.97, 0.84, 0.85),  # fill:   #f8d7da
            (0.45, 0.11, 0.14),  # text:   #721c24
        )
    return (
        (0.12, 0.47, 0.78),
        (0.90, 0.96, 1.0),
        (0.02, 0.20, 0.38),
    )


def _draw_balloons_on_setup_doc(setup_doc: fitz.Document, controls: List[Dict],
                                control_results: Dict[int, Optional[str]]):
    total_pages = len(setup_doc)
    for ctrl in controls:
        raw_page_idx = ctrl.get("pdf_page", 0)
        try:
            page_idx = int(raw_page_idx)
        except (TypeError, ValueError):
            page_idx = 0

        # Evita perdita balloon per indici invalidi: clamp sulla prima/ultima pagina.
        page_idx = max(0, min(page_idx, total_pages - 1))
        page = setup_doc[page_idx]
        rect = page.rect

        # Clamp coordinate per mantenere il balloon visibile anche con dati legacy sporchi.
        x_rel = float(ctrl.get("balloon_x", 0.0))
        y_rel = float(ctrl.get("balloon_y", 0.0))
        x_rel = max(0.0, min(1.0, x_rel))
        y_rel = max(0.0, min(1.0, y_rel))
        x = rect.x0 + (x_rel * rect.width)
        y = rect.y0 + (y_rel * rect.height)

        # Le coordinate salvate provengono dalla vista renderizzata (ruotata).
        # Riportiamo il punto nello spazio pagina nativo per evitare shift su PDF ruotati.
        # Coordinate sempre normalizzate nello spazio pagina nativo:
        # con rotazione=0 la matrice è identità, con 90/180/270 corregge l'orientamento.
        p = fitz.Point(x, y) * page.derotation_matrix

        r = max(9.0, min(rect.width, rect.height) * 0.014)
        circle_rect = fitz.Rect(p.x - r, p.y - r, p.x + r, p.y + r)
        stroke_color, fill_color, text_color = _balloon_colors(
            control_results.get(ctrl["id"])
        )

        page.draw_circle((p.x, p.y), r, color=stroke_color, fill=fill_color, width=1.3)

        num = str(ctrl.get("balloon_num", ""))
        fs = max(7, min(11, int(r * 0.95)))
        page.insert_textbox(
            circle_rect,
            num,
            fontsize=fs,
            fontname="helv",
            color=text_color,
            align=1
        )


def _build_header(setup: Dict, summary: Dict, styles) -> list:
    lot = summary["lot"]
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf_name = os.path.basename(setup["pdf_path"])
    pdf_stem, pdf_ext = os.path.splitext(pdf_name)
    if len(pdf_stem) > 12:
        pdf_name = f"{pdf_stem[:12]}...{pdf_ext}"

    title_style = ParagraphStyle(
        "Title", fontSize=16, fontName="Helvetica-Bold",
        textColor=C_HEADER, alignment=TA_LEFT
    )
    sub_style = ParagraphStyle(
        "Sub", fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#444444"), alignment=TA_LEFT
    )

    items = []
    items.append(Paragraph("RAPPORTO DI CONTROLLO QUALITÀ", title_style))
    items.append(Spacer(1, 3*mm))

    # Tabella info
    data = [
        ["Setup:", setup["name"], "Lotto:", lot["lot_code"]],
        ["Revisione:", str(setup.get("version_number") or "—"),
         "ID revisione:", str(setup.get("revision_uid") or "—")],
        ["Descrizione:", setup.get("description") or "—",
         "Data:", lot["created_at"][:10]],
        ["Operatore:", lot.get("operator") or "—",
         "Fornitore:", lot.get("supplier") or "—"],
        ["Piano:", (lot.get("sampling_profile") or "—").title(),
         "Campioni max:", str(lot["n_samples"])],
        ["Q.tà lotto:", str(lot.get("lot_quantity") or "—"),
         "Generato il:", now],
        ["PDF:", pdf_name,
         "", ""],
    ]

    col_widths = [28*mm, 80*mm, 28*mm, 80*mm]
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",  (0, 0), (0, -1), C_HEADER),
        ("TEXTCOLOR",  (2, 0), (2, -1), C_HEADER),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_GRAY_LIGHT, C_WHITE]),
        ("BOX",        (0, 0), (-1, -1), 0.5, C_GRAY),
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, C_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    items.append(tbl)
    return items


def _build_sampling_result(summary: Dict) -> list:
    evaluation = summary["sampling_evaluation"]
    rows = [["Criticità", "n", "Ac", "Re", "Difettosi", "Decisione"]]
    for criticality in ("C", "I", "N"):
        result = evaluation["by_criticality"][criticality]
        if not result["controls"]:
            continue
        if result["rejected"]:
            decision = (
                "FAIL" if result["open_defective"] else "DEROGA"
            )
        elif result["derogated_defective"]:
            decision = "DEROGA"
        else:
            decision = "PASS"
        rows.append([
            criticality, str(result["n"]), str(result["ac"]),
            str(result["re"]), str(result["defective"]), decision,
        ])

    table = Table(
        rows,
        colWidths=[28*mm, 20*mm, 20*mm, 20*mm, 30*mm, 32*mm],
        repeatRows=1,
    )
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), C_SUBHEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, C_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, C_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_GRAY_LIGHT]),
    ]
    for row_index, row in enumerate(rows[1:], start=1):
        decision = row[-1]
        if decision == "FAIL":
            background, foreground = C_FAIL, C_RED
        elif decision == "DEROGA":
            background, foreground = C_DEROGATION, C_AMBER
        else:
            background, foreground = C_PASS, C_GREEN
        styles.extend([
            ("BACKGROUND", (-1, row_index), (-1, row_index), background),
            ("TEXTCOLOR", (-1, row_index), (-1, row_index), foreground),
            ("FONTNAME", (-1, row_index), (-1, row_index), "Helvetica-Bold"),
        ])
    table.setStyle(TableStyle(styles))
    return [table]


def _build_main_table(controls: List[Dict], summary: Dict) -> list:
    lot = summary["lot"]
    n_samples = lot["n_samples"]
    measurements = summary["measurements"]

    # Crea mappa: {(control_id, sample_num): measurement}
    meas_map = {}
    for m in measurements:
        meas_map[(m["control_id"], m["sample_num"])] = m

    header_style = ParagraphStyle(
        "TH", fontSize=8, fontName="Helvetica-Bold",
        textColor=C_WHITE, alignment=TA_CENTER
    )
    description_style = ParagraphStyle(
        "ControlDescription", fontSize=7, fontName="Helvetica",
        textColor=C_BLACK, alignment=TA_LEFT, leading=8,
    )

    story_tables = []
    chunk_size = 10

    for chunk_start in range(1, n_samples + 1, chunk_size):
        chunk_end = min(n_samples, chunk_start + chunk_size - 1)
        chunk_samples = list(range(chunk_start, chunk_end + 1))

        header_row = [
            Paragraph("N°", header_style),
            Paragraph("Crit.", header_style),
            Paragraph("Descrizione", header_style),
            Paragraph("Tipo", header_style),
            Paragraph("Nominale / Tolleranza", header_style),
            Paragraph("Min", header_style),
            Paragraph("Max", header_style),
        ]
        for s in chunk_samples:
            header_row.append(Paragraph(f"C{s}", header_style))
        header_row.append(Paragraph("Esito ctrl", header_style))

        rows = [header_row]
        row_styles = []

        for row_idx, ctrl in enumerate(controls, start=1):
            required_samples = get_control_sample_count(lot, ctrl)
            sample_cells = []

            for s in chunk_samples:
                if s > required_samples:
                    sample_cells.append("N/A")
                    continue
                m = meas_map.get((ctrl["id"], s))
                if m is None:
                    sample_cells.append("—")
                else:
                    if ctrl["control_type"] == "dimensional":
                        val = format_decimal(m["value_num"]) if m["value_num"] is not None else "—"
                    else:
                        val = "Sì" if m["value_bool"] else "No"
                    if get_measurement_status(m) == STATUS_DEROGATION:
                        val += " *"
                    sample_cells.append(val)

            # Esito controllo calcolato sull'intero lotto, non solo sul chunk
            ctrl_measurements = [
                meas_map[(ctrl["id"], s)]
                for s in range(1, required_samples + 1)
                if (ctrl["id"], s) in meas_map
            ]
            ctrl_status = get_control_status(ctrl_measurements) or STATUS_FAIL

            lower, upper = get_control_limits(ctrl)
            nom_str = (format_tolerance(ctrl["nominal"], ctrl["tol_plus"], ctrl["tol_minus"])
                       if ctrl["control_type"] == "dimensional" else "Sì/No")
            min_str = format_decimal(lower) if lower is not None else "—"
            max_str = format_decimal(upper) if upper is not None else "—"

            row = [
                str(ctrl["balloon_num"]),
                ctrl.get("criticality", "N"),
                Paragraph(
                    escape(ctrl.get("label") or ""), description_style
                ),
                "DIM" if ctrl["control_type"] == "dimensional" else "S/N",
                nom_str,
                min_str,
                max_str,
            ] + sample_cells + [
                "DEROGA" if ctrl_status == STATUS_DEROGATION else ctrl_status
            ]

            rows.append(row)

            r = row_idx
            bg = C_GRAY_LIGHT if row_idx % 2 == 0 else C_WHITE
            row_styles.append(("BACKGROUND", (0, r), (-1, r), bg))
            criticality_color = {
                "C": C_RED,
                "I": C_AMBER,
                "N": C_HEADER,
            }.get(ctrl.get("criticality", "N"), C_HEADER)
            row_styles.append(("TEXTCOLOR", (1, r), (1, r), criticality_color))

            esito_col = 7 + len(chunk_samples)
            if ctrl_status == STATUS_PASS:
                esito_bg, esito_fg = C_PASS, C_GREEN
            elif ctrl_status == STATUS_DEROGATION:
                esito_bg, esito_fg = C_DEROGATION, C_AMBER
            else:
                esito_bg, esito_fg = C_FAIL, C_RED
            row_styles.append(("BACKGROUND", (esito_col, r), (esito_col, r), esito_bg))
            row_styles.append(("TEXTCOLOR",  (esito_col, r), (esito_col, r), esito_fg))
            row_styles.append(("FONTNAME",   (esito_col, r), (esito_col, r), "Helvetica-Bold"))

            for s_idx, s in enumerate(chunk_samples):
                col = 7 + s_idx
                if s > required_samples:
                    row_styles.append((
                        "BACKGROUND", (col, r), (col, r), C_GRAY_LIGHT
                    ))
                    row_styles.append((
                        "TEXTCOLOR", (col, r), (col, r), C_GRAY
                    ))
                    continue
                m = meas_map.get((ctrl["id"], s))
                if m and get_measurement_status(m) == STATUS_DEROGATION:
                    row_styles.append(("BACKGROUND", (col, r), (col, r), C_DEROGATION))
                    row_styles.append(("TEXTCOLOR",  (col, r), (col, r), C_AMBER))
                elif m and get_measurement_status(m) == STATUS_FAIL:
                    row_styles.append(("BACKGROUND", (col, r), (col, r), C_FAIL))
                    row_styles.append(("TEXTCOLOR",  (col, r), (col, r), C_RED))

        usable_w = (landscape(A4)[0] - (10 * mm))
        fixed_cols = [9*mm, 10*mm, 42*mm, 12*mm, 36*mm, 15*mm, 15*mm]
        esito_w = 22*mm
        fixed_w = sum(fixed_cols) + esito_w
        sample_col_w = max(6*mm, (usable_w - fixed_w) / max(len(chunk_samples), 1))
        col_widths = fixed_cols + ([sample_col_w] * len(chunk_samples)) + [esito_w]

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        base_style = [
            ("BACKGROUND", (0, 0), (-1, 0), C_HEADER),
            ("TEXTCOLOR",  (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("BOX",        (0, 0), (-1, -1), 0.5, C_GRAY),
            ("INNERGRID",  (0, 0), (-1, -1), 0.25, C_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("FONTNAME",   (1, 1), (1, -1), "Helvetica-Bold"),
            ("ALIGN",      (2, 1), (2, -1), "LEFT"),
            ("ALIGN",      (4, 1), (4, -1), "LEFT"),
        ] + row_styles
        tbl.setStyle(TableStyle(base_style))

        story_tables.append(tbl)
        if chunk_end < n_samples:
            story_tables.append(PageBreak())

    return story_tables


def _build_final_result(summary: Dict) -> list:
    status = summary["sampling_evaluation"]["status"]
    msg = summary["sampling_evaluation"]["message"]

    if status == STATUS_PASS:
        bg_color, text_color = C_PASS, C_GREEN
        label = "LOTTO CONFORME — PASS"
    elif status == STATUS_DEROGATION:
        bg_color, text_color = C_DEROGATION, C_AMBER
        label = "LOTTO ACCETTATO IN DEROGA"
    else:
        bg_color, text_color = C_FAIL, C_RED
        label = "LOTTO NON CONFORME — FAIL"

    p_style = ParagraphStyle(
        "Result", fontSize=14, fontName="Helvetica-Bold",
        textColor=text_color, alignment=TA_CENTER
    )

    data = [[Paragraph(label, p_style)]]
    sub_text = (f"Totale misure: {summary['total']}  |  "
                f"Superati: {summary['passed']}  |  "
                f"Falliti: {summary['failed']}  |  "
                f"Derogati: {summary.get('derogated', 0)}<br/>"
                f"{escape(msg)}")
    sub_style = ParagraphStyle(
        "Sub2", fontSize=9, fontName="Helvetica",
        textColor=text_color, alignment=TA_CENTER
    )
    data.append([Paragraph(sub_text, sub_style)])

    tbl = Table(data, colWidths=[267*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), bg_color),
        ("BOX",        (0, 0), (-1, -1), 1.5,
         text_color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [tbl]


def _build_derogations(controls: List[Dict], summary: Dict, styles) -> list:
    """Costruisce la sezione di tracciabilità delle misure accettate in deroga."""
    derogations = [
        m for m in summary.get("measurements", [])
        if get_measurement_status(m) == STATUS_DEROGATION
    ]
    if not derogations:
        return []

    controls_by_id = {ctrl["id"]: ctrl for ctrl in controls}
    title_style = ParagraphStyle(
        "DerogationTitle", fontSize=11, fontName="Helvetica-Bold",
        textColor=C_AMBER, alignment=TA_LEFT,
    )
    cell_style = ParagraphStyle(
        "DerogationCell", fontSize=7, fontName="Helvetica",
        textColor=C_BLACK, alignment=TA_LEFT, leading=9,
    )
    header_style = ParagraphStyle(
        "DerogationHeader", fontSize=7, fontName="Helvetica-Bold",
        textColor=C_WHITE, alignment=TA_CENTER,
    )

    rows = [[
        Paragraph("Ref.", header_style),
        Paragraph("Campione", header_style),
        Paragraph("Misura", header_style),
        Paragraph("Motivazione", header_style),
        Paragraph("Autorizzato da", header_style),
        Paragraph("Registrato da", header_style),
        Paragraph("Data/Ora", header_style),
    ]]
    for measurement in derogations:
        ctrl = controls_by_id.get(measurement["control_id"], {})
        if ctrl.get("control_type") == "dimensional":
            value = format_decimal(measurement.get("value_num"))
        else:
            value = "Sì" if measurement.get("value_bool") else "No"
        recorded_at = str(measurement.get("derogation_at") or "—")[:19]
        rows.append([
            str(ctrl.get("balloon_num", "—")),
            str(measurement.get("sample_num", "—")),
            value,
            Paragraph(escape(measurement.get("derogation_reason") or "—"), cell_style),
            Paragraph(escape(measurement.get("derogation_authorized_by") or "—"), cell_style),
            Paragraph(escape(measurement.get("derogation_accepted_by") or "—"), cell_style),
            recorded_at,
        ])

    table = Table(
        rows,
        colWidths=[12*mm, 16*mm, 22*mm, 80*mm, 43*mm, 43*mm, 36*mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_AMBER),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("BACKGROUND", (0, 1), (-1, -1), C_DEROGATION),
        ("BOX", (0, 0), (-1, -1), 0.7, C_AMBER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, C_GRAY),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (2, -1), "CENTER"),
        ("ALIGN", (6, 1), (6, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [
        Paragraph("DETTAGLIO ACCETTAZIONI IN DEROGA", title_style),
        Spacer(1, 2*mm),
        table,
    ]


def _build_footer(summary: Dict, styles) -> list:
    lot = summary["lot"]
    footer_style = ParagraphStyle(
        "Footer", fontSize=8, fontName="Helvetica",
        textColor=colors.HexColor("#888888"), alignment=TA_LEFT
    )
    text = (f"Note lotto: {lot.get('notes') or '—'}  |  "
            f"Operatore: {lot.get('operator') or '—'}  |  "
            f"Data apertura lotto: {lot['created_at'][:19]}")
    return [
        HRFlowable(width="100%", thickness=0.5, color=C_GRAY),
        Spacer(1, 2*mm),
        Paragraph(text, footer_style)
    ]
