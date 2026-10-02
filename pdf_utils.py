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


def _result_elements(data, term, school_name, logo_path, student_full_name, styles, accent_color="#1f3a5f",
                      name_align=None, teacher_signature=None, principal_signature=None):
    """Builds the flowable elements for one student's terminal result —
    shared by the single-student PDF and the whole-class PDF.
    teacher_signature/principal_signature, if given, are dicts with
    "path" (image file) and "name" (signer's name) — used only when that
    specific signer has uploaded a signature AND turned on automatic
    stamping; otherwise a blank line is left for a manual signature, exactly
    as before."""
    section_style = ParagraphStyle("section", parent=styles["Heading3"])
    regular = styles["Normal"].fontName
    bold = styles["Heading1"].fontName

    student = data["student"]
    class_row = data["class_row"]
    name = student_full_name(student) if student_full_name else f"{student['last_name']} {student['first_name']}"

    rs = data.get("rs") or {}
    accent_color = rs.get("accent") or accent_color
    template = rs.get("template", "classic")
    compact = template == "compact"
    elements = _header_elements(
        school_name, logo_path, (rs.get("title") or "Terminal Report Sheet").upper(),
        f"{term['session_name']} &mdash; {term['name']}",
        styles, accent_color=accent_color, name_align=name_align,
    )
    if rs.get("show_contact") and rs.get("contact"):
        elements.append(Paragraph(rs["contact"].replace("&", "&amp;"), ParagraphStyle(
            "contactLine", parent=styles["Normal"], alignment=TA_CENTER, fontSize=8, textColor=colors.grey)))
        elements.append(Spacer(1, 0.15 * cm))
    if data.get("result_date"):
        elements.append(Paragraph(f"Date: {data['result_date']}", ParagraphStyle(
            "resultDate", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9, textColor=colors.grey,
        )))
        elements.append(Spacer(1, 0.2 * cm))

    show_overall = rs.get("show_overall_position", True)
    show_subj_pos = bool(rs.get("show_subject_position", False))
    info_rows = [
        ["Name:", name, "Adm./Reg. No.:", student["admission_no"]],
        ["Class / Arm:", class_row["name"], "Session / Term:", f"{term['session_name']} / {term['name']}"],
        ["Total Score:", str(data["total"]), "Average:", str(data["average"])],
        ["No. of Subjects:", f"{data.get('subjects_written', '-')} of {len(data['subjects'])}",
         "Overall Position:" if show_overall else "", (f"{data.get('position_text', data['position'])} of {data['class_size']}") if show_overall else ""],
    ]
    info_table = Table(info_rows, colWidths=[3 * cm, 5 * cm, 3.5 * cm, 5.5 * cm])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTNAME", (0, 0), (0, -1), bold),
        ("FONTNAME", (2, 0), (2, -1), bold),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    passport_path = rs.get("passport_path")
    if passport_path and os.path.exists(passport_path):
        try:
            pp = Image(passport_path, width=2.4 * cm, height=3 * cm)
            wrapper = Table([[info_table, pp]], colWidths=[17 * cm, 2.6 * cm])
            wrapper.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            elements.append(wrapper)
        except Exception:
            elements.append(info_table)
    else:
        elements.append(info_table)
    elements.append(Spacer(1, 0.4 * cm if compact else 0.5 * cm))

    elements.append(Paragraph("Academic Performance", section_style))
    show_ca3 = bool(data.get("show_ca3"))
    with_remark = not compact
    subj_header = ["Subject", "CA1", "CA2"] + (["CA3"] if show_ca3 else []) + ["Exam", "Total", "Grade"] + (["Position"] if show_subj_pos else []) + (["Remark"] if with_remark else [])
    subj_data = [subj_header]
    for s in data["subjects"]:
        subj_data.append([s["name"], str(s["ca1"]), str(s["ca2"])] + ([str(s.get("ca3", "-"))] if show_ca3 else []) +
                          [str(s["exam"]), str(s["total"]), str(s["grade"])] + ([str(s.get("position_text", "-"))] if show_subj_pos else []) +
                          ([str(s["remark"])] if with_remark else []))
    n_num = 5 + (1 if show_ca3 else 0) + (1 if show_subj_pos else 0)
    name_w = 4.6 * cm
    rem_w = 2.8 * cm if with_remark else 0
    num_w = max(1.2 * cm, (18.4 * cm - name_w - rem_w) / n_num)
    subj_col_widths = [name_w] + [num_w] * n_num + ([rem_w] if with_remark else [])
    subj_table = Table(subj_data, repeatRows=1, colWidths=subj_col_widths)
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
    elements.append(Spacer(1, 0.5 * cm))

    groups = data.get("domain_groups")
    if groups is None and data.get("ratings"):
        groups = [{"label": "Psychomotor / Affective Skills", "items": [(r["name"], r["rating"]) for r in data["ratings"]]}]
    if groups:
        elements.append(Paragraph("Educational Domains (rated 1-5)", section_style))
        for g in groups:
            skill_data = [[g["label"], "Rating"]] + [[n, str(v)] for n, v in g["items"]]
            skill_table = Table(skill_data, colWidths=[12 * cm, 3 * cm], repeatRows=1)
            skill_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(accent_color)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), regular),
                ("FONTNAME", (0, 0), (-1, 0), bold),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5 if compact else 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ]))
            elements.append(skill_table)
            elements.append(Spacer(1, 0.25 * cm))
        elements.append(Spacer(1, 0.25 * cm))

    info = data["info"]
    elements.append(Paragraph("Attendance", section_style))
    promo = data.get("promotion_status")
    show_promo = bool(rs.get("show_promotion", True) and promo)
    att_table = Table([
        ["Days School Opened", "Days Present", "Days Absent"] + (["Promotion / Status"] if show_promo else []),
        [
            str(info["days_school_opened"]) if info else "-",
            str(info["days_present"]) if info else "-",
            str(info["days_absent"]) if info else "-",
        ] + ([str(promo)] if show_promo else []),
    ])
    att_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements.append(att_table)
    elements.append(Spacer(1, 0.5 * cm))

    normal = styles["Normal"]
    teacher_comment = info["teacher_comment"] if info and info["teacher_comment"] else "_" * 70
    elements.append(Paragraph(f"<b>Teacher's Comment:</b> {teacher_comment}", normal))
    elements.append(Spacer(1, 0.3 * cm))
    teacher_date = format_dmy(info["teacher_signed_date"]) if info and info["teacher_signed_date"] else "________________"
    if data.get("teacher_name") and data.get("show_form_teacher_name", True):
        elements.append(Paragraph(f"<b>Form Teacher:</b> {data['teacher_name']}", normal))
    if data.get("show_form_teacher_signature", True):
        if teacher_signature and teacher_signature.get("path") and os.path.exists(teacher_signature["path"]):
            try:
                from PIL import Image as PILImage
                with PILImage.open(teacher_signature["path"]) as im:
                    im.load(); w, h = im.size
                sig_h = 1.1 * cm; sig_w = sig_h * (w / h)
                elements.append(Image(teacher_signature["path"], width=sig_w, height=sig_h))
            except Exception:
                elements.append(Paragraph("Teacher's Signature: ________________________________", normal))
            elements.append(Paragraph(f"Date: {teacher_date}", normal))
        else:
            elements.append(Paragraph(f"Teacher's Signature: ________________________________&nbsp;&nbsp;&nbsp;&nbsp; Date: {teacher_date}", normal))
    elements.append(Spacer(1, 0.6 * cm))

    principal_comment = info["principal_comment"] if info and info["principal_comment"] else "_" * 70
    elements.append(Paragraph(f"<b>Principal's Comment:</b> {principal_comment}", normal))
    elements.append(Spacer(1, 0.3 * cm))
    principal_date = format_dmy(info["principal_signed_date"]) if info and info["principal_signed_date"] else "________________"
    if data.get("principal_name") and data.get("show_principal_name", True):
        elements.append(Paragraph(f"<b>Principal:</b> {data['principal_name']}", normal))
    if data.get("show_principal_signature", True):
        if principal_signature and principal_signature.get("path") and os.path.exists(principal_signature["path"]):
            try:
                from PIL import Image as PILImage
                with PILImage.open(principal_signature["path"]) as im:
                    im.load(); w, h = im.size
                sig_h = 1.1 * cm; sig_w = sig_h * (w / h)
                elements.append(Image(principal_signature["path"], width=sig_w, height=sig_h))
            except Exception:
                elements.append(Paragraph("Principal's Signature: ________________________________", normal))
            elements.append(Paragraph(f"Date: {principal_date}", normal))
        else:
            elements.append(Paragraph(f"Principal's Signature: ________________________________&nbsp;&nbsp;&nbsp;&nbsp; Date: {principal_date}", normal))

    small = ParagraphStyle("rsSmall", parent=normal, fontSize=7.5, textColor=colors.HexColor("#444444"))
    scale = rs.get("grading_scale") or []
    if scale and (rs.get("show_grading_key", True) or template == "detailed"):
        elements.append(Spacer(1, 0.3 * cm))
        key = "; ".join(f"{g['grade']} = {g['min_score']:g}-{g['max_score']:g} ({g['remark']})" for g in scale)
        elements.append(Paragraph(f"<b>Grading key:</b> {key}", small))
    footer_bits = [x for x in (rs.get("footer"), f"Issued {data['result_date']}" if data.get("result_date") else None) if x]
    if footer_bits:
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph(" &nbsp;|&nbsp; ".join(b.replace("&", "&amp;") for b in footer_bits), small))

    return elements


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
    doc.build(elements)
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
        elements.extend(_result_elements(data, term, school_name, logo_path, student_full_name, styles,
                                          accent_color=accent_color, name_align=name_align))
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
