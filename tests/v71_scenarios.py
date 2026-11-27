"""End-to-end scenarios for the V71 requirement: draft/submit/review/approve/publish
permission separation (gap-closing pass).

This phase audited every place that gates a result/broadsheet view, print, download or
e-mail on whether it has been published, specifically looking for code that reads the
legacy, TERM-WIDE `terms.is_published` flag (meaning "at least one class in this term has
been published" — see v63_core.sync_term_flag) instead of the SPECIFIC CLASS's own
`result_publication` status. If any such route existed unprotected, a student/parent/staff
member could reach a class's result the moment ANY OTHER class in the same term got
published, even though that specific class had never been through review or approval.

What the audit found:
- `v63_spec.py` already runs a single, central `before_request` guard
  (`_v63_publication_guard`) in front of every URL shape that serves a result: the student
  portal, the parent portal, and every staff print/pdf/email/export route. It already checks
  the correct, per-class `v63_core.is_published(...)`, resolving the right class for the
  right term via `student_class_for_term`. This file proves that guard holds even in the
  specific two-classes-one-term scenario that exposes the term-wide-flag bug (one class
  published, a sibling class still in draft) — a scenario the existing v63 test suite had a
  placeholder for (`check("another class's student is still blocked ...", True)`) but never
  actually exercised with a second class.
- Several routes in `app.py`/`v61_routes.py` (student_result[_pdf], parent_result[_pdf],
  student_result_print, parent_result_print, email_result, email_class_results) had their
  OWN, separate checks against the leaky term-wide flag. Because the central guard above
  already intercepts these exact URLs first, these were not independently reachable — but
  they were still wrong on their own terms, and would stop being redundant the moment that
  guard's URL patterns ever changed. They're fixed here to use the same per-class source of
  truth (`v63_core.is_published`, via a new `result_class_published` helper), so every layer
  agrees rather than only one of them being correct.
- A genuine, previously-unprotected gap: `save_score`'s mandatory-reason-on-edit rule and the
  `score_audit.result_status` label it writes both read the same leaky term-wide flag, and
  neither is covered by the before_request guard (it only matches output URLs, not the score
  entry/edit route). A class that had been published and was then reopened for correction
  could have its scores edited with NO mandatory reason, and the audit trail would record a
  misleading "Published"/"Draft" label, if some OTHER class in the same term happened to
  still read as published at the term level. Both are fixed to use this class's own true
  workflow state.

(own process, fresh DB, real HTTP requests). Run: python tests/v71_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v71_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import v63_core
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


def publish_one_class(class_id, term_id):
    """Publishes a SINGLE class (unlike tests/wf_helper.py's publish(), which publishes every
    class in the term) — this is exactly the shape that exposes a term-wide-flag bug: one
    class's result goes through approval and publication while a sibling class is still
    mid-workflow, yet terms.is_published flips to 1 for the whole term regardless."""
    c = db()
    school = c.execute("SELECT se.school_id FROM terms t JOIN sessions se ON se.id=t.session_id WHERE t.id=?", (term_id,)).fetchone()[0]
    tenant = c.execute("SELECT tenant_id FROM schools WHERE id=?", (school,)).fetchone()[0]
    c.execute("INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at,published_by) VALUES (?,?,?,?,'published',CURRENT_TIMESTAMP,1) "
              "ON CONFLICT(school_id,class_id,term_id) DO UPDATE SET status='published', published_at=CURRENT_TIMESTAMP, published_by=1", (school, tenant, class_id, term_id))
    v63_core.sync_term_flag(c, school, term_id)
    c.commit()
    c.close()


# ------------------------------------------------------------------ fixtures
# Default fixture: class 1 (JSS1A) has students 1 (Obi Chinedu), 2 (Eze Amaka), 3 (Bakare Tunde).
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
session_id = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
school_id = c0.execute("SELECT school_id FROM classes WHERE id=1").fetchone()[0]
tenant_id = c0.execute("SELECT tenant_id FROM schools WHERE id=?", (school_id,)).fetchone()[0]

# A second class in the SAME school/term, deliberately left out of the workflow entirely (draft).
c0.execute("INSERT INTO classes(school_id,tenant_id,name) VALUES(?,?,'JSS 2')", (school_id, tenant_id))
class2 = c0.execute("SELECT id FROM classes WHERE name='JSS 2' AND school_id=?", (school_id,)).fetchone()[0]
c0.execute(
    "INSERT INTO students(school_id,tenant_id,admission_no,first_name,last_name,gender,class_id,username,password_hash,first_login_completed_at,parent_email) "
    "VALUES(?,?,'CL2-1','Ngozi','Umeh','F',?,'ngozi',?,CURRENT_TIMESTAMP,'ngozi.parent@example.com')",
    (school_id, tenant_id, class2, pw),
)
cl2_student = c0.execute("SELECT id FROM students WHERE username='ngozi'").fetchone()[0]
c0.execute("INSERT INTO enrollments(student_id, session_id, class_id) VALUES(?,?,?)", (cl2_student, session_id, class2))
c0.execute("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,1,1,10,10,0,30)", (cl2_student,))
# A verified parent for the class-2 student.
c0.execute("INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,email) VALUES(?,?,'Mrs Umeh','umehparent',?,'ngozi.parent@example.com')",
           (school_id, tenant_id, pw))
umeh_parent_id = c0.execute("SELECT id FROM parent_accounts WHERE username='umehparent'").fetchone()[0]
c0.execute("INSERT INTO parent_students(parent_id,student_id,school_id,tenant_id,status,verified_at) VALUES(?,?,?,?,'verified',CURRENT_TIMESTAMP)",
           (umeh_parent_id, cl2_student, school_id, tenant_id))
# A verified parent for class-1 student 1, and a student-login for student 1, for the "still works
# normally once genuinely published" side of each check.
c0.execute("INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,email) VALUES(?,?,'Mr Obi','obiparent',?,'obi.parent@example.com')",
           (school_id, tenant_id, pw))
obi_parent_id = c0.execute("SELECT id FROM parent_accounts WHERE username='obiparent'").fetchone()[0]
c0.execute("INSERT INTO parent_students(parent_id,student_id,school_id,tenant_id,status,verified_at) VALUES(?,1,?,?,'verified',CURRENT_TIMESTAMP)",
           (obi_parent_id, school_id, tenant_id))
c0.execute("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP, parent_email='obi.parent@example.com' WHERE id=1", (pw,))
c0.execute("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,10,10,0,30)")
c0.commit()
c0.close()

ADMIN = staff("admin")

# Publish class 1 ONLY. This flips terms.is_published to 1 (the legacy, term-wide signal) while
# class 2's own result_publication row stays absent/draft.
publish_one_class(1, 1)
check("setup sanity: class 1 is genuinely published", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=1") == "published")
check("setup sanity: class 2 was never touched by the workflow (still draft)", one("SELECT status FROM result_publication WHERE class_id=? AND term_id=1", (class2,)) in (None, "draft"))
check("setup sanity: the term-wide flag is 1 even though class 2 isn't published (the exact ambiguity a term-level check can't resolve)",
      one("SELECT is_published FROM terms WHERE id=1") == 1)

# ---------------------------------------------------------------- 1) staff/admin routes
check("admin: class 1 (published) print works", ADMIN.get("/result/1/print?term_id=1").status_code == 200)
check("admin: class 1 (published) pdf works", ADMIN.get("/result/1/pdf?term_id=1").data[:4] == b"%PDF")
check("admin: class 2 (unpublished) print is still blocked even though the term flag is 1", ADMIN.get(f"/result/{cl2_student}/print?term_id=1").status_code == 403)
check("admin: class 2 (unpublished) pdf is still blocked even though the term flag is 1", ADMIN.get(f"/result/{cl2_student}/pdf?term_id=1").status_code == 403)

# ---------------------------------------------------------------- 2) student self-service, with a sibling class published
# This is the scenario the v63 suite's "another class's student is still blocked" check never
# actually set up (it was a bare placeholder) — a REAL second class, never submitted, while a
# sibling class in the same term genuinely completes the workflow.
stu1 = student_client("chinedu")
stu2 = student_client("ngozi")
check("student in the PUBLISHED class can view their own result", stu1.get("/student/result/1").status_code == 200)
check("student in the PUBLISHED class can download their own result PDF", stu1.get("/student/result/1/pdf").status_code == 200)
check("student in the UNPUBLISHED class is blocked from viewing, even though a sibling class is published",
      stu2.get("/student/result/1").status_code in (302, 403))
check("student in the UNPUBLISHED class is blocked from downloading the PDF",
      stu2.get("/student/result/1/pdf").status_code in (302, 403))
check("student in the UNPUBLISHED class is blocked from the print view too",
      stu2.get("/student/result/1/print").status_code in (302, 403))

# ---------------------------------------------------------------- 3) parent portal, same scenario
par1 = parent_client("obiparent")
par2 = parent_client("umehparent")
check("parent of a child in the PUBLISHED class can view the result", par1.get("/parent/children/1/result/1").status_code == 200)
check("parent of a child in the PUBLISHED class can download the PDF", par1.get("/parent/children/1/result/1/pdf").status_code == 200)
check("parent of a child in the UNPUBLISHED class is blocked from viewing, even though a sibling class is published",
      par2.get(f"/parent/children/{cl2_student}/result/1").status_code in (302, 403))
check("parent of a child in the UNPUBLISHED class is blocked from downloading the PDF",
      par2.get(f"/parent/children/{cl2_student}/result/1/pdf").status_code in (302, 403))
check("parent of a child in the UNPUBLISHED class is blocked from the print view too",
      par2.get(f"/parent/children/{cl2_student}/result/1/print").status_code in (302, 403))
check("the parent's own children list correctly never even linked to the unpublished result",
      f"/parent/children/{cl2_student}/result/1" not in html(par2.get(f"/parent/children/{cl2_student}")))

# ---------------------------------------------------------------- 4) staff "email to parent" routes
r = post(ADMIN, f"/result/{cl2_student}/email", {}, f"/result/{cl2_student}")
check("staff cannot email a result for the UNPUBLISHED class, even though a sibling class is published",
      r.status_code == 403 and one("SELECT status FROM result_publication WHERE class_id=? AND term_id=1", (class2,)) in (None, "draft"))
r = post(ADMIN, "/class/1/email_results", {}, "/broadsheet/1")
check("staff emailing the whole PUBLISHED class 1 is allowed through the gate (no regression)", r.status_code in (200, 302))
r = post(ADMIN, f"/class/{class2}/email_results", {}, f"/broadsheet/{class2}")
check("staff emailing the whole UNPUBLISHED class 2 is refused at the gate", r.status_code == 403)
check("...and no result_publication row was created as a side effect of the refused bulk email",
      one("SELECT status FROM result_publication WHERE class_id=? AND term_id=1", (class2,)) in (None, "draft"))

# ---------------------------------------------------------------- 5) access opens up once class 2 is genuinely published too
publish_one_class(class2, 1)
check("once class 2 is ALSO genuinely published, its own student can now see the result", stu2.get("/student/result/1").status_code == 200)
check("...and its own parent can now see the result", parent_client("umehparent").get(f"/parent/children/{cl2_student}/result/1").status_code == 200)

# ---------------------------------------------------------------- 6) score-change audit trail records THIS class's true state
# Reopen class 1 only; class 2 stays published. The term-wide flag stays 1 throughout, so a check
# against that flag alone (the old code) could never tell these two situations apart.
post(ADMIN, "/results/workflow/1/1/reopen", {"reason": "Investigating a parent complaint"}, "/results/workflow?term_id=1")
check("setup: class 1 is reopened (unlocked, previously published)", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=1") == "reopened")
check("the term-wide flag is STILL 1 throughout (class 2 is still published) — the exact ambiguity the fix removes",
      one("SELECT is_published FROM terms WHERE id=1") == 1)
tk = tok(ADMIN, "/scores/1/1")
r = ADMIN.post("/scores/1/1", data=[("csrf_token", tk), ("student_id", "1"), ("ca1_1", "19"), ("ca2_1", "10"), ("exam_1", "30"), ("change_reason", "")])
check("editing a REOPENED (previously-published) class's score without a reason is refused",
      one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1 AND term_id=1") == 10)
tk = tok(ADMIN, "/scores/1/1")
r = ADMIN.post("/scores/1/1", data=[("csrf_token", tk), ("student_id", "1"), ("ca1_1", "19"), ("ca2_1", "10"), ("exam_1", "30"), ("change_reason", "Corrected CA1 after recheck")])
check("...but succeeds once a reason is given", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1 AND term_id=1") == 19)
check("the audit row's result_status records THIS class's own true state (\"Reopened — correction\"), not a binary published/draft label off the leaky term flag",
      one("SELECT result_status FROM score_audit WHERE student_id=1 AND subject_id=1 ORDER BY id DESC LIMIT 1") == "Reopened — correction")
# A change to class 2 (genuinely published, locked) is refused outright — unaffected by this phase, confirms no regression in the lock itself.
tk = tok(ADMIN, f"/scores/{class2}/1")
r = ADMIN.post(f"/scores/{class2}/1", data=[("csrf_token", tk), ("student_id", str(cl2_student)), ("ca1_1", "25"), ("ca2_1", "10"), ("exam_1", "30")])
check("a genuinely published, locked class's scores still cannot be edited directly (no regression)",
      one("SELECT ca1 FROM scores WHERE student_id=? AND subject_id=1 AND term_id=1", (cl2_student,)) == 10)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
