"""End-to-end scenarios for V94: Academic Performance and Cumulative / Annual Performance are now
mutually exclusive on every result-sheet design, per your explicit request after seeing a correctly
-themed sheet that showed both at once:

  "When Cumulative/Annual performance is toggled on, use this interface exactly for result sheet,
   but if it is turn off academic performance should show. Do not show both Cumulative/Annual
   performance and academic performance on one result sheet when Cumulative/Annual performance is
   toggled on."

Scope: the per-term "Academic Performance" subject-score table (CA1/CA2/[CA3]/Exam/Total for the
CURRENT term only) is the thing that duplicates the Cumulative/Annual Performance table once that's
switched on and has data -- so it, specifically, is what's hidden. Everything else that was already
shown alongside Academic Performance (attendance, domain ratings, teacher/principal comments,
signatures, grading/domain keys, and each bespoke design's own secondary summary boxes) is left
exactly as it was: still visible, same as the screenshot you sent showing a correctly-combined
sheet. This matches the generic template's existing section boundaries (rs-perf is its own
<section>, separate from rs-domains/rs-att/rs-comments/etc.) and extends the same boundary to each
of the 6 bespoke `templates/sheets/*.html` designs.

The condition used everywhere is identical by construction -- `cumulative and cumulative.terms` --
the exact same expression _cumulative_breakdown.html has always self-guarded on, so the Academic
Performance table and the Cumulative table can never both show, and can never both hide, for the
same reason _cumulative_breakdown.html already uses (cumulative results off for the school, or on
but no term data recorded yet).

(own process, fresh DB, real HTTP requests). Run: python tests/v94_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v94_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db, RESULT_TEMPLATES
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


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
session_id = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (session_id,))
term1 = 1
term2 = c0.execute("SELECT id FROM terms WHERE name='2nd Term'").fetchone()[0]
c0.commit()
c0.close()

# Student 1, class 1: scores for term1 AND term2 so cumulative has real, multi-term data.
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,20,20,0,40)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,10,10,0,20)", (term2,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,25,25,0,50)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,15,15,0,30)", (term2,))
W.publish(A, term1)
W.publish(A, term2)

ADMIN = staff("admin")


def set_template(key, cumulative=True):
    # cumulative_enabled is a checkbox: like every other checkbox in this form, the field must be
    # OMITTED entirely to turn it off (a browser never submits an unchecked checkbox) -- posting
    # the literal string "0" is still a truthy, present value server-side and would turn it ON.
    data = {
        "template": key, "title": "Terminal Report Sheet",
        "accent_color": "#1f3a5f", "secondary_color": "#0b3b75", "header_layout": "logo-left",
        "text_align": "center", "signature_layout": "split", "pdf_font": "Helvetica",
        "page_orientation": "portrait", "font_scale": "normal",
        "show_address": "1", "show_phone": "1", "show_email": "1",
    }
    if cumulative:
        data["cumulative_enabled"] = "1"
    post(ADMIN, "/admin/result-display-settings", data, "/admin/result-display-settings")


# Per-template "this is the per-term Academic Performance table" marker, and (for the 4 generic
# styles) the exact heading text -- distinct from clean_midterm_report's own "Academic Performance
# (...% Base)" heading, which carries a different, non-colliding exact string.
MARKERS = {
    "professional_classic": ('<h3 class="rs-h">Academic Performance</h3>', 'class="rs-perf"'),
    "modern_academic": ('<h3 class="rs-h">Academic Performance</h3>', 'class="rs-perf"'),
    "compact_academic": ('<h3 class="rs-h">Academic Performance</h3>', 'class="rs-perf"'),
    "minimal_clean": ('<h3 class="rs-h">Academic Performance</h3>', 'class="rs-perf"'),
    "assessment_dossier": ('rsx-dos-table', 'rsx-dos-table'),
    "boxed_grey_card": ('rsx-grey-table', 'rsx-grey-table'),
    "clean_midterm_report": ('Academic Performance (', 'rsx-cln-table'),
    "green_cumulative_report": ('rsx-grn-table', 'rsx-grn-table'),
    "peach_terminal_sheet": ('rsx-peach-table', 'rsx-peach-table'),
    "progress_report_card": ('rsx-prc-table', 'rsx-prc-table'),
}
CUMULATIVE_MARKERS = ("Cumulative / Annual Performance", "rs-cum-table")

print("=== 1) Cumulative ON (with real multi-term data): Academic Performance hidden, Cumulative shown ===")

for key, (heading_needle, table_needle) in MARKERS.items():
    set_template(key, cumulative=True)
    page = html(ADMIN.get(f"/result/1/print?term_id={term2}"))
    check(f"[{key}] Cumulative / Annual Performance heading IS shown", all(m in page for m in CUMULATIVE_MARKERS), key)
    check(f"[{key}] the per-term Academic Performance table is NOT shown", heading_needle not in page and table_needle not in page, key)

print("=== 2) Cumulative OFF: Academic Performance shown (today's default, unchanged), Cumulative absent ===")

for key, (heading_needle, table_needle) in MARKERS.items():
    set_template(key, cumulative=False)
    page = html(ADMIN.get(f"/result/1/print?term_id={term2}"))
    check(f"[{key}] the per-term Academic Performance table IS shown", heading_needle in page and table_needle in page, key)
    check(f"[{key}] Cumulative / Annual Performance is absent", not any(m in page for m in CUMULATIVE_MARKERS), key)

print("=== 3) Cumulative ON for a student with no scores anywhere: still Cumulative, not Academic Performance -- `show_cumulative` tracks _cumulative_breakdown.html's own pre-existing self-guard exactly, rather than inventing a different rule ===")

# A brand-new student with zero scores anywhere: cumulative.terms is the session's list of TERM
# NAMES (not score data), so it's still non-empty even with nothing recorded -- exactly the same
# as how _cumulative_breakdown.html has always behaved (it renders an all-"-" cumulative table
# rather than nothing). Our new `show_cumulative` flag uses that identical expression on purpose,
# so it can never disagree with what the cumulative section itself decides to show.
c = db()
cur = c.cursor()
cur.execute("SELECT class_id, admission_no FROM students WHERE id=1")
cls = cur.fetchone()
cur.execute(
    "INSERT INTO students (class_id, first_name, last_name, admission_no, gender) VALUES (?, 'NoData', 'Student', 'ND-001', 'M')",
    (cls["class_id"],),
)
new_student_id = cur.lastrowid
c.commit()
c.close()

run("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
set_template("professional_classic", cumulative=True)
nodata_page = html(ADMIN.get(f"/result/{new_student_id}/print?term_id={term1}"))
check("a student with no scores anywhere still gets the Cumulative / Annual Performance section (an all-'-' table, same as _cumulative_breakdown.html has always rendered for them)",
      "Cumulative / Annual Performance" in nodata_page and "rs-cum-table" in nodata_page, nodata_page[:300])
check("...and correspondingly, the duplicate per-term Academic Performance table stays hidden for them too",
      '<h3 class="rs-h">Academic Performance</h3>' not in nodata_page and 'class="rs-perf"' not in nodata_page)

print("=== 4) Every include of _cumulative_breakdown.html stays unconditional in the template source (it already self-guards) ===")

sheets_dir = os.path.join(ROOT, "templates", "sheets")
for fn in ("assessment_dossier.html", "boxed_grey_card.html", "clean_midterm_report.html",
           "green_cumulative_report.html", "peach_terminal_sheet.html", "progress_report_card.html"):
    with open(os.path.join(sheets_dir, fn)) as f:
        src = f.read()
    check(f"[{fn}] still includes _cumulative_breakdown.html unconditionally", '{% include "_cumulative_breakdown.html" %}' in src, fn)
with open(os.path.join(ROOT, "templates", "_result_sheet.html")) as f:
    rs_src = f.read()
check("[_result_sheet.html] still includes _cumulative_breakdown.html unconditionally too", '{% include "_cumulative_breakdown.html" %}' in rs_src)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
