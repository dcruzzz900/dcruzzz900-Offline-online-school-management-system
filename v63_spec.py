"""V63: functional-spec integration.

Registered from app.py with register_v63(app, helpers). The school/tenant is ALWAYS taken from the signed-in session,
never from a URL or a form field.

Contents
  1. Publication guard  - a before_request hook that rejects every print/PDF/download/export/e-mail endpoint (and the
                          student/parent portals) for a result or broadsheet that is not officially published.
  2. Approval workflow  - DRAFT > SUBMITTED > UNDER REVIEW > APPROVED > PUBLISHED, return-for-correction, reopen.
  3. Workflow permissions - explicit per-user grants (a title such as Principal never publishes on its own).
  4. Multiple staff roles - add/remove roles without replacing the others; permissions combine.
  5. Registrar / Admissions - dashboard, admission numbers, student status changes with a full history.
"""
import datetime
import re
import sqlite3

from flask import flash, g, redirect, render_template, request, session, url_for

import v63_core as core

STAFF_OUTPUT_PATTERNS = [
    (re.compile(r"^/result/(\d+)/(?:pdf|print|email)$"), "student"),
    (re.compile(r"^/cumulative/student/(\d+)/pdf$"), "student"),
    (re.compile(r"^/broadsheet/(\d+)/(?:pdf|print)$"), "class"),
    (re.compile(r"^/class/(\d+)/(?:results_pdf|email_results)$"), "class"),
]
STAFF_VIEW_PATTERNS = [
    (re.compile(r"^/result/(\d+)$"), "student"),
    (re.compile(r"^/broadsheet/(\d+)$"), "class"),
    (re.compile(r"^/class/(\d+)/results$"), "class"),
]
STUDENT_PORTAL = re.compile(r"^/student/result/(\d+)(?:/pdf|/print)?$")
PARENT_PORTAL = re.compile(r"^/parent/children/(\d+)/result/(\d+)(?:/pdf|/print)?$")

STUDENT_STATUSES = ["Active", "Suspended", "Withdrawn", "Transferred", "Graduated", "Expelled"]
KEEPS_ENROLLED = {"Active", "Suspended"}          # the others leave the class list (is_active = 0)
ADMIN_ONLY_ROLES = {"School Admin"}               # never selectable as an ordinary staff role
REGISTRAR_ROLE = "Registrar / Admissions Officer"
CLASS_TEACHER_ROLE = "Class Teacher / Form Teacher"


