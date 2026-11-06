import io
import os
from db import format_dmy
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Reportlab only ships the base-14 fonts without embedding a font file, so
# "font customization" here means choosing among these three families —
# each has real regular/bold variants reportlab already knows about.
PDF_FONT_CHOICES = {
    "Helvetica": ("Helvetica", "Helvetica-Bold"),
    "Times-Roman": ("Times-Roman", "Times-Bold"),
    "Courier": ("Courier", "Courier-Bold"),
}


def _apply_pdf_font(styles, font_choice):
    """Mutates the base stylesheet in place so every ParagraphStyle built
    from it afterwards (via parent=styles[...]) picks up the school's
    chosen font automatically. Returns (regular, bold) font names, since
    Tables don't inherit from the paragraph stylesheet and need their
    FONTNAME set explicitly wherever one is used below."""
    regular, bold = PDF_FONT_CHOICES.get(font_choice, PDF_FONT_CHOICES["Helvetica"])
    for name in styles.byName:
        style = styles[name]
        is_heading = name.lower().startswith("heading") or name.lower() == "title"
        style.fontName = bold if is_heading else regular
    return regular, bold


def _header_elements(school_name, logo_path, document_title, subtitle_text, styles, accent_color="#1f3a5f", name_align=None):
    """Shared letterhead: logo (if any) + school name + document title + subtitle."""
    align = {"left": TA_LEFT, "right": TA_RIGHT}.get(name_align, TA_CENTER)
    school_style = ParagraphStyle("school", parent=styles["Heading1"], alignment=align, fontSize=16)
    title_style = ParagraphStyle("title", parent=styles["Heading2"], alignment=TA_CENTER, textColor=colors.HexColor(accent_color))
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], alignment=TA_CENTER)

    elements = []

    if logo_path and os.path.exists(logo_path):
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo_path) as im:
                w, h = im.size
            target_h = 1.8 * cm
            target_w = target_h * (w / h)
            img = Image(logo_path, width=target_w, height=target_h)
            img.hAlign = "CENTER"
            elements.append(img)
            elements.append(Spacer(1, 0.15 * cm))
        except Exception:
            pass

    if school_name:
        elements.append(Paragraph(school_name, school_style))

    elements.append(Paragraph(document_title, title_style))
    elements.append(Paragraph(subtitle_text, sub_style))
    elements.append(Spacer(1, 0.5 * cm))
    return elements


def build_broadsheet_pdf(class_row, term, subjects, rows, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica", accent_color="#1f3a5f", use_ca3=False):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=1 * cm, bottomMargin=1 * cm)
    styles = getSampleStyleSheet()
    regular, bold = _apply_pdf_font(styles, font_choice)

    elements = _header_elements(
        school_name, logo_path, "BROADSHEET",
        f"{class_row['name']}" + (f" ({class_row['category']})" if class_row['category'] else "") +
        f" &mdash; {term['session_name']} &mdash; {term['name']}",
        styles, accent_color=accent_color,
    )

    # Assessment columns follow the school's configuration: 1st CA | 2nd CA | (3rd CA) | Exam | Total per subject.
    comp = [("ca1", "1st CA"), ("ca2", "2nd CA")] + ([("ca3", "3rd CA")] if use_ca3 else []) + [("exam", "Exam"), ("total", "Total")]
    width = len(comp)
    top = ["S/N", "Student Name"]
    sub = ["", ""]
    for s in subjects:
        top += [s["name"]] + [""] * (width - 1)
        sub += [label for _k, label in comp]
    top += ["Total", "Average", "Position"]
    sub += ["", "", ""]
    data = [top, sub]
    for i, r in enumerate(rows, start=1):
        name = student_full_name(r["student"]) if student_full_name else f"{r['student']['last_name']} {r['student']['first_name']}"
        row = [str(i), name]
        for subj in subjects:
            cell = r["scores"][subj["id"]]
            row += [str(cell.get(k, "-")) for k, _label in comp]
        row.append(str(r["total"]))
        row.append(str(r["average"]))
        row.append(str(r["position"]))
        data.append(row)

    table = Table(data, repeatRows=2)
    spans = [("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1))]
    for i in range(len(subjects)):
        c0 = 2 + i * width
        spans.append(("SPAN", (c0, 0), (c0 + width - 1, 0)))
    last = 2 + len(subjects) * width
    spans += [("SPAN", (last + k, 0), (last + k, 1)) for k in range(3)]
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor(accent_color)),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTNAME", (0, 0), (-1, 1), bold),
        ("FONTSIZE", (0, 0), (-1, -1), 6 if width > 4 else 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ] + spans))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return buf


def _img_flow(path, max_h, max_w=None):
    """An Image flowable scaled to fit (never stretched). Returns None if the file is missing/unreadable."""
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            im.load()
            w, h = im.size
        scale = max_h / h
        if max_w and w * scale > max_w:
            scale = max_w / w
        return Image(path, width=w * scale, height=h * scale)
    except Exception:
        return None


def _hex(c, fallback):
    try:
        return colors.HexColor(c)
    except Exception:
        return colors.HexColor(fallback)


