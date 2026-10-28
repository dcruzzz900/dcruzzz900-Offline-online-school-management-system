"""End-to-end scenarios for V91: "Dashboard Analytics Phase 5 -- Student & Parent Dashboards" --
  Phase 5 of the 10th requirements doc ("Complete Feature Enhancement Specification").

  1) Student Dashboard: Academic Performance (termly trend, class-average comparison,
     improving/needs-attention subjects), Attendance stats, and a student-scoped Recent
     Activities feed.
  2) Parent Dashboard: the same three, scoped to the parent's verified linked child.
  3) Publication gating holds throughout -- an unpublished term's scores never appear,
     even to the student/parent themselves.
  4) Privacy: a student/parent never sees another student's individual activity or scores.
  5) Tenant isolation holds throughout.

(own process, fresh DB, real HTTP requests). Run: python tests/v91_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v91_")
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


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE students SET username=?, password_hash=? WHERE id=1", ("chinedu", pw))
c0.execute("UPDATE students SET username=?, password_hash=? WHERE id=2", ("amaka", pw))
c0.commit()
c0.close()

school_id = 1
class1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]  # JSS1A
session_id = one("SELECT session_id FROM enrollments WHERE student_id=1")["session_id"]
term1 = one("SELECT id FROM terms WHERE is_active=1")["id"]
subjects = [r["sid"] if "sid" in r.keys() else r["id"] for r in db().execute(
    "SELECT s.id FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id WHERE cs.class_id=?", (class1,)
).fetchall()]

# A second term in the same session, left unpublished -- its scores must never surface.
c = db()
cur = c.cursor()
cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,0)", ("2nd Term", session_id))
term2 = cur.lastrowid
c.commit()
c.close()

ADMIN = staff("admin")

# -- Term 1 scores for Chinedu (student 1) and Amaka (student 2), published
term1_scores = {subjects[0]: (15, 15, 10, 40), subjects[1]: (12, 13, 8, 35), subjects[2]: (18, 17, 10, 45), subjects[3]: (10, 10, 5, 30)}
for sid, (ca1, ca2, ca3, exam) in term1_scores.items():
    run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (1,?,?,?,?,?,?)", (sid, term1, ca1, ca2, ca3, exam))
    run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (2,?,?,?,?,?,?)", (sid, term1, ca1, ca2, ca3 + 5, exam))

run("UPDATE terms SET is_published=1 WHERE id=?", (term1,))
run(
    "INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at,published_by) VALUES (?,?,?,?,'published',CURRENT_TIMESTAMP,1)",
    (school_id, "1", class1, term1),
)
pub_id = one("SELECT id FROM result_publication WHERE class_id=? AND term_id=?", (class1, term1))["id"]
run(
    "INSERT INTO result_publication_audit(school_id,tenant_id,publication_id,class_id,term_id,action,previous_status,new_status,actor_id,actor_name,actor_role,server_timestamp) "
    "VALUES (?,?,?,?,?,'publish','approved','published',1,'Administrator','admin',CURRENT_TIMESTAMP)",
    (school_id, "1", pub_id, class1, term1),
)

# -- Term 2 scores for Chinedu, left UNPUBLISHED (term2.is_published stays 0, no result_publication row)
term2_scores = {subjects[0]: (18, 18, 10, 48), subjects[1]: (8, 8, 5, 20), subjects[2]: (19, 18, 10, 48), subjects[3]: (12, 12, 5, 32)}
for sid, (ca1, ca2, ca3, exam) in term2_scores.items():
    run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (1,?,?,?,?,?,?)", (sid, term2, ca1, ca2, ca3, exam))

# -- Attendance for Chinedu: 8 present, 1 late, 1 absent
for i in range(8):
    run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,?,'present','present')", (class1, term1, f"2026-09-{i+1:02d}"))
run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,'2026-09-09','present','late')", (class1, term1))
run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,'2026-09-10','absent','absent')", (class1, term1))

# -- A learning material for the class, and a score-change event for Amaka (must never leak to Chinedu)
run(
    "INSERT INTO materials(school_id,session_id,class_id,subject_id,title,kind,external_url,uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)",
    (school_id, session_id, class1, subjects[0], "Term 1 Revision Notes", "Document", "https://example.com/notes.pdf"),
)
run(
    "INSERT INTO attendance_audit(school_id,subject_type,subject_id,class_id,term_id,attendance_date,status,action,recorder_name,server_timestamp) "
    "VALUES (?,'student',2,?,?,'2026-09-09','present','record','Mrs Okafor',CURRENT_TIMESTAMP)",
    (school_id, class1, term1),
)

def compute_total(ca1, ca2, ca3, exam):
    return round((ca1 or 0) + (ca2 or 0) + (ca3 or 0) + (exam or 0), 2)


print("=== 1) Student Dashboard: Academic Performance respects publication gating ===")

STUDENT = student_client("chinedu")
sdash = html(STUDENT.get("/student/dashboard"))
check("Academic Performance card present", "Academic Performance" in sdash)
check("published term 1's average appears", "1st Term" in sdash)
expected_t1_avg = round(sum(compute_total(*term1_scores[s]) for s in subjects) / len(subjects), 1)
check("the term-1 average shown matches what was entered", str(expected_t1_avg) in sdash, (expected_t1_avg, sdash))
check("unpublished term 2 never appears in the performance trend", "2nd Term" not in sdash, sdash)

print("=== 2) Student Dashboard: Attendance ===")

check("attendance rate (9 of 10 attended) shown", "90.0%" in sdash, sdash)
check("present/late/absent counts shown correctly (8/1/1)", '<div class="num">8</div>' in sdash and sdash.count('<div class="num">1</div>') >= 2, sdash)

print("=== 3) Student Dashboard: Recent Activities never leaks another student's event ===")

check("Recent Activities card present", "Recent Activities" in sdash)
check("the class's shared result-publication event appears", "Result published" in sdash, sdash)
check("the class's shared material appears", "Term 1 Revision Notes" in sdash, sdash)
check("Amaka's own score-change event never appears on Chinedu's dashboard", "Amaka" not in sdash and "Mrs Okafor" not in sdash, sdash)

print("=== 4) A second student (Amaka) sees only her own data, never Chinedu's ===")

STUDENT2 = student_client("amaka")
sdash2 = html(STUDENT2.get("/student/dashboard"))
check("Amaka's own attendance is independent of Chinedu's (she has none recorded)", "No attendance recorded yet" in sdash2, sdash2)
check("Chinedu's name never appears on Amaka's dashboard", "Chinedu" not in sdash2, sdash2)

print("=== 5) Parent Dashboard: same analytics, scoped to the verified linked child ===")

c = db()
cur = c.cursor()
cur.execute(
    "INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,phone,email) VALUES (1,'1','Mr Parent','mrparent',?,'08011112233','parent@example.com')",
    (pw,),
)
parent_id = cur.lastrowid
cur.execute(
    "INSERT INTO parent_students(parent_id,student_id,school_id,tenant_id,status,verified_at) VALUES (?,1,1,'1','verified',CURRENT_TIMESTAMP)",
    (parent_id,),
)
c.commit()
c.close()

PARENT = parent_client("mrparent")
pdash = html(PARENT.get("/parent/dashboard"))
check("Parent dashboard Academic Performance card present", "Academic Performance" in pdash)
check("parent sees the published term 1 average for their child", "1st Term" in pdash and str(expected_t1_avg) in pdash, pdash)
check("unpublished term 2 never appears to the parent either", "2nd Term" not in pdash, pdash)
check("parent sees the child's attendance rate", "90.0%" in pdash, pdash)
check("parent's Recent Activities never leaks Amaka's event", "Amaka" not in pdash and "Mrs Okafor" not in pdash, pdash)

print("=== 6) Improving / needs-attention subject classification (term1 -> term2, once term2 is published) ===")

run("UPDATE terms SET is_published=1 WHERE id=?", (term2,))
run(
    "INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at,published_by) VALUES (?,?,?,?,'published',CURRENT_TIMESTAMP,1)",
    (school_id, "1", class1, term2),
)
sdash3 = html(STUDENT.get("/student/dashboard"))
check("term 2 now appears once published", "2nd Term" in sdash3, sdash3)
# subjects[0] rose 80->94 (+14.0, improving); subjects[1] fell 68->41 (-27.0, needs attention)
check("an improved subject is flagged as improving", "+14.0" in sdash3, sdash3)
check("a declined subject is flagged as needing attention", "-27.0" in sdash3, sdash3)

print("=== 7) Tenant isolation: a second school's student/parent see nothing of school 1 ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')")
school2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{school2}", f"PUB{school2}", school2))
cur.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (school2, "2025/2026"))
sess2 = cur.lastrowid
cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,1)", ("1st Term", sess2))
cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'Basic 1')", (school2,))
class2 = cur.lastrowid
cur.execute(
    "INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id, username, password_hash) "
    "VALUES (?,?,?,?,?,?,?,?,?)", (school2, "school2", "S2-001", "Bola", "Second", "F", class2, "bola", pw),
)
c.commit()
c.close()

STUDENT3 = student_client("bola")
sdash4 = html(STUDENT3.get("/student/dashboard"))
check("a brand-new student in another school gets the honest empty state", "Nothing to show yet" in sdash4, sdash4)
check("...and never sees anything from school 1", "Chinedu" not in sdash4 and "1st Term" not in sdash4, sdash4)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
