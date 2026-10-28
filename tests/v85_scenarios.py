"""End-to-end scenarios for V85: the three smaller follow-ups Austin asked to continue with after
the ninth requirements document ("Consolidated Development Specification") closed out at V84 --

  A) parent/student-facing cumulative results (self-service, mirroring the existing per-term
     result pattern, with a NEW publication gate scoped to the cutoff term -- the staff-only
     cumulative route deliberately has no such gate, but a self-service one must).
  B) full Result Display Settings customization on the cumulative pages (accent/secondary colors,
     logo, watermark, footer -- threaded in via the existing result_sheet_settings(), the same
     function the regular per-term result already used for this).
  C) automatic portrait/landscape orientation switching for one-page printing ('auto', a third
     page_orientation value) -- a genuine dual-orientation measurement done by the browser itself
     (decideOrientation() in result_print.html / cumulative_result_print.html), not a heuristic.
     This was deliberately deferred twice before (V73, V79) for exactly this reason.

(own process, fresh DB, real HTTP requests). Run: python tests/v85_scenarios.py"""
import io
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v85_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db, PAGE_ORIENTATIONS
from werkzeug.security import generate_password_hash

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

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


def pdf_is_landscape(data):
    r = PdfReader(io.BytesIO(data))
    box = r.pages[0].mediabox
    return float(box.width) > float(box.height)


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
session_id = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (session_id,))
term2 = c0.execute("SELECT id FROM terms WHERE name='2nd Term'").fetchone()[0]
c0.commit()
c0.close()
term1 = 1

# Student 1 (class 1): scores for term1 and term2, subjects 1 (Mathematics) and 2 (English Language).
run("DELETE FROM scores WHERE student_id=1")
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,20,20,0,40)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,10,10,0,20)", (term2,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,25,25,0,50)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,15,15,0,30)", (term2,))

# A student login for student 1, and a verified parent for student 1.
run("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP, parent_email='obi.parent@example.com' WHERE id=1", (pw,))
school_row = one("SELECT tenant_id FROM schools WHERE id=1")
tenant_id = school_row["tenant_id"]
run("INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,email) VALUES(1,?,'Mr Obi','obiparent',?,'obi.parent@example.com')", (tenant_id, pw))
obi_parent_id = one("SELECT id FROM parent_accounts WHERE username='obiparent'")["id"]
run("INSERT INTO parent_students(parent_id,student_id,school_id,tenant_id,status,verified_at) VALUES(?,1,1,?,'verified',CURRENT_TIMESTAMP)", (obi_parent_id, tenant_id))

ADMIN = staff("admin")
# result_display_settings is created lazily (INSERT OR IGNORE) the first time it's read -- touch it
# once so the direct SQL UPDATEs below have a row to act on (same fixture pattern as v73_scenarios.py).
ADMIN.get("/admin/result-display-settings")

# Set some distinctive Result Display Settings so Item B's theming is actually observable.
run("UPDATE result_display_settings SET accent_color='#8822cc', secondary_color='#11aa66', "
    "watermark_text='CONFIDENTIAL', show_watermark=1, footer_text='Issued by My School Hub' WHERE school_id=1")

W.publish(A, term1)
W.publish(A, term2)

print("=== A) parent/student-facing cumulative results ===")

# ---------------------------------------------------------------- unpublished cumulative term is blocked for self-service...
W.unpublish(A, term2)
STU = student_client("chinedu")
r_unpub = STU.get(f"/student/cumulative?session_id={session_id}&term_id={term2}")
check("student cumulative view is blocked while the cutoff term isn't published, even though an earlier term in the same session is",
      r_unpub.status_code in (302, 403) or "isn't published" in html(r_unpub).lower(), r_unpub.status_code)
W.publish(A, term2)

# ---------------------------------------------------------------- ...but works once published
r_stu = STU.get(f"/student/cumulative?session_id={session_id}&term_id={term2}")
check("student can view their own cumulative result once the cutoff term is published", r_stu.status_code == 200, r_stu.status_code)
check("...and it shows both terms' columns", "1st Term" in html(r_stu) and "2nd Term" in html(r_stu))

r_stu_pdf = STU.get(f"/student/cumulative/pdf?session_id={session_id}&term_id={term2}")
check("student can download their own cumulative result PDF", r_stu_pdf.status_code == 200 and r_stu_pdf.data[:4] == b"%PDF", r_stu_pdf.status_code)

