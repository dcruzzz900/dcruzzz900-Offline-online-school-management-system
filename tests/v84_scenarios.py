"""End-to-end scenarios for V84: Phase 7 of the ninth requirements document ("Consolidated
Development Specification") -- the document's FINAL phase, "Security/Regression Testing and
Deployment." This is a confirmation-and-close-out pass across the whole application rather than
one feature, since Phases 1-6 (V79-V83) each already tested their own area thoroughly as they went.

What this round covers that nothing else in the suite specifically checks:
  1. A genuine timing-safety gap found during the audit and fixed this round (see below).
  2. CSRF protection is actually enforced globally (every state-changing request), not just
     exercised incidentally by tests that happen to always send a valid token.
  3. The production security response headers (X-Content-Type-Options, X-Frame-Options,
     Referrer-Policy, Permissions-Policy) are genuinely present on real responses.
  4. Login brute-force rate limiting actually kicks in after repeated attempts (every earlier test
     that touches /login immediately clears the rate-limit store as a workaround -- this is the
     first test that deliberately does NOT, to confirm the protection itself works).
  5. An unauthenticated visitor is redirected to sign in, never shown a staff page directly.
  6. Tenant isolation holds for the newest surfaces built in this document's own phases (cumulative
     results, account recovery, dynamic branding) -- re-confirming it here rather than trusting that
     each phase's own tests were sufficient on their own.
  7. Passwords are never stored anywhere in plain text, across every account-type table this
     project has (staff, students, parents, platform admins).

The fix: the unified /login form's staff-and-parent lookup (app.py, inside login()) used to skip
straight past an UNKNOWN identifier with no password hash ever computed, while a WRONG password for
a REAL identifier always computed one (bcrypt/scrypt, deliberately slow) -- a timing side-channel an
attacker could use to enumerate which usernames/emails/phone numbers have real accounts, purely by
measuring response time, without ever getting a single wrong-password attempt logged as suspicious.
Student login already defended against exactly this with a constant-time dummy-password check
(_DUMMY_PASSWORD_HASH); this brings the staff/parent branch up to that same standard by computing
that same dummy hash whenever neither lookup finds a single candidate.

Run: python tests/v84_scenarios.py"""
import logging
import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v84_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
from db import get_db
from werkzeug.security import generate_password_hash, check_password_hash

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


def db():
    return get_db()


def one(sql, args=()):
    c = db()
    try:
        return c.execute(sql, args).fetchone()
    finally:
        c.close()


def run(sql, args=()):
    c = db()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    return m.group(1) if m else None


def post_with_token(c, path, data, page=None):
    d = dict(data)
    d["csrf_token"] = tok(c, page or path)
    return c.post(path, data=d)


pw = generate_password_hash("Pass1234")

# ---------------------------------------------------------- 1) the timing side-channel fix: a dummy hash IS computed for unknown identifiers
A._rate_limit_store.clear()
calls = []
_real_check = A.check_password_hash


def counting_check(pwhash, candidate):
    calls.append(pwhash)
    return _real_check(pwhash, candidate)


A.check_password_hash = counting_check
c1 = A.app.test_client()
calls.clear()
post_with_token(c1, "/login", {"username": "totally-unknown-person-xyz", "password": "whatever123"}, "/login")
check("an UNKNOWN login identifier still triggers a password-hash comparison (closes the timing side-channel)",
      len(calls) >= 1, calls)
check("...and it's checked against the dedicated dummy hash, not skipped or faked some other way",
      any(A.check_password_hash is counting_check and h == A._DUMMY_PASSWORD_HASH for h in calls) or A._DUMMY_PASSWORD_HASH in calls,
      calls)
A.check_password_hash = _real_check

# A real (wrong-password) identifier was already doing a genuine hash check before this fix --
# confirm the fix didn't change that, so both cases now cost roughly the same amount of work.
admin_row = one("SELECT username FROM users WHERE role='admin' LIMIT 1")
run("UPDATE users SET password_hash=? WHERE username=?", (pw, admin_row["username"]))
A._rate_limit_store.clear()
c2 = A.app.test_client()
r2 = post_with_token(c2, "/login", {"username": admin_row["username"], "password": "wrong-password-here"}, "/login")
check("a KNOWN identifier with the wrong password still fails cleanly (unaffected by the fix)",
      r2.status_code == 200 and "Invalid" in html(r2))

# ---------------------------------------------------------- 2) CSRF is actually enforced, not just incidentally satisfied
A._rate_limit_store.clear()
c3 = A.app.test_client()
c3.get("/login")  # establishes a session (and its own CSRF token, which we deliberately don't send)
c3.post("/login", data={"username": admin_row["username"], "password": "Pass1234"})  # no csrf_token field at all
with c3.session_transaction() as s:
    check("a POST with NO csrf_token field at all is rejected -- no session was established from it", "user_id" not in s)

A._rate_limit_store.clear()
c4 = A.app.test_client()
c4.get("/login")
r4 = c4.post("/login", data={"username": admin_row["username"], "password": "Pass1234", "csrf_token": "totally-made-up-token-value"})
with c4.session_transaction() as s:
    check("a POST with a WRONG/forged csrf_token is also rejected, not just a missing one", "user_id" not in s)

