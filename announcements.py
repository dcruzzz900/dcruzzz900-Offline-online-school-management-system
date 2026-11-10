"""V104: temporary dashboard announcement banners.

* Super Admin (platform admin) can announce to ALL schools or ONE school; a School Admin only ever to their OWN school.
* Banners show on the dashboards of the chosen audience (everyone / admins / teachers / students / parents).
* Every announcement has an optional start and an expiry (entered in the school's local time, stored in UTC); it disappears at
  expiry, and expired rows (and their dismissals) are purged automatically a day later.
* A dismissible banner can be closed by each user; the dismissal is remembered per user.
* Tenant isolation is enforced in every query (school_id = the viewer's school, or NULL = platform-wide).
"""
import datetime
import time

from flask import abort, flash, redirect, render_template, request, session, url_for

AUDIENCES = (("all", "Everyone"), ("admin", "School administrators"), ("teacher", "Teachers / form teachers"),
             ("student", "Students"), ("parent", "Parents / guardians"))
LEVELS = (("info", "Information"), ("success", "Good news"), ("warning", "Important / warning"))
_VALID_AUD = {a for a, _ in AUDIENCES}
_VALID_LEVEL = {a for a, _ in LEVELS}
_last_purge = {"t": 0.0}


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def register_announcements(app, h):
    get_db = h["get_db"]
    login_required = h["login_required"]
    platform_admin_required = h["platform_admin_required"]
    log_audit = h["log_audit"]
    school_tz = h["school_tz"]

    # ------------------------------------------------------------------ helpers
    def viewer():
        """(actor_type, actor_id, audience_role, school_id) for whoever is logged in, or None."""
        if session.get("user_id"):
            role = session.get("role")
            aud = "admin" if role in ("admin", "sub_admin") else ("teacher" if role == "teacher" else role)
            return "user", session["user_id"], aud, session.get("school_id")
        if session.get("student_id"):
            return "student", session["student_id"], "student", session.get("school_id")
        if session.get("parent_id"):
            return "parent", session["parent_id"], "parent", session.get("school_id")
        return None

    def local_to_utc(conn, school_id, text):
        """'2026-11-20T17:30' typed in the school's local time -> naive UTC datetime (None if blank/invalid)."""
        text = (text or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                naive = datetime.datetime.strptime(text, fmt)
                if fmt == "%Y-%m-%d":
                    naive = naive.replace(hour=23, minute=59)       # a bare date means "until the end of that day"
                tz = school_tz(conn, school_id) if school_id else datetime.timezone(datetime.timedelta(hours=1))
                return naive.replace(tzinfo=tz).astimezone(datetime.timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
        return None

    def purge_expired(conn):
        """Remove announcements that expired more than a day ago (at most once an hour per process)."""
        if time.time() - _last_purge["t"] < 3600:
            return
        _last_purge["t"] = time.time()
        cutoff = _fmt(_utc_now() - datetime.timedelta(days=1))
        conn.execute("DELETE FROM announcement_dismissals WHERE announcement_id IN "
                     "(SELECT id FROM announcements WHERE expires_at IS NOT NULL AND expires_at < ?)", (cutoff,))
        conn.execute("DELETE FROM announcements WHERE expires_at IS NOT NULL AND expires_at < ?", (cutoff,))
        conn.commit()

    def active_for(conn, v):
        actor_type, actor_id, aud, school_id = v
        now = _fmt(_utc_now())
        rows = conn.execute(
            "SELECT a.* FROM announcements a WHERE a.is_active=1 AND (a.school_id IS NULL OR a.school_id=?) "
            "AND (a.audience='all' OR a.audience=?) AND (a.starts_at IS NULL OR a.starts_at<=?) "
            "AND (a.expires_at IS NULL OR a.expires_at>?) "
            "AND NOT EXISTS (SELECT 1 FROM announcement_dismissals d WHERE d.announcement_id=a.id AND d.actor_type=? AND d.actor_id=?) "
            "ORDER BY a.id DESC LIMIT 5", (school_id, aud, now, now, actor_type, actor_id)).fetchall()
        return rows

    # ------------------------------------------------------------------ banners on dashboards
    @app.context_processor
    def inject_announcement_banners():
        try:
            ep = request.endpoint or ""
            if "dashboard" not in ep and ep not in ("parent_home", "student_home"):
                return {}
            v = viewer()
            if not v:
                return {}
            conn = get_db()
            try:
                purge_expired(conn)
                return {"announcement_banners": active_for(conn, v)}
            finally:
                conn.close()
        except Exception:
            return {}

    @app.route("/announcements/<int:ann_id>/dismiss", methods=["POST"])
    def announcement_dismiss(ann_id):
        v = viewer()
        if not v:
            abort(403)
        actor_type, actor_id, aud, school_id = v
        conn = get_db()
        row = conn.execute("SELECT * FROM announcements WHERE id=? AND (school_id IS NULL OR school_id=?) AND (audience='all' OR audience=?)",
                           (ann_id, school_id, aud)).fetchone()
        if row and row["dismissible"]:
            try:
                conn.execute("INSERT INTO announcement_dismissals(announcement_id, actor_type, actor_id) VALUES (?,?,?)", (ann_id, actor_type, actor_id))
                conn.commit()
            except Exception:
                conn.rollback()      # already dismissed
        conn.close()
        return redirect(request.referrer or url_for("dashboard"))

    # ------------------------------------------------------------------ create / list / remove
    def _create(conn, school_id, created_by, role_label):
        title = (request.form.get("title") or "").strip()[:150]
        message = (request.form.get("message") or "").strip()[:2000]
        audience = request.form.get("audience") if request.form.get("audience") in _VALID_AUD else "all"
        level = request.form.get("level") if request.form.get("level") in _VALID_LEVEL else "info"
        dismissible = 1 if request.form.get("dismissible") else 0
        tz_school = school_id or (int(request.form.get("tz_school_id")) if (request.form.get("tz_school_id") or "").isdigit() else None)
        starts = local_to_utc(conn, tz_school, request.form.get("starts_at"))
        expires = local_to_utc(conn, tz_school, request.form.get("expires_at"))
        errors = []
        if not title:
            errors.append("Please enter a title.")
        if not message:
            errors.append("Please enter the announcement message.")
        if request.form.get("expires_at", "").strip() and expires is None:
            errors.append("The expiry date/time is not valid.")
        if expires is None:
            errors.append("Choose when the announcement expires, so it does not stay on dashboards forever.")
        if expires is not None and expires <= _utc_now():
            errors.append("The expiry must be in the future.")
        if expires is not None and starts is not None and expires <= starts:
            errors.append("The expiry must be after the start.")
        if errors:
            for e in errors:
                flash(e, "error")
            return None
        cur = conn.execute(
            "INSERT INTO announcements(school_id, title, message, audience, level, dismissible, starts_at, expires_at, created_by, created_by_label) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (school_id, title, message, audience, level, dismissible, _fmt(starts) if starts else None, _fmt(expires), created_by, role_label))
        return cur.lastrowid

    @app.route("/admin/announcements", methods=["GET", "POST"])
    @login_required("admin", "sub_admin")
    def school_announcements():
        conn = get_db()
        sid = session.get("school_id")
        if request.method == "POST":
            if request.form.get("act") == "remove":
                conn.execute("UPDATE announcements SET is_active=0 WHERE id=? AND school_id=?", (request.form.get("id", type=int), sid))
                conn.commit()
                flash("Announcement removed.", "success")
            else:
                new_id = _create(conn, sid, session.get("user_id"), f"{session.get('name') or 'School Admin'}")
                if new_id:
                    log_audit(conn, "staff", session.get("name"), "announcement_created", details=f"announcement #{new_id}", school_id=sid)
                    conn.commit()
                    flash("Announcement published. It will show on the chosen dashboards until it expires.", "success")
            conn.close()
            return redirect(url_for("school_announcements"))
        purge_expired(conn)
        rows = conn.execute("SELECT * FROM announcements WHERE school_id=? ORDER BY id DESC LIMIT 100", (sid,)).fetchall()
        now = _fmt(_utc_now())
        conn.close()
        return render_template("admin_announcements.html", scope="school", rows=rows, now=now, audiences=AUDIENCES, levels=LEVELS, schools=[])

    @app.route("/platform/announcements", methods=["GET", "POST"])
    @platform_admin_required
    def platform_announcements():
        conn = get_db()
        if request.method == "POST":
            if request.form.get("act") == "remove":
                conn.execute("UPDATE announcements SET is_active=0 WHERE id=? AND created_by_label LIKE 'Platform Admin%'", (request.form.get("id", type=int),))
                conn.commit()
                flash("Announcement removed.", "success")
            else:
                target = request.form.get("school_id")
                school_id = int(target) if (target or "").isdigit() else None          # blank = every school
                if school_id and not conn.execute("SELECT 1 FROM schools WHERE id=?", (school_id,)).fetchone():
                    flash("That school does not exist.", "error")
                else:
                    new_id = _create(conn, school_id, None, f"Platform Admin: {session.get('platform_admin_name')}")
                    if new_id:
                        log_audit(conn, "platform_admin", session.get("platform_admin_name"), "announcement_created",
                                  details=f"announcement #{new_id} to {school_id or 'ALL schools'}", school_id=school_id)
                        conn.commit()
                        flash("Announcement published.", "success")
            conn.close()
            return redirect(url_for("platform_announcements"))
        purge_expired(conn)
        rows = conn.execute("SELECT a.*, s.name AS school_name FROM announcements a LEFT JOIN schools s ON s.id=a.school_id "
                            "WHERE a.created_by_label LIKE 'Platform Admin%' ORDER BY a.id DESC LIMIT 100").fetchall()
        schools = conn.execute("SELECT id, name FROM schools ORDER BY name").fetchall()
        now = _fmt(_utc_now())
        conn.close()
        return render_template("admin_announcements.html", scope="platform", rows=rows, now=now, audiences=AUDIENCES, levels=LEVELS, schools=schools)