# A student cannot reach a classmate's cumulative result data via /student/cumulative -- the route
# takes no student_id at all, it's always session["student_id"], so there's nothing to tamper with
# in the URL; confirmed instead that the data returned is genuinely student 1's, not student 2's.
check("the student cumulative page shows student 1's own admission number, not someone else's",
      one("SELECT admission_no FROM students WHERE id=1")["admission_no"] in html(r_stu))

# ---------------------------------------------------------------- parent self-service
PARENT = parent_client("obiparent")
r_par = PARENT.get(f"/parent/children/1/cumulative?session_id={session_id}&term_id={term2}")
check("verified parent can view their child's cumulative result", r_par.status_code == 200, r_par.status_code)
check("...and it shows both terms' columns too", "1st Term" in html(r_par) and "2nd Term" in html(r_par))

r_par_pdf = PARENT.get(f"/parent/children/1/cumulative/pdf?session_id={session_id}&term_id={term2}")
check("parent can download the child's cumulative result PDF", r_par_pdf.status_code == 200 and r_par_pdf.data[:4] == b"%PDF", r_par_pdf.status_code)

# An unverified parent (no parent_students link at all) must be denied student 1's cumulative data.
run("INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,email) VALUES(1,?,'Stranger','strangerparent',?,'stranger@example.com')", (tenant_id, pw))
STRANGER = parent_client("strangerparent")
r_stranger = STRANGER.get(f"/parent/children/1/cumulative?session_id={session_id}&term_id={term2}")
check("a parent with no verified link to student 1 cannot view student 1's cumulative result",
      r_stranger.status_code in (302, 403) or "not found" in html(r_stranger).lower() or "not linked" in html(r_stranger).lower(),
      r_stranger.status_code)

# ---------------------------------------------------------------- "View cumulative result" links on the per-term pages
r_stu_result = STU.get(f"/student/result/{term2}")
check('student_result.html shows a "View cumulative result" link when cumulative is enabled',
      "cumulative" in html(r_stu_result).lower() and "/student/cumulative" in html(r_stu_result), html(r_stu_result)[:3000])
r_par_result = PARENT.get(f"/parent/children/1/result/{term2}")
check('parent_result.html shows a "View cumulative result" link when cumulative is enabled',
      "/parent/children/1/cumulative" in html(r_par_result), html(r_par_result)[:3000])

print("=== B) full Result Display Settings customization on the cumulative pages ===")

r_cum = ADMIN.get(f"/cumulative/student/1?session_id={session_id}&term_id={term2}")
h_cum = html(r_cum)
check("the staff cumulative result page now applies the school's accent color", "#8822cc" in h_cum, h_cum[:3000])
check("...and the watermark text", "CONFIDENTIAL" in h_cum, h_cum[:3000])
check("...and the footer text", "Issued by My School Hub" in h_cum, h_cum[:3000])

r_cum_print = ADMIN.get(f"/cumulative/student/1/print?session_id={session_id}&term_id={term2}")
check("the new cumulative print view loads", r_cum_print.status_code == 200, r_cum_print.status_code)
h_cum_print = html(r_cum_print)
check("...and it's themed the same way (accent color)", "#8822cc" in h_cum_print, h_cum_print[:3000])
check("...and carries the same Fit-to-Page/orientation JS the regular result's print page uses",
      "function decideOrientation()" in h_cum_print and "var RS_ORIENTATION" in h_cum_print)

r_cum_pdf = ADMIN.get(f"/cumulative/student/1/pdf?session_id={session_id}&term_id={term2}")
check("the cumulative result PDF (now built via the HTML/Chromium path, not the old ReportLab builder) still generates",
      r_cum_pdf.status_code == 200 and r_cum_pdf.data[:4] == b"%PDF", r_cum_pdf.status_code)

bs_cum = ADMIN.get(f"/cumulative/{one('SELECT class_id FROM students WHERE id=1')['class_id']}?session_id={session_id}&term_id={term2}")
check("the cumulative broadsheet also picks up the school's accent color", "#8822cc" in html(bs_cum), html(bs_cum)[:3000])
check("...and the footer text", "Issued by My School Hub" in html(bs_cum), html(bs_cum)[:3000])

print("=== C) automatic portrait/landscape orientation switching ===")

check("PAGE_ORIENTATIONS now offers a third 'auto' choice", any(v == "auto" for v, _l in PAGE_ORIENTATIONS), PAGE_ORIENTATIONS)

r_settings = ADMIN.get("/admin/result-display-settings")
check("the admin settings page offers 'auto' as a Page orientation option", 'value="auto"' in html(r_settings), html(r_settings)[:3000])

