from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_file, send_from_directory, g, jsonify,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
import os
import sqlite3
import io
import csv as csv_module
import secrets
import time
import re
import threading
from collections import defaultdict, deque

from db import (
    get_db, init_db, grade_for, get_school, INSTANCE_DIR,
    POSITION_LABELS, FULL_ACCESS_POSITIONS, form_teacher_class_ids,
    can_view_all_results, can_view_class_results, student_full_name,
    seed_school_defaults, upsert_enrollment, log_audit,
    get_visible_notifications, get_unread_notification_count,
    recompute_attendance, attendance_percentage, grading_problems, grade_band_problems, parse_arms,
    generate_teacher_comment, generate_principal_comment,
    CLASS_CATEGORIES, MATERIAL_KINDS, format_dmy, STAFF_ATTENDANCE_STATUSES,
    PDF_FONT_CHOICES, WEB_FONTS, generate_activation_code, current_activation_code_status,
    verify_activation_code, revoke_device_credentials_for_user, revoke_device_credentials_for_school,
    TIMEZONE_CHOICES, RESULT_HEADER_LAYOUTS,
)
import datetime
import json
import random
from pdf_utils import build_broadsheet_pdf, build_result_pdf, build_class_results_pdf, build_cumulative_result_pdf, build_generic_table_pdf
from email_utils import send_email, send_platform_email
from reports import build_csv, build_xlsx
from sync_api import sync_bp

ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# Learning Materials: extension -> the broad type shown to teachers/students.
# Anything not in this map (e.g. a full video file) should be linked via
# external_url instead of uploaded — see MATERIALS_DIR below.
MATERIAL_EXTENSIONS = {
    "pdf": "PDF", "doc": "Word", "docx": "Word", "ppt": "PowerPoint", "pptx": "PowerPoint",
    "jpg": "Image", "jpeg": "Image", "png": "Image", "gif": "Image",
}
MATERIALS_DIR = os.path.join(INSTANCE_DIR, "materials")
STUDENT_PHOTOS_DIR = os.path.join(INSTANCE_DIR, "student_photos")
STAFF_PHOTOS_DIR = os.path.join(INSTANCE_DIR, "staff_photos")
SIGNATURES_DIR = os.path.join(INSTANCE_DIR, "signatures")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB upload limit (logo/CSV/materials)

# Trust one reverse-proxy hop for the real client IP (X-Forwarded-For),
# since PythonAnywhere — and most hosts — put the app behind a proxy.
# Without this, every visitor would appear to share the proxy's own IP,
# which would make the rate limiter below block everyone at once instead
# of just whoever is actually hammering a route.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Cookie hardening. SameSite=Lax is safe for this app everywhere. "Secure"
# (send the cookie only over HTTPS) is opt-in so a plain-http local test still
# works: set SESSION_COOKIE_SECURE=1 on any real HTTPS deployment.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("SESSION_COOKIE_SECURE") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True


def _get_or_create_secret_key():
    key_path = os.path.join(INSTANCE_DIR, "secret_key.txt")
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if not os.path.exists(key_path):
        with open(key_path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(key_path) as f:
        return f.read().strip()


app.secret_key = os.environ.get("SECRET_KEY") or _get_or_create_secret_key()

# A non-permanent Flask session cookie disappears when the browser process
# ends — on a PWA/"Add to Home Screen" app that can mean losing login after
# just being backgrounded for a while. That defeats offline use: staff need
# to stay logged in through a multi-day stretch with no connection so their
# queued offline entries still have a valid session to sync against once
# they're back online. session.permanent is set at login (see login()).
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)

# Make sure the database exists and is migrated, whether this file is run
# directly (python app.py) or imported by a production server (e.g. the
# WSGI file on PythonAnywhere, or gunicorn).
init_db()


# ---------- CSRF protection ----------
# Every form in this app posts data with a browser session cookie, which is
# exactly what CSRF exploits — a malicious page elsewhere can make the
# browser submit a form to us using the person's own logged-in cookie. A
# random per-session token, embedded as a hidden field in every POST form
# and checked against the session on every state-changing request, means a
# request that didn't originate from a page we actually rendered is
# rejected, since an attacker's page has no way to know that token.

CSRF_UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def _check_csrf():
    if request.method not in CSRF_UNSAFE_METHODS:
        return None
    if request.path.startswith("/api/"):
        # The offline sync API is JSON-only and authenticated one of two
        # ways, neither of which is vulnerable to classic cookie-riding
        # CSRF the way a form POST is:
        #   - a device credential sent as custom headers (X-Device-Id /
        #     X-Device-Secret) — a cross-site page can't attach arbitrary
        #     headers to a simple form submission, and reading them back
        #     out of the device's encrypted local storage requires
        #     same-origin JS in the first place;
        #   - the normal session cookie, for the one endpoint that's used
        #     before a device has a credential yet (/api/offline/enroll) —
        #     that path is checked below via an explicit header instead of
        #     the form field, since it's a JSON body rather than a form.
        if request.headers.get("X-Device-Id") and request.headers.get("X-Device-Secret"):
            return None
        if request.path == "/api/offline/verify":
            # Authenticated entirely by knowledge of the device_secret in
            # the JSON body (checked against its stored hash inside the
            # handler) — there's deliberately no session/cookie involved
            # here, since the whole point is to work for a device that
            # only just regained connectivity and hasn't necessarily
            # logged in online this session.
            return None
        if "user_id" in session:
            submitted = request.headers.get("X-CSRF-Token", "")
            expected = session.get("_csrf_token", "")
            if expected and secrets.compare_digest(submitted, expected):
                return None
        return jsonify({"error": "csrf_check_failed"}), 403
    submitted = request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    if not expected or not secrets.compare_digest(submitted, expected):
        flash("Your session timed out or that page was open too long — please try again.", "error")
        return redirect(request.referrer or "/")
    return None


app.jinja_env.filters["dmy"] = format_dmy
app.register_blueprint(sync_bp)


@app.route("/healthz")
def healthz():
    """Cheap liveness probe for hosts like Railway (no login, no data)."""
    conn = get_db()
    conn.execute("SELECT 1").fetchone()
    conn.close()
    resp = jsonify({"status": "ok"})
    resp.headers["Cache-Control"] = "no-store"     # the connectivity monitor needs a LIVE answer
    return resp


@app.route("/csrf-token")
def csrf_token_endpoint():
    """Used by the offline-queue script to fetch a fresh, valid token right
    before replaying a queued submission — the token captured when the
    form was originally filled out (possibly while offline, possibly much
    earlier) may no longer match the session by the time it syncs."""
    if "user_id" not in session and "student_id" not in session and "platform_admin_id" not in session:
        return {"error": "not logged in"}, 401
    return {"csrf_token": get_csrf_token()}


# ---------- rate limiting ----------
# In-memory sliding-window counter per (route, client IP). This is a
# single-process store — fine for the size of deployment this app targets
# (one PythonAnywhere web worker), but it resets if the process restarts
# and isn't shared across multiple workers. That trade-off is consistent
# with the rest of the app's approach (e.g. the secret key is a local
# file, not an external service) — if this ever runs behind several
# worker processes, this should move to a shared store like Redis instead.

_rate_limit_lock = threading.Lock()
_rate_limit_store = defaultdict(deque)


