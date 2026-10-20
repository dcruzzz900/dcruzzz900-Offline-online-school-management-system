"""End-to-end scenarios for the V77 requirement: two items from Austin's direct feedback.

1. "On Broadsheet 1st CA appear on S/N column. Adjust it."
   Root cause (confirmed by reading the actual rendered layout, not guessed): the broadsheet's
   table has a genuine two-row rowspan/colspan header (S/N and Student span both header rows;
   each subject's "1st CA/2nd CA/Exam/Total" sits under that subject's own colspan'd heading).
   The sitewide mobile rule `table{display:block;overflow-x:auto;white-space:nowrap}` (added for
   plain single-header tables so they scroll horizontally on narrow screens) also caught this
   table — but display:block throws away the table's row/column grid entirely, so rowspan and
   colspan have nothing left to measure against, and the second header row's cells drift left
   until they land under S/N/Student instead of their own subject. The broadsheet already wraps
   its table in its own `overflow-x:auto` div for exactly this horizontal-scroll purpose, so the
   fix is to give this one table (`.bs-table`) its layout back at that breakpoint and let the
   existing wrapper do the scrolling, rather than reflowing it to blocks.
   Verified two ways: a static CSS check, and a live, real-headless-browser render at a phone
   viewport width reading every header cell's actual on-screen position — a plain HTTP fetch
   can't catch this (the HTML is identical broken or fixed; only the computed layout differs).

2. "When a principal or teacher set date on result sheet populate it to the whole of the result
   sheet for that particular term."
   A sign date is a one-time, whole-cohort event (the teacher/principal signs on one day, not a
   separate day per student). Per Austin's explicit scoping: the Class/Form Teacher's sign date,
   once set on any one student, now also applies to every OTHER student in that teacher's own
   class for that term; the Principal's sign date applies school-wide (every student, every
   class) for that term. Only the date (and who signed it) is touched on those other students —
   every other field of their own student_term_info row (comments, attendance, etc.) is left
   exactly as it was. A class whose result is currently locked (submitted/under_review/approved/
   published) is skipped by the bulk propagation, the same as the single-student save already
   refuses to touch a locked class.

(own process, fresh DB, real HTTP requests + real headless-browser rendering for item 1's
layout check). Run: python tests/v77_scenarios.py"""
import logging
import os
import re
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v77_")
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


pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.commit()
c0.close()

ADMIN = staff("admin")
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,9,9,0,23),(1,2,1,15,20,0,50)")
W.publish(A, 1)

# ============================================================ 1) broadsheet mobile header alignment
css = open(os.path.join(ROOT, "static", "css", "responsive-ui.css"), encoding="utf-8").read()
check("broadsheet.html's table is marked .bs-table so it can be exempted from the generic mobile rule",
      'class="bs-table"' in open(os.path.join(ROOT, "templates", "broadsheet.html"), encoding="utf-8").read())
check(".bs-table is given back display:table at the same breakpoint the generic rule collapses tables at",
      re.search(r"@media\(max-width:700px\)\{\.bs-table\{display:table", css) is not None, css[-400:])

try:
    from playwright.sync_api import sync_playwright

    PORT = 18677

    def _run_server():
        A.app.run(host="127.0.0.1", port=PORT, use_reloader=False)

    threading.Thread(target=_run_server, daemon=True).start()
    time.sleep(1.5)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Pass1234")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.set_viewport_size({"width": 375, "height": 800})
        page.goto(f"http://127.0.0.1:{PORT}/broadsheet/1?term_id=1")
        page.wait_for_load_state("networkidle")

        display = page.eval_on_selector(".bs-table", "el => getComputedStyle(el).display")
        check("at a phone viewport (375px), .bs-table keeps real table layout (not display:block)", display == "table", display)

        cells = page.eval_on_selector_all(
            ".bs-table th",
            "els => els.map(e => { const r = e.getBoundingClientRect(); return {text: e.textContent.trim(), left: Math.round(r.left), top: Math.round(r.top)}; })",
        )
        by_text_top = {(c["text"], c["top"]): c["left"] for c in cells}
        sn = next(c for c in cells if c["text"] == "S/N")
        basic_science = next(c for c in cells if c["text"] == "Basic Science")
        first_1st_ca = next(c for c in cells if c["text"] == "1st CA")
        check("S/N is in the header's top row", sn["top"] < first_1st_ca["top"], (sn, first_1st_ca))
        check("the first subject's '1st CA' sub-header sits under that subject's own column, not under S/N",
              first_1st_ca["left"] == basic_science["left"] and first_1st_ca["left"] != sn["left"],
              (first_1st_ca, basic_science, sn))

        browser.close()
except ImportError:
    print("Playwright not available in this environment -- skipping the live rendering check (static checks above still ran).")
except Exception as e:
    check("broadsheet live rendering check completed without an unexpected error", False, repr(e))

# ============================================================ 2) sign-date propagation
# Section 1 published class 1 / term 1 (to render totals/averages on the broadsheet), which locks
# comments/sign-off edits for that class per the approval workflow. Reset it back to draft here so
# this section can exercise an ordinary (non-locked) save -- this is independent of, and doesn't
# relax, the actual locked-class-skip behaviour under test below (that's a DIFFERENT, second class).
run("DELETE FROM result_publication WHERE school_id=1 AND class_id=(SELECT class_id FROM students WHERE id=1) AND term_id=1")