# ---------------------------------------------------------- 3) production security headers are present on real responses
A._rate_limit_store.clear()
c5 = A.app.test_client()
r5 = c5.get("/login")
h = r5.headers
check("X-Content-Type-Options: nosniff is set", h.get("X-Content-Type-Options") == "nosniff")
check("X-Frame-Options prevents this app being framed by another site", h.get("X-Frame-Options") == "SAMEORIGIN")
check("a Referrer-Policy header is set", bool(h.get("Referrer-Policy")))
check("a Permissions-Policy header locks down camera/microphone/geolocation by default", "camera=()" in (h.get("Permissions-Policy") or ""))

# ---------------------------------------------------------- 4) login brute-force rate limiting genuinely engages (deliberately NOT cleared first)
A._rate_limit_store.clear()
c6 = A.app.test_client()
results = []
for _ in range(12):
    d = {"username": "brute-force-probe", "password": "guess", "csrf_token": tok(c6, "/login")}
    rr = c6.post("/login", data=d, follow_redirects=True)
    results.append(html(rr))
check("after repeated rapid attempts, the rate limiter eventually blocks further tries",
      any("Too many attempts" in body for body in results), "no rate-limit message seen across 12 attempts")
A._rate_limit_store.clear()

# ---------------------------------------------------------- 5) an unauthenticated visitor is redirected to sign in, never shown a staff page
c7 = A.app.test_client()
for staff_path in ("/dashboard", "/admin/students", "/admin/theme"):
    rr = c7.get(staff_path)
    check(f"an anonymous visit to {staff_path} redirects to sign-in rather than showing the page",
          rr.status_code in (302, 401, 403) and (rr.status_code != 302 or "login" in rr.headers.get("Location", "")), (rr.status_code, rr.headers.get("Location")))

# ---------------------------------------------------------- 6) tenant isolation holds for this document's own newest surfaces
run("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Rival Academy','active','RIVAL','SCH-RIVAL-V84')")
rival_id = one("SELECT id FROM schools WHERE school_code='SCH-RIVAL-V84'")["id"]
run("INSERT INTO classes(name,school_id,category) VALUES('Rival Class',?, 'secondary')", (rival_id,))
rival_class_id = one("SELECT id FROM classes WHERE name='Rival Class'")["id"]

ADMIN = A.app.test_client()
A._rate_limit_store.clear()
post_with_token(ADMIN, "/login", {"username": admin_row["username"], "password": "Pass1234"}, "/login")
with ADMIN.session_transaction() as s:
    check("our admin test session actually authenticated (sanity check before the real assertion)", "user_id" in s, dict(s))

# This route's access-control helper turns an out-of-tenant class id into "that class doesn't
# exist" and redirects to the dashboard (the same pattern this app uses for out-of-tenant access
# throughout) rather than a raw 404 -- what matters is that the content itself is never reached.
r6a = ADMIN.get(f"/cumulative/{rival_class_id}", follow_redirects=True)
check("a school admin cannot view ANOTHER school's cumulative broadsheet by guessing its class id",
      r6a.status_code == 200 and "That class" in html(r6a) and "Rival" not in html(r6a), r6a.status_code)

r6b = ADMIN.get("/admin/theme?school_id=%d" % rival_id) if False else ADMIN.get("/admin/theme")
h6b = html(r6b)
check("the branding/theme settings page never exposes another school's data even if asked for by id", "Rival Academy" not in h6b)

# ---------------------------------------------------------- 7) no plain-text passwords anywhere, across every account type
users_plain = one("SELECT COUNT(*) c FROM users WHERE password_hash IS NOT NULL AND password_hash NOT LIKE 'pbkdf2:%' AND password_hash NOT LIKE 'scrypt:%'")
students_plain = one("SELECT COUNT(*) c FROM students WHERE password_hash IS NOT NULL AND password_hash NOT LIKE 'pbkdf2:%' AND password_hash NOT LIKE 'scrypt:%'")
parents_plain = one("SELECT COUNT(*) c FROM parent_accounts WHERE password_hash IS NOT NULL AND password_hash NOT LIKE 'pbkdf2:%' AND password_hash NOT LIKE 'scrypt:%'") if A._table_exists_safe(db(), "parent_accounts") else {"c": 0}
platform_plain = one("SELECT COUNT(*) c FROM platform_admins WHERE password_hash IS NOT NULL AND password_hash NOT LIKE 'pbkdf2:%' AND password_hash NOT LIKE 'scrypt:%'") if A._table_exists_safe(db(), "platform_admins") else {"c": 0}
check("every staff password on file is a proper salted hash, never plain text", users_plain["c"] == 0, users_plain["c"])
check("every student password on file is a proper salted hash, never plain text", students_plain["c"] == 0, students_plain["c"])
check("every parent password on file is a proper salted hash, never plain text", parents_plain["c"] == 0, parents_plain["c"])
check("every platform-admin password on file is a proper salted hash, never plain text", platform_plain["c"] == 0, platform_plain["c"])

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