def _is_rate_limited(key, max_attempts, window_seconds):
    now = time.time()
    with _rate_limit_lock:
        bucket = _rate_limit_store[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= max_attempts:
            return True
        bucket.append(now)
        return False


def rate_limit(max_attempts, window_seconds):
    """Caps how many POSTs a single IP can make to the decorated route
    within a trailing time window — every submission counts, not just
    failed ones, so a script can't dodge the limit by mixing in the
    occasional well-formed request. GET requests (just viewing the page)
    are never limited. On rejection, redirects back to the same page with
    a flash message rather than a bare error, so it fits the app's normal
    error handling."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if request.method == "POST":
                key = f"{request.endpoint}:{request.remote_addr}"
                if _is_rate_limited(key, max_attempts, window_seconds):
                    flash("Too many attempts from this connection. Please wait a few minutes and try again.", "error")
                    return redirect(request.path)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ---------- custom subdomains ----------
# A school's chosen subdomain (e.g. "greenwood") only means something once
# the *hosting* is set up to route greenwood.<your-domain> to this same
# Flask app — a database column can't make DNS point anywhere. BASE_DOMAIN
# is the one thing the app needs told about that setup: the domain schools'
# subdomains sit under. Leave it unset and this feature quietly does
# nothing (every visitor just sees the normal, unbranded login page).
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "").strip().lower().rstrip(".")

RESERVED_SUBDOMAINS = {"www", "app", "api", "admin", "mail", "portal", "static", "assets"}


def _resolve_subdomain_from_host():
    if not BASE_DOMAIN:
        return None
    host = request.host.split(":")[0].lower()
    suffix = "." + BASE_DOMAIN
    if not host.endswith(suffix):
        return None
    label = host[: -len(suffix)]
    if not label or "." in label:  # only a single subdomain label, not a deeper one
        return None
    return label


@app.before_request
def _load_portal_school():
    g.portal_school = None
    label = _resolve_subdomain_from_host()
    if label and label not in RESERVED_SUBDOMAINS:
        conn = get_db()
        g.portal_school = conn.execute("SELECT * FROM schools WHERE subdomain=?", (label,)).fetchone()
        conn.close()


@app.context_processor
def inject_portal_school():
    return dict(portal_school=g.get("portal_school"))


@app.before_request
def _check_force_logout():
    school_id = session.get("school_id")
    login_time = session.get("login_time")
    if school_id and login_time and ("user_id" in session or "student_id" in session):
        conn = get_db()
        row = conn.execute("SELECT force_logout_at FROM schools WHERE id=?", (school_id,)).fetchone()
        conn.close()
        if row and row["force_logout_at"] and login_time <= row["force_logout_at"]:
            session.clear()
            flash("You've been signed out by your school administrator. Please log in again.", "error")
            return redirect(url_for("login"))
    return None


@app.route("/portal-logo/<int:school_id>")
def portal_logo(school_id):
    """Publicly serves a school's logo so its subdomain's login page can
    show it before anyone has signed in — a school's own logo isn't
    sensitive, so this is intentionally not session-gated."""
    conn = get_db()
    school = get_school(conn, school_id)
    conn.close()
    if not school or not school["logo_filename"]:
        return "", 404
    return send_from_directory(INSTANCE_DIR, school["logo_filename"])


# ---------- helpers ----------

def login_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            # A session must not outlive its account: if an admin deactivated
            # or deleted this user since they logged in, end it now.
            _conn = get_db()
            _u = _conn.execute("SELECT is_active FROM users WHERE id=?", (session["user_id"],)).fetchone()
            _conn.close()
            if _u is None or not _u["is_active"]:
                session.clear()
                flash("This account is no longer active. Contact your school admin.", "error")
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                flash("You don't have access to that page.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def current_school_id():
    return session.get("school_id")


def offline_sync_existing_id(conn, token):
    """If this offline-created record was already synced under this token
    (e.g. an earlier attempt succeeded but the client never saw the
    response), return its id so the caller can reuse it instead of
    inserting a duplicate."""
    if not token:
        return None
    row = conn.execute("SELECT entity_id FROM offline_sync_tokens WHERE token=?", (token,)).fetchone()
    return row["entity_id"] if row else None


def offline_sync_remember(conn, token, entity_type, entity_id):
    if not token:
        return
    conn.execute(
        "INSERT OR IGNORE INTO offline_sync_tokens (token, entity_type, entity_id) VALUES (?,?,?)",
        (token, entity_type, entity_id),
    )
    conn.commit()


def is_offline_sync_request():
    """The offline queue marks its replayed requests with this header so
    create-endpoints know to respond with {ok, id} JSON (which the queue
    needs to resolve dependent, not-yet-synced records) instead of the
    normal flash-and-redirect a live browser submission gets."""
    return request.headers.get("X-Offline-Sync") == "1"


def current_term(conn):
    return conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id = terms.session_id "
        "WHERE terms.is_active=1 AND sessions.school_id=? LIMIT 1",
        (current_school_id(),),
    ).fetchone()


def resolve_term(conn, requested_term_id=None):
    """Returns the requested term (if it belongs to this school) or the
    currently active term otherwise — used so broadsheets/results can show
    a past term's data, not just whatever's active right now."""
    if requested_term_id:
        term = conn.execute(
            "SELECT terms.*, sessions.name as session_name FROM terms "
            "JOIN sessions ON sessions.id = terms.session_id "
            "WHERE terms.id=? AND sessions.school_id=?",
            (requested_term_id, current_school_id()),
        ).fetchone()
        if term:
            return term
    return current_term(conn)


def resolve_session(conn, requested_session_id=None):
    """Same idea as resolve_term, but for a whole academic session — used
    by the cumulative/annual result, which spans every term in a session
    rather than just one."""
    if requested_session_id:
        s = conn.execute(
            "SELECT * FROM sessions WHERE id=? AND school_id=?",
            (requested_session_id, current_school_id()),
        ).fetchone()
        if s:
            return s
    return conn.execute(
        "SELECT * FROM sessions WHERE school_id=? AND is_active=1 LIMIT 1", (current_school_id(),)
    ).fetchone()


# Terms are always named "1st Term" / "2nd Term" / "3rd Term" from the
# fixed dropdown on Setup → Terms, so cumulative results can order them
# chronologically by name — any other name (very old/custom data) just
# sorts after these three, in creation order.
_TERM_ORDER = {"1st Term": 1, "2nd Term": 2, "3rd Term": 3}


def term_sort_key(t):
    return (_TERM_ORDER.get(t["name"], 99), t["id"])


def terms_for_session(conn, session_id):
    rows = conn.execute("SELECT * FROM terms WHERE session_id=?", (session_id,)).fetchall()
    return sorted(rows, key=term_sort_key)


def student_class_for_session(conn, student_id, session_id):
    """Which class this student was in during a given session — mirrors
    student_class_for_term, but keyed directly by session."""
    row = conn.execute(
        "SELECT class_id FROM enrollments WHERE student_id=? AND session_id=?",
        (student_id, session_id),
    ).fetchone()
    if row:
        return row["class_id"]
    current = conn.execute("SELECT class_id FROM students WHERE id=?", (student_id,)).fetchone()
    return current["class_id"] if current else None


def all_terms_for_school(conn):
    return conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id = terms.session_id "
        "WHERE sessions.school_id=? ORDER BY sessions.id DESC, terms.id DESC",
        (current_school_id(),),
    ).fetchall()


def student_class_for_term(conn, student_id, term_id):
    """Which class this student was actually in during the given term's
    session — falls back to their current class if no enrollment record
    exists for that session (e.g. very old data predating this feature)."""
    row = conn.execute(
        "SELECT e.class_id FROM enrollments e JOIN terms t ON t.session_id = e.session_id "
        "WHERE e.student_id=? AND t.id=?", (student_id, term_id),
    ).fetchone()
    if row:
        return row["class_id"]
    current = conn.execute("SELECT class_id FROM students WHERE id=?", (student_id,)).fetchone()
    return current["class_id"] if current else None


def get_grading_config(conn):
    return conn.execute(
        "SELECT * FROM grading_config WHERE school_id=? LIMIT 1", (current_school_id(),)
    ).fetchone()


def compute_total(ca1, ca2, exam, ca3=0):
    return round((ca1 or 0) + (ca2 or 0) + (ca3 or 0) + (exam or 0), 2)


def ca3_enabled(config):
    """CA3 is optional: a school switches it on by giving it a maximum above 0.
    Every existing school keeps it off (ca3_max = 0) until an admin opts in."""
    try:
        return bool(config and (config["ca3_max"] or 0) > 0)
    except (KeyError, IndexError):
        return False


def save_score(conn, student_id, subject_id, term_id, ca1, ca2, ca3, exam, user_id):
    """The one place an online score row is written (form save and CSV
    import both come through here), including the who-changed-what history."""
    existing = conn.execute(
        "SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?",
        (student_id, subject_id, term_id),
    ).fetchone()
    if existing and (existing["ca1"] != ca1 or existing["ca2"] != ca2
                     or (existing["ca3"] or 0) != ca3 or existing["exam"] != exam):
        conn.execute(
            "INSERT INTO score_history (student_id, subject_id, term_id, old_ca1, old_ca2, old_ca3, old_exam, "
            "new_ca1, new_ca2, new_ca3, new_exam, changed_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (student_id, subject_id, term_id, existing["ca1"], existing["ca2"], existing["ca3"], existing["exam"],
             ca1, ca2, ca3, exam, user_id),
        )
    elif not existing and (ca1 or ca2 or ca3 or exam):
        conn.execute(
            "INSERT INTO score_history (student_id, subject_id, term_id, old_ca1, old_ca2, old_ca3, old_exam, "
            "new_ca1, new_ca2, new_ca3, new_exam, changed_by) VALUES (?,?,?,NULL,NULL,NULL,NULL,?,?,?,?,?)",
            (student_id, subject_id, term_id, ca1, ca2, ca3, exam, user_id),
        )
    conn.execute(
        "INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, ca3, exam) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(student_id, subject_id, term_id) DO UPDATE SET "
        "ca1=excluded.ca1, ca2=excluded.ca2, ca3=excluded.ca3, exam=excluded.exam",
        (student_id, subject_id, term_id, ca1, ca2, ca3, exam),
    )


def score_range_errors(config, ca1, ca2, ca3, exam):
    errs = []
    for label, value, limit in (("CA1", ca1, config["ca1_max"]), ("CA2", ca2, config["ca2_max"]),
                                ("CA3", ca3, config["ca3_max"] or 0), ("Exam", exam, config["exam_max"])):
        if value < 0 or value > limit:
            errs.append(f"{label} {value:g} is outside 0–{limit:g}")
    return errs


def class_in_school(conn, class_id):
    return conn.execute(
        "SELECT * FROM classes WHERE id=? AND school_id=?", (class_id, current_school_id())
    ).fetchone()


def subject_in_school(conn, subject_id):
    return conn.execute(
        "SELECT * FROM subjects WHERE id=? AND school_id=?", (subject_id, current_school_id())
    ).fetchone()


def student_in_school(conn, student_id):
    row = conn.execute(
        "SELECT s.* FROM students s JOIN classes c ON c.id=s.class_id "
        "WHERE s.id=? AND c.school_id=?", (student_id, current_school_id())
    ).fetchone()
    return row


def teacher_in_school(conn, teacher_id):
    return conn.execute(
        "SELECT * FROM users WHERE id=? AND school_id=? AND role='teacher'",
        (teacher_id, current_school_id()),
    ).fetchone()


def require_class_result_access(conn, class_id):
    """Returns None if allowed, or a redirect response if denied."""
    class_row = class_in_school(conn, class_id)
    if not class_row:
        flash("That class doesn't exist.", "error")
        return redirect(url_for("dashboard"))
    if not can_view_class_results(conn, session.get("role"), session.get("position"), session.get("user_id"), class_id):
        flash(
            "You don't have access to view results for this class. Only the principal, "
            "vice principal, exam officer, and this class's form teacher can view its results.",
            "error",
        )
        return redirect(url_for("dashboard"))
    return None


def get_accessible_class_ids(conn, role, position, user_id):
    if can_view_all_results(role, position):
        return "all"
    return form_teacher_class_ids(conn, user_id)


def require_cumulative_enabled(conn):
    """Returns None if this school has Cumulative Result turned on, or a
    redirect response otherwise."""
    school = get_school(conn, current_school_id())
    if not school or not school["cumulative_enabled"]:
        flash("Cumulative/Annual results are turned off for this school. Enable it under Setup → Terms.", "error")
        return redirect(url_for("dashboard"))
    return None


# ---------- PWA: manifest & service worker (served at root scope) ----------

@app.route("/service-worker.js")
def service_worker():
    resp = send_from_directory("static", "service-worker.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")


@app.route("/school-logo")
def school_logo():
    if "school_id" not in session:
        return "", 404
    conn = get_db()
    school = get_school(conn, session["school_id"])
    conn.close()
    if not school or not school["logo_filename"]:
        return "", 404
    return send_from_directory(INSTANCE_DIR, school["logo_filename"])


@app.context_processor
def inject_school_settings():
    if "school_id" in session:
        conn = get_db()
        school = get_school(conn, session["school_id"])
        conn.close()
        if school:
            logo_url = url_for("school_logo") if school["logo_filename"] else None
            font = WEB_FONTS.get(school["web_font"] or "system", WEB_FONTS["system"])
            return dict(
                school_name=school["name"], school_logo_url=logo_url,
                school_logo_align=school["logo_align"],
                school_name_align=school["name_align"] or "center",
                cumulative_enabled=bool(school["cumulative_enabled"]),
                web_font_css=font["css"], web_font_google=font["google"],
                school_timezone=school["timezone"] or "Africa/Lagos",
                school_date_format=school["date_format"] or "dmy",
                result_accent_color=school["result_accent_color"] or "#1f3a5f",
                result_header_layout=school["result_header_layout"] or "logo-left",
            )
    return dict(school_name="School Result System", school_logo_url=None, school_logo_align="center",
                school_name_align="center",
                cumulative_enabled=False, web_font_css=WEB_FONTS["system"]["css"], web_font_google=None,
                school_timezone="Africa/Lagos", school_date_format="dmy",
                result_accent_color="#1f3a5f", result_header_layout="logo-left")


@app.context_processor
def inject_unread_notifications():
    count = 0
    if "user_id" in session:
        conn = get_db()
        row = conn.execute("SELECT last_notification_seen_id FROM users WHERE id=?", (session["user_id"],)).fetchone()
        count = get_unread_notification_count(conn, row["last_notification_seen_id"] if row else 0, session.get("role"), session.get("school_id"))
        conn.close()
    elif "student_id" in session:
        conn = get_db()
        row = conn.execute("SELECT last_notification_seen_id FROM students WHERE id=?", (session["student_id"],)).fetchone()
        count = get_unread_notification_count(conn, row["last_notification_seen_id"] if row else 0, "student", session.get("school_id"))
        conn.close()
    return dict(unread_notifications=count)


# ---------- auth ----------

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
@rate_limit(max_attempts=10, window_seconds=300)
def login():
    if request.method == "POST":
        identifier = request.form["username"].strip()
        password = request.form["password"]
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? "
            "OR (email IS NOT NULL AND LOWER(email)=LOWER(?)) "
            "OR (phone IS NOT NULL AND phone=?)",
            (identifier, identifier, identifier),
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            if not user["is_active"]:
                conn.close()
                flash("This account has been deactivated. Contact your school admin.", "error")
                return render_template("login.html")
            school = get_school(conn, user["school_id"])
            conn.close()
            if school and school["activation_status"] != "active":
                flash("This school hasn't been activated yet. Enter your activation code on the Activate School page.", "error")
                return render_template("login.html")
            if school and school["is_archived"]:
                flash("This school's account has been archived. Contact the platform administrator.", "error")
                return render_template("login.html")
            if school and school["is_suspended"]:
                flash("This school's account has been suspended. Contact the platform administrator.", "error")
                return render_template("login.html")
            if g.portal_school and (not school or school["id"] != g.portal_school["id"]):
                flash(f"That account isn't registered under {g.portal_school['name']}'s portal.", "error")
                return render_template("login.html")
            session.permanent = True
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            session["position"] = user["position"]
            session["school_id"] = user["school_id"]
            session["login_time"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
            return redirect(url_for("dashboard"))
        conn.close()
        flash("Invalid username/email/phone or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/account/password", methods=["GET", "POST"])
@login_required()
def change_password():
    if request.method == "POST":
        current = request.form["current_password"]
        new = request.form["new_password"]
        confirm = request.form["confirm_password"]
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not check_password_hash(user["password_hash"], current):
            flash("Your current password is incorrect.", "error")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new != confirm:
            flash("New password and confirmation don't match.", "error")
        else:
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (generate_password_hash(new), session["user_id"]),
            )
            conn.commit()
            conn.close()
            flash("Password updated.", "success")
            return redirect(url_for("dashboard"))
        conn.close()
    return render_template("change_password.html")


SECURITY_QUESTIONS = [
    "What was the name of your first school?",
    "What is your mother's maiden name?",
    "What is the name of your favorite teacher?",
    "What was the name of your first pet?",
    "What town were you born in?",
]

POSITION_CHOICES = [
    ("principal", "Principal"),
    ("vice_principal", "Vice Principal"),
    ("exam_officer", "Exam Officer"),
    ("form_teacher", "Form Teacher"),
    ("subject_teacher", "Subject Teacher"),
]


@app.route("/register-school", methods=["GET", "POST"])
@rate_limit(max_attempts=5, window_seconds=3600)
def register_school():
    if request.method == "POST":
        school_name = request.form.get("school_name", "").strip()
        registered_email = request.form.get("registered_email", "").strip()
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        security_question = request.form.get("security_question", "")
        security_answer = request.form.get("security_answer", "").strip()

        errors = []
        if not school_name or not name or not username or not password:
            errors.append("Please fill in the school name, your name, username, and password.")
        if not registered_email or "@" not in registered_email or "." not in registered_email.split("@")[-1]:
            errors.append("Please provide a valid email address for the school.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Password and confirmation don't match.")
        if security_question not in SECURITY_QUESTIONS or not security_answer:
            errors.append("Please choose a security question and answer, for password recovery later.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register_school.html", security_questions=SECURITY_QUESTIONS)

        conn = get_db()
        try:
            cur = conn.execute("INSERT INTO schools (name, registered_email) VALUES (?,?)",
                                (school_name, registered_email))
            school_id = cur.lastrowid
            conn.execute(
                "INSERT INTO users (school_id, name, username, password_hash, role, security_question, security_answer_hash) "
                "VALUES (?,?,?,?, 'admin', ?, ?)",
                (school_id, name, username, generate_password_hash(password),
                 security_question, generate_password_hash(security_answer.lower())),
            )
            conn.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (school_id, "2025/2026"))
            session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('1st Term', ?, 1)", (session_id,))
            conn.commit()
            seed_school_defaults(conn, school_id)
            conn.close()
            flash(f"'{school_name}' has been created! Log in with your new admin account below.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError as e:
            conn.rollback()
            conn.close()
            if "users.username" in str(e):
                flash("That username is already taken — please choose another.", "error")
            else:
                flash(f"Couldn't create your school: {e}", "error")
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f"Something went wrong creating your school: {e}", "error")

    return render_template("register_school.html", security_questions=SECURITY_QUESTIONS)


@app.route("/register", methods=["GET", "POST"])
@rate_limit(max_attempts=5, window_seconds=3600)
def register():
    conn = get_db()
    schools = conn.execute("SELECT id, name FROM schools ORDER BY name").fetchall()

    if request.method == "POST":
        school_id = request.form.get("school_id", "")
        school = conn.execute("SELECT * FROM schools WHERE id=?", (school_id,)).fetchone()
        signup_enabled = bool(school and school["staff_signup_code"])

        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip() or None
        phone = request.form.get("phone", "").strip() or None
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        position = request.form.get("position", "")
        signup_code = request.form.get("signup_code", "")
        security_question = request.form.get("security_question", "")
        security_answer = request.form.get("security_answer", "").strip()

        errors = []
        if not school:
            errors.append("Please choose your school.")
        elif not signup_enabled:
            errors.append("Staff registration is currently turned off for that school. Ask your admin to enable it from School Profile.")
        elif signup_code != school["staff_signup_code"]:
            errors.append("That staff signup code is incorrect. Ask your admin for the current code.")

        if not name or not username or not password:
            errors.append("Please fill in your name, username, and password.")
        if position not in dict(POSITION_CHOICES):
            errors.append("Please choose your position.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Password and confirmation don't match.")
        if security_question not in SECURITY_QUESTIONS or not security_answer:
            errors.append("Please choose a security question and provide an answer — this is how you'll recover your account if you forget your password.")
        if email and conn.execute("SELECT 1 FROM users WHERE LOWER(email)=LOWER(?)", (email,)).fetchone():
            errors.append("That email is already registered to another account.")
        if phone and conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            errors.append("That phone number is already registered to another account.")

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            try:
                conn.execute(
                    "INSERT INTO users (school_id, name, username, email, phone, password_hash, role, position, security_question, security_answer_hash) "
                    "VALUES (?,?,?,?,?,?,'teacher',?,?,?)",
                    (
                        school["id"], name, username, email, phone, generate_password_hash(password), position,
                        security_question, generate_password_hash(security_answer.lower()),
                    ),
                )
                conn.commit()
                conn.close()
                flash("Your login has been created. You can now sign in below.", "success")
                return redirect(url_for("login"))
            except Exception:
                flash("That username is already taken — please choose another.", "error")

    conn.close()
    return render_template(
        "register.html", schools=schools,
        position_choices=POSITION_CHOICES, security_questions=SECURITY_QUESTIONS,
    )


@app.route("/recover", methods=["GET", "POST"])
@rate_limit(max_attempts=5, window_seconds=600)
def recover():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if not user or not user["security_question"]:
            flash("We couldn't find a recoverable account with that username. Ask your admin for help resetting it.", "error")
            return redirect(url_for("recover"))
        session["recovery_user_id"] = user["id"]
        return redirect(url_for("recover_answer"))
    return render_template("recover.html")


@app.route("/recover/answer", methods=["GET", "POST"])
@rate_limit(max_attempts=5, window_seconds=600)
def recover_answer():
    user_id = session.get("recovery_user_id")
    if not user_id:
        return redirect(url_for("recover"))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    if request.method == "POST":
        answer = request.form.get("security_answer", "").strip().lower()
        if user and check_password_hash(user["security_answer_hash"], answer):
            session["recovery_verified_user_id"] = user_id
            conn.close()
            return redirect(url_for("recover_reset"))
        conn.close()
        flash("That answer doesn't match. Please try again.", "error")
        return redirect(url_for("recover_answer"))

    conn.close()
    if not user:
        return redirect(url_for("recover"))
    return render_template("recover_answer.html", question=user["security_question"])


@app.route("/recover/reset", methods=["GET", "POST"])
@rate_limit(max_attempts=5, window_seconds=600)
def recover_reset():
    user_id = session.get("recovery_verified_user_id")
    if not user_id:
        return redirect(url_for("recover"))

    if request.method == "POST":
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if len(new) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new != confirm:
            flash("New password and confirmation don't match.", "error")
        else:
            conn = get_db()
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user_id))
            conn.commit()
            revoke_device_credentials_for_user(conn, user_id, "password reset (account recovery)")
            conn.close()
            session.pop("recovery_user_id", None)
            session.pop("recovery_verified_user_id", None)
            flash("Password reset. You can now log in with your new password.", "success")
            return redirect(url_for("login"))
    return render_template("recover_reset.html")


# ---------- dashboard ----------

@app.route("/dashboard")
@login_required()
def dashboard():
    # One UI: staff work in the app (/app), which reads and writes the copy of the
    # school's data on the device and syncs it automatically — the same screens
    # whether the connection is up or down. The server-rendered dashboard below is
    # kept only as a fallback: /dashboard?classic=1
    if not request.args.get("classic"):
        return redirect("/app")
    conn = get_db()
    term = current_term(conn)
    school_id = current_school_id()
    if session["role"] in ("admin", "sub_admin"):
        stats = {
            "students": conn.execute(
                "SELECT COUNT(*) c FROM students s JOIN classes c ON c.id=s.class_id "
                "WHERE c.school_id=? AND s.is_active=1", (school_id,)
            ).fetchone()["c"],
            "classes": conn.execute("SELECT COUNT(*) c FROM classes WHERE school_id=?", (school_id,)).fetchone()["c"],
            "teachers": conn.execute(
                "SELECT COUNT(*) c FROM users WHERE role='teacher' AND school_id=?", (school_id,)
            ).fetchone()["c"],
            "subjects": conn.execute("SELECT COUNT(*) c FROM subjects WHERE school_id=?", (school_id,)).fetchone()["c"],
        }
        conn.close()
        return render_template("admin_dashboard.html", term=term, stats=stats)
    else:
        assignments = conn.execute(
            "SELECT cs.*, c.name as class_name, s.name as subject_name FROM class_subjects cs "
            "JOIN classes c ON c.id=cs.class_id JOIN subjects s ON s.id=cs.subject_id "
            "WHERE cs.teacher_id=? AND c.school_id=?", (session["user_id"], school_id)
        ).fetchall()
        accessible = get_accessible_class_ids(conn, session.get("role"), session.get("position"), session["user_id"])
        if accessible == "all":
            result_classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
        elif accessible:
            placeholders = ",".join("?" * len(accessible))
            result_classes = conn.execute(
                f"SELECT * FROM classes WHERE id IN ({placeholders}) AND school_id=? ORDER BY name",
                tuple(accessible) + (school_id,),
            ).fetchall()
        else:
            result_classes = []
        is_form_teacher = bool(form_teacher_class_ids(conn, session["user_id"]))
        conn.close()
        return render_template(
            "teacher_dashboard.html", term=term, assignments=assignments,
            position_label=POSITION_LABELS.get(session.get("position")),
            result_classes=result_classes, is_form_teacher=is_form_teacher,
        )


# ---------- admin: school profile ----------

@app.route("/admin/sync-conflicts")
@login_required("admin", "sub_admin")
def admin_sync_conflicts():
    """Conflicts recorded by the offline sync API (sync_api.py) when a
    device's push disagreed with the server's current data. These aren't
    resolved automatically — a human decides which version is right — so
    without this page they'd only be visible to whichever offline device
    caused them (via the Offline App's own Sync Status screen), and would
    otherwise sit invisible in the database indefinitely."""
    conn = get_db()
    school_id = current_school_id()
    rows = conn.execute(
        "SELECT * FROM sync_conflicts WHERE school_id=? AND resolved=0 ORDER BY detected_at DESC",
        (school_id,),
    ).fetchall()
    conflicts = []
    for r in rows:
        conflicts.append({
            "id": r["id"], "entity": r["entity"], "client_uuid": r["client_uuid"],
            "device_id": r["device_id"], "detected_at": r["detected_at"],
            "client_payload": json.loads(r["client_payload"]),
            "server_payload": json.loads(r["server_payload"]),
        })
    conn.close()
    return render_template("admin_sync_conflicts.html", conflicts=conflicts)


@app.route("/admin/sync-conflicts/<int:conflict_id>/resolve", methods=["POST"])
@login_required("admin", "sub_admin")
def admin_resolve_sync_conflict(conflict_id):
    from sync_api import ENTITIES
    conn = get_db()
    school_id = current_school_id()
    row = conn.execute(
        "SELECT * FROM sync_conflicts WHERE id=? AND school_id=?", (conflict_id, school_id)
    ).fetchone()
    if not row:
        flash("Conflict not found.", "error")
        conn.close()
        return redirect(url_for("admin_sync_conflicts"))

    action = request.form.get("action")
    cfg = ENTITIES.get(row["entity"])
    if action == "apply_client" and cfg:
        client_fields = json.loads(row["client_payload"])
        client_fields = {k: v for k, v in client_fields.items() if k in cfg["fields"]}
        existing = conn.execute(
            f"SELECT id FROM {cfg['table']} WHERE client_uuid=?", (row["client_uuid"],)
        ).fetchone()
        if existing and client_fields:
            set_clause = ", ".join(f"{k}=?" for k in client_fields)
            conn.execute(
                f"UPDATE {cfg['table']} SET {set_clause}, updated_at=? WHERE client_uuid=?",
                (*client_fields.values(), datetime.datetime.utcnow().isoformat(timespec="seconds"), row["client_uuid"]),
            )
            resolution = "applied_client_version"
        else:
            resolution = "kept_server_version (client row not found — likely a create conflict; add it manually if needed)"
    else:
        resolution = "kept_server_version"

    conn.execute(
        "UPDATE sync_conflicts SET resolved=1, resolved_at=?, resolution=? WHERE id=?",
        (datetime.datetime.utcnow().isoformat(timespec="seconds"), resolution, conflict_id),
    )
    conn.commit()
    conn.close()
    flash("Conflict marked resolved.", "success")
    return redirect(url_for("admin_sync_conflicts"))


@app.route("/admin/school", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_school():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        name = request.form.get("school_name", "").strip()
        logo_align = request.form.get("logo_align", "center")
        if logo_align not in ("left", "center", "right"):
            logo_align = "center"
        name_align = request.form.get("name_align", "center")
        if name_align not in ("left", "center", "right"):
            name_align = "center"
        timezone = request.form.get("timezone", "Africa/Lagos").strip() or "Africa/Lagos"
        if timezone not in TIMEZONE_CHOICES:
            timezone = "Africa/Lagos"
        date_format = request.form.get("date_format", "dmy")
        if date_format not in ("dmy", "mdy", "ymd"):
            date_format = "dmy"
        result_accent_color = request.form.get("result_accent_color", "#1f3a5f").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", result_accent_color or ""):
            result_accent_color = "#1f3a5f"
        result_header_layout = request.form.get("result_header_layout", "logo-left")
        if result_header_layout not in ("logo-left", "logo-top-center", "logo-right", "no-logo"):
            result_header_layout = "logo-left"
        auto_teacher_comment = 1 if request.form.get("auto_teacher_comment") else 0
        auto_principal_comment = 1 if request.form.get("auto_principal_comment") else 0
        show_result_date = 1 if request.form.get("show_result_date") else 0
        web_font = request.form.get("web_font", "system")
        if web_font not in WEB_FONTS:
            web_font = "system"
        pdf_font = request.form.get("pdf_font", "Helvetica")
        if pdf_font not in PDF_FONT_CHOICES:
            pdf_font = "Helvetica"
        if not name:
            flash("School name cannot be empty.", "error")
        else:
            conn.execute(
                "UPDATE schools SET name=?, logo_align=?, name_align=?, timezone=?, date_format=?, "
                "result_accent_color=?, result_header_layout=?, "
                "auto_teacher_comment=?, auto_principal_comment=?, "
                "web_font=?, pdf_font=?, show_result_date=? WHERE id=?",
                (name, logo_align, name_align, timezone, date_format,
                 result_accent_color, result_header_layout,
                 auto_teacher_comment, auto_principal_comment, web_font, pdf_font,
                 show_result_date, school_id),
            )
            conn.commit()
            flash("School profile updated.", "success")

        file = request.files.get("logo")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in ALLOWED_LOGO_EXTENSIONS:
                flash("Logo must be a PNG, JPG, or GIF image.", "error")
            else:
                old = get_school(conn, school_id)
                if old and old["logo_filename"]:
                    old_path = os.path.join(INSTANCE_DIR, old["logo_filename"])
                    if os.path.exists(old_path):
                        os.remove(old_path)
                new_filename = f"school_logo_{school_id}.{ext}"
                os.makedirs(INSTANCE_DIR, exist_ok=True)
                file.save(os.path.join(INSTANCE_DIR, new_filename))
                conn.execute("UPDATE schools SET logo_filename=? WHERE id=?", (new_filename, school_id))
                conn.commit()
                flash("Logo updated.", "success")

    settings = get_school(conn, school_id)
    conn.close()
    return render_template("admin_school.html", settings=settings, web_fonts=WEB_FONTS, pdf_fonts=PDF_FONT_CHOICES,
                            base_domain=BASE_DOMAIN, timezones=TIMEZONE_CHOICES, header_layouts=RESULT_HEADER_LAYOUTS)


@app.route("/admin/school/subdomain", methods=["POST"])
@login_required("admin", "sub_admin")
def set_school_subdomain():
    conn = get_db()
    school_id = current_school_id()
    raw = request.form.get("subdomain", "").strip().lower()
    if not raw:
        conn.execute("UPDATE schools SET subdomain=NULL WHERE id=?", (school_id,))
        conn.commit()
        conn.close()
        flash("Custom subdomain removed.", "success")
        return redirect(url_for("admin_school"))

    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])?", raw):
        conn.close()
        flash("Subdomain must be 3-30 characters: lowercase letters, digits and hyphens only, and can't start or end with a hyphen.", "error")
        return redirect(url_for("admin_school"))
    if raw in RESERVED_SUBDOMAINS:
        conn.close()
        flash(f"'{raw}' is reserved and can't be used as a subdomain.", "error")
        return redirect(url_for("admin_school"))

    taken = conn.execute("SELECT id FROM schools WHERE subdomain=? AND id!=?", (raw, school_id)).fetchone()
    if taken:
        conn.close()
        flash(f"'{raw}' is already taken by another school. Please choose a different subdomain.", "error")
        return redirect(url_for("admin_school"))

    conn.execute("UPDATE schools SET subdomain=? WHERE id=?", (raw, school_id))
    conn.commit()
    conn.close()
    flash(f"Subdomain set to '{raw}'.", "success")
    return redirect(url_for("admin_school"))


@app.route("/admin/school/remove_logo", methods=["POST"])
@login_required("admin", "sub_admin")
def remove_school_logo():
    conn = get_db()
    school_id = current_school_id()
    settings = get_school(conn, school_id)
    if settings and settings["logo_filename"]:
        old_path = os.path.join(INSTANCE_DIR, settings["logo_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
        conn.execute("UPDATE schools SET logo_filename=NULL WHERE id=?", (school_id,))
        conn.commit()
        flash("Logo removed.", "success")
    conn.close()
    return redirect(url_for("admin_school"))


@app.route("/admin/school/signup_code", methods=["POST"])
@login_required("admin", "sub_admin")
def set_staff_signup_code():
    code = request.form.get("staff_signup_code", "").strip()
    conn = get_db()
    conn.execute("UPDATE schools SET staff_signup_code=? WHERE id=?", (code or None, current_school_id()))
    conn.commit()
    conn.close()
    if code:
        flash(f"Staff registration is now enabled with the code: {code}", "success")
    else:
        flash("Staff registration has been turned off.", "success")
    return redirect(url_for("admin_school"))


@app.route("/admin/email", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_email():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            conn.execute(
                "UPDATE schools SET smtp_host=?, smtp_port=?, smtp_username=?, smtp_password=?, "
                "smtp_use_tls=?, smtp_from_email=?, smtp_from_name=? WHERE id=?",
                (
                    request.form.get("smtp_host", "").strip() or None,
                    int(request.form["smtp_port"]) if request.form.get("smtp_port") else None,
                    request.form.get("smtp_username", "").strip() or None,
                    request.form.get("smtp_password", "").strip() or None,
                    1 if request.form.get("smtp_use_tls") else 0,
                    request.form.get("smtp_from_email", "").strip() or None,
                    request.form.get("smtp_from_name", "").strip() or None,
                    school_id,
                ),
            )
            conn.commit()
            flash("Email settings saved.", "success")
        elif action == "test":
            test_to = request.form.get("test_email", "").strip()
            school = get_school(conn, school_id)
            if test_to:
                ok, msg = send_email(school, test_to, "Test email from your School Result System",
                                      "If you're reading this, your email settings are working correctly.")
                flash(msg, "success" if ok else "error")
    settings = get_school(conn, school_id)
    conn.close()
    return render_template("admin_email.html", settings=settings)


# ---------- settings hub ----------

@app.route("/admin/school/result-preview")
@login_required("admin", "sub_admin")
def result_design_preview():
    conn = get_db()
    school = get_school(conn, current_school_id())
    conn.close()
    return render_template("result_preview.html", settings=school)


@app.route("/settings")
@login_required()
def settings_hub():
    conn = get_db()
    me = conn.execute("SELECT email, phone FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("settings_hub.html", me=me)


@app.route("/account/contact", methods=["POST"])
@login_required()
def update_my_contact():
    conn = get_db()
    email = request.form.get("email", "").strip() or None
    phone = request.form.get("phone", "").strip() or None
    if email and conn.execute("SELECT 1 FROM users WHERE LOWER(email)=LOWER(?) AND id!=?", (email, session["user_id"])).fetchone():
        conn.close()
        flash("That email is already in use by another account.", "error")
        return redirect(url_for("settings_hub"))
    if phone and conn.execute("SELECT 1 FROM users WHERE phone=? AND id!=?", (phone, session["user_id"])).fetchone():
        conn.close()
        flash("That phone number is already in use by another account.", "error")
        return redirect(url_for("settings_hub"))
    conn.execute("UPDATE users SET email=?, phone=? WHERE id=?", (email, phone, session["user_id"]))
    conn.commit()
    conn.close()
    flash("Contact info updated.", "success")
    return redirect(url_for("settings_hub"))


# ---------- staff profile, photo & digital signature ----------

@app.route("/my-profile")
@login_required()
def my_profile():
    return redirect(url_for("staff_profile", user_id=session["user_id"]))


@app.route("/staff/<int:user_id>")
@login_required()
def staff_profile(user_id):
    conn = get_db()
    school_id = current_school_id()
    staff = conn.execute("SELECT * FROM users WHERE id=? AND school_id=?", (user_id, school_id)).fetchone()
    if not staff:
        conn.close()
        flash("Staff member not found.", "error")
        return redirect(url_for("dashboard"))
    is_self = user_id == session["user_id"]
    can_manage = session["role"] in ("admin", "sub_admin")
    if not is_self and not can_manage:
        conn.close()
        flash("You don't have access to that profile.", "error")
        return redirect(url_for("dashboard"))

    subjects_taught = conn.execute(
        "SELECT DISTINCT s.name FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id "
        "WHERE cs.teacher_id=? ORDER BY s.name", (user_id,)
    ).fetchall()
    classes_taught = conn.execute(
        "SELECT DISTINCT c.name FROM class_subjects cs JOIN classes c ON c.id=cs.class_id "
        "WHERE cs.teacher_id=? ORDER BY c.name", (user_id,)
    ).fetchall()
    form_classes = conn.execute(
        "SELECT name FROM classes WHERE form_teacher_id=? AND school_id=? ORDER BY name", (user_id, school_id)
    ).fetchall()
    recent_attendance = conn.execute(
        "SELECT * FROM staff_attendance WHERE user_id=? ORDER BY date DESC, id DESC LIMIT 20", (user_id,)
    ).fetchall()
    conn.close()
    return render_template(
        "staff_profile.html", staff=staff, is_self=is_self, can_manage=can_manage,
        subjects_taught=subjects_taught, classes_taught=classes_taught, form_classes=form_classes,
        recent_attendance=recent_attendance, position_labels=POSITION_LABELS,
    )


@app.route("/staff/<int:user_id>/photo")
@login_required()
def staff_photo(user_id):
    conn = get_db()
    staff = conn.execute("SELECT photo_filename, school_id FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not staff or staff["school_id"] != current_school_id() or not staff["photo_filename"]:
        return "", 404
    return send_from_directory(STAFF_PHOTOS_DIR, staff["photo_filename"])


@app.route("/staff/<int:user_id>/signature")
def staff_signature(user_id):
    # Used as an <img src> straight from result pages (viewed by staff AND
    # by logged-in students/parents), so this accepts either session kind —
    # same rule school_logo() already uses — rather than @login_required(),
    # which only recognises staff sessions.
    if "school_id" not in session:
        return "", 404
    conn = get_db()
    staff = conn.execute("SELECT signature_filename, school_id FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not staff or staff["school_id"] != session["school_id"] or not staff["signature_filename"]:
        return "", 404
    return send_from_directory(SIGNATURES_DIR, staff["signature_filename"])


@app.route("/account/photo/upload", methods=["POST"])
@login_required()
def upload_my_photo():
    conn = get_db()
    user_id = session["user_id"]
    file = request.files.get("photo")
    if not file or not file.filename:
        conn.close()
        flash("Please choose an image file to upload.", "error")
        return redirect(url_for("staff_profile", user_id=user_id))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        conn.close()
        flash("Photo must be a PNG, JPG, or GIF image.", "error")
        return redirect(url_for("staff_profile", user_id=user_id))
    old = conn.execute("SELECT photo_filename FROM users WHERE id=?", (user_id,)).fetchone()
    if old and old["photo_filename"]:
        old_path = os.path.join(STAFF_PHOTOS_DIR, old["photo_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
    new_filename = f"staff_{user_id}.{ext}"
    os.makedirs(STAFF_PHOTOS_DIR, exist_ok=True)
    file.save(os.path.join(STAFF_PHOTOS_DIR, new_filename))
    conn.execute("UPDATE users SET photo_filename=? WHERE id=?", (new_filename, user_id))
    conn.commit()
    conn.close()
    flash("Photo updated.", "success")
    return redirect(url_for("staff_profile", user_id=user_id))


@app.route("/account/signature/upload", methods=["POST"])
@login_required()
def upload_my_signature():
    conn = get_db()
    user_id = session["user_id"]
    file = request.files.get("signature")
    if not file or not file.filename:
        conn.close()
        flash("Please choose an image file to upload.", "error")
        return redirect(url_for("staff_profile", user_id=user_id))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        conn.close()
        flash("Signature must be a PNG, JPG, or GIF image (ideally a transparent PNG).", "error")
        return redirect(url_for("staff_profile", user_id=user_id))
    old = conn.execute("SELECT signature_filename FROM users WHERE id=?", (user_id,)).fetchone()
    if old and old["signature_filename"]:
        old_path = os.path.join(SIGNATURES_DIR, old["signature_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
    new_filename = f"sig_{user_id}.{ext}"
    os.makedirs(SIGNATURES_DIR, exist_ok=True)
    file.save(os.path.join(SIGNATURES_DIR, new_filename))
    # Uploading a fresh signature doesn't silently turn it on — the person
    # may want to review it first, so `use_digital_signature` is left as-is
    # and toggled explicitly below.
    conn.execute("UPDATE users SET signature_filename=? WHERE id=?", (new_filename, user_id))
    conn.commit()
    conn.close()
    flash("Signature uploaded. Turn it on below to have it stamped on results automatically.", "success")
    return redirect(url_for("staff_profile", user_id=user_id))


@app.route("/account/signature/toggle", methods=["POST"])
@login_required()
def toggle_my_signature():
    conn = get_db()
    user_id = session["user_id"]
    use_it = 1 if request.form.get("use_digital_signature") else 0
    row = conn.execute("SELECT signature_filename FROM users WHERE id=?", (user_id,)).fetchone()
    if use_it and (not row or not row["signature_filename"]):
        conn.close()
        flash("Upload a signature image before turning this on.", "error")
        return redirect(url_for("staff_profile", user_id=user_id))
    conn.execute("UPDATE users SET use_digital_signature=? WHERE id=?", (use_it, user_id))
    conn.commit()
    conn.close()
    flash("Digital signature " + ("enabled." if use_it else "disabled — results will show a blank line for a manual signature."), "success")
    return redirect(url_for("staff_profile", user_id=user_id))


@app.route("/account/signature/remove", methods=["POST"])
@login_required()
def remove_my_signature():
    conn = get_db()
    user_id = session["user_id"]
    row = conn.execute("SELECT signature_filename FROM users WHERE id=?", (user_id,)).fetchone()
    if row and row["signature_filename"]:
        old_path = os.path.join(SIGNATURES_DIR, row["signature_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
        conn.execute("UPDATE users SET signature_filename=NULL, use_digital_signature=0 WHERE id=?", (user_id,))
        conn.commit()
        flash("Signature removed.", "success")
    conn.close()
    return redirect(url_for("staff_profile", user_id=user_id))


# ---------- notifications (staff) ----------

@app.route("/notifications")
@login_required()
def notifications_inbox():
    conn = get_db()
    notifications = get_visible_notifications(conn, session.get("role"), session.get("school_id"))
    if notifications:
        conn.execute("UPDATE users SET last_notification_seen_id=? WHERE id=?", (notifications[0]["id"], session["user_id"]))
        conn.commit()
    conn.close()
    return render_template("notifications_inbox.html", notifications=notifications)


@app.route("/notifications/compose", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def notifications_compose():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        target_role = request.form.get("target_role", "all")
        if target_role not in ("all", "teacher", "student"):
            target_role = "all"
        if not title or not message:
            flash("Please fill in both a title and a message.", "error")
        else:
            conn = get_db()
            conn.execute(
                "INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES (?,?,?,?,?)",
                (f"Admin: {session['name']}", current_school_id(), target_role, title, message),
            )
            conn.commit()
            conn.close()
            flash("Notification sent.", "success")
            return redirect(url_for("notifications_inbox"))
    return render_template("notifications_compose.html")


@app.route("/settings/delete_account", methods=["POST"])
@login_required("admin")
def delete_account():
    password = request.form.get("password", "")
    confirm_text = request.form.get("confirm_text", "").strip().upper()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

    if not check_password_hash(user["password_hash"], password):
        conn.close()
        flash("Your password was incorrect. Account not deleted.", "error")
        return redirect(url_for("settings_hub"))
    if confirm_text != "DELETE":
        conn.close()
        flash("You must type DELETE exactly to confirm. Account not deleted.", "error")
        return redirect(url_for("settings_hub"))

    school_id = current_school_id()
    class_ids = [r["id"] for r in conn.execute("SELECT id FROM classes WHERE school_id=?", (school_id,)).fetchall()]
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        student_ids = [r["id"] for r in conn.execute(
            f"SELECT id FROM students WHERE class_id IN ({placeholders})", class_ids
        ).fetchall()]
        if student_ids:
            sp = ",".join("?" * len(student_ids))
            conn.execute(f"DELETE FROM student_skill_ratings WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM student_term_info WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM score_history WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM scores WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM enrollments WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM students WHERE id IN ({sp})", student_ids)
        conn.execute(f"DELETE FROM class_subjects WHERE class_id IN ({placeholders})", class_ids)
        conn.execute(f"DELETE FROM classes WHERE id IN ({placeholders})", class_ids)
    conn.execute("DELETE FROM subjects WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM skill_traits WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM grade_scale WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM grading_config WHERE school_id=?", (school_id,))
    term_ids = [r["id"] for r in conn.execute(
        "SELECT terms.id FROM terms JOIN sessions ON sessions.id=terms.session_id WHERE sessions.school_id=?",
        (school_id,),
    ).fetchall()]
    if term_ids:
        tp = ",".join("?" * len(term_ids))
        conn.execute(f"DELETE FROM terms WHERE id IN ({tp})", term_ids)
    conn.execute("DELETE FROM sessions WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM users WHERE school_id=?", (school_id,))
    school = get_school(conn, school_id)
    school_name = school["name"] if school else "Unknown"
    if school and school["logo_filename"]:
        old_path = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
    conn.execute("DELETE FROM schools WHERE id=?", (school_id,))
    log_audit(conn, "admin", user["name"], "self_delete_account",
              details=f"School admin permanently deleted their own school '{school_name}'", school_id=None)
    conn.commit()
    conn.close()
    session.clear()
    flash("Your school's account and all its data have been permanently deleted.", "success")
    return redirect(url_for("login"))


# ---------- admin: setup ----------

@app.route("/admin/classes", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_classes():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        name = request.form["name"].strip()
        category = request.form.get("category", "").strip() or None
        if category and category not in CLASS_CATEGORIES:
            category = None
        arms = parse_arms(request.form.get("arms", ""))
        if name and arms:
            # "JSS 1" + arms "A, B, C" -> three classes: "JSS 1 A", "JSS 1 B", "JSS 1 C"
            added, existed = [], []
            for arm in arms:
                full = f"{name} {arm}"
                try:
                    conn.execute("INSERT INTO classes (school_id, name, category, level, arm) VALUES (?,?,?,?,?)",
                                 (school_id, full, category, name, arm))
                    added.append(full)
                except Exception:
                    existed.append(full)
            conn.commit()
            if added:
                flash("Added: " + ", ".join(added) + ".", "success")
            if existed:
                flash("Already existed: " + ", ".join(existed) + ".", "error")
        elif name:
            # A phone running the earlier build may replay a form it queued while offline; its token
            # makes the create happen once, and the X-Offline-Sync header asks for JSON with the new id.
            offline_token = request.form.get("offline_token")
            existing_id = offline_sync_existing_id(conn, offline_token)
            if existing_id:
                if is_offline_sync_request():
                    conn.close()
                    return {"ok": True, "id": existing_id}
                flash(f"Class '{name}' added.", "success")
            else:
                try:
                    cur = conn.execute("INSERT INTO classes (school_id, name, category) VALUES (?,?,?)", (school_id, name, category))
                    conn.commit()
                    offline_sync_remember(conn, offline_token, "class", cur.lastrowid)
                    if is_offline_sync_request():
                        conn.close()
                        return {"ok": True, "id": cur.lastrowid}
                    flash(f"Class '{name}' added.", "success")
                except Exception:
                    if is_offline_sync_request():
                        conn.close()
                        return {"ok": False, "error": "That class already exists."}, 409
                    flash("That class already exists.", "error")
    classes = conn.execute(
        "SELECT c.*, u.name as teacher_name FROM classes c LEFT JOIN users u ON u.id=c.form_teacher_id "
        "WHERE c.school_id=? ORDER BY c.name", (school_id,)
    ).fetchall()
    teachers = conn.execute("SELECT * FROM users WHERE role='teacher' AND school_id=? ORDER BY name", (school_id,)).fetchall()
    conn.close()
    return render_template("admin_classes.html", classes=classes, teachers=teachers, categories=CLASS_CATEGORIES)


@app.route("/admin/classes/<int:class_id>/set_category", methods=["POST"])
@login_required("admin", "sub_admin")
def set_class_category(class_id):
    conn = get_db()
    class_row = class_in_school(conn, class_id)
    if not class_row:
        conn.close()
        flash("That class doesn't exist.", "error")
        return redirect(url_for("admin_classes"))
    category = request.form.get("category", "").strip() or None
    if category and category not in CLASS_CATEGORIES:
        conn.close()
        flash("Not a recognized category.", "error")
        return redirect(url_for("admin_classes"))
    conn.execute("UPDATE classes SET category=? WHERE id=?", (category, class_id))
    conn.commit()
    conn.close()
    flash(f"Category for '{class_row['name']}' updated.", "success")
    return redirect(url_for("admin_classes"))


@app.route("/admin/classes/<int:class_id>/set_form_teacher", methods=["POST"])
@login_required("admin", "sub_admin")
def set_form_teacher(class_id):
    conn = get_db()
    if not class_in_school(conn, class_id):
        conn.close()
        flash("Class not found.", "error")
        return redirect(url_for("admin_classes"))
    teacher_id = request.form.get("teacher_id") or None
    if teacher_id and not teacher_in_school(conn, teacher_id):
        conn.close()
        flash("That teacher was not found.", "error")
        return redirect(url_for("admin_classes"))
    conn.execute("UPDATE classes SET form_teacher_id=? WHERE id=?", (teacher_id, class_id))
    conn.commit()
    conn.close()
    flash("Form teacher updated.", "success")
    return redirect(url_for("admin_classes"))


@app.route("/admin/classes/<int:class_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_class(class_id):
    conn = get_db()
    if not class_in_school(conn, class_id):
        conn.close()
        flash("Class not found.", "error")
        return redirect(url_for("admin_classes"))
    student_count = conn.execute(
        "SELECT COUNT(*) c FROM students WHERE class_id=?", (class_id,)
    ).fetchone()["c"]
    if student_count > 0:
        conn.close()
        flash(f"Can't delete this class — it still has {student_count} student(s) in it. Remove or reassign them first.", "error")
        return redirect(url_for("admin_classes"))
    conn.execute("DELETE FROM class_subjects WHERE class_id=?", (class_id,))
    conn.execute("DELETE FROM classes WHERE id=?", (class_id,))
    conn.commit()
    conn.close()
    flash("Class deleted.", "success")
    return redirect(url_for("admin_classes"))


@app.route("/admin/subjects", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_subjects():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        name = request.form["name"].strip()
        offline_token = request.form.get("offline_token")
        if name:
            existing_id = offline_sync_existing_id(conn, offline_token)
            if existing_id:
                if is_offline_sync_request():
                    conn.close()
                    return {"ok": True, "id": existing_id}
                flash(f"Subject '{name}' added.", "success")
            else:
                try:
                    cur = conn.execute("INSERT INTO subjects (school_id, name) VALUES (?,?)", (school_id, name))
                    conn.commit()
                    offline_sync_remember(conn, offline_token, "subject", cur.lastrowid)
                    if is_offline_sync_request():
                        conn.close()
                        return {"ok": True, "id": cur.lastrowid}
                    flash(f"Subject '{name}' added.", "success")
                except Exception:
                    if is_offline_sync_request():
                        conn.close()
                        return {"ok": False, "error": "That subject already exists."}, 409
                    flash("That subject already exists.", "error")
    subjects = conn.execute("SELECT * FROM subjects WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    conn.close()
    return render_template("admin_subjects.html", subjects=subjects)


@app.route("/admin/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_subject(subject_id):
    conn = get_db()
    if not subject_in_school(conn, subject_id):
        conn.close()
        flash("Subject not found.", "error")
        return redirect(url_for("admin_subjects"))
    usage = conn.execute(
        "SELECT COUNT(*) c FROM class_subjects WHERE subject_id=?", (subject_id,)
    ).fetchone()["c"]
    if usage > 0:
        conn.close()
        flash("Can't delete this subject — it's still assigned to one or more classes. Unassign it first.", "error")
        return redirect(url_for("admin_subjects"))
    conn.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
    conn.commit()
    conn.close()
    flash("Subject deleted.", "success")
    return redirect(url_for("admin_subjects"))


@app.route("/admin/class_subjects", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_class_subjects():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        class_id = request.form["class_id"]
        subject_id = request.form["subject_id"]
        teacher_id = request.form.get("teacher_id") or None
        if not class_in_school(conn, class_id) or not subject_in_school(conn, subject_id):
            flash("Class or subject not found.", "error")
        elif teacher_id and not teacher_in_school(conn, teacher_id):
            flash("That teacher was not found.", "error")
        else:
            try:
                conn.execute(
                    "INSERT INTO class_subjects (class_id, subject_id, teacher_id) VALUES (?,?,?)",
                    (class_id, subject_id, teacher_id),
                )
                conn.commit()
                flash("Subject assigned to class.", "success")
            except Exception:
                flash("That subject is already assigned to this class.", "error")
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    subjects = conn.execute("SELECT * FROM subjects WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    teachers = conn.execute("SELECT * FROM users WHERE role='teacher' AND school_id=? ORDER BY name", (school_id,)).fetchall()
    assignments = conn.execute(
        "SELECT cs.*, c.name as class_name, s.name as subject_name, u.name as teacher_name "
        "FROM class_subjects cs JOIN classes c ON c.id=cs.class_id "
        "JOIN subjects s ON s.id=cs.subject_id LEFT JOIN users u ON u.id=cs.teacher_id "
        "WHERE c.school_id=? ORDER BY c.name, s.name", (school_id,)
    ).fetchall()
    conn.close()
    return render_template(
        "admin_class_subjects.html", classes=classes, subjects=subjects,
        teachers=teachers, assignments=assignments
    )


@app.route("/admin/class_subjects/<int:cs_id>/assign_teacher", methods=["POST"])
@login_required("admin", "sub_admin")
def assign_teacher(cs_id):
    conn = get_db()
    teacher_id = request.form.get("teacher_id") or None
    if teacher_id and not teacher_in_school(conn, teacher_id):
        conn.close()
        flash("That teacher was not found.", "error")
        return redirect(url_for("admin_class_subjects"))
    conn.execute(
        "UPDATE class_subjects SET teacher_id=? WHERE id=? AND class_id IN (SELECT id FROM classes WHERE school_id=?)",
        (teacher_id, cs_id, current_school_id()),
    )
    conn.commit()
    conn.close()
    flash("Teacher assigned.", "success")
    return redirect(url_for("admin_class_subjects"))


@app.route("/admin/class_subjects/<int:cs_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_class_subject(cs_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM class_subjects WHERE id=? AND class_id IN (SELECT id FROM classes WHERE school_id=?)",
        (cs_id, current_school_id()),
    )
    conn.commit()
    conn.close()
    flash("Assignment removed.", "success")
    return redirect(url_for("admin_class_subjects"))


@app.route("/admin/students", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_students():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        class_id = request.form["class_id"]
        offline_token = request.form.get("offline_token")
        existing_id = offline_sync_existing_id(conn, offline_token)
        if existing_id:
            if is_offline_sync_request():
                conn.close()
                return {"ok": True, "id": existing_id}
            flash(f"Student '{request.form['first_name']} {request.form['last_name']}' added.", "success")
        elif not class_in_school(conn, class_id):
            if is_offline_sync_request():
                conn.close()
                return {"ok": False, "error": "Class not found — it may not have synced yet."}, 409
            flash("Class not found.", "error")
        else:
            try:
                cur = conn.execute(
                    "INSERT INTO students (admission_no, first_name, last_name, other_names, "
                    "gender, class_id, date_of_birth, religion, parent_name, parent_address, parent_email, parent_phone, parent_relationship, "
                    "status, phone) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        request.form["admission_no"].strip(),
                        request.form["first_name"].strip(),
                        request.form["last_name"].strip(),
                        request.form.get("other_names", "").strip() or None,
                        request.form["gender"],
                        class_id,
                        request.form.get("date_of_birth", "").strip() or None,
                        request.form.get("religion", "").strip() or None,
                        request.form.get("parent_name", "").strip() or None,
                        request.form.get("parent_address", "").strip() or None,
                        request.form.get("parent_email", "").strip() or None,
                        request.form.get("parent_phone", "").strip() or None,
                        request.form.get("parent_relationship", "").strip() or None,
                        request.form.get("status", "Active") if request.form.get("status") in
                            ("Active", "Graduated", "Transferred", "Withdrawn", "Suspended") else "Active",
                        request.form.get("phone", "").strip() or None,
                    ),
                )
                upsert_enrollment(conn, cur.lastrowid, class_id)
                conn.commit()
                offline_sync_remember(conn, offline_token, "student", cur.lastrowid)
                if is_offline_sync_request():
                    conn.close()
                    return {"ok": True, "id": cur.lastrowid}
                flash(f"Student '{request.form['first_name']} {request.form['last_name']}' added.", "success")
            except Exception:
                if is_offline_sync_request():
                    conn.close()
                    return {"ok": False, "error": "That Admission No. / Register No. is already in use in this class."}, 409
                flash("That Admission No. / Register No. is already in use in this class.", "error")
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    class_filter = request.args.get("class_id")
    if class_filter:
        students = conn.execute(
            "SELECT s.*, c.name as class_name FROM students s JOIN classes c ON c.id=s.class_id "
            "WHERE s.class_id=? AND c.school_id=? AND s.is_active=1 ORDER BY s.last_name", (class_filter, school_id)
        ).fetchall()
    else:
        students = conn.execute(
            "SELECT s.*, c.name as class_name FROM students s JOIN classes c ON c.id=s.class_id "
            "WHERE c.school_id=? AND s.is_active=1 ORDER BY c.name, s.last_name", (school_id,)
        ).fetchall()
    conn.close()
    return render_template(
        "admin_students.html", classes=classes, students=students, class_filter=class_filter,
        student_full_name=student_full_name,
    )


@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_student(student_id):
    conn = get_db()
    if not student_in_school(conn, student_id):
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("admin_students"))
    conn.execute("DELETE FROM student_skill_ratings WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM student_term_info WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM score_history WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM scores WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM enrollments WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    conn.close()
    flash("Student and their records deleted.", "success")
    return redirect(url_for("admin_students"))


@app.route("/students/<int:student_id>/parent")
@login_required()
def parent_profile(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    if session["role"] not in ("admin", "sub_admin") and student["class_id"] not in form_teacher_class_ids(conn, session["user_id"]):
        conn.close()
        flash("You don't have access to view this parent's profile.", "error")
        return redirect(url_for("dashboard"))
    if not student["parent_phone"] and not student["parent_email"]:
        conn.close()
        flash("No parent/guardian contact info has been recorded for this student yet.", "error")
        return redirect(url_for("student_profile", student_id=student_id))

    school_id = current_school_id()
    # A "parent profile" isn't its own login/account in this system yet —
    # it's assembled from the parent_* contact fields shared across every
    # student record that has the same guardian, matched by phone (or email
    # when no phone was given).
    if student["parent_phone"]:
        siblings = conn.execute(
            "SELECT s.*, c.name as class_name FROM students s JOIN classes c ON c.id=s.class_id "
            "WHERE c.school_id=? AND s.parent_phone=? AND s.is_active=1 ORDER BY s.first_name",
            (school_id, student["parent_phone"]),
        ).fetchall()
    else:
        siblings = conn.execute(
            "SELECT s.*, c.name as class_name FROM students s JOIN classes c ON c.id=s.class_id "
            "WHERE c.school_id=? AND s.parent_email=? AND s.is_active=1 ORDER BY s.first_name",
            (school_id, student["parent_email"]),
        ).fetchall()
    parent_account = _find_parent_account(conn, school_id, student)
    can_manage = session["role"] in ("admin", "sub_admin")
    conn.close()
    return render_template(
        "parent_profile.html", student=student, siblings=siblings, student_full_name=student_full_name,
        parent_account=parent_account, can_manage=can_manage,
    )


def _find_parent_account(conn, school_id, student):
    """The parents row for this guardian, if an account has been created —
    matched the same way parent_profile() groups siblings: by phone, falling
    back to email."""
    if student["parent_phone"]:
        return conn.execute(
            "SELECT * FROM parents WHERE school_id=? AND phone=?", (school_id, student["parent_phone"])
        ).fetchone()
    if student["parent_email"]:
        return conn.execute(
            "SELECT * FROM parents WHERE school_id=? AND email=?", (school_id, student["parent_email"])
        ).fetchone()
    return None


@app.route("/students/<int:student_id>/parent/set_login", methods=["POST"])
@login_required("admin", "sub_admin")
def set_parent_login(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    if not student["parent_phone"] and not student["parent_email"]:
        conn.close()
        flash("Add a parent/guardian phone or email to this student before creating a login.", "error")
        return redirect(url_for("student_profile", student_id=student_id))

    school_id = current_school_id()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username:
        conn.close()
        flash("Username is required.", "error")
        return redirect(url_for("parent_profile", student_id=student_id))
    if password and len(password) < 6:
        conn.close()
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("parent_profile", student_id=student_id))

    account = _find_parent_account(conn, school_id, student)
    try:
        if account:
            conn.execute(
                "UPDATE parents SET name=?, relationship=?, phone=?, email=?, address=?, username=? WHERE id=?",
                (student["parent_name"] or account["name"], student["parent_relationship"], student["parent_phone"],
                 student["parent_email"], student["parent_address"], username, account["id"]),
            )
            parent_id = account["id"]
            if password:
                conn.execute("UPDATE parents SET password_hash=? WHERE id=?", (generate_password_hash(password), parent_id))
        else:
            cur = conn.execute(
                "INSERT INTO parents (school_id, name, relationship, phone, email, address, username, password_hash) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (school_id, student["parent_name"] or "Parent/Guardian", student["parent_relationship"],
                 student["parent_phone"], student["parent_email"], student["parent_address"], username,
                 generate_password_hash(password) if password else None),
            )
            parent_id = cur.lastrowid
            if not password:
                conn.close()
                flash("Set a password the first time you create this login.", "error")
                return redirect(url_for("parent_profile", student_id=student_id))

        # Link every currently-matching sibling (same lookup parent_profile()
        # itself uses) so one login covers all of this guardian's children —
        # re-run on every save so a newly registered sibling gets picked up.
        if student["parent_phone"]:
            siblings = conn.execute(
                "SELECT s.id FROM students s JOIN classes c ON c.id=s.class_id "
                "WHERE c.school_id=? AND s.parent_phone=? AND s.is_active=1", (school_id, student["parent_phone"])
            ).fetchall()
        else:
            siblings = conn.execute(
                "SELECT s.id FROM students s JOIN classes c ON c.id=s.class_id "
                "WHERE c.school_id=? AND s.parent_email=? AND s.is_active=1", (school_id, student["parent_email"])
            ).fetchall()
        for s in siblings:
            conn.execute("INSERT OR IGNORE INTO parent_students (parent_id, student_id) VALUES (?,?)", (parent_id, s["id"]))
        conn.commit()
        flash("Parent login saved.", "success")
    except Exception:
        conn.rollback()
        flash("That username is already taken by another parent account.", "error")
    conn.close()
    return redirect(url_for("parent_profile", student_id=student_id))


@app.route("/students/<int:student_id>/parent/remove_login", methods=["POST"])
@login_required("admin", "sub_admin")
def remove_parent_login(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    account = _find_parent_account(conn, current_school_id(), student)
    if account:
        conn.execute("DELETE FROM parent_students WHERE parent_id=?", (account["id"],))
        conn.execute("DELETE FROM parents WHERE id=?", (account["id"],))
        conn.commit()
        flash("Parent login removed.", "success")
    conn.close()
    return redirect(url_for("parent_profile", student_id=student_id))


@app.route("/admin/parents")
@login_required("admin", "sub_admin")
def admin_parents():
    conn = get_db()
    school_id = current_school_id()
    rows = conn.execute(
        "SELECT s.id, s.parent_name, s.parent_phone, s.parent_email, s.parent_relationship "
        "FROM students s JOIN classes c ON c.id=s.class_id "
        "WHERE c.school_id=? AND s.is_active=1 AND (s.parent_phone IS NOT NULL OR s.parent_email IS NOT NULL) "
        "ORDER BY s.parent_name", (school_id,)
    ).fetchall()
    has_login = set()
    for r in conn.execute("SELECT phone, email FROM parents WHERE school_id=? AND username IS NOT NULL", (school_id,)).fetchall():
        has_login.add(r["phone"] or r["email"])
    conn.close()
    # Group by the same key parent_profile() uses (phone, falling back to email),
    # keeping only the first student id seen for each guardian as the entry point.
    seen = {}
    guardians = []
    for r in rows:
        key = r["parent_phone"] or r["parent_email"]
        if key in seen:
            continue
        seen[key] = True
        row = dict(r)
        row["has_login"] = key in has_login
        guardians.append(row)
    return render_template("admin_parents.html", guardians=guardians)



@app.route("/students/<int:student_id>/profile")
@login_required()
def student_profile(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    if session["role"] not in ("admin", "sub_admin") and student["class_id"] not in form_teacher_class_ids(conn, session["user_id"]):
        conn.close()
        flash("You don't have access to view this student's profile.", "error")
        return redirect(url_for("dashboard"))
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (student["class_id"],)).fetchone()
    enrollment_history = conn.execute(
        "SELECT e.*, s.name as session_name, c.name as class_name FROM enrollments e "
        "JOIN sessions s ON s.id=e.session_id JOIN classes c ON c.id=e.class_id "
        "WHERE e.student_id=? ORDER BY s.id", (student_id,)
    ).fetchall()
    conn.close()
    return render_template(
        "student_profile.html", student=student, class_row=class_row,
        student_full_name=student_full_name, enrollment_history=enrollment_history,
    )


def _can_manage_student(conn, student):
    return session["role"] in ("admin", "sub_admin") or student["class_id"] in form_teacher_class_ids(conn, session["user_id"])


@app.route("/students/<int:student_id>/photo")
@login_required()
def student_photo(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student or not _can_manage_student(conn, student):
        conn.close()
        return "", 404
    filename = student["photo_filename"]
    conn.close()
    if not filename:
        return "", 404
    return send_from_directory(STUDENT_PHOTOS_DIR, filename)


@app.route("/students/<int:student_id>/photo/upload", methods=["POST"])
@login_required()
def upload_student_photo(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student or not _can_manage_student(conn, student):
        conn.close()
        flash("You don't have access to manage this student's profile.", "error")
        return redirect(url_for("dashboard"))
    file = request.files.get("photo")
    if not file or not file.filename:
        conn.close()
        flash("Please choose an image file to upload.", "error")
        return redirect(url_for("student_profile", student_id=student_id))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        conn.close()
        flash("Passport photo must be a PNG, JPG, or GIF image.", "error")
        return redirect(url_for("student_profile", student_id=student_id))
    if student["photo_filename"]:
        old_path = os.path.join(STUDENT_PHOTOS_DIR, student["photo_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
    new_filename = f"student_{student_id}.{ext}"
    os.makedirs(STUDENT_PHOTOS_DIR, exist_ok=True)
    file.save(os.path.join(STUDENT_PHOTOS_DIR, new_filename))
    conn.execute("UPDATE students SET photo_filename=? WHERE id=?", (new_filename, student_id))
    conn.commit()
    conn.close()
    flash("Passport photo updated.", "success")
    return redirect(url_for("student_profile", student_id=student_id))


@app.route("/students/<int:student_id>/photo/remove", methods=["POST"])
@login_required()
def remove_student_photo(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student or not _can_manage_student(conn, student):
        conn.close()
        flash("You don't have access to manage this student's profile.", "error")
        return redirect(url_for("dashboard"))
    if student["photo_filename"]:
        old_path = os.path.join(STUDENT_PHOTOS_DIR, student["photo_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
        conn.execute("UPDATE students SET photo_filename=NULL WHERE id=?", (student_id,))
        conn.commit()
        flash("Passport photo removed.", "success")
    conn.close()
    return redirect(url_for("student_profile", student_id=student_id))


@app.route("/students/<int:student_id>/set_login", methods=["POST"])
@login_required()
def set_student_login(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student or not _can_manage_student(conn, student):
        conn.close()
        flash("You don't have access to manage this student's login.", "error")
        return redirect(url_for("dashboard"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username:
        conn.close()
        flash("Username is required.", "error")
        return redirect(url_for("student_profile", student_id=student_id))
    if password and len(password) < 6:
        conn.close()
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("student_profile", student_id=student_id))
    try:
        if password:
            conn.execute(
                "UPDATE students SET username=?, password_hash=? WHERE id=?",
                (username, generate_password_hash(password), student_id),
            )
        else:
            conn.execute("UPDATE students SET username=? WHERE id=?", (username, student_id))
        conn.commit()
        flash("Student login saved.", "success")
    except Exception:
        flash("That username is already taken by another student.", "error")
    conn.close()
    return redirect(url_for("student_profile", student_id=student_id))


@app.route("/students/<int:student_id>/remove_login", methods=["POST"])
@login_required()
def remove_student_login(student_id):
    conn = get_db()
    student = student_in_school(conn, student_id)
    if not student or not _can_manage_student(conn, student):
        conn.close()
        flash("You don't have access to manage this student's login.", "error")
        return redirect(url_for("dashboard"))
    conn.execute("UPDATE students SET username=NULL, password_hash=NULL WHERE id=?", (student_id,))
    conn.commit()
    conn.close()
    flash("Student login removed.", "success")
    return redirect(url_for("student_profile", student_id=student_id))


@app.route("/admin/students/csv_template")
@login_required("admin", "sub_admin")
def students_csv_template():
    content = (
        "admission_no,first_name,last_name,other_names,gender,class_name,date_of_birth,religion,parent_name,parent_address,parent_email,parent_phone,parent_relationship\n"
        "010,Fatima,Bello,Amina,F,JSS1A,2012-05-14,Christian,Mr Bello,12 Ahmadu Bello Way,parent@example.com,08012345678,Father\n"
    )
    buf = io.BytesIO(content.encode("utf-8"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="students_template.csv")


@app.route("/admin/students/bulk_upload", methods=["POST"])
@login_required("admin", "sub_admin")
def students_bulk_upload():
    file = request.files.get("csv_file")
    if not file or file.filename == "":
        flash("Please choose a CSV file to upload.", "error")
        return redirect(url_for("admin_students"))

    conn = get_db()
    school_id = current_school_id()
    classes_by_name = {
        row["name"].strip().lower(): row["id"]
        for row in conn.execute("SELECT * FROM classes WHERE school_id=?", (school_id,)).fetchall()
    }

    try:
        text = file.read().decode("utf-8-sig")
    except Exception:
        conn.close()
        flash("Could not read that file — please upload a plain CSV file.", "error")
        return redirect(url_for("admin_students"))

    reader = csv_module.DictReader(io.StringIO(text))
    required_cols = {"admission_no", "first_name", "last_name", "class_name"}
    if not required_cols.issubset(set(c.strip() for c in (reader.fieldnames or []))):
        conn.close()
        flash(f"CSV must at least have these columns: {', '.join(sorted(required_cols))}. Download the template for reference.", "error")
        return redirect(url_for("admin_students"))

    added, skipped = 0, []
    for i, row in enumerate(reader, start=2):
        adm = (row.get("admission_no") or "").strip()
        fn = (row.get("first_name") or "").strip()
        ln = (row.get("last_name") or "").strip()
        other_names = (row.get("other_names") or "").strip() or None
        gender = (row.get("gender") or "").strip().upper()[:1]
        class_name = (row.get("class_name") or "").strip().lower()
        dob = (row.get("date_of_birth") or "").strip() or None
        religion = (row.get("religion") or "").strip() or None
        parent_name = (row.get("parent_name") or "").strip() or None
        parent_address = (row.get("parent_address") or "").strip() or None
        parent_email = (row.get("parent_email") or "").strip() or None
        parent_phone = (row.get("parent_phone") or "").strip() or None
        parent_relationship = (row.get("parent_relationship") or "").strip() or None

        if not (adm and fn and ln and class_name):
            skipped.append(f"Row {i}: missing required field(s)")
            continue
        class_id = classes_by_name.get(class_name)
        if not class_id:
            skipped.append(f"Row {i}: class '{row.get('class_name')}' doesn't exist — create it first")
            continue
        try:
            cur = conn.execute(
                "INSERT INTO students (admission_no, first_name, last_name, other_names, gender, "
                "class_id, date_of_birth, religion, parent_name, parent_address, parent_email, parent_phone, parent_relationship) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (adm, fn, ln, other_names, gender if gender in ("M", "F") else None,
                 class_id, dob, religion, parent_name, parent_address, parent_email, parent_phone, parent_relationship),
            )
            upsert_enrollment(conn, cur.lastrowid, class_id)
            added += 1
        except Exception:
            skipped.append(f"Row {i}: Admission No./Register No. '{adm}' is already used by another student in class '{row.get('class_name')}'")

    conn.commit()
    conn.close()

    if added:
        flash(f"Imported {added} student(s) successfully.", "success")
    if skipped:
        preview = "; ".join(skipped[:8]) + (f" (+{len(skipped)-8} more)" if len(skipped) > 8 else "")
        flash(f"Skipped {len(skipped)} row(s): {preview}", "error")
    if not added and not skipped:
        flash("No rows found in that file.", "error")

    return redirect(url_for("admin_students"))


@app.route("/admin/teachers", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_teachers():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        name = request.form["name"].strip()
        username = request.form["username"].strip()
        email = request.form.get("email", "").strip() or None
        phone = request.form.get("phone", "").strip() or None
        password = request.form["password"]
        position = request.form.get("position") or None
        if position and position not in dict(POSITION_CHOICES):
            position = None
        offline_token = request.form.get("offline_token")
        existing_id = offline_sync_existing_id(conn, offline_token)
        if existing_id:
            if is_offline_sync_request():
                conn.close()
                return {"ok": True, "id": existing_id}
            flash(f"Teacher '{name}' added.", "success")
        elif email and conn.execute("SELECT 1 FROM users WHERE LOWER(email)=LOWER(?)", (email,)).fetchone():
            if is_offline_sync_request():
                conn.close()
                return {"ok": False, "error": "That email is already in use by another account."}, 409
            flash("That email is already in use by another account.", "error")
        elif phone and conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            if is_offline_sync_request():
                conn.close()
                return {"ok": False, "error": "That phone number is already in use by another account."}, 409
            flash("That phone number is already in use by another account.", "error")
        else:
            try:
                cur = conn.execute(
                    "INSERT INTO users (school_id, name, username, email, phone, password_hash, role, position) VALUES (?,?,?,?,?,?, 'teacher', ?)",
                    (school_id, name, username, email, phone, generate_password_hash(password), position),
                )
                conn.commit()
                offline_sync_remember(conn, offline_token, "teacher", cur.lastrowid)
                if is_offline_sync_request():
                    conn.close()
                    return {"ok": True, "id": cur.lastrowid}
                flash(f"Teacher '{name}' added.", "success")
            except Exception:
                if is_offline_sync_request():
                    conn.close()
                    return {"ok": False, "error": "That username is already taken."}, 409
                flash("That username is already taken.", "error")
    teachers = conn.execute("SELECT * FROM users WHERE role='teacher' AND school_id=? ORDER BY name", (school_id,)).fetchall()
    conn.close()
    return render_template("admin_teachers.html", teachers=teachers, position_choices=POSITION_CHOICES, position_labels=POSITION_LABELS)


@app.route("/admin/teachers/<int:teacher_id>/contact", methods=["POST"])
@login_required("admin", "sub_admin")
def update_teacher_contact(teacher_id):
    conn = get_db()
    if not teacher_in_school(conn, teacher_id):
        conn.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers"))
    email = request.form.get("email", "").strip() or None
    phone = request.form.get("phone", "").strip() or None
    if email and conn.execute("SELECT 1 FROM users WHERE LOWER(email)=LOWER(?) AND id!=?", (email, teacher_id)).fetchone():
        conn.close()
        flash("That email is already in use by another account.", "error")
        return redirect(url_for("admin_teachers"))
    if phone and conn.execute("SELECT 1 FROM users WHERE phone=? AND id!=?", (phone, teacher_id)).fetchone():
        conn.close()
        flash("That phone number is already in use by another account.", "error")
        return redirect(url_for("admin_teachers"))
    conn.execute("UPDATE users SET email=?, phone=? WHERE id=?", (email, phone, teacher_id))
    conn.commit()
    conn.close()
    flash("Contact info updated.", "success")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/teachers/<int:teacher_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_teacher(teacher_id):
    conn = get_db()
    if not teacher_in_school(conn, teacher_id):
        conn.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers"))
    conn.execute("UPDATE classes SET form_teacher_id=NULL WHERE form_teacher_id=?", (teacher_id,))
    conn.execute("UPDATE class_subjects SET teacher_id=NULL WHERE teacher_id=?", (teacher_id,))
    conn.execute("DELETE FROM users WHERE id=? AND role='teacher'", (teacher_id,))
    revoke_device_credentials_for_user(conn, teacher_id, reason="account deleted")
    conn.commit()
    conn.close()
    flash("Teacher removed. Any classes/subjects they were assigned to are now unassigned.", "success")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/teachers/<int:teacher_id>/set_position", methods=["POST"])
@login_required("admin", "sub_admin")
def set_teacher_position(teacher_id):
    conn = get_db()
    if not teacher_in_school(conn, teacher_id):
        conn.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers"))
    position = request.form.get("position") or None
    if position and position not in dict(POSITION_CHOICES):
        conn.close()
        flash("Not a valid position.", "error")
        return redirect(url_for("admin_teachers"))
    conn.execute("UPDATE users SET position=? WHERE id=?", (position, teacher_id))
    conn.commit()
    conn.close()
    flash("Position updated.", "success")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/teachers/<int:teacher_id>/toggle_active", methods=["POST"])
@login_required("admin", "sub_admin")
def toggle_teacher_active(teacher_id):
    conn = get_db()
    teacher = teacher_in_school(conn, teacher_id)
    if not teacher:
        conn.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers"))
    new_status = 0 if teacher["is_active"] else 1
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, teacher_id))
    conn.commit()
    if not new_status:
        # Cut off every device this person enrolled for offline use, too.
        revoke_device_credentials_for_user(conn, teacher_id, "account deactivated")
    conn.close()
    flash(
        "Account deactivated. This also stops every device they enrolled for offline use from syncing or unlocking."
        if not new_status else "Account reactivated. They will need to log in online once on each device to renew offline access.",
        "success",
    )
    return redirect(url_for("admin_teachers"))


@app.route("/admin/teachers/<int:teacher_id>/reset_password", methods=["POST"])
@login_required("admin", "sub_admin")
def admin_reset_teacher_password(teacher_id):
    conn = get_db()
    teacher = teacher_in_school(conn, teacher_id)
    if not teacher:
        conn.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("admin_teachers"))
    new_password = secrets.token_urlsafe(6)
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), teacher_id))
    conn.commit()
    # A reset means the old password may be known to someone else, and a device
    # that was set up with it still opens with it. Cut those devices off; the
    # person logs in online with the new password and each device renews itself.
    revoke_device_credentials_for_user(conn, teacher_id, "password reset by admin")
    conn.close()
    flash(
        f"Password reset for {teacher['name']} (username: {teacher['username']}). "
        f"New temporary password: {new_password} — share this with them securely; "
        f"they can change it themselves afterward from Change Password.",
        "success",
    )
    return redirect(url_for("admin_teachers"))


# ---------- sub-admin management (main admin only) ----------

@app.route("/admin/subadmins", methods=["GET", "POST"])
@login_required("admin")
def admin_subadmins():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        name = request.form["name"].strip()
        username = request.form["username"].strip()
        password = request.form["password"]
        try:
            conn.execute(
                "INSERT INTO users (school_id, name, username, password_hash, role) VALUES (?,?,?,?, 'sub_admin')",
                (school_id, name, username, generate_password_hash(password)),
            )
            conn.commit()
            flash(f"Sub-Admin '{name}' added.", "success")
        except Exception:
            flash("That username is already taken.", "error")
    subadmins = conn.execute(
        "SELECT * FROM users WHERE role='sub_admin' AND school_id=? ORDER BY name", (school_id,)
    ).fetchall()
    conn.close()
    return render_template("admin_subadmins.html", subadmins=subadmins)


@app.route("/admin/subadmins/<int:user_id>/delete", methods=["POST"])
@login_required("admin")
def delete_subadmin(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=? AND role='sub_admin' AND school_id=?", (user_id, current_school_id()))
    conn.commit()
    conn.close()
    flash("Sub-Admin removed.", "success")
    return redirect(url_for("admin_subadmins"))


@app.route("/admin/subadmins/<int:user_id>/reset_password", methods=["POST"])
@login_required("admin")
def reset_subadmin_password(user_id):
    conn = get_db()
    sub = conn.execute(
        "SELECT * FROM users WHERE id=? AND role='sub_admin' AND school_id=?", (user_id, current_school_id())
    ).fetchone()
    if not sub:
        conn.close()
        flash("Sub-Admin not found.", "error")
        return redirect(url_for("admin_subadmins"))
    new_password = secrets.token_urlsafe(6)
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()
    flash(
        f"Password reset for {sub['name']} (username: {sub['username']}). "
        f"New temporary password: {new_password} — share this with them securely.",
        "success",
    )
    return redirect(url_for("admin_subadmins"))


@app.route("/admin/grading", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_grading():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        ca1 = float(request.form["ca1_max"])
        ca2 = float(request.form["ca2_max"])
        ca3 = float(request.form.get("ca3_max") or 0)   # 0 = CA3 not used
        exam = float(request.form["exam_max"])
        problems = grading_problems(conn, school_id, ca1, ca2, ca3, exam)
        if problems:
            flash(" ".join(problems), "error")
        else:
            conn.execute("UPDATE grading_config SET ca1_max=?, ca2_max=?, ca3_max=?, exam_max=? WHERE school_id=?",
                         (ca1, ca2, ca3, exam, school_id))
            conn.commit()
            if abs(ca1 + ca2 + ca3 + exam - 100) > 0.001:
                flash(f"Grading weights updated — note the maximums add up to {ca1 + ca2 + ca3 + exam:g}, not 100.", "success")
            else:
                flash("Grading weights updated.", "success")
    config = get_grading_config(conn)
    scale = conn.execute("SELECT * FROM grade_scale WHERE school_id=? ORDER BY min_score DESC", (school_id,)).fetchall()
    conn.close()
    return render_template("admin_grading.html", config=config, scale=scale)


@app.route("/admin/grading/scale/add", methods=["POST"])
@login_required("admin", "sub_admin")
def add_grade_scale():
    conn = get_db()
    try:
        lo, hi = float(request.form["min_score"]), float(request.form["max_score"])
        problems = grade_band_problems(conn, current_school_id(), request.form["grade"], lo, hi)
        if problems:
            flash(" ".join(problems), "error")
            conn.close()
            return redirect(url_for("admin_grading"))
        conn.execute(
            "INSERT INTO grade_scale (school_id, grade, min_score, max_score, remark) VALUES (?,?,?,?,?)",
            (current_school_id(), request.form["grade"].strip(), lo, hi, request.form.get("remark", "").strip()),
        )
        conn.commit()
        flash("Grade band added.", "success")
    except Exception:
        flash("Couldn't add that grade band — check the values entered.", "error")
    conn.close()
    return redirect(url_for("admin_grading"))


@app.route("/admin/grading/scale/<int:scale_id>/edit", methods=["POST"])
@login_required("admin", "sub_admin")
def edit_grade_scale(scale_id):
    conn = get_db()
    try:
        lo, hi = float(request.form["min_score"]), float(request.form["max_score"])
        problems = grade_band_problems(conn, current_school_id(), request.form["grade"], lo, hi, exclude_id=scale_id)
        if problems:
            flash(" ".join(problems), "error")
            conn.close()
            return redirect(url_for("admin_grading"))
        conn.execute(
            "UPDATE grade_scale SET grade=?, min_score=?, max_score=?, remark=? WHERE id=? AND school_id=?",
            (request.form["grade"].strip(), lo, hi, request.form.get("remark", "").strip(), scale_id, current_school_id()),
        )
        conn.commit()
        flash("Grade band updated.", "success")
    except Exception:
        flash("Couldn't update that grade band — check the values entered.", "error")
    conn.close()
    return redirect(url_for("admin_grading"))


@app.route("/admin/grading/scale/<int:scale_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_grade_scale(scale_id):
    conn = get_db()
    conn.execute("DELETE FROM grade_scale WHERE id=? AND school_id=?", (scale_id, current_school_id()))
    conn.commit()
    conn.close()
    flash("Grade band deleted.", "success")
    return redirect(url_for("admin_grading"))


@app.route("/admin/terms", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_terms():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "new_session":
            name = request.form["session_name"].strip()
            try:
                conn.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?, 0)", (school_id, name))
                conn.commit()
                flash("Session created.", "success")
            except Exception:
                flash("That session name already exists.", "error")
        elif action == "new_term":
            name = request.form["term_name"]
            session_id = request.form["session_id"]
            owner = conn.execute("SELECT * FROM sessions WHERE id=? AND school_id=?", (session_id, school_id)).fetchone()
            if owner:
                conn.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,0)", (name, session_id))
                conn.commit()
                flash("Term created.", "success")
        elif action == "activate_session":
            sid = request.form["session_id"]
            owner = conn.execute("SELECT * FROM sessions WHERE id=? AND school_id=?", (sid, school_id)).fetchone()
            if owner:
                conn.execute("UPDATE sessions SET is_active=0 WHERE school_id=?", (school_id,))
                conn.execute("UPDATE sessions SET is_active=1 WHERE id=?", (sid,))
                conn.commit()
                flash("Active session updated.", "success")
        elif action == "activate_term":
            tid = request.form["term_id"]
            owner = conn.execute(
                "SELECT terms.* FROM terms JOIN sessions ON sessions.id=terms.session_id "
                "WHERE terms.id=? AND sessions.school_id=?", (tid, school_id)
            ).fetchone()
            if owner:
                conn.execute(
                    "UPDATE terms SET is_active=0 WHERE session_id IN (SELECT id FROM sessions WHERE school_id=?)",
                    (school_id,),
                )
                conn.execute("UPDATE terms SET is_active=1 WHERE id=?", (tid,))
                conn.commit()
                flash("Active term updated.", "success")
        elif action == "publish_term":
            tid = request.form["term_id"]
            owner = conn.execute(
                "SELECT terms.* FROM terms JOIN sessions ON sessions.id=terms.session_id "
                "WHERE terms.id=? AND sessions.school_id=?", (tid, school_id)
            ).fetchone()
            if owner:
                conn.execute("UPDATE terms SET is_published=1 WHERE id=?", (tid,))
                conn.commit()
                flash("Term published — results can now be emailed to parents.", "success")
        elif action == "unpublish_term":
            tid = request.form["term_id"]
            owner = conn.execute(
                "SELECT terms.* FROM terms JOIN sessions ON sessions.id=terms.session_id "
                "WHERE terms.id=? AND sessions.school_id=?", (tid, school_id)
            ).fetchone()
            if owner:
                conn.execute("UPDATE terms SET is_published=0 WHERE id=?", (tid,))
                conn.commit()
                flash("Term unpublished — emailing results is now paused for this term.", "success")
        elif action == "toggle_cumulative":
            enabled = 1 if request.form.get("cumulative_enabled") else 0
            conn.execute("UPDATE schools SET cumulative_enabled=? WHERE id=?", (enabled, school_id))
            conn.commit()
            flash(
                "Cumulative/Annual results are now " + ("enabled." if enabled else "disabled — terms operate independently again."),
                "success",
            )
    sessions_ = conn.execute("SELECT * FROM sessions WHERE school_id=? ORDER BY id DESC", (school_id,)).fetchall()
    terms = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id=terms.session_id WHERE sessions.school_id=? ORDER BY terms.id DESC", (school_id,)
    ).fetchall()
    school = get_school(conn, school_id)
    conn.close()
    return render_template("admin_terms.html", sessions=sessions_, terms=terms, school=school)


@app.route("/admin/reset_demo_data", methods=["POST"])
@login_required("admin", "sub_admin")
def reset_demo_data():
    if request.form.get("confirm_text", "").strip().upper() != "RESET":
        flash('You must type RESET exactly to confirm clearing demo data.', "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    school_id = current_school_id()
    class_ids = [r["id"] for r in conn.execute("SELECT id FROM classes WHERE school_id=?", (school_id,)).fetchall()]
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        student_ids = [r["id"] for r in conn.execute(
            f"SELECT id FROM students WHERE class_id IN ({placeholders})", class_ids
        ).fetchall()]
        if student_ids:
            sp = ",".join("?" * len(student_ids))
            conn.execute(f"DELETE FROM student_skill_ratings WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM student_term_info WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM score_history WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM scores WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM enrollments WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM students WHERE id IN ({sp})", student_ids)
        conn.execute(f"DELETE FROM class_subjects WHERE class_id IN ({placeholders})", class_ids)
        conn.execute(f"DELETE FROM timetable_entries WHERE class_id IN ({placeholders})", class_ids)
        conn.execute(f"DELETE FROM classes WHERE id IN ({placeholders})", class_ids)
    conn.execute("DELETE FROM subjects WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM users WHERE role='teacher' AND school_id=?", (school_id,))
    log_audit(conn, session["role"], session.get("name"), "clear_demo_data",
              details="Cleared demo/sample classes, subjects, students, and teachers", school_id=school_id)
    conn.commit()
    conn.close()
    flash("Demo data cleared. Sessions/terms, your admin login, the grading setup, and skill traits were kept. Start adding your real classes, subjects, teachers and students.", "success")
    return redirect(url_for("dashboard"))


# ---------- student promotion ----------

@app.route("/admin/promote", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def admin_promote():
    conn = get_db()
    school_id = current_school_id()
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()

    from_class_id = request.values.get("from_class_id", type=int)
    students = []
    if from_class_id and class_in_school(conn, from_class_id):
        students = conn.execute(
            "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY admission_no, last_name",
            (from_class_id,),
        ).fetchall()

    if request.method == "POST":
        to_class_name = request.form.get("to_class_name", "").strip()
        to_class_id = request.form.get("to_class_id") or None
        student_ids = request.form.getlist("student_ids")

        if not class_in_school(conn, from_class_id):
            flash("Source class not found.", "error")
            return redirect(url_for("admin_promote"))

        if to_class_name:
            existing = conn.execute(
                "SELECT id FROM classes WHERE school_id=? AND name=?", (school_id, to_class_name)
            ).fetchone()
            if existing:
                to_class_id = existing["id"]
            else:
                cur = conn.execute("INSERT INTO classes (school_id, name) VALUES (?,?)", (school_id, to_class_name))
                to_class_id = cur.lastrowid
                conn.commit()
        elif to_class_id and not class_in_school(conn, to_class_id):
            flash("Destination class not found.", "error")
            return redirect(url_for("admin_promote", from_class_id=from_class_id))

        if not to_class_id:
            flash("Please choose or name a destination class.", "error")
            return redirect(url_for("admin_promote", from_class_id=from_class_id))
        if int(to_class_id) == from_class_id:
            flash("Destination class must be different from the source class.", "error")
            return redirect(url_for("admin_promote", from_class_id=from_class_id))
        if not student_ids:
            flash("Select at least one student to promote.", "error")
            return redirect(url_for("admin_promote", from_class_id=from_class_id))

        existing_admissions = {
            r["admission_no"]
            for r in conn.execute("SELECT admission_no FROM students WHERE class_id=?", (to_class_id,)).fetchall()
        }
        promoted, conflicts = 0, []
        for sid in student_ids:
            st = conn.execute("SELECT * FROM students WHERE id=? AND class_id=?", (sid, from_class_id)).fetchone()
            if not st:
                continue
            if st["admission_no"] in existing_admissions:
                conflicts.append(f"{student_full_name(st)} (Admission No./Register No. '{st['admission_no']}' already used in destination class)")
                continue
            conn.execute("UPDATE students SET class_id=? WHERE id=?", (to_class_id, sid))
            upsert_enrollment(conn, sid, to_class_id)
            existing_admissions.add(st["admission_no"])
            promoted += 1
        conn.commit()
        conn.close()

        if promoted:
            flash(f"Promoted {promoted} student(s) to their new class.", "success")
        if conflicts:
            preview = "; ".join(conflicts[:8]) + (f" (+{len(conflicts)-8} more)" if len(conflicts) > 8 else "")
            flash(f"Skipped {len(conflicts)} student(s) due to Admission No./Register No. conflicts in the destination class — resolve manually: {preview}", "error")
        return redirect(url_for("admin_promote"))

    conn.close()
    return render_template(
        "admin_promote.html", classes=classes, from_class_id=from_class_id, students=students,
        student_full_name=student_full_name,
    )


# ---------- timetable ----------

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _timetable_can_edit():
    return session.get("role") in ("admin", "sub_admin")


def _timetable_can_view_class(conn, class_id):
    if session.get("role") in ("admin", "sub_admin") or session.get("position") in FULL_ACCESS_POSITIONS:
        return True
    if class_id in form_teacher_class_ids(conn, session["user_id"]):
        return True
    row = conn.execute(
        "SELECT 1 FROM class_subjects WHERE class_id=? AND teacher_id=?",
        (class_id, session["user_id"]),
    ).fetchone()
    return bool(row)


def _timetable_can_view_teacher(teacher_id):
    if session.get("role") in ("admin", "sub_admin") or session.get("position") in FULL_ACCESS_POSITIONS:
        return True
    return teacher_id == session.get("user_id")


@app.route("/timetable")
@login_required()
def timetable_hub():
    conn = get_db()
    school_id = current_school_id()
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    teachers = conn.execute(
        "SELECT * FROM users WHERE school_id=? AND role='teacher' AND is_active=1 ORDER BY name", (school_id,)
    ).fetchall()
    conn.close()
    return render_template("timetable_hub.html", classes=classes, teachers=teachers,
                            can_edit=_timetable_can_edit())


@app.route("/timetable/periods", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def timetable_periods():
    conn = get_db()
    school_id = current_school_id()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            start_time = request.form.get("start_time", "").strip() or None
            end_time = request.form.get("end_time", "").strip() or None
            is_break = 1 if request.form.get("is_break") else 0
            if name:
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) FROM timetable_periods WHERE school_id=?", (school_id,)
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO timetable_periods (school_id, name, start_time, end_time, sort_order, is_break) "
                    "VALUES (?,?,?,?,?,?)",
                    (school_id, name, start_time, end_time, max_order + 1, is_break),
                )
                conn.commit()
                flash(f"Period '{name}' added.", "success")
            else:
                flash("Period name is required.", "error")
        elif action == "delete":
            period_id = request.form.get("period_id")
            row = conn.execute(
                "SELECT id FROM timetable_periods WHERE id=? AND school_id=?", (period_id, school_id)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM timetable_entries WHERE period_id=?", (period_id,))
                conn.execute("DELETE FROM timetable_periods WHERE id=?", (period_id,))
                conn.commit()
                flash("Period removed (and any timetable entries using it).", "success")
        conn.close()
        return redirect(url_for("timetable_periods"))

    periods = conn.execute(
        "SELECT * FROM timetable_periods WHERE school_id=? ORDER BY sort_order, id", (school_id,)
    ).fetchall()
    conn.close()
    return render_template("timetable_periods.html", periods=periods)


@app.route("/timetable/class/<int:class_id>", methods=["GET", "POST"])
@login_required()
def timetable_class(class_id):
    conn = get_db()
    school_id = current_school_id()
    class_row = conn.execute("SELECT * FROM classes WHERE id=? AND school_id=?", (class_id, school_id)).fetchone()
    if not class_row:
        conn.close()
        flash("Class not found.", "error")
        return redirect(url_for("timetable_hub"))
    if not _timetable_can_view_class(conn, class_id):
        conn.close()
        flash("You don't have access to that class's timetable.", "error")
        return redirect(url_for("timetable_hub"))

    can_edit = _timetable_can_edit()
    if request.method == "POST":
        if not can_edit:
            conn.close()
            flash("You don't have permission to edit the timetable.", "error")
            return redirect(url_for("timetable_class", class_id=class_id))
        period_rows = conn.execute(
            "SELECT id FROM timetable_periods WHERE school_id=? AND is_break=0", (school_id,)
        ).fetchall()
        for day in range(len(DAY_NAMES)):
            for prow in period_rows:
                period_id = prow["id"]
                key = f"cell_{day}_{period_id}"
                subject_id = request.form.get(f"{key}_subject") or None
                teacher_id = request.form.get(f"{key}_teacher") or None
                room = request.form.get(f"{key}_room", "").strip() or None
                existing = conn.execute(
                    "SELECT id FROM timetable_entries WHERE class_id=? AND day_of_week=? AND period_id=?",
                    (class_id, day, period_id),
                ).fetchone()
                if not subject_id and not teacher_id and not room:
                    if existing:
                        conn.execute("DELETE FROM timetable_entries WHERE id=?", (existing["id"],))
                    continue
                if existing:
                    conn.execute(
                        "UPDATE timetable_entries SET subject_id=?, teacher_id=?, room=? WHERE id=?",
                        (subject_id, teacher_id, room, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO timetable_entries "
                        "(school_id, class_id, day_of_week, period_id, subject_id, teacher_id, room) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (school_id, class_id, day, period_id, subject_id, teacher_id, room),
                    )
        conn.commit()
        flash("Timetable saved.", "success")
        return redirect(url_for("timetable_class", class_id=class_id))

    periods = conn.execute(
        "SELECT * FROM timetable_periods WHERE school_id=? ORDER BY sort_order, id", (school_id,)
    ).fetchall()
    subjects = conn.execute("SELECT * FROM subjects WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    teachers = conn.execute(
        "SELECT * FROM users WHERE school_id=? AND role='teacher' AND is_active=1 ORDER BY name", (school_id,)
    ).fetchall()
    entries = conn.execute(
        "SELECT te.*, s.name as subject_name, u.name as teacher_name FROM timetable_entries te "
        "LEFT JOIN subjects s ON s.id=te.subject_id LEFT JOIN users u ON u.id=te.teacher_id "
        "WHERE te.class_id=?", (class_id,)
    ).fetchall()
    grid = {(e["day_of_week"], e["period_id"]): e for e in entries}
    conn.close()
    return render_template(
        "timetable_class.html", class_row=class_row, periods=periods, subjects=subjects,
        teachers=teachers, grid=grid, days=list(enumerate(DAY_NAMES)), can_edit=can_edit,
    )


@app.route("/timetable/class/<int:class_id>/auto-generate", methods=["POST"])
@login_required("admin", "sub_admin")
def timetable_auto_generate(class_id):
    """Fills this class's timetable from its subject allocation (class_subjects):
    each subject/teacher pair gets an even share of the week's teaching periods,
    never on the same day twice, and never in a period where that teacher is
    already teaching a different class — checked across the whole school, not
    just this class, so auto-generating one class can't double-book a teacher
    who is already placed on another class's timetable."""
    conn = get_db()
    school_id = current_school_id()
    class_row = conn.execute("SELECT * FROM classes WHERE id=? AND school_id=?", (class_id, school_id)).fetchone()
    if not class_row:
        conn.close()
        flash("Class not found.", "error")
        return redirect(url_for("timetable_hub"))

    assignments = conn.execute(
        "SELECT subject_id, teacher_id FROM class_subjects WHERE class_id=? AND teacher_id IS NOT NULL",
        (class_id,)
    ).fetchall()
    if not assignments:
        conn.close()
        flash("Assign subjects with teachers to this class first (Setup → Assign Subjects), then auto-generate.", "error")
        return redirect(url_for("timetable_class", class_id=class_id))

    period_rows = conn.execute(
        "SELECT id FROM timetable_periods WHERE school_id=? AND is_break=0 ORDER BY sort_order, id", (school_id,)
    ).fetchall()
    if not period_rows:
        conn.close()
        flash("Set up periods first, under Timetable → Manage Periods.", "error")
        return redirect(url_for("timetable_periods"))
    period_ids = [p["id"] for p in period_rows]
    days = list(range(len(DAY_NAMES)))

    if request.form.get("clear_existing") == "1":
        conn.execute("DELETE FROM timetable_entries WHERE class_id=?", (class_id,))

    # Every OTHER class's booked (teacher, day, period) slots — this class's
    # own current slots are handled separately below via `filled`.
    busy = {
        (row["teacher_id"], row["day_of_week"], row["period_id"])
        for row in conn.execute(
            "SELECT teacher_id, day_of_week, period_id FROM timetable_entries "
            "WHERE school_id=? AND teacher_id IS NOT NULL AND class_id != ?",
            (school_id, class_id),
        )
    }
    filled = {}
    day_has_subject = {}
    for row in conn.execute(
        "SELECT day_of_week, period_id, subject_id FROM timetable_entries WHERE class_id=?", (class_id,)
    ):
        filled[(row["day_of_week"], row["period_id"])] = row["subject_id"]
        day_has_subject[(row["day_of_week"], row["subject_id"])] = True

    empty_slots = [(d, p) for d in days for p in period_ids if (d, p) not in filled]
    total_slots = len(days) * len(period_ids)
    num_subjects = len(assignments)
    target_per_subject = min(6, max(1, total_slots // num_subjects)) if num_subjects else 0

    placed_count = {a["subject_id"]: 0 for a in assignments}
    assignments_list = list(assignments)
    random.shuffle(assignments_list)

    inserted = 0
    progress = True
    while progress and empty_slots:
        progress = False
        for a in assignments_list:
            subj_id, teacher_id = a["subject_id"], a["teacher_id"]
            if placed_count[subj_id] >= target_per_subject:
                continue
            chosen = None
            for slot in empty_slots:
                d, p = slot
                if day_has_subject.get((d, subj_id)):
                    continue
                if (teacher_id, d, p) in busy:
                    continue
                chosen = slot
                break
            if chosen:
                d, p = chosen
                conn.execute(
                    "INSERT INTO timetable_entries (school_id, class_id, day_of_week, period_id, subject_id, teacher_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (school_id, class_id, d, p, subj_id, teacher_id),
                )
                busy.add((teacher_id, d, p))
                day_has_subject[(d, subj_id)] = True
                placed_count[subj_id] += 1
                empty_slots.remove(chosen)
                inserted += 1
                progress = True
    conn.commit()
    conn.close()
    if inserted:
        flash(f"Auto-generated {inserted} timetable slot(s) for {class_row['name']} — review and adjust below as needed.", "success")
    else:
        flash("Couldn't place any new slots — every remaining period is either full or clashes with a teacher's other class.", "error")
    return redirect(url_for("timetable_class", class_id=class_id))


@app.route("/timetable/teacher/<int:teacher_id>")
@login_required()
def timetable_teacher(teacher_id):
    conn = get_db()
    school_id = current_school_id()
    teacher = conn.execute("SELECT * FROM users WHERE id=? AND school_id=?", (teacher_id, school_id)).fetchone()
    if not teacher:
        conn.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("timetable_hub"))
    if not _timetable_can_view_teacher(teacher_id):
        conn.close()
        flash("You don't have access to that teacher's timetable.", "error")
        return redirect(url_for("timetable_hub"))

    periods = conn.execute(
        "SELECT * FROM timetable_periods WHERE school_id=? ORDER BY sort_order, id", (school_id,)
    ).fetchall()
    entries = conn.execute(
        "SELECT te.*, s.name as subject_name, c.name as class_name FROM timetable_entries te "
        "LEFT JOIN subjects s ON s.id=te.subject_id LEFT JOIN classes c ON c.id=te.class_id "
        "WHERE te.teacher_id=?", (teacher_id,)
    ).fetchall()
    grid = {(e["day_of_week"], e["period_id"]): e for e in entries}
    conn.close()
    return render_template(
        "timetable_teacher.html", teacher=teacher, periods=periods, grid=grid, days=list(enumerate(DAY_NAMES)),
    )


@app.route("/my-class")
@login_required()
def my_class():
    conn = get_db()
    class_ids = form_teacher_class_ids(conn, session["user_id"])
    conn.close()
    if not class_ids:
        flash("You are not currently assigned as a Form Teacher for any class. Please ask your administrator to assign you.", "error")
        return redirect(url_for("dashboard"))
    if len(class_ids) == 1:
        return redirect(url_for("my_class_roster", class_id=class_ids[0]))
    conn = get_db()
    classes = conn.execute(
        f"SELECT * FROM classes WHERE id IN ({','.join('?'*len(class_ids))}) ORDER BY name", class_ids
    ).fetchall()
    conn.close()
    return render_template("my_class_picker.html", classes=classes)


@app.route("/my-class/<int:class_id>", methods=["GET", "POST"])
@login_required()
def my_class_roster(class_id):
    conn = get_db()
    class_row = class_in_school(conn, class_id)
    if not class_row:
        conn.close()
        flash("Class not found.", "error")
        return redirect(url_for("dashboard"))
    if session["role"] not in ("admin", "sub_admin") and class_id not in form_teacher_class_ids(conn, session["user_id"]):
        conn.close()
        flash("You're not the form teacher for that class.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        try:
            cur = conn.execute(
                "INSERT INTO students (admission_no, first_name, last_name, other_names, "
                "gender, class_id, date_of_birth, religion, parent_name, parent_address, parent_email, parent_phone, parent_relationship) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    request.form["admission_no"].strip(),
                    request.form["first_name"].strip(),
                    request.form["last_name"].strip(),
                    request.form.get("other_names", "").strip() or None,
                    request.form.get("gender") or None,
                    class_id,
                    request.form.get("date_of_birth", "").strip() or None,
                    request.form.get("religion", "").strip() or None,
                    request.form.get("parent_name", "").strip() or None,
                    request.form.get("parent_address", "").strip() or None,
                    request.form.get("parent_email", "").strip() or None,
                    request.form.get("parent_phone", "").strip() or None,
                    request.form.get("parent_relationship", "").strip() or None,
                ),
            )
            upsert_enrollment(conn, cur.lastrowid, class_id)
            conn.commit()
            flash("Student added to your class register.", "success")
        except Exception:
            flash("That Admission No. / Register No. is already in use in this class.", "error")

    students = conn.execute(
        "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY admission_no, last_name", (class_id,)
    ).fetchall()
    conn.close()
    return render_template(
        "my_class_roster.html", class_row=class_row, students=students, student_full_name=student_full_name
    )


def _require_own_class(conn, class_id):
    class_row = class_in_school(conn, class_id)
    if not class_row:
        return None
    if session["role"] not in ("admin", "sub_admin") and class_id not in form_teacher_class_ids(conn, session["user_id"]):
        return None
    return class_row


@app.route("/my-class/<int:class_id>/roll-call", methods=["GET", "POST"])
@login_required()
def roll_call(class_id):
    conn = get_db()
    class_row = _require_own_class(conn, class_id)
    if not class_row:
        conn.close()
        flash("You're not the form teacher for that class.", "error")
        return redirect(url_for("dashboard"))

    term = current_term(conn)
    if not term:
        conn.close()
        flash("There's no active term set up yet. Ask your admin to set one under Setup → Terms.", "error")
        return redirect(url_for("dashboard"))

    date_str = request.values.get("date", "").strip() or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        date_str = datetime.date.today().isoformat()

    students = conn.execute(
        "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY admission_no, last_name", (class_id,)
    ).fetchall()

    if request.method == "POST":
        present_count = absent_count = 0
        for s in students:
            status = "absent" if request.form.get(f"status_{s['id']}") == "absent" else "present"
            if status == "present":
                present_count += 1
            else:
                absent_count += 1
            conn.execute(
                "INSERT INTO attendance_records (student_id, class_id, term_id, date, status, recorded_by, source) "
                "VALUES (?,?,?,?,?,?,'online') "
                "ON CONFLICT(student_id, term_id, date) DO UPDATE SET "
                "status=excluded.status, recorded_by=excluded.recorded_by, recorded_at=CURRENT_TIMESTAMP, source='online'",
                (s["id"], class_id, term["id"], date_str, status, session["user_id"]),
            )
            recompute_attendance(conn, s["id"], term["id"])
        conn.commit()
        log_audit(
            conn, session["role"], session.get("name"),
            "roll_call",
            f"{class_row['name']} — {date_str}: {present_count} present, {absent_count} absent",
            school_id=current_school_id(),
        )
        flash(f"Roll call saved for {format_dmy(date_str)} — {present_count} present, {absent_count} absent.", "success")
        conn.close()
        return redirect(url_for("roll_call", class_id=class_id, date=date_str))

    existing = {
        r["student_id"]: r["status"] for r in conn.execute(
            "SELECT student_id, status FROM attendance_records WHERE class_id=? AND term_id=? AND date=?",
            (class_id, term["id"], date_str),
        ).fetchall()
    }
    conn.close()
    prev_day = (datetime.date.fromisoformat(date_str) - datetime.timedelta(days=1)).isoformat()
    next_day = (datetime.date.fromisoformat(date_str) + datetime.timedelta(days=1)).isoformat()
    return render_template(
        "roll_call.html", class_row=class_row, students=students, student_full_name=student_full_name,
        date_str=date_str, prev_day=prev_day, next_day=next_day, existing=existing,
        today=datetime.date.today().isoformat(),
    )


@app.route("/my-class/<int:class_id>/roll-call/history")
@login_required()
def roll_call_history(class_id):
    conn = get_db()
    class_row = _require_own_class(conn, class_id)
    if not class_row:
        conn.close()
        flash("You're not the form teacher for that class.", "error")
        return redirect(url_for("dashboard"))

    term = current_term(conn)
    if not term:
        conn.close()
        flash("There's no active term set up yet. Ask your admin to set one under Setup → Terms.", "error")
        return redirect(url_for("dashboard"))

    students = conn.execute(
        "SELECT s.*, sti.days_school_opened, sti.days_present, sti.days_absent "
        "FROM students s LEFT JOIN student_term_info sti ON sti.student_id=s.id AND sti.term_id=? "
        "WHERE s.class_id=? AND s.is_active=1 ORDER BY s.admission_no, s.last_name",
        (term["id"], class_id),
    ).fetchall()
    summaries = []
    for s in students:
        opened = s["days_school_opened"] or 0
        present = s["days_present"] or 0
        absent = s["days_absent"] or 0
        summaries.append({
            "student": s, "opened": opened, "present": present, "absent": absent,
            "percentage": attendance_percentage(present, opened),
        })

    dates = conn.execute(
        "SELECT date, "
        "SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present, "
        "SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END) AS absent "
        "FROM attendance_records WHERE class_id=? AND term_id=? GROUP BY date ORDER BY date DESC",
        (class_id, term["id"]),
    ).fetchall()
    conn.close()
    return render_template(
        "roll_call_history.html", class_row=class_row, summaries=summaries, dates=dates,
        student_full_name=student_full_name,
    )


@app.route("/my-class/<int:class_id>/csv_template")
@login_required()
def my_class_csv_template(class_id):
    conn = get_db()
    class_row = _require_own_class(conn, class_id)
    if not class_row:
        conn.close()
        flash("You're not the form teacher for that class.", "error")
        return redirect(url_for("dashboard"))
    students = conn.execute(
        "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY admission_no, last_name", (class_id,)
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv_module.writer(buf)
    writer.writerow([
        "admission_no", "first_name", "last_name", "other_names", "gender",
        "date_of_birth", "religion", "parent_name", "parent_address", "parent_email", "parent_phone", "parent_relationship",
    ])
    for s in students:
        writer.writerow([
            s["admission_no"], s["first_name"], s["last_name"], s["other_names"] or "",
            s["gender"] or "", s["date_of_birth"] or "", s["religion"] or "",
            s["parent_name"] or "", s["parent_address"] or "", s["parent_email"] or "", s["parent_phone"] or "",
            s["parent_relationship"] or "",
        ])
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    fname = f"class_register_{class_row['name']}.csv".replace(" ", "_")
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=fname)


@app.route("/my-class/<int:class_id>/csv_upload", methods=["POST"])
@login_required()
def my_class_csv_upload(class_id):
    conn = get_db()
    class_row = _require_own_class(conn, class_id)
    if not class_row:
        conn.close()
        flash("You're not the form teacher for that class.", "error")
        return redirect(url_for("dashboard"))

    file = request.files.get("csv_file")
    if not file or file.filename == "":
        conn.close()
        flash("Please choose a CSV file to upload.", "error")
        return redirect(url_for("my_class_roster", class_id=class_id))

    existing_by_adm = {
        s["admission_no"]: s["id"]
        for s in conn.execute("SELECT * FROM students WHERE class_id=?", (class_id,)).fetchall()
    }
    text = file.read().decode("utf-8-sig")
    reader = csv_module.DictReader(io.StringIO(text))
    required_cols = {"admission_no", "first_name", "last_name"}
    if not required_cols.issubset(set(c.strip() for c in (reader.fieldnames or []))):
        conn.close()
        flash(f"CSV must at least have these columns: {', '.join(sorted(required_cols))}. Download the template for reference.", "error")
        return redirect(url_for("my_class_roster", class_id=class_id))

    added, updated, skipped = 0, 0, []
    for i, row in enumerate(reader, start=2):
        adm = (row.get("admission_no") or "").strip()
        fn = (row.get("first_name") or "").strip()
        ln = (row.get("last_name") or "").strip()
        if not (adm and fn and ln):
            skipped.append(f"Row {i}: missing required field(s)")
            continue
        fields = (
            row.get("other_names", "").strip() or None,
            row.get("gender", "").strip().upper()[:1] or None,
            row.get("date_of_birth", "").strip() or None,
            row.get("religion", "").strip() or None,
            row.get("parent_name", "").strip() or None,
            row.get("parent_address", "").strip() or None,
            row.get("parent_email", "").strip() or None,
            row.get("parent_phone", "").strip() or None,
            row.get("parent_relationship", "").strip() or None,
        )
        try:
            if adm in existing_by_adm:
                conn.execute(
                    "UPDATE students SET first_name=?, last_name=?, other_names=?, gender=?, date_of_birth=?, "
                    "religion=?, parent_name=?, parent_address=?, parent_email=?, parent_phone=?, parent_relationship=? "
                    "WHERE id=?",
                    (fn, ln, *fields, existing_by_adm[adm]),
                )
                updated += 1
            else:
                cur = conn.execute(
                    "INSERT INTO students (admission_no, first_name, last_name, other_names, gender, class_id, "
                    "date_of_birth, religion, parent_name, parent_address, parent_email, parent_phone, parent_relationship) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (adm, fn, ln, fields[0], fields[1], class_id, fields[2], fields[3], fields[4], fields[5], fields[6], fields[7], fields[8]),
                )
                upsert_enrollment(conn, cur.lastrowid, class_id)
                added += 1
        except Exception:
            skipped.append(f"Row {i}: couldn't save '{fn} {ln}' ({adm})")

    conn.commit()
    conn.close()
    if added or updated:
        flash(f"Imported: {added} new student(s) added, {updated} existing student(s) updated.", "success")
    if skipped:
        preview = "; ".join(skipped[:8]) + (f" (+{len(skipped)-8} more)" if len(skipped) > 8 else "")
        flash(f"Skipped {len(skipped)} row(s): {preview}", "error")
    return redirect(url_for("my_class_roster", class_id=class_id))


@app.route("/my-class/<int:class_id>/students/<int:student_id>/edit", methods=["POST"])
@login_required()
def my_class_edit_student(class_id, student_id):
    conn = get_db()
    class_row = class_in_school(conn, class_id)
    if not class_row or (session["role"] not in ("admin", "sub_admin") and class_id not in form_teacher_class_ids(conn, session["user_id"])):
        conn.close()
        flash("You're not the form teacher for that class.", "error")
        return redirect(url_for("dashboard"))
    try:
        status = request.form.get("status", "Active")
        if status not in ("Active", "Graduated", "Transferred", "Withdrawn", "Suspended"):
            status = "Active"
        conn.execute(
            "UPDATE students SET first_name=?, last_name=?, other_names=?, admission_no=?, gender=?, "
            "date_of_birth=?, religion=?, parent_name=?, parent_address=?, parent_email=?, parent_phone=?, parent_relationship=?, "
            "status=?, phone=?, is_active=? "
            "WHERE id=? AND class_id=?",
            (
                request.form["first_name"].strip(),
                request.form["last_name"].strip(),
                request.form.get("other_names", "").strip() or None,
                request.form["admission_no"].strip(),
                request.form.get("gender") or None,
                request.form.get("date_of_birth", "").strip() or None,
                request.form.get("religion", "").strip() or None,
                request.form.get("parent_name", "").strip() or None,
                request.form.get("parent_address", "").strip() or None,
                request.form.get("parent_email", "").strip() or None,
                request.form.get("parent_phone", "").strip() or None,
                request.form.get("parent_relationship", "").strip() or None,
                status,
                request.form.get("phone", "").strip() or None,
                1 if status == "Active" else 0,
                student_id, class_id,
            ),
        )
        conn.commit()
        flash("Student details updated.", "success")
    except Exception:
        flash("That register number is already used by another student in this class.", "error")
    conn.close()
    return redirect(url_for("my_class_roster", class_id=class_id))


# ---------- score entry (teacher) ----------

@app.route("/scores/<int:class_id>/<int:subject_id>", methods=["GET", "POST"])
@login_required()
def score_entry(class_id, subject_id):
    conn = get_db()
    term = current_term(conn)
    if not term:
        conn.close()
        flash("No active term set. Ask the admin to activate a term.", "error")
        return redirect(url_for("dashboard"))

    class_row = class_in_school(conn, class_id)
    subject_row = subject_in_school(conn, subject_id)
    if not class_row or not subject_row:
        conn.close()
        flash("Class or subject not found.", "error")
        return redirect(url_for("dashboard"))

    cs = conn.execute(
        "SELECT * FROM class_subjects WHERE class_id=? AND subject_id=?", (class_id, subject_id)
    ).fetchone()
    if not cs:
        conn.close()
        flash("This subject is not assigned to this class.", "error")
        return redirect(url_for("dashboard"))
    if session["role"] == "teacher" and cs["teacher_id"] != session["user_id"]:
        conn.close()
        flash("You are not assigned to teach this subject/class.", "error")
        return redirect(url_for("dashboard"))

    config = get_grading_config(conn)

    if request.method == "POST":
        students_ids = request.form.getlist("student_id")
        allowed_ids = {r["id"] for r in conn.execute(
            "SELECT id FROM students WHERE class_id=?", (class_id,)).fetchall()}
        use_ca3 = ca3_enabled(config)
        bad_rows = []
        for sid in students_ids:
            if not sid.isdigit() or int(sid) not in allowed_ids:
                continue  # never write a score for a student outside this class
            sid = int(sid)
            try:
                ca1 = float(request.form.get(f"ca1_{sid}", "0") or "0")
                ca2 = float(request.form.get(f"ca2_{sid}", "0") or "0")
                ca3 = float(request.form.get(f"ca3_{sid}", "0") or "0") if use_ca3 else 0.0
                exam = float(request.form.get(f"exam_{sid}", "0") or "0")
            except ValueError:
                bad_rows.append(f"student {sid}: scores must be numbers")
                continue
            errs = score_range_errors(config, ca1, ca2, ca3, exam)
            if errs:
                bad_rows.append(f"student {sid}: " + "; ".join(errs))
                continue
            save_score(conn, sid, subject_id, term["id"], ca1, ca2, ca3, exam, session["user_id"])
        conn.commit()
        if bad_rows:
            flash("Some rows were not saved — " + " | ".join(bad_rows[:5]), "error")
        else:
            flash("Scores saved.", "success")

    students = conn.execute(
        "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY admission_no, last_name", (class_id,)
    ).fetchall()
    existing = {
        row["student_id"]: row
        for row in conn.execute(
            "SELECT * FROM scores WHERE subject_id=? AND term_id=? AND student_id IN "
            "(SELECT id FROM students WHERE class_id=?)", (subject_id, term["id"], class_id)
        ).fetchall()
    }
    conn.close()
    return render_template(
        "score_entry.html", students=students, existing=existing, config=config,
        class_row=class_row, subject_row=subject_row, term=term, student_full_name=student_full_name,
    )


@app.route("/scores/<int:class_id>/<int:subject_id>/csv_template")
@login_required()
def score_csv_template(class_id, subject_id):
    conn = get_db()
    class_row = class_in_school(conn, class_id)
    subject_row = subject_in_school(conn, subject_id)
    term = current_term(conn)
    if not class_row or not subject_row or not term:
        conn.close()
        flash("Class, subject, or active term not found.", "error")
        return redirect(url_for("dashboard"))

    config = get_grading_config(conn)
    students = conn.execute(
        "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY admission_no, last_name", (class_id,)
    ).fetchall()
    existing = {
        row["student_id"]: row
        for row in conn.execute(
            "SELECT * FROM scores WHERE subject_id=? AND term_id=? AND student_id IN "
            "(SELECT id FROM students WHERE class_id=?)", (subject_id, term["id"], class_id)
        ).fetchall()
    }
    conn.close()

    buf = io.StringIO()
    writer = csv_module.writer(buf)
    use_ca3 = ca3_enabled(config)
    maxes = f"CA1: {config['ca1_max']}, CA2: {config['ca2_max']}, " + (f"CA3: {config['ca3_max']}, " if use_ca3 else "") + f"Exam: {config['exam_max']}"
    writer.writerow([f"# Max marks — {maxes}"])
    writer.writerow(["admission_no", "student_name", "ca1", "ca2"] + (["ca3"] if use_ca3 else []) + ["exam", "total"])
    for s in students:
        sc = existing.get(s["id"])
        ca1 = sc["ca1"] if sc else ""
        ca2 = sc["ca2"] if sc else ""
        ca3 = (sc["ca3"] or 0) if sc else ""
        exam = sc["exam"] if sc else ""
        total = compute_total(ca1, ca2, exam, ca3 or 0) if sc else ""
        writer.writerow([s["admission_no"], student_full_name(s), ca1, ca2] + ([ca3] if use_ca3 else []) + [exam, total])
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    fname = f"scores_{class_row['name']}_{subject_row['name']}.csv".replace(" ", "_")
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=fname)


@app.route("/scores/<int:class_id>/<int:subject_id>/csv_upload", methods=["POST"])
@login_required()
def score_csv_upload(class_id, subject_id):
    conn = get_db()
    class_row = class_in_school(conn, class_id)
    subject_row = subject_in_school(conn, subject_id)
    term = current_term(conn)
    if not class_row or not subject_row or not term:
        conn.close()
        flash("Class, subject, or active term not found.", "error")
        return redirect(url_for("dashboard"))

    cs = conn.execute("SELECT * FROM class_subjects WHERE class_id=? AND subject_id=?", (class_id, subject_id)).fetchone()
    if session["role"] == "teacher" and (not cs or cs["teacher_id"] != session["user_id"]):
        conn.close()
        flash("You are not assigned to teach this subject/class.", "error")
        return redirect(url_for("dashboard"))

    file = request.files.get("csv_file")
    if not file or file.filename == "":
        conn.close()
        flash("Please choose a CSV file to upload.", "error")
        return redirect(url_for("score_entry", class_id=class_id, subject_id=subject_id))

    students_by_adm = {
        s["admission_no"]: s
        for s in conn.execute("SELECT * FROM students WHERE class_id=?", (class_id,)).fetchall()
    }
    config = get_grading_config(conn)
    text = file.read().decode("utf-8-sig")
    # Skip a leading "# Max marks..." comment line if present (from our own
    # template). The CSV writer may have wrapped it in quotes since it
    # contains commas, so check for both forms.
    lines = text.splitlines()
    if lines and lines[0].strip().lstrip('"').startswith("#"):
        text = "\n".join(lines[1:])
    reader = csv_module.DictReader(io.StringIO(text))
    updated, skipped = 0, []
    for i, row in enumerate(reader, start=2):
        adm = (row.get("admission_no") or "").strip()
        student = students_by_adm.get(adm)
        if not student:
            skipped.append(f"Row {i}: no student with Admission No./Register No. '{adm}' in this class")
            continue
        sid = student["id"]
        student_label = f"{student_full_name(student)} ({adm})"
        try:
            ca1 = float(row.get("ca1") or 0)
            ca2 = float(row.get("ca2") or 0)
            ca3 = float(row.get("ca3") or 0) if ca3_enabled(config) else 0.0
            exam = float(row.get("exam") or 0)
        except ValueError:
            skipped.append(f"Row {i} ({student_label}, {subject_row['name']}): CA1/CA2/CA3/Exam must be numbers")
            continue

        row_errors = score_range_errors(config, ca1, ca2, ca3, exam)
        if row_errors:
            skipped.append(f"Row {i} ({student_label}, {subject_row['name']}): " + "; ".join(row_errors))
            continue

        save_score(conn, sid, subject_id, term["id"], ca1, ca2, ca3, exam, session["user_id"])
        updated += 1

    conn.commit()
    conn.close()
    if updated:
        flash(f"Updated scores for {updated} student(s) from the uploaded file.", "success")
    if skipped:
        preview = "; ".join(skipped[:8]) + (f" (+{len(skipped)-8} more)" if len(skipped) > 8 else "")
        flash(f"Skipped {len(skipped)} row(s): {preview}", "error")
    return redirect(url_for("score_entry", class_id=class_id, subject_id=subject_id))


@app.route("/scores/<int:class_id>/<int:subject_id>/history")
@login_required()
def score_history_view(class_id, subject_id):
    conn = get_db()
    class_row = class_in_school(conn, class_id)
    subject_row = subject_in_school(conn, subject_id)
    if not class_row or not subject_row:
        conn.close()
        flash("Class or subject not found.", "error")
        return redirect(url_for("dashboard"))
    cs = conn.execute("SELECT * FROM class_subjects WHERE class_id=? AND subject_id=?", (class_id, subject_id)).fetchone()
    if session["role"] == "teacher" and (not cs or cs["teacher_id"] != session["user_id"]):
        conn.close()
        flash("You are not assigned to teach this subject/class.", "error")
        return redirect(url_for("dashboard"))

    history = conn.execute(
        "SELECT h.*, s.first_name, s.last_name, s.other_names, u.name as changed_by_name "
        "FROM score_history h JOIN students s ON s.id=h.student_id "
        "LEFT JOIN users u ON u.id=h.changed_by "
        "WHERE h.subject_id=? AND h.term_id=(SELECT id FROM terms WHERE is_active=1 LIMIT 1) "
        "AND s.class_id=? ORDER BY h.changed_at DESC", (subject_id, class_id)
    ).fetchall()
    conn.close()
    return render_template(
        "score_history.html", class_row=class_row, subject_row=subject_row, history=history,
        student_full_name=student_full_name,
    )


# ---------- broadsheet ----------

def build_broadsheet_data(conn, class_id, term_id):
    school_id = current_school_id()
    subjects = conn.execute(
        "SELECT s.* FROM subjects s JOIN class_subjects cs ON cs.subject_id=s.id "
        "WHERE cs.class_id=? ORDER BY s.name", (class_id,)
    ).fetchall()
    # Use the enrollment record for this term's session if one exists (so a
    # later promotion doesn't rewrite which class a student appears under
    # for a past term); fall back to their current class otherwise.
    term_row = conn.execute("SELECT session_id FROM terms WHERE id=?", (term_id,)).fetchone()
    session_id = term_row["session_id"] if term_row else None
    students = conn.execute(
        "SELECT s.* FROM students s "
        "LEFT JOIN enrollments e ON e.student_id = s.id AND e.session_id = ? "
        "WHERE COALESCE(e.class_id, s.class_id) = ? AND s.is_active=1 ORDER BY s.last_name",
        (session_id, class_id),
    ).fetchall()

    rows = []
    for st in students:
        subj_scores = {}
        total = 0
        count = 0
        for subj in subjects:
            score = conn.execute(
                "SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?",
                (st["id"], subj["id"], term_id),
            ).fetchone()
            if score:
                t = compute_total(score["ca1"], score["ca2"], score["exam"], score["ca3"])
                grade, remark = grade_for(t, conn, school_id)
                subj_scores[subj["id"]] = {"total": t, "grade": grade}
                total += t
                count += 1
            else:
                subj_scores[subj["id"]] = {"total": "-", "grade": "-"}
        average = round(total / count, 2) if count else 0
        rows.append({
            "student": st, "scores": subj_scores, "total": total, "average": average
        })

    rows.sort(key=lambda r: r["total"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["position"] = i

    return subjects, rows


def build_cumulative_broadsheet_data(conn, class_id, session_id):
    """Annual/Cumulative broadsheet: for each subject, averages the totals
    from every term in the session that has a score recorded (a term with
    no score for that subject simply isn't counted — it doesn't drag the
    average down to 0), then ranks students by their overall cumulative
    average."""
    school_id = current_school_id()
    subjects = conn.execute(
        "SELECT s.* FROM subjects s JOIN class_subjects cs ON cs.subject_id=s.id "
        "WHERE cs.class_id=? ORDER BY s.name", (class_id,)
    ).fetchall()
    terms = terms_for_session(conn, session_id)
    students = conn.execute(
        "SELECT s.* FROM students s "
        "LEFT JOIN enrollments e ON e.student_id = s.id AND e.session_id = ? "
        "WHERE COALESCE(e.class_id, s.class_id) = ? AND s.is_active=1 ORDER BY s.last_name",
        (session_id, class_id),
    ).fetchall()

    rows = []
    for st in students:
        subj_cumulative = {}
        overall_total = 0
        overall_count = 0
        for subj in subjects:
            term_values = []
            present_totals = []
            for term in terms:
                score = conn.execute(
                    "SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?",
                    (st["id"], subj["id"], term["id"]),
                ).fetchone()
                if score:
                    t = compute_total(score["ca1"], score["ca2"], score["exam"], score["ca3"])
                    term_values.append(t)
                    present_totals.append(t)
                else:
                    term_values.append(None)
            if present_totals:
                cum_avg = round(sum(present_totals) / len(present_totals), 2)
                grade, remark = grade_for(cum_avg, conn, school_id)
                overall_total += cum_avg
                overall_count += 1
            else:
                cum_avg, grade, remark = "-", "-", "-"
            subj_cumulative[subj["id"]] = {"term_values": term_values, "average": cum_avg, "grade": grade}
        overall_average = round(overall_total / overall_count, 2) if overall_count else 0
        rows.append({"student": st, "subjects": subj_cumulative, "average": overall_average})

    rows.sort(key=lambda r: r["average"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["position"] = i

    return subjects, terms, rows


def build_cumulative_result_data(conn, student_id, session_id):
    student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    class_id = student_class_for_session(conn, student_id, session_id)
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
    subjects, terms, rows = build_cumulative_broadsheet_data(conn, class_id, session_id)

    my_row = next((r for r in rows if r["student"]["id"] == student_id), None)
    school_id = current_school_id()
    average = my_row["average"] if my_row else 0
    grade, remark = grade_for(average, conn, school_id) if my_row else ("-", "-")

    subject_details = []
    for subj in subjects:
        cell = my_row["subjects"][subj["id"]] if my_row else {"term_values": [None] * len(terms), "average": "-", "grade": "-"}
        subject_details.append({"name": subj["name"], **cell})

    return {
        "student": student, "class_row": class_row, "terms": terms, "subjects": subject_details,
        "average": average, "grade": grade, "remark": remark,
        "position": my_row["position"] if my_row else "-", "class_size": len(rows),
    }


@app.route("/broadsheet/<int:class_id>")
@login_required()
def broadsheet(class_id):
    conn = get_db()
    denied = require_class_result_access(conn, class_id)
    if denied:
        conn.close()
        return denied
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("dashboard"))
    subjects, rows = build_broadsheet_data(conn, class_id, term["id"])
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
    all_terms = all_terms_for_school(conn)
    conn.close()
    return render_template(
        "broadsheet.html", subjects=subjects, rows=rows, class_row=class_row, term=term,
        student_full_name=student_full_name, all_terms=all_terms,
    )


@app.route("/broadsheet/<int:class_id>/pdf")
@login_required()
def broadsheet_pdf(class_id):
    conn = get_db()
    denied = require_class_result_access(conn, class_id)
    if denied:
        conn.close()
        return denied
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("dashboard"))
    subjects, rows = build_broadsheet_data(conn, class_id, term["id"])
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
    school = get_school(conn, current_school_id())
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p
    conn.close()
    buf = build_broadsheet_pdf(
        class_row, term, subjects, rows,
        school_name=school["name"] if school else None,
        logo_path=logo_path, student_full_name=student_full_name,
        font_choice=school["pdf_font"] if school else "Helvetica",
    )
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                      download_name=f"broadsheet_{class_row['name']}_{term['name']}.pdf".replace(" ", "_"))


@app.route("/cumulative/<int:class_id>")
@login_required()
def cumulative_broadsheet(class_id):
    conn = get_db()
    denied = require_class_result_access(conn, class_id)
    if denied:
        conn.close()
        return denied
    denied = require_cumulative_enabled(conn)
    if denied:
        conn.close()
        return denied
    session_row = resolve_session(conn, request.args.get("session_id", type=int))
    if not session_row:
        conn.close()
        flash("No academic session set up yet.", "error")
        return redirect(url_for("dashboard"))
    subjects, terms, rows = build_cumulative_broadsheet_data(conn, class_id, session_row["id"])
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
    all_sessions = conn.execute(
        "SELECT * FROM sessions WHERE school_id=? ORDER BY id DESC", (current_school_id(),)
    ).fetchall()
    conn.close()
    return render_template(
        "cumulative_broadsheet.html", class_row=class_row, academic_session=session_row, subjects=subjects,
        terms=terms, rows=rows, all_sessions=all_sessions, student_full_name=student_full_name,
    )


@app.route("/class/<int:class_id>/email_results", methods=["POST"])
@login_required()
def email_class_results(class_id):
    conn = get_db()
    denied = require_class_result_access(conn, class_id)
    if denied:
        conn.close()
        return denied
    term = current_term(conn)
    if not term:
        conn.close()
        flash("No active term set.", "error")
        return redirect(url_for("dashboard"))
    if not term["is_published"]:
        conn.close()
        flash(
            "This term's results haven't been published yet. Ask your admin/principal to "
            "publish the term (Setup → Terms) before emailing results to parents.",
            "error",
        )
        return redirect(url_for("broadsheet", class_id=class_id))

    school = get_school(conn, current_school_id())
    students = conn.execute(
        "SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY last_name", (class_id,)
    ).fetchall()

    offline_token = request.form.get("offline_token")
    if offline_sync_existing_id(conn, offline_token) is not None:
        conn.close()
        flash("Results already emailed for this class (skipped duplicate offline resend).", "success")
        return redirect(url_for("broadsheet", class_id=class_id))

    sent, skipped = 0, 0
    for st in students:
        if not st["parent_email"]:
            skipped += 1
            continue
        data = build_result_data(conn, st["id"], term["id"])
        logo_path = None
        if school and school["logo_filename"]:
            p = os.path.join(INSTANCE_DIR, school["logo_filename"])
            if os.path.exists(p):
                logo_path = p
        pdf_buf = build_result_pdf(data, term, school_name=school["name"] if school else None,
                                    logo_path=logo_path, student_full_name=student_full_name,
                                    font_choice=school["pdf_font"] if school else "Helvetica")
        ok, _ = send_email(
            school, st["parent_email"],
            f"{student_full_name(st)}'s Result — {term['session_name']} {term['name']}",
            f"Please find attached {student_full_name(st)}'s result for {term['session_name']} {term['name']}.",
            attachment_bytes=pdf_buf.getvalue(),
            attachment_filename=f"result_{st['admission_no']}.pdf".replace("/", "-"),
        )
        if ok:
            sent += 1
        else:
            skipped += 1
    if sent:
        offline_sync_remember(conn, offline_token, "email_class_results", class_id)
    conn.close()
    flash(f"Emailed {sent} result(s). {skipped} skipped (no parent email on file, or sending failed).",
          "success" if sent else "error")
    return redirect(url_for("broadsheet", class_id=class_id))


# ---------- terminal result ----------

def build_result_data(conn, student_id, term_id):
    student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    historical_class_id = student_class_for_term(conn, student_id, term_id)
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (historical_class_id,)).fetchone()
    subjects, rows = build_broadsheet_data(conn, historical_class_id, term_id)

    my_row = next((r for r in rows if r["student"]["id"] == student_id), None)
    class_size = len(rows)
    school_id = current_school_id()

    subject_details = []
    subjects_written = 0
    for subj in subjects:
        score = conn.execute(
            "SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?",
            (student_id, subj["id"], term_id),
        ).fetchone()
        if score:
            subjects_written += 1
            total = compute_total(score["ca1"], score["ca2"], score["exam"], score["ca3"])
            grade, remark = grade_for(total, conn, school_id)
            subject_details.append({
                "name": subj["name"], "ca1": score["ca1"], "ca2": score["ca2"], "ca3": score["ca3"] or 0,
                "exam": score["exam"], "total": total, "grade": grade, "remark": remark
            })
        else:
            subject_details.append({
                "name": subj["name"], "ca1": "-", "ca2": "-", "ca3": "-", "exam": "-",
                "total": "-", "grade": "-", "remark": "-"
            })

    info_row = conn.execute(
        "SELECT * FROM student_term_info WHERE student_id=? AND term_id=?", (student_id, term_id)
    ).fetchone()

    # info stays exactly as before (a Row, or None) unless this school has
    # turned on auto-generated comments — in which case we swap in a dict
    # with the comment field(s) computed from the student's grade, so
    # schools that never touch the new toggle see zero behavior change.
    info = info_row
    average = my_row["average"] if my_row else 0
    school = get_school(conn, school_id)
    if school and (school["auto_teacher_comment"] or school["auto_principal_comment"]):
        _, remark = grade_for(average, conn, school_id)
        info = dict(info_row) if info_row else {
            "days_school_opened": None, "days_present": None, "days_absent": None,
            "teacher_signed_date": None, "principal_signed_date": None,
            "teacher_comment": None, "principal_comment": None,
            "teacher_signed_by": None, "principal_signed_by": None,
        }
        if school["auto_teacher_comment"]:
            info["teacher_comment"] = generate_teacher_comment(remark, average, subjects_written)
        if school["auto_principal_comment"]:
            info["principal_comment"] = generate_principal_comment(remark, average, subjects_written)

    ratings = conn.execute(
        "SELECT st.name, st.category, r.rating FROM student_skill_ratings r "
        "JOIN skill_traits st ON st.id=r.trait_id WHERE r.student_id=? AND r.term_id=?",
        (student_id, term_id),
    ).fetchall()

    # Digital signatures: only shown when the specific signer recorded on
    # *this* result has one uploaded AND has turned it on — never "whoever
    # is logged in now", and teacher/principal are always looked up
    # separately so one can never appear in the other's slot.
    def _signature_user(field):
        if not info:
            return None
        signer_id = info[field] if field in info.keys() else None
        if not signer_id:
            return None
        row = conn.execute(
            "SELECT id, name, signature_filename, use_digital_signature FROM users WHERE id=? AND school_id=?",
            (signer_id, school_id),
        ).fetchone()
        if row and row["signature_filename"] and row["use_digital_signature"]:
            return row
        return None

    teacher_signature_user = _signature_user("teacher_signed_by")
    principal_signature_user = _signature_user("principal_signed_by")

    return {
        "student": student, "class_row": class_row, "subjects": subject_details,
        "total": my_row["total"] if my_row else 0,
        "average": my_row["average"] if my_row else 0,
        "position": my_row["position"] if my_row else "-",
        "class_size": class_size, "info": info, "ratings": ratings,
        "subjects_written": subjects_written,
        "show_ca3": ca3_enabled(conn.execute(
            "SELECT ca3_max FROM grading_config WHERE school_id=? LIMIT 1", (school_id,)).fetchone()),
        "result_date": format_dmy(datetime.date.today().isoformat()) if school and school["show_result_date"] else None,
        "teacher_signature_user": teacher_signature_user,
        "principal_signature_user": principal_signature_user,
    }


@app.route("/result/<int:student_id>")
@login_required()
def result(student_id):
    conn = get_db()
    student_row = student_in_school(conn, student_id)
    if not student_row:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("dashboard"))
    historical_class_id = student_class_for_term(conn, student_id, term["id"])
    denied = require_class_result_access(conn, historical_class_id)
    if denied:
        conn.close()
        return denied
    data = build_result_data(conn, student_id, term["id"])
    all_traits = conn.execute("SELECT * FROM skill_traits WHERE school_id=? ORDER BY category, name", (current_school_id(),)).fetchall()
    all_terms = all_terms_for_school(conn)
    conn.close()
    return render_template(
        "result.html", term=term, all_traits=all_traits, student_full_name=student_full_name,
        all_terms=all_terms, **data
    )


@app.route("/result/<int:student_id>/pdf")
@login_required()
def result_pdf(student_id):
    conn = get_db()
    student_row = student_in_school(conn, student_id)
    if not student_row:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("dashboard"))
    historical_class_id = student_class_for_term(conn, student_id, term["id"])
    denied = require_class_result_access(conn, historical_class_id)
    if denied:
        conn.close()
        return denied
    data = build_result_data(conn, student_id, term["id"])
    school = get_school(conn, current_school_id())
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p
    teacher_signature = None
    if data.get("teacher_signature_user"):
        u = data["teacher_signature_user"]
        teacher_signature = {"path": os.path.join(SIGNATURES_DIR, u["signature_filename"]), "name": u["name"]}
    principal_signature = None
    if data.get("principal_signature_user"):
        u = data["principal_signature_user"]
        principal_signature = {"path": os.path.join(SIGNATURES_DIR, u["signature_filename"]), "name": u["name"]}
    conn.close()
    buf = build_result_pdf(
        data, term, school_name=school["name"] if school else None,
        logo_path=logo_path, student_full_name=student_full_name,
        font_choice=school["pdf_font"] if school else "Helvetica",
        accent_color=school["result_accent_color"] if school and school["result_accent_color"] else "#1f3a5f",
        name_align=school["name_align"] if school else None,
        teacher_signature=teacher_signature, principal_signature=principal_signature,
    )
    fname = f"result_{data['student']['admission_no']}_{term['name']}.pdf".replace(" ", "_").replace("/", "-")
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=fname)


