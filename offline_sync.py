"""Offline-first sync support for My School Hub (server side, SQLite today, portable to PostgreSQL later).

How offline writes reach the server
-----------------------------------
A device that is offline keeps its changes in a local queue (IndexedDB, see static/js/offline/). When the connection
returns, the browser REPLAYS each queued request against the very same Flask route that would have handled it online,
so permissions, validation, the result-approval workflow lock and the audit trail are applied exactly as before.
This module adds three things around that replay, without touching the routes themselves:

1. Idempotency  - every replayed request carries ``X-Change-Id`` (a UUID created on the device). The first result is
                  stored in ``sync_changes``; a retry of the same change is answered from that record and never runs
                  twice, so a dropped connection can never create a duplicate record.
2. Conflicts    - a replayed score save also carries ``X-Base-Version`` (the row's ``updated_at`` when the device last
                  saw it). If somebody changed that row meanwhile, the change is NOT applied: it is parked in
                  ``sync_conflicts`` for an administrator (scores are sensitive academic data). Identical values
                  resolve automatically. Attendance replayed after its day has passed is parked too, because the
                  server-date-only attendance rule must never be bypassed silently.
3. Visibility   - status / report / conflict endpoints for the Sync Center page.
"""
import datetime
import hashlib
import json
import re
import time

from werkzeug.security import check_password_hash
from flask import Blueprint, current_app, g, get_flashed_messages, jsonify, make_response, redirect, render_template, request, session, url_for, flash

import v63_core
from db import get_db, log_audit

sync_bp = Blueprint("sync", __name__)

UNSAFE = ("POST", "PUT", "PATCH", "DELETE")
CHANGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
SCORE_PATH = re.compile(r"^/api/scores/(\d+)/(\d+)/row$")
ROLL_CALL_PATH = re.compile(r"^/my-class/(\d+)/roll-call$")
SCORE_FIELDS = ("ca1", "ca2", "ca3", "exam")
MAX_STORED_BODY = 20000

_hooks = {}
_pw_fail = {}          # user id -> [attempt times]; slows down password guessing on the offline-unlock endpoint


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def user_fingerprint():
    """Opaque id of 'this user in this school'. Sent to the browser so it can keep its cached pages and queued changes
    separate per user, and wipe them when a different person signs in on the same device."""
    if not session.get("user_id"):
        return ""
    raw = f"{session.get('user_id')}|{session.get('school_id')}|{session.get('tenant_id')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def init_offline_sync(app, *, login_required, current_term, get_csrf_token, compute_total, grade_for, student_full_name=None):
    """Wire the blueprint and the request hooks into the Flask app (called once from app.py)."""
    _hooks.update(login_required=login_required, current_term=current_term, get_csrf_token=get_csrf_token,
                  compute_total=compute_total, grade_for=grade_for, student_full_name=student_full_name)
    _register_routes()
    app.register_blueprint(sync_bp)
    app.before_request(_sync_before)
    app.after_request(_sync_after)


# ------------------------------------------------------------------ request hooks
def _sync_before():
    """Runs after the CSRF check. Handles duplicate replays and offline-replay conflict detection."""
    cid = request.headers.get("X-Change-Id")
    if not cid or request.method not in UNSAFE or not session.get("user_id"):
        return None
    if not CHANGE_ID_RE.match(cid):
        return jsonify({"ok": False, "error": "Invalid change id."}), 400
    school_id = session.get("school_id")
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM sync_changes WHERE school_id=? AND change_id=?", (school_id, cid)).fetchone()
        if row and row["state"] in ("applied", "conflict"):
            conn.execute("UPDATE sync_changes SET attempts=attempts+1 WHERE id=?", (row["id"],))
            conn.commit()
            g.sync_recorded = True
            return _stored_response(row)
        g.sync_change = {"id": cid, "device": (request.headers.get("X-Device-Id") or "")[:64],
                         "captured_at": (request.headers.get("X-Captured-At") or "")[:40],
                         "base": request.headers.get("X-Base-Version"), "replay": request.headers.get("X-Offline-Replay") == "1"}
        if not g.sync_change["replay"]:
            return None
        m = SCORE_PATH.match(request.path)
        if m:
            return _check_score_conflict(conn, int(m.group(1)), int(m.group(2)))
        m = ROLL_CALL_PATH.match(request.path)
        if m:
            return _check_stale_attendance(conn, int(m.group(1)))
    finally:
        conn.close()
    return None


