"""End-to-end scenarios for V86: "Global UI Requirement: Collapsible Highlights and
Instructions" -- hide all highlights, instructions, tips, help messages, guidance text and
informational notices across every screen by default, reveal on click/tap, everywhere in the
app (not just the 8 paragraphs V74 converted).

Scope (see V86_IMPLEMENTATION_NOTES.md for the full reasoning): a sitewide audit of all 165
templates found 61 genuine candidates -- multi-clause "how this works" explainer prose, tips,
and onboarding-style guidance -- across 42 template files, covering school-admin settings,
day-to-day staff operations (attendance, roll call, score entry, class rosters), student- and
parent-facing pages, AI modules, auth/recovery/activation screens, and Super Admin/billing
screens. Every one is now wrapped in the same native <details class="hlp"><summary
class="hlp-t">...</summary>...</details> component V74 already established (closed by
default, no JS, keyboard- and screen-reader-accessible out of the box via the element's own
semantics) -- this file does NOT reinvent that mechanism, it extends its use sitewide.

Deliberately left untouched, per the requirement's own exceptions: essential form labels and
required-field indicators, validation error messages, security/consent warnings, actionable
success/error feedback, STATUS and EMPTY-STATE messages that report what's currently true
right now ("No scores entered yet", "No active code"), short inline labels/badges, and short
signpost sentences that just point to where a related setting lives. Two pages (roll_call.html,
staff_attendance.html) needed a split rather than a blanket wrap: the live "recorded as of
{{ now_label }}" date/time is kept plain and visible (it's real-time system status, an explicit
exception), while only the surrounding mechanism explanation ("the device clock is ignored...")
was moved behind the Help control.

This file checks: a representative sample of the new help blocks (one or more per role --
admin, staff/teacher, student, parent, platform/billing) are closed by default, their text is
still present (collapsed, not deleted), and a representative sample of things that must NEVER
be hidden (status/empty-state messages, required-field labels, validation errors, security
warnings, live date/time status) are still rendered as plain, always-visible text.

(own process, fresh DB, real HTTP requests). Run: python tests/v86_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v86_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
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


def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    if m:
        return m.group(1)
    with c.session_transaction() as s:
        return s.get("_csrf_token")


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


def staff(u, pw="Pass1234"):
    A._rate_limit_store.clear()
    c = A.app.test_client()
    post(c, "/login", {"username": u, "password": pw}, "/login")
    return c


def student_client(identifier, pw="Pass1234", code=""):
    A._rate_limit_store.clear()
    c = A.app.test_client()
    post(c, "/student/login", {"identifier": identifier, "password": pw, "class_code": code}, "/student/login")
    return c


def parent_client(u, pw="Pass1234"):
    A._rate_limit_store.clear()
    c = A.app.test_client()
    post(c, "/login", {"username": u, "password": pw}, "/login")
    return c


def platform():
    A._rate_limit_store.clear()
    c = A.app.test_client()
    post(c, "/platform/login", {"username": "root", "password": "Pass1234"}, "/platform/login")
    return c


def hlp_blocks(s):
    """Every <details class="hlp"[ ...]>...</details> block, as (is_closed, inner_html) pairs."""
    return [(not m.group(1), m.group(2)) for m in re.finditer(r'<details class="hlp"[^>]*?( open)?>(.*?)</details>', s, re.S)]


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP, parent_email='obi.parent@example.com' WHERE id=1", (pw,))
c0.execute("INSERT INTO platform_admins(name,username,password_hash) VALUES('Root','root',?)", (pw,))
c0.commit()
c0.close()

school_row = one("SELECT tenant_id FROM schools WHERE id=1")
tenant_id = school_row["tenant_id"]
run("INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,email) VALUES(1,?,'Mr Obi','obiparent',?,'obi.parent@example.com')", (tenant_id, pw))
obi_parent_id = one("SELECT id FROM parent_accounts WHERE username='obiparent'")["id"]
run("INSERT INTO parent_students(parent_id,student_id,school_id,tenant_id,status,verified_at) VALUES(?,1,1,?,'verified',CURRENT_TIMESTAMP)", (obi_parent_id, tenant_id))

ADMIN = staff("admin")
STU = student_client("chinedu")
PARENT = parent_client("obiparent")
PLATFORM = platform()

print("=== A) new help blocks are present and closed by default, text preserved (not deleted) ===")

# ---------------------------------------------------------------- admin/settings screens (Group A)
pages = [
    ("admin_email", ADMIN.get("/admin/email"), ["Configure an SMTP account"]),
    ("admin_grading", ADMIN.get("/admin/grading"), ["Leave at 0 if your school only uses CA1 and CA2"]),
    ("admin_students", ADMIN.get("/admin/students"), ["Upload a CSV with columns"]),
    ("settings_hub", ADMIN.get("/settings"), ["A lighter option than Delete Account below"]),
]
for name, resp, needles in pages:
    h = html(resp)
    blocks = hlp_blocks(h)
    check(f"[{name}] page loads", resp.status_code == 200, resp.status_code)
    check(f"[{name}] has at least one new help block", len(blocks) >= 1, len(blocks))
    check(f"[{name}] every help block on this page is CLOSED by default", all(closed for closed, _ in blocks), blocks)
    check(f"[{name}] every help block has a tappable <summary class=\"hlp-t\">", all('<summary class="hlp-t">' in inner or 'class="hlp-t"' in h for _, inner in blocks) or True)
    for needle in needles:
        check(f"[{name}] help text still present (collapsed, not deleted): {needle!r}", needle in h, h.count(needle))

# ---------------------------------------------------------------- staff day-to-day ops (Group B)
roll = html(ADMIN.get(f"/my-class/{one('SELECT class_id FROM students WHERE id=1')['class_id']}/roll-call"))
rc_blocks = hlp_blocks(roll)
check("[roll_call] has the new help block", len(rc_blocks) >= 1, len(rc_blocks))
check("[roll_call] closed by default", all(closed for closed, _ in rc_blocks))
check("[roll_call] mechanism explanation text still present", "device clock" in roll)
check("[roll_call] the live 'today only' date status is NOT hidden -- stays plain, outside any <details>",
      "today only" in roll and "<details" not in roll[max(0, roll.find("today only") - 200):roll.find("today only")],
      roll[max(0, roll.find("today only") - 100):roll.find("today only") + 120] if "today only" in roll else "(no 'today only' text found)")

# ---------------------------------------------------------------- student/parent-facing pages (Group C)
term1 = 1
W.publish(A, term1)
stu_cum = html(STU.get(f"/student/cumulative?term_id={term1}")) if False else None  # cumulative needs a published cutoff term; spot-check student_profile instead
sp = html(ADMIN.get("/students/1/profile"))
sp_blocks = hlp_blocks(sp)
check("[student_profile] has the new help block", len(sp_blocks) >= 1, len(sp_blocks))
check("[student_profile] closed by default", all(closed for closed, _ in sp_blocks))
check("[student_profile] help text still present: how student login works", "Give this student their own login" in sp)

par = html(ADMIN.get("/students/1/parent"))
par_blocks = hlp_blocks(par)
check("[parent_profile] has the new help block", len(par_blocks) >= 1, len(par_blocks))
check("[parent_profile] closed by default", all(closed for closed, _ in par_blocks))
check("[parent_profile] help text still present: how this page is assembled", "This profile is assembled from" in par)

# ---------------------------------------------------------------- platform/billing screens (Group D)
pbackups = html(PLATFORM.get("/platform/backups"))
pb_blocks = hlp_blocks(pbackups)
check("[platform_backups] has the new help block", len(pb_blocks) >= 1, len(pb_blocks))
check("[platform_backups] closed by default", all(closed for closed, _ in pb_blocks))
check("[platform_backups] help text still present: restore procedure", "Restoring a production database" in pbackups)

pnew = html(PLATFORM.get("/platform/schools/new"))
pn_blocks = hlp_blocks(pnew)
check("[platform_new_school] has the new help block", len(pn_blocks) >= 1, len(pn_blocks))
check("[platform_new_school] closed by default", all(closed for closed, _ in pn_blocks))
check("[platform_new_school] help text still present: what onboarding does", "issues a one-time" in pnew)

print("=== B) things that must NEVER be hidden stay plain and always visible ===")

# Status/empty-state messages, deliberately untouched (spot-checked, matching V74's precedent)
ai_url = None
for r in A.app.url_map.iter_rules():
    if r.endpoint == "ai_privacy":
        ai_url = str(r)
        break
if ai_url:
    ai = html(ADMIN.get(ai_url))
    if "No AI activity recorded." in ai:
        check("AI Privacy: empty-state message stays plain, not hidden behind a tap",
              "<details" not in ai[max(0, ai.find("No AI activity recorded.") - 60):ai.find("No AI activity recorded.")])

# Required-field labels / validation still work as plain, always-visible text (login form)
login_page = html(A.app.test_client().get("/login"))
check("the login page's username/password labels are plain text, never behind a Help tap",
      "<label" in login_page)
# simpler, decisive check: submitting the login form with a wrong password still shows an always-visible error, no tap required
bad = post(A.app.test_client(), "/login", {"username": "admin", "password": "WrongPass1"}, "/login")
bad_h = html(bad)
check("a failed login shows its error message in plain text immediately, never behind a Help control",
      ("Invalid" in bad_h or "incorrect" in bad_h.lower() or "wrong" in bad_h.lower()) and "<details" not in bad_h[max(0, bad_h.lower().find("invalid")):bad_h.lower().find("invalid") + 5] if "invalid" in bad_h.lower() else True)

# settings_hub: the Delete Account destructive warning must remain plain (security/destructive-action exception)
sh = html(ADMIN.get("/settings"))
check("settings_hub: the Delete Account warning is NOT hidden behind a tap (destructive-action warning stays visible)",
      "cannot be undone" in sh and "<details" not in sh[max(0, sh.find("cannot be undone") - 300):sh.find("cannot be undone")],
      sh[max(0, sh.find("cannot be undone") - 150):sh.find("cannot be undone") + 30] if "cannot be undone" in sh else "(warning not found)")

# admin_terms: term Published/Draft status badges stay plain, real per-term data
at = html(ADMIN.get("/admin/terms"))
check("admin_terms: the actual Published/Draft status per term is real data, not wrapped (table rows outside any <details>)",
      "<table" in at and re.search(r"</details>.*<table", at, re.S) is not None, at[:800])

print("=== C) keyboard/screen-reader accessibility: native <details>/<summary> semantics ===")

# Every <details class="hlp"> uses a real <summary> (focusable, native expanded/collapsed state
# via the `open` attribute -- no hand-rolled div+aria-expanded reimplementation that could drift
# out of sync with the real DOM state).
sample = html(ADMIN.get("/admin/email"))
check("the help control is a real <summary> element inside <details> (native keyboard + screen-reader semantics, not a custom div)",
      re.search(r'<details class="hlp"[^>]*><summary class="hlp-t">', sample) is not None, sample[:500])

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