@app.route("/cumulative/student/<int:student_id>")
@login_required()
def cumulative_result(student_id):
    conn = get_db()
    student_row = student_in_school(conn, student_id)
    if not student_row:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    denied = require_cumulative_enabled(conn)
    if denied:
        conn.close()
        return denied
    session_row = resolve_session(conn, request.args.get("session_id", type=int))
    if not session_row:
        conn.close()
        flash("No academic session set up yet.", "error")
        return redirect(url_for("dashboard"))
    historical_class_id = student_class_for_session(conn, student_id, session_row["id"])
    denied = require_class_result_access(conn, historical_class_id)
    if denied:
        conn.close()
        return denied
    data = build_cumulative_result_data(conn, student_id, session_row["id"])
    all_sessions = conn.execute(
        "SELECT * FROM sessions WHERE school_id=? ORDER BY id DESC", (current_school_id(),)
    ).fetchall()
    conn.close()
    return render_template(
        "cumulative_result.html", academic_session=session_row, all_sessions=all_sessions,
        student_full_name=student_full_name, **data
    )


@app.route("/cumulative/student/<int:student_id>/pdf")
@login_required()
def cumulative_result_pdf(student_id):
    conn = get_db()
    student_row = student_in_school(conn, student_id)
    if not student_row:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    denied = require_cumulative_enabled(conn)
    if denied:
        conn.close()
        return denied
    session_row = resolve_session(conn, request.args.get("session_id", type=int))
    if not session_row:
        conn.close()
        flash("No academic session set up yet.", "error")
        return redirect(url_for("dashboard"))
    historical_class_id = student_class_for_session(conn, student_id, session_row["id"])
    denied = require_class_result_access(conn, historical_class_id)
    if denied:
        conn.close()
        return denied
    data = build_cumulative_result_data(conn, student_id, session_row["id"])
    school = get_school(conn, current_school_id())
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p
    conn.close()
    buf = build_cumulative_result_pdf(
        data, session_row, school_name=school["name"] if school else None,
        logo_path=logo_path, student_full_name=student_full_name,
        font_choice=school["pdf_font"] if school else "Helvetica",
        accent_color=school["result_accent_color"] if school and school["result_accent_color"] else "#1f3a5f",
        name_align=school["name_align"] if school else None,
    )
    fname = f"annual_result_{data['student']['admission_no']}_{session_row['name']}.pdf".replace(" ", "_").replace("/", "-")
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=fname)


