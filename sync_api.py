"""
Offline sync API.

This module is intentionally kept separate from app.py's page routes: it
speaks JSON only, is used by the offline-capable JS (static/js/offline-*.js)
running in the browser/PWA shell, and is the ONE place that decides what an
offline device is allowed to read or write. Every function in here treats
the request body as untrusted and re-derives the caller's school_id/role
from either their Flask session or their verified device credential —
never from anything the client sent — which is what makes multi-school
isolation hold even if a device's local database were tampered with.

------------------------------------------------------------------------
Identity
------------------------------------------------------------------------
A caller is authenticated one of two ways:
  1. A normal online Flask session (cookie) — same as every other route.
  2. An offline device credential presented as two headers:
       X-Device-Id:     the device_id returned by /api/offline/enroll
       X-Device-Secret: the plaintext secret returned at enrollment time
     (kept encrypted at rest on the device — see offline-auth.js — and
     only held in memory after the user unlocks it with their PIN).
Either way, resolve_identity() below is the only source of truth for
{user_id, school_id, role, position}. Route handlers never read school_id
from query params or JSON bodies.

------------------------------------------------------------------------
Entity registry
------------------------------------------------------------------------
ENTITIES describes every table that can be synced, and is the single place
that would need a new entry to bring another part of the app offline (see
OFFLINE_ARCHITECTURE.md for the migration checklist). Each entry says:
  table            - the SQLite table
  fields           - columns an offline client may set directly
  school_col       - 'direct' if the table has its own school_id column,
                     or a callable(conn, row_dict) -> school_id | None that
                     resolves it via a join, used to validate a write
                     before it touches the database
  scope_ids        - callable(conn, identity) -> 'all' | set(of allowed
                     foreign-key ids) used to restrict which rows a
                     non-admin caller may read/write (e.g. a teacher's own
                     classes). Returning 'all' means no extra restriction
                     beyond school_id.
  scope_col        - the column on `table` that scope_ids restricts (e.g.
                     'class_id'), or None if scope_ids always returns 'all'
                     for every role this entity permits
  can_write        - set of roles allowed to push changes
  can_read         - set of roles allowed to pull/bootstrap this entity
  before_write     - optional callable(conn, identity, fields_dict) that
                     may mutate fields_dict (e.g. hash a password) or raise
                     SyncValidationError to reject the record
"""
import datetime
import json
import re
import sqlite3
from functools import wraps

from flask import Blueprint, request, session, jsonify, g

from db import (
    get_db, new_client_uuid, now_iso, issue_device_credential,
    verify_device_credential, record_sync_conflict, record_sync_log,
    form_teacher_class_ids, is_main_admin, get_school, POSITION_LABELS,
    recompute_attendance, upsert_enrollment, FULL_ACCESS_POSITIONS, grading_problems,
    grade_band_problems, get_visible_notifications,
)
from werkzeug.security import generate_password_hash

from sync_rules import (
    POLICY_MERGE, POLICY_LATEST_WINS, POLICY_MANUAL,
    decide, parse_ts, values_equal,
)

sync_bp = Blueprint("sync_api", __name__)

STAFF_ROLES = ("admin", "sub_admin", "teacher")
ADMIN_ROLES = ("admin", "sub_admin")


class SyncValidationError(Exception):
    pass


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------

def resolve_identity(conn):
    """Returns a dict {user_id, school_id, role, position, device_id} or
    None. device_id is present only when authenticated via an offline
    credential (useful for logging / conflict attribution)."""
    device_id = request.headers.get("X-Device-Id")
    device_secret = request.headers.get("X-Device-Secret")
    if device_id and device_secret:
        status, cred = verify_device_credential(conn, device_id, device_secret)
        if status != "ok":
            g.sync_auth_reason = status      # expired / revoked / school_suspended / ...
            return None
        # Role, position and school come from the user's record AS IT IS NOW,
        # not from the snapshot taken when the device enrolled. Otherwise
        # demoting a sub-admin (or moving a teacher) would leave every device
        # they had already enrolled quietly holding the old, higher access.
        user = conn.execute(
            "SELECT school_id, role, position, is_active FROM users WHERE id=?", (cred["user_id"],)
        ).fetchone()
        if (not user or user["school_id"] != cred["school_id"]
                or user["role"] not in STAFF_ROLES or not user["is_active"]):
            g.sync_auth_reason = "revoked"
            return None
        return {
            "user_id": cred["user_id"],
            "school_id": cred["school_id"],
            "role": user["role"],
            "position": user["position"],
            "device_id": device_id,
        }
    if "user_id" in session and session.get("role") in STAFF_ROLES:
        return {
            "user_id": session["user_id"],
            "school_id": session["school_id"],
            "role": session["role"],
            "position": session.get("position"),
            "device_id": request.headers.get("X-Device-Id"),  # online but device already enrolled
        }
    return None


