"""ONE description of a result sheet, built once from (result data + Result Display Settings + permissions-resolved content).

The browser preview, the student/parent report, the print page and the PDF are all PAINTERS of this same model, so they cannot
disagree about what is shown: every toggle is evaluated here, exactly once."""

SCALE = [(1, "Poor"), (2, "Fair"), (3, "Good"), (4, "Very Good"), (5, "Excellent")]
SCALE_WORD = dict(SCALE)


def _s(v):
    return "" if v is None else str(v)


def build_sheet(data, term, full_name):
    rs = data["rs"]
    info = data.get("info") or {}
    student, cls = data["student"], data["class_row"]
    show_ca3 = bool(data.get("show_ca3"))

    header = {
        "logo_uri": rs.get("logo"), "logo_path": rs.get("logo_path"), "logo_align": rs.get("logo_align", "left"), "text_align": rs.get("text_align", "center"),
        "school_name": rs.get("school_name") or "", "motto": rs.get("tagline"), "address": rs.get("address"), "contact": rs.get("contact") or None,
        "title": rs.get("title") or "Terminal Report Sheet",
        "term_line": " — ".join(x for x in ((term["session_name"] if rs.get("show_session") else None), (term["name"] if rs.get("show_term") else None)) if x) or None,
    }

    identity = [("Name", full_name(student))]
    if rs.get("show_admission_no"):
        identity.append(("Admission No.", _s(student["admission_no"])))
    reg = student["register_no"] if "register_no" in student.keys() else None
    if rs.get("show_register_no") and reg:
        identity.append(("Register No.", _s(reg)))
    if rs.get("show_class"):
        identity.append(("Class / Arm", _s(cls["name"])))
    if rs.get("show_session"):
        identity.append(("Academic Session", _s(term["session_name"])))
    if rs.get("show_term"):
        identity.append(("Term", _s(term["name"])))
    if rs.get("show_total"):
        identity.append(("Total Score", _s(data["total"])))
    if rs.get("show_average"):
        identity.append(("Average", _s(data["average"])))
    identity.append(("Subjects", f"{data.get('subjects_written', '-')} of {len(data['subjects'])}"))
    if rs.get("show_overall_position"):
        identity.append(("Overall Position", f"{data.get('position_text', data.get('position'))} of {data.get('class_size')}"))
    if data.get("result_date"):
        identity.append(("Result Date", data["result_date"]))

    passport = {"uri": rs.get("passport"), "path": rs.get("passport_path")} if rs.get("show_passport") else None

    cols = [{"label": "Subject", "align": "l"}]
    if rs.get("show_score"):
        cols += [{"label": "CA1", "align": "c"}, {"label": "CA2", "align": "c"}] + ([{"label": "CA3", "align": "c"}] if show_ca3 else []) + [{"label": "Exam", "align": "c"}, {"label": "Total", "align": "c"}]
    if rs.get("show_grade"):
        cols.append({"label": "Grade", "align": "c"})
    if rs.get("show_subject_position"):
        cols.append({"label": "Position", "align": "c"})
    if rs.get("show_remarks"):
        cols.append({"label": "Remark", "align": "l"})
    if rs.get("show_subject_comment"):
        cols.append({"label": "Subject Teacher's Comment", "align": "l"})
    rows = []
    for s in data["subjects"]:
        r = [_s(s["name"])]
        if rs.get("show_score"):
            r += [_s(s["ca1"]), _s(s["ca2"])] + ([_s(s.get("ca3", "-"))] if show_ca3 else []) + [_s(s["exam"]), _s(s["total"])]
        if rs.get("show_grade"):
            r.append(_s(s["grade"]))
        if rs.get("show_subject_position"):
            r.append(_s(s.get("position_text", "-")))
        if rs.get("show_remarks"):
            r.append(_s(s["remark"]))
        if rs.get("show_subject_comment"):
            r.append(_s(s.get("comment")))
        rows.append(r)

    domains = None
    if rs.get("show_domains") and data.get("domain_groups"):
        groups = [{"label": g["label"], "items": [(n, _s(v), SCALE_WORD.get(int(v), "") if str(v).isdigit() else "") for n, v in g["items"]]} for g in data["domain_groups"]]
        domains = {"groups": groups, "legend": [(n, w) for n, w in SCALE] if rs.get("show_domain_legend") else None}

    attendance = []
    if rs.get("show_attendance"):
        dash = lambda v: "—" if v is None else str(v)
        if rs.get("show_days_opened"):
            attendance.append(("Days School Opened", dash(info.get("days_school_opened"))))
        if rs.get("show_days_present"):
            attendance.append(("Days Present", dash(info.get("days_present"))))
        if rs.get("show_days_absent"):
            attendance.append(("Days Absent", dash(info.get("days_absent"))))
    if rs.get("show_promotion") and data.get("promotion_status"):
        attendance.append(("Promotion / Status", data["promotion_status"]))

    custom = list(data.get("custom_result_fields") or []) if rs.get("show_custom_fields") else []

    comments = []
    if rs.get("show_teacher_comment"):
        comments.append(("Class/Form Teacher's Comment", info.get("teacher_comment") or ""))
    if rs.get("show_principal_comment"):
        comments.append(("Principal's Comment", info.get("principal_comment") or ""))

    def fmt(d):
        return data["format_date"](d) if (d and data.get("format_date")) else (d or "")
    sigs = []
    if rs.get("show_teacher_signature") or rs.get("show_teacher_sign_date"):
        sigs.append({"role": "Class Teacher", "name": data.get("teacher_name") if rs.get("show_teacher_signature") else None, "show_signature": rs.get("show_teacher_signature"),
                     "uri": rs.get("teacher_sig"), "path": rs.get("teacher_sig_path"), "show_date": rs.get("show_teacher_sign_date"), "date": fmt(info.get("teacher_signed_date"))})
    if rs.get("show_principal_signature") or rs.get("show_principal_sign_date"):
        pdate = info.get("principal_signed_date")
        if rs.get("principal_date_mode") == "auto" and data.get("published_date"):
            pdate = data["published_date"]
        sigs.append({"role": "Principal", "name": data.get("principal_name") if rs.get("show_principal_signature") else None, "show_signature": rs.get("show_principal_signature"),
                     "uri": rs.get("principal_sig"), "path": rs.get("principal_sig_path"), "show_date": rs.get("show_principal_sign_date"), "date": fmt(pdate)})

    scale = rs.get("grading_scale") or []
    key = None
    if scale and (rs.get("show_grading_key") or rs["template"] == "detailed_report"):
        key = "; ".join(f"{g['grade']} = {g['min_score']:g}-{g['max_score']:g} ({g['remark']})" for g in scale)

    return {"style": {"template": rs["template"], "accent": rs["accent"], "secondary": rs["secondary"], "font": rs.get("pdf_font", "Helvetica"),
                      "signature_layout": rs.get("signature_layout", "split"), "watermark": rs.get("watermark")},
            "header": header, "identity": identity, "passport": passport, "table": {"cols": cols, "rows": rows}, "domains": domains,
            "attendance": attendance, "custom": custom, "comments": comments, "signatures": sigs, "key": key, "footer": rs.get("footer") or None}