@app.route("/result/<int:student_id>/email", methods=["POST"])
@login_required()
def email_result(student_id):
    conn = get_db()
    student_row = student_in_school(conn, student_id)
    if not student_row:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    denied = require_class_result_access(conn, student_row["class_id"])
    if denied:
        conn.close()
        return denied
    if not student_row["parent_email"]:
        conn.close()
        flash("This student has no parent email on file. Add one from Setup → Students.", "error")
        return redirect(url_for("result", student_id=student_id))

    term = current_term(conn)
    if not term:
        conn.close()
        flash("No active term set.", "error")
        return redirect(url_for("dashboard"))
    if not term["is_published"]:
        conn.close()
        flash(
            "This term's results haven't been published yet. Ask your admin/principal to "
            "publish the term (Setup → Terms) before emailing results to parents.",
            "error",
        )
        return redirect(url_for("result", student_id=student_id))

    offline_token = request.form.get("offline_token")
    if offline_sync_existing_id(conn, offline_token) is not None:
        # This exact offline-queued email already went out — most likely
        # the send succeeded earlier but the device never saw the response
        # (e.g. connection dropped right after) and retried. Don't send it
        # again; just report success as if it had gone through this time.
        conn.close()
        flash(f"Result emailed to {student_row['parent_email']}.", "success")
        return redirect(url_for("result", student_id=student_id))

    data = build_result_data(conn, student_id, term["id"])
    school = get_school(conn, current_school_id())
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p
    pdf_buf = build_result_pdf(data, term, school_name=school["name"] if school else None,
                                logo_path=logo_path, student_full_name=student_full_name,
                                font_choice=school["pdf_font"] if school else "Helvetica")
    conn.close()
    ok, msg = send_email(
        school, student_row["parent_email"],
        f"{student_full_name(student_row)}'s Result — {term['session_name']} {term['name']}",
        f"Please find attached {student_full_name(student_row)}'s result for {term['session_name']} {term['name']}.",
        attachment_bytes=pdf_buf.getvalue(),
        attachment_filename=f"result_{student_row['admission_no']}.pdf".replace("/", "-"),
    )
    if ok:
        offline_sync_remember(conn, offline_token, "email_result", student_id)
    conn.close()
    flash(msg, "success" if ok else "error")
    return redirect(url_for("result", student_id=student_id))