# The whitelist gate in result_sheet_settings() (the exact bug this round found and fixed) --
# without this fix, saving 'auto' would have silently reverted to 'portrait' everywhere it's read.
run("UPDATE result_display_settings SET page_orientation='auto' WHERE school_id=1")
s_auto = html(ADMIN.get("/result/1/print?term_id=1"))
check("page_orientation='auto' is NOT coerced back to 'portrait' by result_sheet_settings()",
      "var RS_ORIENTATION = \"auto\"" in s_auto, s_auto)
check("...and the auto-orientation decision function is present on the print page", "function decideOrientation()" in s_auto)

s_cum_auto = html(ADMIN.get(f"/cumulative/student/1/print?session_id={session_id}&term_id={term2}"))
check("page_orientation='auto' also reaches the cumulative print page", "var RS_ORIENTATION = \"auto\"" in s_cum_auto, s_cum_auto)

# Genuine dual-orientation measurement, run for real through Chromium (html_pdf.render_documents),
# not just a JS-presence check: a normal-sized result stays portrait...
pdf_normal = ADMIN.get("/result/1/pdf?term_id=1")
check("a normal-sized result, with orientation='auto', renders as a portrait PDF",
      pdf_normal.status_code == 200 and not pdf_is_landscape(pdf_normal.data), pdf_normal.status_code)

# ...but a result engineered to overflow MUCH more in portrait than landscape is measured by the
# browser itself to fit better in landscape, and decideOrientation() picks it -- this is the "real
# dual-orientation zoom measurement, not a heuristic" V79 deferred this for. A single long comment
# paragraph can never save enough height to flip it (it's capped at half the page width by the
# 2-column comments grid); a genuinely WIDE cumulative table does: 3 terms x (this class's 4
# existing + 4 new) long-named subjects, which saves well over the ~29% margin decideOrientation()
# requires. (V87: the cumulative section now shows every term's full CA1/CA2/[CA3]/Exam/Total
# breakdown, not just one running-total column per term -- several times wider per term than
# before -- so this used to need 10 terms x 8 long-named subjects to tip the scale; now 3 terms x
# 4 does, and 10 x 8 so overloads even a landscape page with unavoidable per-term columns that
# portrait and landscape end up equally (not differently) squeezed, which no longer exercises the
# thing this check is about.) Verified end-to-end through the real route with pypdf's mediabox.
c0 = db()
extra_term_ids = []
for i in range(3, 4):  # term 3, on top of the existing term1/term2 -- 3 terms total
    c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?, ?, 0)", (f"{i}th Term", session_id))
    extra_term_ids.append(c0.execute("SELECT id FROM terms WHERE name=?", (f"{i}th Term",)).fetchone()[0])
c0.commit()
c0.close()
all_wide_term_ids = [term1, term2] + extra_term_ids

class_id_1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]
wide_subject_ids = []
for i in range(1, 5):  # 4 long-named subjects (on top of the class's existing 4) -- empirically
                        # the smallest set, under this school's REAL Result Display Settings
                        # (accent colors, watermark, footer -- all turned on earlier in this fixture
                        # for item B), that genuinely crosses decideOrientation()'s margin
    sname = f"A Very Long Subject Name That Really Wraps Across Many Many Separate Lines Of Text When The Page Is Narrow Like Portrait {i}"
    run("INSERT INTO subjects(school_id, name) VALUES(1, ?)", (sname,))
    sid = one("SELECT id FROM subjects WHERE school_id=1 AND name=?", (sname,))["id"]
    wide_subject_ids.append(sid)
    run("INSERT INTO class_subjects(class_id, subject_id) VALUES(?, ?)", (class_id_1, sid))
    for t in all_wide_term_ids:
        run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,20,20,0,40)", (sid, t))

for t in extra_term_ids:
    W.publish(A, t)

last_wide_term = extra_term_ids[-1]
pdf_wide = ADMIN.get(f"/cumulative/student/1/pdf?session_id={session_id}&term_id={last_wide_term}")
check("a cumulative result wide enough (3 terms x many long-named subjects) to genuinely overflow far more in portrait than landscape is measured and switched to a landscape PDF",
      pdf_wide.status_code == 200 and pdf_is_landscape(pdf_wide.data), pdf_wide.status_code)

pdf_normal_again = ADMIN.get("/result/1/pdf?term_id=1")
check("...while an ordinary, unmodified single-term result still stays portrait under the same 'auto' setting",
      pdf_normal_again.status_code == 200 and not pdf_is_landscape(pdf_normal_again.data), pdf_normal_again.status_code)

run("UPDATE result_display_settings SET page_orientation='portrait' WHERE school_id=1")

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
