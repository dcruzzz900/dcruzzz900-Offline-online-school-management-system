"""V64: Quick Actions, optional staff titles, automatic activation at 100% setup, student status indicators and the
student pages (attendance / timetable / subjects) and parent 'Contact School' page that the Quick Actions point to.

Quick Actions are SHORTCUTS: they only build links. Every target route still authorises the request on the backend.
"""
import datetime
import re

from flask import abort, flash, redirect, render_template, request, session, url_for

import v63_core as core

DEFAULT_TITLES = ["Mr.", "Mrs.", "Master", "Miss", "Dr.", "Prof."]
STATUS_BADGES = {   # accessible: the text is always shown, the symbol/colour only supports it
    "Active": ("🟢", "#1b5e20", "#e8f5e9"), "Suspended": ("🟠", "#8a4b00", "#fff3e0"), "Withdrawn": ("🔴", "#8e1b1b", "#fdecea"),
    "Transferred": ("🔵", "#0d47a1", "#e3f2fd"), "Graduated": ("🟣", "#4a148c", "#f3e5f5"), "Expelled": ("⛔", "#5d0000", "#fbe9e7"),
}
STATE_LABELS = {"available": "Available", "pending": "Pending", "completed": "Completed", "attention": "Requires Attention",
                "locked": "Locked", "unpublished": "Not Yet Published"}
REGISTRAR_ROLE = "Registrar / Admissions Officer"
CT_ROLE = "Class Teacher / Form Teacher"