def _stored_response(row):
    body = row["response_body"] or ""
    if row["status_code"] and 300 <= row["status_code"] < 400:
        try:
            loc = json.loads(body).get("location") or "/"
        except Exception:
            loc = "/"
        resp = redirect(loc, code=row["status_code"])
    else:
        resp = make_response(body or "{}", row["status_code"] or 200)
        resp.mimetype = "application/json"
    resp.headers["X-Sync-Duplicate"] = "1"
    return resp


def _sync_after(response):
    if session.get("user_id"):
        response.headers["X-SH-User"] = user_fingerprint()
    ch = getattr(g, "sync_change", None)
    cid = request.headers.get("X-Change-Id")
    if cid and (ch or getattr(g, "sync_recorded", False)):
        # The device only treats a replay as done when the server echoes THIS change id back.
        response.headers["X-Sync-Ack"] = cid
    if not ch or getattr(g, "sync_recorded", False):
        return response
    if ch["replay"] and 300 <= response.status_code < 400:
        response = _replay_outcome(response, cid)
    try:
        code = response.status_code
        state = "applied" if code < 400 else "failed"
        if 300 <= code < 400:
            body = json.dumps({"location": response.headers.get("Location", "/")})
        elif response.is_json or (response.mimetype or "").startswith("text/"):
            body = response.get_data(as_text=True)[:MAX_STORED_BODY]
        else:
            body = ""
        entity, key = _entity_of(request.path)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO sync_changes (change_id, school_id, tenant_id, user_id, device_id, method, path, entity, entity_key, base_version, captured_at, state, status_code, response_body) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(school_id, change_id) DO UPDATE SET state=excluded.state, status_code=excluded.status_code, "
                "response_body=excluded.response_body, attempts=sync_changes.attempts+1",
                (ch["id"], session.get("school_id"), session.get("tenant_id"), session.get("user_id"), ch["device"], request.method,
                 request.path, entity, key, ch["base"], ch["captured_at"], state, code, body))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # recording must never break the real response
        current_app.logger.exception("sync_changes record failed")
    return response


def _replay_outcome(response, cid):
    """A browser form post answers 'redirect + flash message'. For a replay from the offline queue the device needs the actual
    outcome, not the page it redirects to: success -> 200 JSON; a rejected form (the route flashed an error) -> 422 JSON with
    the message the user would have seen online. The route itself is untouched."""
    msgs = get_flashed_messages(with_categories=True)
    bad = [m for c, m in msgs if c in ("error", "danger", "warning")]
    if bad:
        out = jsonify({"ok": False, "error": bad[0], "messages": [m for _c, m in msgs]})
        out.status_code = 422
    else:
        out = jsonify({"ok": True, "messages": [m for _c, m in msgs], "location": response.headers.get("Location", "/")})
    out.headers["X-Sync-Ack"] = cid
    return out


def _entity_of(path):
    if SCORE_PATH.match(path):
        return "score", path
    if ROLL_CALL_PATH.match(path):
        return "attendance", path
    return "request", path


def _record_change(conn, state, code, body, entity, key):
    ch = g.sync_change
    conn.execute(
        "INSERT INTO sync_changes (change_id, school_id, tenant_id, user_id, device_id, method, path, entity, entity_key, base_version, captured_at, state, status_code, response_body) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(school_id, change_id) DO UPDATE SET state=excluded.state, status_code=excluded.status_code, response_body=excluded.response_body, attempts=sync_changes.attempts+1",
        (ch["id"], session.get("school_id"), session.get("tenant_id"), session.get("user_id"), ch["device"], request.method, request.path,
         entity, key, ch["base"], ch["captured_at"], state, code, json.dumps(body)))
    g.sync_recorded = True


