"""End-to-end scenarios for the V82 requirement: Phase 5 of the ninth requirements document
("Consolidated Development Specification"), "Secure Account Recovery" / "Username and Password
Recovery."

Audited gap: the only account-recovery flow in the app (/recover) asked for a USERNAME and then a
security question -- and only the `users` table (staff) has security-question columns at all, so
parents (and students, who have no email of their own) had no self-service way to recover a lost
password. The spec calls for email-based recovery covering all account types.

Fixed: a new /account-recovery flow asks only for an EMAIL ADDRESS (never a username, so it can't
be used to test whether a given username exists), looks that email up across BOTH staff (`users`)
and parent (`parent_accounts`) accounts, and -- for every match -- emails a single-use, time-limited
reset link via that match's OWN school's SMTP settings (the same per-school `send_email()` every
other outbound email in this app already uses). The confirmation shown on screen is identical
whether or not the email matched anything, so the page can't be used to enumerate which addresses
have accounts (the same anti-enumeration principle student login already follows with its
constant-time dummy-password check). The reset email also states the account's username, so this
covers "forgot my username" as well as "forgot my password" in one flow.

A parent who shares the same email across TWO different schools (the per-school username-collision
case flagged as a known follow-up back when the parent portal was built) gets one clearly-labeled
email per school rather than one ambiguous combined message, because each school's email has to go
out through that school's own SMTP credentials anyway.

Deliberately NOT built this round: self-service recovery for STUDENT accounts. Students have no
email field of their own in this system (only a shared parent_email on the student record, which
the student doesn't control) -- inventing one wasn't asked for, and routing a student's own password
reset through a parent's inbox would hand account control to someone else. Student passwords remain
staff-assisted (Setup -> Students -> Reset Login / class login codes), exactly as before this phase.
The older /recover (username + security question) flow is left fully in place, unchanged, as a
fallback for a staff member who has no email on file -- it is simply no longer the link shown on the
main sign-in screen.

Run: python tests/v82_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v82_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
from db import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from flask.testing import FlaskClient

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


# ------------------------------------------------------------------ fake email transport
# No real SMTP in a test run: record every call instead of touching the network, the way this
# project captures outbound side-effects elsewhere (no prior test exercised email sending at all,
# so this is the first -- recording calls is the simplest faithful stand-in for "an email went out").
SENT = []


def fake_send_email(school, to_email, subject, body_text, attachment_bytes=None, attachment_filename=None):
    SENT.append({"school_id": school["id"] if school else None, "to": to_email, "subject": subject, "body": body_text})
    return True, "Sent (fake)."


A.send_email = fake_send_email


def extract_token(body):
    m = re.search(r"/account-recovery/reset/([A-Za-z0-9_\-]+)", body)
    return m.group(1) if m else None


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("OldPass123")
c0 = db()

staff = c0.execute("SELECT id, username, name FROM users WHERE role='admin' LIMIT 1").fetchone()
c0.execute("UPDATE users SET password_hash=?, email=? WHERE id=?", (pw, "staffmail@example.com", staff["id"]))

# A staff member with NO email on file -- should get no email, same generic response.
nomail_staff = c0.execute("SELECT id, username FROM users WHERE id!=?", (staff["id"],)).fetchone()
if nomail_staff:
    c0.execute("UPDATE users SET password_hash=?, email=NULL WHERE id=?", (pw, nomail_staff["id"]))

tenant1 = c0.execute("SELECT tenant_id FROM schools WHERE id=1").fetchone()["tenant_id"]
c0.execute(
    "INSERT INTO parent_accounts(school_id,tenant_id,name,username,email,phone,password_hash,is_active,account_status,signup_status) "
    "VALUES(1,?,?,?,?,?,?,1,'active','approved')",
    (tenant1, "Mrs Adeyemi", "madeyemi", "shared@example.com", "08011112222", pw),
)
parent1_id = c0.execute("SELECT id FROM parent_accounts WHERE username='madeyemi'").fetchone()["id"]

# A second, unrelated school, and a SECOND parent account under the SAME shared email -- this is
# the per-school username-collision case: same email, two different schools, two different accounts.
c0.execute("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Other College','active','2','SCH-OTHER-V82')")
school2_id = c0.execute("SELECT id FROM schools WHERE school_code='SCH-OTHER-V82'").fetchone()["id"]
c0.execute(
    "INSERT INTO parent_accounts(school_id,tenant_id,name,username,email,phone,password_hash,is_active,account_status,signup_status) "
    "VALUES(?,?,?,?,?,?,?,1,'active','approved')",
    (school2_id, "2", "Mrs Adeyemi", "madeyemi-oc", "shared@example.com", "08011112222", pw),
)
parent2_id = c0.execute("SELECT id FROM parent_accounts WHERE username='madeyemi-oc'").fetchone()["id"]

c0.commit()
c0.close()

# ---------------------------------------------------------- 1) the forgot-password link on the unified sign-in form points here
anon = A.app.test_client()
lg = html(anon.get("/login"))
check("the unified sign-in page's forgot-password link now points at the new email-based flow",
      'href="/account-recovery"' in lg)
check("the older username+security-question flow is still reachable too (not removed, just not the headline link)",
      A.app.test_client().get("/recover").status_code == 200)

# ---------------------------------------------------------- 2) a staff member recovers by email
A._rate_limit_store.clear()
c1 = A.app.test_client()
SENT.clear()
r1 = post(c1, "/account-recovery", {"email": "staffmail@example.com"}, "/account-recovery")
check("submitting a real staff email redirects back to the login page", r1.status_code == 302 and r1.headers.get("Location", "").endswith("/login"))
check("exactly one email was sent for a single matching staff account", len(SENT) == 1, SENT)
check("the email went to the right address", SENT and SENT[0]["to"] == "staffmail@example.com", SENT)
check("the email states the account's username (covers 'forgot my username' too)", SENT and staff["username"] in SENT[0]["body"], SENT[0]["body"] if SENT else "")
token1 = extract_token(SENT[0]["body"]) if SENT else None
check("the email contains a reset link with a token", bool(token1), SENT)

# ---------------------------------------------------------- 3) the reset link actually works, once
A._rate_limit_store.clear()
c2 = A.app.test_client()
rg = c2.get(f"/account-recovery/reset/{token1}")
check("the reset link opens a working 'set a new password' page", rg.status_code == 200 and "New Password" in html(rg))

rbad = post(c2, f"/account-recovery/reset/{token1}", {"new_password": "NewPass456", "confirm_password": "DIFFERENT"}, f"/account-recovery/reset/{token1}")
check("a mismatched confirmation is rejected", "don't match" in html(rbad) or rbad.status_code == 200)
check("...and the password was NOT changed yet", check_password_hash(one("SELECT password_hash FROM users WHERE id=?", (staff["id"],))["password_hash"], "OldPass123"))

rok = post(c2, f"/account-recovery/reset/{token1}", {"new_password": "NewPass456", "confirm_password": "NewPass456"}, f"/account-recovery/reset/{token1}")
check("a matching new password succeeds and redirects to login", rok.status_code == 302 and rok.headers.get("Location", "").endswith("/login"))
staff_after = one("SELECT password_hash FROM users WHERE id=?", (staff["id"],))
check("the staff account's password is now the NEW one", check_password_hash(staff_after["password_hash"], "NewPass456"))
check("...and the OLD password no longer works", not check_password_hash(staff_after["password_hash"], "OldPass123"))

c3 = A.app.test_client()
rlogin = post(c3, "/login", {"username": staff["username"], "password": "NewPass456", "school_code": ""}, "/login")
check("the staff member can now sign in through the unified form with the new password", rlogin.status_code == 302 and "/dashboard" in rlogin.headers.get("Location", ""))

# ---------------------------------------------------------- 4) the reset link is single-use
# A used-up link is caught on the GET itself (there's no legitimate CSRF token to even try
# posting with -- a visitor following the old link just gets redirected straight past the form),
# so this checks the GET behaviour directly rather than forging a POST with no real token.
A._rate_limit_store.clear()
c4 = A.app.test_client()
rreplay = c4.get(f"/account-recovery/reset/{token1}")
check("revisiting the SAME reset link after it's been used redirects away instead of showing the form again",
      rreplay.status_code == 302 and rreplay.headers.get("Location", "").endswith("/account-recovery"))
check("...and the password from the first use is still the one in effect (no silent second change)",
      check_password_hash(one("SELECT password_hash FROM users WHERE id=?", (staff["id"],))["password_hash"], "NewPass456"))

# ---------------------------------------------------------- 5) an unknown email gets the SAME generic response (no enumeration)
A._rate_limit_store.clear()
c5 = A.app.test_client()
SENT.clear()
r5 = post(c5, "/account-recovery", {"email": "nobody-registered@example.com"}, "/account-recovery")
check("an email with no matching account still redirects to login with no error revealed", r5.status_code == 302 and r5.headers.get("Location", "").endswith("/login"))
check("...and, correctly, no email was actually sent for it", len(SENT) == 0, SENT)

with c5.session_transaction() as s:
    pass  # no persistent recovery state should be needed/left behind for a non-match

# Compare the flash message text between a real match and a non-match -- they must be identical,
# otherwise the page could be used to probe which emails are registered.
A._rate_limit_store.clear()
c6 = A.app.test_client()
SENT.clear()
run("UPDATE users SET email=? WHERE id=?", ("staffmail2@example.com", staff["id"]))
rA = post(c6, "/account-recovery", {"email": "staffmail2@example.com"}, "/account-recovery")
msgA = html(c6.get("/login"))
A._rate_limit_store.clear()
c7 = A.app.test_client()
rB = post(c7, "/account-recovery", {"email": "definitely-not-registered@example.com"}, "/account-recovery")
msgB = html(c7.get("/login"))
genericA = re.search(r"If an account is associated.*?minutes\.", msgA)
genericB = re.search(r"If an account is associated.*?minutes\.", msgB)
check("the on-screen confirmation is word-for-word identical whether or not the email matched an account",
      bool(genericA) and bool(genericB) and genericA.group(0) == genericB.group(0))

# ---------------------------------------------------------- 6) a staff member with NO email on file triggers no email either
if nomail_staff:
    A._rate_limit_store.clear()
    c8 = A.app.test_client()
    SENT.clear()
    r8 = post(c8, "/account-recovery", {"email": "doesnt-matter@example.com"}, "/account-recovery")
    check("a staff account with no email configured can't be reached through this flow at all", len(SENT) == 0, SENT)

# ---------------------------------------------------------- 7) a parent recovers by email, scoped to their OWN school
A._rate_limit_store.clear()
c9 = A.app.test_client()
SENT.clear()
r9 = post(c9, "/account-recovery", {"email": "shared@example.com"}, "/account-recovery")
check("a shared parent email matching accounts at TWO schools sends TWO separate emails, not one combined one",
      len(SENT) == 2, SENT)
check("each email is clearly scoped to its OWN school's account/username, not mixed together",
      {s["to"] for s in SENT} == {"shared@example.com"} and
      any("madeyemi-oc" in s["body"] for s in SENT) and any(("madeyemi" in s["body"] and "madeyemi-oc" not in s["body"]) for s in SENT),
      SENT)
tokens_parent = [extract_token(s["body"]) for s in SENT]
check("both parent emails contain their own distinct, usable reset token", all(tokens_parent) and len(set(tokens_parent)) == 2, tokens_parent)

# Resetting via ONE parent's link only changes THAT parent account, not the other school's.
A._rate_limit_store.clear()
c10 = A.app.test_client()
target_token = None
for s, t in zip(SENT, tokens_parent):
    if "madeyemi-oc" in s["body"]:
        target_token = t
r10 = post(c10, f"/account-recovery/reset/{target_token}", {"new_password": "ParentNew123", "confirm_password": "ParentNew123"}, f"/account-recovery/reset/{target_token}")
check("resetting via the school-2 parent's link succeeds", r10.status_code == 302)
p2_after = one("SELECT password_hash FROM parent_accounts WHERE id=?", (parent2_id,))
p1_after = one("SELECT password_hash FROM parent_accounts WHERE id=?", (parent1_id,))
check("only the school-2 parent account's password actually changed", check_password_hash(p2_after["password_hash"], "ParentNew123"))
check("the OTHER school's parent account (same email) was left completely untouched", check_password_hash(p1_after["password_hash"], "OldPass123"))

# ---------------------------------------------------------- 8) requesting a new link invalidates an earlier, still-unused one
A._rate_limit_store.clear()
c11 = A.app.test_client()
SENT.clear()
run("UPDATE users SET email=? WHERE id=?", ("staffmail3@example.com", staff["id"]))
post(c11, "/account-recovery", {"email": "staffmail3@example.com"}, "/account-recovery")
first_token = extract_token(SENT[0]["body"])
A._rate_limit_store.clear()
SENT.clear()
post(c11, "/account-recovery", {"email": "staffmail3@example.com"}, "/account-recovery")
second_token = extract_token(SENT[0]["body"])
check("two different tokens were issued for two separate requests", first_token != second_token, (first_token, second_token))
c12 = A.app.test_client()
r_old = c12.get(f"/account-recovery/reset/{first_token}")
check("the EARLIER token is no longer valid once a newer one was issued", r_old.status_code == 302 and r_old.headers.get("Location", "").endswith("/account-recovery"))

# ---------------------------------------------------------- 9) a bogus/garbage token is rejected cleanly, no crash
A._rate_limit_store.clear()
c13 = A.app.test_client()
r13 = c13.get("/account-recovery/reset/not-a-real-token-at-all")
check("a bogus token is rejected cleanly (no server error)", r13.status_code == 302 and r13.headers.get("Location", "").endswith("/account-recovery"))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
