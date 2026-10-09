"""Registrar / Admissions Officer: register students, generate admission/register numbers, assign class/arm,
process transfer/withdrawal/suspension/graduation/expulsion, and maintain student status history. School and
tenant always come from the session; nothing here trusts an id supplied in the request."""
import re
import sqlite3

from flask import abort, flash, redirect, render_template, request, session, url_for

import profile_core as pc

STATUS_EVENTS = {
    "activate": ("Active", False),
    "suspend": ("Suspended", False),
    "withdraw": ("Withdrawn", True),
    "transfer": ("Transferred", True),
    "graduate": ("Graduated", True),
    "expel": ("Expelled", True),
}


def register_registrar_routes(app, h):
    get_db = h["get_db"]
    login_required = h["login_required"]
    current_school_id = h["current_school_id"]
    class_in_school = h["class_in_school"]
    student_in_school = h["student_in_school"]
    student_full_name = h["student_full_name"]
    actor_role_label = h["_actor_role_label"]
    ops_core = h["ops_core"]

    def is_registrar():
        if session.get("role") in ("admin", "sub_admin"):
            return True
        if session.get("role") != "teacher" or not session.get("user_id"):
            return False
        conn = get_db()
        try:
            return "Registrar / Admissions Officer" in ops_core.staff_roles(conn, session["user_id"], current_school_id())
        finally:
            conn.close()

    def guard():
        if not is_registrar():
            return render_template("profile_denied.html", message="Only the Registrar / Admissions Officer role (or the school administration) can use this page."), 403
        return None

    def actor():
        return {"type": "staff", "id": session.get("user_id"), "name": session.get("name"), "role": actor_role_label(),
                "school_id": current_school_id(), "tenant_id": session.get("tenant_id")}

    def ip():
        return (request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64].split(",")[0]).strip()

    def next_admission_no(conn, school_id):
        import datetime
        year = datetime.date.today().year
        prefix = f"{year}/"
        rows = conn.execute("SELECT admission_no FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? AND s.admission_no LIKE ?", (school_id, prefix + "%")).fetchall()
        used = set()
        for r in rows:
            m = re.fullmatch(re.escape(prefix) + r"(\d+)", r["admission_no"] or "")
            if m:
                used.add(int(m.group(1)))
        n = 1
        while n in used:
            n += 1
        return f"{prefix}{n:04d}"

    def next_register_no(conn, school_id, class_id):
        rows = conn.execute("SELECT register_no FROM students WHERE class_id=? AND register_no IS NOT NULL", (class_id,)).fetchall()
        used = {int(r["register_no"]) for r in rows if (r["register_no"] or "").isdigit()}
        n = 1
        while n in used:
            n += 1
        return str(n)

    def enabled_statuses(conn, school_id):
        return conn.execute("SELECT * FROM school_student_statuses WHERE school_id=? AND is_enabled=1 ORDER BY sort_order, id", (school_id,)).fetchall()

    def log_status(conn, school_id, student_id, prev, new, event, **extra):
        conn.execute(
            "INSERT INTO student_status_history(school_id,tenant_id,student_id,previous_status,new_status,event,effective_date,destination_school,previous_school,reason,"
            "from_class_id,to_class_id,changed_by,changed_by_name,changed_by_role) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (school_id, session.get("tenant_id"), student_id, prev, new, event, extra.get("effective_date"), extra.get("destination_school"),
             extra.get("previous_school"), extra.get("reason"), extra.get("from_class_id"), extra.get("to_class_id"), session.get("user_id"), session.get("name"), actor_role_label()))
        pc.audit(conn, actor(), f"student_{event}", "student", student_id, {"status": [prev, new], **{k: v for k, v in extra.items() if v}}, ip=ip())

    @app.route("/registrar")
    @login_required()
    def registrar_dashboard():
        denied = guard()
        if denied:
            return denied
        conn = get_db()
        try:
            sid = current_school_id()
            counts = {r["name"]: r["n"] for r in conn.execute(
                "SELECT COALESCE(status,'Active') AS name, COUNT(*) n FROM students st JOIN classes c ON c.id=st.class_id WHERE c.school_id=? GROUP BY 1", (sid,))}
            recent = conn.execute(
                "SELECT h.*, st.first_name, st.last_name, st.admission_no FROM student_status_history h JOIN students st ON st.id=h.student_id "
                "WHERE h.school_id=? ORDER BY h.id DESC LIMIT 25", (sid,)).fetchall()
            classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY level, name, arm", (sid,)).fetchall()
            statuses = enabled_statuses(conn, sid)
        finally:
            conn.close()
        return render_template("registrar_dashboard.html", counts=counts, recent=recent, classes=classes, statuses=statuses, student_full_name=student_full_name)

    @app.route("/registrar/admit", methods=["GET", "POST"])
    @login_required()
    def registrar_admit():
        denied = guard()
        if denied:
            return denied
        conn = get_db()
        try:
            sid = current_school_id()
            errors = {}
            form = {}
            if request.method == "POST":
                form = request.form.to_dict()
                first = pc.clean(request.form.get("first_name"))
                last = pc.clean(request.form.get("last_name"))
                other = pc.clean(request.form.get("other_names"))
                gender = request.form.get("gender", "")
                class_id = request.form.get("class_id", type=int)
                dob = request.form.get("date_of_birth", "").strip()
                admission_no = pc.clean(request.form.get("admission_no")) or None
                register_no = pc.clean(request.form.get("register_no")) or None
                admission_date = request.form.get("date_of_admission", "").strip()
                previous_school = pc.clean(request.form.get("previous_school"))
                notes = pc.clean_multiline(request.form.get("admission_notes"))[:500]
                parent_name = pc.clean(request.form.get("parent_name"))
                parent_phone = pc.clean(request.form.get("parent_phone"))
                if len(first) < 2:
                    errors["first_name"] = "First name is required."
                if len(last) < 2:
                    errors["last_name"] = "Surname is required."
                if gender not in ("M", "F"):
                    errors["gender"] = "Choose Male or Female."
                if not class_id or not class_in_school(conn, class_id):
                    errors["class_id"] = "Choose a class."
                if dob:
                    d = pc.parse_date(dob)
                    if not d:
                        errors["date_of_birth"] = "Enter a valid date."
                if admission_no and class_id:
                    if conn.execute("SELECT 1 FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? AND LOWER(TRIM(s.admission_no))=LOWER(?)", (sid, admission_no)).fetchone():
                        errors["admission_no"] = "That Admission No. is already used in this school."
                if not errors:
                    admission_no = admission_no or next_admission_no(conn, sid)
                    register_no = register_no or next_register_no(conn, sid, class_id)
                    try:
                        conn.execute("BEGIN IMMEDIATE")
                        cur = conn.execute(
                            "INSERT INTO students(school_id,tenant_id,admission_no,register_no,first_name,last_name,other_names,gender,class_id,date_of_birth,"
                            "date_of_admission,previous_school,admission_notes,parent_name,parent_phone,status,is_active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Active',1)",
                            (sid, session.get("tenant_id"), admission_no, register_no, first, last, other or None, gender, class_id, dob or None,
                             admission_date or None, previous_school or None, notes or None, parent_name or None, parent_phone or None))
                        sid_new = cur.lastrowid
                        log_status(conn, sid, sid_new, None, "Active", "admitted", previous_school=previous_school or None, effective_date=admission_date or None)
                        conn.commit()
                        flash(f"{last} {first} admitted with Admission No. {admission_no}.", "success")
                        return redirect(url_for("registrar_student", student_id=sid_new))
                    except sqlite3.IntegrityError:
                        conn.rollback()
                        errors["admission_no"] = "That Admission No. is already used in this school."
            classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY level, name, arm", (sid,)).fetchall()
            suggested_adm = next_admission_no(conn, sid)
        finally:
            conn.close()
        return render_template("registrar_admit.html", classes=classes, errors=errors, form=form, suggested_adm=suggested_adm), (422 if errors else 200)

    def student_or_404(conn, student_id):
        row = student_in_school(conn, student_id)
        if not row:
            abort(404)
        return row

    @app.route("/registrar/students/<int:student_id>")
    @login_required()
    def registrar_student(student_id):
        denied = guard()
        if denied:
            return denied
        conn = get_db()
        try:
            st = student_or_404(conn, student_id)
            history = conn.execute("SELECT * FROM student_status_history WHERE student_id=? AND school_id=? ORDER BY id DESC", (student_id, current_school_id())).fetchall()
            classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY level, name, arm", (current_school_id(),)).fetchall()
            statuses = enabled_statuses(conn, current_school_id())
        finally:
            conn.close()
        return render_template("registrar_student.html", st=st, history=history, classes=classes, statuses=statuses, student_full_name=student_full_name)

    @app.route("/registrar/students/<int:student_id>/status", methods=["POST"])
    @login_required()
    def registrar_status(student_id):
        denied = guard()
        if denied:
            return denied
        conn = get_db()
        try:
            st = student_or_404(conn, student_id)
            event = request.form.get("event")
            reason = pc.clean_multiline(request.form.get("reason"))[:400]
            if event not in STATUS_EVENTS:
                flash("Choose a valid action.", "error")
                return redirect(url_for("registrar_student", student_id=student_id))
            new_status, needs_reason = STATUS_EVENTS[event]
            if needs_reason and len(reason) < 5:
                flash(f"A reason is required to mark a student {new_status.lower()} (at least 5 characters).", "error")
                return redirect(url_for("registrar_student", student_id=student_id))
            dest = pc.clean(request.form.get("destination_school")) if event == "transfer" else None
            if event == "transfer" and not dest:
                flash("Enter the destination school for a transfer.", "error")
                return redirect(url_for("registrar_student", student_id=student_id))
            effective = request.form.get("effective_date", "").strip() or None
            if effective and not pc.parse_date(effective):
                flash("Enter a valid effective date.", "error")
                return redirect(url_for("registrar_student", student_id=student_id))
            prev = st["status"] or "Active"
            is_active = 1 if event == "activate" else 0
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("UPDATE students SET status=?, is_active=? WHERE id=? AND school_id=?", (new_status, is_active, student_id, current_school_id()))
                log_status(conn, current_school_id(), student_id, prev, new_status, event, reason=reason or None, destination_school=dest, effective_date=effective)
                conn.commit()
                flash(f"{student_full_name(st)} marked {new_status}.", "success")
            except Exception:
                conn.rollback()
                app.logger.exception("Student status change failed")
                flash("The status could not be changed. Please try again.", "error")
        finally:
            conn.close()
        return redirect(url_for("registrar_student", student_id=student_id))

    @app.route("/registrar/students/<int:student_id>/move-class", methods=["POST"])
    @login_required()
    def registrar_move_class(student_id):
        denied = guard()
        if denied:
            return denied
        conn = get_db()
        try:
            st = student_or_404(conn, student_id)
            new_class = request.form.get("class_id", type=int)
            if not new_class or not class_in_school(conn, new_class):
                flash("Choose a valid class.", "error")
                return redirect(url_for("registrar_student", student_id=student_id))
            if new_class == st["class_id"]:
                flash("The student is already in that class.", "error")
                return redirect(url_for("registrar_student", student_id=student_id))
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("UPDATE students SET class_id=? WHERE id=? AND school_id=?", (new_class, student_id, current_school_id()))
                log_status(conn, current_school_id(), student_id, st["status"] or "Active", st["status"] or "Active", "class_changed", from_class_id=st["class_id"], to_class_id=new_class)
                conn.commit()
                flash("Class/arm updated.", "success")
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("Admission No. clashes in the new class. Nothing was changed.", "error")
        finally:
            conn.close()
        return redirect(url_for("registrar_student", student_id=student_id))

    # ---------------------------------------------------------------- School Admin: configure student statuses
    @app.route("/admin/student-statuses", methods=["GET", "POST"])
    @login_required("admin", "sub_admin")
    def admin_student_statuses():
        conn = get_db()
        try:
            sid = current_school_id()
            if request.method == "POST":
                act = request.form.get("action")
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    if act == "add":
                        name = pc.clean(request.form.get("name"))
                        if not 2 <= len(name) <= 40:
                            raise ValueError("Status name must be 2-40 characters.")
                        order = conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM school_student_statuses WHERE school_id=?", (sid,)).fetchone()[0]
                        conn.execute("INSERT INTO school_student_statuses(school_id,tenant_id,name,counts_as_active,sort_order) VALUES(?,?,?,?,?)",
                                     (sid, session.get("tenant_id"), name, 1 if request.form.get("counts_as_active") else 0, order))
                    elif act == "toggle":
                        row = conn.execute("SELECT * FROM school_student_statuses WHERE id=? AND school_id=?", (request.form.get("status_id", type=int), sid)).fetchone()
                        if not row:
                            raise ValueError("Status not found.")
                        if row["is_builtin"] and row["name"] == "Active":
                            raise ValueError("The Active status cannot be disabled.")
                        conn.execute("UPDATE school_student_statuses SET is_enabled=? WHERE id=?", (0 if row["is_enabled"] else 1, row["id"]))
                    else:
                        raise ValueError("Unknown action.")
                    conn.commit()
                    flash("Saved.", "success")
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), "error")
                except sqlite3.IntegrityError:
                    conn.rollback()
                    flash("That status name already exists.", "error")
                return redirect(url_for("admin_student_statuses"))
            rows = conn.execute("SELECT * FROM school_student_statuses WHERE school_id=? ORDER BY sort_order, id", (sid,)).fetchall()
        finally:
            conn.close()
        return render_template("admin_student_statuses.html", rows=rows)
