"""End-to-end scenarios for the V81 requirement: Phase 4 of the ninth requirements document
("Consolidated Development Specification"), "One Unified Login Form for All User Roles" + "No
School Selection on the Login Form."

Audited gap: the app already had ONE combined form for staff + parents (/login), but students had
their own separate page (/student/login) and the Platform/Super Admin had another (/platform/login)
-- both explicitly linked from, or reachable alongside, /login, contradicting the spec's "Do not
create separate login pages for individual user roles or schools."

Fixed: /login now ALSO tries a student account, then a platform-admin account, before giving the
same generic failure -- via two new functions, _try_student_login and _try_platform_login, that
contain the exact same matching/authorization logic the old dedicated pages used (constant-time
handling for an unknown identifier, per-student lockout, the "two schools share this number"
disambiguation, the first-login class-code requirement, every school-state check) with nothing
weakened or skipped. /student/login and /platform/login no longer have a page of their own -- GET
on either now serves the exact same unified template (not a second copy, not even a redirect round
trip) -- but POST still works on both, unchanged, for any old bookmark or cached form.

Deliberately NOT built this round: a public link to /platform/login, or a "Platform Admin" option
anywhere on the unified form. That portal was always deliberately unlisted ("not listed on the
public school login screen"), consistent with the spec's own "Super Admin... hidden from all
public-facing screens" expectation audited back in the third requirements document -- a platform
admin still signs in through the exact same /login form, just without it being advertised.

Run: python tests/v81_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v81_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash
from flask.testing import FlaskClient


class ListDataClient(FlaskClient):
    def open(self, *args, **kwargs):
        if isinstance(kwargs.get("data"), list):
            kwargs["data"] = MultiDict(kwargs["data"])
        return super().open(*args, **kwargs)


A.app.test_client_class = ListDataClient
A.app.config["TESTING"] = False
A.app.config["PROPAGATE_EXCEPTIONS"] = False
logging.disable(logging.CRITICAL)

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print("FAIL:", name, str(detail)[:400])


def html(r):
    return r.get_data(as_text=True)


def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    return m.group(1) if m else None


def post(c, path, data=None, page=None):
    d = dict(data or {})
    d["csrf_token"] = tok(c, page or path)
    return c.post(path, data=d)


def db():
    return get_db()


def run(sql, args=()):
    c = db()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def one(sql, args=()):
    c = db()
    try:
        return c.execute(sql, args).fetchone()
    finally:
        c.close()


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
student_row = c0.execute("SELECT id, admission_no, class_id FROM students LIMIT 1").fetchone()
c0.execute(
    "UPDATE students SET password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP, "
    "failed_logins=0, locked_until=NULL WHERE id=?",
    (pw, student_row["id"]),
)
c0.execute("INSERT INTO platform_admins(name,username,password_hash) VALUES('Root','root',?)", (pw,))
c0.commit()
c0.close()

def _strip_csrf(h):
    return re.sub(r'name="csrf_token" value="[^"]*"', "", h)


# ---------------------------------------------------------- 1) no separate pages: GET redirects/renders the SAME form
# (one client throughout, so the CSRF token -- the only thing that legitimately differs per
# request -- stays the same across all three fetches; it's stripped too, belt and braces.)
same_client = A.app.test_client()
lg = html(same_client.get("/login"))
sl = html(same_client.get("/student/login"))
pl = html(same_client.get("/platform/login"))
check("the unified /login form now mentions students too", "students" in lg.lower() and 'name="class_code"' in lg)
check("/student/login no longer has its own distinct form -- it serves the SAME unified page", _strip_csrf(sl) == _strip_csrf(lg))
check("/platform/login no longer has its own distinct form -- it serves the SAME unified page", _strip_csrf(pl) == _strip_csrf(lg))
check("there is still no visible link to /platform/login anywhere on the unified page (stays unlisted)", "/platform/login" not in lg)
check("the unified page still has no school selector/dropdown anywhere", 'name="school_id"' not in lg and "<select" not in lg)

# ---------------------------------------------------------- 2) a student can sign in through the ONE unified /login form
c = A.app.test_client()
r = post(c, "/login", {"username": student_row["admission_no"], "password": "Pass1234", "class_code": "", "school_code": ""}, "/login")
check("a student can sign in with the unified form (one field set, no separate page)", r.status_code == 302 and "/student/dashboard" in r.headers.get("Location", ""), (r.status_code, r.headers.get("Location")))
with c.session_transaction() as s:
    check("the session is a genuine student session afterward", s.get("role") == "student" and s.get("student_id") == student_row["id"])

# ---------------------------------------------------------- 3) a platform admin can sign in through the SAME unified form
c2 = A.app.test_client()
r2 = post(c2, "/login", {"username": "root", "password": "Pass1234"}, "/login")
check("a platform admin can sign in through the SAME unified /login form (no separate page needed)",
      r2.status_code == 302 and "/platform/dashboard" in r2.headers.get("Location", ""), (r2.status_code, r2.headers.get("Location")))
with c2.session_transaction() as s:
    check("...and gets a genuine platform-admin session, with NO school context at all", s.get("platform_admin_id") is not None and "school_id" not in s)

# ---------------------------------------------------------- 4) the old POST endpoints still work (backward compatible for old bookmarks/forms)
c3 = A.app.test_client()
r3 = post(c3, "/student/login", {"identifier": student_row["admission_no"], "password": "Pass1234", "class_code": ""}, "/student/login")
check("POSTing to the old /student/login URL with its original field names still works", r3.status_code == 302 and "/student/dashboard" in r3.headers.get("Location", ""))

c4 = A.app.test_client()
r4 = post(c4, "/platform/login", {"username": "root", "password": "Pass1234"}, "/platform/login")
check("POSTing to the old /platform/login URL still works", r4.status_code == 302 and "/platform/dashboard" in r4.headers.get("Location", ""))

# ---------------------------------------------------------- 5) wrong credentials still fail the same way, through either route
c5 = A.app.test_client()
r5 = post(c5, "/login", {"username": student_row["admission_no"], "password": "WrongPass1", "class_code": "", "school_code": ""}, "/login")
check("a wrong password for a real student still fails (no accidental backdoor)", "Invalid" in html(r5) or r5.status_code == 200)
with c5.session_transaction() as s:
    check("...and no session was created", "student_id" not in s)

c6 = A.app.test_client()
r6 = post(c6, "/login", {"username": "root", "password": "WrongPass1"}, "/login")
with c6.session_transaction() as s:
    check("a wrong password for the platform admin also fails cleanly", "platform_admin_id" not in s)

# ---------------------------------------------------------- 6) class-code behaviour is unchanged through the unified form:
#    a normal sign-in needs no code at all (it's for enrolment/linking, not authentication -- the
#    same rule tests/v61_scenarios.py already established for the old dedicated page), but a WRONG
#    code is still refused rather than silently ignored.
cls_id = student_row["class_id"]
run("DELETE FROM class_login_codes WHERE class_id=?", (cls_id,))
code = "ABC123"
tenant_id = one("SELECT tenant_id FROM schools WHERE id=1")["tenant_id"]
run("INSERT INTO class_login_codes (class_id, school_id, tenant_id, code, status) VALUES (?, 1, ?, ?, 'active')", (cls_id, tenant_id, code))
c7 = A.app.test_client()
r7 = post(c7, "/login", {"username": student_row["admission_no"], "password": "Pass1234", "class_code": "", "school_code": ""}, "/login")
with c7.session_transaction() as s:
    check("a normal sign-in through the unified form needs no class code at all", s.get("student_id") == student_row["id"], r7.status_code)
c8 = A.app.test_client()
r8 = post(c8, "/login", {"username": student_row["admission_no"], "password": "Pass1234", "class_code": "WRONGCODE", "school_code": ""}, "/login")
with c8.session_transaction() as s:
    check("...but typing a WRONG class code is still refused, not silently ignored", "student_id" not in s, r8.status_code)
c9 = A.app.test_client()
r9 = post(c9, "/login", {"username": student_row["admission_no"], "password": "Pass1234", "class_code": code, "school_code": ""}, "/login")
with c9.session_transaction() as s:
    check("the CORRECT class code is harmless on an already-first-logged-in student", s.get("student_id") == student_row["id"])

# ---------------------------------------------------------- 7) staff/parent logins are completely unaffected
ADMIN = A.app.test_client()
rA = post(ADMIN, "/login", {"username": "admin", "password": "Pass1234", "school_code": ""}, "/login")
check("an ordinary staff login through the unified form still works exactly as before", rA.status_code == 302 and "/dashboard" in rA.headers.get("Location", ""))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
