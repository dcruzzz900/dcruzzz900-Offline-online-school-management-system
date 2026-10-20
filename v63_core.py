"""V63 core helpers (no Flask app dependency, so db/app/tests can all import them).

* School time: the server clock in the school's own timezone (default Africa/Lagos). The device clock is never read.
* Attendance: the submitted date must equal the school's current date; every record/correction is audited.
* Result publication: one workflow row per school + class + term. Anything printable/downloadable needs 'published'.
"""
import datetime
import zoneinfo

DEFAULT_TZ = "Africa/Lagos"

FUTURE_ATTENDANCE_MSG = "Future attendance cannot be recorded. Please record attendance on the correct date."
BACKDATED_ATTENDANCE_MSG = "Backdated attendance is not allowed. Attendance must be recorded on the current date."

# ---------------------------------------------------------------- school time
def school_tz(conn, school_id):
    name = DEFAULT_TZ
    try:
        row = conn.execute("SELECT timezone FROM schools WHERE id=?", (school_id,)).fetchone()
        if row and row["timezone"]:
            name = row["timezone"]
    except Exception:
        pass
    for candidate in (name, DEFAULT_TZ):
        try:
            return zoneinfo.ZoneInfo(candidate)
        except Exception:
            continue
    return datetime.timezone(datetime.timedelta(hours=1))   # WAT, UTC+1


def school_now(conn, school_id):
    """Server time in the school's timezone. Never derived from anything the browser sends."""
    return datetime.datetime.now(datetime.timezone.utc).astimezone(school_tz(conn, school_id))


def school_today(conn, school_id):
    return school_now(conn, school_id).date().isoformat()


def server_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def friendly_now(conn, school_id):
    """'Friday, 03/10/2026 — 7:02 PM' in the school's timezone."""
    n = school_now(conn, school_id)
    hour = n.hour % 12 or 12
    return f"{n.strftime('%A')}, {n.strftime('%d/%m/%Y')} — {hour}:{n.minute:02d} {'AM' if n.hour < 12 else 'PM'}"


def validate_attendance_date(conn, school_id, submitted):
    """Core rule: the submitted date MUST equal the school's current date according to the server.
    An empty value means 'use the server date'. Returns (ok, message)."""
    today = school_today(conn, school_id)
    value = (submitted or "").strip()
    if not value or value == today:
        return True, ""
    try:
        d = datetime.date.fromisoformat(value)
    except ValueError:
        return False, BACKDATED_ATTENDANCE_MSG
    return False, (FUTURE_ATTENDANCE_MSG if d > datetime.date.fromisoformat(today) else BACKDATED_ATTENDANCE_MSG)


def audit_attendance(conn, *, school_id, subject_type, subject_id, attendance_date, status, previous_status=None, action="record",
                     recorded_by=None, recorder_name=None, recorder_role=None, class_id=None, class_arm=None, term_id=None,
                     correction_reason=None):
    tenant = conn.execute("SELECT tenant_id FROM schools WHERE id=?", (school_id,)).fetchone()
    corrected = action == "correct"
    conn.execute(
        "INSERT INTO attendance_audit(school_id,tenant_id,subject_type,subject_id,class_id,class_arm,term_id,attendance_date,status,"
        "previous_status,action,recorded_by,recorder_name,recorder_role,correction_reason,corrected_by,corrected_at,server_timestamp) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (school_id, tenant["tenant_id"] if tenant else None, subject_type, subject_id, class_id, class_arm, term_id, attendance_date,
         status, previous_status, action, recorded_by, recorder_name, recorder_role, correction_reason,
         recorded_by if corrected else None, server_stamp() if corrected else None, server_stamp()))


# ---------------------------------------------------------------- result publication
STATES = ("draft", "submitted", "under_review", "returned", "approved", "published", "reopened")
STATE_LABELS = {"draft": "Draft", "submitted": "Submitted for review", "under_review": "Under review",
                "returned": "Returned for correction", "approved": "Approved — ready to publish",
                "published": "Published", "reopened": "Reopened — correction"}
LOCKED_STATES = ("submitted", "under_review", "approved", "published")

PERMISSIONS = {
    "result.submit": "Submit results for review",
    "result.review": "Start a review / return results for correction",
    "result.approve": "Give final approval",
    "result.publish": "Publish results officially",
    "result.reopen": "Reopen / unpublish published results",
}

# action -> (allowed from, new status, permission(s) that authorise it; None = submit rule, reason mandatory?)
TRANSITIONS = {
    "submit": ({"draft", "returned", "reopened"}, "submitted", None, False),
    "start_review": ({"submitted"}, "under_review", ("result.review",), False),
    "approve": ({"under_review"}, "approved", ("result.approve",), False),
    "return": ({"under_review"}, "returned", ("result.review", "result.approve"), True),
    "publish": ({"approved"}, "published", ("result.publish",), False),
    "reopen": ({"published"}, "reopened", ("result.reopen",), True),
}


def get_publication(conn, school_id, class_id, term_id):
    return conn.execute("SELECT * FROM result_publication WHERE school_id=? AND class_id=? AND term_id=?",
                        (school_id, class_id, term_id)).fetchone()


def publication_status(conn, school_id, class_id, term_id):
    row = get_publication(conn, school_id, class_id, term_id)
    return row["status"] if row else "draft"


def is_published(conn, school_id, class_id, term_id):
    return publication_status(conn, school_id, class_id, term_id) == "published"


def result_locked(conn, school_id, class_id, term_id):
    """Scores are locked against normal editing from submission until the result is returned or reopened."""
    return publication_status(conn, school_id, class_id, term_id) in LOCKED_STATES


def has_workflow_permission(conn, user_id, permission):
    """Explicit RBAC only: holding a title such as Principal never grants publication by itself."""
    if not user_id:
        return False
    row = conn.execute("SELECT granted FROM result_workflow_permissions WHERE user_id=? AND permission=?",
                       (user_id, permission)).fetchone()
    return bool(row and row["granted"])


def sync_term_flag(conn, school_id, term_id):
    """terms.is_published means 'this term has at least one published class' (older screens read it). The real,
    per-class decision always comes from result_publication. Returns True when the flag flipped 0 -> 1."""
    any_pub = conn.execute("SELECT 1 FROM result_publication WHERE school_id=? AND term_id=? AND status='published' LIMIT 1",
                           (school_id, term_id)).fetchone()
    before = conn.execute("SELECT is_published FROM terms WHERE id=?", (term_id,)).fetchone()
    want = 1 if any_pub else 0
    conn.execute("UPDATE terms SET is_published=? WHERE id=?", (want, term_id))
    return bool(before and not before["is_published"] and want)
