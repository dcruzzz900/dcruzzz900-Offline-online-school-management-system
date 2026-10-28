"""End-to-end scenarios for V88: "Dashboard Analytics Phase 2 -- Gender & Enrolment Statistics" --
  Phase 2 of the 10th requirements doc ("Complete Feature Enhancement Specification").

  1) Admin Dashboard shows exactly ONE combined Boys & Girls statistics card, with figures
     drawn directly from the students table, scoped to the authenticated school, excluding
     inactive (withdrawn/transferred) students and excluding missing/unspecified gender
     values from the boys/girls counts.
  2) Teacher Dashboard shows, for every class the signed-in staff member can see in their
     Results workspace, that class's Total Students / Boys / Girls -- reconciling as
     Total Students = Boys + Girls + Unspecified.
  3) Figures update automatically (no caching/staleness) when a student is registered,
     transferred (deactivated), or their gender changes.
  4) Tenant isolation: a second school's admin never sees the first school's counts.

(own process, fresh DB, real HTTP requests). Run: python tests/v88_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v88_")
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

# Seeded school 1: class 1 (JSS1A) has 3 active students -- 2 boys (Chinedu, Tunde),
# 1 girl (Amaka). Form teacher is aokafor.
class1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]

ADMIN = staff("admin")
TEACHER = staff("aokafor")

print("=== 1) Admin Dashboard: one combined Boys & Girls card, correct starting counts ===")

dash = html(ADMIN.get("/dashboard"))
check("admin dashboard has exactly one gender-stat-card", dash.count('class="gender-stat-card"') == 1, dash.count('class="gender-stat-card"'))
check("admin dashboard shows 2 boys", re.search(r'gender-num">\s*2\s*<', dash) is not None, dash)
check("admin dashboard shows 1 girl", re.search(r'gender-num">\s*1\s*<', dash) is not None, dash)
check("Boys label present", "Boys" in dash)
check("Girls label present", "Girls" in dash)

print("=== 2) Figures are tenant-scoped -- a second school's admin sees only its own ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')")
school2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{school2}", f"PUB{school2}", school2))
cur.execute(
    "INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)",
    (school2, "school2", "Second Admin", "admin2", pw, "admin"),
)
cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'JSS1B')", (school2,))
class2 = cur.lastrowid
cur.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (school2, "2025/2026"))
sess2 = cur.lastrowid
cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,1)", ("1st Term", sess2))
# One girl only, at school 2 -- must never show up in school 1's counts or vice versa.
cur.execute(
    "INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) "
    "VALUES (?,?,?,?,?,?,?)", (school2, "school2", "S2-001", "Zainab", "Bello", "F", class2),
)
c.commit()
c.close()

ADMIN2 = staff("admin2")
dash2 = html(ADMIN2.get("/dashboard"))
check("second school's admin sees 0 boys (not school 1's 2)", re.search(r'gender-num">\s*0\s*<', dash2) is not None, dash2)
check("second school's admin sees 1 girl (only their own)", re.search(r'gender-num">\s*1\s*<', dash2) is not None, dash2)

dash1_again = html(ADMIN.get("/dashboard"))
check("first school's admin is unaffected by school 2's data (still 2 boys, 1 girl)",
      re.search(r'gender-num">\s*2\s*<', dash1_again) is not None and re.search(r'gender-num">\s*1\s*<', dash1_again) is not None)

print("=== 3) Teacher Dashboard: per-class Total/Boys/Girls, reconciling with an unspecified-gender student ===")

tdash = html(TEACHER.get("/dashboard"))
check("teacher dashboard results workspace shows class JSS1A", "JSS1A" in tdash)
check("teacher dashboard shows 3 total students for the class", re.search(r"<td>3</td>", tdash) is not None, tdash)
check("teacher dashboard shows boys/girls figures for the class", "♂ 2" in tdash and "♀ 1" in tdash, tdash)

# Add a 4th student to class 1 with gender left NULL (unspecified) -- must count toward
# Total Students but be excluded from both Boys and Girls.
run(
    "INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) "
    "SELECT school_id, tenant_id, 'U-001', 'Kemi', 'Ade', NULL, class_id FROM students WHERE id=1"
)
tdash2 = html(TEACHER.get("/dashboard"))
check("after adding an unspecified-gender student, class total is now 4", re.search(r"<td>4</td>", tdash2) is not None, tdash2)
check("boys/girls counts for the class are unchanged (unspecified excluded from both)",
      "♂ 2" in tdash2 and "♀ 1" in tdash2, tdash2)

adash_after = html(ADMIN.get("/dashboard"))
check("admin card's boys/girls totals also unaffected by the unspecified-gender student",
      re.search(r'gender-num">\s*2\s*<', adash_after) is not None and re.search(r'gender-num">\s*1\s*<', adash_after) is not None)

print("=== 4) Transferring (deactivating) a student updates the counts immediately ===")

run("UPDATE students SET is_active=0 WHERE id=3")  # Tunde (M) marked inactive/transferred
dash_after_transfer = html(ADMIN.get("/dashboard"))
check("after transferring a boy out, admin boys count drops to 1", re.search(r'gender-num">\s*1\s*<', dash_after_transfer) is not None, dash_after_transfer)
check("deactivated student no longer counted in his class's total on the teacher dashboard",
      re.search(r"<td>3</td>", html(TEACHER.get("/dashboard"))) is not None)
run("UPDATE students SET is_active=1 WHERE id=3")

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