def require_identity(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        conn = get_db()
        identity = resolve_identity(conn)
        if identity is None:
            conn.close()
            # `status` tells a device WHY (expired credential, revoked, school
            # suspended...) so it can show the right message and keep the
            # person's unsynced work safe instead of just retrying forever.
            return jsonify({"error": "not_authenticated",
                            "status": getattr(g, "sync_auth_reason", "not_authenticated")}), 401
        g.sync_conn = conn
        g.sync_identity = identity
        try:
            return f(*args, **kwargs)
        finally:
            conn.close()
    return wrapped


# ---------------------------------------------------------------------------
# Per-entity scoping helpers
# ---------------------------------------------------------------------------

def _teacher_class_ids(conn, identity):
    if identity["role"] in ADMIN_ROLES:
        return "all"
    return set(form_teacher_class_ids(conn, identity["user_id"]))


def _teacher_subject_class_ids(conn, identity):
    """Classes a teacher has been assigned at least one subject in (used
    for scores, which are entered per class+subject, not just by the form
    teacher)."""
    if identity["role"] in ADMIN_ROLES:
        return "all"
    rows = conn.execute(
        "SELECT DISTINCT class_id FROM class_subjects WHERE teacher_id=?", (identity["user_id"],)
    ).fetchall()
    return {r["class_id"] for r in rows}


def _admin_only_scope(conn, identity):
    return "all" if identity["role"] in ADMIN_ROLES else set()


def _all_scope(conn, identity):
    """Every staff role may read this entity in full — used for read-only
    reference data (terms, sessions, the class/subject/teacher map) that
    every offline screen needs cached locally to build its own dropdowns,
    even though nobody writes it through the sync API."""
    return "all"


def _school_via_session(conn, row):
    session_id = row.get("session_id")
    if session_id is None:
        return None
    r = conn.execute("SELECT school_id FROM sessions WHERE id=?", (session_id,)).fetchone()
    return r["school_id"] if r else None


def _school_via_class(conn, row):
    class_id = row.get("class_id")
    if class_id is None:
        return None
    r = conn.execute("SELECT school_id FROM classes WHERE id=?", (class_id,)).fetchone()
    return r["school_id"] if r else None


def _school_via_student(conn, row):
    student_id = row.get("student_id")
    if student_id is None:
        return None
    r = conn.execute(
        "SELECT c.school_id FROM students s JOIN classes c ON c.id=s.class_id WHERE s.id=?",
        (student_id,),
    ).fetchone()
    return r["school_id"] if r else None


def _restrict_principal_comment(conn, identity, fields):
    if "principal_comment" in fields and identity["role"] not in ADMIN_ROLES:
        # Client UI never shows this field to a teacher, but a hand-crafted
        # request shouldn't be able to set it either — comments are one
        # entity but the two comment fields have different authors.
        fields.pop("principal_comment")
        fields.pop("principal_signed_date", None)


def _validate_class_category(conn, identity, fields):
    from db import CLASS_CATEGORIES
    if fields.get("category") and fields["category"] not in CLASS_CATEGORIES:
        fields["category"] = None
    for k, limit in (("level", 60), ("arm", 20)):
        if k in fields:
            v = " ".join(str(fields[k] or "").split())[:limit]
            fields[k] = v or None


# A device may send an already-hashed password (so the plaintext never sits in
# its local database) in Werkzeug's PBKDF2 format. The iteration count is
# bounded on both sides: too low is trivially crackable, too high would let a
# crafted account make every login attempt burn server CPU.
_CLIENT_HASH_RE = re.compile(r"pbkdf2:sha256:(\d{5,7})\$([A-Za-z0-9]{8,64})\$([0-9a-f]{64})")
_MIN_CLIENT_ITERATIONS, _MAX_CLIENT_ITERATIONS = 100_000, 1_000_000


def _hash_password_before_write(conn, identity, fields):
    client_hash = fields.pop("password_hash", None)
    plain = fields.pop("password", None)
    if client_hash:
        m = _CLIENT_HASH_RE.fullmatch(str(client_hash))
        if not m or not (_MIN_CLIENT_ITERATIONS <= int(m.group(1)) <= _MAX_CLIENT_ITERATIONS):
            raise SyncValidationError("The password could not be accepted from this device — set it again.")
        fields["password_hash"] = client_hash
    elif plain:
        fields["password_hash"] = generate_password_hash(plain)
    # A generic offline "add teacher/staff" form must not become a way to
    # mint a new main-admin account — that account type is created only at
    # school signup. sub_admin is allowed since admins can already promote
    # someone to sub_admin online today.
    if fields.get("role") not in ("teacher", "sub_admin"):
        fields["role"] = "teacher"
    if fields.get("role") == "sub_admin" and identity["role"] != "admin":
        # Matches the online rule (SCHOOL_MANAGER_ROLES / is_main_admin in
        # db.py): only the main admin can create sub-admins, not another
        # sub-admin acting through this same generic offline path.
        fields["role"] = "teacher"
    if fields.get("position") not in POSITION_LABELS:
        fields.pop("position", None)


def _validate_score(conn, identity, fields):
    """Server-side check of a pushed score row. Offline screens enforce max
    marks in the browser, but the server must not rely on that: a tampered or
    buggy client could otherwise store a CA1 of 500. Limits come from the
    school's own grading configuration (CA3 is only accepted when the school
    has switched it on)."""
    cfg = conn.execute(
        "SELECT ca1_max, ca2_max, ca3_max, exam_max FROM grading_config WHERE school_id=? LIMIT 1",
        (identity["school_id"],),
    ).fetchone()
    limits = {
        "ca1": cfg["ca1_max"] if cfg else 20,
        "ca2": cfg["ca2_max"] if cfg else 20,
        "ca3": (cfg["ca3_max"] if cfg else 0) or 0,
        "exam": cfg["exam_max"] if cfg else 60,
    }
    for name, limit in limits.items():
        if name not in fields:
            continue
        raw = fields[name]
        if raw is None or raw == "":
            fields[name] = 0
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise SyncValidationError(f"{name.upper()} must be a number.")
        if value != value or value < 0:  # NaN or negative
            raise SyncValidationError(f"{name.upper()} can't be negative.")
        if value > limit:
            if name == "ca3" and limit == 0:
                raise SyncValidationError("CA3 is not enabled for this school.")
            raise SyncValidationError(f"{name.upper()} {value:g} is above the maximum of {limit:g}.")
        fields[name] = value


def _validate_grading(conn, identity, fields):
    """Offline edits of the school's maximum marks. Same rules as the online
    Grading Setup screen (db.grading_problems)."""
    cfg = conn.execute("SELECT ca1_max, ca2_max, ca3_max, exam_max FROM grading_config WHERE school_id=? LIMIT 1",
                       (identity["school_id"],)).fetchone()
    merged = dict(cfg) if cfg else {"ca1_max": 20, "ca2_max": 20, "ca3_max": 0, "exam_max": 60}
    for k in ("ca1_max", "ca2_max", "ca3_max", "exam_max"):
        if k in fields:
            try:
                v = float(fields[k] if fields[k] not in (None, "") else 0)
            except (TypeError, ValueError):
                raise SyncValidationError("Maximum marks must be numbers.")
            if v != v or v in (float("inf"), float("-inf")):
                raise SyncValidationError("Maximum marks must be numbers.")
            fields[k] = v
            merged[k] = v
    problems = grading_problems(conn, identity["school_id"], merged["ca1_max"], merged["ca2_max"],
                                merged["ca3_max"] or 0, merged["exam_max"])
    if problems:
        raise SyncValidationError(" ".join(problems))


def _check_grade_band(conn, identity, existing, fields):
    """Runs once the row being edited (if any) is known, so a band never counts as
    overlapping ITSELF."""
    merged = {**(dict(existing) if existing else {}), **fields}
    try:
        lo, hi = float(merged.get("min_score")), float(merged.get("max_score"))
    except (TypeError, ValueError):
        raise SyncValidationError("The scores must be numbers.")
    problems = grade_band_problems(conn, identity["school_id"], merged.get("grade"), lo, hi,
                                   exclude_id=existing["id"] if existing else None)
    if problems:
        raise SyncValidationError(" ".join(problems))
    fields["grade"] = str(merged["grade"]).strip()
    fields["min_score"], fields["max_score"] = lo, hi


def _validate_staff_attendance(conn, identity, fields):
    from db import STAFF_ATTENDANCE_STATUSES
    if "status" in fields and fields["status"] not in STAFF_ATTENDANCE_STATUSES:
        raise SyncValidationError("Staff attendance status must be one of: " + ", ".join(STAFF_ATTENDANCE_STATUSES) + ".")
    if "date" in fields:
        try:
            datetime.date.fromisoformat(str(fields["date"]))
        except ValueError:
            raise SyncValidationError("Attendance date must be YYYY-MM-DD.")


def _validate_attendance(conn, identity, fields):
    if "status" in fields and fields["status"] not in ("present", "absent"):
        raise SyncValidationError("Attendance status must be 'present' or 'absent'.")
    if "date" in fields:
        try:
            datetime.date.fromisoformat(str(fields["date"]))
        except ValueError:
            raise SyncValidationError("Attendance date must be YYYY-MM-DD.")


def _guard_user_update(conn, identity, existing, fields):
    """Who may modify an EXISTING staff account through sync. Mirrors the
    online rules: a sub-admin can never edit (or take over) the main admin
    account, only the main admin manages sub-admins, and nobody changes an
    admin account's role through this generic path."""
    if existing["role"] == "admin" and identity["role"] != "admin":
        raise SyncValidationError("Only the main admin can change the main admin account.")
    if existing["role"] == "admin":
        fields.pop("role", None)  # never re-role the main admin here
        fields.pop("position", None)
    elif existing["role"] == "sub_admin" and identity["role"] != "admin":
        raise SyncValidationError("Only the main admin can change a sub-admin account.")


ENTITIES = {
    "students": {
        "table": "students",
        "fields": ["admission_no", "first_name", "last_name", "other_names", "gender",
                   "class_id", "date_of_birth", "religion", "parent_name", "parent_address",
                   "parent_email", "parent_phone", "parent_relationship", "is_active"],
        "school_col": _school_via_class,
        "scope_ids": _teacher_class_ids,
        "scope_col": "class_id",
        "can_write": set(STAFF_ROLES),
        "can_read": set(STAFF_ROLES),
        "conflict_policy": POLICY_MERGE,
        # Never sent to devices: the student-portal login credentials.
        "never_send": {"password_hash", "username", "last_notification_seen_id"},
    },
    "scores": {
        "table": "scores",
        "fields": ["student_id", "subject_id", "term_id", "ca1", "ca2", "ca3", "exam"],
        "school_col": _school_via_student,
        "scope_ids": _teacher_subject_class_ids,
        "scope_col": None,  # validated via student's class below (needs custom check)
        "can_write": set(STAFF_ROLES),
        "can_read": set(STAFF_ROLES),
        # One score row per student+subject+term. Two devices entering the
        # same cell independently must meet each other as a conflict on the
        # SAME row, not fail on the database's unique constraint.
        "natural_key": ("student_id", "subject_id", "term_id"),
        "conflict_policy": POLICY_MERGE,
        "before_write": _validate_score,
    },
    "attendance_records": {
        "table": "attendance_records",
        "fields": ["student_id", "class_id", "term_id", "date", "status", "recorded_by"],
        "school_col": _school_via_class,
        "scope_ids": _teacher_class_ids,
        "scope_col": "class_id",
        "can_write": set(STAFF_ROLES),
        "can_read": set(STAFF_ROLES),
        "natural_key": ("student_id", "term_id", "date"),
        "conflict_policy": POLICY_LATEST_WINS,
        "before_write": _validate_attendance,
    },
    "staff_attendance": {
        "table": "staff_attendance",
        "fields": ["user_id", "date", "status", "recorded_by"],
        "school_col": "direct",
        "scope_ids": _admin_only_scope,
        "scope_col": None,
        "can_write": set(ADMIN_ROLES),
        "can_read": set(ADMIN_ROLES),
        "natural_key": ("user_id", "date"),
        "conflict_policy": POLICY_LATEST_WINS,
        "before_write": _validate_staff_attendance,
    },
    "student_term_info": {
        "table": "student_term_info",
        "fields": ["student_id", "term_id", "days_present", "days_absent", "days_school_opened",
                   "teacher_comment", "principal_comment", "teacher_signed_date", "principal_signed_date"],
        "school_col": _school_via_student,
        "scope_ids": _teacher_class_ids,
        "scope_col": None,
        "can_write": set(STAFF_ROLES),
        "can_read": set(STAFF_ROLES),
        "before_write": _restrict_principal_comment,
        "natural_key": ("student_id", "term_id"),
        "conflict_policy": POLICY_MERGE,
    },
    "classes": {
        # Row visibility is `_all_scope` (every staff role can see every
        # class in their school — needed just to populate dropdowns);
        # `can_write` below is what actually restricts editing to admins.
        "table": "classes",
        "fields": ["name", "category", "form_teacher_id", "level", "arm"],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(ADMIN_ROLES),
        "can_read": set(STAFF_ROLES),
        "before_write": _validate_class_category,
        "conflict_policy": POLICY_MERGE,
    },
    "subjects": {
        "table": "subjects",
        "fields": ["name"],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(ADMIN_ROLES),
        "can_read": set(STAFF_ROLES),
        "conflict_policy": POLICY_MERGE,
    },
    "users": {
        "table": "users",
        "fields": ["name", "username", "password", "password_hash", "role", "position", "email", "phone", "use_digital_signature"],
        "school_col": "direct",
        "scope_ids": _admin_only_scope,
        "scope_col": None,
        "can_write": set(ADMIN_ROLES),
        "can_read": set(ADMIN_ROLES),
        "before_write": _hash_password_before_write,
        "before_update": _guard_user_update,
        "conflict_policy": POLICY_MANUAL,
        # Credential material never leaves the server. Devices only need
        # names/roles to build dropdowns and the staff list.
        "never_send": {"password_hash", "security_question", "security_answer_hash",
                       "last_notification_seen_id"},
    },
    # Read-only reference data below: can_write is empty, so any push
    # attempt against these is rejected by the generic "not permitted to
    # write this entity" check in _apply_one. They exist in the registry
    # purely so bootstrap/pull can hand them to the offline UI.
    "sessions": {
        "table": "sessions",
        "fields": [],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(),
        "can_read": set(STAFF_ROLES),
    },
    "terms": {
        "table": "terms",
        "fields": [],
        "school_col": _school_via_session,
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(),
        "can_read": set(STAFF_ROLES),
    },
    "class_subjects": {
        # Which teacher takes which subject in which class. Admins can assign and
        # re-assign from a device; REMOVING an assignment (which also deletes that
        # subject's scores for the class) stays an online action.
        "table": "class_subjects",
        "fields": ["class_id", "subject_id", "teacher_id"],
        "school_col": _school_via_class,
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(ADMIN_ROLES),
        "can_read": set(STAFF_ROLES),
        "natural_key": ("class_id", "subject_id"),
        "conflict_policy": POLICY_MERGE,
    },
    # Grading settings: read-only on devices (changing how every student in
    # the school is graded is an online admin action), but cached locally so
    # totals, averages, grades and positions can be worked out offline.
    "materials": {
        # Read-only listing of learning materials. Same visibility rule as the online page:
        # admins and full-access positions see the whole school's, a form teacher sees their
        # own class's. (Uploading/removing stays online; files are saved on demand.)
        "table": "materials",
        "fields": [],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(),
        "can_read": set(STAFF_ROLES),
    },
    "skill_traits": {
        "table": "skill_traits",
        "fields": [],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(),
        "can_read": set(STAFF_ROLES),
    },
    "student_skill_ratings": {
        "table": "student_skill_ratings",
        "fields": [],
        "school_col": _school_via_student,
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(),
        "can_read": set(STAFF_ROLES),
    },
    "enrollments": {
        # Which class a student was in during each session — needed so a past
        # term's broadsheet/result is worked out against the right class list.
        "table": "enrollments",
        "fields": [],
        "school_col": _school_via_class,
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(),
        "can_read": set(STAFF_ROLES),
    },
    "grading_config": {
        "table": "grading_config",
        "fields": ["ca1_max", "ca2_max", "ca3_max", "exam_max"],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        # School managers only. Editing the weights offline is allowed; the
        # server applies the same checks as the online screen.
        "can_write": set(ADMIN_ROLES),
        "can_read": set(STAFF_ROLES),
        "natural_key": ("school_id",),
        "conflict_policy": POLICY_MERGE,
        "before_write": _validate_grading,
    },
    "grade_scale": {
        # A/B/C… bands. Admins can add and edit them from a device (same checks as the
        # online screen: sensible limits, no overlapping bands); DELETING a band stays online.
        "table": "grade_scale",
        "fields": ["grade", "min_score", "max_score", "remark"],
        "school_col": "direct",
        "scope_ids": _all_scope,
        "scope_col": None,
        "can_write": set(ADMIN_ROLES),
        "can_read": set(STAFF_ROLES),
        "conflict_policy": POLICY_MERGE,
        "check_row": _check_grade_band,
    },
}


def _scoped_sql_base(entity, identity):
    """Returns (from_clause, where_sql, params) with tenant + per-role
    scoping expressed directly in SQL (joins + WHERE), rather than
    fetched-then-filtered-in-Python. This is what makes real pagination
    possible: a LIMIT/OFFSET only means something if the WHERE clause
    already reflects exactly which rows the caller may see — an offset
    computed against an unfiltered table would skip or repeat rows once
    Python-side filtering was layered on afterwards.

    `params` covers everything up to but not including `since`, which
    callers append themselves (its column name differs per entity's FROM
    clause alias)."""
    role, school_id, user_id = identity["role"], identity["school_id"], identity["user_id"]
    is_admin = role in ADMIN_ROLES
    # Reading class results: same rule as the online result pages
    # (can_view_all_results) — admins, and principal/vice-principal/exam-officer
    # positions, may see every class; other teachers only their form class.
    # This is READ scope only; what a device may WRITE is narrower (see _in_scope).
    read_all = is_admin or identity.get("position") in FULL_ACCESS_POSITIONS

    if entity == "students":
        base = "FROM students s JOIN classes c ON c.id = s.class_id"
        if read_all:
            return base, "c.school_id = ?", [school_id]
        return base, "c.school_id = ? AND c.form_teacher_id = ?", [school_id, user_id]

    if entity == "scores":
        base = "FROM scores x JOIN students s ON s.id = x.student_id JOIN classes c ON c.id = s.class_id"
        if read_all:
            return base, "c.school_id = ?", [school_id]
        # a class they teach a subject in (to enter marks) OR their own form class (to print its results)
        return base, ("c.school_id = ? AND (c.id IN (SELECT class_id FROM class_subjects WHERE teacher_id = ?) "
                      "OR c.form_teacher_id = ?)"), [school_id, user_id, user_id]

    if entity == "attendance_records":
        base = "FROM attendance_records x JOIN classes c ON c.id = x.class_id"
        if read_all:
            return base, "c.school_id = ?", [school_id]
        return base, "c.school_id = ? AND c.form_teacher_id = ?", [school_id, user_id]

    if entity in ("student_term_info", "student_skill_ratings"):
        base = f"FROM {entity} x JOIN students s ON s.id = x.student_id JOIN classes c ON c.id = s.class_id"
        if read_all:
            return base, "c.school_id = ?", [school_id]
        return base, "c.school_id = ? AND c.form_teacher_id = ?", [school_id, user_id]

    if entity == "staff_attendance":
        return "FROM staff_attendance x", "x.school_id = ?", [school_id]

    if entity == "users":
        return "FROM users x", "x.school_id = ?", [school_id]

    if entity == "classes":
        return "FROM classes x", "x.school_id = ?", [school_id]

    if entity == "subjects":
        return "FROM subjects x", "x.school_id = ?", [school_id]

    if entity == "sessions":
        return "FROM sessions x", "x.school_id = ?", [school_id]

    if entity == "terms":
        return "FROM terms x JOIN sessions se ON se.id = x.session_id", "se.school_id = ?", [school_id]

    if entity == "class_subjects":
        return "FROM class_subjects x JOIN classes c ON c.id = x.class_id", "c.school_id = ?", [school_id]

    if entity == "enrollments":
        return "FROM enrollments x JOIN classes c ON c.id = x.class_id", "c.school_id = ?", [school_id]

    if entity == "materials":
        base = "FROM materials x JOIN classes c ON c.id = x.class_id"
        if read_all:
            return base, "x.school_id = ?", [school_id]
        return base, "x.school_id = ? AND c.form_teacher_id = ?", [school_id, user_id]

    if entity in ("grading_config", "grade_scale", "skill_traits"):
        return f"FROM {entity} x", "x.school_id = ?", [school_id]

    raise ValueError(f"no scoped query defined for entity '{entity}'")


# The per-term entities are by far the biggest part of a school's data (a 1,200-pupil school
# has ~19,000 scores and ~75,000 attendance marks a TERM, and history piles up year on year).
# A phone only needs what is being worked on, so a device receives:
#   - scores, comment/attendance summaries and skill ratings for the ACTIVE SESSION's terms;
#   - attendance marks for the ACTIVE TERM (or the whole active session if none is active).
# Earlier sessions stay on the server (their result pages are online pages). When the school
# moves to a new term or session the app notices and downloads the new window by itself.
_ACTIVE_SESSION = ("COALESCE((SELECT id FROM sessions WHERE school_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1), "
                   "(SELECT MAX(id) FROM sessions WHERE school_id = ?))")
_WINDOWED = {"scores": "session", "student_term_info": "session", "student_skill_ratings": "session",
             "attendance_records": "term"}


def _scoped_sql(entity, identity):
    from_sql, where_sql, params = _scoped_sql_base(entity, identity)
    kind = _WINDOWED.get(entity)
    if not kind:
        return from_sql, where_sql, params
    sid = identity["school_id"]
    col = "x.term_id"
    if kind == "session":
        extra = f"{col} IN (SELECT id FROM terms WHERE session_id = {_ACTIVE_SESSION})"
        return from_sql, f"{where_sql} AND {extra}", list(params) + [sid, sid]
    extra = (f"{col} IN (SELECT id FROM terms WHERE session_id = {_ACTIVE_SESSION} AND (is_active = 1 OR NOT EXISTS "
             f"(SELECT 1 FROM terms t2 WHERE t2.session_id = {_ACTIVE_SESSION} AND t2.is_active = 1)))")
    return from_sql, f"{where_sql} AND {extra}", list(params) + [sid, sid, sid, sid]


# Which alias each entity's base query uses for its own columns — 'students'
# selects via alias 's' (since 's' was already taken by the joined
# students table in scores/attendance_records/student_term_info, those
# use 'x' for their OWN table and 's' for the joined students table).
_ENTITY_SELF_ALIAS = {
    "students": "s", "scores": "x", "attendance_records": "x",
    "student_term_info": "x", "staff_attendance": "x", "users": "x",
    "classes": "x", "subjects": "x", "sessions": "x", "terms": "x",
    "class_subjects": "x", "grading_config": "x", "grade_scale": "x", "enrollments": "x", "skill_traits": "x", "student_skill_ratings": "x", "materials": "x",
}

PAGE_SIZE = 500
BOOTSTRAP_PAGE_SIZE = 2000   # a first-time download is many pages of the same shape; fewer, bigger ones
MAX_PAGE_SIZE = 2000


PULL_OVERLAP_SECONDS = 3


def _overlap_since(since):
    """Timestamps have one-second resolution, so a change committed in the
    same second a previous pull was generated could be missed forever by a
    strict `updated_at > since`. Re-reading a few seconds of overlap costs a
    few redundant rows (harmless: applying a pulled row is idempotent, and the
    client ignores rows it already has) and closes that gap."""
    dt = parse_ts(since)
    if dt is None:
        return since
    return (dt - datetime.timedelta(seconds=PULL_OVERLAP_SECONDS)).isoformat(timespec="seconds")


def _read_entity_page(conn, name, identity, since, limit, offset):
    """Returns (rows, has_more). Fetches `limit + 1` rows so "is there
    another page" is a free byproduct of this query instead of a second
    COUNT(*) round trip; the +1th row (if present) is trimmed before
    returning."""
    alias = _ENTITY_SELF_ALIAS[name]
    from_clause, where_sql, params = _scoped_sql(name, identity)
    # client_uuid should never actually be NULL here — migration_026's
    # triggers guarantee every row gets one, however it was inserted —
    # but a NULL value is not a valid IndexedDB key, so this filter is a
    # defense-in-depth belt against a row somehow still slipping through
    # (e.g. a future migration order issue) breaking a device's bootstrap
    # entirely rather than just quietly omitting that one row.
    conditions = [where_sql, f"{alias}.client_uuid IS NOT NULL"]
    if since:
        conditions.append(f"{alias}.updated_at > ?")
        params.append(_overlap_since(since))
    else:
        conditions.append(f"{alias}.is_deleted = 0")
    sql = (
        f"SELECT {alias}.* {from_clause} WHERE " + " AND ".join(conditions) +
        f" ORDER BY {alias}.id LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, params + [limit + 1, offset]).fetchall()
    has_more = len(rows) > limit
    hidden = ENTITIES[name].get("never_send", ())
    return [{k: v for k, v in dict(r).items() if k not in hidden} for r in rows[:limit]], has_more


def _row_school_id(conn, entity_name, row):
    cfg = ENTITIES[entity_name]
    if cfg["school_col"] == "direct":
        return row.get("school_id")
    return cfg["school_col"](conn, row)


def _in_scope(conn, entity_name, identity, row):
    """True if `identity` may write/read this row, given its foreign keys.
    Combines the generic scope_col check with the one entity-specific case
    (scores) that needs its own logic because it isn't scoped by a single
    foreign key column."""
    cfg = ENTITIES[entity_name]
    scope = cfg["scope_ids"](conn, identity)
    if scope == "all":
        return True
    if entity_name == "scores":
        student_id = row.get("student_id")
        if student_id is None:
            return False
        r = conn.execute("SELECT class_id FROM students WHERE id=?", (student_id,)).fetchone()
        return bool(r) and r["class_id"] in scope
    if entity_name == "student_term_info":
        student_id = row.get("student_id")
        if student_id is None:
            return False
        r = conn.execute("SELECT class_id FROM students WHERE id=?", (student_id,)).fetchone()
        return bool(r) and r["class_id"] in scope
    col = cfg["scope_col"]
    if col is None:
        return False
    return row.get(col) in scope


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------

@sync_bp.route("/api/offline/enroll", methods=["POST"])
def enroll():
    """Must be called from a normal ONLINE session — this is the "account
    successfully authenticated online at least once" step the offline
    login requirement refers to. Issues a per-device credential the
    browser will encrypt with the user's chosen offline PIN (see
    offline-auth.js) and use for every future offline login."""
    if "user_id" not in session or session.get("role") not in STAFF_ROLES:
        return jsonify({"error": "not_authenticated"}), 401
    conn = get_db()
    try:
        me = conn.execute("SELECT is_active, username FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not me or not me["is_active"]:
            return jsonify({"error": "not_authenticated"}), 401
        body = request.get_json(silent=True) or {}
        cred = issue_device_credential(
            conn, session["school_id"], session["user_id"],
            session["role"], session.get("position"),
            device_label=body.get("device_label"),
            device_id=body.get("device_id"),  # re-enrolling the same device keeps its id
        )
        user = conn.execute("SELECT name FROM users WHERE id=?", (session["user_id"],)).fetchone()
        return jsonify({
            "device_id": cred["device_id"],
            "device_secret": cred["secret"],
            "expires_at": cred["expires_at"],
            "user": {
                "user_id": session["user_id"],
                "username": me["username"],
                "name": user["name"] if user else session.get("name"),
                "role": session["role"],
                "position": session.get("position"),
                "school_id": session["school_id"],
            },
        })
    finally:
        conn.close()


@sync_bp.route("/api/offline/verify", methods=["POST"])
def verify():
    """Called opportunistically whenever the device has connectivity, to
    confirm the offline credential is still good (not revoked, not
    expired, school not suspended/archived) and to slide its expiry
    forward. A device that fails this should treat itself as logged out
    for offline purposes and require a fresh online login + re-enrollment."""
    body = request.get_json(silent=True) or {}
    device_id, secret = body.get("device_id"), body.get("device_secret")
    if not device_id or not secret:
        return jsonify({"error": "missing_credentials"}), 400
    conn = get_db()
    try:
        status, cred = verify_device_credential(conn, device_id, secret)
        if status != "ok":
            return jsonify({"status": status}), 200
        user = conn.execute(
            "SELECT name, school_id, role, position, is_active FROM users WHERE id=?", (cred["user_id"],)
        ).fetchone()
        if (not user or user["school_id"] != cred["school_id"] or user["role"] not in STAFF_ROLES
                or not user["is_active"]):
            return jsonify({"status": "revoked"}), 200
        return jsonify({
            "status": "ok",
            "expires_at": cred["expires_at"],
            "user": {
                "user_id": cred["user_id"],
                "name": user["name"],
                "role": user["role"],
                "position": user["position"],
                "school_id": cred["school_id"],
            },
        })
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# School profile + deletions (shared by bootstrap and pull)
# ---------------------------------------------------------------------------

def _school_meta(conn, school_id):
    """The bits of the school profile an offline result sheet needs. An
    explicit allow-list: the schools row also holds SMTP credentials and
    activation data, which must never be sent to a device."""
    row = get_school(conn, school_id)
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "logo_align": row["logo_align"],
        "has_logo": bool(row["logo_filename"]),
        "logo_url": f"/portal-logo/{row['id']}" if row["logo_filename"] else None,
        "show_result_date": bool(row["show_result_date"]),
        "auto_teacher_comment": bool(row["auto_teacher_comment"]),
        "auto_principal_comment": bool(row["auto_principal_comment"]),
    }


def _tombstones_since(conn, identity, since):
    """Records hard-deleted online since `since`, for this school only.
    Tombstones with no resolvable school are never returned."""
    if not since:
        return []
    rows = conn.execute(
        "SELECT entity, client_uuid, deleted_at FROM sync_tombstones "
        "WHERE school_id=? AND deleted_at > ? ORDER BY id",
        (identity["school_id"], _overlap_since(since)),
    ).fetchall()
    return [dict(r) for r in rows
            if r["entity"] in ENTITIES and identity["role"] in ENTITIES[r["entity"]]["can_read"]]


# ---------------------------------------------------------------------------
# Bootstrap (initial full snapshot for a newly enrolled device)
# ---------------------------------------------------------------------------

def _parse_cursor(cursor_raw):
    """A paging cursor remembers how far into each entity we are AND which entities are
    finished. (Remembering only the unfinished ones — as this once did — made every
    later page start the finished entities over from row 0, so a school with more than
    one page of data re-downloaded its classes, subjects, students... on every page.)"""
    if not cursor_raw:
        return {}, set()
    try:
        data = json.loads(cursor_raw)
        return dict(data.get("offsets") or {}), set(data.get("done") or [])
    except (ValueError, TypeError, AttributeError):
        return {}, set()


@sync_bp.route("/api/sync/bootstrap", methods=["GET"])
@require_identity
def bootstrap():
    conn, identity = g.sync_conn, g.sync_identity
    limit = min(int(request.args.get("limit", BOOTSTRAP_PAGE_SIZE) or BOOTSTRAP_PAGE_SIZE), MAX_PAGE_SIZE)
    cursor_raw = request.args.get("cursor")
    offsets, done = _parse_cursor(cursor_raw)

    out = {"generated_at": now_iso(), "entities": {},
           "school": _school_meta(conn, identity["school_id"])}
    next_offsets = {}
    for name, cfg in ENTITIES.items():
        if identity["role"] not in cfg["can_read"] or name in done:
            continue
        offset = offsets.get(name, 0)
        rows, has_more = _read_entity_page(conn, name, identity, since=None, limit=limit, offset=offset)
        # An entity is always PRESENT in the answer (empty if it has no rows) until it is
        # done, so the client can tell "empty" from "not readable by this account".
        out["entities"][name] = rows
        if has_more:
            next_offsets[name] = offset + limit
        else:
            done.add(name)
    if next_offsets:
        # There's more data than fit in this page for at least one
        # entity — the client is expected to call this same endpoint
        # again with ?cursor=<this value> to keep going, rather than this
        # response trying to hold an entire large school's data at once.
        out["cursor"] = json.dumps({"offsets": next_offsets, "done": sorted(done)})
    record_sync_log(conn, identity["school_id"], identity.get("device_id") or "online", identity["user_id"],
                     "pull", "bootstrap", sum(len(v) for v in out["entities"].values()))
    return jsonify(out)


# ---------------------------------------------------------------------------
# Pull (incremental)
# ---------------------------------------------------------------------------

@sync_bp.route("/api/sync/pull", methods=["GET"])
@require_identity
def pull():
    conn, identity = g.sync_conn, g.sync_identity
    since = request.args.get("since")
    entity_filter = request.args.get("entity")
    limit = min(int(request.args.get("limit", PAGE_SIZE) or PAGE_SIZE), MAX_PAGE_SIZE)
    cursor_raw = request.args.get("cursor")
    offsets, done = _parse_cursor(cursor_raw)

    out = {"generated_at": now_iso(), "entities": {},
           "school": _school_meta(conn, identity["school_id"]),
           # deletions are listed once, on the first page
           "deleted": [] if cursor_raw else _tombstones_since(conn, identity, since)}
    next_offsets = {}
    for name, cfg in ENTITIES.items():
        if entity_filter and name != entity_filter:
            continue
        if identity["role"] not in cfg["can_read"] or name in done:
            continue
        offset = offsets.get(name, 0)
        rows, has_more = _read_entity_page(conn, name, identity, since=since, limit=limit, offset=offset)
        if rows:
            out["entities"][name] = rows
        if has_more:
            next_offsets[name] = offset + limit
        else:
            done.add(name)
    if next_offsets:
        out["cursor"] = json.dumps({"offsets": next_offsets, "done": sorted(done)})
    return jsonify(out)


# ---------------------------------------------------------------------------
# Push (batched writes from the offline outbox)
# ---------------------------------------------------------------------------

@sync_bp.route("/api/sync/push", methods=["POST"])
@require_identity
def push():
    conn, identity = g.sync_conn, g.sync_identity
    body = request.get_json(silent=True) or {}
    changes = body.get("changes", [])
    if not isinstance(changes, list) or len(changes) > 500:
        return jsonify({"error": "invalid_or_too_large_batch"}), 400

    # Take the write lock ONCE, up front. A transaction that starts as a read and later tries
    # to write can be refused instantly ("database is locked") when another device wrote in
    # between; asking for the write lock first makes it wait its turn instead.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    results = []
    synced = conflicts = errors = 0
    for change in changes:
        if not conn.in_transaction:      # (recording a conflict commits; start the next change's turn the same way)
            conn.execute("BEGIN IMMEDIATE")
        result = _apply_one(conn, identity, change)
        results.append(result)
        if result["status"] == "synced":
            synced += 1
        elif result["status"] == "conflict":
            conflicts += 1
        else:
            errors += 1
    conn.commit()
    record_sync_log(conn, identity["school_id"], identity.get("device_id") or "online",
                     identity["user_id"], "push", None, synced, conflicts, errors)
    return jsonify({"results": results, "synced": synced, "conflicts": conflicts, "errors": errors})


# ---------------------------------------------------------------------------
# Applying pushed changes
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = {"password", "password_hash", "security_answer_hash", "security_question"}


def _redact(d):
    """Audit trails and conflict records must never become a second copy of
    anyone's credentials."""
    if not isinstance(d, dict):
        return d
    return {k: ("[redacted]" if k in _SENSITIVE_KEYS else v) for k, v in d.items()}


def _public_row(entity, row):
    hidden = ENTITIES[entity].get("never_send", ())
    return {k: v for k, v in dict(row).items() if k not in hidden}


def _next_ts(previous, now_str):
    """A new updated_at that is strictly later than `previous` (the row's
    old version token), even if the wall clock hasn't moved on a full second."""
    prev = parse_ts(previous)
    now_dt = parse_ts(now_str)
    if prev is not None and now_dt is not None and now_dt <= prev:
        return (prev + datetime.timedelta(seconds=1)).isoformat(timespec="seconds")
    return now_str


def _audit(conn, identity, entity, client_uuid, change, outcome, *, server_id=None,
           result_updated_at=None, old=None, new=None, note=None):
    try:
        conn.execute(
            "INSERT INTO change_audit (school_id, entity, client_uuid, change_id, op, outcome, "
            "device_id, user_id, client_ts, server_id, result_updated_at, old_data, new_data, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (identity["school_id"], entity, client_uuid, change.get("change_id"),
             change.get("op", "upsert"), outcome, identity.get("device_id"), identity["user_id"],
             change.get("client_ts"), server_id, result_updated_at,
             json.dumps(_redact(old), default=str) if old is not None else None,
             json.dumps(_redact(new), default=str) if new is not None else None,
             note),
        )
    except sqlite3.IntegrityError:
        # Same (school, change_id) applied twice concurrently — the first one wins.
        pass


def _log_score_history(conn, identity, change, before, after):
    """Offline/synced score edits get the same who-changed-what trail the
    online score screen keeps."""
    names = ("ca1", "ca2", "ca3", "exam")
    if before is not None and all(values_equal(before.get(n), after.get(n)) for n in names):
        return
    if before is None and not any(after.get(n) for n in names):
        return
    conn.execute(
        "INSERT INTO score_history (student_id, subject_id, term_id, "
        "old_ca1, old_ca2, old_ca3, old_exam, new_ca1, new_ca2, new_ca3, new_exam, "
        "changed_by, source, device_id, change_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (after["student_id"], after["subject_id"], after["term_id"],
         *(before.get(n) if before is not None else None for n in names),
         *(after.get(n) or 0 for n in names),
         identity["user_id"], "offline-sync", identity.get("device_id"), change.get("change_id")),
    )


