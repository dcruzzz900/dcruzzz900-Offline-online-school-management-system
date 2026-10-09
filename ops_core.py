"""Operational rules shared by routes: school time, strict attendance dates, staff roles, result workflow, notifications.

Every function takes an open sqlite connection and explicit school ids; nothing here reads a school/tenant id from a request."""
import datetime
import json
import sqlite3

DEFAULT_TZ = "Africa/Lagos"

# ------------------------------------------------------------------ school time (server clock, school timezone)
def _tz(name):
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(name or DEFAULT_TZ)
    except Exception:
        # tzdata missing on the host: Lagos has no DST, so a fixed UTC+1 is exact; anything else falls back to UTC.
        return datetime.timezone(datetime.timedelta(hours=1)) if (name or DEFAULT_TZ) == DEFAULT_TZ else datetime.timezone.utc


def school_timezone_name(conn, school_id):
    row = conn.execute("SELECT timezone FROM schools WHERE id=?", (school_id,)).fetchone()
    return (row["timezone"] if row and row["timezone"] else DEFAULT_TZ)


def school_now(conn, school_id, _override=None):
    """(aware datetime in the school's timezone, timezone name). Always the SERVER clock - never the device clock.
    `_override` exists only so tests can pin the clock."""
    name = school_timezone_name(conn, school_id)
    base = _override or datetime.datetime.now(datetime.timezone.utc)
    return base.astimezone(_tz(name)), name


def server_stamp(conn, school_id):
    now, name = school_now(conn, school_id)
    return now.isoformat(timespec="seconds"), name


MSG_FUTURE = "Future attendance cannot be recorded. Please record attendance on the correct date."
MSG_BACKDATED = "Backdated attendance is not allowed. Attendance must be recorded on the current date."


def check_attendance_date(conn, school_id, submitted):
    """Core rule: the submitted date MUST equal the school's current date on the server. Returns an error message or None.
    A form that sends no date at all is fine - the server then uses today's date itself."""
    today = school_now(conn, school_id)[0].date()
    if submitted in (None, ""):
        return None
    try:
        d = datetime.date.fromisoformat(str(submitted).strip())
    except ValueError:
        return MSG_BACKDATED if False else "That is not a valid attendance date. Attendance is recorded for the current date only."
    if d > today:
        return MSG_FUTURE
    if d < today:
        return MSG_BACKDATED
    return None


# ------------------------------------------------------------------ staff roles (multiple, simultaneous)
LEGACY_ROLE_NAMES = {
    "Form Teacher": "Class Teacher / Form Teacher", "Class Teacher": "Class Teacher / Form Teacher",
}


def staff_roles(conn, user_id, school_id):
    """Every ACTIVE role the staff member holds right now (from active role assignments), canonical names, ordered."""
    today = datetime.date.today().isoformat()
    rows = conn.execute(
        "SELECT DISTINCT role FROM role_assignments WHERE user_id=? AND school_id=? AND status='active' "
        "AND (start_date IS NULL OR start_date<=?) AND (end_date IS NULL OR end_date>=?) ORDER BY id", (user_id, school_id, today, today)).fetchall()
    return [LEGACY_ROLE_NAMES.get(r["role"], r["role"]) for r in rows]


def has_permission_anywhere(conn, user_id, school_id, permission):
    today = datetime.date.today().isoformat()
    return bool(conn.execute(
        "SELECT 1 FROM role_assignments ra JOIN role_assignment_permissions p ON p.assignment_id=ra.id "
        "WHERE ra.user_id=? AND ra.school_id=? AND ra.status='active' AND (ra.start_date IS NULL OR ra.start_date<=?) AND (ra.end_date IS NULL OR ra.end_date>=?) "
        "AND p.permission=? AND p.granted=1 "
        "AND NOT EXISTS (SELECT 1 FROM role_assignment_permissions d JOIN role_assignments ra2 ON ra2.id=d.assignment_id WHERE ra2.user_id=ra.user_id AND ra2.status='active' AND d.permission=p.permission AND d.granted=0 AND ra2.id=ra.id) "
        "LIMIT 1", (user_id, school_id, today, today, permission)).fetchone())


# ------------------------------------------------------------------ result workflow
STATES = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "RETURNED", "APPROVED", "PUBLISHED", "REOPENED"]
STATE_LABELS = {"DRAFT": "Draft", "SUBMITTED": "Submitted for review", "UNDER_REVIEW": "Under review", "RETURNED": "Returned for correction",
                "APPROVED": "Approved - ready to publish", "PUBLISHED": "Published", "REOPENED": "Reopened for correction"}
