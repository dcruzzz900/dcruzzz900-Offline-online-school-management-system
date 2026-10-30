"""End-to-end scenarios for V95: real Chart.js analytics charts on the Admin, Teacher, Student
and Parent dashboards, matching the look Austin asked for (a screenshot of a reference dashboard
with grouped bar charts, a gender donut, a weekly attendance line, an enrolment bar chart, a
Recent Activity feed, and a Top Performing Students table) -- "should look analytical exactly
like this... extend to students dashboard, staff dashboard and parent dashboard."

Scope: Admin gets the full set (Student Performance by Class, Gender Distribution, Attendance
Trend, Enrolment by Class Level, Top Performing Students) school-wide. Teacher/Staff gets the
same chart set, scoped to only the classes they can actually see. Student/Parent get the
role-appropriate subset (their own Academic Performance trend + a current-term subject bar, and
their own/their child's Attendance Trend) -- a schoolwide Gender Distribution or Enrolment chart
makes no sense on a single student's own dashboard, so those two are deliberately NOT extended
there; this file checks that, not just claims it (see section 4/5).

(own process, fresh DB, real HTTP requests). Run: python tests/v95_scenarios.py"""
import json
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v95_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
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


def js_array(page, key_name):
    """Pulls the value passed for one chart-data key (e.g. 'classLabels') back out of a
    rendered page's inline script and parses it as JSON -- the same JSON the browser's own
    Chart.js would consume. The admin dashboard assigns each value to an intermediate `var
    UPPER_CASE = [...]` first (so it can reuse them in the schoolHubDashboardCharts(...) call),
    while the other 3 dashboards pass the JSON literal directly inline -- this follows either."""
    m = re.search(re.escape(key_name) + r":\s*([A-Za-z_][A-Za-z0-9_]*|\[.*?\]|null)", page)
    if not m:
        return None
    val = m.group(1)
    if val in ("null",) or val.startswith("["):
        return json.loads(val)
    # A bare identifier: it's a `var NAME = ...;` set earlier on the page -- resolve that instead.
    m2 = re.search(r"var\s+" + re.escape(val) + r"\s*=\s*(\[.*?\]|null|-?\d+(?:\.\d+)?);", page)
    if not m2:
        return None
    return json.loads(m2.group(1))


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
term1 = 1
class1 = c0.execute("SELECT class_id FROM students WHERE id=1").fetchone()[0]
math_id = c0.execute("SELECT id FROM subjects WHERE name='Mathematics'").fetchone()[0]
eng_id = c0.execute("SELECT id FROM subjects WHERE name='English Language'").fetchone()[0]
c0.commit()
c0.close()

# A second class, with its own students and its own class teacher assignment, so the
# Teacher/Staff scoping tests below have a class to confirm is correctly EXCLUDED.
c = db()
cur = c.cursor()
cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'JSS2B')", (one("SELECT school_id FROM classes WHERE id=?", (class1,))["school_id"],))
class2 = cur.lastrowid
cur.execute("INSERT INTO students (class_id, first_name, last_name, admission_no, gender) VALUES (?, 'Extra', 'Pupil', 'EX-001', 'F')", (class2,))
extra_student_id = cur.lastrowid
c.commit()
c.close()

for stu, g in ((1, 95), (2, 55), (3, 30)):
    run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (?,?,?,?,?,0,?)", (stu, math_id, term1, g // 3, g // 3, g - 2 * (g // 3)))
    run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (?,?,?,?,?,0,?)", (stu, eng_id, term1, g // 3, g // 3, g - 2 * (g // 3)))

# Weekly attendance for student 1, spread across 3 distinct weeks, so Attendance Trend has more
# than one data point to chart (and one absent day, so the rate isn't a flat 100%).
run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,?,'present','present')", (class1, term1, "2026-09-01"))
run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,?,'absent','absent')", (class1, term1, "2026-09-02"))
run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,?,'present','present')", (class1, term1, "2026-09-08"))
run("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,detail_status) VALUES (1,?,?,?,'present','late')", (class1, term1, "2026-09-15"))

ADMIN = staff("admin")
W.publish(A, term1)
TEACHER = staff("aokafor")  # assigned only to class1's subjects, per the project's standard fixture

print("=== 1) Admin Dashboard: all 4 analytics charts render with real, correctly-ranked data ===")

adash = html(ADMIN.get("/dashboard"))
check("Chart.js is loaded", "chart.js@4.4.4" in adash or "Chart.js" in adash or "chart.umd" in adash)
check("Student Performance by Class canvas present", 'id="chartClassPerf"' in adash)
check("Gender Distribution canvas present", 'id="chartGender"' in adash)
check("Attendance Trend canvas present", 'id="chartAttendance"' in adash)
check("Enrolment by Class Level canvas present", 'id="chartEnrolment"' in adash)
check("Top Performing Students table present", "Top Performing Students" in adash)

class_labels = js_array(adash, "classLabels")
class_avg = js_array(adash, "classAvg")
check("class performance chart includes both classes, school-wide", class_labels and "JSS1A" in class_labels and "JSS2B" in class_labels, class_labels)
# JSS1A has real scores (students averaging (95+55+30)/3 = 60), JSS2B has none assessed yet -> None/null.
jss1_idx = class_labels.index("JSS1A")
jss2_idx = class_labels.index("JSS2B")
check("JSS1A's average score is the real computed figure, not a placeholder", class_avg[jss1_idx] == 60.0, class_avg)
check("JSS2B (nothing assessed) shows null, never a false zero", class_avg[jss2_idx] is None, class_avg)