@app.route("/result/<int:student_id>/extra", methods=["POST"])
@login_required()
def result_extra(student_id):
    conn = get_db()
    student_row = student_in_school(conn, student_id)
    if not student_row:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard"))
    denied = require_class_result_access(conn, student_row["class_id"])
    if denied:
        conn.close()
        return denied
    term_id = request.form["term_id"]
    days_present = int(request.form.get("days_present") or 0)
    days_absent = int(request.form.get("days_absent") or 0)
    days_school_opened = int(request.form.get("days_school_opened") or 0)

    if days_present < 0 or days_absent < 0 or days_school_opened < 0:
        conn.close()
        flash("Attendance figures can't be negative.", "error")
        return redirect(url_for("result", student_id=student_id))
    if days_present + days_absent > days_school_opened:
        conn.close()
        flash(
            f"Invalid attendance: Present ({days_present}) + Absent ({days_absent}) = "
            f"{days_present + days_absent}, which is more than Days School Opened ({days_school_opened}). "
            "Please correct the figures before saving.",
            "error",
        )
        return redirect(url_for("result", student_id=student_id))

    existing = conn.execute(
        "SELECT teacher_signed_by, principal_signed_by FROM student_term_info WHERE student_id=? AND term_id=?",
        (student_id, term_id),
    ).fetchone()
    teacher_signed_date = request.form.get("teacher_signed_date", "").strip() or None
    principal_signed_date = request.form.get("principal_signed_date", "").strip() or None
    # Whoever is saving a signed date is credited as that signer — but only
    # if their own role matches (a subject teacher saving a date can never
    # end up recorded as the principal's signature, or vice versa).
    teacher_signed_by = existing["teacher_signed_by"] if existing else None
    if teacher_signed_date and session.get("role") == "teacher":
        teacher_signed_by = session["user_id"]
    principal_signed_by = existing["principal_signed_by"] if existing else None
    if principal_signed_date and (
        session.get("role") in ("admin", "sub_admin") or session.get("position") in ("principal", "vice_principal")
    ):
        principal_signed_by = session["user_id"]

    conn.execute(
        "INSERT INTO student_term_info (student_id, term_id, days_present, days_absent, "
        "days_school_opened, teacher_comment, principal_comment, teacher_signed_date, principal_signed_date, "
        "teacher_signed_by, principal_signed_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(student_id, term_id) DO UPDATE SET "
        "days_present=excluded.days_present, days_absent=excluded.days_absent, "
        "days_school_opened=excluded.days_school_opened, "
        "teacher_comment=excluded.teacher_comment, principal_comment=excluded.principal_comment, "
        "teacher_signed_date=excluded.teacher_signed_date, principal_signed_date=excluded.principal_signed_date, "
        "teacher_signed_by=excluded.teacher_signed_by, principal_signed_by=excluded.principal_signed_by",
        (
            student_id, term_id, days_present, days_absent, days_school_opened,
            request.form.get("teacher_comment", ""),
            request.form.get("principal_comment", ""),
            teacher_signed_date,
            principal_signed_date,
            teacher_signed_by,
            principal_signed_by,
        ),
    )
    all_traits = conn.execute("SELECT * FROM skill_traits WHERE school_id=?", (current_school_id(),)).fetchall()
    for trait in all_traits:
        val = request.form.get(f"trait_{trait['id']}")
        if val:
            conn.execute(
                "INSERT INTO student_skill_ratings (student_id, term_id, trait_id, rating) "
                "VALUES (?,?,?,?) ON CONFLICT(student_id, term_id, trait_id) "
                "DO UPDATE SET rating=excluded.rating",
                (student_id, term_id, trait["id"], int(val)),
            )
    conn.commit()
    conn.close()
    flash("Report card details updated.", "success")
    return redirect(url_for("result", student_id=student_id))