def _tint(color, amount):
    return colors.Color(1 - (1 - color.red) * amount, 1 - (1 - color.green) * amount, 1 - (1 - color.blue) * amount)


def _result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color="#0b2a6f",
                      name_align=None, teacher_signature=None, principal_signature=None):
    """V100: delegates to pdf_sheet.py, which draws the single "Updated Terminal Report Sheet" design --
    the same sections, order and colours as templates/_result_sheet.html + result-sheet.css, including the
    Cumulative / Annual Performance table -- so a downloaded PDF matches the print view even on hosts
    where the Chromium-based path cannot run. Returns the page's flowables (already shrunk to one page)."""
    import pdf_sheet
    regular, bold = styles["Normal"].fontName, styles["Heading1"].fontName
    els, pal, wm = pdf_sheet.result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color=accent_color,
                                              teacher_signature=teacher_signature, principal_signature=principal_signature,
                                              regular=regular, bold=bold)
    return pdf_sheet.one_page(els, pal, wm, bold)


def _one_page(elements, doc):
    """Result sheets are already wrapped into one-page frames by pdf_sheet; anything else is shrunk, never cut."""
    from reportlab.platypus import KeepInFrame
    import pdf_sheet
    if len(elements) == 1 and isinstance(elements[0], pdf_sheet.SheetFrame):
        return elements
    return [KeepInFrame(doc.width, doc.height, elements, mode="shrink")]


def _sheet_doc(buf):
    import pdf_sheet
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=pdf_sheet.MARGIN_X, rightMargin=pdf_sheet.MARGIN_X,
                             topMargin=pdf_sheet.MARGIN_Y, bottomMargin=pdf_sheet.MARGIN_Y)


def build_result_pdf(data, term, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica",
                      accent_color="#0b2a6f", name_align=None, teacher_signature=None, principal_signature=None):
    if teacher_signature is None and data.get("teacher_signature_path"):
        teacher_signature = {"path": data.get("teacher_signature_path"), "name": data.get("teacher_name")}
    if principal_signature is None and data.get("principal_signature_path"):
        principal_signature = {"path": data.get("principal_signature_path"), "name": data.get("principal_name")}
    buf = io.BytesIO()
    doc = _sheet_doc(buf)
    styles = getSampleStyleSheet()
    _apply_pdf_font(styles, font_choice)
    elements = _result_elements(data, term, school_name, logo_path, student_full_name, styles,
                                 accent_color=accent_color, name_align=name_align,
                                 teacher_signature=teacher_signature, principal_signature=principal_signature)
    doc.build(_one_page(elements, doc))
    buf.seek(0)
    return buf


def build_class_results_pdf(data_list, term, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica",
                             accent_color="#0b2a6f", name_align=None):
    """One combined, printable PDF containing every student's terminal
    result in a class, each starting on its own page."""
    buf = io.BytesIO()
    doc = _sheet_doc(buf)
    styles = getSampleStyleSheet()
    _apply_pdf_font(styles, font_choice)
    elements = []
    for i, data in enumerate(data_list):
        if i > 0:
            elements.append(PageBreak())
        elements.extend(_one_page(_result_elements(data, term, school_name, logo_path, student_full_name, styles,
                                                   accent_color=accent_color, name_align=name_align,
                                                   teacher_signature=({"path": data.get("teacher_signature_path"), "name": data.get("teacher_name")} if data.get("teacher_signature_path") else None),
                                                   principal_signature=({"path": data.get("principal_signature_path"), "name": data.get("principal_name")} if data.get("principal_signature_path") else None)), doc))
    doc.build(elements)
    buf.seek(0)
    return buf


def build_cumulative_result_pdf(data, session, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica",
                                 accent_color="#0b2a6f", name_align=None, rs=None):
    """Annual / Cumulative Result fallback (V100): the same Cumulative / Annual Performance table and
    sheet design as the print view -- every term's CA1/CA2/Exam/Total/Avg./Pos. plus the Overall
    Cumulative group, with fixed column widths so Remark is never cut off."""
    import pdf_sheet
    buf = io.BytesIO()
    doc = _sheet_doc(buf)
    styles = getSampleStyleSheet()
    regular, bold = _apply_pdf_font(styles, font_choice)
    els, pal, wm = pdf_sheet.cumulative_page_elements(data, session, school_name, logo_path, student_full_name, rs or {},
                                                       accent_color=accent_color, regular=regular, bold=bold)
    doc.build(pdf_sheet.one_page(els, pal, wm, bold))
    buf.seek(0)
    return buf


def build_generic_table_pdf(title, subtitle, headers, rows, school_name=None, logo_path=None, font_choice="Helvetica",
                             accent_color="#1f3a5f"):
    """A plain landscape table report (headers + rows) with the school's
    letterhead — used for reports that aren't a results document, like the
    Staff Attendance export."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=1 * cm, bottomMargin=1 * cm)
    styles = getSampleStyleSheet()
    regular, bold = _apply_pdf_font(styles, font_choice)
    elements = _header_elements(school_name, logo_path, title, subtitle, styles, accent_color=accent_color)

    data = [headers] + [[str(c) for c in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(accent_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return buf