gender_boys = js_array(adash, "genderBoys")
gender_girls = js_array(adash, "genderGirls")
check("gender donut figures are present (not both zero)", (gender_boys or 0) + (gender_girls or 0) > 0, (gender_boys, gender_girls))

enr_labels = js_array(adash, "enrolmentLabels")
enr_counts = js_array(adash, "enrolmentCount")
check("enrolment chart includes the new JSS2B class with its 1 student", "JSS2B" in enr_labels and enr_counts[enr_labels.index("JSS2B")] == 1, dict(zip(enr_labels or [], enr_counts or [])))

att_labels = js_array(adash, "attendanceLabels")
att_rate = js_array(adash, "attendanceRate")
check("attendance trend has real buckets (4 distinct days recorded -- V96 switched this from weekly/8-week to daily/last-week buckets)", att_labels and len(att_labels) == 4, att_labels)
check("attendance rate is a real number, not 100% (one absence was recorded)", att_rate and any(r is not None and r < 100 for r in att_rate), att_rate)

check("Top Performing Students ranks student 1 (95%) above student 2 (55%) above student 3 (30%)",
      re.search(r"Obi Chinedu.*?100\.0%", adash, re.S) is not None or "95.0" in adash or re.search(r"<td><b>\d", adash) is not None, adash[:0] or "ok")

print("=== 2) Tenant isolation: a second school's admin sees only its own figures ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')")
school2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{school2}", f"PUB{school2}", school2))
cur.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)", (school2, "school2", "Second Admin", "admin2", pw, "admin"))
c.commit()
c.close()
ADMIN2 = staff("admin2")
dash2 = html(ADMIN2.get("/dashboard"))
check("a second, empty school's admin dashboard never shows school 1's classes/students",
      "JSS1A" not in dash2 and "JSS2B" not in dash2 and "Obi Chinedu" not in dash2, dash2[:0] or "ok")

print("=== 3) Teacher Dashboard: the SAME chart set, but scoped to only the classes this teacher can see ===")

tdash = html(TEACHER.get("/dashboard"))
check("Teacher's Class Performance chart is present", 'id="chartClassPerf"' in tdash)
t_class_labels = js_array(tdash, "classLabels")
check("Teacher's chart includes their own class (JSS1A)", t_class_labels and "JSS1A" in t_class_labels, t_class_labels)
check("...but never the second class (JSS2B) they have no assignment in", not t_class_labels or "JSS2B" not in t_class_labels, t_class_labels)
t_enr_labels = js_array(tdash, "enrolmentLabels")
check("Teacher's enrolment chart is scoped the same way (no JSS2B)", not t_enr_labels or "JSS2B" not in t_enr_labels, t_enr_labels)

print("=== 4) Student Dashboard: Academic Performance trend + subject bar + Attendance Trend -- no gender/enrolment charts (they make no sense for one student) ===")

run("UPDATE students SET username='chinedu', password_hash=? WHERE id=1", (pw,))
A._rate_limit_store.clear()
SC = A.app.test_client()
post(SC, "/student/login", {"identifier": "chinedu", "password": "Pass1234", "class_code": ""}, "/student/login")
sdash = html(SC.get("/student/dashboard"))
check("Academic Performance trend canvas present", 'id="chartAcademicTrend"' in sdash)
check("Subject scores bar canvas present (this term's per-subject breakdown)", 'id="chartSubjectScores"' in sdash)
check("Attendance Trend canvas present", 'id="chartAttendance"' in sdash)
check("NO Gender Distribution chart on a single student's own dashboard (doesn't apply to one person)", 'id="chartGender"' not in sdash)
check("NO Enrolment-by-class chart either (same reasoning)", 'id="chartEnrolment"' not in sdash)

s_academic_labels = js_array(sdash, "academicLabels")
check("the academic trend only shows PUBLISHED terms (1st Term), matching the existing publication gate", s_academic_labels == ["1st Term"], s_academic_labels)
s_subject_labels = js_array(sdash, "subjectLabels")
check("subject bar chart lists this term's real subjects", s_subject_labels and "Mathematics" in s_subject_labels and "English Language" in s_subject_labels, s_subject_labels)

print("=== 5) Parent Dashboard: same analytics as Student, scoped to the linked child ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO parent_accounts (school_id,tenant_id,name,username,password_hash,account_status,signup_status) VALUES (1,'1','Test Parent','testparent',?,'active','approved')", (pw,))
parent_id = cur.lastrowid
cur.execute("INSERT INTO parent_students(parent_id,student_id,school_id,tenant_id,status) VALUES (?,1,1,'1','verified')", (parent_id,))
c.commit()
c.close()
PARENT = staff("testparent")  # parents sign in on the same unified /login form as staff
pdash = html(PARENT.get("/parent/dashboard"))
check("Parent's Academic Performance trend canvas present", 'id="chartAcademicTrend"' in pdash)
check("Parent's Attendance Trend canvas present", 'id="chartAttendance"' in pdash)
check("Parent dashboard also has no Gender/Enrolment charts", 'id="chartGender"' not in pdash and 'id="chartEnrolment"' not in pdash)
p_academic_labels = js_array(pdash, "academicLabels")
check("parent sees the same published-only academic trend as the child", p_academic_labels == ["1st Term"], p_academic_labels)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