@app.route("/class/<int:class_id>/results")
@login_required()
def class_results_list(class_id):
    conn = get_db()
    denied = require_class_result_access(conn, class_id)
    if denied:
        conn.close()
        return denied
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("dashboard"))
    students = conn.execute(
        "SELECT s.* FROM students s "
        "LEFT JOIN enrollments e ON e.student_id = s.id AND e.session_id = ? "
        "WHERE COALESCE(e.class_id, s.class_id) = ? AND s.is_active=1 ORDER BY s.last_name",
        (term["session_id"], class_id),
    ).fetchall()
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
    all_terms = all_terms_for_school(conn)
    conn.close()
    return render_template(
        "class_results_list.html", students=students, class_row=class_row, term=term,
        student_full_name=student_full_name, all_terms=all_terms,
    )


@app.route("/class/<int:class_id>/results_pdf")
@login_required()
def class_results_pdf(class_id):
    conn = get_db()
    denied = require_class_result_access(conn, class_id)
    if denied:
        conn.close()
        return denied
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("dashboard"))
    students = conn.execute(
        "SELECT s.* FROM students s "
        "LEFT JOIN enrollments e ON e.student_id = s.id AND e.session_id = ? "
        "WHERE COALESCE(e.class_id, s.class_id) = ? AND s.is_active=1 ORDER BY s.last_name",
        (term["session_id"], class_id),
    ).fetchall()
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
    if not students:
        conn.close()
        flash("No students found for this class/term.", "error")
        return redirect(url_for("class_results_list", class_id=class_id, term_id=term["id"]))

    school = get_school(conn, current_school_id())
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p

    data_list = [build_result_data(conn, s["id"], term["id"]) for s in students]
    conn.close()
    buf = build_class_results_pdf(
        data_list, term, school_name=school["name"] if school else None,
        logo_path=logo_path, student_full_name=student_full_name,
        font_choice=school["pdf_font"] if school else "Helvetica",
        accent_color=school["result_accent_color"] if school and school["result_accent_color"] else "#1f3a5f",
        name_align=school["name_align"] if school else None,
    )
    fname = f"all_results_{class_row['name']}_{term['name']}.pdf".replace(" ", "_")
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=fname)


@app.route("/classes")
@login_required()
def classes_list():
    conn = get_db()
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (current_school_id(),)).fetchall()
    accessible = get_accessible_class_ids(conn, session.get("role"), session.get("position"), session["user_id"])
    conn.close()
    return render_template("classes_list.html", classes=classes, accessible=accessible)


# ---------- learning materials ----------

def _material_extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _staff_accessible_classes(conn):
    """Classes this staff member is allowed to see materials for — the
    exact same rule already used for results/broadsheets, so a subject
    teacher who isn't a Form Teacher sees the same classes here as
    everywhere else in the app, no new permission surface."""
    accessible = get_accessible_class_ids(conn, session.get("role"), session.get("position"), session["user_id"])
    if accessible == "all":
        return conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (current_school_id(),)).fetchall()
    if not accessible:
        return []
    placeholders = ",".join("?" * len(accessible))
    return conn.execute(
        f"SELECT * FROM classes WHERE id IN ({placeholders}) ORDER BY name", accessible
    ).fetchall()


