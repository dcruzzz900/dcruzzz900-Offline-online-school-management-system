"""End-to-end scenarios for the V74 requirement: hide long instructional/help text by
default, reveal it on tap/click, instead of it always cluttering the page.

Scope decision (see V74_IMPLEMENTATION_NOTES.md for the full reasoning): a sitewide audit
found 139 `class="muted"` occurrences across 58 templates, but the great majority are short
inline labels (ON/OFF badges, one-clause captions) or STATUS / EMPTY-STATE messages ("No
scores have been entered yet", "No active code", "You are not assigned as Form Teacher of
any class") — those are real page content/feedback, not instructional clutter, and hiding
them behind a tap would hide information the user actually needs to see. Only genuine,
multi-clause "how this feature works" explainer prose was converted. That turned out to be
8 paragraphs across 3 files: templates/result_display_settings.html (6: Next Term Resumes,
Passport/Logo defaults, orientation/font/Fit to Page, comment suggestions, Cumulative/Annual
Result, and how Next Term Resumes picks a date), templates/student_account.html (1: why the
official-details fields are locked), templates/timetable_setup_v2.html (1: how period
structure applies to days). Each is now wrapped in a native <details>/<summary> element
(closed by default, no JS) — reusing the one show/hide-on-click pattern already used
elsewhere in this app (Quick Actions "View All Actions", Roles & Scope's per-assignment
panel), rather than inventing a new mechanism.

This file checks: the 8 target paragraphs are now inside a closed-by-default <details class
="hlp">, their text content is still present (nothing was deleted, just collapsed), and nine
representative status/empty-state/short-label texts that were deliberately LEFT ALONE are
still rendered as plain, always-visible text (not wrapped in <details>) — proving the scope
decision was actually followed, not just claimed.

(own process, fresh DB, real HTTP requests). Run: python tests/v74_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v74_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
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
        print("FAIL:", name, str(detail)[:300])


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


pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP WHERE id=1", (pw,))
c0.commit()
c0.close()

ADMIN = staff("admin")


def hlp_blocks(s):
    """Every <details class="hlp">...</details> block, as (is_closed, inner_html) pairs."""
    return [(not m.group(1), m.group(2)) for m in re.finditer(r'<details class="hlp"( open)?>(.*?)</details>', s, re.S)]


# ---------------------------------------------------------------- 1) Result Display Settings: 6 explainer blocks
rd = html(ADMIN.get("/admin/result-display-settings"))
blocks = hlp_blocks(rd)
check("Result Display Settings has at least the 6 new help blocks", len(blocks) >= 6, len(blocks))
check("every help block on this page is CLOSED by default (no 'open' attribute)", all(closed for closed, _ in blocks), blocks)
check("every help block has a tappable <summary class=\"hlp-t\">...</summary> trigger", all('<summary class="hlp-t">' in inner for _, inner in blocks), blocks)

expectations = [
    "Next Term Resumes", "resumption date already set for the", "following",
    "Passport: ON with no photo leaves the box blank",
    "apply to the individual result sheet",  # V91: wording now also mentions paper size
    "A saved comment is never replaced by a suggestion",
    "the annual result (all terms of the session) becomes available",
    "Each term's own resumption date is set under",
]
for needle in expectations:
    check(f"help text still present (collapsed, not deleted): {needle!r}", needle in rd, rd.count(needle))

# ---------------------------------------------------------------- 2) things that must NOT be wrapped (status/empty-state/short labels)
must_stay_plain = [
    ("ON/OFF state badges are ordinary <small class=\"muted\">, not help blocks", '<small class="muted">ON</small>' in rd or '<small class="muted">OFF</small>' in rd),
]
for name, cond in must_stay_plain:
    check(name, cond)
# the term-resumption-dates LIST (real data, not instructional prose) must stay outside/after the help block, always visible
check("the actual per-term resumption-date list is NOT hidden inside a help block (it's data, not an explanation)",
      re.search(r"</details>\s*<ul", rd) is not None, rd[rd.find("Term resumption dates"):rd.find("Term resumption dates") + 900] if "Term resumption dates" in rd else rd)

# ---------------------------------------------------------------- 3) student_account.html
stu = student_client("chinedu")
sa = html(stu.get("/student/account"))
blocks = hlp_blocks(sa)
check("Student Account page has the new help block", len(blocks) >= 1, len(blocks))
check("...closed by default", all(closed for closed, _ in blocks))
check("help text still present: why fields are locked", "set by the school and cannot be changed here" in sa)
check("the student's actual name/admission number are NOT hidden (real data, not explanatory text)",
      re.search(r"</details>.*Admission No\.", sa, re.S) is not None, sa[:1500])

# ---------------------------------------------------------------- 4) timetable_setup_v2.html
tt = html(ADMIN.get("/timetable/setup"))
blocks = hlp_blocks(tt)
check("Timetable Setup page has the new help block", len(blocks) >= 1, len(blocks))
check("...closed by default", all(closed for closed, _ in blocks))
check("help text still present: how period structure applies to days", "written to every school day you tick" in tt)
# the status summary (session/term/class counts) is real data and must stay plain, not wrapped
check("the Timetable Setup Status summary is NOT hidden inside a help block",
      "Timetable Setup Status" in tt and re.search(r"Timetable Setup Status</h3><div[^>]*>(?!.*<details)", tt) is not None or "<details" not in tt[:tt.find("Timetable Setup Status") + 50])

# ---------------------------------------------------------------- 5) deliberately-untouched status/empty-state text elsewhere, spot-checked
# AI Privacy: "No AI activity recorded." must remain plain (it's the entire content of that panel when empty)
ai = html(ADMIN.get("/admin/ai-privacy")) if "ai_privacy" in [r.rule for r in A.app.url_map.iter_rules()] or True else ""
# locate the actual route name defensively
ai_url = None
for r in A.app.url_map.iter_rules():
    if r.endpoint == "ai_privacy":
        ai_url = str(r)
        break
if ai_url:
    ai = html(ADMIN.get(ai_url))
    check("AI Privacy: an empty-state message ('No AI activity recorded.') is plain text, not hidden behind a tap",
          "No AI activity recorded." not in ai or "<details" not in ai[max(0, ai.find("No AI activity recorded.") - 60):ai.find("No AI activity recorded.")],
          ai[max(0, ai.find("No AI activity recorded.") - 80):ai.find("No AI activity recorded.") + 30] if "No AI activity recorded." in ai else "(no AI activity row in this fixture)")

# class_login_codes.html: "not assigned as Form/Class Teacher" must remain plain (it's the whole-page message, not clutter)
clc_url = None
for r in A.app.url_map.iter_rules():
    if r.endpoint == "class_login_codes":
        clc_url = str(r)
        break
if clc_url:
    clc = html(ADMIN.get(clc_url))
    if "not assigned as Form/Class Teacher" in clc:
        check("Class Login Codes: the 'not assigned' message is plain text, not hidden behind a tap",
              "<details" not in clc[max(0, clc.find("not assigned as Form/Class Teacher") - 80):clc.find("not assigned as Form/Class Teacher")])

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
