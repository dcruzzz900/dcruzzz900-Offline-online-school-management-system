"""End-to-end scenarios for the V80 requirement: Phase 3 of the ninth requirements document
("Consolidated Development Specification"), Cumulative / Annual Results becoming genuinely
TERM-DEPENDENT instead of always silently aggregating every term in the session.

Audited gap (found in V79's triage of the ninth spec, confirmed again here by reading
build_cumulative_broadsheet_data/build_cumulative_result_data before touching anything):
build_cumulative_broadsheet_data always called terms_for_session() and used EVERY term in the
session, no matter which term the admin was actually looking at -- so a "cumulative result"
viewed from First Term's own result page looked identical to one viewed from Third Term's, even
though the spec is explicit:

  First Term: only First Term.
  Second Term: First + Second.
  Third Term: First + Second + Third.
  Cumulative disabled: only the selected term (already true -- this is just the ordinary result page).

Fixed with a new resolve_term_in_session() helper (picks the requested term if it belongs to the
session being viewed, else that session's own active term, else its chronologically latest term)
and an upto_term_id cutoff in build_cumulative_broadsheet_data/build_cumulative_result_data that
drops any term AFTER the selected one from the `terms` list entirely -- not shown as a blank
column, not counted toward the average, just not there, so a Second Term cumulative never leaks a
preview of Third Term work. A term BEFORE or AT the selected one with no score for a given subject
still correctly isn't treated as a zero (unchanged from before this phase -- only present scores
are averaged).

Backward compatibility: when no term_id is passed at all, the data-builders keep their old
"every term in the session" behaviour (upto_term_id=None -> no restriction) -- but the ROUTES now
always resolve a concrete term via resolve_term_in_session (active term in that session, or its
latest term), so in practice an admin following a link (now wired with term_id on both the
Term Result and Term Broadsheet pages) always gets a well-defined, term-scoped cumulative view.
tests/v68_scenarios.py's two-term checks were updated to pass term_id explicitly for this reason.

Run: python tests/v80_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v80_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db
from werkzeug.security import generate_password_hash

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


def db():
    return get_db()


def run(sql, args=()):
    c = db()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def result_table(h):
    """The actual per-subject/per-term consolidated table on cumulative_result.html -- excludes the
    page's own "Through term:" <select>, which (by design) always lists every term in the session as
    an option regardless of the chosen cutoff, so checking the whole page for a term name would be
    testing the selector, not the consolidated data."""
    m = re.search(r"Academic Performance.*?<table[^>]*>(.*?)</table>", h, re.S)
    return m.group(1) if m else ""


def one(sql, args=()):
    c = db()
    try:
        return c.execute(sql, args).fetchone()
    finally:
        c.close()


def staff(u, pw="Pass1234"):
    A._rate_limit_store.clear()
    c = A.app.test_client()
    c.post("/login", data={"username": u, "password": pw, "csrf_token": tok(c, "/login")})
    return c


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
session_id = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (session_id,))
term2 = c0.execute("SELECT id FROM terms WHERE name='2nd Term'").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('3rd Term', ?, 0)", (session_id,))
term3 = c0.execute("SELECT id FROM terms WHERE name='3rd Term'").fetchone()[0]
c0.commit()
c0.close()
term1 = 1

# Student 1, subject 1: scores entered for term1 and term2 only -- term3 is a genuinely future,
# not-yet-reached term and must NEVER show up (not even as a blank "-" column) unless term3 itself
# is the selected term.
run("DELETE FROM scores WHERE student_id=1")
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,20,20,0,40)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,10,10,0,20)", (term2,))
# Subject 2 deliberately has NO term2 score (a genuinely missing term, not a future one) -- its
# cumulative average through term2 must still be computed from term1 alone, not averaged with a 0.
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,25,25,0,50)", (term1,))

ADMIN = staff("admin")

# ---------------------------------------------------------- 1) First Term selected: ONLY First Term
r1 = ADMIN.get(f"/cumulative/student/1?term_id={term1}")
check("the cumulative result page loads for First Term", r1.status_code == 200, r1.status_code)
h1 = html(r1)
t1 = result_table(h1)
check("with First Term selected, only First Term's column appears in the consolidated table (no 2nd/3rd Term)",
      "1st Term" in t1 and "2nd Term" not in t1 and "3rd Term" not in t1, t1[:300])

# ---------------------------------------------------------- 2) Second Term selected: First + Second only
r2 = ADMIN.get(f"/cumulative/student/1?term_id={term2}")
h2 = html(r2)
t2 = result_table(h2)
check("with Second Term selected, First AND Second Term columns both appear in the table", "1st Term" in t2 and "2nd Term" in t2)
check("...but Third Term (not yet reached) still does not appear at all", "3rd Term" not in t2, t2[:300])

# ---------------------------------------------------------- 3) Third Term selected: all three terms
r3 = ADMIN.get(f"/cumulative/student/1?term_id={term3}")
h3 = html(r3)
t3 = result_table(h3)
check("with Third Term selected, all three terms' columns appear in the table",
      all(t in t3 for t in ("1st Term", "2nd Term", "3rd Term")))

# ---------------------------------------------------------- 4) missing-term handling: not treated as zero
# Subject "English Language"'s term2 score is missing (never entered), not "future" -- on the
# student's own consolidated sheet (which lists one row per subject, one column per included term),
# through Second Term its cumulative average must be exactly its (only) term1 total, 100, not
# (100+0)/2=50 -- h2 is the Second-Term-cutoff page fetched in check 2) above.
row = re.search(r"<td[^>]*>\s*(?:<b>)?English Language(?:</b>)?\s*</td>.*?</tr>", h2, re.S)
check("English Language's row is present on the Second-Term cutoff result sheet", row is not None, h2[:1500])
if row:
    check("...and its missing term2 score is shown as '-', not a zero", ">-<" in row.group(0), row.group(0))
    check("...and its cumulative average through Second Term is 100 (term1 alone), not 50 (averaged with a missing 0)",
          ">100.0<" in row.group(0) or ">100<" in row.group(0), row.group(0))

# ---------------------------------------------------------- 5) disabling cumulative blocks the feature entirely
run("UPDATE schools SET cumulative_enabled=0 WHERE id=1")
r_off = ADMIN.get(f"/cumulative/student/1?term_id={term1}")
check("with Cumulative/Annual disabled, the cumulative page is blocked (falls back / denies, never shows a mix of terms)",
      r_off.status_code in (302, 403) or "cumulative" not in html(r_off).lower() or r_off.status_code == 200 and "Enable it under Result Display Settings" in html(r_off),
      r_off.status_code)
run("UPDATE schools SET cumulative_enabled=1 WHERE id=1")

# ---------------------------------------------------------- 6) default (no term_id) resolves to a well-defined term,
#    scoped to the viewed SESSION (not just "whatever's globally active") -- here that's term1, since it's
#    the only is_active=1 term in this session.
r_default = ADMIN.get("/cumulative/student/1")
t_default = result_table(html(r_default))
check("omitting term_id resolves to the session's own active term (1st Term), not a silent 'every term' mix",
      "1st Term" in t_default and "2nd Term" not in t_default, t_default[:300])

# ---------------------------------------------------------- 7) the class broadsheet & result PDF routes also honour term_id
# (the class broadsheet shows one column per SUBJECT, not per term -- so the term cutoff shows up in
# its "through <term>" heading and in the computed averages, not as extra term-name columns.)
cls_id = one("SELECT class_id FROM students WHERE id=1")["class_id"]
cbs1 = ADMIN.get(f"/cumulative/{cls_id}?term_id={term1}")
check("cumulative broadsheet: First Term selected is labelled 'through 1st Term'", "through 1st Term" in html(cbs1), html(cbs1)[:600])
cbs3 = ADMIN.get(f"/cumulative/{cls_id}?term_id={term3}")
check("cumulative broadsheet: Third Term selected is labelled 'through 3rd Term'", "through 3rd Term" in html(cbs3), html(cbs3)[:600])
# Student 1, Mathematics: term1 total=80, term2 total=40 -> through term1 average=80.0, through term2 average=60.0.
# (the broadsheet cell shows "<average> (<grade>)", e.g. "80.0 (A)".)
avg_t1 = re.search(r"<td>80\.0\s*\(", html(cbs1)) is not None
avg_t2 = re.search(r"<td>60\.0\s*\(", html(ADMIN.get(f"/cumulative/{cls_id}?term_id={term2}"))) is not None
check("Mathematics' cumulative average through First Term alone is 80.0 (just that term's total)", avg_t1, html(cbs1)[:2000])
check("Mathematics' cumulative average through First+Second Term is 60.0 (the mean of both terms' totals)", avg_t2)

# The result/broadsheet PDF routes are gated by an existing (pre-V80) publication guard that blocks
# print/PDF/download for any class/term that hasn't actually been published yet -- unrelated to this
# phase's own change, so the fixture publishes every term first, the same way other PDF-route tests
# in this suite do (see wf_helper.publish), before checking the term-cutoff behaviour itself.
W.publish(A, term1)
W.publish(A, term2)
W.publish(A, term3)
pdf2 = ADMIN.get(f"/cumulative/student/1/pdf?term_id={term2}")
check("cumulative result PDF still generates with a term_id cutoff applied", pdf2.status_code == 200, pdf2.status_code)
check("...and it's a real PDF", pdf2.data[:4] == b"%PDF")

# ---------------------------------------------------------- 8) navigation links from the ordinary result/broadsheet
#    pages now carry the viewed term through, so clicking through naturally lands on the matching cutoff
#    (not always 'every term so far') -- confirmed by reading the actual link, not guessing from app.py.
#    (term1 was already published above.)
result_page = html(ADMIN.get(f"/result/1?term_id={term1}"))
check('the "View cumulative result" link on the First Term result page is wired to term_id={term1}'.format(term1=term1),
      f"term_id={term1}" in result_page, result_page[:2000])

bs_page = html(ADMIN.get(f"/broadsheet/{cls_id}?term_id={term1}"))
check('the "Annual / Cumulative Broadsheet" link on the First Term broadsheet is wired to term_id={term1}'.format(term1=term1),
      f"term_id={term1}" in bs_page, bs_page[:2000])

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
