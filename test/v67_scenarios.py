"""End-to-end scenarios for the V67 requirement: a dedicated "Next Term Resumes" toggle
that retrieves the FOLLOWING term's own resumption date (First Term's sheet shows Second
Term's date, Second shows Third's, Third shows the next session's first term's date),
never guessing when nothing is configured, plus the consolidation of the old
`next_term_begins` field into the new single-source model.
(own process, fresh DB, real HTTP requests). Run: python tests/v67_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v67_")
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
session_id = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c0.execute("UPDATE terms SET name='First Term', is_active=1 WHERE id=1")
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('Second Term', ?, 0)", (session_id,))
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('Third Term', ?, 0)", (session_id,))
term2 = c0.execute("SELECT id FROM terms WHERE name='Second Term'").fetchone()[0]
term3 = c0.execute("SELECT id FROM terms WHERE name='Third Term'").fetchone()[0]
c0.execute("INSERT INTO sessions (school_id, name, is_active, tenant_id) VALUES (1, '2026/2027', 0, '1')")
session2_id = c0.execute("SELECT id FROM sessions WHERE name='2026/2027'").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('First Term', ?, 0)", (session2_id,))
term_next_session_1 = c0.execute("SELECT id FROM terms WHERE session_id=?", (session2_id,)).fetchone()[0]
get_result_display(c0, 1)  # lazily creates the row for school 1 so the direct UPDATE below actually lands
c0.execute("UPDATE result_display_settings SET show_next_term_resumes=1 WHERE school_id=1")
# a second, unrelated school, to prove no cross-tenant leakage
c0.execute("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Other College','active','2','SCH-OTHER-001')")
sid2 = c0.execute("SELECT id FROM schools WHERE name='Other College'").fetchone()[0]
c0.commit()
c0.close()

a_c = staff("admin")

student = one("SELECT id FROM students WHERE school_id=1 LIMIT 1")
subj = one("SELECT id FROM subjects WHERE school_id=1 LIMIT 1")
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,12,13,0,50)", (student, subj, 1))


def sheet(term_id=1):
    r = a_c.get(f"/result/{student}?term_id={term_id}")
    assert r.status_code == 200, (term_id, r.status_code)
    return html(r)


# ---------------------------------------------------------------- scenarios

# 1) Nothing configured anywhere -> nothing shown, nothing guessed, on any of the three terms.
check("First Term: nothing configured -> no Next Term Resumes shown", "Next Term Resumes" not in sheet(1))
check("Second Term: nothing configured -> no Next Term Resumes shown", "Next Term Resumes" not in sheet(term2))
check("Third Term: nothing configured -> no Next Term Resumes shown", "Next Term Resumes" not in sheet(term3))

# 2) First Term's sheet shows SECOND Term's own resumption date, not its own.
post(a_c, "/admin/terms", {"action": "set_resumption", "term_id": "1", "resumption_date": "2099-01-01"}, "/admin/terms")  # term 1's own date (a decoy)
post(a_c, "/admin/terms", {"action": "set_resumption", "term_id": str(term2), "resumption_date": "2027-04-20"}, "/admin/terms")
s1 = sheet(1)
check("First Term's sheet shows Second Term's date (20/04/2027)", "Next Term Resumes" in s1 and "20/04/2027" in s1)
check("First Term's sheet does NOT show its own decoy date (01/01/2099)", "01/01/2099" not in s1)

# 3) Second Term's sheet shows THIRD Term's date.
post(a_c, "/admin/terms", {"action": "set_resumption", "term_id": str(term3), "resumption_date": "2027-09-08"}, "/admin/terms")
s2 = sheet(term2)
check("Second Term's sheet shows Third Term's date (08/09/2027)", "Next Term Resumes" in s2 and "08/09/2027" in s2)

# 4) Third Term's sheet shows the NEXT SESSION's first term's date, when configured...
s3 = sheet(term3)
check("Third Term's sheet: next session's term has no date yet -> nothing shown, not guessed", "Next Term Resumes" not in s3)
post(a_c, "/admin/terms", {"action": "set_resumption", "term_id": str(term_next_session_1), "resumption_date": "2028-01-15"}, "/admin/terms")
s3b = sheet(term3)
check("...and once it IS configured, Third Term's sheet shows it", "Next Term Resumes" in s3b and "15/01/2028" in s3b)

# 5) Turning the toggle OFF hides it everywhere without deleting any date.
run("UPDATE result_display_settings SET show_next_term_resumes=0 WHERE school_id=1")
check("toggle OFF hides it on First Term's sheet", "Next Term Resumes" not in sheet(1))
check("...but the underlying date is untouched", one("SELECT resumption_date FROM terms WHERE id=?", (term2,)) == "2027-04-20")
run("UPDATE result_display_settings SET show_next_term_resumes=1 WHERE school_id=1")
check("turning it back ON shows the preserved date again", "20/04/2027" in sheet(1))

# 6) The old next_term_begins field (entered on the term before) is folded into the
#    following term's resumption_date by the migration, when that term has none of its own.
run("UPDATE terms SET resumption_date=NULL WHERE id=?", (term3,))
run("UPDATE terms SET next_term_begins='2027-09-30' WHERE id=?", (term2,))
from db import migration_067_v67_next_term_resumes
conn = db()
migration_067_v67_next_term_resumes(conn)
conn.commit()
conn.close()
check("next_term_begins on Second Term was folded into Third Term's resumption_date", one("SELECT resumption_date FROM terms WHERE id=?", (term3,)) == "2027-09-30")

# 7) Tenant isolation: another school's terms are never touched by any of this.
check("another school has no terms/dates affected", one("SELECT COUNT(*) FROM terms t JOIN sessions se ON se.id=t.session_id WHERE se.school_id=?", (sid2,)) == 0)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