run("INSERT INTO classes (school_id, name) VALUES (1, 'V77 Open Second Class')")
open_class_id = one("SELECT id FROM classes WHERE name='V77 Open Second Class'")["id"]
run("INSERT INTO classes (school_id, name) VALUES (1, 'V77 Locked Second Class')")
locked_class_id = one("SELECT id FROM classes WHERE name='V77 Locked Second Class'")["id"]
run("INSERT INTO students (school_id, class_id, first_name, last_name, is_active, admission_no) VALUES (1,?, 'V77Open','Kid',1,'V77OPEN1')", (open_class_id,))
open_student_id = one("SELECT id FROM students WHERE admission_no='V77OPEN1'")["id"]
run("INSERT INTO students (school_id, class_id, first_name, last_name, is_active, admission_no) VALUES (1,?, 'V77Locked','Kid',1,'V77LOCK1')", (locked_class_id,))
locked_student_id = one("SELECT id FROM students WHERE admission_no='V77LOCK1'")["id"]
run("INSERT INTO result_publication (school_id, class_id, term_id, status) VALUES (1,?,?, 'published')", (locked_class_id, 1))

cls_1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]
classmates = [r["id"] for r in db().execute("SELECT id FROM students WHERE class_id=? AND is_active=1", (cls_1,)).fetchall()]
other_classmate = next((i for i in classmates if i != 1), None)
if other_classmate:
    run("INSERT INTO student_term_info (student_id, term_id, teacher_comment) VALUES (?,1,?) "
        "ON CONFLICT(student_id, term_id) DO UPDATE SET teacher_comment=excluded.teacher_comment",
        (other_classmate, "DO NOT TOUCH ME"))

r = post(ADMIN, "/result/1/extra", {
    "term_id": "1", "teacher_signed_date": "2026-10-18", "principal_signed_date": "2026-10-19",
    "teacher_comment": "fine", "principal_comment": "fine",
}, "/result/1?term_id=1")
check("the result-details save succeeded", r.status_code == 302, r.status_code)

rows = db().execute("SELECT student_id, teacher_signed_date, principal_signed_date, teacher_comment FROM student_term_info WHERE term_id=1").fetchall()
by_id = {row["student_id"]: row for row in rows}

check("the student directly edited has the teacher sign date", by_id.get(1) and by_id[1]["teacher_signed_date"] == "2026-10-18")
check("the student directly edited has the principal sign date", by_id.get(1) and by_id[1]["principal_signed_date"] == "2026-10-19")
for cm in classmates:
    if cm == 1:
        continue
    check(f"classmate {cm} (same class) got the teacher sign date propagated to them",
          by_id.get(cm) and by_id[cm]["teacher_signed_date"] == "2026-10-18", by_id.get(cm))
if other_classmate:
    check("a classmate's own, unrelated teacher_comment was preserved (propagation only touches the date/signer)",
          by_id.get(other_classmate) and by_id[other_classmate]["teacher_comment"] == "DO NOT TOUCH ME", by_id.get(other_classmate))

check("a student in a DIFFERENT, open class also got the principal sign date (school-wide scope)",
      by_id.get(open_student_id) and by_id[open_student_id]["principal_signed_date"] == "2026-10-19", by_id.get(open_student_id))
check("that different-class student did NOT get the teacher sign date (class-scoped only)",
      not by_id.get(open_student_id) or by_id[open_student_id]["teacher_signed_date"] != "2026-10-18", by_id.get(open_student_id))
check("a student in a LOCKED (published) class was skipped by the school-wide principal propagation",
      locked_student_id not in by_id, by_id.get(locked_student_id))

audit_rows = db().execute(
    "SELECT action, changes FROM rbac_audit_log WHERE action IN ('teacher_sign_date_applied_to_class','principal_sign_date_applied_to_school') ORDER BY id DESC LIMIT 5"
).fetchall()
check("both bulk-propagation actions were written to the audit log",
      {r["action"] for r in audit_rows} == {"teacher_sign_date_applied_to_class", "principal_sign_date_applied_to_school"}, [r["action"] for r in audit_rows])

# Saving again with the SAME dates must not re-propagate (no-op, no duplicate audit noise) --
# this also exercises that an unchanged date doesn't trigger a needless bulk write every save.
before_count = len(db().execute("SELECT 1 FROM rbac_audit_log WHERE action IN ('teacher_sign_date_applied_to_class','principal_sign_date_applied_to_school')").fetchall())
post(ADMIN, "/result/1/extra", {
    "term_id": "1", "teacher_signed_date": "2026-10-18", "principal_signed_date": "2026-10-19",
    "teacher_comment": "fine", "principal_comment": "fine",
}, "/result/1?term_id=1")
after_count = len(db().execute("SELECT 1 FROM rbac_audit_log WHERE action IN ('teacher_sign_date_applied_to_class','principal_sign_date_applied_to_school')").fetchall())
check("re-saving with an UNCHANGED date does not re-trigger the bulk propagation", after_count == before_count, (before_count, after_count))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