def register_v64(app, h):
    get_db, login_required = h["get_db"], h["login_required"]
    current_school_id, current_term = h["current_school_id"], h["current_term"]
    log_audit = h["log_audit"]
    form_teacher_class_ids = h["form_teacher_class_ids"]
    active_role_assignments, canonical_rbac_role = h["active_role_assignments"], h["canonical_rbac_role"]
    student_full_name = h["student_full_name"]

    # ------------------------------------------------------------------ student status badge (text always shown)
    @app.template_filter("status_badge")
    def status_badge(value):
        from markupsafe import Markup, escape
        name = (value or "Active")
        icon, fg, bg = STATUS_BADGES.get(name, ("⚪", "#37474f", "#eceff1"))
        return Markup(f'<span class="status-badge" style="display:inline-flex;gap:.3rem;align-items:center;padding:.1rem .55rem;border-radius:999px;'
                      f'font-size:.8rem;font-weight:600;color:{fg};background:{bg};border:1px solid {fg}33"><span aria-hidden="true">{icon}</span>{escape(name)}</span>')

    @app.template_filter("staff_name")
    def staff_name(row, name=None):
        """'Dr. John James' — the title is optional."""
        try:
            title = (row["title"] or "").strip()
            nm = name or row["name"]
        except Exception:
            title, nm = "", name or ""
        return f"{title} {nm}".strip() if title else nm

    # ------------------------------------------------------------------ helpers
    def sid():
        return session.get("school_id")

    def staff_roles(conn):
        found = {canonical_rbac_role(a["role"]) for a in active_role_assignments(conn, session["user_id"], sid())}
        u = conn.execute("SELECT rbac_role FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if u and u["rbac_role"]:
            found.add(canonical_rbac_role(u["rbac_role"]))
        return found

    def act(key, label, icon, url, group, state="available", badge=None, hint=None):
        return {"key": key, "label": label, "icon": icon, "url": url, "group": group, "state": state,
                "state_label": STATE_LABELS.get(state, state), "badge": badge, "hint": hint}

    # ------------------------------------------------------------------ STAFF
    def staff_actions(conn):
        school_id, uid = sid(), session["user_id"]
        term = current_term(conn)
        roles = staff_roles(conn)
        is_admin = session.get("role") in ("admin", "sub_admin")
        acts, seen = [], set()

        def add(a):
            if a["key"] not in seen:
                seen.add(a["key"]); acts.append(a)

        assigned = conn.execute(
            "SELECT cs.class_id, cs.subject_id, c.name cname, s.name sname FROM class_subjects cs JOIN classes c ON c.id=cs.class_id "
            "JOIN subjects s ON s.id=cs.subject_id WHERE cs.teacher_id=? AND c.school_id=? AND s.school_id=? ORDER BY c.name, s.name",
            (uid, school_id, school_id)).fetchall()
        ft = list(form_teacher_class_ids(conn, uid) or [])
        today = core.school_today(conn, school_id)

        if assigned and not is_admin:
            pending = locked = 0
            first_pending = None
            for a in assigned:
                st = core.publication_status(conn, school_id, a["class_id"], term["id"]) if term else "draft"
                if st in core.LOCKED_STATES:
                    locked += 1
                    continue
                missing = 0
                if term:
                    missing = conn.execute(
                        "SELECT COUNT(*) c FROM students s WHERE s.class_id=? AND s.is_active=1 AND NOT EXISTS "
                        "(SELECT 1 FROM scores sc WHERE sc.student_id=s.id AND sc.subject_id=? AND sc.term_id=?)",
                        (a["class_id"], a["subject_id"], term["id"])).fetchone()["c"]
                if missing:
                    pending += 1
                    first_pending = first_pending or a
            target = first_pending or assigned[0]
            if pending:
                add(act("enter_scores", "Enter Scores", "✎", url_for("score_entry", class_id=target["class_id"], subject_id=target["subject_id"]),
                        "Scores", "pending", f"{pending} Class{'es' if pending != 1 else ''} Pending"))
            elif locked == len(assigned):
                add(act("enter_scores", "Enter Scores", "✎", url_for("my_class"), "Scores", "locked", "Submitted / published"))
            else:
                add(act("enter_scores", "Enter Scores", "✎", url_for("score_entry", class_id=target["class_id"], subject_id=target["subject_id"]),
                        "Scores", "completed", "All scores entered"))
            add(act("assigned_classes", "Assigned Classes", "▣", url_for("my_class"), "Scores", badge=f"{len(assigned)} assignment{'s' if len(assigned) != 1 else ''}"))
            add(act("view_scores", "View / Edit Scores", "▤", url_for("score_history_all"), "Scores"))
            if not ft:
                add(act("view_results", "View Results", "◧", url_for("classes_list"), "Results"))

        if ft:
            cid = ft[0]
            taken = conn.execute("SELECT 1 FROM attendance_records WHERE class_id=? AND date=? LIMIT 1", (cid, today)).fetchone() if term else None
            add(act("take_attendance", "Take Class Attendance", "✔", url_for("roll_call", class_id=cid), "Class",
                    "completed" if taken else "pending", "Today — Taken" if taken else "Today — Not Taken"))
            add(act("class_register", "Class Register", "☰", url_for("class_register", class_id=cid), "Class"))
            add(act("class_results", "Class Results", "◧", url_for("class_results_list", class_id=cid), "Results"))
            add(act("class_broadsheet", "Class Broadsheet", "▦", url_for("broadsheet", class_id=cid), "Results"))
            add(act("domains", "Educational Domains", "★", url_for("class_results_list", class_id=cid), "Results", hint="Open a student's result to rate domains"))
            add(act("ct_comments", "Class Teacher Comments", "✍", url_for("class_results_list", class_id=cid), "Results", hint="Open a student's result to write the comment"))
            st = core.publication_status(conn, school_id, cid, term["id"]) if term else "draft"
            add(act("submit_results", "Submit Results for Review", "⇪", url_for("result_workflow"), "Results",
                    "available" if st in ("draft", "returned", "reopened") else ("completed" if st == "published" else "locked"), core.STATE_LABELS.get(st, st)))

        if REGISTRAR_ROLE in roles or is_admin:
            add(act("register_student", "Register Student", "＋", url_for("registrar_dashboard"), "Admissions"))
            add(act("admission_number", "Admission Number", "#", url_for("registrar_dashboard"), "Admissions"))
            add(act("transfer_student", "Transfer Student", "⇄", url_for("registrar_dashboard"), "Admissions"))
            add(act("withdraw_student", "Withdraw Student", "⎋", url_for("registrar_dashboard"), "Admissions"))
            add(act("update_status", "Update Student Status", "◐", url_for("registrar_dashboard"), "Admissions"))

        if is_admin or conn.execute("SELECT 1 FROM result_workflow_permissions WHERE user_id=? AND granted=1 AND permission IN ('result.review','result.approve','result.publish','result.reopen') LIMIT 1", (uid,)).fetchone():
            n = conn.execute("SELECT COUNT(*) c FROM result_publication WHERE school_id=? AND term_id=? AND status IN ('submitted','under_review')",
                             (school_id, term["id"] if term else 0)).fetchone()["c"]
            ready = conn.execute("SELECT COUNT(*) c FROM result_publication WHERE school_id=? AND term_id=? AND status='approved'", (school_id, term["id"] if term else 0)).fetchone()["c"]
            add(act("review_results", "Results Awaiting Review", "✔", url_for("result_workflow"), "Results",
                    "attention" if n else ("pending" if ready else "available"), f"{n} Awaiting Review" if n else (f"{ready} Ready to Publish" if ready else None)))

        if is_admin:
            add(act("assign_subjects", "Assign Subjects", "◈", url_for("admin_class_subjects"), "Academics"))
            add(act("staff_attendance", "Staff Attendance", "☑", url_for("staff_attendance"), "Staff"))
            add(act("view_results", "View Results", "◧", url_for("classes_list"), "Results"))

        add(act("timetable", "View Timetable", "▥", url_for("timetable_hub"), "Daily"))
        add(act("materials", "Learning Materials", "▤", url_for("materials"), "Daily"))
        add(act("messages", "Messages", "✉", url_for("teacher_parent_messages"), "Daily"))
        add(act("notifications", "Notifications", "🔔", url_for("notifications_inbox"), "Daily"))
        add(act("my_profile", "My Profile", "☺", url_for("my_profile"), "Daily"))
        return acts, sorted(roles)

    # ------------------------------------------------------------------ STUDENT
    def student_actions(conn):
        student = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
        if not student:
            return []
        school_id = student["school_id"] if "school_id" in student.keys() and student["school_id"] else sid()
        published = conn.execute(
            "SELECT t.id, t.name FROM terms t JOIN enrollments e ON e.session_id=t.session_id WHERE e.student_id=? AND t.is_published=1 "
            "AND EXISTS (SELECT 1 FROM result_publication rp WHERE rp.term_id=t.id AND rp.status='published' AND rp.class_id=e.class_id) ORDER BY t.id DESC",
            (student["id"],)).fetchall()
        today = core.school_today(conn, sid())
        rec = conn.execute("SELECT COALESCE(detail_status,status) s FROM attendance_records WHERE student_id=? AND date=?", (student["id"], today)).fetchone()
        a = []
        if published:
            a.append(act("my_results", "My Results", "◧", url_for("student_result", term_id=published[0]["id"]), "Results", "available", f"{len(published)} published"))
            a.append(act("result_history", "Result History", "⟲", url_for("student_dashboard") + "#results", "Results"))
        else:
            a.append(act("my_results", "My Results", "◧", url_for("student_dashboard"), "Results", "unpublished", "Not Yet Published"))
            a.append(act("result_history", "Result History", "⟲", url_for("student_dashboard") + "#results", "Results", "unpublished", "Not Yet Published"))
        a += [act("my_attendance", "My Attendance", "✔", url_for("student_attendance"), "School", "available", f"Today — {rec['s'].title()}" if rec else None),
              act("my_timetable", "My Timetable", "▥", url_for("student_timetable"), "School"),
              act("my_subjects", "My Subjects", "▦", url_for("student_subjects"), "School"),
              act("materials", "Learning Materials", "▤", url_for("student_materials"), "School"),
              act("notifications", "Notifications", "🔔", url_for("student_notifications"), "Account"),
              act("my_profile", "My Profile", "☺", url_for("student_self_profile"), "Account"),
              act("update_profile", "Update Profile", "✎", url_for("student_self_profile"), "Account"),
              act("change_password", "Change Password", "⚿", url_for("student_account"), "Account")]
        return a

    # ------------------------------------------------------------------ PARENT
    def parent_children_list(conn):
        return h["parent_children"](conn, session["parent_id"])

    def parent_actions(conn, child_id):
        a = [act("my_children", "My Children", "☺", url_for("parent_children_page"), "Children")]
        if child_id:
            a += [act("child_results", "View Child Results", "◧", url_for("parent_child_detail", student_id=child_id), "Selected child"),
                  act("result_history", "Result History", "⟲", url_for("parent_child_detail", student_id=child_id), "Selected child"),
                  act("child_attendance", "Child Attendance", "✔", url_for("parent_attendance", student_id=child_id), "Selected child"),
                  act("child_timetable", "Child Timetable", "▥", url_for("parent_timetable", student_id=child_id), "Selected child"),
                  act("child_materials", "Learning Materials", "▤", url_for("parent_child_detail", student_id=child_id) + "#materials", "Selected child"),
                  act("messages", "Messages", "✉", url_for("parent_child_detail", student_id=child_id) + "#messages", "Selected child"),
                  act("child_profile", "Child Profile", "☺", url_for("parent_child_detail", student_id=child_id), "Selected child")]
        a += [act("notices", "School Notices", "📢", url_for("parent_notifications"), "School"),
              act("notifications", "Notifications", "🔔", url_for("parent_notifications"), "School"),
              act("contact_school", "Contact School", "☎", url_for("parent_contact_school"), "School"),
              act("parent_profile", "Parent Profile", "☺", url_for("parent_self_profile"), "Account"),
              act("change_password", "Change Password", "⚿", url_for("parent_self_profile"), "Account")]
        return a

    def quick_actions():
        """Used by partials/quick_actions.html. Returns {'audience','actions','roles','children','selected'}."""
        try:
            conn = get_db()
            try:
                if session.get("user_id"):
                    acts, roles = staff_actions(conn)
                    return {"audience": "staff", "actions": acts, "roles": roles, "children": [], "selected": None}
                if session.get("student_id"):
                    return {"audience": "student", "actions": student_actions(conn), "roles": [], "children": [], "selected": None}
                if session.get("parent_id"):
                    kids = parent_children_list(conn)
                    ids = {k["id"] for k in kids}
                    want = request.args.get("child", type=int)
                    selected = want if want in ids else (kids[0]["id"] if kids else None)   # only linked children can ever be selected
                    return {"audience": "parent", "actions": parent_actions(conn, selected), "roles": [],
                            "children": [{"id": k["id"], "name": f"{k['first_name']} {k['last_name']}"} for k in kids], "selected": selected}
            finally:
                conn.close()
        except Exception:
            app.logger.exception("Quick Actions failed")
        return {"audience": None, "actions": [], "roles": [], "children": [], "selected": None}

    app.jinja_env.globals["quick_actions"] = quick_actions

    # ------------------------------------------------------------------ student pages the Quick Actions need
    def student_required(fn):
        return h["student_login_required"](fn)

    @app.route("/student/attendance")
    @h["student_login_required"]
    def student_attendance():
        conn = get_db()
        st = conn.execute("SELECT * FROM students WHERE id=? ", (session["student_id"],)).fetchone()
        rows = conn.execute(
            "SELECT t.name term_name, se.name session_name, COUNT(ar.id) days, "
            "SUM(CASE WHEN ar.status='present' THEN 1 ELSE 0 END) present, SUM(CASE WHEN ar.status='absent' THEN 1 ELSE 0 END) absent, "
            "SUM(CASE WHEN ar.detail_status='late' THEN 1 ELSE 0 END) late, SUM(CASE WHEN ar.detail_status='excused' THEN 1 ELSE 0 END) excused "
            "FROM terms t JOIN sessions se ON se.id=t.session_id LEFT JOIN attendance_records ar ON ar.term_id=t.id AND ar.student_id=? "
            "GROUP BY t.id HAVING days>0 ORDER BY t.id DESC", (st["id"],)).fetchall()
        conn.close()
        return render_template("student_attendance.html", student=st, rows=rows)

    @app.route("/student/timetable")
    @h["student_login_required"]
    def student_timetable():
        conn = get_db()
        st = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
        school = conn.execute("SELECT COALESCE(tenant_id,CAST(id AS TEXT)) t FROM schools WHERE id=?", (sid(),)).fetchone()
        tenant = school["t"] if school else str(sid())
        version = conn.execute("SELECT * FROM timetable_versions_v2 WHERE school_id=? AND tenant_id=? AND status='PUBLISHED' ORDER BY id DESC LIMIT 1", (sid(), tenant)).fetchone()
        entries = []
        if version:
            entries = conn.execute(
                "SELECT te.*, ss.slot_name, ss.start_time, ss.end_time, s.name subject_name, u.name teacher_name, sd.day_name, sd.day_order "
                "FROM timetable_entries_v2 te JOIN schedule_slots ss ON ss.id=te.slot_id JOIN school_days_v2 sd ON sd.id=te.day_id "
                "JOIN subjects s ON s.id=te.subject_id LEFT JOIN users u ON u.id=te.teacher_id "
                "WHERE te.timetable_version_id=? AND te.class_id=? AND te.school_id=? ORDER BY sd.day_order, ss.start_time",
                (version["id"], st["class_id"], sid())).fetchall()
        conn.close()
        return render_template("student_timetable.html", student=st, entries=entries, version=version)

    @app.route("/student/subjects")
    @h["student_login_required"]
    def student_subjects():
        conn = get_db()
        st = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
        rows = conn.execute("SELECT s.name subject_name, u.name teacher_name, u.title teacher_title FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id "
                            "JOIN classes c ON c.id=cs.class_id LEFT JOIN users u ON u.id=cs.teacher_id WHERE cs.class_id=? AND c.school_id=? ORDER BY s.name",
                            (st["class_id"], sid())).fetchall()
        cls = conn.execute("SELECT * FROM classes WHERE id=?", (st["class_id"],)).fetchone()
        conn.close()
        return render_template("student_subjects.html", student=st, rows=rows, cls=cls)

    @app.route("/parent/contact-school")
    @h["parent_login_required"]
    def parent_contact_school():
        conn = get_db()
        school = h["get_school"](conn, sid())
        conn.close()
        return render_template("parent_contact_school.html", school=school)

    # ------------------------------------------------------------------ staff titles (optional)
    def titles_for(conn):
        extra = [r["name"] for r in conn.execute("SELECT name FROM school_staff_titles WHERE school_id=? ORDER BY name", (sid(),)).fetchall()]
        return DEFAULT_TITLES + [t for t in extra if t not in DEFAULT_TITLES]

    app.jinja_env.globals["staff_title_options"] = lambda: (lambda c: (titles_for(c), c.close())[0])(get_db())

    @app.route("/admin/staff/<int:user_id>/title", methods=["POST"])
    @login_required("admin", "sub_admin")
    def staff_set_title(user_id):
        conn = get_db()
        user = conn.execute("SELECT id, name, title FROM users WHERE id=? AND school_id=?", (user_id, sid())).fetchone()
        if not user:
            conn.close(); flash("Staff member not found.", "error"); return redirect(url_for("admin_teachers"))
        chosen = (request.form.get("title") or "").strip()
        custom = re.sub(r"\s+", " ", (request.form.get("custom_title") or "").strip())[:20]
        title = custom or chosen
        if custom and custom not in DEFAULT_TITLES:
            conn.execute("INSERT OR IGNORE INTO school_staff_titles(school_id,tenant_id,name) SELECT id,tenant_id,? FROM schools WHERE id=?", (custom, sid()))
        if title and title not in titles_for(conn):
            conn.close(); flash("Choose a listed title or add your own.", "error"); return redirect(url_for("staff_roles", user_id=user_id))
        conn.execute("UPDATE users SET title=? WHERE id=?", (title or None, user_id))
        log_audit(conn, session.get("role"), session.get("name"), "staff_title_changed", f"{user['name']}: {user['title'] or '—'} -> {title or '—'}", school_id=sid())
        conn.commit(); conn.close()
        flash("Title saved." if title else "Title removed (titles are optional).", "success")
        return redirect(url_for("staff_roles", user_id=user_id))

    # ------------------------------------------------------------------ setup at 100% => LIVE / ACTIVE automatically
    def auto_activate(conn, school_id):
        school = conn.execute("SELECT id, name, readiness_status FROM schools WHERE id=?", (school_id,)).fetchone()
        if not school or (school["readiness_status"] or "pending") == "ready":
            return False
        checks, ready = h["school_readiness_checks"](conn, school_id)
        if not ready:
            return False
        now = core.server_stamp()
        conn.execute("UPDATE schools SET readiness_status='ready', ready_at=?, ready_by=NULL, readiness_version=1, activation_status='active' WHERE id=?", (now, school_id))
        log_audit(conn, "system", "System", "school_auto_activated",
                  details=f"Setup reached 100% ({len(checks)}/{len(checks)} checks). School set to LIVE / ACTIVE automatically.", school_id=school_id)
        conn.execute("INSERT INTO notifications(sender_label,school_id,target_role,title,message) VALUES (?,?,?,?,?)",
                     ("System", school_id, "admin", "Your school is now LIVE",
                      "Setup reached 100%, so your school was activated automatically. Results can now be approved and published."))
        conn.commit()
        return True

    @app.after_request
    def _v64_auto_activate(resp):
        try:
            if not session.get("user_id") or session.get("role") not in ("admin", "sub_admin") or not session.get("school_id") or resp.status_code >= 400:
                return resp
            if request.method == "GET" and request.endpoint not in ("dashboard", "admin_setup_wizard"):
                return resp
            conn = get_db()
            try:
                auto_activate(conn, session["school_id"])
            finally:
                conn.close()
        except Exception:
            app.logger.exception("Automatic activation check failed")
        return resp

    h["auto_activate"] = auto_activate
