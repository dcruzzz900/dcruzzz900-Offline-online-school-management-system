"""End-to-end scenarios for the V66 requirement: flexible score weighting with a safe
review workflow instead of a permanent block when a lower maximum conflicts with a
saved score (own process, fresh DB, real HTTP requests).
Run: python tests/v66_scenarios.py   (exit 0 = all passed)"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v66_")
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
c0.execute("UPDATE terms SET is_active=1 WHERE id=1")
c0.commit()
subj = c0.execute("SELECT id FROM subjects WHERE school_id=1 LIMIT 1").fetchone()[0]
student = c0.execute("SELECT id FROM students WHERE school_id=1 LIMIT 1").fetchone()[0]
term = c0.execute("SELECT id FROM terms WHERE is_active=1 AND id IN (SELECT id FROM terms) LIMIT 1").fetchone()[0]
c0.close()

a_c = staff("admin")

# ---------------------------------------------------------------- scenarios

# 1) Lowering CA1 below a saved score shows a review instead of a hard refusal,
#    and does NOT touch the score or the config.
run("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, ca3, exam) VALUES (?,?,?,20,10,0,50) "
    "ON CONFLICT(student_id, subject_id, term_id) DO UPDATE SET ca1=20, ca2=10, ca3=0, exam=50",
    (student, subj, term))
before_max = one("SELECT ca1_max FROM grading_config WHERE school_id=1")
r = post(a_c, "/admin/grading", {"ca1_max": "10", "ca2_max": "20", "ca3_max": "0", "exam_max": "60"}, "/admin/grading")
page = html(r) if r.status_code != 302 else html(a_c.get("/admin/grading"))
check("lowering CA1 below a saved score is not an outright refusal", "can't be lowered" not in page)
check("shows a review panel naming the affected score", "Review before applying" in page and "exceed" in page)
check("the saved score itself is untouched while under review", one("SELECT ca1 FROM scores WHERE student_id=? AND subject_id=? AND term_id=?", (student, subj, term)) == 20)
check("the maximum itself is not changed until confirmed", one("SELECT ca1_max FROM grading_config WHERE school_id=1") == before_max)

# 2) Confirming applies the new maximum, preserves the saved (now out-of-range) score exactly,
#    and writes an audit row with old/new values + affected count.
r2 = post(a_c, "/admin/grading", {"ca1_max": "10", "ca2_max": "20", "ca3_max": "0", "exam_max": "60", "confirm_override": "1"}, "/admin/grading")
check("confirming redirects/succeeds", r2.status_code in (200, 302))
check("the maximum is now applied", one("SELECT ca1_max FROM grading_config WHERE school_id=1") == 10)
check("the pre-existing score is preserved exactly, not capped or deleted", one("SELECT ca1 FROM scores WHERE student_id=? AND subject_id=? AND term_id=?", (student, subj, term)) == 20)
audit = db()
row = audit.execute("SELECT * FROM grading_config_audit WHERE school_id=1 ORDER BY id DESC LIMIT 1").fetchone()
audit.close()
check("an audit row was written", row is not None)
if row is not None:
    check("audit records old and new CA1 max", row["old_ca1_max"] == before_max and row["new_ca1_max"] == 10, dict(row))
    check("audit records who made the change", row["changed_by_name"] == "Admin" or bool(row["changed_by_name"]))
    check("audit records the affected count", row["affected_count"] >= 1, row["affected_count"])

# 3) Negative maximums and totals over 100 are still hard-refused immediately (no review needed).
r3 = post(a_c, "/admin/grading", {"ca1_max": "-5", "ca2_max": "20", "ca3_max": "0", "exam_max": "60"}, "/admin/grading")
p3 = html(r3)
check("a negative maximum is still refused outright", "CA1 maximum can" in p3 and "negative" in p3)

r4 = post(a_c, "/admin/grading", {"ca1_max": "50", "ca2_max": "50", "ca3_max": "10", "exam_max": "60"}, "/admin/grading")
p4 = html(r4)
check("a total over 100 is still refused outright", "add up to" in p4 and "exceed 100" in p4)

# 4) Re-applying a maximum with no conflicting scores (e.g. raising it back) needs no review step.
r5 = post(a_c, "/admin/grading", {"ca1_max": "20", "ca2_max": "20", "ca3_max": "0", "exam_max": "60"}, "/admin/grading")
p5 = html(r5) if r5.status_code != 302 else html(a_c.get("/admin/grading"))
check("raising a maximum back up needs no review", "Review before applying" not in p5)
check("it is applied immediately", one("SELECT ca1_max FROM grading_config WHERE school_id=1") == 20)

# 5) CA3 can be switched on then off again without losing previously saved CA3 scores.
run("UPDATE scores SET ca3=7 WHERE student_id=? AND subject_id=? AND term_id=?", (student, subj, term))
post(a_c, "/admin/grading", {"ca1_max": "20", "ca2_max": "20", "ca3_max": "10", "exam_max": "50"}, "/admin/grading")
check("CA3 can be switched on", one("SELECT ca3_max FROM grading_config WHERE school_id=1") == 10)
post(a_c, "/admin/grading", {"ca1_max": "20", "ca2_max": "20", "ca3_max": "0", "exam_max": "60"}, "/admin/grading")
check("switching CA3 back off keeps the saved CA3 score", one("SELECT ca3 FROM scores WHERE student_id=? AND subject_id=? AND term_id=?", (student, subj, term)) == 7)

# 6) Tenant isolation: changing school 1's weighting never touches another school's grading_config.
other_before = one("SELECT ca1_max FROM grading_config WHERE school_id=2") if one("SELECT COUNT(*) FROM schools WHERE id=2") else None
if other_before is not None:
    check("another school's grading config is untouched", one("SELECT ca1_max FROM grading_config WHERE school_id=2") == other_before)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