@app.route("/materials", methods=["GET", "POST"])
@login_required()
def materials():
    conn = get_db()
    school_id = current_school_id()
    can_upload = session.get("role") in ("admin", "sub_admin")

    if request.method == "POST":
        if not can_upload:
            conn.close()
            flash("Only a School Admin can upload learning materials.", "error")
            return redirect(url_for("materials"))
        session_id = request.form.get("session_id", type=int)
        class_id = request.form.get("class_id", type=int)
        subject_id = request.form.get("subject_id", type=int)
        title = request.form.get("title", "").strip()
        kind = request.form.get("kind", "Notes")
        external_url = request.form.get("external_url", "").strip()
        kind = kind if kind in MATERIAL_KINDS else "Notes"

        owner_session = conn.execute("SELECT * FROM sessions WHERE id=? AND school_id=?", (session_id, school_id)).fetchone()
        owner_class = conn.execute("SELECT * FROM classes WHERE id=? AND school_id=?", (class_id, school_id)).fetchone()
        owner_subject = conn.execute(
            "SELECT s.* FROM subjects s JOIN class_subjects cs ON cs.subject_id=s.id "
            "WHERE s.id=? AND cs.class_id=? AND s.school_id=?", (subject_id, class_id, school_id)
        ).fetchone()

        file = request.files.get("file")
        has_file = file and file.filename

        if not (owner_session and owner_class and owner_subject):
            flash("Choose a valid session, class and subject.", "error")
        elif not title:
            flash("Give the material a title.", "error")
        elif not has_file and not external_url:
            flash("Attach a file or provide a link.", "error")
        else:
            filename = original_filename = None
            if has_file:
                ext = _material_extension(file.filename)
                if ext not in MATERIAL_EXTENSIONS:
                    conn.close()
                    flash("File type not supported. Upload a PDF, Word, PowerPoint or image file — for videos, paste a link instead.", "error")
                    return redirect(url_for("materials"))
                school_dir = os.path.join(MATERIALS_DIR, str(school_id))
                os.makedirs(school_dir, exist_ok=True)
                original_filename = secure_filename(file.filename)
                filename = f"{secrets.token_hex(8)}.{ext}"
                file.save(os.path.join(school_dir, filename))

            conn.execute(
                "INSERT INTO materials (school_id, session_id, class_id, subject_id, title, kind, "
                "filename, original_filename, external_url, uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (school_id, session_id, class_id, subject_id, title, kind,
                 filename, original_filename, external_url or None, session["user_id"]),
            )
            conn.commit()
            log_audit(conn, session["role"], session.get("name"), "material_upload",
                       f"{title} — {owner_class['name']} / {owner_subject['name']}", school_id=school_id)
            conn.commit()
            flash("Material uploaded.", "success")
        return redirect(url_for(
            "materials", session_id=session_id, class_id=class_id, subject_id=subject_id
        ))

    accessible_classes = _staff_accessible_classes(conn)
    accessible_ids = [c["id"] for c in accessible_classes]

    all_sessions = conn.execute("SELECT * FROM sessions WHERE school_id=? ORDER BY id DESC", (school_id,)).fetchall()
    active_session = conn.execute("SELECT * FROM sessions WHERE school_id=? AND is_active=1", (school_id,)).fetchone()
    session_id = request.args.get("session_id", type=int) or (active_session["id"] if active_session else None)

    class_id = request.args.get("class_id", type=int)
    if class_id not in accessible_ids:
        class_id = accessible_ids[0] if accessible_ids else None

    subjects = []
    items = []
    if class_id:
        subjects = conn.execute(
            "SELECT s.* FROM subjects s JOIN class_subjects cs ON cs.subject_id=s.id "
            "WHERE cs.class_id=? ORDER BY s.name", (class_id,)
        ).fetchall()
        subject_id = request.args.get("subject_id", type=int)
        query = (
            "SELECT m.*, sub.name as subject_name, u.name as uploaded_by_name FROM materials m "
            "JOIN subjects sub ON sub.id=m.subject_id LEFT JOIN users u ON u.id=m.uploaded_by "
            "WHERE m.class_id=? AND m.session_id=?"
        )
        params = [class_id, session_id]
        if subject_id:
            query += " AND m.subject_id=?"
            params.append(subject_id)
        query += " ORDER BY m.uploaded_at DESC"
        items = conn.execute(query, params).fetchall()

    conn.close()
    return render_template(
        "materials.html", can_upload=can_upload, accessible_classes=accessible_classes,
        all_sessions=all_sessions, session_id=session_id, class_id=class_id,
        subjects=subjects, items=items, kinds=MATERIAL_KINDS,
        selected_subject_id=request.args.get("subject_id", type=int),
    )


@app.route("/materials/<int:material_id>/delete", methods=["POST"])
@login_required("admin", "sub_admin")
def delete_material(material_id):
    conn = get_db()
    m = conn.execute("SELECT * FROM materials WHERE id=? AND school_id=?", (material_id, current_school_id())).fetchone()
    if not m:
        conn.close()
        flash("Material not found.", "error")
        return redirect(url_for("materials"))
    if m["filename"]:
        p = os.path.join(MATERIALS_DIR, str(current_school_id()), m["filename"])
        if os.path.exists(p):
            os.remove(p)
    conn.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    log_audit(conn, session["role"], session.get("name"), "material_delete", m["title"], school_id=current_school_id())
    conn.commit()
    conn.close()
    flash("Material removed.", "success")
    return redirect(url_for("materials", session_id=m["session_id"], class_id=m["class_id"]))


def _authorize_material_for_download(conn, material_id):
    """Returns the material row if the current staff member is allowed to
    see it — the same class-access rule already used for results and
    broadsheets — or None otherwise, so the caller can refuse."""
    m = conn.execute("SELECT * FROM materials WHERE id=? AND school_id=?", (material_id, current_school_id())).fetchone()
    if not m:
        return None
    if not can_view_class_results(conn, session.get("role"), session.get("position"), session.get("user_id"), m["class_id"]):
        return None
    return m


@app.route("/materials/<int:material_id>/download")
@login_required()
def download_material(material_id):
    conn = get_db()
    m = _authorize_material_for_download(conn, material_id)
    conn.close()
    if not m:
        flash("You don't have access to that material.", "error")
        return redirect(url_for("materials"))
    if m["external_url"]:
        return redirect(m["external_url"])
    return send_from_directory(
        os.path.join(MATERIALS_DIR, str(current_school_id())), m["filename"],
        as_attachment=True, download_name=m["original_filename"] or m["filename"],
    )


# ---------- staff attendance ----------

@app.route("/admin/staff-attendance", methods=["GET", "POST"])
@login_required("admin", "sub_admin")
def staff_attendance():
    conn = get_db()
    school_id = current_school_id()
    staff = conn.execute(
        "SELECT * FROM users WHERE school_id=? ORDER BY role, name", (school_id,)
    ).fetchall()

    date_str = request.values.get("date", "").strip() or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        date_str = datetime.date.today().isoformat()

    if request.method == "POST":
        counts = {s: 0 for s in STAFF_ATTENDANCE_STATUSES}
        for member in staff:
            status = request.form.get(f"status_{member['id']}", "Present")
            if status not in STAFF_ATTENDANCE_STATUSES:
                status = "Present"
            counts[status] += 1
            conn.execute(
                "INSERT INTO staff_attendance (school_id, user_id, date, status, recorded_by, source) "
                "VALUES (?,?,?,?,?,'online') "
                "ON CONFLICT(user_id, date) DO UPDATE SET status=excluded.status, "
                "recorded_by=excluded.recorded_by, recorded_at=CURRENT_TIMESTAMP, source='online'",
                (school_id, member["id"], date_str, status, session["user_id"]),
            )
        conn.commit()
        log_audit(
            conn, session["role"], session.get("name"), "staff_attendance",
            f"{date_str}: " + ", ".join(f"{v} {k}" for k, v in counts.items() if v),
            school_id=school_id,
        )
        conn.commit()
        flash(f"Staff attendance saved for {format_dmy(date_str)}.", "success")
        conn.close()
        return redirect(url_for("staff_attendance", date=date_str))

    existing = {
        r["user_id"]: r["status"] for r in conn.execute(
            "SELECT user_id, status FROM staff_attendance WHERE school_id=? AND date=?",
            (school_id, date_str),
        ).fetchall()
    }
    conn.close()
    prev_day = (datetime.date.fromisoformat(date_str) - datetime.timedelta(days=1)).isoformat()
    next_day = (datetime.date.fromisoformat(date_str) + datetime.timedelta(days=1)).isoformat()
    return render_template(
        "staff_attendance.html", staff=staff, date_str=date_str, prev_day=prev_day, next_day=next_day,
        existing=existing, today=datetime.date.today().isoformat(), statuses=STAFF_ATTENDANCE_STATUSES,
        position_labels=POSITION_LABELS,
    )


@app.route("/admin/staff-attendance/history")
@login_required("admin", "sub_admin")
def staff_attendance_history():
    conn = get_db()
    school_id = current_school_id()
    today = datetime.date.today()
    start = request.args.get("start", "").strip() or today.replace(day=1).isoformat()
    end = request.args.get("end", "").strip() or today.isoformat()
    try:
        datetime.date.fromisoformat(start)
        datetime.date.fromisoformat(end)
    except ValueError:
        start, end = today.replace(day=1).isoformat(), today.isoformat()

    staff = conn.execute("SELECT * FROM users WHERE school_id=? ORDER BY role, name", (school_id,)).fetchall()
    summaries = []
    for member in staff:
        counts = {s: 0 for s in STAFF_ATTENDANCE_STATUSES}
        rows = conn.execute(
            "SELECT status, COUNT(*) as c FROM staff_attendance "
            "WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY status",
            (member["id"], start, end),
        ).fetchall()
        for r in rows:
            counts[r["status"]] = r["c"]
        summaries.append({"staff": member, "counts": counts, "total": sum(counts.values())})

    days = conn.execute(
        "SELECT date, "
        "SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present, "
        "SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) AS absent, "
        "SUM(CASE WHEN status='Late' THEN 1 ELSE 0 END) AS late, "
        "SUM(CASE WHEN status='Leave' THEN 1 ELSE 0 END) AS leave_count "
        "FROM staff_attendance WHERE school_id=? AND date BETWEEN ? AND ? GROUP BY date ORDER BY date DESC",
        (school_id, start, end),
    ).fetchall()
    conn.close()
    return render_template(
        "staff_attendance_history.html", summaries=summaries, days=days, start=start, end=end,
        position_labels=POSITION_LABELS,
    )


@app.route("/reports/staff_attendance")
@login_required("admin", "sub_admin")
def report_staff_attendance(fmt=None):
    fmt = request.args.get("format", "csv")
    conn = get_db()
    school_id = current_school_id()
    today = datetime.date.today()
    start = request.args.get("start", "").strip() or today.replace(day=1).isoformat()
    end = request.args.get("end", "").strip() or today.isoformat()
    try:
        datetime.date.fromisoformat(start)
        datetime.date.fromisoformat(end)
    except ValueError:
        start, end = today.replace(day=1).isoformat(), today.isoformat()

    staff = conn.execute("SELECT * FROM users WHERE school_id=? ORDER BY role, name", (school_id,)).fetchall()
    headers = ["Staff Name", "Role", "Present", "Absent", "Late", "Leave", "Days Recorded"]
    rows = []
    for member in staff:
        counts = {s: 0 for s in STAFF_ATTENDANCE_STATUSES}
        for r in conn.execute(
            "SELECT status, COUNT(*) as c FROM staff_attendance WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY status",
            (member["id"], start, end),
        ).fetchall():
            counts[r["status"]] = r["c"]
        role_label = POSITION_LABELS.get(member["position"], member["role"].replace("_", " ").title())
        rows.append([
            member["name"], role_label, counts["Present"], counts["Absent"], counts["Late"], counts["Leave"],
            sum(counts.values()),
        ])
    conn.close()
    fname = f"staff_attendance_{start}_to_{end}".replace("/", "-")
    return _send_report(fmt, "Staff Attendance", headers, rows, fname, subtitle=f"{format_dmy(start)} to {format_dmy(end)}")


@app.route("/offline")
@login_required()
def offline_queue_page():
    """The queue itself lives in this browser's localStorage, not the
    server — this page is just the JS-rendered view onto it, so it works
    the same regardless of which staff member's device it is."""
    return render_template("offline_queue.html")


@app.route("/api/offline/confirm_password", methods=["POST"])
@rate_limit(max_attempts=10, window_seconds=300)
def offline_confirm_password():
    """Used by Settings -> Offline Access when a person who is already logged
    in (from before this device was set up) wants to set up offline access
    without logging out and in: it checks the password they type really is
    their account password before the device encrypts anything with it."""
    if "user_id" not in session:
        return jsonify({"ok": False}), 401
    password = (request.get_json(silent=True) or {}).get("password", "")
    conn = get_db()
    user = conn.execute("SELECT password_hash, is_active FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    ok = bool(user and user["is_active"] and check_password_hash(user["password_hash"], password))
    return jsonify({"ok": ok}), (200 if ok else 403)


@app.route("/app")
@app.route("/offline-app")
def offline_app_shell():
    """The full offline-first app shell: PIN login (no server session
    needed at all) plus attendance/score-entry/registration/sync screens
    rendered entirely from this device's local IndexedDB copy of the
    data. Deliberately NOT behind @login_required — the whole point is
    that it has to open with zero connectivity, so it can't depend on a
    live Flask session. See OFFLINE_ARCHITECTURE.md."""
    school_name = None
    if "school_id" in session:
        conn = get_db()
        school = get_school(conn, session["school_id"])
        conn.close()
        school_name = school["name"] if school else None
    return render_template("offline_app.html", school_name=school_name)


# ---------- reports & analytics ----------

@app.route("/reports")
@login_required("admin", "sub_admin")
def reports_hub():
    conn = get_db()
    school_id = current_school_id()
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    all_terms = all_terms_for_school(conn)
    students = conn.execute(
        "SELECT s.*, c.name as class_name FROM students s JOIN classes c ON c.id=s.class_id "
        "WHERE c.school_id=? AND s.is_active=1 ORDER BY c.name, s.last_name", (school_id,)
    ).fetchall()
    conn.close()
    return render_template("reports_hub.html", classes=classes, all_terms=all_terms, students=students, student_full_name=student_full_name)


def _send_report(fmt, title, headers, rows, filename_base, subtitle=""):
    if fmt == "xlsx":
        buf = build_xlsx(title, headers, rows)
        return send_file(
            buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True, download_name=f"{filename_base}.xlsx",
        )
    if fmt == "pdf":
        conn = get_db()
        school = get_school(conn, current_school_id())
        logo_path = None
        if school and school["logo_filename"]:
            p = os.path.join(INSTANCE_DIR, school["logo_filename"])
            if os.path.exists(p):
                logo_path = p
        conn.close()
        buf = build_generic_table_pdf(
            title.upper(), subtitle, headers, rows,
            school_name=school["name"] if school else None, logo_path=logo_path,
            font_choice=school["pdf_font"] if school else "Helvetica",
        )
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=f"{filename_base}.pdf")
    buf = build_csv(headers, rows)
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name=f"{filename_base}.csv")


@app.route("/reports/broadsheet")
@login_required("admin", "sub_admin")
def report_broadsheet(fmt=None):
    fmt = request.args.get("format", "csv")
    class_id = request.args.get("class_id", type=int)
    conn = get_db()
    class_row = class_in_school(conn, class_id) if class_id else None
    if not class_row:
        conn.close()
        flash("Please choose a class.", "error")
        return redirect(url_for("reports_hub"))
    term = resolve_term(conn, request.args.get("term_id", type=int))
    subjects, rows_data = build_broadsheet_data(conn, class_id, term["id"])
    conn.close()

    headers = ["S/N", "Admission No. / Register No.", "Student Name"] + [s["name"] for s in subjects] + ["Total", "Average", "Position"]
    rows = []
    for i, r in enumerate(rows_data, start=1):
        row = [i, r["student"]["admission_no"], student_full_name(r["student"])]
        for subj in subjects:
            row.append(r["scores"][subj["id"]]["total"])
        row.extend([r["total"], r["average"], r["position"]])
        rows.append(row)

    fname = f"broadsheet_{class_row['name']}_{term['name']}".replace(" ", "_")
    return _send_report(fmt, "Broadsheet", headers, rows, fname)


@app.route("/reports/subject_performance")
@login_required("admin", "sub_admin")
def report_subject_performance(fmt=None):
    fmt = request.args.get("format", "csv")
    conn = get_db()
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("reports_hub"))

    school_id = current_school_id()
    classes = conn.execute("SELECT * FROM classes WHERE school_id=? ORDER BY name", (school_id,)).fetchall()
    headers = ["Class", "Subject", "Students with Scores", "Average", "Highest", "Lowest"]
    rows = []
    for class_row in classes:
        subjects, rows_data = build_broadsheet_data(conn, class_row["id"], term["id"])
        for subj in subjects:
            totals = [
                r["scores"][subj["id"]]["total"] for r in rows_data
                if r["scores"][subj["id"]]["total"] != "-"
            ]
            if totals:
                rows.append([
                    class_row["name"], subj["name"], len(totals),
                    round(sum(totals) / len(totals), 2), max(totals), min(totals),
                ])
            else:
                rows.append([class_row["name"], subj["name"], 0, "-", "-", "-"])
    conn.close()

    fname = f"subject_performance_{term['session_name']}_{term['name']}".replace(" ", "_").replace("/", "-")
    return _send_report(fmt, "Subject Performance", headers, rows, fname)


@app.route("/reports/attendance")
@login_required("admin", "sub_admin")
def report_attendance(fmt=None):
    fmt = request.args.get("format", "csv")
    conn = get_db()
    term = resolve_term(conn, request.args.get("term_id", type=int))
    if not term:
        conn.close()
        flash("No term set yet.", "error")
        return redirect(url_for("reports_hub"))
    class_id = request.args.get("class_id", type=int)

    school_id = current_school_id()
    query = (
        "SELECT s.*, c.name as class_name, sti.days_school_opened, sti.days_present, sti.days_absent "
        "FROM students s JOIN classes c ON c.id=s.class_id "
        "LEFT JOIN student_term_info sti ON sti.student_id=s.id AND sti.term_id=? "
        "WHERE c.school_id=? AND s.is_active=1"
    )
    params = [term["id"], school_id]
    if class_id:
        query += " AND c.id=?"
        params.append(class_id)
    query += " ORDER BY c.name, s.last_name"
    students = conn.execute(query, params).fetchall()
    conn.close()

    headers = ["Admission No. / Register No.", "Student Name", "Class", "Days School Opened", "Days Present", "Days Absent", "Attendance %"]
    rows = []
    for s in students:
        opened = s["days_school_opened"] or 0
        present = s["days_present"] or 0
        absent = s["days_absent"] or 0
        pct = round((present / opened) * 100, 1) if opened else "-"
        rows.append([s["admission_no"], student_full_name(s), s["class_name"], opened, present, absent, pct])

    fname = f"attendance_{term['session_name']}_{term['name']}".replace(" ", "_").replace("/", "-")
    return _send_report(fmt, "Attendance", headers, rows, fname)


@app.route("/reports/student_history")
@login_required("admin", "sub_admin")
def report_student_history(fmt=None):
    fmt = request.args.get("format", "csv")
    student_id = request.args.get("student_id", type=int)
    conn = get_db()
    student = student_in_school(conn, student_id) if student_id else None
    if not student:
        conn.close()
        flash("Please choose a student.", "error")
        return redirect(url_for("reports_hub"))

    terms = all_terms_for_school(conn)
    headers = ["Session", "Term", "Class / Arm", "Subject", "CA1", "CA2", "Exam", "Total", "Grade"]
    rows = []
    school_id = current_school_id()
    for term in terms:
        enrolled = conn.execute(
            "SELECT 1 FROM enrollments WHERE student_id=? AND session_id=?", (student_id, term["session_id"])
        ).fetchone()
        if not enrolled:
            continue
        class_id = student_class_for_term(conn, student_id, term["id"])
        class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()
        subjects = conn.execute(
            "SELECT s.* FROM subjects s JOIN class_subjects cs ON cs.subject_id=s.id WHERE cs.class_id=? ORDER BY s.name",
            (class_id,),
        ).fetchall()
        for subj in subjects:
            score = conn.execute(
                "SELECT * FROM scores WHERE student_id=? AND subject_id=? AND term_id=?",
                (student_id, subj["id"], term["id"]),
            ).fetchone()
            if score:
                total = compute_total(score["ca1"], score["ca2"], score["exam"], score["ca3"])
                grade, _ = grade_for(total, conn, school_id)
                rows.append([term["session_name"], term["name"], class_row["name"], subj["name"],
                             score["ca1"], score["ca2"], score["exam"], total, grade])
    conn.close()

    fname = f"academic_history_{student['admission_no']}".replace("/", "-")
    return _send_report(fmt, "Academic History", headers, rows, fname)




# ---------- parent portal ----------
# A separate, browser-only login (no offline access yet — same as the
# student portal below), scoped entirely to the parents/parent_students
# tables so it can never see or touch staff/student credentials.

def parent_login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "parent_id" not in session:
            return redirect(url_for("parent_login"))
        return f(*args, **kwargs)
    return wrapped


def _parent_own_child(conn, parent_id, student_id):
    """The requested student, only if linked to this parent account —
    the access boundary for every parent-facing route below."""
    return conn.execute(
        "SELECT s.* FROM students s JOIN parent_students ps ON ps.student_id=s.id "
        "WHERE ps.parent_id=? AND s.id=?", (parent_id, student_id)
    ).fetchone()


@app.route("/parent/login", methods=["GET", "POST"])
@rate_limit(max_attempts=10, window_seconds=300)
def parent_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        parent = conn.execute("SELECT * FROM parents WHERE username=? AND is_active=1", (username,)).fetchone()
        if parent and parent["password_hash"] and check_password_hash(parent["password_hash"], password):
            school = get_school(conn, parent["school_id"])
            conn.close()
            if school and school["activation_status"] != "active":
                flash("This school hasn't been activated yet.", "error")
                return render_template("parent_login.html")
            if school and school["is_archived"]:
                flash("This school's account has been archived. Contact the platform administrator.", "error")
                return render_template("parent_login.html")
            if school and school["is_suspended"]:
                flash("This school's account has been suspended. Contact the platform administrator.", "error")
                return render_template("parent_login.html")
            if g.portal_school and (not school or school["id"] != g.portal_school["id"]):
                flash(f"That account isn't registered under {g.portal_school['name']}'s portal.", "error")
                return render_template("parent_login.html")
            session.clear()
            session["parent_id"] = parent["id"]
            session["parent_name"] = parent["name"]
            session["role"] = "parent"
            session["school_id"] = school["id"] if school else None
            session["login_time"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
            return redirect(url_for("parent_dashboard"))
        conn.close()
        flash("Invalid username or password.", "error")
    return render_template("parent_login.html")


@app.route("/parent/logout")
def parent_logout():
    session.clear()
    return redirect(url_for("parent_login"))


@app.route("/parent/dashboard")
@parent_login_required
def parent_dashboard():
    conn = get_db()
    parent = conn.execute("SELECT * FROM parents WHERE id=?", (session["parent_id"],)).fetchone()
    if not parent:
        session.clear()
        conn.close()
        return redirect(url_for("parent_login"))
    children = conn.execute(
        "SELECT s.*, c.name as class_name FROM students s "
        "JOIN parent_students ps ON ps.student_id=s.id "
        "JOIN classes c ON c.id=s.class_id "
        "WHERE ps.parent_id=? ORDER BY s.first_name", (parent["id"],)
    ).fetchall()
    conn.close()
    return render_template(
        "parent_dashboard.html", parent=parent, children=children, student_full_name=student_full_name,
    )


@app.route("/parent/child/<int:student_id>")
@parent_login_required
def parent_child(student_id):
    conn = get_db()
    student = _parent_own_child(conn, session["parent_id"], student_id)
    if not student:
        conn.close()
        flash("That student isn't linked to your account.", "error")
        return redirect(url_for("parent_dashboard"))
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (student["class_id"],)).fetchone()
    published_terms = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id = terms.session_id "
        "JOIN enrollments e ON e.session_id = sessions.id "
        "WHERE e.student_id=? AND terms.is_published=1 "
        "ORDER BY sessions.id DESC, terms.id DESC",
        (student["id"],),
    ).fetchall()
    recent_attendance = conn.execute(
        "SELECT * FROM attendance_records WHERE student_id=? ORDER BY date DESC LIMIT 20", (student_id,)
    ).fetchall()
    conn.close()
    return render_template(
        "parent_child.html", student=student, class_row=class_row, published_terms=published_terms,
        recent_attendance=recent_attendance, student_full_name=student_full_name,
    )


@app.route("/parent/child/<int:student_id>/result/<int:term_id>")
@parent_login_required
def parent_child_result(student_id, term_id):
    conn = get_db()
    student = _parent_own_child(conn, session["parent_id"], student_id)
    if not student:
        conn.close()
        flash("That student isn't linked to your account.", "error")
        return redirect(url_for("parent_dashboard"))
    term = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id=terms.session_id WHERE terms.id=?", (term_id,)
    ).fetchone()
    if not term or not term["is_published"]:
        conn.close()
        flash("That term's result isn't published yet.", "error")
        return redirect(url_for("parent_child", student_id=student_id))
    enrolled = conn.execute(
        "SELECT 1 FROM enrollments WHERE student_id=? AND session_id=?", (student_id, term["session_id"])
    ).fetchone()
    if not enrolled:
        conn.close()
        flash("This student wasn't enrolled in that term.", "error")
        return redirect(url_for("parent_child", student_id=student_id))
    data = build_result_data(conn, student_id, term_id)
    all_traits = conn.execute(
        "SELECT * FROM skill_traits WHERE school_id=? ORDER BY category, name", (session["school_id"],)
    ).fetchall()
    conn.close()
    return render_template(
        "parent_child_result.html", term=term, student_full_name=student_full_name, all_traits=all_traits, **data
    )


@app.route("/parent/child/<int:student_id>/result/<int:term_id>/pdf")
@parent_login_required
def parent_child_result_pdf(student_id, term_id):
    conn = get_db()
    student = _parent_own_child(conn, session["parent_id"], student_id)
    if not student:
        conn.close()
        flash("That student isn't linked to your account.", "error")
        return redirect(url_for("parent_dashboard"))
    term = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id=terms.session_id WHERE terms.id=?", (term_id,)
    ).fetchone()
    if not term or not term["is_published"]:
        conn.close()
        flash("That term's result isn't published yet.", "error")
        return redirect(url_for("parent_child", student_id=student_id))
    enrolled = conn.execute(
        "SELECT 1 FROM enrollments WHERE student_id=? AND session_id=?", (student_id, term["session_id"])
    ).fetchone()
    if not enrolled:
        conn.close()
        flash("This student wasn't enrolled in that term.", "error")
        return redirect(url_for("parent_child", student_id=student_id))
    data = build_result_data(conn, student_id, term_id)
    school = get_school(conn, session["school_id"])
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p
    teacher_signature = None
    if data.get("teacher_signature_user"):
        u = data["teacher_signature_user"]
        teacher_signature = {"path": os.path.join(SIGNATURES_DIR, u["signature_filename"]), "name": u["name"]}
    principal_signature = None
    if data.get("principal_signature_user"):
        u = data["principal_signature_user"]
        principal_signature = {"path": os.path.join(SIGNATURES_DIR, u["signature_filename"]), "name": u["name"]}
    conn.close()
    buf = build_result_pdf(
        data, term, school_name=school["name"] if school else None,
        logo_path=logo_path, student_full_name=student_full_name,
        font_choice=school["pdf_font"] if school else "Helvetica",
        accent_color=school["result_accent_color"] if school and school["result_accent_color"] else "#1f3a5f",
        name_align=school["name_align"] if school else None,
        teacher_signature=teacher_signature, principal_signature=principal_signature,
    )
    filename = f"{student_full_name(data['student'])}_{term['name']}_Result.pdf".replace(" ", "_")
    return send_file(buf, mimetype="application/pdf", as_attachment=False, download_name=filename)