def _park_conflict(conn, *, kind, entity_key, client_payload, server_payload, reason, sensitive=1):
    ch = g.sync_change
    cur = conn.execute(
        "INSERT INTO sync_conflicts (school_id, entity, client_uuid, device_id, client_payload, server_payload, change_id, kind, sensitive, reason, entity_key, tenant_id, method, path) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (session.get("school_id"), kind, ch["id"], ch["device"], json.dumps(client_payload), json.dumps(server_payload), ch["id"], kind, sensitive,
         reason, entity_key, session.get("tenant_id"), request.method, request.path))
    cid = cur.lastrowid
    log_audit(conn, session.get("role"), session.get("name"), "offline_conflict_detected", f"{kind} {entity_key}: {reason}", school_id=session.get("school_id"))
    return cid


# ------------------------------------------------------------------ conflict detection
def _check_score_conflict(conn, class_id, subject_id):
    body = request.get_json(silent=True) or {}
    sid = body.get("student_id")
    term = _hooks["current_term"](conn)
    if not isinstance(sid, int) or not term:
        return None                      # let the real route reject it with its normal message
    srv = conn.execute("SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?", (sid, subject_id, term["id"])).fetchone()
    server_version = (srv["updated_at"] if srv else "") or ""
    base = g.sync_change["base"] or ""
    if server_version == base:
        return None                      # nobody touched it: apply normally
    incoming = {}
    for k in SCORE_FIELDS:
        raw = body.get(k)
        try:
            incoming[k] = 0.0 if raw in (None, "") else float(raw)
        except (TypeError, ValueError):
            return None                  # invalid input: the real route answers 400
    key = f"score:{sid}:{subject_id}:{term['id']}"
    if srv is not None and all(abs(float(srv[k] or 0) - incoming[k]) < 1e-9 for k in SCORE_FIELDS):
        total = _hooks["compute_total"](incoming["ca1"], incoming["ca2"], incoming["exam"], incoming["ca3"])
        grade, remark = _hooks["grade_for"](total, conn, session.get("school_id"))
        out = {"ok": True, "noop": True, "auto_resolved": True, "student_id": sid, "total": total, "grade": grade, "remark": remark,
               "updated_at": server_version, "saved_at": datetime.datetime.now().strftime("%H:%M:%S")}
        _record_change(conn, "applied", 200, out, "score", key)
        log_audit(conn, session.get("role"), session.get("name"), "offline_conflict_auto_resolved", f"{key}: same values on both sides", school_id=session.get("school_id"))
        conn.commit()
        return jsonify(out)
    server_payload = {k: (srv[k] if srv is not None else None) for k in SCORE_FIELDS}
    server_payload.update({"updated_at": server_version, "student_id": sid, "subject_id": subject_id, "class_id": class_id, "term_id": term["id"]})
    cid = _park_conflict(conn, kind="score", entity_key=key,
                         client_payload={"body": body, "captured_at": g.sync_change["captured_at"], "base_version": base,
                                         "class_id": class_id, "subject_id": subject_id, "term_id": term["id"], "student_id": sid},
                         server_payload=server_payload,
                         reason="Score changed by someone else while this device was offline")
    out = {"ok": False, "conflict": True, "conflict_id": cid,
           "error": "This score was changed by someone else while you were offline. An administrator must choose which version to keep."}
    _record_change(conn, "conflict", 409, out, "score", key)
    conn.commit()
    return jsonify(out), 409