EDITABLE_STATES = {"DRAFT", "RETURNED", "REOPENED"}          # scores / class-level result info may be changed only here
TRANSITIONS = {  # action -> (allowed from, to, needs reason)
    "submit": ({"DRAFT", "RETURNED", "REOPENED"}, "SUBMITTED", False),
    "start_review": ({"SUBMITTED"}, "UNDER_REVIEW", False),
    "return": ({"UNDER_REVIEW", "SUBMITTED"}, "RETURNED", True),
    "approve": ({"UNDER_REVIEW"}, "APPROVED", False),
    "publish": ({"APPROVED"}, "PUBLISHED", False),
    "reopen": ({"PUBLISHED"}, "REOPENED", True),
}


def get_batch(conn, school_id, class_id, term_id):
    """The workflow record for one class in one term (created on first use). A term that was already published before
    the workflow existed starts as PUBLISHED so nothing that parents already see disappears."""
    row = conn.execute("SELECT * FROM result_batches WHERE class_id=? AND term_id=? AND school_id=?", (class_id, term_id, school_id)).fetchone()
    if row:
        return row
    legacy = conn.execute("SELECT is_published FROM terms WHERE id=?", (term_id,)).fetchone()
    status = "PUBLISHED" if legacy and legacy["is_published"] else "DRAFT"
    tenant = (conn.execute("SELECT COALESCE(NULLIF(tenant_id,''),CAST(id AS TEXT)) FROM schools WHERE id=?", (school_id,)).fetchone() or [str(school_id)])[0]
    conn.execute("INSERT OR IGNORE INTO result_batches(school_id,tenant_id,class_id,term_id,status) VALUES(?,?,?,?,?)", (school_id, tenant, class_id, term_id, status))
    return conn.execute("SELECT * FROM result_batches WHERE class_id=? AND term_id=? AND school_id=?", (class_id, term_id, school_id)).fetchone()


def is_published(conn, school_id, class_id, term_id):
    return get_batch(conn, school_id, class_id, term_id)["status"] == "PUBLISHED"


def is_editable(conn, school_id, class_id, term_id):
    return get_batch(conn, school_id, class_id, term_id)["status"] in EDITABLE_STATES


def validate_for_submission(conn, school_id, class_id, term_id):
    """Returns (blocking_problems, warnings). Blocking: a subject nobody has scored, impossible scores, or no students."""
    problems, warnings = [], []
    students = conn.execute("SELECT id FROM students WHERE class_id=? AND is_active=1", (class_id,)).fetchall()
    if not students:
        problems.append("The class has no active students.")
        return problems, warnings
    ids = [s["id"] for s in students]
    subjects = conn.execute("SELECT cs.subject_id, s.name FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id WHERE cs.class_id=? AND s.school_id=?", (class_id, school_id)).fetchall()
    if not subjects:
        problems.append("The class has no subjects assigned.")
    ph = ",".join("?" * len(ids))
    for sj in subjects:
        n = conn.execute(f"SELECT COUNT(*) FROM scores WHERE term_id=? AND subject_id=? AND student_id IN ({ph})", (term_id, sj["subject_id"], *ids)).fetchone()[0]
        if n == 0:
            problems.append(f"{sj['name']}: no scores have been entered.")
        elif n < len(ids):
            warnings.append(f"{sj['name']}: {len(ids) - n} of {len(ids)} students have no score.")
    bad = conn.execute(
        f"SELECT st.first_name, st.last_name, sub.name FROM scores sc JOIN students st ON st.id=sc.student_id JOIN subjects sub ON sub.id=sc.subject_id "
        f"WHERE sc.term_id=? AND sc.student_id IN ({ph}) AND (sc.ca1<0 OR sc.ca2<0 OR COALESCE(sc.ca3,0)<0 OR sc.exam<0 OR (sc.ca1+sc.ca2+COALESCE(sc.ca3,0)+sc.exam)>100) LIMIT 5",
        (term_id, *ids)).fetchall()
    for b in bad:
        problems.append(f"{b['last_name']} {b['first_name']} - {b['name']}: invalid score or total above 100.")
    return problems, warnings


def log_publication(conn, school_id, batch, action, previous, new, reason, actor):
    now, tz = school_now(conn, school_id)
    conn.execute(
        "INSERT INTO result_publication_log(school_id,tenant_id,batch_id,class_id,term_id,action,previous_status,new_status,reason,actor_id,actor_name,actor_role,action_date,server_timestamp,school_timezone) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (school_id, batch["tenant_id"], batch["id"], batch["class_id"], batch["term_id"], action, previous, new, reason,
         actor.get("id"), actor.get("name"), actor.get("roles"), now.date().isoformat(), now.isoformat(timespec="seconds"), tz))


