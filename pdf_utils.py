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


# Layout differences for the V64 styles; the HTML/print CSS in static/css/result-sheet.css mirrors the same choices.
STYLE_SPECS = {
    "executive_band": {"header": "band", "head_align": "left", "id": "strip", "table": "rows"},
    "minimal_clean": {"header": "plain", "id": "minimal", "table": "minimal"},
    "ledger_classic": {"header": "ledger", "id": "ledger", "table": "ledger", "mono": True, "paper": "#fffdf5"},
    "vibrant_cards": {"header": "band", "id": "cards", "table": "cards"},
    "split_header": {"header": "split", "head_align": "left", "id": "topbar", "table": "rows"},
}


def _tint(color, amount):
    return colors.Color(1 - (1 - color.red) * amount, 1 - (1 - color.green) * amount, 1 - (1 - color.blue) * amount)


def _result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color="#1f3a5f",
                      name_align=None, teacher_signature=None, principal_signature=None):
    """One student's terminal result as flowables. Mirrors templates/_result_sheet.html: the same Result Display
    Settings (data["rs"]) decide every section, so preview, print and PDF cannot disagree."""
    rs = data.get("rs") or {}
    info = data.get("info") or {}
    student, class_row = data["student"], data["class_row"]
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"
    accent = _hex(rs.get("accent") or accent_color, "#1f3a5f")
    second = _hex(rs.get("secondary") or "#c9a227", "#c9a227")
    template = rs.get("template", "professional_classic")
    compact = template == "compact_academic"
    formal = template == "formal_school"
    modern = template == "modern_academic"
    spec = STYLE_SPECS.get(template, {})
    dark_head = modern or spec.get("header") in ("band", "split")
    regular, bold = styles["Normal"].fontName, styles["Heading1"].fontName
    if spec.get("mono"):
        regular, bold = "Courier", "Courier-Bold"
        for _n in ("Normal", "Heading1", "Heading2", "Heading3"):
            styles[_n].fontName = bold if _n.startswith("Heading") else regular
    head_align = TA_LEFT if spec.get("head_align") == "left" else TA_CENTER
    base = 8.5 if compact else 9
    pad = 2 if compact else 4
    small = ParagraphStyle("rsSmall", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#444444"))
    normal = ParagraphStyle("rsNormal", parent=styles["Normal"], fontSize=base, leading=base + 2)
    h3 = ParagraphStyle("rsH3", parent=styles["Heading3"], fontSize=10.5, textColor=accent, spaceBefore=4, spaceAfter=2)
    school_style = ParagraphStyle("rsSchool", parent=styles["Heading1"], fontSize=16, textColor=colors.white if dark_head else accent, alignment=head_align, spaceAfter=0)
    title_style = ParagraphStyle("rsTitle", parent=styles["Heading2"], fontSize=12, alignment=head_align, textColor=colors.white if dark_head else colors.black, spaceAfter=0)
    sub_style = ParagraphStyle("rsSub", parent=styles["Normal"], fontSize=8.5, alignment=head_align, textColor=colors.white if dark_head else colors.HexColor("#444444"))
    elements = []

    # ---- header: logo (only if enabled AND uploaded) | school text | passport (blank frame if none) ----------------
    logo = _img_flow(rs.get("logo_path"), 1.9 * cm, 3 * cm) if rs.get("show_logo") and rs.get("header_layout") != "no-logo" else None
    text_cell = [Paragraph((school_name or rs.get("school_name") or "").replace("&", "&amp;"), school_style)]
    if rs.get("tagline"):
        text_cell.append(Paragraph(str(rs["tagline"]).replace("&", "&amp;"), sub_style))
    if rs.get("contact"):
        text_cell.append(Paragraph(rs["contact"].replace("&", "&amp;"), sub_style))
    text_cell.append(Paragraph((rs.get("title") or "Terminal Report Sheet").upper().replace("&", "&amp;"), title_style))
    ses = [x for x in ((term["session_name"] if rs.get("show_session", True) else None), (term["name"] if rs.get("show_term", True) else None)) if x]
    if ses:
        text_cell.append(Paragraph(" &mdash; ".join(ses), sub_style))
    passport_cell = ""
    if rs.get("show_passport"):
        pimg = _img_flow(rs.get("passport_path"), 3.0 * cm, 2.4 * cm)
        passport_cell = pimg if pimg is not None else ""
    left = logo if (logo is not None and rs.get("header_layout") in (None, "logo-left", "logo-center")) else ""
    right = passport_cell
    if logo is not None and rs.get("header_layout") == "logo-right":
        left, right = right, logo
        if not rs.get("show_passport"):
            left = ""
    head = Table([[left, text_cell, right]], colWidths=[3.2 * cm, 11.4 * cm, 3.2 * cm])
    hs = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (2, 0), (2, 0), "RIGHT"),
          ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    if rs.get("show_passport"):
        hs += [("BOX", (2, 0), (2, 0), 0.8, colors.grey)]          # the frame stays even when empty: blank, never an avatar
    if modern or spec.get("header") == "band":
        hs += [("BACKGROUND", (0, 0), (-1, -1), accent), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
        if template == "vibrant_cards":
            hs += [("LINEBELOW", (0, 0), (-1, -1), 5, second)]
    elif spec.get("header") == "split":
        hs += [("BACKGROUND", (0, 0), (1, 0), accent), ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#e9edf4")),
               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
    elif spec.get("header") == "plain":
        hs += [("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#bbbbbb")), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    elif spec.get("header") == "ledger":
        hs += [("LINEABOVE", (0, 0), (-1, -1), 1.8, colors.black), ("LINEBELOW", (0, 0), (-1, -1), 1.8, colors.black),
               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    else:
        hs += [("LINEBELOW", (0, 0), (-1, -1), 2.2 if not formal else 3, accent), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    head.setStyle(TableStyle(hs))
    elements += [head, Spacer(1, 0.3 * cm)]

    # ---- identity block -----------------------------------------------------------------------------------------------
    cells = [("Name:", name)]
    if rs.get("show_admission_no", True):
        cells.append(("Adm./Reg. No.:", student["admission_no"]))
    if rs.get("show_class", True):
        cells.append(("Class / Arm:", class_row["name"]))
    if rs.get("show_session", True):
        cells.append(("Academic Session:", term["session_name"]))
    if rs.get("show_term", True):
        cells.append(("Term:", term["name"]))
    if rs.get("show_score", True):
        cells += [("Total Score:", str(data["total"])), ("Average:", str(data["average"]))]
    cells.append(("No. of Subjects:", f"{data.get('subjects_written', '-')} of {len(data['subjects'])}"))
    if rs.get("show_overall_position", True):
        cells.append(("Overall Position:", f"{data.get('position_text', data['position'])} of {data['class_size']}"))
    if data.get("result_date"):
        cells.append(("Result Date:", data["result_date"]))
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        r = []
        for lab, val in pair:
            r += [lab, Paragraph(str(val).replace("&", "&amp;"), normal)]
        while len(r) < 4:
            r += ["", ""]
        rows.append(r)
    idt = Table(rows, colWidths=[3.2 * cm, 5.6 * cm, 3.4 * cm, 5.6 * cm])
    id_style = [("FONTNAME", (0, 0), (0, -1), bold), ("FONTNAME", (2, 0), (2, -1), bold), ("FONTSIZE", (0, 0), (-1, -1), base),
                ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    id_mode = spec.get("id")
    if id_mode == "strip":
        id_style += [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f7f9")), ("LINEBEFORE", (0, 0), (0, -1), 2.2, second), ("LINEBEFORE", (2, 0), (2, -1), 2.2, second)]
    elif id_mode == "minimal":
        id_style += [("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd"))]
    elif id_mode == "ledger":
        id_style += [("GRID", (0, 0), (-1, -1), 1.0, colors.black)]
    elif id_mode == "cards":
        id_style += [("BACKGROUND", (0, 0), (-1, -1), _tint(accent, 0.11)), ("GRID", (0, 0), (-1, -1), 3, colors.white)]
    elif id_mode == "topbar":
        id_style += [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f7f9")), ("LINEABOVE", (0, 0), (-1, 0), 2.5, accent)]
    else:
        id_style += [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f4f9") if modern else colors.white), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc"))]
    idt.setStyle(TableStyle(id_style))
    elements += [idt, Spacer(1, 0.25 * cm)]

    # ---- subjects ---------------------------------------------------------------------------------------------------------
    show_ca3 = data.get("show_ca3")
    head_row = ["Subject"]
    if rs.get("show_score", True):
        head_row += ["CA1", "CA2"] + (["CA3"] if show_ca3 else []) + ["Exam", "Total"]
    if rs.get("show_grade", True):
        head_row.append("Grade")
    if rs.get("show_subject_position"):
        head_row.append("Position")
    with_remarks = rs.get("show_remarks", True) and not compact
    if with_remarks:
        head_row.append("Remark")
    body = [head_row]
    for s in data["subjects"]:
        r = [Paragraph(str(s["name"]).replace("&", "&amp;"), normal)]
        if rs.get("show_score", True):
            r += [str(s["ca1"]), str(s["ca2"])] + ([str(s.get("ca3", "-"))] if show_ca3 else []) + [str(s["exam"]), str(s["total"])]
        if rs.get("show_grade", True):
            r.append(str(s["grade"]))
        if rs.get("show_subject_position"):
            r.append(str(s.get("position_text", "-")))
        if with_remarks:
            r.append(str(s["remark"]))
        body.append(r)
    n_cols = len(head_row)
    name_w = 4.8 * cm
    rem_w = 3.0 * cm if with_remarks else 0
    other = max(n_cols - 1 - (1 if with_remarks else 0), 1)
    num_w = max(1.1 * cm, (17.8 * cm - name_w - rem_w) / other)
    widths = [name_w] + [num_w] * other + ([rem_w] if with_remarks else [])
    subj = Table(body, colWidths=widths, repeatRows=1)
    hdr_bg = colors.white if formal else (second if modern else accent)
    hdr_fg = accent if formal else (colors.black if modern else colors.white)
    ts = [("BACKGROUND", (0, 0), (-1, 0), hdr_bg), ("TEXTCOLOR", (0, 0), (-1, 0), hdr_fg), ("FONTNAME", (0, 0), (-1, 0), bold),
          ("FONTNAME", (0, 1), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), base), ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.5, accent if formal else colors.HexColor("#999999")),
          ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6f8")])]
    tmode = spec.get("table")
    if tmode == "rows":
        ts = [t for t in ts if t[0] not in ("GRID", "ROWBACKGROUNDS")] + [("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#d5d9e0"))]
    elif tmode == "minimal":
        ts = [t for t in ts if t[0] not in ("GRID", "ROWBACKGROUNDS", "BACKGROUND", "TEXTCOLOR")] + [
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black), ("LINEBELOW", (0, 0), (-1, 0), 1.4, colors.black), ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e2e2e2"))]
    elif tmode == "ledger":
        ts = [t for t in ts if t[0] not in ("GRID", "ROWBACKGROUNDS", "BACKGROUND", "TEXTCOLOR")] + [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe9d2")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.black), ("GRID", (0, 0), (-1, -1), 0.9, colors.black),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fffdf5"), colors.HexColor("#faf5e1")])]
    elif tmode == "cards":
        ts = [t for t in ts if t[0] not in ("GRID", "ROWBACKGROUNDS")] + [
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_tint(accent, 0.07), colors.white]), ("LINEBELOW", (0, 1), (-1, -1), 0.8, colors.white)]
    if with_remarks:
        ts.append(("ALIGN", (-1, 1), (-1, -1), "LEFT"))
    subj.setStyle(TableStyle(ts))
    elements += [Paragraph("Academic Performance", h3), subj]

    # ---- educational domains ------------------------------------------------------------------------------------------------
    groups = data.get("domain_groups") if rs.get("show_domains", True) else None
    if groups:
        elements.append(Paragraph("Educational Domains (rated 1-5)", h3))
        tables = []
        for g in groups:
            rows_ = [[g["label"], "Rating"]] + [[n, str(v)] for n, v in g["items"]]
            t = Table(rows_, colWidths=[5.3 * cm, 1.5 * cm])
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), accent), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), bold),
                                   ("FONTNAME", (0, 1), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), base - 0.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                   ("ALIGN", (1, 0), (1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
            tables.append(t)
        for i in range(0, len(tables), 2):
            pair = tables[i:i + 2]
            row = Table([pair + [""] * (2 - len(pair))], colWidths=[8.9 * cm, 8.9 * cm])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            elements += [row, Spacer(1, 0.15 * cm)]

    # ---- attendance --------------------------------------------------------------------------------------------------------------
    promo = data.get("promotion_status") if rs.get("show_promotion", True) else None
    att_cols = []
    if rs.get("show_attendance", True):
        if rs.get("show_days_opened", True):
            att_cols.append(("Days School Opened", info.get("days_school_opened")))
        if rs.get("show_days_present", True):
            att_cols.append(("Days Present", info.get("days_present")))
        if rs.get("show_days_absent", True):
            att_cols.append(("Days Absent", info.get("days_absent")))
    if promo:
        att_cols.append(("Promotion / Status", promo))
    if att_cols:
        att = Table([[c[0] for c in att_cols], [("-" if c[1] is None else str(c[1])) for c in att_cols]])
        att.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, 0), bold),
                                 ("FONTNAME", (0, 1), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), base), ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1)]))
        elements += [Spacer(1, 0.25 * cm), att]

    # ---- comments: separate boxes, separate values --------------------------------------------------------------------------------
    def comment_box(label, text):
        t = Table([[Paragraph(f"<b>{label}</b>", normal)], [Paragraph((text or "").replace("&", "&amp;").replace("\n", "<br/>") or "&nbsp;", normal)]], colWidths=[17.6 * cm],
                  rowHeights=[None, 0.9 * cm if compact else 1.3 * cm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t
    if rs.get("show_teacher_comment", True) or rs.get("show_principal_comment", True):
        elements.append(Spacer(1, 0.25 * cm))
        if rs.get("show_teacher_comment", True):
            elements += [comment_box("Class/Form Teacher's Comment", info.get("teacher_comment")), Spacer(1, 0.15 * cm)]
        if rs.get("show_principal_comment", True):
            elements += [comment_box("Principal's Comment", info.get("principal_comment")), Spacer(1, 0.15 * cm)]

    # ---- signatures + sign dates ------------------------------------------------------------------------------------------------------
    def sign_cell(role, sig, name_text, show_sig, show_date, date_iso):
        cell = []
        if show_sig:
            simg = _img_flow(sig["path"], 1.0 * cm, 4 * cm) if sig and sig.get("path") else None
            cell.append(simg if simg is not None else Spacer(1, 1.0 * cm))
            cell.append(Paragraph(f"{role}{(': ' + name_text) if name_text else ''}", ParagraphStyle("sg", parent=normal, alignment=TA_CENTER, borderPadding=0)))
        if show_date:
            cell.append(Paragraph(f"Date: {format_dmy(date_iso) if date_iso else ''}", ParagraphStyle("sd", parent=normal, alignment=TA_CENTER)))
        return cell
    tcell = sign_cell("Class Teacher", teacher_signature, data.get("teacher_name"), rs.get("show_teacher_signature", True), rs.get("show_teacher_sign_date", True), info.get("teacher_signed_date")) \
        if (rs.get("show_teacher_signature", True) or rs.get("show_teacher_sign_date", True)) else ""
    pcell = sign_cell("Principal", principal_signature, data.get("principal_name"), rs.get("show_principal_signature", True), rs.get("show_principal_sign_date", True), info.get("principal_signed_date")) \
        if (rs.get("show_principal_signature", True) or rs.get("show_principal_sign_date", True)) else ""
    if tcell or pcell:
        sg = Table([[tcell, pcell]], colWidths=[8.8 * cm, 8.8 * cm])
        sg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEABOVE", (0, 0), (0, 0), 0, colors.white)]))
        elements += [Spacer(1, 0.2 * cm), sg]

    scale = rs.get("grading_scale") or []
    if scale and (rs.get("show_grading_key", True) or template == "detailed_report"):
        key = "; ".join(f"{g['grade']} = {g['min_score']:g}-{g['max_score']:g} ({g['remark']})" for g in scale)
        elements += [Spacer(1, 0.2 * cm), Paragraph(f"<b>Grading key:</b> {key}", small)]
    if rs.get("footer"):
        elements += [Spacer(1, 0.15 * cm), Paragraph(str(rs["footer"]).replace("&", "&amp;"), small)]
    # No "Issued <date>" line exists anywhere: a date appears only as the explicit, saved Result Date above.
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
