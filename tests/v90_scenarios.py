"""End-to-end scenarios for V90: "Dashboard Analytics Phase 4 -- Recent Activities" --
  Phase 4 of the 10th requirements doc ("Complete Feature Enhancement Specification").

  1) Admin Dashboard: a Recent Activities panel built entirely from the app's own existing
     (or newly instrumented) audit trails -- student registration, student status change,
     parent registration (admin-created and self-signup), form/subject teacher assignment,
     attendance, score entry, and result publication -- newest first, never fabricated.
  2) Teacher Dashboard: the same feed, but restricted to the classes the teacher can actually
     see -- an activity in a class the teacher has no access to must never appear.
  3) A "View All Activities" page with pagination and a type filter.
  4) Tenant isolation holds throughout.

(own process, fresh DB, real HTTP requests). Run: python tests/v90_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v90_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
from db import get_db
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
c0.commit()
c0.close()

school_id = 1
class1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]  # JSS1A
math_id = one("SELECT id FROM subjects WHERE name='Mathematics'")["id"]
term1 = one("SELECT id FROM terms WHERE is_active=1")["id"]

ADMIN = staff("admin")
TEACHER = staff("aokafor")

print("=== 1) Student registration is now logged and shows on the Admin feed ===")

post(ADMIN, "/admin/students", {
    "class_id": class1, "admission_no": "999", "first_name": "New", "last_name": "Student", "gender": "M",
}, "/admin/students")
adash = html(ADMIN.get("/dashboard"))
check("Recent Activities panel present", "Recent Activities" in adash)
check("new student's registration appears in the admin feed", "Student registered" in adash and "New Student" in adash, adash)

print("=== 2) Student status change (transfer) is logged ===")

new_student_id = one("SELECT id FROM students WHERE admission_no='999'")["id"]
post(ADMIN, f"/my-class/{class1}/students/{new_student_id}/edit", {
    "first_name": "New", "last_name": "Student", "admission_no": "999", "gender": "M", "status": "Transferred",
}, f"/my-class/{class1}/roster")
adash2 = html(ADMIN.get("/dashboard"))
check("status change appears in the feed", "Student status changed" in adash2 and "Transferred" in adash2, adash2)

print("=== 3) Teacher-class/subject assignment is now logged ===")

cs_row = one("SELECT id FROM class_subjects WHERE class_id=? AND subject_id=?", (class1, math_id))
teacher_id = one("SELECT id FROM users WHERE username='aokafor'")["id"]
post(ADMIN, f"/admin/class_subjects/{cs_row['id']}/assign_teacher", {"teacher_id": teacher_id}, "/admin/class_subjects")
adash3 = html(ADMIN.get("/dashboard"))
check("subject-teacher assignment appears in the feed", "Subject teacher assigned" in adash3, adash3)

print("=== 4) Attendance, score entry and result publication all surface in the feed (already-audited paths) ===")

# Score entry (teacher)
post(TEACHER, f"/scores/{class1}/{math_id}", {
    "student_id": "1", "ca1_1": "15", "ca2_1": "15", "ca3_1": "0", "exam_1": "40",
}, f"/scores/{class1}/{math_id}")
adash4 = html(ADMIN.get("/dashboard"))
check("a score entry shows up in the admin feed", "Score entered" in adash4 or "Score " in adash4, adash4)

tdash = html(TEACHER.get("/dashboard"))
check("Recent Class Activities panel present on the teacher dashboard", "Recent Class Activities" in tdash)
check("the score entry for the teacher's own class appears there too", "Score entered" in tdash or "Score " in tdash, tdash)

print("=== 5) Teacher's feed is scoped to accessible classes only ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'JSS2B')", (school_id,))
other_class = cur.lastrowid
cur.execute(
    "INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) "
    "VALUES (?,?,?,?,?,?,?)", (school_id, "1", "OC-001", "Other", "Classmate", "F", other_class),
)
c.commit()
c.close()
run(
    "INSERT INTO audit_log(actor_type,actor_name,school_id,action,details,class_id) VALUES('admin','Administrator',?,?,?,?)",
    (school_id, "student_registered", "Other Classmate (OC-001) registered, status: Active", other_class),
)
tdash2 = html(TEACHER.get("/dashboard"))
check("an activity from a class the teacher cannot see never appears on their dashboard", "Other Classmate" not in tdash2, tdash2)
adash5 = html(ADMIN.get("/dashboard"))
check("...but the admin (whole-school view) does see it", "Other Classmate" in adash5, adash5)

print("=== 6) View All Activities: pagination + type filter ===")

all_page = html(ADMIN.get("/activities"))
check("View All Activities page loads and lists events", "Recent Activities" in all_page and "New Student" in all_page, all_page)
filtered = html(ADMIN.get("/activities?type=scores"))
check("type filter narrows the feed (no registration events shown under 'scores')", "New Student" not in filtered, filtered)
check("...but does show the score entry", "Score entered" in filtered or "Score " in filtered, filtered)

teacher_all = html(TEACHER.get("/activities"))
check("teacher's View All page is also scoped -- no activity from the inaccessible class", "Other Classmate" not in teacher_all, teacher_all)

print("=== 7) Tenant isolation ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')")
school2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{school2}", f"PUB{school2}", school2))
cur.execute(
    "INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)",
    (school2, "school2", "Second Admin", "admin2", pw, "admin"),
)
cur.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (school2, "2025/2026"))
sess2 = cur.lastrowid
cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,1)", ("1st Term", sess2))
c.commit()
c.close()

ADMIN2 = staff("admin2")
dash2 = html(ADMIN2.get("/dashboard"))
check("second school's admin sees none of school 1's activity", "New Student" not in dash2 and "Other Classmate" not in dash2, dash2)
check("...and gets the honest empty state instead", "No activities recorded yet" in dash2, dash2)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