def transition(conn, school_id, class_id, term_id, action, actor, reason=None):
    """Move one class's result through the workflow. The caller has already checked the actor's permission for `action`.
    Raises ValueError with a user-safe message when the move is not allowed. The caller commits."""
    if action not in TRANSITIONS:
        raise ValueError("Unknown workflow action.")
    allowed_from, to, needs_reason = TRANSITIONS[action]
    batch = get_batch(conn, school_id, class_id, term_id)
    if batch["status"] not in allowed_from:
        raise ValueError(f"This result is {STATE_LABELS[batch['status']].lower()}; it cannot be moved with '{action.replace('_', ' ')}' from there.")
    reason = (reason or "").strip()[:400]
    if needs_reason and len(reason) < 5:
        raise ValueError("A reason is required (at least 5 characters).")
    if action == "submit":
        problems, _w = validate_for_submission(conn, school_id, class_id, term_id)
        if problems:
            raise ValueError("The result cannot be submitted yet: " + " ".join(problems[:6]))
    now, _tz_name = school_now(conn, school_id)
    stamp = now.isoformat(timespec="seconds")
    cols = {"submit": ("submitted_by", "submitted_at"), "start_review": ("reviewed_by", "reviewed_at"), "approve": ("approved_by", "approved_at"), "publish": ("published_by", "published_at")}
    sets, args = ["status=?", "last_reason=?", "updated_at=CURRENT_TIMESTAMP"], [to, reason or None]
    if action in cols:
        sets += [f"{cols[action][0]}=?", f"{cols[action][1]}=?"]
        args += [actor.get("id"), stamp]
    conn.execute(f"UPDATE result_batches SET {', '.join(sets)} WHERE id=?", [*args, batch["id"]])
    log_publication(conn, school_id, batch, action, batch["status"], to, reason or None, actor)
    if action == "publish":
        # keep the legacy term-level flag meaningful: the term counts as published once any class has been officially published
        conn.execute("UPDATE terms SET is_published=1 WHERE id=?", (term_id,))
    return batch["status"], to


# ------------------------------------------------------------------ notifications (per-reader read state)
def _visible_where(reader_type):
    return {"staff": ("all", "teacher", "admin"), "student": ("all", "student"), "parent": ("all", "parent")}[reader_type]


def visible_notifications(conn, reader_type, reader_id, school_id, role=None, limit=200):
    targets = list(_visible_where(reader_type))
    if reader_type == "staff" and role in ("admin", "sub_admin"):
        targets = ["all", "teacher", "admin"]
    elif reader_type == "staff":
        targets = ["all", "teacher"]
    ph = ",".join("?" * len(targets))
    legacy = {"staff": "users", "student": "students", "parent": "parent_accounts"}[reader_type]
    marker = (conn.execute(f"SELECT COALESCE(last_notification_seen_id,0) FROM {legacy} WHERE id=?", (reader_id,)).fetchone() or [0])[0] or 0
    rows = conn.execute(
        f"SELECT n.*, (CASE WHEN n.id<=? OR r.id IS NOT NULL THEN 1 ELSE 0 END) AS is_read FROM notifications n "
        f"LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.reader_type=? AND r.reader_id=? "
        f"WHERE (n.school_id=? OR n.school_id IS NULL) AND n.target_role IN ({ph}) ORDER BY n.id DESC LIMIT ?",
        (marker, reader_type, reader_id, school_id, *targets, limit)).fetchall()
    return rows


def unread_count(conn, reader_type, reader_id, school_id, role=None):
    return sum(1 for r in visible_notifications(conn, reader_type, reader_id, school_id, role, limit=500) if not r["is_read"])


def mark_read(conn, reader_type, reader_id, school_id, notification_id=None, role=None):
    """Mark one notification (or all visible ones) as read for this reader only. Returns how many were newly marked."""
    n = 0
    for r in visible_notifications(conn, reader_type, reader_id, school_id, role, limit=500):
        if r["is_read"] or (notification_id is not None and r["id"] != notification_id):
            continue
        conn.execute("INSERT OR IGNORE INTO notification_reads(notification_id,reader_type,reader_id) VALUES(?,?,?)", (r["id"], reader_type, reader_id))
        n += 1
    return n