def _ref_error(conn, entity, school_id, row):
    """Every foreign key on a pushed row must point inside the caller's own
    school. _row_school_id() already covers the primary parent; this covers
    the rest (subject, term, form teacher, ...), so a row can't be stitched
    to another school's records."""
    def owner(sql, v):
        r = conn.execute(sql, (v,)).fetchone()
        return None if r is None else r["school_id"]

    def make(sql):
        def check(v):
            o = owner(sql, v)
            return "missing" if o is None else ("ok" if o == school_id else "foreign")
        return check

    subject_ok = make("SELECT school_id FROM subjects WHERE id=?")
    term_ok = make("SELECT se.school_id AS school_id FROM terms t JOIN sessions se ON se.id=t.session_id WHERE t.id=?")
    user_ok = make("SELECT school_id FROM users WHERE id=?")
    class_ok = make("SELECT school_id FROM classes WHERE id=?")
    student_ok = make("SELECT c.school_id AS school_id FROM students s JOIN classes c ON c.id=s.class_id WHERE s.id=?")

    checks = {
        "scores": (("student_id", student_ok), ("subject_id", subject_ok), ("term_id", term_ok)),
        "student_term_info": (("student_id", student_ok), ("term_id", term_ok)),
        "attendance_records": (("student_id", student_ok), ("term_id", term_ok), ("class_id", class_ok), ("recorded_by", user_ok)),
        "staff_attendance": (("user_id", user_ok), ("recorded_by", user_ok)),
        "classes": (("form_teacher_id", user_ok),),
        "class_subjects": (("class_id", class_ok), ("subject_id", subject_ok), ("teacher_id", user_ok)),
        "students": (("class_id", class_ok),),
    }
    for col, ok in checks.get(entity, ()):
        v = row.get(col)
        if v is None:
            continue
        verdict = ok(v)
        if verdict == "foreign":
            return f"cross-school write rejected ({col})"
        if verdict == "missing":
            return f"refers to a record that no longer exists ({col}) — it may have been deleted online"
    if entity == "attendance_records" and row.get("student_id") is not None and row.get("class_id") is not None:
        r = conn.execute("SELECT class_id FROM students WHERE id=?", (row["student_id"],)).fetchone()
        if not r or r["class_id"] != row["class_id"]:
            return "student is not in that class"
    return None


