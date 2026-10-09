"""Result approval & publication workflow screens. DRAFT -> SUBMITTED -> UNDER REVIEW -> APPROVED -> PUBLISHED
(with RETURNED for correction and REOPENED after publication). The class, term and school always come from the session
and the database - never from a tenant id in the request."""
import sqlite3

from flask import abort, flash, redirect, render_template, request, session, url_for

import ops_core


def register_workflow_routes(app, h):
    get_db = h["get_db"]
    login_required = h["login_required"]
    current_school_id = h["current_school_id"]
    resolve_term = h["resolve_term"]
    all_terms_for_school = h["all_terms_for_school"]
    can_view_results_for_class = h["can_view_results_for_class"]
    workflow_permission = h["workflow_permission"]
    workflow_actor = h["workflow_actor"]
    AUTO_ADVANCE = h["AUTO_ADVANCE"]
    security_event = h["security_event"]
    import profile_core as pc

    ACTION_LABELS = {"submit": "Submit for review", "start_review": "Start review", "return": "Return for correction", "approve": "Approve",
                     "publish": "Publish", "reopen": "Reopen for correction"}
    NEEDS_REASON = {"return", "reopen"}
    NEXT_ACTIONS = {"DRAFT": ["submit"], "RETURNED": ["submit"], "REOPENED": ["submit"], "SUBMITTED": ["start_review", "return"],
                    "UNDER_REVIEW": ["approve", "return"], "APPROVED": ["publish"], "PUBLISHED": ["reopen"]}

    def review_summary(conn, school_id, class_id, term_id):
        """What a reviewer must verify: scores, attendance, domains, comments, student status."""
        studs = conn.execute("SELECT id, status FROM students WHERE class_id=? AND is_active=1", (class_id,)).fetchall()
        ids = [s["id"] for s in studs]
        n = len(ids)
        if not n:
            return {"students": 0}
        ph = ",".join("?" * len(ids))
        def cnt(sql, *a):
            return conn.execute(sql, a).fetchone()[0]
        subjects = cnt("SELECT COUNT(*) FROM class_subjects WHERE class_id=?", class_id)
        return {
            "students": n, "subjects": subjects,
            "scored_cells": cnt(f"SELECT COUNT(*) FROM scores WHERE term_id=? AND student_id IN ({ph}) AND subject_id IN (SELECT subject_id FROM class_subjects WHERE class_id=?)", term_id, *ids, class_id),
            "expected_cells": n * subjects,
            "with_attendance": cnt(f"SELECT COUNT(DISTINCT student_id) FROM attendance_records WHERE term_id=? AND student_id IN ({ph})", term_id, *ids)
                               + 0,
            "with_domains": cnt(f"SELECT COUNT(DISTINCT student_id) FROM student_skill_ratings WHERE term_id=? AND student_id IN ({ph})", term_id, *ids),
            "with_teacher_comment": cnt(f"SELECT COUNT(*) FROM student_term_info WHERE term_id=? AND student_id IN ({ph}) AND COALESCE(teacher_comment,'')<>''", term_id, *ids),
            "with_principal_comment": cnt(f"SELECT COUNT(*) FROM student_term_info WHERE term_id=? AND student_id IN ({ph}) AND COALESCE(principal_comment,'')<>''", term_id, *ids),
            "inactive_status": cnt("SELECT COUNT(*) FROM students WHERE class_id=? AND is_active=0 AND status IS NOT NULL", class_id),
        }

    @app.route("/results/workflow")
    @login_required("admin", "sub_admin", "teacher")
    def results_workflow():
        conn = get_db()
        try:
            sid = current_school_id()
            term = resolve_term(conn, request.args.get("term_id", type=int))
            if not term:
                flash("No term set yet.", "error")
                return redirect(url_for("dashboard"))
            rows = []
            for c in conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (sid,)).fetchall():
                if not can_view_results_for_class(conn, c["id"]):
                    continue
                b = ops_core.get_batch(conn, sid, c["id"], term["id"])
                actions = [a for a in NEXT_ACTIONS.get(b["status"], []) if workflow_permission(conn, a, c["id"])]
                problems, warnings = ops_core.validate_for_submission(conn, sid, c["id"], term["id"]) if b["status"] in ("DRAFT", "RETURNED", "REOPENED") else ([], [])
                rows.append({"cls": c, "batch": b, "label": ops_core.STATE_LABELS[b["status"]], "actions": actions, "problems": problems, "warnings": warnings,
                             "summary": review_summary(conn, sid, c["id"], term["id"]) if b["status"] in ("SUBMITTED", "UNDER_REVIEW", "APPROVED") else None})
            conn.commit()
            terms = all_terms_for_school(conn)
        finally:
            conn.close()
        return render_template("results_workflow.html", rows=rows, term=term, terms=terms, action_labels=ACTION_LABELS, needs_reason=NEEDS_REASON)

    @app.route("/results/workflow/<int:class_id>/<action>", methods=["POST"])
    @login_required("admin", "sub_admin", "teacher")
    def results_workflow_action(class_id, action):
        if action not in ops_core.TRANSITIONS:
            abort(404)
        conn = get_db()
        try:
            sid = current_school_id()
            if not conn.execute("SELECT 1 FROM classes WHERE id=? AND school_id=?", (class_id, sid)).fetchone():
                abort(404)
            term_id = request.form.get("term_id", type=int)
            if not term_id or not conn.execute("SELECT 1 FROM terms t JOIN sessions s ON s.id=t.session_id WHERE t.id=? AND s.school_id=?", (term_id, sid)).fetchone():
                abort(404)
            if not can_view_results_for_class(conn, class_id) or not workflow_permission(conn, action, class_id):
                try:
                    security_event(conn, "WORKFLOW_DENIED", "denied", f"{action} class={class_id} term={term_id}", "result_batch", f"{class_id}:{term_id}")
                    conn.commit()
                except Exception:
                    pass
                return render_template("profile_denied.html", message=f"You do not have permission to {ACTION_LABELS[action].lower()} these results."), 403
            try:
                conn.execute("BEGIN IMMEDIATE")
                prev, new = ops_core.transition(conn, sid, class_id, term_id, action, workflow_actor(conn), request.form.get("reason"))
                pc.audit(conn, {"type": "staff", "id": session.get("user_id"), "name": session.get("name"), "role": workflow_actor(conn)["roles"], "school_id": sid, "tenant_id": session.get("tenant_id")},
                         f"result_{action}", "result_batch", f"{class_id}:{term_id}", {"status": [prev, new], "reason": (request.form.get("reason") or None)}, ip=request.remote_addr)
                msg = f"{ACTION_LABELS[action]}: now {ops_core.STATE_LABELS[new].lower()}."
                if action == "publish":
                    try:
                        auto = AUTO_ADVANCE(conn, term_id)
                        if auto:
                            flash(auto, "success")
                    except Exception:
                        app.logger.exception("Automatic next term/session creation failed")
                    conn.execute("INSERT INTO notifications(sender_label,school_id,target_role,title,message) VALUES (?,?,?,?,?)",
                                 (session.get("name", "System"), sid, "all", "Results published", f"Results for {conn.execute('SELECT name FROM classes WHERE id=?', (class_id,)).fetchone()[0]} are now published."))
                if action in ("submit", "return", "approve"):
                    conn.execute("INSERT INTO notifications(sender_label,school_id,target_role,title,message) VALUES (?,?,?,?,?)",
                                 (session.get("name", "System"), sid, "admin", f"Results {new.replace('_', ' ').lower()}",
                                  f"{conn.execute('SELECT name FROM classes WHERE id=?', (class_id,)).fetchone()[0]}: {ACTION_LABELS[action].lower()} by {session.get('name')}."))
                conn.commit()
                flash(msg, "success")
            except ValueError as exc:
                conn.rollback()
                flash(str(exc), "error")
            except sqlite3.Error:
                conn.rollback()
                app.logger.exception("Workflow action failed")
                flash("The action could not be completed. Nothing was changed.", "error")
        finally:
            conn.close()
        return redirect(url_for("results_workflow", term_id=term_id))

    @app.route("/results/workflow/<int:class_id>/history")
    @login_required("admin", "sub_admin", "teacher")
    def results_workflow_history(class_id):
        conn = get_db()
        try:
            sid = current_school_id()
            cls = conn.execute("SELECT * FROM classes WHERE id=? AND school_id=?", (class_id, sid)).fetchone()
            if not cls:
                abort(404)
            if not can_view_results_for_class(conn, class_id):
                abort(403)
            term = resolve_term(conn, request.args.get("term_id", type=int))
            rows = conn.execute("SELECT * FROM result_publication_log WHERE school_id=? AND class_id=? AND term_id=? ORDER BY id DESC", (sid, class_id, term["id"])).fetchall() if term else []
        finally:
            conn.close()
        return render_template("results_workflow_history.html", cls=cls, term=term, rows=rows)

    @app.route("/results/publication-log")
    @login_required("admin")
    def publication_log():
        conn = get_db()
        try:
            rows = conn.execute("SELECT l.*, c.name AS class_name, t.name AS term_name FROM result_publication_log l LEFT JOIN classes c ON c.id=l.class_id LEFT JOIN terms t ON t.id=l.term_id "
                                "WHERE l.school_id=? ORDER BY l.id DESC LIMIT 300", (current_school_id(),)).fetchall()
        finally:
            conn.close()
        return render_template("results_workflow_history.html", cls=None, term=None, rows=rows)
