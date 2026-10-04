"""V62: central Result Display Settings (+ live sample preview), dedicated broadsheet print, school custom information,
parent passports. Registered from app.py with register_v62_routes(app, helpers). School and tenant always come from
the signed-in session, never from the URL or a form."""
import datetime
import re
import sqlite3

from flask import abort, flash, redirect, render_template, request, send_from_directory, session, url_for

import profile_core as pc

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
HEADER_LAYOUTS = [("logo-left", "Logo left"), ("logo-center", "Logo centre"), ("logo-right", "Logo right"), ("no-logo", "No logo")]
SIGNATURE_LAYOUTS = [("split", "Teacher left, Principal right"), ("stacked", "Stacked"), ("right", "Right-aligned")]

# Section grouping for the settings page. Every key here is stored in result_display_settings, nowhere else.
SECTIONS = [
    ("Identity & header", ["show_logo", "show_passport", "show_contact", "show_watermark"]),
    ("Student details", ["show_admission_no", "show_class", "show_session", "show_term", "show_result_date"]),
    ("Scores", ["show_score", "show_grade", "show_remarks", "show_overall_position", "show_subject_position", "show_domains", "show_grading_key", "show_promotion"]),
    ("Attendance", ["show_attendance", "show_days_opened", "show_days_present", "show_days_absent"]),
    ("Comments & signatures", ["show_teacher_comment", "show_principal_comment", "show_teacher_signature", "show_teacher_sign_date",
                               "show_teacher_name", "show_principal_signature", "show_principal_sign_date", "show_principal_name"]),
]