def _check_stale_attendance(conn, class_id):
    cap = g.sync_change["captured_at"]
    try:
        captured = datetime.datetime.fromisoformat(cap.replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
    school_id = session.get("school_id")
    cap_day = captured.astimezone(v63_core.school_tz(conn, school_id)).date().isoformat()
    today = v63_core.school_today(conn, school_id)
    if cap_day == today:
        return None                      # still the same school day: the normal route applies its normal rules
    form = {k: v for k, v in request.form.items() if k != "csrf_token"}
    cid = _park_conflict(conn, kind="attendance_stale_date", entity_key=f"attendance:{class_id}:{cap_day}",
                         client_payload={"form": form, "captured_at": cap, "captured_school_date": cap_day, "class_id": class_id},
                         server_payload={"school_today": today},
                         reason=f"Attendance taken offline for {cap_day} reached the server on {today}. Attendance can only be recorded on the current date.")
    out = {"ok": False, "conflict": True, "conflict_id": cid,
           "error": "This attendance was taken on an earlier day. An administrator must review it."}
    _record_change(conn, "conflict", 409, out, "attendance", f"attendance:{class_id}:{cap_day}")
    conn.commit()
    return jsonify(out), 409


# ------------------------------------------------------------------ routes
def _register_routes():
    login_required = _hooks["login_required"]

    @sync_bp.route("/api/sync/ping", methods=["GET", "HEAD"])
    def sync_ping():
        resp = jsonify({"ok": True, "time": _now()})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @sync_bp.route("/api/sync/static-manifest")
    def static_manifest():
        """V117: every public /static file the app can ask for (CSS, JS, icons, images). The service worker downloads ALL of them when it
        is installed - on the very first visit, even on the sign-in page - so no screen ever has to be opened once online before its
        styles, scripts and charts work offline. Static files hold no school data, so this list is public (no sign-in needed)."""
        import os
        root = current_app.static_folder or ""
        urls = []
        for base, _dirs, files in os.walk(root):
            for name in sorted(files):
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in ("css", "js", "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "woff", "woff2", "ttf", "json"):
                    continue
                full = os.path.join(base, name)
                try:
                    if os.path.getsize(full) > 3 * 1024 * 1024:
                        continue
                except OSError:
                    continue
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                urls.append("/static/" + rel)
        resp = jsonify({"files": sorted(urls)})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @sync_bp.route("/offline")
    def offline_page():
        """Shown by the service worker when a page was never opened on this device before the connection dropped."""
        resp = make_response(render_template("offline.html"))
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @sync_bp.route("/api/sync/session")
    def sync_session():
        """Tells the browser who is signed in (so it can namespace its local data) and hands it a fresh CSRF token."""
        uname = ""
        if session.get("user_id"):
            conn = get_db()
            try:
                r = conn.execute("SELECT username FROM users WHERE id=?", (session.get("user_id"),)).fetchone()
                uname = (r["username"] if r else "") or ""
            finally:
                conn.close()
        resp = jsonify({"authenticated": bool(session.get("user_id")), "fingerprint": user_fingerprint(), "username": uname,
                        "role": session.get("role"), "school_id": session.get("school_id"),
                        "csrf": _hooks["get_csrf_token"](),
                        "verified_at": _now(), "offline_window_days": int(current_app.config.get("OFFLINE_WINDOW_DAYS", 7))})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @sync_bp.route("/api/sync/verify-password", methods=["POST"])
    @login_required()
    def sync_verify_password():
        """Lets a person who is ALREADY signed in re-open their encrypted offline storage on this device (for example after an
        idle lock) without signing out. The password is checked here, then used in the browser only to unwrap their key."""
        uid = session.get("user_id")
        now = time.time()
        recent = [t for t in _pw_fail.get(uid, []) if now - t < 600]
        if len(recent) >= 5:
            return jsonify({"ok": False, "error": "Too many attempts. Try again in a few minutes."}), 429
        pw = (request.get_json(silent=True) or {}).get("password") or ""
        conn = get_db()
        try:
            row = conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
        finally:
            conn.close()
        if not row or not pw or not check_password_hash(row["password_hash"], pw):
            _pw_fail[uid] = recent + [now]
            return jsonify({"ok": False, "error": "That password is not correct."}), 403
        _pw_fail.pop(uid, None)
        return jsonify({"ok": True})

    @sync_bp.route("/api/sync/status")
    @login_required()
    def sync_status():
        conn = get_db()
        sid = session.get("school_id")
        try:
            counts = {r["state"]: r["n"] for r in conn.execute(
                "SELECT state, COUNT(*) n FROM sync_changes WHERE school_id=? GROUP BY state", (sid,)).fetchall()}
            last = conn.execute("SELECT MAX(received_at) m FROM sync_changes WHERE school_id=?", (sid,)).fetchone()["m"]
            open_conf = conn.execute("SELECT COUNT(*) n FROM sync_conflicts WHERE school_id=? AND resolved=0", (sid,)).fetchone()["n"]
        finally:
            conn.close()
        return jsonify({"ok": True, "applied": counts.get("applied", 0), "failed": counts.get("failed", 0),
                        "conflicts": counts.get("conflict", 0), "open_conflicts": open_conf, "last_received": last})

    @sync_bp.route("/api/sync/report", methods=["POST"])
    @login_required()
    def sync_report():
        """The browser reports how a sync run went, so administrators can see device activity."""
        b = request.get_json(silent=True) or {}
        conn = get_db()
        try:
            conn.execute("INSERT INTO sync_log (school_id, device_id, user_id, direction, entity, record_count, conflict_count, error_count) VALUES (?,?,?,?,?,?,?,?)",
                         (session.get("school_id"), str(b.get("device_id") or "browser")[:64], session.get("user_id"), "push", "queue",
                          int(b.get("synced") or 0), int(b.get("conflicts") or 0), int(b.get("failed") or 0)))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"ok": True})

    @sync_bp.route("/sync")
    @login_required()
    def sync_center():
        conn = get_db()
        sid = session.get("school_id")
        is_admin = session.get("role") in ("admin", "sub_admin")
        try:
            log = conn.execute("SELECT * FROM sync_log WHERE school_id=? ORDER BY id DESC LIMIT 15", (sid,)).fetchall() if is_admin else []
            changes = conn.execute("SELECT * FROM sync_changes WHERE school_id=? ORDER BY id DESC LIMIT 25", (sid,)).fetchall() if is_admin else []
            shaped = _conflict_rows(conn, sid, None if is_admin else session.get("user_id"))
        finally:
            conn.close()
        return render_template("sync_center.html", log=log, conflicts=shaped, changes=changes, is_admin=is_admin,
                               open_conflicts=sum(1 for c in shaped if not c["resolved"]))

    @sync_bp.route("/api/sync/conflicts/<int:conflict_id>/resolve", methods=["POST"])
    @login_required()
    def sync_resolve(conflict_id):
        b = request.get_json(silent=True) or request.form
        choice = (b.get("resolution") or "").strip()
        if choice not in ("keep_server", "apply_offline", "dismiss"):
            return jsonify({"ok": False, "error": "Choose keep_server, apply_offline or dismiss."}), 400
        conn = get_db()
        try:
            c = conn.execute("SELECT * FROM sync_conflicts WHERE id=? AND school_id=?", (conflict_id, session.get("school_id"))).fetchone()
            if not c or not _may_resolve(conn, c):
                return jsonify({"ok": False, "error": "Conflict not found."}), 404
            if c["resolved"]:
                return jsonify({"ok": False, "error": "Already resolved."}), 409
            ok, note = _resolve_one(conn, c, choice)
            if not ok:
                return jsonify({"ok": False, "error": note}), 409
            conn.commit()
        finally:
            conn.close()
        return jsonify({"ok": True, "resolution": choice, "note": note})

    @sync_bp.route("/api/sync/conflicts/resolve-all", methods=["POST"])
    @login_required()
    def sync_resolve_all():
        """One click for many conflicts: 'keep_server' or 'apply_offline' for every open conflict the person may resolve."""
        b = request.get_json(silent=True) or {}
        choice = (b.get("resolution") or "").strip()
        if choice not in ("keep_server", "apply_offline"):
            return jsonify({"ok": False, "error": "Choose keep_server or apply_offline."}), 400
        conn = get_db()
        done, failed = 0, []
        try:
            admin = session.get("role") in ("admin", "sub_admin")
            for c in [r for r in _conflict_rows(conn, session.get("school_id"), None if admin else session.get("user_id")) if not r["resolved"]]:
                row = conn.execute("SELECT * FROM sync_conflicts WHERE id=?", (c["id"],)).fetchone()
                if choice == "apply_offline" and row["kind"] != "score":
                    continue
                ok, note = _resolve_one(conn, row, choice)
                conn.commit()
                if ok:
                    done += 1
                else:
                    failed.append({"id": c["id"], "student": c["student"], "error": note})
        finally:
            conn.close()
        return jsonify({"ok": True, "resolved": done, "failed": failed})


