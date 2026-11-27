"""End-to-end scenarios for the V83 requirement: Phase 6 of the ninth requirements document
("Consolidated Development Specification"), "Dynamic Login Branding" -- a confirmation pass.

Audit finding: unlike the other phases in this document, this one was already almost entirely
built well before the 9th requirements document existed -- a school's own subdomain, logo, and
color/name display preferences already apply automatically to the sign-in screen
(_resolve_subdomain_from_host / _load_portal_school / _public_auth_school / _auth_branding_payload
in app.py), with no code in this suite needed to add that. What this phase actually needed was
confirmation it genuinely works end-to-end (nothing in the test suite exercised it before this
round) plus closing one real, if minor, gap found while confirming it:

Fixed: _public_auth_school()'s fallback branding lookup (used when there's no custom subdomain, so
branding is guessed from a submitted "username" field after a failed sign-in attempt) only ever
checked the staff `users` table. Since V81 folded student and parent sign-in into this same unified
form and its same "username" field, a STUDENT or PARENT whose login attempt failed and whose page
re-rendered would silently fall back to the generic unbranded look, even though their own school's
branding could have been resolved from their identifier. Now checks students and parent_accounts
too, in that order, after users.

Confirmed already correct, not changed: subdomain resolution takes priority over everything else
and ignores reserved subdomains (www, app, api, ...); an unrecognized subdomain shows the generic
unbranded page rather than erroring; a school with auth_branding_enabled=0, no logo, or an inactive
activation_status never shows branding even if its subdomain matches; auth_show_school_name=0 shows
the generic "My School Hub" name while still (correctly) not showing a logo if branding is off
elsewhere; the /auth/branding JSON endpoint mirrors exactly what the page itself renders, for any
front-end script that wants it. No School Selection: the login form has never had a school
picker/dropdown, confirmed again here as part of this pass (also covered in V81's own tests).

Run: python tests/v83_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v83_")
os.environ["BASE_DOMAIN"] = "myschoolhub.test"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
from db import get_db
from werkzeug.security import generate_password_hash

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


BASE = "http://myschoolhub.test"


def at(subdomain=None):
    return f"http://{subdomain}.myschoolhub.test" if subdomain else BASE


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute(
    "UPDATE schools SET subdomain='greenwood', name='Greenwood Academy', auth_branding_enabled=1, "
    "logo_filename='fake_logo.png', activation_status='active', auth_show_school_name=1, "
    "auth_logo_opacity=0.15, auth_logo_position='left' WHERE id=1"
)
c0.execute("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Other College','active','2','SCH-OTHER-V83')")
other_school_id = c0.execute("SELECT id FROM schools WHERE school_code='SCH-OTHER-V83'").fetchone()["id"]
c0.execute("UPDATE schools SET subdomain='other', logo_filename='fake_logo2.png', auth_branding_enabled=1 WHERE id=?", (other_school_id,))

student = c0.execute("SELECT id, admission_no, class_id FROM students LIMIT 1").fetchone()
tenant1 = c0.execute("SELECT tenant_id FROM schools WHERE id=1").fetchone()["tenant_id"]
c0.execute(
    "INSERT INTO parent_accounts(school_id,tenant_id,name,username,email,phone,password_hash,is_active,account_status,signup_status) "
    "VALUES(1,?,?,?,?,?,?,1,'active','approved')",
    (tenant1, "Mr Okafor", "mrokafor", "okafor@example.com", "08033334444", pw),
)
c0.commit()
c0.close()

# ---------------------------------------------------------- 1) a custom subdomain automatically brands the sign-in page
anon = A.app.test_client()
r1 = anon.get("/login", base_url=at("greenwood"))
h1 = html(r1)
check("visiting a school's own subdomain shows that school's name on the sign-in page, automatically", "Greenwood Academy" in h1)
check("...and that school's own logo, served from its own (public) logo route", f'src="/portal-logo/1"' in h1)
check("there is still no school-picker/dropdown anywhere on the page", 'name="school_id"' not in h1 and "<select" not in h1)

# ---------------------------------------------------------- 2) a DIFFERENT subdomain shows a DIFFERENT school, correctly isolated
r2 = anon.get("/login", base_url=at("other"))
h2 = html(r2)
check("a second school's own subdomain shows ITS OWN name, not the first school's", "Other College" in h2 and "Greenwood Academy" not in h2)
check("...and ITS OWN logo (different school id in the logo URL)", f"/portal-logo/{other_school_id}" in h2)

# ---------------------------------------------------------- 3) an unrecognized subdomain falls back to the generic, unbranded page (never errors)
r3 = anon.get("/login", base_url=at("doesnt-exist-anywhere"))
check("a subdomain nobody owns shows the plain generic page, not an error", r3.status_code == 200 and "My School Hub" in html(r3) and "Greenwood Academy" not in html(r3))

# ---------------------------------------------------------- 4) reserved subdomains (www, app, api, ...) never resolve to a school
for reserved in ("www", "app", "api"):
    rr = anon.get("/login", base_url=at(reserved))
    check(f"the reserved subdomain '{reserved}' never shows school branding", rr.status_code == 200 and "Greenwood Academy" not in html(rr) and "Other College" not in html(rr))

# ---------------------------------------------------------- 5) the plain base domain (no subdomain at all) shows the generic page
r5 = anon.get("/login", base_url=at(None))
check("the plain base domain with no subdomain shows the generic unbranded page", "My School Hub" in html(r5) and "Greenwood Academy" not in html(r5))

# ---------------------------------------------------------- 6) branding respects the school's own on/off switch, even with a working subdomain+logo
run("UPDATE schools SET auth_branding_enabled=0 WHERE id=1")
r6 = anon.get("/login", base_url=at("greenwood"))
h6 = html(r6)
check("turning branding off hides the logo even though the subdomain still resolves", f'src="/portal-logo/1"' not in h6)
check("...and the generic site name is shown instead of the school's own name (the master switch covers both)", "My School Hub" in h6 and "Greenwood Academy" not in h6)
run("UPDATE schools SET auth_branding_enabled=1 WHERE id=1")

# ---------------------------------------------------------- 7) the school-name display toggle works independently of the logo toggle
run("UPDATE schools SET auth_show_school_name=0 WHERE id=1")
r7 = anon.get("/login", base_url=at("greenwood"))
h7 = html(r7)
name_tag = re.search(r"data-auth-school-name>([^<]*)<", h7)
check("turning off 'show school name' falls back to the generic site name in that spot", bool(name_tag) and name_tag.group(1).strip() == "My School Hub", name_tag.group(1) if name_tag else None)
check("...while the logo (a separate setting) is unaffected and still shows", f'src="/portal-logo/1"' in h7)
run("UPDATE schools SET auth_show_school_name=1 WHERE id=1")

# ---------------------------------------------------------- 8) an inactive/suspended school never shows branding, even on its own subdomain
run("UPDATE schools SET activation_status='pending' WHERE id=1")
r8 = anon.get("/login", base_url=at("greenwood"))
check("a school that isn't active yet doesn't show its logo on its own subdomain", f'src="/portal-logo/1"' not in html(r8))
run("UPDATE schools SET activation_status='active' WHERE id=1")

# ---------------------------------------------------------- 9) the public /auth/branding JSON endpoint mirrors the page exactly
rj = anon.get("/auth/branding", base_url=at("greenwood"))
data = rj.get_json()
check("the JSON branding endpoint reports the same school as the rendered page", data.get("school_name") == "Greenwood Academy" and data.get("branding") is True)
check("...and carries the school's own logo opacity/position settings through", abs(data.get("opacity", 0) - 0.15) < 0.001 and data.get("position") == "left")

# ---------------------------------------------------------- 10) [the fix] a STUDENT's failed sign-in attempt still re-brands correctly (new gap closed this round)
anon2 = A.app.test_client()
r10 = anon2.get(f"/login?username={student['admission_no']}", base_url=at(None))
check("a student identifier in the login form resolves THEIR school's branding on the plain domain (previously fell back to generic)", "Greenwood Academy" in html(r10))

# ---------------------------------------------------------- 11) [the fix] a PARENT's identifier does the same
anon3 = A.app.test_client()
r11 = anon3.get("/login?username=mrokafor", base_url=at(None))
check("a parent's username in the login form also resolves their school's branding (previously fell back to generic)", "Greenwood Academy" in html(r11))

# ---------------------------------------------------------- 12) a subdomain still takes priority over a username query param pointing elsewhere
anon4 = A.app.test_client()
r12 = anon4.get(f"/login?username={student['admission_no']}", base_url=at("other"))
check("when both a subdomain AND a username are present, the subdomain (the more certain signal) wins", "Other College" in html(r12) and "Greenwood Academy" not in html(r12))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