def register_v63(app, h):
    get_db = h["get_db"]
    login_required = h["login_required"]
    log_audit = h["log_audit"]
    current_school_id = h["current_school_id"]
    resolve_term = h["resolve_term"]
    student_class_for_term = h["student_class_for_term"]
    class_in_school = h["class_in_school"]
    form_teacher_class_ids = h["form_teacher_class_ids"]
    student_full_name = h["student_full_name"]
    actor_role_label = h["_actor_role_label"]
    ROLE_CATALOG = h["ROLE_CATALOG"]
    canonical_rbac_role = h["canonical_rbac_role"]
    active_role_assignments = h["active_role_assignments"]
    security_event = h["security_event"]

    # ------------------------------------------------------------------ small helpers
    def sid():
        return session.get("school_id")

    def tenant_of(conn, school_id):
        row = conn.execute("SELECT tenant_id FROM schools WHERE id=?", (school_id,)).fetchone()
        return row["tenant_id"] if row else None

    def roles_of(conn, user_id, school_id):
        """Every ACTIVE role the staff member holds right now (primary + additional), canonical names."""
        found = set()
        for ra in active_role_assignments(conn, user_id, school_id):
            found.add(canonical_rbac_role(ra["role"]))
        u = conn.execute("SELECT rbac_role FROM users WHERE id=? AND school_id=?", (user_id, school_id)).fetchone()
        if u and u["rbac_role"]:
            found.add(canonical_rbac_role(u["rbac_role"]))
        return found

    def is_school_admin():
        return session.get("role") == "admin"

    def is_admin_like():
        return session.get("role") in ("admin", "sub_admin")

    def client_ip():
        return (request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64].split(",")[0]).strip()

    def blocked(message, status=403):
        return render_template("result_blocked.html", message=message), status

    # ================================================================== 1. PUBLICATION GUARD
    def _student_row(conn, student_id, school_id):
        return conn.execute("SELECT s.id, s.class_id FROM students s JOIN classes c ON c.id=s.class_id WHERE s.id=? AND c.school_id=?",
                            (student_id, school_id)).fetchone()

    def _term_for_request(conn):
        term = resolve_term(conn, request.args.get("term_id", type=int))
        return term["id"] if term else None

    def _class_term_for(conn, kind, ident, term_id, school_id):
        if kind == "class":
            row = conn.execute("SELECT id FROM classes WHERE id=? AND school_id=?", (ident, school_id)).fetchone()
            return (row["id"], term_id) if row else (None, term_id)
        st = _student_row(conn, ident, school_id)
        if not st:
            return None, term_id
        return student_class_for_term(conn, ident, term_id) or st["class_id"], term_id

    @app.before_request
    def _v63_publication_guard():
        path = request.path
        if request.endpoint == "static" or path.startswith("/static/"):
            return None
        school_id = session.get("school_id")
        if not school_id:
            return None
        target = None            # (kind, ident, term_id or None)
        portal = False
        m = STUDENT_PORTAL.match(path)
        if m and session.get("student_id"):
            target, portal = ("student", session["student_id"], int(m.group(1))), True
        m = PARENT_PORTAL.match(path)
        if m and session.get("parent_id"):
            target, portal = ("student", int(m.group(1)), int(m.group(2))), True
        if target is None and session.get("user_id"):
            for pattern, kind in STAFF_OUTPUT_PATTERNS:
                m = pattern.match(path)
                if m:
                    target = (kind, int(m.group(1)), None)
                    break
            if target is None and path in ("/reports", "/reports/broadsheet") and request.args.get("class_id", type=int):
                target = ("class", request.args.get("class_id", type=int), None)
        if target is None:
            return None
        conn = get_db()
        try:
            kind, ident, term_id = target
            if term_id is None:
                term_id = _term_for_request(conn)
            if term_id is None:
                return None          # the route reports "no term" itself
            class_id, term_id = _class_term_for(conn, kind, ident, term_id, school_id)
            if class_id is None:
                return None          # not in this school: the route answers "not found"; nothing leaks
            if core.is_published(conn, school_id, class_id, term_id):
                return None
            status = core.publication_status(conn, school_id, class_id, term_id)
            try:
                security_event(conn, "UNPUBLISHED_OUTPUT_BLOCKED", "blocked", f"path={path} class={class_id} term={term_id} status={status}",
                               "result", class_id)
                conn.commit()
            except Exception:
                pass
            if portal:
                return blocked("These results have not been published yet. They will appear here as soon as your school publishes them.")
            return blocked("This result is not published. Unpublished results can be viewed or previewed by authorised staff only - "
                           "printing, downloading, PDF generation, e-mailing and export are blocked until it is officially published.")
        finally:
            conn.close()

    @app.after_request
    def _v63_unpublished_banner(resp):
        """Authorised staff may preview unpublished results; mark the page and neutralise browser printing."""
        try:
            if request.method != "GET" or resp.status_code != 200 or not session.get("user_id") or not session.get("school_id"):
                return resp
            if not (resp.mimetype or "").startswith("text/html"):
                return resp
            target = None
            for pattern, kind in STAFF_VIEW_PATTERNS:
                m = pattern.match(request.path)
                if m:
                    target = (kind, int(m.group(1)))
                    break
            if not target:
                return resp
            conn = get_db()
            try:
                term_id = _term_for_request(conn)
                if term_id is None:
                    return resp
                class_id, term_id = _class_term_for(conn, target[0], target[1], term_id, session["school_id"])
                if class_id is None or core.is_published(conn, session["school_id"], class_id, term_id):
                    return resp
                status = core.publication_status(conn, session["school_id"], class_id, term_id)
            finally:
                conn.close()
            html = resp.get_data(as_text=True)
            banner = (
                '<style id="v63-unpublished-print">@media print{html,body{display:none!important}}</style>'
                '<div class="no-print" role="status" style="position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#7c2d12;color:#fff;'
                'padding:.55rem 1rem;font-size:.9rem;text-align:center">'
                f'{core.STATE_LABELS.get(status, status)} &mdash; preview only. Printing, download and PDF are blocked until the result is officially published.</div>')
            if "</body>" in html:
                resp.set_data(html.replace("</body>", banner + "</body>", 1))
        except Exception:
            app.logger.exception("Could not add the unpublished banner")
        return resp

    @app.context_processor
    def _v63_context():
        """pub_state for result pages (buttons are only an aid - the guard above is the real control) + school clock."""
        out = {"pub_state": None, "school_now_label": None, "my_roles": [], "server_now_ms": int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)}
        school_id = session.get("school_id")
        if not school_id or request.endpoint in (None, "static"):
            return out
        try:
            conn = get_db()
            try:
                out["school_now_label"] = core.friendly_now(conn, school_id)
                if session.get("user_id"):
                    out["my_roles"] = sorted(roles_of(conn, session["user_id"], school_id))
                for pattern, kind in STAFF_VIEW_PATTERNS:
                    m = pattern.match(request.path)
                    if m and session.get("user_id"):
                        term_id = _term_for_request(conn)
                        class_id, term_id = _class_term_for(conn, kind, int(m.group(1)), term_id, school_id) if term_id else (None, None)
                        if class_id:
                            st = core.publication_status(conn, school_id, class_id, term_id)
                            out["pub_state"] = {"status": st, "published": st == "published", "label": core.STATE_LABELS.get(st, st)}
                        break
            finally:
                conn.close()
        except Exception:
            app.logger.exception("v63 context failed")
        return out

    # ================================================================== 2. APPROVAL WORKFLOW
    def can_do(conn, user_id, school_id, action, class_id):
        allowed_from, _new, perms, _need_reason = core.TRANSITIONS[action]
        if perms is None:   # submit: explicit grant, or the class's own Class/Form Teacher
            return (core.has_workflow_permission(conn, user_id, "result.submit")
                    or class_id in form_teacher_class_ids(conn, user_id))
        return any(core.has_workflow_permission(conn, user_id, p) for p in perms)

    def seed_admin_permissions(conn, school_id):
        """A School Admin starts with every workflow permission as an explicit, revocable grant (never re-seeded once changed)."""
        if not is_school_admin():
            return
        tenant = tenant_of(conn, school_id)
        for perm in core.PERMISSIONS:
            conn.execute("INSERT OR IGNORE INTO result_workflow_permissions(school_id,tenant_id,user_id,permission,granted) VALUES (?,?,?,?,1)",
                         (school_id, tenant, session["user_id"], perm))
        conn.commit()

    def submission_problems(conn, school_id, class_id, term_id):
        """Required-data checks before a result may be submitted: scores present, within range, totals and grades valid."""
        cfg = h["get_grading_config"](conn)
        students = conn.execute("SELECT id, first_name, last_name, other_names FROM students WHERE class_id=? AND is_active=1 ORDER BY last_name",
                                (class_id,)).fetchall()
        subjects = conn.execute("SELECT cs.subject_id, s.name FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id "
                                "WHERE cs.class_id=? AND s.school_id=?", (class_id, school_id)).fetchall()
        problems = []
        if not students:
            problems.append("The class has no active students.")
        if not subjects:
            problems.append("No subjects are assigned to this class.")
        for st in students:
            name = student_full_name(st)
            for sub in subjects:
                row = conn.execute("SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?",
                                   (st["id"], sub["subject_id"], term_id)).fetchone()
                if row is None:
                    problems.append(f"{name}: no {sub['name']} score entered.")
                    continue
                ca1, ca2, ca3, exam = (row["ca1"] or 0), (row["ca2"] or 0), (row["ca3"] or 0), (row["exam"] or 0)
                for msg in h["score_range_errors"](cfg, ca1, ca2, ca3, exam):
                    problems.append(f"{name} - {sub['name']}: {msg}.")
                total = h["compute_total"](ca1, ca2, exam, ca3)
                if total is None or total < 0:
                    problems.append(f"{name} - {sub['name']}: total is invalid.")
                else:
                    grade = h["grade_for"](total, conn, school_id)
                    if not grade or not grade[0]:
                        problems.append(f"{name} - {sub['name']}: no grade matches a total of {total:g}.")
        return problems

    def review_summary(conn, school_id, class_id, term_id):
        """What the reviewer verifies besides scores: attendance, comments, domains, student status."""
        students = conn.execute("SELECT id FROM students WHERE class_id=? AND is_active=1", (class_id,)).fetchall()
        n = len(students)
        att = com_t = com_p = dom = 0
        for st in students:
            info = conn.execute("SELECT * FROM student_term_info WHERE student_id=? AND term_id=?", (st["id"], term_id)).fetchone()
            if info:
                att += 1 if (info["days_school_opened"] or 0) > 0 else 0
                keys = info.keys()
                com_t += 1 if ("teacher_comment" in keys and (info["teacher_comment"] or "").strip()) else 0
                com_p += 1 if ("principal_comment" in keys and (info["principal_comment"] or "").strip()) else 0
            dom += 1 if conn.execute("SELECT 1 FROM student_skill_ratings WHERE student_id=? AND term_id=? LIMIT 1", (st["id"], term_id)).fetchone() else 0
        inactive = conn.execute("SELECT COUNT(*) c FROM students WHERE class_id=? AND status NOT IN ('Active','Suspended')", (class_id,)).fetchone()["c"]
        return {"students": n, "with_attendance": att, "with_teacher_comment": com_t, "with_principal_comment": com_p,
                "with_domains": dom, "other_status_students": inactive}

    def transition(conn, class_id, term_id, action, reason):
        school_id = sid()
        allowed_from, new_status, _perms, need_reason = core.TRANSITIONS[action]
        row = core.get_publication(conn, school_id, class_id, term_id)
        current = row["status"] if row else "draft"
        if current not in allowed_from:
            return False, f"A result that is '{core.STATE_LABELS.get(current, current)}' cannot be moved with '{action.replace('_', ' ')}'."
        if not can_do(conn, session["user_id"], school_id, action, class_id):
            return False, "You do not have permission for this step."
        reason = (reason or "").strip()[:500]
        if need_reason and not reason:
            return False, "A reason is mandatory for this step."
        if action == "submit":
            problems = submission_problems(conn, school_id, class_id, term_id)
            if problems:
                shown = " ".join(problems[:6]) + (f" (+{len(problems) - 6} more)" if len(problems) > 6 else "")
                return False, "Cannot submit yet. " + shown
        if action == "publish":
            ready = conn.execute("SELECT readiness_status FROM schools WHERE id=?", (school_id,)).fetchone()
            if not ready or ready["readiness_status"] != "ready":
                return False, "This school is not READY FOR LIVE DATA. Complete the Setup Wizard before publishing results."
        now = core.server_stamp()
        tenant = tenant_of(conn, school_id)
        uid = session["user_id"]
        if row is None:
            conn.execute("INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status) VALUES (?,?,?,?, 'draft')",
                         (school_id, tenant, class_id, term_id))
        sets, vals = ["status=?", "last_reason=?", "updated_by=?", "updated_at=?"], [new_status, reason or None, uid, now]
        if action == "submit":
            sets += ["submitted_by=?", "submitted_at=?"]; vals += [uid, now]
        elif action in ("start_review", "return"):
            sets += ["reviewed_by=?", "reviewed_at=?"]; vals += [uid, now]
        elif action == "approve":
            sets += ["approved_by=?", "approved_at=?"]; vals += [uid, now]
        elif action == "publish":
            sets += ["published_by=?", "published_at=?"]; vals += [uid, now]
        conn.execute(f"UPDATE result_publication SET {', '.join(sets)} WHERE school_id=? AND class_id=? AND term_id=?",
                     (*vals, school_id, class_id, term_id))
        pub = core.get_publication(conn, school_id, class_id, term_id)
        conn.execute(
            "INSERT INTO result_publication_audit(school_id,tenant_id,publication_id,class_id,term_id,action,previous_status,new_status,"
            "actor_id,actor_name,actor_role,reason,event_date,server_timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (school_id, tenant, pub["id"], class_id, term_id, action, current, new_status, uid, session.get("name"),
             actor_role_label(), reason or None, core.school_today(conn, school_id), now))
        flipped = False
        if action in ("publish", "reopen"):
            flipped = core.sync_term_flag(conn, school_id, term_id)
        cls = class_in_school(conn, class_id)
        conn.execute("INSERT INTO notifications(sender_label,school_id,target_role,title,message) VALUES (?,?,?,?,?)",
                     (session.get("name", "System"), school_id, "admin", "Result workflow",
                      f"{cls['name'] if cls else 'Class'}: {core.STATE_LABELS[current]} -> {core.STATE_LABELS[new_status]}"
                      + (f" ({reason})" if reason else "")))
        log_audit(conn, session.get("role"), session.get("name"), f"result_{action}",
                  f"class {class_id} term {term_id}: {current} -> {new_status}" + (f" | {reason}" if reason else ""), school_id=school_id)
        conn.commit()
        if flipped:
            try:
                msg = h["AUTO_ADVANCE"](conn, int(term_id))
                conn.commit()
                if msg:
                    flash(msg, "success")
            except Exception:
                app.logger.exception("Automatic next term/session creation failed")
        return True, f"{cls['name'] if cls else 'Class'}: now {core.STATE_LABELS[new_status]}."

    @app.route("/results/workflow")
    @login_required()
    def result_workflow():
        conn = get_db()
        school_id = sid()
        seed_admin_permissions(conn, school_id)
        uid = session["user_id"]
        term = resolve_term(conn, request.args.get("term_id", type=int))
        if not term:
            conn.close(); flash("No term set yet.", "error"); return redirect(url_for("dashboard"))
        perms = {p: core.has_workflow_permission(conn, uid, p) for p in core.PERMISSIONS}
        own = set(form_teacher_class_ids(conn, uid) or [])
        if not (any(perms.values()) or own or is_admin_like()):
            conn.close(); flash("You do not have access to the result approval workflow.", "error"); return redirect(url_for("dashboard"))
        all_classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
        broad = any(perms[p] for p in ("result.review", "result.approve", "result.publish", "result.reopen")) or is_admin_like()
        rows = []
        for c in all_classes:
            if not broad and c["id"] not in own:
                continue
            pub = core.get_publication(conn, school_id, c["id"], term["id"])
            status = pub["status"] if pub else "draft"
            actions = [a for a, (frm, _n, _p, _r) in core.TRANSITIONS.items() if status in frm and can_do(conn, uid, school_id, a, c["id"])]
            summary = review_summary(conn, school_id, c["id"], term["id"]) if status in ("submitted", "under_review", "approved") else None
            rows.append({"cls": c, "status": status, "label": core.STATE_LABELS[status], "pub": pub, "actions": actions, "summary": summary,
                         "students": conn.execute("SELECT COUNT(*) c FROM students WHERE class_id=? AND is_active=1", (c["id"],)).fetchone()["c"]})
        terms = h["all_terms_for_school"](conn)
        conn.close()
        return render_template("result_workflow.html", rows=rows, term=term, terms=terms, need_reason={a: v[3] for a, v in core.TRANSITIONS.items()},
                               action_labels={"submit": "Submit for review", "start_review": "Start review", "approve": "Approve", "return": "Return for correction",
                                              "publish": "Publish", "reopen": "Reopen / unpublish"})

    @app.route("/results/workflow/<int:class_id>/<int:term_id>/<action>", methods=["POST"])
    @login_required()
    def result_workflow_action(class_id, term_id, action):
        if action not in core.TRANSITIONS:
            flash("Unknown workflow step.", "error"); return redirect(url_for("result_workflow"))
        conn = get_db()
        school_id = sid()
        term_ok = conn.execute("SELECT t.id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE t.id=? AND s.school_id=?", (term_id, school_id)).fetchone()
        if not class_in_school(conn, class_id) or not term_ok:
            conn.close(); flash("Class or term not found.", "error"); return redirect(url_for("result_workflow"))
        ok, msg = transition(conn, class_id, term_id, action, request.form.get("reason"))
        conn.close()
        flash(msg, "success" if ok else "error")
        return redirect(url_for("result_workflow", term_id=term_id))

    @app.route("/results/workflow/<int:class_id>/<int:term_id>/history")
    @login_required()
    def result_workflow_history(class_id, term_id):
        conn = get_db()
        school_id = sid()
        cls = class_in_school(conn, class_id)
        uid = session["user_id"]
        allowed = is_admin_like() or any(core.has_workflow_permission(conn, uid, p) for p in core.PERMISSIONS) or class_id in (form_teacher_class_ids(conn, uid) or [])
        if not cls or not allowed:
            conn.close(); flash("You do not have access to that history.", "error"); return redirect(url_for("dashboard"))
        rows = conn.execute("SELECT * FROM result_publication_audit WHERE school_id=? AND class_id=? AND term_id=? ORDER BY id DESC",
                            (school_id, class_id, term_id)).fetchall()
        conn.close()
        return render_template("result_workflow_history.html", rows=rows, cls=cls, term_id=term_id, labels=core.STATE_LABELS)

    # ================================================================== 3. WORKFLOW PERMISSIONS (School Admin only)
    @app.route("/admin/result-permissions", methods=["GET", "POST"])
    @login_required("admin")
    def result_permissions():
        conn = get_db()
        school_id = sid()
        seed_admin_permissions(conn, school_id)
        staff = conn.execute("SELECT id,name,username,role,rbac_role FROM users WHERE school_id=? AND COALESCE(is_active,1)=1 ORDER BY name", (school_id,)).fetchall()
        if request.method == "POST":
            tenant = tenant_of(conn, school_id)
            changes = []
            for u in staff:
                for perm in core.PERMISSIONS:
                    want = 1 if request.form.get(f"p_{u['id']}_{perm}") else 0
                    cur = conn.execute("SELECT granted FROM result_workflow_permissions WHERE user_id=? AND permission=?", (u["id"], perm)).fetchone()
                    if (cur["granted"] if cur else 0) == want:
                        continue
                    conn.execute("INSERT INTO result_workflow_permissions(school_id,tenant_id,user_id,permission,granted,changed_by,changed_at) VALUES (?,?,?,?,?,?,?) "
                                 "ON CONFLICT(user_id,permission) DO UPDATE SET granted=excluded.granted, changed_by=excluded.changed_by, changed_at=excluded.changed_at",
                                 (school_id, tenant, u["id"], perm, want, session["user_id"], core.server_stamp()))
                    changes.append(f"{u['name']}: {perm} {'granted' if want else 'removed'}")
            if changes:
                log_audit(conn, session.get("role"), session.get("name"), "result_permissions_changed", "; ".join(changes)[:1500], school_id=school_id)
                conn.commit()
            flash(f"{len(changes)} permission change(s) saved." if changes else "No changes.", "success")
            conn.close()
            return redirect(url_for("result_permissions"))
        grants = {(r["user_id"], r["permission"]): r["granted"] for r in conn.execute(
            "SELECT user_id,permission,granted FROM result_workflow_permissions WHERE school_id=?", (school_id,)).fetchall()}
        conn.close()
        return render_template("result_permissions.html", staff=staff, perms=core.PERMISSIONS, grants=grants)

    # ================================================================== 4. MULTIPLE STAFF ROLES
    def assignable_staff_roles():
        return [r for r in h["assignable_roles"]() if r not in ADMIN_ONLY_ROLES]

    @app.route("/admin/staff/<int:user_id>/roles", methods=["GET", "POST"])
    @login_required("admin", "sub_admin")
    def staff_roles(user_id):
        conn = get_db()
        school_id = sid()
        user = conn.execute("SELECT * FROM users WHERE id=? AND school_id=?", (user_id, school_id)).fetchone()
        if not user or user["role"] == "admin":
            conn.close(); flash("Staff member not found.", "error"); return redirect(url_for("admin_teachers"))
        if request.method == "POST":
            action = request.form.get("action")
            tenant = tenant_of(conn, school_id)
            if action == "add":
                role = request.form.get("role", "").strip()
                if role in ADMIN_ONLY_ROLES or role not in ROLE_CATALOG or role not in assignable_staff_roles():
                    conn.close(); flash("That role cannot be assigned to staff.", "error"); return redirect(url_for("staff_roles", user_id=user_id))
                class_id = request.form.get("class_id", type=int)
                subject_id = request.form.get("subject_id", type=int)
                if class_id and not class_in_school(conn, class_id):
                    conn.close(); flash("Class not found.", "error"); return redirect(url_for("staff_roles", user_id=user_id))
                if subject_id and not conn.execute("SELECT 1 FROM subjects WHERE id=? AND school_id=?", (subject_id, school_id)).fetchone():
                    conn.close(); flash("Subject not found.", "error"); return redirect(url_for("staff_roles", user_id=user_id))
                dup = conn.execute("SELECT id FROM role_assignments WHERE user_id=? AND school_id=? AND status='active' AND role=? AND COALESCE(class_id,0)=? AND COALESCE(subject_id,0)=?",
                                   (user_id, school_id, role, class_id or 0, subject_id or 0)).fetchone()
                if dup:
                    conn.close(); flash("The staff member already holds that role.", "error"); return redirect(url_for("staff_roles", user_id=user_id))
                aid = conn.execute(
                    "INSERT INTO role_assignments(user_id,school_id,tenant_id,school_level,role,class_id,subject_id,status,requested_by,approved_by,approved_at,reason) "
                    "VALUES (?,?,?, 'All', ?,?,?, 'active', ?, ?, CURRENT_TIMESTAMP, 'Additional role added by School Admin')",
                    (user_id, school_id, tenant, role, class_id, subject_id, session["user_id"], session["user_id"])).lastrowid
                for perm in ROLE_CATALOG[role]:
                    conn.execute("INSERT INTO role_assignment_permissions(assignment_id,permission,granted) VALUES (?,?,1)", (aid, perm))
                conn.execute("INSERT INTO role_assignment_audit(assignment_id,user_id,school_id,actor_user_id,actor_name,action,new_role,approval_status,reason) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", (aid, user_id, school_id, session["user_id"], session.get("name"), "role_added", role, "active_immediately", "Additional role"))
                log_audit(conn, session.get("role"), session.get("name"), "role_added", f"{user['name']}: +{role}", school_id=school_id)
                conn.commit()
                flash(f"{role} added. It is active immediately and combines with the other roles.", "success")
            elif action == "remove":
                aid = request.form.get("assignment_id", type=int)
                ra = conn.execute("SELECT * FROM role_assignments WHERE id=? AND user_id=? AND school_id=? AND status='active'", (aid, user_id, school_id)).fetchone()
                if not ra:
                    conn.close(); flash("Role not found.", "error"); return redirect(url_for("staff_roles", user_id=user_id))
                conn.execute("UPDATE role_assignments SET status='revoked', updated_at=CURRENT_TIMESTAMP WHERE id=?", (aid,))
                remaining = [r for r in active_role_assignments(conn, user_id, school_id) if r["id"] != aid]
                if canonical_rbac_role(user["rbac_role"]) == canonical_rbac_role(ra["role"]):
                    nxt = remaining[0]["role"] if remaining else "Teacher"
                    conn.execute("UPDATE users SET rbac_role=? WHERE id=?", (nxt, user_id))
                conn.execute("INSERT INTO role_assignment_audit(assignment_id,user_id,school_id,actor_user_id,actor_name,action,previous_role,approval_status,reason) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", (aid, user_id, school_id, session["user_id"], session.get("name"), "role_removed", ra["role"], "active_immediately", "Role removed"))
                log_audit(conn, session.get("role"), session.get("name"), "role_removed", f"{user['name']}: -{ra['role']}", school_id=school_id)
                conn.commit()
                flash(f"{ra['role']} removed. Its permissions stopped applying immediately.", "success")
            conn.close()
            return redirect(url_for("staff_roles", user_id=user_id))
        assignments = active_role_assignments(conn, user_id, school_id)
        classes = conn.execute("SELECT id,name FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
        subjects = conn.execute("SELECT id,name FROM subjects WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
        conn.close()
        return render_template("staff_roles.html", user=user, assignments=assignments, roles=assignable_staff_roles(), classes=classes, subjects=subjects)

    # ================================================================== 5. REGISTRAR / ADMISSIONS + STUDENT STATUS
    def registrar_ok(conn):
        if is_admin_like():
            return True
        return REGISTRAR_ROLE in roles_of(conn, session.get("user_id"), sid())

    def next_admission_number(conn, school_id):
        school = conn.execute("SELECT school_code, name FROM schools WHERE id=?", (school_id,)).fetchone()
        prefix = re.sub(r"[^A-Z0-9]", "", str((school["school_code"] if school and school["school_code"] else (school["name"] if school else "ADM"))).upper())[:6] or "ADM"
        year = core.school_now(conn, school_id).year
        n = conn.execute("SELECT COUNT(*) c FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=?", (school_id,)).fetchone()["c"] + 1
        while True:
            cand = f"{prefix}/{year}/{n:04d}"
            if not conn.execute("SELECT 1 FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? AND LOWER(TRIM(s.admission_no))=LOWER(?)", (school_id, cand)).fetchone():
                return cand
            n += 1

    def next_register_number(conn, class_id):
        row = conn.execute("SELECT MAX(CAST(register_no AS INTEGER)) m FROM students WHERE class_id=? AND register_no GLOB '[0-9]*'", (class_id,)).fetchone()
        return str((row["m"] or 0) + 1)

    def log_status(conn, school_id, student_id, previous, new, *, effective=None, destination=None, previous_school=None, reason=None):
        conn.execute(
            "INSERT INTO student_status_history(school_id,tenant_id,student_id,previous_status,new_status,effective_date,destination_school,previous_school,"
            "reason,changed_by,changed_by_name,changed_by_role,server_timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (school_id, tenant_of(conn, school_id), student_id, previous, new, effective or core.school_today(conn, school_id), destination,
             previous_school, reason, session.get("user_id"), session.get("name"), actor_role_label(), core.server_stamp()))

    def custom_statuses(conn, school_id):
        return conn.execute("SELECT * FROM school_student_statuses WHERE school_id=? AND is_active=1 ORDER BY name", (school_id,)).fetchall()

    def all_status_names(conn, school_id):
        return STUDENT_STATUSES + [r["name"] for r in custom_statuses(conn, school_id) if r["name"] not in STUDENT_STATUSES]

    @app.route("/registrar")
    @login_required()
    def registrar_dashboard():
        conn = get_db()
        school_id = sid()
        if not registrar_ok(conn):
            conn.close(); flash("The Registrar / Admissions dashboard is for the Registrar and school administrators.", "error"); return redirect(url_for("dashboard"))
        counts = conn.execute("SELECT s.status, COUNT(*) c FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? GROUP BY s.status ORDER BY s.status", (school_id,)).fetchall()
        recent = conn.execute("SELECT s.* , c.name class_name FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? ORDER BY s.id DESC LIMIT 15", (school_id,)).fetchall()
        history = conn.execute("SELECT h.*, s.first_name, s.last_name FROM student_status_history h JOIN students s ON s.id=h.student_id WHERE h.school_id=? ORDER BY h.id DESC LIMIT 20", (school_id,)).fetchall()
        classes = conn.execute("SELECT id,name FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
        statuses = all_status_names(conn, school_id)
        students = conn.execute("SELECT s.id,s.first_name,s.last_name,s.admission_no,s.status,c.name class_name FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? ORDER BY c.name,s.last_name", (school_id,)).fetchall()
        suggestion = next_admission_number(conn, school_id)
        conn.close()
        return render_template("registrar_dashboard.html", counts=counts, recent=recent, history=history, classes=classes, statuses=statuses,
                               students=students, suggestion=suggestion, student_full_name=student_full_name)

    @app.route("/registrar/register", methods=["POST"])
    @login_required()
    def registrar_register_student():
        conn = get_db()
        school_id = sid()
        if not registrar_ok(conn):
            conn.close(); flash("You do not have permission to register students.", "error"); return redirect(url_for("dashboard"))
        f = request.form
        class_id = f.get("class_id", type=int)
        first, last = f.get("first_name", "").strip(), f.get("last_name", "").strip()
        errors = []
        if not class_id or not class_in_school(conn, class_id):
            errors.append("Choose a valid class/arm.")
        if not first or not last:
            errors.append("First and last name are required.")
        if f.get("gender") not in ("M", "F"):
            errors.append("Gender is required.")
        admission = f.get("admission_no", "").strip() or (next_admission_number(conn, school_id) if not errors else "")
        if admission and conn.execute("SELECT 1 FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=? AND LOWER(TRIM(s.admission_no))=LOWER(TRIM(?))", (school_id, admission)).fetchone():
            errors.append("That admission number is already used in this school.")
        register_no = f.get("register_no", "").strip() or (next_register_number(conn, class_id) if class_id else None)
        if class_id and register_no and conn.execute("SELECT 1 FROM students WHERE class_id=? AND TRIM(register_no)=TRIM(?)", (class_id, register_no)).fetchone():
            errors.append("That register number is already used in this class.")
        if not errors:
            allowed, message, _ = h["plan_limit_check"](conn, school_id, "students", 1)
            if not allowed:
                errors.append(message)
        if errors:
            for e in errors:
                flash(e, "error")
            conn.close()
            return redirect(url_for("registrar_dashboard"))
        try:
            cur = conn.execute(
                "INSERT INTO students (school_id,tenant_id,admission_no,register_no,first_name,last_name,other_names,gender,class_id,date_of_birth,religion,"
                "parent_name,parent_address,parent_email,parent_phone,parent_relationship,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'Active')",
                (school_id, tenant_of(conn, school_id), admission, register_no, first, last, f.get("other_names", "").strip() or None, f.get("gender"), class_id,
                 f.get("date_of_birth", "").strip() or None, f.get("religion", "").strip() or None, f.get("parent_name", "").strip() or None,
                 f.get("parent_address", "").strip() or None, f.get("parent_email", "").strip() or None, f.get("parent_phone", "").strip() or None,
                 f.get("parent_relationship", "").strip() or None))
            student_id = cur.lastrowid
            h["upsert_enrollment"](conn, student_id, class_id)
            log_status(conn, school_id, student_id, None, "Active", previous_school=f.get("previous_school", "").strip() or None,
                       reason="Admitted" + (f" - {f.get('admission_notes').strip()}" if f.get("admission_notes", "").strip() else ""))
            log_audit(conn, session.get("role"), session.get("name"), "student_admitted", f"{first} {last} ({admission})", school_id=school_id)
            conn.commit()
            flash(f"{first} {last} admitted. Admission No. {admission}, Register No. {register_no}.", "success")
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("That admission or register number is already in use.", "error")
        conn.close()
        return redirect(url_for("registrar_dashboard"))

    @app.route("/registrar/students/<int:student_id>/status", methods=["POST"])
    @login_required()
    def registrar_change_status(student_id):
        conn = get_db()
        school_id = sid()
        if not registrar_ok(conn):
            conn.close(); flash("You do not have permission to change student status.", "error"); return redirect(url_for("dashboard"))
        st = conn.execute("SELECT s.* FROM students s JOIN classes c ON c.id=s.class_id WHERE s.id=? AND c.school_id=?", (student_id, school_id)).fetchone()
        new = request.form.get("new_status", "").strip()
        if not st or new not in all_status_names(conn, school_id):
            conn.close(); flash("Student or status not found.", "error"); return redirect(url_for("registrar_dashboard"))
        reason = request.form.get("reason", "").strip()[:500]
        destination = request.form.get("destination_school", "").strip()[:200]
        effective = request.form.get("effective_date", "").strip() or core.school_today(conn, school_id)
        try:
            datetime.date.fromisoformat(effective)
        except ValueError:
            conn.close(); flash("Enter a valid effective date.", "error"); return redirect(url_for("registrar_dashboard"))
        if new == "Transferred" and not destination:
            conn.close(); flash("A transfer needs the destination school.", "error"); return redirect(url_for("registrar_dashboard"))
        if new in ("Withdrawn", "Suspended", "Expelled") and not reason:
            conn.close(); flash(f"A reason is required to mark a student {new.lower()}.", "error"); return redirect(url_for("registrar_dashboard"))
        custom = conn.execute("SELECT keeps_enrolled FROM school_student_statuses WHERE school_id=? AND name=? AND is_active=1", (school_id, new)).fetchone()
        keeps = new in KEEPS_ENROLLED or bool(custom and custom["keeps_enrolled"])
        previous = st["status"] or "Active"
        conn.execute("UPDATE students SET status=?, is_active=?, status_changed_at=? WHERE id=?", (new, 1 if keeps else 0, core.server_stamp(), student_id))
        log_status(conn, school_id, student_id, previous, new, effective=effective, destination=destination or None, reason=reason or None)
        log_audit(conn, session.get("role"), session.get("name"), "student_status_changed", f"{student_full_name(st)}: {previous} -> {new}", school_id=school_id)
        conn.commit(); conn.close()
        flash(f"Status updated: {previous} -> {new}.", "success")
        return redirect(url_for("registrar_dashboard"))

    @app.route("/registrar/statuses", methods=["POST"])
    @login_required()
    def registrar_add_status():
        conn = get_db()
        school_id = sid()
        if not registrar_ok(conn):
            conn.close(); flash("You do not have permission.", "error"); return redirect(url_for("dashboard"))
        name = re.sub(r"\s+", " ", request.form.get("name", "").strip())[:40]
        if not name or name in STUDENT_STATUSES:
            conn.close(); flash("Enter a new status name.", "error"); return redirect(url_for("registrar_dashboard"))
        conn.execute("INSERT OR IGNORE INTO school_student_statuses(school_id,tenant_id,name,keeps_enrolled) VALUES (?,?,?,?)",
                     (school_id, tenant_of(conn, school_id), name, 1 if request.form.get("keeps_enrolled") else 0))
        log_audit(conn, session.get("role"), session.get("name"), "student_status_defined", name, school_id=school_id)
        conn.commit(); conn.close()
        flash(f"Status '{name}' added.", "success")
        return redirect(url_for("registrar_dashboard"))

    @app.route("/students/<int:student_id>/status-history")
    @login_required()
    def student_status_history_view(student_id):
        conn = get_db()
        school_id = sid()
        st = conn.execute("SELECT s.*, c.name class_name FROM students s JOIN classes c ON c.id=s.class_id WHERE s.id=? AND c.school_id=?", (student_id, school_id)).fetchone()
        if not st or not (registrar_ok(conn) or st["class_id"] in (form_teacher_class_ids(conn, session["user_id"]) or [])):
            conn.close(); flash("Student not found.", "error"); return redirect(url_for("dashboard"))
        rows = conn.execute("SELECT * FROM student_status_history WHERE school_id=? AND student_id=? ORDER BY id DESC", (school_id, student_id)).fetchall()
        conn.close()
        return render_template("student_status_history.html", st=st, rows=rows, student_full_name=student_full_name)

    # ---- Class/Form Teacher: register numbers for the assigned class only --------------------------------------
    @app.route("/my-class/<int:class_id>/register", methods=["GET", "POST"])
    @login_required()
    def class_register(class_id):
        conn = get_db()
        school_id = sid()
        cls = class_in_school(conn, class_id)
        if not cls or not (is_admin_like() or class_id in (form_teacher_class_ids(conn, session["user_id"]) or [])):
            conn.close(); flash("You're not the form teacher for that class.", "error"); return redirect(url_for("dashboard"))
        students = conn.execute("SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY last_name, first_name", (class_id,)).fetchall()
        if request.method == "POST":
            values, seen, errors = {}, set(), []
            for s in students:
                v = request.form.get(f"reg_{s['id']}", "").strip()[:12]
                if v and v.lower() in seen:
                    errors.append(f"Register number {v} is used twice.")
                seen.add(v.lower()) if v else None
                values[s["id"]] = v or None
            if errors:
                flash(" ".join(sorted(set(errors))), "error")
            else:
                for s in students:
                    if (s["register_no"] or None) != values[s["id"]]:
                        conn.execute("UPDATE students SET register_no=? WHERE id=? AND class_id=?", (values[s["id"]], s["id"], class_id))
                log_audit(conn, session.get("role"), session.get("name"), "register_numbers_updated", cls["name"], school_id=school_id)
                conn.commit()
                flash("Register numbers saved.", "success")
            conn.close()
            return redirect(url_for("class_register", class_id=class_id))
        conn.close()
        return render_template("class_register.html", cls=cls, students=students, student_full_name=student_full_name)

    # expose for the dashboard link
    app.jinja_env.globals["v63_is_registrar"] = lambda: bool(session.get("user_id") and session.get("school_id") and _is_registrar_cached())

    def _is_registrar_cached():
        try:
            conn = get_db()
            try:
                return registrar_ok(conn)
            finally:
                conn.close()
        except Exception:
            return False