def _conflict_rows(conn, school_id, only_user_id):
    """Conflicts of this school (administrators see all; a teacher sees only the ones from their own offline entries),
    with the student / subject / person shown in plain words."""
    sql = ("SELECT c.*, ch.user_id AS entered_by_id, u.name AS entered_by FROM sync_conflicts c "
           "LEFT JOIN sync_changes ch ON ch.change_id=c.change_id AND ch.school_id=c.school_id "
           "LEFT JOIN users u ON u.id=ch.user_id WHERE c.school_id=?")
    args = [school_id]
    if only_user_id is not None:
        sql += " AND ch.user_id=?"
        args.append(only_user_id)
    rows = conn.execute(sql + " ORDER BY c.resolved, c.id DESC LIMIT 200", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("client_payload", "server_payload"):
            try:
                d[k] = json.loads(d[k] or "{}")
            except Exception:
                d[k] = {}
        d["student"] = d["subject"] = ""
        if d["kind"] == "score":
            sp = d["server_payload"]
            st = conn.execute("SELECT * FROM students WHERE id=? AND school_id=?", (sp.get("student_id"), school_id)).fetchone()
            sub = conn.execute("SELECT name FROM subjects WHERE id=?", (sp.get("subject_id"),)).fetchone()
            fn = _hooks.get("student_full_name")
            d["student"] = (fn(st) if (fn and st) else (st["admission_no"] if st else "")) or ""
            d["subject"] = sub["name"] if sub else ""
        out.append(d)
    return out


def _may_resolve(conn, c):
    """Administrators resolve any conflict of their school. A teacher resolves the conflicts of THEIR OWN offline entries only
    (the replay of 'apply mine' still runs through the real score route, so class/subject assignment and result locks apply)."""
    if session.get("role") in ("admin", "sub_admin"):
        return True
    ch = conn.execute("SELECT user_id FROM sync_changes WHERE school_id=? AND change_id=?", (c["school_id"], c["change_id"])).fetchone()
    return bool(ch and ch["user_id"] == session.get("user_id"))


def _resolve_one(conn, c, choice):
    note = ""
    if choice == "apply_offline":
        if c["kind"] != "score":
            return False, "Only score conflicts can be applied; review attendance manually, then dismiss."
        ok, note = _apply_score(conn, c)
        if not ok:
            return False, note
    conn.execute("UPDATE sync_conflicts SET resolved=1, resolved_at=?, resolution=?, resolved_by=? WHERE id=?",
                 (_now(), choice, session.get("name") or str(session.get("user_id")), c["id"]))
    log_audit(conn, session.get("role"), session.get("name"), "offline_conflict_resolved",
              f"{c['kind']} {c['entity_key']}: {choice}. {note}", school_id=session.get("school_id"))
    return True, note


def _apply_score(conn, c):
    """Administrator chose the offline version: run it through the real score route (same permission, lock, range rules and
    audit trail) as the approving administrator."""
    payload = json.loads(c["client_payload"] or "{}")
    term = _hooks["current_term"](conn)
    if not term or term["id"] != payload.get("term_id"):
        return False, "The active term has changed since this score was entered; enter it manually."
    body = dict(payload.get("body") or {})
    body["reason"] = (body.get("reason") or f"Approved by administrator after offline conflict #{c['id']}")[:300]
    with current_app.test_client() as client:
        with client.session_transaction() as s:
            s.update(dict(session))
        resp = client.post(f"/api/scores/{payload['class_id']}/{payload['subject_id']}/row", json=body,
                           headers={"X-CSRF-Token": session.get("_csrf_token", "")})
        data = resp.get_json(silent=True) or {}
    if resp.status_code != 200 or not data.get("ok"):
        return False, data.get("error") or f"The score could not be applied ({resp.status_code})."
    return True, "Offline score applied."