def register_v62_routes(app, h):
    get_db = h["get_db"]
    login_required = h["login_required"]
    log_audit = h["log_audit"]
    RESULT_BOOL_SETTINGS = h["RESULT_BOOL_SETTINGS"]
    RESULT_TEMPLATES = h["RESULT_TEMPLATES"]
    get_result_display = h["get_result_display"]
    result_sheet_settings = h["result_sheet_settings"]
    student_full_name = h["student_full_name"]
    actor_role_label = h["_actor_role_label"]
    PDF_FONT_CHOICES = h["PDF_FONT_CHOICES"]
    PARENT_PHOTOS_DIR = h["PARENT_PHOTOS_DIR"]
    labels = {k: l for k, l, _d in RESULT_BOOL_SETTINGS}

    def sid():
        return session.get("school_id")

    def actor():
        return {"type": "staff", "id": session.get("user_id"), "name": session.get("name"), "role": actor_role_label(),
                "school_id": sid(), "tenant_id": session.get("tenant_id")}

    def ip():
        return (request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64].split(",")[0]).strip()

    # ===================================================================== RESULT DISPLAY SETTINGS (the one place)
    def sample_result(conn, cfg_rs):
        """Realistic fake data rendered through the SAME sheet component, so the preview always matches print/PDF."""
        school = conn.execute("SELECT * FROM schools WHERE id=?", (sid(),)).fetchone()
        subjects = [("Mathematics", 14, 13, 58), ("English Language", 12, 14, 55), ("Basic Science", 15, 12, 52), ("Social Studies", 11, 12, 49), ("Civic Education", 13, 15, 60)]
        details, tot_all = [], 0
        for i, (n, a, b, e) in enumerate(subjects, 1):
            total = a + b + e
            tot_all += total
            grade, remark = h["grade_for"](total, conn, sid())
            details.append({"name": n, "ca1": a, "ca2": b, "ca3": 0, "exam": e, "total": total, "grade": grade, "remark": remark,
                            "position": i, "position_text": h["ordinal_text"](i)})
        today = datetime.date.today()
        info = {"days_school_opened": 60, "days_present": 56, "days_absent": 4, "teacher_comment": "A focused and well-behaved pupil. Keep it up.",
                "principal_comment": "An excellent result. Congratulations.", "teacher_signed_date": today.isoformat(), "principal_signed_date": today.isoformat(),
                "promotion_status": "Promoted to the next class", "attendance_from": "register"}
        domain_groups = [{"label": "Affective Domain", "items": [("Punctuality", 5), ("Neatness", 4), ("Honesty", 5)]},
                         {"label": "Psychomotor Domain", "items": [("Handwriting", 4), ("Sports", 5)]}]
        student = {"first_name": "Sample", "last_name": "Student", "other_names": "", "admission_no": "ADM/001", "status": "Active"}
        term = {"name": "First Term", "session_name": "2025/2026"}
        rs = dict(cfg_rs)
        rs["passport"] = None
        rs["teacher_sig"] = None
        rs["principal_sig"] = None
        rs["grading_scale"] = conn.execute("SELECT grade,min_score,max_score,remark FROM grade_scale WHERE school_id=? ORDER BY min_score DESC", (sid(),)).fetchall()
        return dict(rs=rs, term=term, student=student, class_row={"name": "JSS 1A"}, subjects=details, total=tot_all, average=round(tot_all / len(details), 1),
                    position_text="1st", class_size=30, subjects_written=len(details), show_ca3=False, info=info, domain_groups=domain_groups,
                    promotion_status=info["promotion_status"], result_date=(today.strftime("%d/%m/%Y") if cfg_rs["show_result_date"] else None),
                    teacher_name=None, principal_name=None, student_full_name=lambda s: f"{s['last_name']} {s['first_name']}")

    @app.route("/admin/result-display-settings", methods=["GET", "POST"])
    @login_required("admin", "sub_admin")
    def result_display_settings():
        conn = get_db()
        try:
            cfg = get_result_display(conn, sid())
            school = conn.execute("SELECT * FROM schools WHERE id=?", (sid(),)).fetchone()
            errors = {}
            terms = h["all_terms_for_school"](conn)
            if request.method == "POST":
                f = request.form
                tmpl = f.get("template", "")
                if tmpl not in {t[0] for t in RESULT_TEMPLATES}:
                    errors["template"] = "Choose one of the available result sheet styles."
                prim, sec = (f.get("accent_color") or "").strip(), (f.get("secondary_color") or "").strip()
                if prim and not COLOR_RE.match(prim):
                    errors["accent_color"] = "Use a colour like #1f3a5f."
                if sec and not COLOR_RE.match(sec):
                    errors["secondary_color"] = "Use a colour like #c9a227."
                title = pc.clean(f.get("title"))[:80]
                footer = pc.clean_multiline(f.get("footer_text"))[:300]
                wm = pc.clean(f.get("watermark_text"))[:40]
                if any(c in (title + footer + wm) for c in "<>"):
                    errors["title"] = "Angle brackets are not allowed."
                layout = f.get("header_layout", "logo-left")
                sig = f.get("signature_layout", "split")
                if layout not in {x[0] for x in HEADER_LAYOUTS}:
                    errors["header_layout"] = "Choose a header arrangement."
                if sig not in {x[0] for x in SIGNATURE_LAYOUTS}:
                    errors["signature_layout"] = "Choose a signature placement."
                pdf_font = f.get("pdf_font", school["pdf_font"] or "Helvetica")
                if pdf_font not in PDF_FONT_CHOICES:
                    errors["pdf_font"] = "Choose one of the listed fonts."
                # Term-wide default result date
                term_dates = {}
                for t in terms:
                    raw = (f.get(f"term_result_date_{t['id']}") or "").strip()
                    if raw:
                        d = pc.parse_date(raw)
                        if not d:
                            errors[f"term_{t['id']}"] = f"Result date for {t['name']} is not a valid date."
                        else:
                            term_dates[t["id"]] = d.isoformat()
                    else:
                        term_dates[t["id"]] = None
                if not errors:
                    vals = {k: (1 if f.get(k) else 0) for k, _l, _d in RESULT_BOOL_SETTINGS}
                    vals.update(template=tmpl, title=title or None, footer_text=footer or None, watermark_text=wm or None,
                                accent_color=prim or None, secondary_color=sec or None, header_layout=layout, signature_layout=sig)
                    before = dict(cfg)
                    try:
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute("UPDATE result_display_settings SET " + ",".join(f"{k}=?" for k in vals) + ", updated_at=CURRENT_TIMESTAMP, updated_by=? WHERE school_id=?",
                                     [*vals.values(), session.get("name"), sid()])
                        conn.execute("UPDATE schools SET pdf_font=?, auto_teacher_comment=?, auto_principal_comment=? WHERE id=?",
                                     (pdf_font, 1 if f.get("auto_teacher_comment") else 0, 1 if f.get("auto_principal_comment") else 0, sid()))
                        for t in terms:
                            conn.execute("UPDATE terms SET result_date=? WHERE id=? AND session_id IN (SELECT id FROM sessions WHERE school_id=?)",
                                         (term_dates.get(t["id"]), t["id"], sid()))
                        ch = pc.diff(before, vals, list(vals))
                        if (school["pdf_font"] or "Helvetica") != pdf_font:
                            ch["pdf_font"] = [school["pdf_font"], pdf_font]
                        ch["term_result_dates"] = {str(k): v for k, v in term_dates.items() if v}
                        pc.audit(conn, actor(), "result_display_settings_changed", "school", sid(), ch, ip=ip())
                        conn.commit()
                        flash("Result Display Settings saved. They now apply to the preview, printed results and PDFs.", "success")
                        return redirect(url_for("result_display_settings"))
                    except Exception:
                        conn.rollback()
                        app.logger.exception("Result display settings save failed")
                        errors["_form"] = "The settings could not be saved. Please try again."
                cfg = {**cfg, **{k: (1 if f.get(k) else 0) for k, _l, _d in RESULT_BOOL_SETTINGS}, "template": tmpl, "title": title, "footer_text": footer,
                       "watermark_text": wm, "accent_color": prim, "secondary_color": sec, "header_layout": layout, "signature_layout": sig}
                school = {**dict(school), "pdf_font": pdf_font, "auto_teacher_comment": 1 if f.get("auto_teacher_comment") else 0,
                          "auto_principal_comment": 1 if f.get("auto_principal_comment") else 0}
            # live sample through the real sheet component
            preview_rs = result_sheet_settings(conn, sid())
            if request.method == "POST" and errors:
                preview = None
            else:
                preview = sample_result(conn, preview_rs)
            term_dates_now = {t["id"]: conn.execute("SELECT result_date FROM terms WHERE id=?", (t["id"],)).fetchone()[0] for t in terms}
            return render_template("result_display_settings.html", cfg=cfg, school=school, sections=SECTIONS, labels=labels, templates=RESULT_TEMPLATES,
                                   header_layouts=HEADER_LAYOUTS, signature_layouts=SIGNATURE_LAYOUTS, pdf_fonts=PDF_FONT_CHOICES, errors=errors,
                                   preview=preview, terms=terms, term_dates=term_dates_now), (422 if errors else 200)
        finally:
            conn.close()

    # Old URLs keep working but lead to the single settings page (no duplicate controls anywhere else).
    @app.route("/admin/result-settings")
    @login_required("admin", "sub_admin")
    def legacy_result_settings():
        return redirect(url_for("result_display_settings"))

    @app.route("/admin/result-design-preview")
    @login_required("admin", "sub_admin")
    def result_design_preview_v62():
        return redirect(url_for("result_display_settings") + "#preview")

    # ===================================================================== BROADSHEET PRINT
    @app.route("/broadsheet/<int:class_id>/print")
    @login_required()
    def broadsheet_print(class_id):
        conn = get_db()
        try:
            denied = h["require_class_result_access"](conn, class_id)
            if denied:
                return denied
            term = h["resolve_term"](conn, request.args.get("term_id", type=int))
            if not term:
                flash("No term set yet.", "error")
                return redirect(url_for("dashboard"))
            subjects, rows = h["build_broadsheet_data"](conn, class_id, term["id"])
            class_row = conn.execute("SELECT * FROM classes WHERE id=? AND school_id=?", (class_id, sid())).fetchone()
            if not class_row:
                abort(404)
            rs = result_sheet_settings(conn, sid())
            return render_template("broadsheet_print.html", subjects=subjects, rows=rows, class_row=class_row, term=term, rs=rs,
                                   student_full_name=student_full_name, autoprint=request.args.get("auto") == "1",
                                   pdf_url=url_for("broadsheet_pdf", class_id=class_id, term_id=term["id"]),
                                   back_url=url_for("broadsheet", class_id=class_id, term_id=term["id"]))
        finally:
            conn.close()

    # ===================================================================== SCHOOL CUSTOM INFORMATION
    @app.route("/admin/school-info", methods=["GET", "POST"])
    @login_required("admin", "sub_admin")
    def admin_school_info():
        conn = get_db()
        try:
            if request.method == "POST":
                act = request.form.get("action")
                label = pc.clean(request.form.get("label"))
                value = pc.clean_multiline(request.form.get("value"))[:500]
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    if act == "add":
                        if not 2 <= len(label) <= 60 or any(c in label + value for c in "<>"):
                            raise ValueError("Give the field a name of 2-60 characters (no < or >).")
                        order = conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM school_custom_info WHERE school_id=?", (sid(),)).fetchone()[0]
                        conn.execute("INSERT INTO school_custom_info(school_id,tenant_id,label,value,sort_order,created_by) VALUES(?,?,?,?,?,?)",
                                     (sid(), session.get("tenant_id"), label, value, order, session.get("name")))
                        pc.audit(conn, actor(), "school_info_added", "school_custom_info", label, {"label": label, "value": value}, ip=ip())
                        msg = "Field added."
                    elif act in ("update", "delete"):
                        row = conn.execute("SELECT * FROM school_custom_info WHERE id=? AND school_id=?", (request.form.get("info_id", type=int), sid())).fetchone()
                        if not row:
                            raise ValueError("That field was not found.")
                        if act == "delete":
                            conn.execute("DELETE FROM school_custom_info WHERE id=?", (row["id"],))
                            pc.audit(conn, actor(), "school_info_removed", "school_custom_info", row["label"], {"label": row["label"], "value": row["value"]}, ip=ip())
                            msg = "Field removed."
                        else:
                            if not 2 <= len(label) <= 60 or any(c in label + value for c in "<>"):
                                raise ValueError("Give the field a name of 2-60 characters (no < or >).")
                            conn.execute("UPDATE school_custom_info SET label=?, value=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (label, value, row["id"]))
                            pc.audit(conn, actor(), "school_info_updated", "school_custom_info", row["id"], pc.diff(row, {"label": label, "value": value}, ["label", "value"]), ip=ip())
                            msg = "Field updated."
                    else:
                        raise ValueError("Unknown action.")
                    conn.commit()
                    flash(msg, "success")
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), "error")
                except sqlite3.IntegrityError:
                    conn.rollback()
                    flash("A field with that name already exists.", "error")
                return redirect(url_for("admin_school_info"))
            rows = conn.execute("SELECT * FROM school_custom_info WHERE school_id=? ORDER BY sort_order, id", (sid(),)).fetchall()
        finally:
            conn.close()
        return render_template("admin_school_info.html", rows=rows)

    # ===================================================================== PASSPORT VISIBILITY (parents)
    @app.route("/admin/parents/<int:parent_id>")
    @login_required("admin", "sub_admin")
    def admin_parent_detail(parent_id):
        conn = get_db()
        try:
            p = conn.execute("SELECT * FROM parent_accounts WHERE id=? AND school_id=?", (parent_id, sid())).fetchone()
            if not p:
                abort(404)
            kids = conn.execute(
                "SELECT st.id, st.first_name, st.last_name, st.other_names, st.admission_no, c.name AS class_name FROM parent_students ps "
                "JOIN students st ON st.id=ps.student_id JOIN classes c ON c.id=st.class_id WHERE ps.parent_id=? AND ps.school_id=? AND ps.status='verified' AND c.school_id=?",
                (parent_id, sid(), sid())).fetchall()
        finally:
            conn.close()
        return render_template("admin_parent_detail.html", p=p, kids=kids, student_full_name=student_full_name)

    @app.route("/admin/parents/<int:parent_id>/photo")
    @login_required("admin", "sub_admin")
    def admin_parent_photo(parent_id):
        conn = get_db()
        try:
            p = conn.execute("SELECT photo_filename FROM parent_accounts WHERE id=? AND school_id=?", (parent_id, sid())).fetchone()
        finally:
            conn.close()
        if not p or not p["photo_filename"]:
            return "", 404
        return send_from_directory(PARENT_PHOTOS_DIR, p["photo_filename"])

    @app.route("/parent/profile", methods=["GET", "POST"])
    @h["parent_login_required"]
    def parent_self_profile():
        import os
        import uuid
        conn = get_db()
        try:
            p = conn.execute("SELECT * FROM parent_accounts WHERE id=? AND school_id=?", (session["parent_id"], sid())).fetchone()
            if not p:
                session.clear()
                return redirect(url_for("login"))
            error = None
            if request.method == "POST":
                blob, ext, error = pc.read_image_upload(request.files.get("photo"), pc.PASSPORT_MAX, "Passport photograph")
                if not error and blob is None and not request.form.get("remove_photo"):
                    error = "Choose a photograph to upload."
                if not error:
                    os.makedirs(PARENT_PHOTOS_DIR, exist_ok=True)
                    old = p["photo_filename"]
                    new_name = None
                    if blob is not None:
                        new_name = f"parent_{p['id']}_{uuid.uuid4().hex[:8]}.{ext}"
                        with open(os.path.join(PARENT_PHOTOS_DIR, new_name), "wb") as fh:
                            fh.write(blob)
                    conn.execute("UPDATE parent_accounts SET photo_filename=? WHERE id=? AND school_id=?", (new_name, p["id"], sid()))
                    conn.commit()
                    if old:
                        try:
                            os.remove(os.path.join(PARENT_PHOTOS_DIR, old))
                        except OSError:
                            pass
                    flash("Profile saved successfully.", "success")
                    return redirect(url_for("parent_self_profile"))
            return render_template("parent_profile_self.html", p=p, error=error), (422 if error else 200)
        finally:
            conn.close()

    @app.route("/parent/profile/photo")
    @h["parent_login_required"]
    def parent_self_photo():
        conn = get_db()
        try:
            p = conn.execute("SELECT photo_filename FROM parent_accounts WHERE id=? AND school_id=?", (session["parent_id"], sid())).fetchone()
        finally:
            conn.close()
        if not p or not p["photo_filename"]:
            return "", 404
        return send_from_directory(PARENT_PHOTOS_DIR, p["photo_filename"])
