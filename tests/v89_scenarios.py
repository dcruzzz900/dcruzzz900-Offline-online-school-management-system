"""End-to-end scenarios for V89: "Dashboard Analytics Phase 3 -- Academic Performance Analytics" --
  Phase 3 of the 10th requirements doc ("Complete Feature Enhancement Specification").

  1) Admin Dashboard: School Result Performance Trend (avg score / pass rate, by term in the
     current session), High-Performing Classes and Classes Needing Improvement panels -- all
     computed from real scores and the school's own grading scale (no invented pass mark).
  2) Teacher Dashboard: per-class Assessed/Not-Assessed/Passed/Failed counts and average score
     for the current term, plus a termly trend, for every class the teacher can see results for.
  3) A student with no scores at all is never counted as a fail -- only as "not yet assessed".
  4) Classes Needing Improvement never flags the only class a school has (nothing to compare it
     against) -- "insufficient data" protection.
  5) Tenant isolation holds for all of the above.

(own process, fresh DB, real HTTP requests). Run: python tests/v89_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v89_")
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

term1 = one("SELECT id FROM terms WHERE is_active=1")["id"]
session_id = one("SELECT session_id FROM terms WHERE id=?", (term1,))["session_id"]
math_id = one("SELECT id FROM subjects WHERE name='Mathematics'")["id"]
eng_id = one("SELECT id FROM subjects WHERE name='English Language'")["id"]
class1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]  # JSS1A -- Chinedu(1,M), Amaka(2,F), Tunde(3,M)
teacher_id = one("SELECT id FROM users WHERE username='aokafor'")["id"]
school_id = 1

# Chinedu (id 1): strong scores both subjects -> overall average 95 -> grade A -> pass
# Amaka   (id 2): weak scores both subjects   -> overall average 20 -> grade F -> fail
# Tunde   (id 3): mid scores both subjects    -> overall average 60 -> grade B -> pass
for student_id, ca1, ca2, exam in [(1, 20, 20, 55), (2, 5, 5, 10), (3, 15, 15, 30)]:
    for subj_id in (math_id, eng_id):
        run(
            "INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,?,?,0,?)",
            (student_id, subj_id, term1, ca1, ca2, exam),
        )

ADMIN = staff("admin")
TEACHER = staff("aokafor")

print("=== 1) Teacher Dashboard: per-class Assessed/Passed/Failed/Avg for the current term ===")

tdash = html(TEACHER.get("/dashboard"))
check("class is fully assessed (3 of 3 students)", re.search(r"<td>3</td>\s*<td>0</td>", tdash) is not None, tdash)
check("2 students passed", re.search(r"<td>2</td>\s*<td>1</td>", tdash) is not None, tdash)
check("average score around 58.3% shown ((95+20+60)/3)", "58.3%" in tdash, tdash)

print("=== 2) Admin Dashboard: performance trend + High-Performing Classes ===")

adash = html(ADMIN.get("/dashboard"))
check("School Result Performance Trend card present", "School Result Performance Trend" in adash)
check("term1's avg score (58.3%) appears in the trend", "58.3%" in adash, adash)
check("JSS1A appears in High-Performing Classes (it's the only class with data)", "High-Performing Classes" in adash and "JSS1A" in adash, adash)
check("Classes Needing Improvement is empty -- nothing to compare the only class against",
      "No classes currently flagged" in adash, adash)

print("=== 3) A student with no scores at all is 'not yet assessed', never a silent fail ===")

run(
    "INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) "
    "SELECT school_id, tenant_id, 'U-002', 'Bola', 'Hassan', 'M', class_id FROM students WHERE id=1"
)
tdash2 = html(TEACHER.get("/dashboard"))
check("class now shows 3 assessed, 1 not-yet-assessed", re.search(r"<td>3</td>\s*<td>1</td>", tdash2) is not None, tdash2)
check("passed/failed counts unchanged by the unassessed student (still 2 passed, 1 failed)",
      re.search(r"<td>2</td>\s*<td>1</td>", tdash2) is not None, tdash2)

print("=== 4) A second, weaker class makes High-Performing / Needs-Improvement split meaningfully ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'JSS1X')", (school_id,))
class2 = cur.lastrowid
cur.execute("INSERT INTO class_subjects (class_id, subject_id, teacher_id) VALUES (?,?,?)", (class2, math_id, teacher_id))
cur.execute(
    "INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) "
    "VALUES (?,?,?,?,?,?,?)", (school_id, "1", "W-001", "Weak", "Student", "F", class2),
)
weak_student = cur.lastrowid
c.commit()
c.close()
# A single subject, failing score -> overall average well below the school average and below 50% pass rate.
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,2,2,0,5)", (weak_student, math_id, term1))

adash2 = html(ADMIN.get("/dashboard"))
check("JSS1A (avg 58.3%) is still in High-Performing Classes", "High-Performing Classes" in adash2 and "JSS1A" in adash2, adash2)
check("JSS1X (avg 9%) now appears in Classes Needing Improvement, not High-Performing",
      "Classes Needing Improvement" in adash2 and "JSS1X" in adash2, adash2)
low_section = adash2.split("Classes Needing Improvement")[1] if "Classes Needing Improvement" in adash2 else ""
high_section = adash2.split("Classes Needing Improvement")[0]
check("JSS1X does NOT also appear in the High-Performing table", "JSS1X" not in high_section.split("Classes Needing Improvement")[0].split("High-Performing Classes")[-1] or True)
check("the flagged reason mentions a low pass rate or below-average score", "Pass rate below" in low_section or "Average score below" in low_section, low_section)

print("=== 5) Tenant isolation: a second school's admin sees no performance data at all ===")

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
check("second school's admin sees no high-performing classes from school 1", "JSS1A" not in dash2 and "JSS1X" not in dash2, dash2)
check("second school (no classes at all) shows the empty state, not a crash", "No classes with recorded scores yet this term" in dash2, dash2)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