def student_login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "student_id" not in session:
            return redirect(url_for("student_login"))
        return f(*args, **kwargs)
    return wrapped


@app.route("/student/login", methods=["GET", "POST"])
@rate_limit(max_attempts=10, window_seconds=300)
def student_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        student = conn.execute(
            "SELECT * FROM students WHERE username=? AND is_active=1", (username,)
        ).fetchone()
        if student and student["password_hash"] and check_password_hash(student["password_hash"], password):
            class_row = conn.execute("SELECT school_id FROM classes WHERE id=?", (student["class_id"],)).fetchone()
            school = get_school(conn, class_row["school_id"]) if class_row else None
            conn.close()
            if school and school["activation_status"] != "active":
                flash("This school hasn't been activated yet.", "error")
                return render_template("student_login.html")
            if school and school["is_archived"]:
                flash("This school's account has been archived. Contact the platform administrator.", "error")
                return render_template("student_login.html")
            if school and school["is_suspended"]:
                flash("This school's account has been suspended. Contact the platform administrator.", "error")
                return render_template("student_login.html")
            if g.portal_school and (not school or school["id"] != g.portal_school["id"]):
                flash(f"That account isn't registered under {g.portal_school['name']}'s portal.", "error")
                return render_template("student_login.html")
            session.clear()
            session["student_id"] = student["id"]
            session["role"] = "student"
            session["school_id"] = school["id"] if school else None
            session["login_time"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
            return redirect(url_for("student_dashboard"))
        conn.close()
        flash("Invalid username or password.", "error")
    return render_template("student_login.html")


@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))


@app.route("/student/dashboard")
@student_login_required
def student_dashboard():
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
    if not student:
        session.clear()
        conn.close()
        return redirect(url_for("student_login"))
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (student["class_id"],)).fetchone()
    published_terms = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id = terms.session_id "
        "JOIN enrollments e ON e.session_id = sessions.id "
        "WHERE e.student_id=? AND terms.is_published=1 "
        "ORDER BY sessions.id DESC, terms.id DESC",
        (student["id"],),
    ).fetchall()
    conn.close()
    return render_template(
        "student_dashboard.html", student=student, class_row=class_row,
        published_terms=published_terms, student_full_name=student_full_name,
    )


@app.route("/student/notifications")
@student_login_required
def student_notifications():
    conn = get_db()
    notifications = get_visible_notifications(conn, "student", session.get("school_id"))
    if notifications:
        conn.execute(
            "UPDATE students SET last_notification_seen_id=? WHERE id=?",
            (notifications[0]["id"], session["student_id"]),
        )
        conn.commit()
    conn.close()
    return render_template("notifications_inbox.html", notifications=notifications)


@app.route("/student/materials")
@student_login_required
def student_materials():
    conn = get_db()
    student_id = session["student_id"]
    student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        session.clear()
        conn.close()
        return redirect(url_for("student_login"))

    # A student may only browse sessions they were actually enrolled in —
    # never an arbitrary session_id typed into the URL.
    enrolled_sessions = conn.execute(
        "SELECT sessions.* FROM sessions JOIN enrollments e ON e.session_id=sessions.id "
        "WHERE e.student_id=? ORDER BY sessions.id DESC", (student_id,)
    ).fetchall()
    active_session = conn.execute(
        "SELECT * FROM sessions WHERE school_id=? AND is_active=1", (session.get("school_id"),)
    ).fetchone()
    requested_session_id = request.args.get("session_id", type=int)
    valid_ids = [s["id"] for s in enrolled_sessions]
    if requested_session_id in valid_ids:
        session_id = requested_session_id
    elif active_session and active_session["id"] in valid_ids:
        session_id = active_session["id"]
    elif valid_ids:
        session_id = valid_ids[0]
    else:
        session_id = None

    class_id = student["class_id"]
    if session_id:
        enrollment = conn.execute(
            "SELECT class_id FROM enrollments WHERE student_id=? AND session_id=?", (student_id, session_id)
        ).fetchone()
        if enrollment:
            class_id = enrollment["class_id"]

    subjects = []
    items = []
    if session_id and class_id:
        subjects = conn.execute(
            "SELECT s.* FROM subjects s JOIN class_subjects cs ON cs.subject_id=s.id "
            "WHERE cs.class_id=? ORDER BY s.name", (class_id,)
        ).fetchall()
        items = conn.execute(
            "SELECT m.*, sub.name as subject_name FROM materials m "
            "JOIN subjects sub ON sub.id=m.subject_id "
            "WHERE m.class_id=? AND m.session_id=? ORDER BY sub.name, m.uploaded_at DESC",
            (class_id, session_id),
        ).fetchall()
    class_row = conn.execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone() if class_id else None
    conn.close()
    return render_template(
        "student_materials.html", enrolled_sessions=enrolled_sessions, session_id=session_id,
        class_row=class_row, subjects=subjects, items=items,
    )


@app.route("/student/materials/<int:material_id>/download")
@student_login_required
def student_download_material(material_id):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
    if not student:
        conn.close()
        return redirect(url_for("student_login"))
    m = conn.execute("SELECT * FROM materials WHERE id=? AND school_id=?", (material_id, session.get("school_id"))).fetchone()
    # A student's class for that material's OWN session is the access
    # boundary — not just their current class — so materials from before a
    # promotion stay reachable, but a material from any other class
    # (including another category/arm at the same level) never is.
    my_class_for_that_session = student_class_for_session(conn, student["id"], m["session_id"]) if m else None
    conn.close()
    if not m or my_class_for_that_session != m["class_id"]:
        flash("That material isn't available to you.", "error")
        return redirect(url_for("student_materials"))
    if m["external_url"]:
        return redirect(m["external_url"])
    return send_from_directory(
        os.path.join(MATERIALS_DIR, str(session["school_id"])), m["filename"],
        as_attachment=True, download_name=m["original_filename"] or m["filename"],
    )


@app.route("/student/result/<int:term_id>")
@student_login_required
def student_result(term_id):
    conn = get_db()
    student_id = session["student_id"]
    term = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id=terms.session_id WHERE terms.id=?", (term_id,)
    ).fetchone()
    if not term or not term["is_published"]:
        conn.close()
        flash("That term's result isn't published yet.", "error")
        return redirect(url_for("student_dashboard"))
    enrolled = conn.execute(
        "SELECT 1 FROM enrollments WHERE student_id=? AND session_id=?", (student_id, term["session_id"])
    ).fetchone()
    if not enrolled:
        conn.close()
        flash("You weren't enrolled in that term.", "error")
        return redirect(url_for("student_dashboard"))
    data = build_result_data(conn, student_id, term_id)
    all_traits = conn.execute(
        "SELECT * FROM skill_traits WHERE school_id=? ORDER BY category, name", (session["school_id"],)
    ).fetchall()
    conn.close()
    return render_template(
        "student_result.html", term=term, student_full_name=student_full_name, all_traits=all_traits, **data
    )


@app.route("/student/result/<int:term_id>/pdf")
@student_login_required
def student_result_pdf(term_id):
    conn = get_db()
    student_id = session["student_id"]
    term = conn.execute(
        "SELECT terms.*, sessions.name as session_name FROM terms "
        "JOIN sessions ON sessions.id=terms.session_id WHERE terms.id=?", (term_id,)
    ).fetchone()
    if not term or not term["is_published"]:
        conn.close()
        flash("That term's result isn't published yet.", "error")
        return redirect(url_for("student_dashboard"))
    enrolled = conn.execute(
        "SELECT 1 FROM enrollments WHERE student_id=? AND session_id=?", (student_id, term["session_id"])
    ).fetchone()
    if not enrolled:
        conn.close()
        flash("You weren't enrolled in that term.", "error")
        return redirect(url_for("student_dashboard"))
    data = build_result_data(conn, student_id, term_id)
    school = get_school(conn, session["school_id"])
    logo_path = None
    if school and school["logo_filename"]:
        p = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(p):
            logo_path = p
    conn.close()
    buf = build_result_pdf(data, term, school_name=school["name"] if school else None,
                            logo_path=logo_path, student_full_name=student_full_name,
                            font_choice=school["pdf_font"] if school else "Helvetica")
    fname = f"result_{data['student']['admission_no']}_{term['name']}.pdf".replace(" ", "_").replace("/", "-")
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=fname)


# ---------- platform (super admin) tier ----------
#
# A Super Admin oversees the whole platform, not any one school. Their login
# is completely separate from school staff/students (platform_admins table),
# and their access to school data is deliberately limited to metadata and
# moderation (counts, status, suspend/activate/delete) rather than browsing
# actual student names/scores — that stays isolated to each school's own
# staff, per the "strict data isolation between schools" requirement.

def platform_admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "platform_admin_id" not in session:
            return redirect(url_for("platform_login"))
        return f(*args, **kwargs)
    return wrapped


@app.route("/platform/login", methods=["GET", "POST"])
@rate_limit(max_attempts=10, window_seconds=300)
def platform_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        admin = conn.execute("SELECT * FROM platform_admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["platform_admin_id"] = admin["id"]
            session["platform_admin_name"] = admin["name"]
            log_audit(conn, "platform_admin", admin["name"], "login")
            conn.close()
            return redirect(url_for("platform_dashboard"))
        conn.close()
        flash("Invalid username or password.", "error")
    return render_template("platform_login.html")


@app.route("/platform/logout")
def platform_logout():
    session.clear()
    return redirect(url_for("platform_login"))


@app.route("/platform/dashboard")
@platform_admin_required
def platform_dashboard():
    conn = get_db()
    stats = {
        "schools_total": conn.execute("SELECT COUNT(*) c FROM schools").fetchone()["c"],
        "schools_active": conn.execute("SELECT COUNT(*) c FROM schools WHERE is_suspended=0").fetchone()["c"],
        "schools_suspended": conn.execute("SELECT COUNT(*) c FROM schools WHERE is_suspended=1").fetchone()["c"],
        "students": conn.execute("SELECT COUNT(*) c FROM students WHERE is_active=1").fetchone()["c"],
        "teachers": conn.execute("SELECT COUNT(*) c FROM users WHERE role='teacher'").fetchone()["c"],
        "admins": conn.execute("SELECT COUNT(*) c FROM users WHERE role IN ('admin','sub_admin')").fetchone()["c"],
        "classes": conn.execute("SELECT COUNT(*) c FROM classes").fetchone()["c"],
        "published_terms": conn.execute("SELECT COUNT(*) c FROM terms WHERE is_published=1").fetchone()["c"],
    }
    recent_audit = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return render_template("platform_dashboard.html", stats=stats, recent_audit=recent_audit)


@app.route("/platform/schools")
@platform_admin_required
def platform_schools():
    conn = get_db()
    schools = conn.execute(
        "SELECT s.*, "
        "(SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role IN ('admin','sub_admin')) as admin_count, "
        "(SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role='teacher') as teacher_count, "
        "(SELECT COUNT(*) FROM classes c WHERE c.school_id=s.id) as class_count, "
        "(SELECT COUNT(*) FROM students st JOIN classes c ON c.id=st.class_id WHERE c.school_id=s.id AND st.is_active=1) as student_count "
        "FROM schools s ORDER BY s.name"
    ).fetchall()
    code_status = {s["id"]: current_activation_code_status(conn, s["id"]) for s in schools}
    conn.close()
    return render_template("platform_schools.html", schools=schools, code_status=code_status)


@app.route("/platform/schools/new", methods=["GET", "POST"])
@platform_admin_required
def platform_new_school():
    if request.method == "POST":
        school_name = request.form.get("school_name", "").strip()
        registered_email = request.form.get("registered_email", "").strip()
        admin_name = request.form.get("admin_name", "").strip()
        admin_username = request.form.get("admin_username", "").strip()

        errors = []
        if not school_name or not registered_email or not admin_name or not admin_username:
            errors.append("Please fill in every field.")
        if registered_email and ("@" not in registered_email or "." not in registered_email.split("@")[-1]):
            errors.append("Please provide a valid school email address.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("platform_new_school.html")

        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO schools (name, registered_email, activation_status) VALUES (?,?,'pending')",
                (school_name, registered_email),
            )
            school_id = cur.lastrowid
            # No usable password yet — the School Admin sets a real one during activation.
            placeholder_hash = generate_password_hash(secrets.token_urlsafe(32))
            conn.execute(
                "INSERT INTO users (school_id, name, username, password_hash, role) VALUES (?,?,?,?, 'admin')",
                (school_id, admin_name, admin_username, placeholder_hash),
            )
            code, expires_at = generate_activation_code(conn, school_id, created_by=session.get("platform_admin_name"))
            log_audit(conn, "platform_admin", session.get("platform_admin_name"), "onboard_school",
                      details=f"Onboarded '{school_name}' ({registered_email})", school_id=school_id)
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            conn.close()
            if "users.username" in str(e):
                flash("That admin username is already taken — please choose another.", "error")
            else:
                flash(f"Couldn't create the school: {e}", "error")
            return render_template("platform_new_school.html")

        sent, msg = send_platform_email(
            registered_email, f"Activate {school_name} on School Result System",
            f"Your school has been onboarded.\n\nActivation code: {code}\n"
            f"This code expires {format_dmy(expires_at)} and can only be used once.\n\n"
            f"Visit the Activate School page and enter this code (with admin username '{admin_username}') "
            "to finish setting up your account.",
        )
        conn.close()
        flash(f"'{school_name}' onboarded. Activation code: {code} (expires {format_dmy(expires_at)}).", "success")
        if not sent:
            flash(f"Couldn't email the code automatically ({msg}) — share the code above with the school directly.", "error")
        return redirect(url_for("platform_schools"))

    return render_template("platform_new_school.html")


@app.route("/platform/schools/<int:school_id>/regenerate_code", methods=["POST"])
@platform_admin_required
def platform_regenerate_code(school_id):
    conn = get_db()
    school = get_school(conn, school_id)
    if not school:
        conn.close()
        flash("School not found.", "error")
        return redirect(url_for("platform_schools"))
    code, expires_at = generate_activation_code(conn, school_id, created_by=session.get("platform_admin_name"))
    log_audit(conn, "platform_admin", session.get("platform_admin_name"), "regenerate_activation_code",
              details=f"Regenerated code for '{school['name']}'", school_id=school_id)
    conn.commit()
    sent, msg = (False, "No registered email on file.")
    if school["registered_email"]:
        sent, msg = send_platform_email(
            school["registered_email"], f"New activation code for {school['name']}",
            f"A new activation code has been issued: {code}\nThis code expires {format_dmy(expires_at)} "
            "and invalidates any previous code.",
        )
    conn.close()
    flash(f"New activation code: {code} (expires {format_dmy(expires_at)}).", "success")
    if not sent:
        flash(f"Couldn't email the code automatically ({msg}) — share the code above with the school directly.", "error")
    return redirect(url_for("platform_schools"))


@app.route("/platform/schools/<int:school_id>/archive", methods=["POST"])
@platform_admin_required
def platform_archive_school(school_id):
    conn = get_db()
    school = get_school(conn, school_id)
    if school:
        conn.execute("UPDATE schools SET is_archived=1 WHERE id=?", (school_id,))
        log_audit(conn, "platform_admin", session.get("platform_admin_name"), "archive_school",
                  details=f"Archived '{school['name']}'", school_id=school_id)
        conn.commit()
        flash(f"'{school['name']}' has been archived. Its staff and students can no longer log in.", "success")
    conn.close()
    return redirect(url_for("platform_schools"))


@app.route("/platform/schools/<int:school_id>/unarchive", methods=["POST"])
@platform_admin_required
def platform_unarchive_school(school_id):
    conn = get_db()
    school = get_school(conn, school_id)
    if school:
        conn.execute("UPDATE schools SET is_archived=0 WHERE id=?", (school_id,))
        log_audit(conn, "platform_admin", session.get("platform_admin_name"), "unarchive_school",
                  details=f"Unarchived '{school['name']}'", school_id=school_id)
        conn.commit()
        flash(f"'{school['name']}' has been unarchived.", "success")
    conn.close()
    return redirect(url_for("platform_schools"))


@app.route("/platform/schools/<int:school_id>/force_logout", methods=["POST"])
@platform_admin_required
def platform_force_logout_school(school_id):
    conn = get_db()
    school = get_school(conn, school_id)
    if school:
        conn.execute("UPDATE schools SET force_logout_at=? WHERE id=?",
                     (datetime.datetime.utcnow().isoformat(timespec="seconds"), school_id))
        log_audit(conn, "platform_admin", session.get("platform_admin_name"), "force_logout_school",
                  details=f"Forced logout for all of '{school['name']}'s users", school_id=school_id)
        conn.commit()
        flash(f"All of '{school['name']}'s staff and students will be signed out on their next action.", "success")
    conn.close()
    return redirect(url_for("platform_schools"))


@app.route("/activate", methods=["GET", "POST"])
@rate_limit(max_attempts=8, window_seconds=600)
def activate_school():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND role='admin'", (username,)).fetchone()
        if not user:
            conn.close()
            flash("No pending school admin account found with that username.", "error")
            return render_template("activate.html")
        school = get_school(conn, user["school_id"])
        if school["activation_status"] == "active":
            conn.close()
            flash("This school is already active — please log in instead.", "error")
            return redirect(url_for("login"))
        if len(password) < 6:
            conn.close()
            flash("Password must be at least 6 characters.", "error")
            return render_template("activate.html")
        if password != confirm:
            conn.close()
            flash("Password and confirmation don't match.", "error")
            return render_template("activate.html")

        ok, reason = verify_activation_code(conn, school["id"], code)
        if not ok:
            conn.close()
            flash(reason, "error")
            return render_template("activate.html")

        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password), user["id"]))
        conn.execute(
            "UPDATE schools SET activation_status='active', activated_at=? WHERE id=?",
            (datetime.datetime.utcnow().isoformat(timespec="seconds"), school["id"]),
        )
        log_audit(conn, "admin", user["name"], "school_activated", details=f"'{school['name']}' activated", school_id=school["id"])
        conn.commit()
        conn.close()

        session.clear()
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]
        session["position"] = user["position"]
        session["school_id"] = user["school_id"]
        session["login_time"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
        flash(f"Welcome! '{school['name']}' is now active — you can finish setting up your school profile.", "success")
        return redirect(url_for("admin_school"))

    return render_template("activate.html")


@app.route("/platform/schools/export")
@platform_admin_required
def platform_schools_export():
    fmt = request.args.get("format", "csv")
    conn = get_db()
    schools = conn.execute(
        "SELECT s.*, "
        "(SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role IN ('admin','sub_admin')) as admin_count, "
        "(SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role='teacher') as teacher_count, "
        "(SELECT COUNT(*) FROM classes c WHERE c.school_id=s.id) as class_count, "
        "(SELECT COUNT(*) FROM students st JOIN classes c ON c.id=st.class_id WHERE c.school_id=s.id AND st.is_active=1) as student_count "
        "FROM schools s ORDER BY s.name"
    ).fetchall()
    conn.close()

    headers = ["School ID", "School", "Registered Email", "Activation Status", "Account Status",
               "Admins", "Teachers", "Classes", "Students", "Date Registered", "Date Activated"]
    rows = [
        [s["id"], s["name"], s["registered_email"] or "-",
         "Active" if s["activation_status"] == "active" else "Pending",
         "Archived" if s["is_archived"] else ("Suspended" if s["is_suspended"] else "Active"),
         s["admin_count"], s["teacher_count"], s["class_count"], s["student_count"],
         format_dmy(s["created_at"]), format_dmy(s["activated_at"]) if s["activated_at"] else "-"]
        for s in schools
    ]
    return _send_report(fmt, "Schools", headers, rows, "platform_schools_summary")


@app.route("/platform/schools/<int:school_id>/suspend", methods=["POST"])
@platform_admin_required
def platform_suspend_school(school_id):
    conn = get_db()
    school = get_school(conn, school_id)
    if school:
        conn.execute("UPDATE schools SET is_suspended=1 WHERE id=?", (school_id,))
        revoke_device_credentials_for_school(conn, school_id, reason="school suspended")
        log_audit(conn, "platform_admin", session.get("platform_admin_name"), "suspend_school",
                  details=f"Suspended '{school['name']}'", school_id=school_id)
        conn.commit()
        flash(f"'{school['name']}' has been suspended. Its staff and students can no longer log in.", "success")
    conn.close()
    return redirect(url_for("platform_schools"))


@app.route("/platform/schools/<int:school_id>/activate", methods=["POST"])
@platform_admin_required
def platform_activate_school(school_id):
    conn = get_db()
    school = get_school(conn, school_id)
    if school:
        conn.execute("UPDATE schools SET is_suspended=0 WHERE id=?", (school_id,))
        log_audit(conn, "platform_admin", session.get("platform_admin_name"), "activate_school",
                  details=f"Activated '{school['name']}'", school_id=school_id)
        conn.commit()
        flash(f"'{school['name']}' has been reactivated.", "success")
    conn.close()
    return redirect(url_for("platform_schools"))


@app.route("/platform/schools/<int:school_id>/delete", methods=["POST"])
@platform_admin_required
def platform_delete_school(school_id):
    if request.form.get("confirm_text", "").strip().upper() != "DELETE":
        flash("You must type DELETE exactly to confirm.", "error")
        return redirect(url_for("platform_schools"))

    conn = get_db()
    school = get_school(conn, school_id)
    if not school:
        conn.close()
        flash("School not found.", "error")
        return redirect(url_for("platform_schools"))

    school_name = school["name"]
    class_ids = [r["id"] for r in conn.execute("SELECT id FROM classes WHERE school_id=?", (school_id,)).fetchall()]
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        student_ids = [r["id"] for r in conn.execute(
            f"SELECT id FROM students WHERE class_id IN ({placeholders})", class_ids
        ).fetchall()]
        if student_ids:
            sp = ",".join("?" * len(student_ids))
            conn.execute(f"DELETE FROM student_skill_ratings WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM student_term_info WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM score_history WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM scores WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM enrollments WHERE student_id IN ({sp})", student_ids)
            conn.execute(f"DELETE FROM students WHERE id IN ({sp})", student_ids)
        conn.execute(f"DELETE FROM class_subjects WHERE class_id IN ({placeholders})", class_ids)
        conn.execute(f"DELETE FROM timetable_entries WHERE class_id IN ({placeholders})", class_ids)
        conn.execute(f"DELETE FROM classes WHERE id IN ({placeholders})", class_ids)
    conn.execute("DELETE FROM timetable_periods WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM subjects WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM skill_traits WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM grade_scale WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM grading_config WHERE school_id=?", (school_id,))
    term_ids = [r["id"] for r in conn.execute(
        "SELECT terms.id FROM terms JOIN sessions ON sessions.id=terms.session_id WHERE sessions.school_id=?",
        (school_id,),
    ).fetchall()]
    if term_ids:
        tp = ",".join("?" * len(term_ids))
        conn.execute(f"DELETE FROM terms WHERE id IN ({tp})", term_ids)
    conn.execute("DELETE FROM sessions WHERE school_id=?", (school_id,))
    conn.execute("DELETE FROM users WHERE school_id=?", (school_id,))
    if school["logo_filename"]:
        old_path = os.path.join(INSTANCE_DIR, school["logo_filename"])
        if os.path.exists(old_path):
            os.remove(old_path)
    conn.execute("DELETE FROM schools WHERE id=?", (school_id,))
    log_audit(conn, "platform_admin", session.get("platform_admin_name"), "delete_school",
              details=f"Permanently deleted '{school_name}'", school_id=None)
    conn.commit()
    conn.close()
    flash(f"'{school_name}' and all its data have been permanently deleted.", "success")
    return redirect(url_for("platform_schools"))


@app.route("/platform/users")
@platform_admin_required
def platform_users():
    conn = get_db()
    school_filter = request.args.get("school_id", type=int)
    schools = conn.execute("SELECT * FROM schools ORDER BY name").fetchall()
    query = (
        "SELECT u.*, s.name as school_name FROM users u JOIN schools s ON s.id=u.school_id"
    )
    params = ()
    if school_filter:
        query += " WHERE u.school_id=?"
        params = (school_filter,)
    query += " ORDER BY s.name, u.role, u.name"
    users = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("platform_users.html", users=users, schools=schools, school_filter=school_filter)


@app.route("/platform/users/<int:user_id>/reset_password", methods=["POST"])
@platform_admin_required
def platform_reset_user_password(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash("User not found.", "error")
        return redirect(url_for("platform_users"))
    new_password = secrets.token_urlsafe(6)
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user_id))
    log_audit(conn, "platform_admin", session.get("platform_admin_name"), "reset_user_password",
              details=f"Reset password for {user['name']} ({user['username']})", school_id=user["school_id"])
    conn.commit()
    conn.close()
    flash(f"Password reset for {user['name']} (username: {user['username']}). New temporary password: {new_password}", "success")
    return redirect(url_for("platform_users"))


@app.route("/platform/audit")
@platform_admin_required
def platform_audit():
    conn = get_db()
    logs = conn.execute(
        "SELECT audit_log.*, schools.name as school_name FROM audit_log "
        "LEFT JOIN schools ON schools.id = audit_log.school_id "
        "ORDER BY audit_log.id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return render_template("platform_audit.html", logs=logs)


@app.route("/platform/notifications", methods=["GET", "POST"])
@platform_admin_required
def platform_notifications():
    conn = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        target_role = request.form.get("target_role", "all")
        if target_role not in ("all", "admin", "teacher", "student"):
            target_role = "all"
        school_id = request.form.get("school_id") or None  # blank = all schools

        if not title or not message:
            flash("Please fill in both a title and a message.", "error")
        else:
            conn.execute(
                "INSERT INTO notifications (sender_label, school_id, target_role, title, message) VALUES (?,?,?,?,?)",
                (f"Platform Admin: {session.get('platform_admin_name')}", school_id, target_role, title, message),
            )
            school_row = get_school(conn, school_id) if school_id else None
            log_audit(
                conn, "platform_admin", session.get("platform_admin_name"), "send_notification",
                details=f"'{title}' to {target_role} in {school_row['name'] if school_row else 'ALL schools'}",
                school_id=school_id,
            )
            conn.commit()
            flash("Notification sent.", "success")
            conn.close()
            return redirect(url_for("platform_notifications"))

    schools = conn.execute("SELECT * FROM schools ORDER BY name").fetchall()
    sent = conn.execute(
        "SELECT n.*, s.name as school_name FROM notifications n LEFT JOIN schools s ON s.id=n.school_id "
        "ORDER BY n.id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return render_template("platform_notifications.html", schools=schools, sent=sent)


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=5050, debug=debug_mode)