def _find_existing(conn, cfg, client_uuid, fields):
    """Returns (row, matched_by_natural_key)."""
    table = cfg["table"]
    row = conn.execute(f"SELECT * FROM {table} WHERE client_uuid=?", (client_uuid,)).fetchone()
    if row:
        return row, False
    nk = cfg.get("natural_key")
    if nk and all(fields.get(k) is not None for k in nk):
        where = " AND ".join(f"{k}=?" for k in nk)
        row = conn.execute(f"SELECT * FROM {table} WHERE {where}", tuple(fields[k] for k in nk)).fetchone()
        if row:
            return row, True
    return None, False


def _apply_one(conn, identity, change):
    entity = change.get("entity")
    client_uuid = change.get("client_uuid")
    op = change.get("op", "upsert")
    base_updated_at = change.get("base_updated_at")   # updated_at this device last saw for the row
    base_data = change.get("base_data") if isinstance(change.get("base_data"), dict) else None
    change_id = change.get("change_id")
    data = change.get("data")

    if entity not in ENTITIES:
        return {"client_uuid": client_uuid, "status": "error", "message": f"unknown entity '{entity}'"}
    cfg = ENTITIES[entity]
    if not client_uuid:
        return {"client_uuid": client_uuid, "status": "error", "message": "missing client_uuid"}
    # A device chooses its own record ids, and other devices later render them.
    # Keep them to a boring, harmless shape.
    if not isinstance(client_uuid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client_uuid):
        return {"client_uuid": None, "status": "error", "message": "invalid client_uuid"}
    if change_id is not None and (not isinstance(change_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", change_id)):
        return {"client_uuid": client_uuid, "status": "error", "message": "invalid change_id"}
    if not isinstance(data, dict):
        data = {}

    def reject(message, outcome="rejected"):
        _audit(conn, identity, entity, client_uuid, change, outcome, new=data, note=message)
        return {"client_uuid": client_uuid, "status": "error", "message": message}

    if identity["role"] not in cfg["can_write"]:
        return reject("not permitted to write this entity")
    if op == "delete":
        # No screen offers offline deletion, and the online screens hard-delete
        # (with cascades). Deletions made online reach devices as tombstones.
        return reject("Deleting records has to be done online.")

    table = cfg["table"]

    # -- Idempotency: the same change (same change_id) must never apply twice,
    #    however many times a flaky connection makes the device retry it.
    if change_id:
        prior = conn.execute(
            "SELECT * FROM change_audit WHERE school_id=? AND change_id=? "
            "AND outcome IN ('applied','merged','latest_wins')",
            (identity["school_id"], change_id),
        ).fetchone()
        if prior:
            row = conn.execute(f"SELECT * FROM {table} WHERE client_uuid=?", (client_uuid,)).fetchone()
            out = {"client_uuid": client_uuid, "status": "synced", "outcome": prior["outcome"],
                   "server_id": prior["server_id"], "updated_at": prior["result_updated_at"],
                   "duplicate": True}
            if row is not None:
                out["server_data"] = _public_row(entity, row)
                out["updated_at"] = row["updated_at"]
            return out

    # -- Validate + normalise the incoming fields.
    fields = {k: v for k, v in data.items() if k in cfg["fields"]}
    if cfg["school_col"] == "direct":
        fields["school_id"] = identity["school_id"]  # never trust a client-supplied school_id
    try:
        if cfg.get("before_write"):
            cfg["before_write"](conn, identity, fields)
    except SyncValidationError as e:
        return reject(str(e))

    existing, by_natural_key = _find_existing(conn, cfg, client_uuid, fields)

    if cfg.get("check_row"):
        try:
            cfg["check_row"](conn, identity, existing, fields)
        except SyncValidationError as e:
            return reject(str(e))

    # -- Tenant + role scope, checked on the row as it is AND as it would become.
    candidates = [dict(fields)]
    if existing is not None:
        candidates.append(dict(existing))
        candidates.append({**dict(existing), **fields})
    for probe in candidates:
        row_school_id = _row_school_id(conn, entity, probe)
        if row_school_id is not None and row_school_id != identity["school_id"]:
            return reject("cross-school write rejected", outcome="rejected")
        if not _in_scope(conn, entity, identity, probe):
            return reject("not permitted for your class/subject assignment")
    ref_err = _ref_error(conn, entity, identity["school_id"], {**(dict(existing) if existing else {}), **fields})
    if ref_err:
        return reject(ref_err)

    now = now_iso()
    now_dt = parse_ts(now)

    # ================= existing row =================
    if existing is not None:
        existing = dict(existing)
        canonical = existing["client_uuid"]
        # A record's identity (which student/subject/term...) never changes.
        for k in (cfg.get("natural_key") or ()):
            if k in fields and not values_equal(fields[k], existing.get(k)):
                return reject("A record can't be moved to a different student/subject/term.")
        if cfg.get("before_update"):
            try:
                cfg["before_update"](conn, identity, existing, fields)
            except SyncValidationError as e:
                return reject(str(e))

        writable = {k: v for k, v in fields.items() if k != "school_id"}

        if existing.get("is_deleted"):
            record_sync_conflict(conn, identity["school_id"], entity, client_uuid, identity.get("device_id"),
                                 _redact(fields), _redact(_public_row(entity, existing)))
            _audit(conn, identity, entity, client_uuid, change, "conflict", server_id=existing["id"],
                   new=fields, note="Deleted elsewhere while this device edited it.")
            return {"client_uuid": client_uuid, "status": "conflict", "server_id": existing["id"],
                    "server_data": _public_row(entity, existing),
                    "message": "This record was deleted elsewhere after you last synced it."}

        if by_natural_key:
            # This device never saw the row that's already there (someone else
            # created the same student/subject/term cell). Nothing to compare
            # against except "an empty row", which makes the merge rules do the
            # sensible thing: fields this device actually filled in are its
            # changes; fields it left blank are not.
            unchanged = all(values_equal(existing.get(k), v) for k, v in writable.items())
            concurrent = not unchanged
            effective_base = {}
        else:
            concurrent = bool(base_updated_at) and existing["updated_at"] != base_updated_at
            effective_base = base_data

        policy = cfg.get("conflict_policy", POLICY_MANUAL)
        if not concurrent:
            decision_kind, to_write, note = "apply", writable, None
        else:
            d = decide(policy, [k for k in writable], writable, existing, effective_base,
                       change.get("client_ts"), existing["updated_at"], now_dt)
            decision_kind, to_write, note = d.kind, d.fields, d.note
            if d.kind == "conflict":
                record_sync_conflict(conn, identity["school_id"], entity, client_uuid, identity.get("device_id"),
                                     _redact(fields), _redact(_public_row(entity, existing)))
                _audit(conn, identity, entity, client_uuid, change, "conflict", server_id=existing["id"],
                       old={k: existing.get(k) for k in writable}, new=fields, note=d.note)
                return {"client_uuid": client_uuid, "status": "conflict", "server_id": existing["id"],
                        "server_data": _public_row(entity, existing), "conflicting_fields": d.conflicting,
                        "message": d.note or "This record changed elsewhere since you last synced it."}

        if decision_kind == "latest_server":
            _audit(conn, identity, entity, client_uuid, change, "latest_wins", server_id=existing["id"],
                   result_updated_at=existing["updated_at"], old={k: existing.get(k) for k in writable},
                   new=fields, note="Superseded: " + (note or "server copy was more recent"))
            return {"client_uuid": client_uuid, "status": "synced", "outcome": "latest_wins",
                    "server_id": existing["id"], "updated_at": existing["updated_at"],
                    "canonical_client_uuid": canonical, "server_data": _public_row(entity, existing),
                    "message": note}

        changed = {k: v for k, v in to_write.items() if not values_equal(existing.get(k), v)}
        new_ts = existing["updated_at"]
        if changed:
            new_ts = _next_ts(existing["updated_at"], now)
            set_clause = ", ".join(f"{k}=?" for k in changed)
            try:
                conn.execute(
                    f"UPDATE {table} SET {set_clause}, updated_at=? WHERE id=?",
                    (*changed.values(), new_ts, existing["id"]),
                )
            except sqlite3.IntegrityError as e:
                record_sync_conflict(conn, identity["school_id"], entity, client_uuid, identity.get("device_id"),
                                     _redact(fields), {"error": str(e)})
                _audit(conn, identity, entity, client_uuid, change, "conflict", server_id=existing["id"],
                       new=fields, note=f"constraint violation: {e}")
                return {"client_uuid": client_uuid, "status": "conflict", "server_id": existing["id"],
                        "message": f"duplicate or invalid: {e}"}
            if entity == "scores":
                _log_score_history(conn, identity, change, existing, {**existing, **changed})
            if entity == "attendance_records":
                recompute_attendance(conn, existing["student_id"], existing["term_id"])
            if entity == "students" and "class_id" in changed:
                upsert_enrollment(conn, existing["id"], changed["class_id"])
        outcome = {"apply": "applied", "merge": "merged", "latest_client": "latest_wins"}[decision_kind]
        _audit(conn, identity, entity, client_uuid, change, outcome, server_id=existing["id"],
               result_updated_at=new_ts, old={k: existing.get(k) for k in changed},
               new=changed, note=note)
        out = {"client_uuid": client_uuid, "status": "synced", "outcome": outcome,
               "server_id": existing["id"], "updated_at": new_ts}
        if decision_kind != "apply" or by_natural_key or canonical != client_uuid:
            fresh = conn.execute(f"SELECT * FROM {table} WHERE id=?", (existing["id"],)).fetchone()
            out["server_data"] = _public_row(entity, fresh)
            out["canonical_client_uuid"] = canonical
            out["message"] = note
        return out

    # ================= new row =================
    if base_updated_at:
        # The device is EDITING a record it had synced before, but the server
        # no longer has it: someone deleted it online. Don't quietly re-create
        # it — flag it so the person decides (keep mine = re-create).
        record_sync_conflict(conn, identity["school_id"], entity, client_uuid, identity.get("device_id"),
                             _redact(fields), {"deleted": True})
        _audit(conn, identity, entity, client_uuid, change, "conflict", new=fields,
               note="Edited offline, but the record was deleted online.")
        return {"client_uuid": client_uuid, "status": "conflict", "server_data": None,
                "message": "This record was deleted online after you last synced it."}
    new_fields = dict(fields)
    new_fields["client_uuid"] = client_uuid
    new_fields["updated_at"] = now
    cols = ", ".join(new_fields.keys())
    placeholders = ", ".join("?" for _ in new_fields)
    try:
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", tuple(new_fields.values()))
    except sqlite3.IntegrityError as e:
        # A uniqueness clash the server can see but the offline device couldn't
        # (a username, admission number, class or subject name another device
        # already used while this one was offline). Surfaced as a conflict, not
        # silently dropped and not silently overwritten.
        record_sync_conflict(conn, identity["school_id"], entity, client_uuid, identity.get("device_id"),
                             _redact(fields), {"error": str(e)})
        _audit(conn, identity, entity, client_uuid, change, "conflict", new=fields,
               note=f"duplicate or invalid: {e}")
        return {"client_uuid": client_uuid, "status": "conflict", "message": f"duplicate or invalid: {e}"}
    if entity == "scores":
        _log_score_history(conn, identity, change, None, fields)
    if entity == "students":
        # Same as the online "add student": record which class they are in for
        # the current session, so a later promotion doesn't rewrite history.
        upsert_enrollment(conn, cur.lastrowid, fields["class_id"])
    if entity == "attendance_records":
        # Report cards read Days Open/Present/Absent from student_term_info,
        # which the online roll-call keeps in step. Do the same for synced
        # roll calls, or offline attendance would never reach a report card.
        recompute_attendance(conn, fields["student_id"], fields["term_id"])
    _audit(conn, identity, entity, client_uuid, change, "applied", server_id=cur.lastrowid,
           result_updated_at=now, new=fields)
    return {"client_uuid": client_uuid, "status": "synced", "outcome": "applied",
            "server_id": cur.lastrowid, "updated_at": now}


@sync_bp.after_request
def _compress_sync_responses(response):
    """Sync answers are large, repetitive JSON (thousands of similar rows), which gzip shrinks
    5-10x. On a phone's mobile data that is the difference between a first-time download that
    takes a minute and one that takes seconds. Only when the client asks for it."""
    try:
        if (request.path.startswith("/api/sync/") and response.status_code == 200
                and "gzip" in request.headers.get("Accept-Encoding", "").lower()
                and response.mimetype == "application/json" and not response.direct_passthrough):
            data = response.get_data()
            if len(data) > 1024:
                import gzip
                response.set_data(gzip.compress(data, compresslevel=5))
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Vary"] = "Accept-Encoding"
                response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass        # never let compression break a sync answer
    return response


# ---------------------------------------------------------------------------
# Notifications (read-only on devices)
# ---------------------------------------------------------------------------

@sync_bp.route("/api/sync/notifications", methods=["GET"])
@require_identity
def notifications():
    """The notices this person can see (platform-wide ones and their own school's, for
    their role), so the app can show its inbox with no connection. Read-only: writing
    or sending notices is an online action."""
    conn, identity = g.sync_conn, g.sync_identity
    rows = get_visible_notifications(conn, identity["role"], identity["school_id"], limit=100)
    me = conn.execute("SELECT last_notification_seen_id FROM users WHERE id=?", (identity["user_id"],)).fetchone()
    return jsonify({
        "items": [{"id": r["id"], "sender_label": r["sender_label"], "title": r["title"], "message": r["message"],
                   "created_at": r["created_at"], "platform_wide": r["school_id"] is None} for r in rows],
        "last_seen_id": (me["last_notification_seen_id"] if me else 0) or 0,
    })


@sync_bp.route("/api/sync/notifications/seen", methods=["POST"])
@require_identity
def notifications_seen():
    conn, identity = g.sync_conn, g.sync_identity
    rows = get_visible_notifications(conn, identity["role"], identity["school_id"], limit=1)
    if rows:
        conn.execute("UPDATE users SET last_notification_seen_id=? WHERE id=?", (rows[0]["id"], identity["user_id"]))
        conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Audit trail (admins)
# ---------------------------------------------------------------------------

@sync_bp.route("/api/sync/audit", methods=["GET"])
@require_identity
def audit_trail():
    """Recent changes applied, merged, superseded, refused or flagged for this
    school. Admins only, always scoped to the caller's own school."""
    conn, identity = g.sync_conn, g.sync_identity
    if identity["role"] not in ADMIN_ROLES:
        return jsonify({"error": "forbidden"}), 403
    limit = min(int(request.args.get("limit", 100) or 100), 500)
    entity = request.args.get("entity")
    sql = "SELECT * FROM change_audit WHERE school_id=?"
    params = [identity["school_id"]]
    if entity:
        sql += " AND entity=?"
        params.append(entity)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return jsonify({"entries": rows})
