"""End-to-end scenarios for the V68 requirement: annual/cumulative calculation
correctness, specifically that "Overall Position" (on the term broadsheet, the
cumulative/annual broadsheet, and a student's own result sheet) uses standard
competition ranking (1,2,2,4 — tied students share a position) instead of a
strict count that silently breaks ties apart, so it never disagrees with the
subject-level positions shown right next to it, which were already tie-aware.
(own process, fresh DB, real HTTP requests). Run: python tests/v68_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v68_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
from db import get_db, get_result_display
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


def one(sql, args=()):
    c = db()
    try:
        r = c.execute(sql, args).fetchone()
        return r[0] if r is not None else None
    finally:
        c.close()


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


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
# Default fixture: class JSS1A has students 1 (Obi Chinedu), 2 (Eze Amaka), 3 (Bakare Tunde)
# and subjects Mathematics(1)/English(2)/Basic Science(3)/Social Studies(4).
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', (SELECT session_id FROM terms WHERE id=1), 0)")
term2 = c0.execute("SELECT id FROM terms WHERE name='2nd Term'").fetchone()[0]
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
get_result_display(c0, 1)  # lazily creates the row so the toggle UPDATE below actually lands
c0.execute("UPDATE result_display_settings SET show_subject_position=1 WHERE school_id=1")
c0.commit()
c0.close()

ADMIN = staff("admin")

# Student 1 and 2 tie for the top total in Term 1; student 3 is clearly behind.
# (ca1+ca2+ca3+exam, no scaling — compute_total just sums them.)
for sid, ca1, ca2, ca3, exam in [(1, 20, 20, 10, 40), (2, 18, 18, 14, 40), (3, 10, 10, 5, 30)]:
    run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,1,1,?,?,?,?)", (sid, ca1, ca2, ca3, exam))
# totals: student1=90, student2=90, student3=55 -> expect positions 1,1,3


def broadsheet_html(term_id=1):
    r = ADMIN.get(f"/broadsheet/1?term_id={term_id}")
    assert r.status_code == 200, r.status_code
    return html(r)


def result_html(student_id, term_id=1):
    r = ADMIN.get(f"/result/{student_id}?term_id={term_id}")
    assert r.status_code == 200, r.status_code
    return html(r)


def row_cells(page, admission_no_fragment):
    """Grab the row of a broadsheet/cumulative table containing a given marker, as plain text."""
    for block in re.findall(r"<tr>.*?</tr>", page, re.S):
        if admission_no_fragment in block:
            return re.sub(r"<[^>]+>", "|", block)
    return ""


# ---------------------------------------------------------------- scenarios

# 1) Term broadsheet: tied top-two students share position 1; the third (clearly behind) is 3rd, not 2nd.
bs1 = broadsheet_html(1)
check("Obi Chinedu (tied top) is position 1 on the term broadsheet", "|1|" in row_cells(bs1, "Obi Chinedu"))
check("Eze Amaka (tied top) is ALSO position 1, not 2", "|1|" in row_cells(bs1, "Eze Amaka"))
check("Bakare Tunde (clearly behind) is position 3, not 2", "|3|" in row_cells(bs1, "Bakare Tunde"))

# 2) Each tied student's own result sheet shows the same tie-aware "Overall Position".
s1 = result_html(1, 1)
s2 = result_html(2, 1)
s3 = result_html(3, 1)
check("student 1's result sheet shows Overall Position 1st", "1st" in s1)
check("student 2's result sheet ALSO shows Overall Position 1st (not 2nd)", "1st" in s2 and "2nd" not in s2.split("Overall Position")[1][:80] if "Overall Position" in s2 else False)
check("student 3's result sheet shows Overall Position 3rd (not 2nd)", "3rd" in s3)

# 3) This matches the subject-level position convention, which was already tie-aware:
#    both tied students are 1st in Mathematics too.
check("subject position for the tied students is ALSO 1st (consistent convention)",
      s1.split("Mathematics")[1][:400].count("1st") >= 1 and s2.split("Mathematics")[1][:400].count("1st") >= 1)

# 4) A clean, untied Term 2 case still ranks 1,2,3 as before (no regression for the normal case).
for sid, ca1, ca2, ca3, exam in [(1, 20, 20, 10, 40), (2, 15, 15, 10, 35), (3, 10, 10, 5, 30)]:
    run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,1,?,?,?,?,?)", (sid, term2, ca1, ca2, ca3, exam))
bs2 = broadsheet_html(term2)
check("no ties -> strictly 1,2,3 as before", "|1|" in row_cells(bs2, "Obi Chinedu") and "|2|" in row_cells(bs2, "Eze Amaka") and "|3|" in row_cells(bs2, "Bakare Tunde"))

# 5) Annual/cumulative broadsheet: the same tie, now averaged across two terms (term1 tie + term2 not-tied),
#    still ends up tied overall because both terms' totals for students 1 & 2 average out equal.
#    (term1: 90 vs 90 tie; term2: 90 vs 75 -> not tied; cumulative average per subject: (90+90)/2=90 vs (90+75)/2=82.5 -> NOT a tie this time)
#    V80 made the cumulative broadsheet "based on the selected term" (consolidating only up through
#    whichever term is asked for) instead of always silently aggregating every term that happens to
#    have data -- so to consolidate BOTH terms here, term_id must be passed explicitly as term2.
cbs = ADMIN.get(f"/cumulative/1?term_id={term2}").get_data(as_text=True)
check("cumulative broadsheet renders", "Cumulative" in cbs or "cumulative" in cbs.lower())
check("cumulative positions are still strictly ordered here (no false tie introduced)",
      "|1|" in row_cells(cbs, "Obi Chinedu") and "|2|" in row_cells(cbs, "Eze Amaka"))

# 6) Now force an actual cumulative tie between two different students across both terms, and confirm
#    the overall ("annual") position ties correctly rather than breaking it apart arbitrarily.
run("UPDATE scores SET ca1=20,ca2=20,ca3=10,exam=40 WHERE student_id=2 AND subject_id=1 AND term_id=?", (term2,))
cbs2 = ADMIN.get(f"/cumulative/1?term_id={term2}").get_data(as_text=True)
check("cumulative broadsheet: equal cumulative averages share position 1", "|1|" in row_cells(cbs2, "Obi Chinedu") and "|1|" in row_cells(cbs2, "Eze Amaka"))
check("...and the third student (behind) is position 3, not 2", "|3|" in row_cells(cbs2, "Bakare Tunde"))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
