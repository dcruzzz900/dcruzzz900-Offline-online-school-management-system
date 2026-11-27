"""End-to-end scenarios for the V69 requirement: admin-wide (bulk) AI consent
management — the one P0 item left unfinished after the original audit (consent
could previously only be set one student at a time). Applying a status to many
students at once must still record every student individually (same history
table, same single-writer function), must stay tenant-scoped, must require a
name+relationship when bulk-setting "Granted" (consent can't be granted on
someone else's behalf without saying who), and must not touch or re-log
students who already have the target status.
(own process, fresh DB, real HTTP requests). Run: python tests/v69_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v69_")
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
# a second, unrelated school + student, to prove no cross-tenant leakage
c0.execute("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Other College','active','2','SCH-OTHER-002')")
sid2 = c0.execute("SELECT id FROM schools WHERE name='Other College'").fetchone()[0]
c0.execute("INSERT INTO classes(school_id,name,tenant_id) VALUES(?, 'JSS1A', '2')", (sid2,))
other_class_id = c0.execute("SELECT id FROM classes WHERE school_id=?", (sid2,)).fetchone()[0]
c0.execute("INSERT INTO students(school_id,class_id,first_name,last_name,admission_no,is_active,tenant_id) VALUES(?,?, 'Foreign','Student','OC-001',1,'2')", (sid2, other_class_id))
other_student_id = c0.execute("SELECT id FROM students WHERE school_id=?", (sid2,)).fetchone()[0]
c0.commit()
c0.close()

ADMIN = staff("admin")

# default fixture: students 1 (Obi Chinedu), 2 (Eze Amaka), 3 (Bakare Tunde), all in class JSS1A, all 'pending'.


def consent_page():
    return html(ADMIN.get("/ai/consent"))


def status_of(student_id):
    return one("SELECT status FROM student_ai_consent WHERE student_id=? AND school_id=1", (student_id,)) or "pending"


def events_for(student_id):
    c = db()
    try:
        return c.execute("SELECT * FROM student_ai_consent_events WHERE student_id=? ORDER BY id", (student_id,)).fetchall()
    finally:
        c.close()


# ---------------------------------------------------------------- scenarios

# 1) Bulk withdraw for two of the three students in one submit.
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": ["1", "2"], "bulk_status": "withdrawn", "bulk_notes": "Policy review"}, "/ai/consent")
check("student 1 is now withdrawn", status_of(1) == "withdrawn")
check("student 2 is now withdrawn", status_of(2) == "withdrawn")
check("student 3 (not selected) is untouched, still pending", status_of(3) == "pending")
check("each selected student got their OWN history event (not a shared/merged row)", len(events_for(1)) == 1 and len(events_for(2)) == 1 and len(events_for(3)) == 0)
check("the page confirms how many were changed", "2 student" in consent_page())

# 2) Re-applying the same bulk status to the same students is a no-op: 0 changed, no new events.
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": ["1", "2"], "bulk_status": "withdrawn"}, "/ai/consent")
check("no-op bulk update does not add a second history event", len(events_for(1)) == 1 and len(events_for(2)) == 1)
check("the page says nothing needed to change", "No changes were needed" in consent_page())

# 3) Bulk "Granted" without a name+relationship is refused outright (can't grant consent anonymously, even in bulk).
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": ["3"], "bulk_status": "granted"}, "/ai/consent")
check("bulk 'granted' without a name+relationship is refused", status_of(3) == "pending")
check("the page explains why", "enter who gave it" in consent_page())

# 4) Bulk "Granted" WITH a name+relationship (e.g. a batch of paper forms logged together) succeeds for all selected.
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": ["1", "2", "3"], "bulk_status": "granted",
                            "bulk_consenting_name": "Mrs. Adeyemi (PTA)", "bulk_relationship": "School representative",
                            "bulk_notes": "Paper consent forms collected at term start"}, "/ai/consent")
check("student 1 is now granted", status_of(1) == "granted")
check("student 2 is now granted", status_of(2) == "granted")
check("student 3 is now granted", status_of(3) == "granted")
check("each got the same consenting name recorded on their OWN row", one("SELECT granted_by_name FROM student_ai_consent WHERE student_id=1") == "Mrs. Adeyemi (PTA)" and
      one("SELECT granted_by_name FROM student_ai_consent WHERE student_id=3") == "Mrs. Adeyemi (PTA)")
check("the single-student audit trail still has one event per student per change", len(events_for(1)) == 2 and len(events_for(3)) == 1)

# 5) An invalid bulk status is rejected outright.
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": ["1"], "bulk_status": "nonsense"}, "/ai/consent")
check("an invalid bulk status changes nothing", status_of(1) == "granted")

# 6) No students selected is rejected with a clear message, not a silent no-op.
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": [], "bulk_status": "withdrawn"}, "/ai/consent")
check("submitting with no students selected is refused", "Select at least one student" in consent_page())
check("...and nothing was changed", status_of(1) == "granted")

# 7) Tenant isolation: posting another school's student id in the bulk list touches nothing there,
#    and doesn't error out — it's just silently excluded (every OTHER selected id still applies).
post(ADMIN, "/ai/consent", {"bulk": "1", "student_ids": [str(other_student_id), "1"], "bulk_status": "withdrawn"}, "/ai/consent")
check("another school's student is never touched by our bulk update", one("SELECT status FROM student_ai_consent WHERE student_id=? AND school_id=?", (other_student_id, sid2)) is None)
check("our own selected student in the same submission is still updated", status_of(1) == "withdrawn")

# 8) A single bulk-change audit_log entry is written (summary), in addition to the per-student history.
check("a summary audit_log entry exists for the bulk action", one("SELECT COUNT(*) FROM audit_log WHERE action='ai_consent_bulk_changed'") >= 1)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
