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


def build_broadsheet_pdf(class_row, term, subjects, rows, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica", accent_color="#1f3a5f"):
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

    header = ["S/N", "Student Name"] + [s["name"] for s in subjects] + ["Total", "Average", "Position"]
    data = [header]
    for i, r in enumerate(rows, start=1):
        name = student_full_name(r["student"]) if student_full_name else f"{r['student']['last_name']} {r['student']['first_name']}"
        row = [str(i), name]
        for subj in subjects:
            row.append(str(r["scores"][subj["id"]]["total"]))
        row.append(str(r["total"]))
        row.append(str(r["average"]))
        row.append(str(r["position"]))
        data.append(row)

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(accent_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
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


def _result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color="#1f3a5f",
                      name_align=None, teacher_signature=None, principal_signature=None):
    """Paint the unified sheet model (sheet_model.build_sheet) with ReportLab. The HTML preview/print paints the very same
    model, so what is shown, hidden, ordered and worded is identical; only the drawing technology differs."""
    sheet = data["sheet"]
    st, h = sheet["style"], sheet["header"]
    accent = _hex(st["accent"], "#1f3a5f")
    second = _hex(st["secondary"], "#c9a227")
    template = st["template"]
    compact, formal, modern = template == "compact_academic", template == "formal_school", template == "modern_academic"
    regular, bold = styles["Normal"].fontName, styles["Heading1"].fontName
    base = 8.5 if compact else 9
    pad = 2 if compact else 4
    al = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
    text_al = al.get(h["text_align"], TA_CENTER)
    esc = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    small = ParagraphStyle("rsSmall", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#444444"))
    normal = ParagraphStyle("rsNormal", parent=styles["Normal"], fontSize=base, leading=base + 2)
    h3 = ParagraphStyle("rsH3", parent=styles["Heading3"], fontSize=10.5, textColor=accent, spaceBefore=4, spaceAfter=2)
    on_dark = colors.white if modern else None
    school_style = ParagraphStyle("rsSchool", parent=styles["Heading1"], fontSize=16, textColor=on_dark or accent, alignment=text_al, spaceAfter=0)
    title_style = ParagraphStyle("rsTitle", parent=styles["Heading2"], fontSize=12, alignment=text_al, textColor=on_dark or colors.black, spaceAfter=0)
    sub_style = ParagraphStyle("rsSub", parent=styles["Normal"], fontSize=8.5, alignment=text_al, textColor=on_dark or colors.HexColor("#444444"))
    elements = []

    # ---- header: a logo row (aligned on its own) above the school text (aligned on its own) --------------------------------------
    head_rows = []
    logo = _img_flow(h["logo_path"], 1.9 * cm, 5 * cm) if h.get("logo_uri") else None
    if logo is not None:
        t = Table([[logo]], colWidths=[17.8 * cm])
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), h["logo_align"].upper()), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        head_rows.append([t])
    text_cell = [Paragraph(esc(h["school_name"]), school_style)]
    for line in (h["motto"], h["address"], h["contact"]):
        if line:
            text_cell.append(Paragraph(esc(line), sub_style))
    text_cell.append(Paragraph(esc(h["title"]).upper(), title_style))
    if h["term_line"]:
        text_cell.append(Paragraph(esc(h["term_line"]), sub_style))
    head_rows.append([text_cell])
    head = Table(head_rows, colWidths=[17.8 * cm])
    hs = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if modern:
        hs += [("BACKGROUND", (0, 0), (-1, -1), accent)]
    else:
        hs += [("LINEBELOW", (0, -1), (-1, -1), 3 if formal else 2.2, accent)]
    head.setStyle(TableStyle(hs))
    elements += [head, Spacer(1, 0.35 * cm)]

    # ---- identity + passport (no border; aspect ratio kept; blank when none) ---------------------------------------------------
    cells = sheet["identity"]
    rows = []
    for i in range(0, len(cells), 2):
        r = []
        for lab, val in cells[i:i + 2]:
            r += [lab + ":", Paragraph(esc(val), normal)]
        while len(r) < 4:
            r += ["", ""]
        rows.append(r)
    idw = [3.0 * cm, 4.6 * cm, 3.0 * cm, 4.2 * cm] if sheet["passport"] else [3.2 * cm, 5.6 * cm, 3.4 * cm, 5.6 * cm]
    idt = Table(rows, colWidths=idw)
    idt.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), bold), ("FONTNAME", (2, 0), (2, -1), bold), ("FONTSIZE", (0, 0), (-1, -1), base),
                             ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f4f9") if modern else colors.white), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc"))]))
    if sheet["passport"]:
        pimg = _img_flow(sheet["passport"]["path"], 3.4 * cm, 2.6 * cm) if sheet["passport"]["uri"] else None
        wrap = Table([[idt, pimg if pimg is not None else ""]], colWidths=[14.8 * cm, 3.0 * cm])
        wrap.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
        elements.append(wrap)
    else:
        elements.append(idt)
    elements.append(Spacer(1, 0.25 * cm))

    # ---- subjects --------------------------------------------------------------------------------------------------------------------
    cols, body_rows = sheet["table"]["cols"], sheet["table"]["rows"]
    body = [[c["label"] for c in cols]]
    for r in body_rows:
        body.append([Paragraph(esc(v), normal) if cols[i]["align"] == "l" else v for i, v in enumerate(r)])
    left_idx = [i for i, c in enumerate(cols) if c["align"] == "l"]
    fixed = 4.4 * cm + sum(3.4 * cm for i in left_idx if i != 0)
    n_num = max(len(cols) - len(left_idx), 1)
    num_w = max(1.1 * cm, (17.8 * cm - fixed) / n_num)
    widths = [4.4 * cm if i == 0 else (3.4 * cm if i in left_idx else num_w) for i in range(len(cols))]
    scale_to = 17.8 * cm / sum(widths)
    widths = [w * scale_to for w in widths]
    subj = Table(body, colWidths=widths, repeatRows=1)
    hdr_bg = colors.white if formal else (second if modern else accent)
    hdr_fg = accent if formal else (colors.black if modern else colors.white)
    ts = [("BACKGROUND", (0, 0), (-1, 0), hdr_bg), ("TEXTCOLOR", (0, 0), (-1, 0), hdr_fg), ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), regular),
          ("FONTSIZE", (0, 0), (-1, -1), base), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.5, accent if formal else colors.HexColor("#999999")), ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6f8")])]
    for i in left_idx:
        ts.append(("ALIGN", (i, 0), (i, -1), "LEFT"))
    subj.setStyle(TableStyle(ts))
    elements += [Paragraph("Academic Performance", h3), subj]

    # ---- educational domains (+ the 1-5 meaning) ----------------------------------------------------------------------------------------
    dom = sheet["domains"]
    if dom:
        elements.append(Paragraph("Educational Domains", h3))
        tables = []
        for g in dom["groups"]:
            rows_ = [[g["label"], "", ""]] + [[n, v, m] for n, v, m in g["items"]]
            t = Table(rows_, colWidths=[4.2 * cm, 1.0 * cm, 2.2 * cm])
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), accent), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), bold), ("SPAN", (0, 0), (-1, 0)),
                                   ("FONTNAME", (0, 1), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), base - 0.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                   ("ALIGN", (1, 0), (1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
            tables.append(t)
        for i in range(0, len(tables), 2):
            pair = tables[i:i + 2]
            row = Table([pair + [""] * (2 - len(pair))], colWidths=[8.9 * cm, 8.9 * cm])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            elements += [row, Spacer(1, 0.12 * cm)]
        if dom["legend"]:
            elements.append(Paragraph("<b>Scale:</b> " + "  ".join(f"{n} = {esc(w)}" for n, w in dom["legend"]), small))

    # ---- attendance / promotion, custom fields -----------------------------------------------------------------------------------------------
    def info_strip(items):
        t = Table([[a for a, _ in items], [esc(b) if False else b for _, b in items]])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), regular),
                               ("FONTSIZE", (0, 0), (-1, -1), base), ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1)]))
        return t
    if sheet["attendance"]:
        elements += [Spacer(1, 0.25 * cm), info_strip(sheet["attendance"])]
    if sheet["custom"]:
        elements += [Spacer(1, 0.2 * cm), info_strip(sheet["custom"])]

    # ---- comments: separate boxes ----------------------------------------------------------------------------------------------------------------
    if sheet["comments"]:
        elements.append(Spacer(1, 0.25 * cm))
    for label, text in sheet["comments"]:
        t = Table([[Paragraph(f"<b>{esc(label)}</b>", normal)], [Paragraph(esc(text).replace("\n", "<br/>") or "&nbsp;", normal)]], colWidths=[17.6 * cm],
                  rowHeights=[None, 0.9 * cm if compact else 1.3 * cm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        elements += [t, Spacer(1, 0.15 * cm)]

    # ---- signatures + sign dates -----------------------------------------------------------------------------------------------------------------------
    cells = []
    for g in sheet["signatures"]:
        cell = []
        if g["show_signature"]:
            simg = _img_flow(g["path"], 1.0 * cm, 4 * cm) if g["uri"] else None
            cell.append(simg if simg is not None else Spacer(1, 1.0 * cm))
            cell.append(Paragraph(esc(g["role"] + (": " + g["name"] if g["name"] else "")), ParagraphStyle("sg", parent=normal, alignment=TA_CENTER)))
        if g["show_date"]:
            cell.append(Paragraph("Date: " + esc(g["date"]), ParagraphStyle("sd", parent=normal, alignment=TA_CENTER)))
        cells.append(cell)
    if cells:
        sg = Table([cells + [""] * (2 - len(cells))] if len(cells) < 2 else [cells], colWidths=[8.8 * cm, 8.8 * cm])
        sg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        elements += [Spacer(1, 0.2 * cm), sg]
    if sheet["key"]:
        elements += [Spacer(1, 0.2 * cm), Paragraph("<b>Grading key:</b> " + esc(sheet["key"]), small)]
    if sheet["footer"]:
        elements += [Spacer(1, 0.15 * cm), Paragraph(esc(sheet["footer"]), small)]
    return elements


def _one_page(elements, doc):
    """Shrink the sheet (never cut it) so one result is exactly one A4 page."""
    from reportlab.platypus import KeepInFrame
    return [KeepInFrame(doc.width, doc.height, elements, mode="shrink")]


def build_result_pdf(data, term, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica",
                      accent_color="#1f3a5f", name_align=None, teacher_signature=None, principal_signature=None):
    if teacher_signature is None and data.get("teacher_signature_path"):
        teacher_signature = {"path": data.get("teacher_signature_path"), "name": data.get("teacher_name")}
    if principal_signature is None and data.get("principal_signature_path"):
        principal_signature = {"path": data.get("principal_signature_path"), "name": data.get("principal_name")}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = getSampleStyleSheet()
    _apply_pdf_font(styles, font_choice)
    elements = _result_elements(data, term, school_name, logo_path, student_full_name, styles,
                                 accent_color=accent_color, name_align=name_align,
                                 teacher_signature=teacher_signature, principal_signature=principal_signature)
    doc.build(_one_page(elements, doc))
    buf.seek(0)
    return buf


def build_class_results_pdf(data_list, term, school_name=None, logo_path=None, student_full_name=None, font_choice="Helvetica",
                             accent_color="#1f3a5f", name_align=None):
    """One combined, printable PDF containing every student's terminal
    result in a class, each starting on its own page."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
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
                                 accent_color="#1f3a5f", name_align=None):
    """Annual/Cumulative Result: one column per term plus a cumulative
    average/grade per subject, for the whole session rather than one term."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = getSampleStyleSheet()
    regular, bold = _apply_pdf_font(styles, font_choice)
    section_style = ParagraphStyle("section", parent=styles["Heading3"], textColor=colors.HexColor(accent_color))

    elements = _header_elements(
        school_name, logo_path, "ANNUAL / CUMULATIVE RESULT", session["name"], styles,
        accent_color=accent_color, name_align=name_align,
    )

    student = data["student"]
    class_row = data["class_row"]
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"

    info_table = Table([
        ["Name:", name, "Adm./Reg. No.:", student["admission_no"]],
        ["Class / Arm:", class_row["name"], "Category:" if class_row["category"] else "", class_row["category"] or ""],
        ["Cumulative Average:", str(data["average"]), "Grade:", str(data["grade"])],
        ["Position:", f"{data['position']} of {data['class_size']}", "", ""],
    ], colWidths=[3.5 * cm, 5 * cm, 3.5 * cm, 5 * cm])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTNAME", (0, 0), (0, -1), bold),
        ("FONTNAME", (2, 0), (2, -1), bold),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph("Academic Performance Across the Session", section_style))
    term_names = [t["name"] for t in data["terms"]]
    subj_header = ["Subject"] + term_names + ["Cumulative Avg", "Grade"]
    subj_data = [subj_header]
    for s in data["subjects"]:
        row = [s["name"]]
        for v in s["term_values"]:
            row.append(str(v) if v is not None else "-")
        row.append(str(s["average"]))
        row.append(str(s["grade"]))
        subj_data.append(row)
    col_widths = [5 * cm] + [2.2 * cm] * len(term_names) + [2.8 * cm, 2 * cm]
    subj_table = Table(subj_data, repeatRows=1, colWidths=col_widths)
    subj_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(accent_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    elements.append(subj_table)
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(
        "Cumulative Average is the mean of the totals from every term above that has a score "
        "recorded for that subject.", styles["Normal"],
    ))

    doc.build(elements)
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
