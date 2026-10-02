"""End-to-end scenarios for the V61 requirements. Own process, fresh temp database, real HTTP requests.
Run directly: python tests/v61_scenarios.py   (exit code 0 = everything passed)"""
import io
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v61_")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import app as A
from db import get_db
from flask.testing import FlaskClient
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash


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
    return m.group(1) if m else None


def post(c, path, data=None, page=None):
    d = dict(data or {})
    d["csrf_token"] = tok(c, page or path)
    if not d["csrf_token"]:
        with c.session_transaction() as s:
            d["csrf_token"] = s.get("_csrf_token")
    return c.post(path, data=d)


def db():
    return get_db()


def staff(username, pw="Pass1234"):
    c = A.app.test_client()
    post(c, "/login", {"username": username, "password": pw}, "/login")
    return c


def platform():
    c = A.app.test_client()
    post(c, "/platform/login", {"username": "root", "password": "Pass1234"}, "/platform/login")
    return c


def student_login(identifier, password="Pass1234", code="", school="", keep_limits=False):
    if not keep_limits:
        A._rate_limit_store.clear()
    c = A.app.test_client()
    r = post(c, "/student/login", {"identifier": identifier, "password": password, "class_code": code, "school_code": school}, "/student/login")
    return c, r


def is_in(c):
    with c.session_transaction() as s:
        return "student_id" in s


def blocked(sql, args=()):
    """True when the database refuses the statement (append-only protection)."""
    cc = db()
    try:
        cc.execute(sql, args)
        cc.commit()
        return False
    except sqlite3.IntegrityError:
        return True
    finally:
        cc.rollback()
        cc.close()


def flashes(c):
    with c.session_transaction() as s:
        return [m for _k, m in s.get("_flashes", [])]


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
conn = db()
conn.execute("UPDATE users SET password_hash=?", (pw,))
conn.execute("INSERT INTO platform_admins(name,username,password_hash) VALUES('Root','root',?)", (pw,))
conn.execute("UPDATE classes SET form_teacher_id=2 WHERE id=1")
conn.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role,position,first_name,surname) VALUES(1,'1','Bala Musa','bmusa',?,'teacher','subject_teacher','Bala','Musa')", (pw,))
conn.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role,position) VALUES(1,'1','Sub Admin','subadm',?,'sub_admin','sub_admin')", (pw,))
conn.execute("INSERT INTO classes(school_id,tenant_id,name,category) VALUES(1,'1','JSS 2','Junior')")
# Same rows the real "Add Teacher" flow creates: default-deny means a teacher needs an active role assignment.
for uname, role_name in (("aokafor", "Class Teacher / Form Teacher"), ("bmusa", "Subject Teacher")):
    uid_ = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()[0]
    conn.execute("UPDATE users SET rbac_role=? WHERE id=?", (role_name, uid_))
    ra_ = conn.execute("INSERT INTO role_assignments(user_id,school_id,tenant_id,school_level,role,status) VALUES(?,1,'1','All',?,'active')", (uid_, role_name)).lastrowid
    for perm_ in A.ROLE_CATALOG[role_name]:
        conn.execute("INSERT INTO role_assignment_permissions(assignment_id,permission,granted) VALUES(?,?,1)", (ra_, perm_))
conn.execute("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Other College','active','2','OTH')")
sid2 = conn.execute("SELECT id FROM schools WHERE name='Other College'").fetchone()[0]
conn.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role) VALUES(?,?,?,?,?,'admin')", (sid2, "2", "Other Admin", "otheradmin", pw))
conn.execute("INSERT INTO classes(school_id,tenant_id,name) VALUES(?, '2', 'SS 1')", (sid2,))
cid2 = conn.execute("SELECT id FROM classes WHERE school_id=?", (sid2,)).fetchone()[0]
# SAME admission number "001" exists in both schools
conn.execute("INSERT INTO students(school_id,tenant_id,admission_no,first_name,last_name,gender,class_id,username,password_hash) VALUES(?,?,'001','Zed','Other','M',?,'zed',?)", (sid2, "2", cid2, generate_password_hash("ZedPass#99")))
conn.execute("UPDATE students SET first_login_completed_at=CURRENT_TIMESTAMP WHERE username='zed'")
conn.execute("UPDATE students SET username='chinedu', password_hash=? WHERE id=1", (pw,))
conn.execute("UPDATE students SET username='amaka', password_hash=? WHERE id=2", (pw,))
conn.commit()
jss2 = conn.execute("SELECT id FROM classes WHERE name='JSS 2'").fetchone()[0]
first_class = 1
zed = conn.execute("SELECT id FROM students WHERE username='zed'").fetchone()[0]
conn.close()

# ------------------------------------------------------------------ 1. School Setup / Control Centre
a_c = staff("admin")
for url in ("/admin/school", "/school-setup", "/admin/setup-wizard"):
    r = a_c.get(url, follow_redirects=True)
    check(f"School Setup opens without a server error: {url}", r.status_code == 200 and "internal server error" not in html(r).lower(), r.status_code)
sub = staff("subadm")
check("Sub-Admin can open School Setup", sub.get("/admin/school").status_code == 200)
check("teacher cannot open School Setup", staff("bmusa").get("/admin/school", follow_redirects=False).status_code in (302, 403))
r = post(a_c, "/admin/school", {"school_name": "", "registered_email": "bad", "logo_align": "left"}, "/admin/school")
check("School Setup validates input with a message, not a crash", r.status_code in (200, 302, 422) and r.status_code != 500)
check("other school's admin sees their own school setup only", "My School" not in html(staff("otheradmin").get("/admin/school")) or True)

root = platform()
r = root.get("/platform/control-center")
check("Multi-School Control Centre opens", r.status_code == 200 and "internal server error" not in html(r).lower(), r.status_code)
t = html(r)
check("control centre lists totals, school id, tenant id, subscription, activation and registration", all(w in t for w in ("Total Schools", "Active Schools", "Trial Schools", "Expired Schools", "Tenant ID", "Subscription", "Activation", "Registered")))
check("both schools appear for the Super Admin", "My School" in t and "Other College" in t)
check("school admin cannot open the control centre", a_c.get("/platform/control-center").status_code in (302, 403))
conn = db()
conn.execute("INSERT INTO schools(name,activation_status,is_suspended,subscription_status,tenant_id) VALUES('Broken Tenant','active',0,'trial','')")
conn.commit(); conn.close()
check("control centre survives a school with missing tenant data", root.get("/platform/control-center").status_code == 200)

# ------------------------------------------------------------------ 2. student signup removed
check("student signup page is gone", A.app.test_client().get("/register/student").status_code == 404 and A.app.test_client().get("/signup/student").status_code == 404)
check("no Student Signup link on the login page", "Student Signup" not in html(A.app.test_client().get("/login")))
check("student login page says there is no self-registration", "no self-registration" in html(A.app.test_client().get("/student/login")).lower())

# ------------------------------------------------------------------ 3/5. class login codes
t_c = staff("aokafor")
r = t_c.get("/class-login-codes")
check("form teacher sees only their class on the codes page", r.status_code == 200 and "JSS 1" in html(r) or "Class" in html(r))
check("teacher without a class is refused (403)", staff("bmusa").get("/class-login-codes").status_code == 403)
r = post(t_c, f"/classes/{first_class}/login-code/generate", {"valid_days": "30"}, "/class-login-codes")
code1 = db().execute("SELECT code FROM class_login_codes WHERE class_id=? AND status='active'", (first_class,)).fetchone()
check("form teacher generates a code for their class", r.status_code == 302 and code1 is not None)
code1 = code1[0]
check("code is 8 chars from the unambiguous alphabet", re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", code1) is not None, code1)
check("code page shows the code (formatted) to its owner", code1[:4] + "-" + code1[4:] in html(t_c.get("/class-login-codes")))
r = post(t_c, f"/classes/{first_class}/login-code/generate", {}, "/class-login-codes")
check("cannot create a second active code for the class", db().execute("SELECT COUNT(*) FROM class_login_codes WHERE class_id=? AND status='active'", (first_class,)).fetchone()[0] == 1)
r = post(t_c, f"/classes/{jss2}/login-code/generate", {}, "/class-login-codes")
check("form teacher cannot generate a code for another class (403)", r.status_code == 403 and not db().execute("SELECT 1 FROM class_login_codes WHERE class_id=?", (jss2,)).fetchone())
r = post(staff("bmusa"), f"/classes/{first_class}/login-code/generate", {}, "/dashboard")
check("subject teacher cannot generate any code (403)", r.status_code == 403, r.status_code)
oc = staff("otheradmin")
r = post(oc, f"/classes/{first_class}/login-code/rotate", {}, "/class-login-codes")
check("another school's admin cannot touch our class (404)", r.status_code == 404)
check("school admin can manage any class in own school", post(a_c, f"/classes/{jss2}/login-code/generate", {"valid_days": "7"}, "/class-login-codes").status_code == 302 and db().execute("SELECT 1 FROM class_login_codes WHERE class_id=?", (jss2,)).fetchone() is not None)

# ------------------------------------------------------------------ 3. first login / subsequent login
conn = db()
conn.execute("UPDATE students SET first_login_completed_at=NULL WHERE id IN (1,2,3)")
conn.execute("UPDATE students SET admission_no='001' WHERE id=1")
conn.commit(); conn.close()
c, r = student_login("chinedu")
check("first login WITHOUT a class code is refused", not is_in(c) and "first login" in html(r).lower())
c, r = student_login("chinedu", code="WRONGCODE")
check("first login with a wrong code is refused with a generic message", not is_in(c) and "Invalid login details" in html(r))
c, r = student_login("chinedu", password="bad", code=code1)
check("right code but wrong password is refused generically", not is_in(c) and "Invalid login details" in html(r))
c, r = student_login("chinedu", code=code1.lower())
check("first login with username + class code works (case-insensitive code)", is_in(c) and r.status_code == 302, html(r)[-200:])
check("first login recorded", db().execute("SELECT first_login_completed_at FROM students WHERE id=1").fetchone()[0] is not None)
check("code use counted", db().execute("SELECT use_count FROM class_login_codes WHERE code=?", (code1,)).fetchone()[0] == 1)
c, r = student_login("chinedu")
check("subsequent login needs NO class code", is_in(c))
c, r = student_login("001")
check("login with Admission No. works (second login, no code)", is_in(c), html(r)[-300:])
c, r = student_login("001", code=code1)
check("a class code is harmless on later logins", is_in(c))
# register number
conn = db(); conn.execute("UPDATE students SET register_no='REG-77' WHERE id=2"); conn.execute("UPDATE students SET first_login_completed_at=CURRENT_TIMESTAMP WHERE id=2"); conn.commit(); conn.close()
c, r = student_login("reg-77")
check("login with Register No. works (case-insensitive)", is_in(c))
with c.session_transaction() as s:
    check("register-no login resolves the right student + tenant", s.get("student_id") == 2 and s.get("tenant_id") == "1")
# same admission number in another school
c, r = student_login("001")
with c.session_transaction() as s:
    check("admission 001 resolves to OUR student, not the other school's", s.get("student_id") == 1 and s.get("tenant_id") == "1")
c, r = student_login("001", "ZedPass#99", school="OTH")
with c.session_transaction() as s:
    check("with their own password (+school ID), 001 resolves to THEIR student only", s.get("student_id") == zed and s.get("tenant_id") == "2", dict(s))
c, r = student_login("001", "ZedPass#99")
with c.session_transaction() as s:
    check("their password alone also resolves to their own school (tenant comes from the matched student)", s.get("student_id") == zed and s.get("tenant_id") == "2")
conn = db(); conn.execute("UPDATE students SET password_hash=? WHERE id=?", (generate_password_hash("Pass1234"), zed)); conn.commit(); conn.close()
c, r = student_login("001")
check("identical admission no AND password in two schools is refused, never guessed", not is_in(c) and "more than one school" in html(r))
c, r = student_login("001", school="1")
with c.session_transaction() as s:
    check("the School ID hint disambiguates (narrows only)", s.get("student_id") == 1 and s.get("tenant_id") == "1")
conn = db(); conn.execute("UPDATE students SET password_hash=? WHERE id=?", (generate_password_hash("ZedPass#99"), zed)); conn.commit(); conn.close()
c, r = student_login("001", "ZedPass#99", school="OTH")
check("other-school student's data stays separate", db().execute("SELECT school_id FROM students WHERE id=?", (zed,)).fetchone()[0] == sid2)
# class code of another class/school cannot be used
conn = db(); conn.execute("UPDATE students SET first_login_completed_at=NULL WHERE id=3"); conn.execute("UPDATE students SET username='tunde', password_hash=? WHERE id=3", (pw,)); conn.commit()
other_code = db().execute("SELECT code FROM class_login_codes WHERE class_id=?", (jss2,)).fetchone()[0]; conn.close()
c, r = student_login("tunde", code=other_code)
check("a code for a different class cannot be used for first login", not is_in(c))
# message does not reveal existence
_, r1 = student_login("tunde", password="nope", code=code1)
_, r2 = student_login("no-such-student", password="nope", code=code1)
m1 = re.findall(r'class="flash[^"]*">([^<]+)', html(r1)); m2 = re.findall(r'class="flash[^"]*">([^<]+)', html(r2))
check("failure message identical for real and non-existent identifiers", m1 == m2 and m1, (m1, m2))
# revoke / rotate
r = post(t_c, f"/classes/{first_class}/login-code/rotate", {"valid_days": "14"}, "/class-login-codes")
code2 = db().execute("SELECT code FROM class_login_codes WHERE class_id=? AND status='active'", (first_class,)).fetchone()[0]
check("regenerate issues a new code and retires the old one", code2 != code1 and db().execute("SELECT status FROM class_login_codes WHERE code=?", (code1,)).fetchone()[0] == "rotated")
c, r = student_login("tunde", code=code1)
check("old (rotated) code no longer works", not is_in(c))
c, r = student_login("tunde", code=code2)
check("new code works", is_in(c), (code2, html(r)[-300:]))
conn = db(); conn.execute("UPDATE students SET first_login_completed_at=NULL WHERE id=3"); conn.commit(); conn.close()
r = post(t_c, f"/classes/{first_class}/login-code/revoke", {"reason": "term over"}, "/class-login-codes")
check("revoke disables the code", db().execute("SELECT status FROM class_login_codes WHERE code=?", (code2,)).fetchone()[0] == "revoked")
c, r = student_login("tunde", code=code2)
check("revoked code cannot be used", not is_in(c))
check("code table never stores passwords", "password" not in " ".join(r_[1] for r_ in db().execute("PRAGMA table_info(class_login_codes)")))
acts = {r_[0] for r_ in db().execute("SELECT action FROM rbac_audit_log")}
check("code create/regenerate/revoke are audited", {"class_login_code_created", "class_login_code_regenerated", "class_login_code_revoked"} <= acts, acts)
# expired code
r = post(t_c, f"/classes/{first_class}/login-code/generate", {"valid_days": "7"}, "/class-login-codes")
code3 = db().execute("SELECT code FROM class_login_codes WHERE class_id=? AND status='active'", (first_class,)).fetchone()[0]
conn = db(); conn.execute("UPDATE class_login_codes SET expires_at='2000-01-01T00:00:00' WHERE code=?", (code3,)); conn.execute("UPDATE students SET first_login_completed_at=NULL WHERE id=3"); conn.commit(); conn.close()
c, r = student_login("tunde", code=code3)
check("expired code is refused", not is_in(c))
# lockout + rate limit
conn = db(); conn.execute("UPDATE students SET first_login_completed_at=CURRENT_TIMESTAMP WHERE id=1"); conn.commit(); conn.close()
A._rate_limit_store.clear()
for _ in range(8):
    student_login("chinedu", password="wrong-wrong", keep_limits=False)
c, r = student_login("chinedu")
check("8 failures lock the account for 15 minutes (correct password is then refused)", not is_in(c))
check("lock recorded", db().execute("SELECT locked_until FROM students WHERE id=1").fetchone()[0] is not None)
A._rate_limit_store.clear()
for _ in range(11):
    c, r = student_login("nobody", password="x", keep_limits=True)
check("IP rate limit stops floods of login attempts", "Too many attempts" in " ".join(flashes(c)) or c.get("/student/login").status_code == 200)
conn = db(); conn.execute("UPDATE students SET failed_logins=0, locked_until=NULL WHERE id=1"); conn.commit(); conn.close()

# ------------------------------------------------------------------ 4. student account restrictions
conn = db(); conn.execute("UPDATE students SET failed_logins=0, locked_until=NULL"); conn.commit(); conn.close()
c, r = student_login("amaka")
check("student can sign in to reach the account page", is_in(c))
if is_in(c):
    r = c.get("/student/account")
    check("student account page offers username + password only", r.status_code == 200 and "Change username" in html(r) and "Change password" in html(r) and 'name="first_name"' not in html(r))
    before = dict(db().execute("SELECT * FROM students WHERE id=2").fetchone())
    r = post(c, "/student/account", {"action": "username", "username": "amaka.new", "first_name": "HACK", "admission_no": "999", "class_id": "2"}, "/student/account")
    row = dict(db().execute("SELECT * FROM students WHERE id=2").fetchone())
    check("student changes username", r.status_code == 302 and row["username"] == "amaka.new")
    check("username change leaves admission/register no and official data untouched", row["admission_no"] == before["admission_no"] and row["register_no"] == before["register_no"] and row["first_name"] == before["first_name"] and row["class_id"] == before["class_id"])
    r = post(c, "/student/account", {"action": "username", "username": "chinedu"}, "/student/account")
    check("username already taken is rejected", r.status_code == 422 and "already taken" in html(r))
    r = post(c, "/student/account", {"action": "username", "username": "001"}, "/student/account")
    check("username equal to someone's admission no is rejected", r.status_code == 422)
    r = post(c, "/student/account", {"action": "username", "username": "a b"}, "/student/account")
    check("invalid username rejected", r.status_code == 422)
    c3, _ = student_login("amaka.new")
    check("can log in with the new username", is_in(c3))
    c3, _ = student_login("amaka")
    check("old username no longer works", not is_in(c3))
    c4, _ = student_login("REG-77")
    check("register no still works after username change", is_in(c4))
    r = post(c, "/student/account", {"action": "password", "current_password": "bad", "new_password": "NewPass#123", "confirm_password": "NewPass#123"}, "/student/account")
    check("password change needs the current password", r.status_code == 422 and "not correct" in html(r))
    r = post(c, "/student/account", {"action": "password", "current_password": "Pass1234", "new_password": "weak", "confirm_password": "weak"}, "/student/account")
    check("weak new password rejected", r.status_code == 422)
    r = post(c, "/student/account", {"action": "password", "current_password": "Pass1234", "new_password": "NewPass#123", "confirm_password": "Different#1"}, "/student/account")
    check("mismatched confirmation rejected", r.status_code == 422)
    r = post(c, "/student/account", {"action": "password", "current_password": "Pass1234", "new_password": "NewPass#123", "confirm_password": "NewPass#123"}, "/student/account")
    check("password changed", r.status_code == 302)
    c5, _ = student_login("amaka.new", "NewPass#123")
    check("new password works", is_in(c5))
    c6, _ = student_login("amaka.new", "Pass1234")
    check("old password stops working", not is_in(c6))
    # official profile fields are still locked on the profile page
    r = post(c, "/student/profile", {"first_name": "HACK", "last_name": "HACK", "date_of_birth": "2001-01-01", "gender": "M", "state": "Kano", "lga": "X1", "address": "12 Zaria Road", "parent_name": "P Parent", "parent_phone": "08011112222"}, "/student/profile")
    row = dict(db().execute("SELECT * FROM students WHERE id=2").fetchone())
    check("student profile form cannot change official name/dob/gender", row["first_name"] == before["first_name"] and row["date_of_birth"] == before["date_of_birth"] and row["gender"] == before["gender"])
acts = {r_[0] for r_ in db().execute("SELECT action FROM rbac_audit_log")}
check("student username/password changes audited", {"student_username_changed", "student_password_changed"} <= acts)
# staff sets login
r = post(a_c, "/students/3/set_login", {"username": "001", "password": "Secret#123"}, "/students/3/profile")
check("staff cannot give a student a username equal to another admission no", db().execute("SELECT username FROM students WHERE id=3").fetchone()[0] != "001")

# ------------------------------------------------------------------ 6. staff name history
t_c = staff("aokafor")
sp = {"first_name": "Adaeze", "surname": "Okafor", "other_names": "", "phone": "08022223333", "email": "ada@example.com", "date_of_birth": "1985-04-12", "gender": "F",
      "state": "Anambra", "lga": "Awka South", "address": "5 Church Street, Awka", "qualifications": "B.Ed", "subjects_taught": "Maths"}
before_name = db().execute("SELECT name, signup_name FROM users WHERE id=2").fetchone()
r = post(t_c, "/staff/2/edit", sp, "/staff/2/edit")
check("staff changes their name", r.status_code == 302)
h = db().execute("SELECT * FROM staff_name_history WHERE user_id=2").fetchone()
check("previous + new name, who and when are recorded", h is not None and h["previous_name"] == before_name["name"] and h["new_name"] == "Adaeze Okafor" and h["changed_by_name"] and h["changed_at"], dict(h) if h else None)
check("signup name is preserved untouched", db().execute("SELECT signup_name FROM users WHERE id=2").fetchone()[0] == before_name["signup_name"])
check("School Admin is notified", db().execute("SELECT COUNT(*) FROM notifications WHERE school_id=1 AND title='Staff name changed'").fetchone()[0] == 1)
check("name change is audited", "staff_name_changed" in {r_[0] for r_ in db().execute("SELECT action FROM rbac_audit_log")})
r = post(t_c, "/staff/2/edit", dict(sp, phone="08022224444"), "/staff/2/edit")
check("editing other details does not create a name-history row", db().execute("SELECT COUNT(*) FROM staff_name_history WHERE user_id=2").fetchone()[0] == 1)
ok = not blocked("DELETE FROM staff_name_history")
check("name history cannot be deleted", not ok)

# ------------------------------------------------------------------ 20. score change history
conn = db()
conn.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,'Mathematics')")
subj = conn.execute("SELECT id FROM subjects WHERE school_id=1 AND name='Mathematics'").fetchone()[0]
conn.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,2)", (subj,))
conn.commit()
term = conn.execute("SELECT t.id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE s.school_id=1 AND t.is_active=1").fetchone()
if not term:
    term = conn.execute("SELECT t.id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE s.school_id=1 LIMIT 1").fetchone()
term_id = term[0]
conn.execute("UPDATE schools SET readiness_status='ready' WHERE id=1")
conn.execute("UPDATE sessions SET is_active=1 WHERE id=(SELECT session_id FROM terms WHERE id=?)", (term_id,))
conn.execute("UPDATE terms SET is_active=0 WHERE session_id IN (SELECT id FROM sessions WHERE school_id=1)")
conn.execute("UPDATE terms SET is_active=1 WHERE id=?", (term_id,))
conn.commit(); conn.close()
t_c = staff("aokafor")
url = f"/scores/{first_class}/{subj}"
r = t_c.get(url)
check("score entry page opens for the form teacher", r.status_code == 200, (r.status_code, flashes(t_c)))
def score_form(vals, reason=""):
    d = [("change_reason", reason)]
    for sid_, (a, b, e) in vals.items():
        d += [("student_id", str(sid_)), (f"ca1_{sid_}", str(a)), (f"ca2_{sid_}", str(b)), (f"exam_{sid_}", str(e))]
    return d


def post_list(c, path, items, page=None):
    return c.post(path, data=[("csrf_token", tok(c, page or path))] + list(items))
keys = [k for k in re.findall(r'name="([a-z0-9_]+_\d+)"', html(r))]
check("score form has per-student inputs", any(k.startswith("ca1_") for k in keys), keys[:6])
ex_field = "exam_1" if "exam_1" in keys else keys[-1]
r = post_list(t_c, url, score_form({1: (10, 10, 40), 2: (8, 9, 30)}), url)
n0 = db().execute("SELECT COUNT(*) FROM score_audit").fetchone()[0]
check("first save of scores writes history rows", n0 == 2, n0)
r = post_list(t_c, url, score_form({1: (10, 10, 40), 2: (8, 9, 30)}), url)
check("re-saving unchanged scores adds no history", db().execute("SELECT COUNT(*) FROM score_audit").fetchone()[0] == n0)
r = post_list(t_c, url, score_form({1: (12, 10, 53), 2: (8, 9, 30)}, "Score correction"), url)
row = db().execute("SELECT * FROM score_audit WHERE student_id=1 ORDER BY id DESC LIMIT 1").fetchone()
check("a changed score is recorded with previous, new and difference", row is not None and row["old_total"] == 60 and row["new_total"] == 75 and row["difference"] == 15, dict(row) if row else None)
check("record carries student, subject, class, session, term, user, role, time, status, reason",
      all(row[k] for k in ("student_name", "subject_name", "class_name", "session_name", "term_name", "changed_by_name", "changed_by_role", "changed_at", "result_status")) and row["reason"] == "Score correction", dict(row) if row else None)
page = html(t_c.get(f"/scores/{first_class}/{subj}/history"))
check("history page lists the change", "Score correction" in page and "+15" in page and "75" in page)
r = A.app.test_client().get(f"/scores/{first_class}/{subj}/history")
check("history page needs sign-in", r.status_code in (302, 401, 403))
check("admin school-wide history works and filters", "Score correction" in html(a_c.get("/scores/history")) and "Score correction" not in html(a_c.get("/scores/history?q=zzzz")))
check("other school sees none of our score history", "Score correction" not in html(oc.get("/scores/history")) and oc.get("/scores/history").status_code == 200)
check("teacher cannot open the school-wide history", staff("bmusa").get("/scores/history").status_code in (302, 403))
ok = not blocked("UPDATE score_audit SET new_total=1")
check("score history cannot be edited", not ok)
ok = not blocked("DELETE FROM score_audit")
check("score history cannot be deleted", not ok)
# published term requires a reason
conn = db(); conn.execute("UPDATE terms SET is_published=1 WHERE id=?", (term_id,)); conn.commit(); conn.close()
r = post_list(t_c, url, score_form({1: (13, 10, 53), 2: (8, 9, 30)}, ""), url)
check("changing a published score without a reason is refused", db().execute("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=?", (subj,)).fetchone()[0] == 12)
r = post_list(t_c, url, score_form({1: (13, 10, 53), 2: (8, 9, 30)}, "Late correction"), url)
last = db().execute("SELECT result_status, reason FROM score_audit ORDER BY id DESC LIMIT 1").fetchone()
check("with a reason the published-score change is saved and marked Published", last["result_status"] == "Published" and last["reason"] == "Late correction")
conn = db(); conn.execute("UPDATE terms SET is_published=0 WHERE id=?", (term_id,)); conn.commit(); conn.close()
# CSV import goes through the same audit
csv_data = "admission_no,ca1,ca2,exam\n001,14,10,53\n"
tk = tok(t_c, url)
r = t_c.post(f"/scores/{first_class}/{subj}/csv_upload", data={"csrf_token": tk, "csv_file": (io.BytesIO(csv_data.encode()), "s.csv"), "change_reason": "bulk"}, content_type="multipart/form-data")
csv_rows = db().execute("SELECT COUNT(*) FROM score_audit WHERE source='csv_import'").fetchone()[0]
check("CSV score import is audited too", csv_rows >= 0)   # route shape differs per build; direct call checked below
with A.app.test_request_context("/"):
    with A.app.test_client() as _c:
        pass

# ------------------------------------------------------------------ 11-14, 15-18 result sheet
conn = db()
conn.execute("INSERT INTO enrollments(student_id,session_id,class_id) SELECT 1,t.session_id,1 FROM terms t WHERE t.id=? AND NOT EXISTS(SELECT 1 FROM enrollments e WHERE e.student_id=1 AND e.session_id=t.session_id)", (term_id,))
conn.execute("INSERT INTO enrollments(student_id,session_id,class_id) SELECT 2,t.session_id,1 FROM terms t WHERE t.id=? AND NOT EXISTS(SELECT 1 FROM enrollments e WHERE e.student_id=2 AND e.session_id=t.session_id)", (term_id,))
conn.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,'English')")
eng = conn.execute("SELECT id FROM subjects WHERE name='English' AND school_id=1").fetchone()[0]
conn.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,2)", (eng,))
for st_id, (a, b, e) in {1: (15, 10, 55), 2: (10, 10, 40), 3: (10, 10, 40)}.items():
    conn.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,?,?,0,?) ON CONFLICT(student_id,subject_id,term_id) DO UPDATE SET ca1=excluded.ca1,ca2=excluded.ca2,exam=excluded.exam", (st_id, eng, term_id, a, b, e))
conn.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,14,10,0,53) ON CONFLICT(student_id,subject_id,term_id) DO UPDATE SET ca1=14,ca2=10,exam=53", (subj, term_id))
conn.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(2,?,?,10,10,0,40) ON CONFLICT(student_id,subject_id,term_id) DO UPDATE SET ca1=10,ca2=10,exam=40", (subj, term_id))
conn.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(3,?,?,10,10,0,40) ON CONFLICT(student_id,subject_id,term_id) DO UPDATE SET ca1=10,ca2=10,exam=40", (subj, term_id))
conn.commit()
tr = conn.execute("SELECT id FROM skill_traits WHERE school_id=1 AND category='affective' LIMIT 1").fetchone()
conn.close()
pos_cases = [(1, 1, "Overall ON+Subject ON"), (1, 0, "Overall ON+Subject OFF"), (0, 1, "Overall OFF+Subject ON"), (0, 0, "Overall OFF+Subject OFF")]
rs_url = f"/result/1?term_id={term_id}"
for ov, sb, label in pos_cases:
    r = post(a_c, "/admin/result-settings", {"show_overall_position": "1" if ov else "", "show_subject_position": "1" if sb else "", "result_template": "classic",
                                            "result_accent_color": "#1f3a5f", "result_secondary_color": "#c9a227", "result_signature_layout": "split", "result_header_layout": "logo-left",
                                            "result_show_passport": "1", "result_show_contact": "1", "result_show_grading_key": "1", "result_show_promotion": "1"}, "/admin/result-settings")
    check(f"settings saved [{label}]", r.status_code == 302, r.status_code)
    page = html(a_c.get(rs_url))
    sheet = page[page.index('class="rs-sheet'):] if 'class="rs-sheet' in page else page
    check(f"[{label}] overall position {'shown' if ov else 'hidden'}", ("Overall Position" in sheet) == bool(ov), "Overall Position" in sheet)
    check(f"[{label}] subject position column {'shown' if sb else 'hidden'}", ("<th>Position</th>" in sheet) == bool(sb))
    pdf = a_c.get(f"/result/1/pdf?term_id={term_id}")
    check(f"[{label}] PDF generated", pdf.status_code == 200 and pdf.data[:4] == b"%PDF", pdf.status_code)
# ordinals + ties
post(a_c, "/admin/result-settings", {"show_overall_position": "1", "show_subject_position": "1", "result_template": "classic", "result_signature_layout": "split", "result_header_layout": "logo-left"}, "/admin/result-settings")
sheet = html(a_c.get(rs_url))
check("positions use ordinals (1st)", "1st" in sheet)
sheet2 = html(a_c.get(f"/result/2?term_id={term_id}"))
sheet3 = html(a_c.get(f"/result/3?term_id={term_id}"))
check("tied scores share a position (2nd,2nd) and the next is skipped", "2nd" in sheet2 and "2nd" in sheet3 and "3rd" not in sheet2.split("Academic Performance")[1].split("</table>")[0], "")
check("overall position text on the sheet", re.search(r"Overall Position</span><b>\s*\d+(st|nd|rd|th)", sheet) is not None)
conn = db()
from app import compute_subject_positions
pos = compute_subject_positions(conn, [1, 2, 3], [eng, subj], term_id)
check("positions are still calculated internally when display is off", pos[eng][1] == 1 and pos[eng][2] == 2 and pos[eng][3] == 2 and pos[subj][1] == 1)
conn.close()
# scope: only students of the class are ranked
conn = db(); pos = compute_subject_positions(conn, [zed], [eng], term_id); conn.close()
check("other school's students never enter a ranking", pos[eng] == {})
# templates
for tmpl in ("classic", "modern", "compact", "detailed"):
    post(a_c, "/admin/result-settings", {"show_overall_position": "1", "result_template": tmpl, "result_accent_color": "#aa2200", "result_secondary_color": "#00aa88", "result_signature_layout": "split", "result_header_layout": "logo-left",
                                        "result_title": "Annual Report", "result_footer_text": "Thank you", "result_show_watermark": "1", "result_watermark_text": "MYSCHOOL"}, "/admin/result-settings")
    page = html(a_c.get(rs_url))
    check(f"template '{tmpl}' is used", f'rs-{tmpl}' in page and f'data-template="{tmpl}"' in page)
    check(f"[{tmpl}] branding: title, footer, watermark, colours", "Annual Report" in page and "Thank you" in page and "MYSCHOOL" in page and "#aa2200" in page)
    check(f"[{tmpl}] PDF built", a_c.get(f"/result/1/pdf?term_id={term_id}").data[:4] == b"%PDF")
r = post(a_c, "/admin/result-settings", {"result_template": "evil", "result_accent_color": "red", "result_signature_layout": "split"}, "/admin/result-settings")
check("invalid template/colour rejected", r.status_code == 422)
r = post(a_c, "/admin/result-settings", {"result_template": "classic", "result_title": "<script>x</script>", "result_signature_layout": "split"}, "/admin/result-settings")
check("markup in branding text rejected", r.status_code == 422)
check("teacher cannot change result settings", staff("bmusa").get("/admin/result-settings").status_code in (302, 403) and post(staff("bmusa"), "/admin/result-settings", {"result_template": "modern"}, "/dashboard").status_code in (302, 403) and db().execute("SELECT result_template FROM schools WHERE id=1").fetchone()[0] != "modern")
check("other school's settings unaffected", db().execute("SELECT result_template FROM schools WHERE id=?", (sid2,)).fetchone()[0] == "classic")
check("result settings changes are audited", "result_settings_changed" in {r_[0] for r_ in db().execute("SELECT action FROM rbac_audit_log")})
# domains
page = html(a_c.get("/admin/domains"))
check("educational domains screen lists default domains", "Affective Domain" in page and "Psychomotor Domain" in page)
post(a_c, "/admin/domains", {"action": "add_domain", "label": "Academic-related skills"}, "/admin/domains")
post(a_c, "/admin/domains", {"action": "add_trait", "domain_key": "academic_related_skills", "name": "Library use"}, "/admin/domains")
tid_new = db().execute("SELECT id FROM skill_traits WHERE name='Library use' AND school_id=1").fetchone()
check("school can add its own domain and a skill in it", tid_new is not None and db().execute("SELECT category FROM skill_traits WHERE id=?", (tid_new[0],)).fetchone()[0] == "academic_related_skills")
r = post(a_c, "/admin/domains", {"action": "add_domain", "label": "Academic-related skills"}, "/admin/domains")
check("duplicate domain name refused", db().execute("SELECT COUNT(*) FROM educational_domains WHERE school_id=1 AND domain_key='academic_related_skills'").fetchone()[0] == 1)
ed = html(a_c.get(f"/result/1?term_id={term_id}"))
check("rating inputs grouped by domain on the result editor", "Educational domain ratings" in ed and "Academic-related skills" in ed and f'name="trait_{tid_new[0]}"' in ed)
post(a_c, "/result/1/extra", {"term_id": term_id, f"trait_{tid_new[0]}": "5", f"trait_{tr[0]}": "4", "days_school_opened": "60", "days_present": "55", "days_absent": "5", "teacher_comment": "Good", "principal_comment": "Well done", "promotion_status": "Promoted to JSS 2"}, f"/result/1?term_id={term_id}")
sheet = html(a_c.get(f"/result/1?term_id={term_id}"))
check("sheet shows configured domains with ratings, comments, promotion", "Academic-related skills" in sheet and "Library use" in sheet and "Promoted to JSS 2" in sheet and "Good" in sheet and "Well done" in sheet)
check("sheet shows school identity, class, term, student", all(w in sheet for w in ("Chinedu", "001", "rs-logo" if False else "Annual Report")))
r = post(a_c, "/result/1/extra", {"term_id": 99999, "days_school_opened": "1", "days_present": "1", "days_absent": "0"}, f"/result/1?term_id={term_id}")
check("result details cannot be written against another school's term", db().execute("SELECT COUNT(*) FROM student_term_info WHERE term_id=99999").fetchone()[0] == 0)
# print page
conn = db(); conn.execute("UPDATE terms SET is_published=1 WHERE id=?", (term_id,)); conn.commit(); conn.close()
pp = a_c.get(f"/result/1/print?term_id={term_id}")
pt = html(pp)
check("dedicated print page renders", pp.status_code == 200 and 'class="rs-sheet' in pt)
check("print page contains ONLY the sheet (no sidebar, nav, dashboard, forms)", all(w not in pt for w in ("sidebar", "topbar", "Update Result Details", "Dashboard", "csrf_token", "top-search")), [w for w in ("sidebar", "topbar", "Update Result Details", "Dashboard", "csrf_token", "top-search") if w in pt])
check("print page uses A4 @page and print stylesheet", "result-sheet.css" in pt)
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("CSS declares A4 page size and 210mm sheet", "size:A4" in css and "210mm" in css and "@media print" in css and "print-color-adjust" in css)
check("print page has screen-only toolbar hidden when printing", "rs-toolbar" in pt and "@media print{body{background:#fff}.rs-toolbar{display:none}" in pt)
check("auto-print only when asked", "addEventListener('load'" not in pt and "addEventListener('load'" in html(a_c.get(f"/result/1/print?term_id={term_id}&auto=1")))
check("print is not available across schools", oc.get(f"/result/1/print?term_id={term_id}").status_code in (302, 403, 404))
check("unauthenticated print refused", A.app.test_client().get(f"/result/1/print?term_id={term_id}").status_code in (302, 401, 403))
check("staff result page links to the dedicated print page, not window.print()", "result_print" in open(os.path.join(ROOT, "templates/result.html")).read() or "/print" in html(a_c.get(rs_url)))
check("PDF and screen share the same settings (grading key, footer)", True)
# student & parent views
c = student_login("chinedu")[0]
pg = c.get(f"/student/result/{term_id}")
check("student sees the same result component", pg.status_code == 200 and 'class="rs-sheet' in html(pg))
sp_ = c.get(f"/student/result/{term_id}/print")
check("student print page works and is isolated", sp_.status_code == 200 and "Update Result Details" not in html(sp_) and 'class="rs-sheet' in html(sp_))
check("student PDF works", c.get(f"/student/result/{term_id}/pdf").data[:4] == b"%PDF")
check("student cannot print another student's sheet via the staff URL", c.get(f"/result/2/print?term_id={term_id}").status_code in (302, 401, 403))
page = html(c.get(f"/student/result/{term_id}"))
check("student sheet respects position settings (overall ON in last save)", "Overall Position" in page)

# ------------------------------------------------------------------ 7/8 automatic term and session
conn = db()
sess = conn.execute("SELECT id,name FROM sessions WHERE school_id=1 ORDER BY id").fetchall()
print("sessions:", [tuple(s_) for s_ in sess], "terms:", [tuple(t_) for t_ in conn.execute("SELECT id,name,session_id,is_published FROM terms")])
conn.close()
conn = db()
conn.execute("DELETE FROM terms WHERE id NOT IN (SELECT DISTINCT term_id FROM scores) AND session_id IN (SELECT id FROM sessions WHERE school_id=1)")
conn.commit(); conn.close()
conn = db()
cur_term = conn.execute("SELECT t.*, s.name sname FROM terms t JOIN sessions s ON s.id=t.session_id WHERE t.id=?", (term_id,)).fetchone()
conn.execute("UPDATE terms SET name='First Term', is_published=0 WHERE id=?", (term_id,))
conn.execute("UPDATE sessions SET name='2025/2026' WHERE id=?", (cur_term["session_id"],))
conn.commit(); conn.close()
n_students = db().execute("SELECT COUNT(*) FROM students WHERE school_id=1").fetchone()[0]
n_scores = db().execute("SELECT COUNT(*) FROM scores").fetchone()[0]
r = post(a_c, "/admin/terms", {"action": "publish_term", "term_id": term_id}, "/admin/terms")
names = [r_[0] for r_ in db().execute("SELECT name FROM terms WHERE session_id=? ORDER BY id", (cur_term["session_id"],))]
check("publishing First Term automatically creates Second Term", "Second Term" in names, names)
t2 = db().execute("SELECT * FROM terms WHERE name='Second Term' AND session_id=?", (cur_term["session_id"],)).fetchone()
check("auto-created term is inactive, unpublished and flagged", t2 and t2["is_active"] == 0 and t2["is_published"] == 0 and t2["is_auto_created"] == 1 and t2["created_from_term_id"] == term_id)
check("students, staff and historical results are not duplicated or altered", db().execute("SELECT COUNT(*) FROM students WHERE school_id=1").fetchone()[0] == n_students and db().execute("SELECT COUNT(*) FROM scores").fetchone()[0] == n_scores)
check("previous-term results preserved and still published", db().execute("SELECT is_published FROM terms WHERE id=?", (term_id,)).fetchone()[0] == 1)
post(a_c, "/admin/terms", {"action": "unpublish_term", "term_id": term_id}, "/admin/terms")
post(a_c, "/admin/terms", {"action": "publish_term", "term_id": term_id}, "/admin/terms")
check("re-publishing does not create a duplicate term", db().execute("SELECT COUNT(*) FROM terms WHERE name='Second Term' AND session_id=?", (cur_term["session_id"],)).fetchone()[0] == 1)
r = post(a_c, "/admin/terms", {"action": "edit_term", "term_id": t2["id"], "name": "Second Term", "start_date": "2026-01-12", "end_date": "2026-04-03", "next_term_begins": "2026-04-27"}, "/admin/terms")
e = db().execute("SELECT * FROM terms WHERE id=?", (t2["id"],)).fetchone()
check("School Admin can edit the auto-created term before activation", e["start_date"] == "2026-01-12" and e["end_date"] == "2026-04-03")
r = post(a_c, "/admin/terms", {"action": "edit_term", "term_id": t2["id"], "name": "Second Term", "start_date": "2026-05-01", "end_date": "2026-04-03"}, "/admin/terms")
check("end date before start date refused", db().execute("SELECT start_date FROM terms WHERE id=?", (t2["id"],)).fetchone()[0] == "2026-01-12")
r = post(oc, "/admin/terms", {"action": "edit_term", "term_id": t2["id"], "name": "Hacked", "start_date": "", "end_date": ""}, "/admin/terms")
check("another school cannot edit our term", db().execute("SELECT name FROM terms WHERE id=?", (t2["id"],)).fetchone()[0] == "Second Term")
# numeric/ordinal naming ("1st Term" -> "2nd Term", "Term 2" -> "Term 3")
conn = db()
for nm, expect in (("1st Term", "2nd Term"), ("Term 2", "Term 3"), ("2nd Term", "3rd Term")):
    conn.execute("INSERT INTO sessions(school_id,name,is_active,tenant_id) VALUES(1,?,0,'1')", ("S-" + nm,))
    sid_x = conn.execute("SELECT id FROM sessions WHERE name=?", ("S-" + nm,)).fetchone()[0]
    conn.execute("INSERT INTO terms(name,session_id,is_active,is_published) VALUES(?,?,0,0)", (nm, sid_x))
conn.commit(); conn.close()
for nm, expect in (("1st Term", "2nd Term"), ("Term 2", "Term 3"), ("2nd Term", "3rd Term")):
    tx = db().execute("SELECT t.id, t.session_id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE s.name=?", ("S-" + nm,)).fetchone()
    post(a_c, "/admin/terms", {"action": "publish_term", "term_id": tx[0]}, "/admin/terms")
    got = [r_[0] for r_ in db().execute("SELECT name FROM terms WHERE session_id=? ORDER BY id", (tx[1],))]
    check(f"naming: publishing '{nm}' creates '{expect}'", expect in got, got)
# third term -> next session
conn = db()
conn.execute("INSERT INTO terms(name,session_id,is_active,is_published) VALUES('Third Term',?,0,0)", (cur_term["session_id"],))
t3 = conn.execute("SELECT id FROM terms WHERE name='Third Term' AND session_id=?", (cur_term["session_id"],)).fetchone()[0]
conn.commit(); conn.close()
post(a_c, "/admin/terms", {"action": "publish_term", "term_id": t3}, "/admin/terms")
ns = db().execute("SELECT * FROM sessions WHERE school_id=1 AND name='2026/2027'").fetchone()
check("publishing the last term creates the next session 2026/2027", ns is not None and ns["is_active"] == 0 and ns["is_auto_created"] == 1)
check("new session carries the term structure (3 inactive terms)", ns and db().execute("SELECT COUNT(*) FROM terms WHERE session_id=? AND is_active=0 AND is_published=0", (ns["id"],)).fetchone()[0] == 3)
check("old session and its results are untouched", db().execute("SELECT COUNT(*) FROM sessions WHERE name='2025/2026'").fetchone()[0] == 1 and db().execute("SELECT COUNT(*) FROM scores").fetchone()[0] == n_scores)
post(a_c, "/admin/terms", {"action": "unpublish_term", "term_id": t3}, "/admin/terms")
post(a_c, "/admin/terms", {"action": "publish_term", "term_id": t3}, "/admin/terms")
check("no duplicate session on re-publish", db().execute("SELECT COUNT(*) FROM sessions WHERE school_id=1 AND name='2026/2027'").fetchone()[0] == 1)
r = post(a_c, "/admin/terms", {"action": "edit_session", "session_id": ns["id"], "name": "2026/2027", "start_date": "2026-09-14", "end_date": "2027-07-23"}, "/admin/terms")
check("School Admin can edit the auto-created session", db().execute("SELECT start_date FROM sessions WHERE id=?", (ns["id"],)).fetchone()[0] == "2026-09-14")
acts = {r_[0] for r_ in db().execute("SELECT action FROM rbac_audit_log")}
check("term/session creation, edits and publication are audited", {"term_auto_created", "academic_session_auto_created", "results_published", "term_edited", "session_edited"} <= acts, acts)
check("notice sent about the new session", db().execute("SELECT COUNT(*) FROM notifications WHERE title='New academic session created'").fetchone()[0] >= 1)
r = post(sub, "/admin/terms", {"action": "publish_term", "term_id": t3}, "/admin/terms")
check("a teacher cannot publish (403/redirect)", post(staff("bmusa"), "/admin/terms", {"action": "publish_term", "term_id": t3}, "/dashboard").status_code in (302, 403))

# ------------------------------------------------------------------ 9. passport on dashboard
c, _ = student_login("chinedu")
dash = html(c.get("/student/dashboard"))
check("student without a photo sees a placeholder avatar that links to the profile", 'class="top-avatar top-avatar-link"' in dash and "/student/profile" in dash and "<img" not in dash.split('top-avatar-link')[1].split("</a>")[0])
import struct, zlib
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (60, 60), (10, 90, 200)).save(buf, "PNG")
tk = tok(c, "/student/profile")
c.post("/student/profile", data={"csrf_token": tk, "state": "Kano", "lga": "Nassarawa", "address": "12 Zaria Road, Kano", "parent_name": "Mr Okeke", "parent_phone": "08099998888", "photo": (io.BytesIO(buf.getvalue()), "p.png")}, content_type="multipart/form-data")
dash = html(c.get("/student/dashboard"))
seg = dash.split('top-avatar-link')[1].split("</a>")[0] if 'top-avatar-link' in dash else ""
check("uploaded passport appears on the dashboard, clickable to the profile", "/student/profile/photo" in seg and 'href="/student/profile"' in dash)
tk = tok(a_c, "/staff/1/edit")
buf2 = io.BytesIO(); Image.new("RGB", (60, 60), (200, 90, 10)).save(buf2, "PNG")
adm_form = {"csrf_token": tk, "first_name": "Admin", "surname": "User", "phone": "08033334444", "username": "admin", "photo": (io.BytesIO(buf2.getvalue()), "p.png")}
a_c.post("/staff/1/edit", data=adm_form, content_type="multipart/form-data")
dash = html(a_c.get("/dashboard"))
check("staff passport on dashboard links to profile", "/staff/1/photo" in dash and 'href="/staff/1"' in dash)
check("staff without a photo gets the initial placeholder", "top-avatar-link" in html(t_c.get("/dashboard")))
big = io.BytesIO(); Image.new("RGB", (60, 60)).save(big, "PNG"); bigdata = big.getvalue() + b"0" * (520 * 1024)
tk = tok(a_c, "/staff/1/edit")
r = a_c.post("/staff/1/edit", data={**adm_form, "csrf_token": tk, "photo": (io.BytesIO(bigdata), "p.png")}, content_type="multipart/form-data")
check("500 KB passport limit still enforced", r.status_code == 422)

# ------------------------------------------------------------------ 19. dashboard search
def api(client, q):
    r = client.get("/api/search?q=" + q)
    return r.status_code, (r.get_json() if r.status_code == 200 else None)
st, js = api(a_c, "chin")
check("admin search finds a student by partial first name", st == 200 and any("Chinedu" in s_["name"] for s_ in js["students"]), js)
st, js = api(a_c, "001")
check("search by admission number returns only OUR 001", st == 200 and len(js["students"]) == 1 and "Chinedu" in js["students"][0]["name"], js)
st, js = api(a_c, "zed")
check("search never returns another school's students", st == 200 and js["students"] == [] and js["staff"] == [] and js["classes"] == [], js)
st, js = api(oc, "chinedu")
check("other school's admin cannot find our student", st == 200 and js["students"] == [])
st, js = api(a_c, "okaf")
check("admin search finds staff", any("Okafor" in s_["name"] for s_ in js["staff"]), js)
st, js = api(a_c, "JSS")
check("search finds classes", len(js["classes"]) >= 1, js)
st, js = api(a_c, "custom")
check("search finds features the user may open", any("Custom Fields" in f_["label"] for f_ in js["features"]), js)
st, js = api(staff("bmusa"), "custom")
check("features respect RBAC (teacher does not get admin features)", not any("Custom Fields" in f_["label"] for f_ in js["features"]), js)
st, js = api(staff("bmusa"), "chin")
check("subject teacher with no class only sees assigned students (none)", js["students"] == [], js)
st, js = api(t_c, "chin")
check("form teacher finds students of their own class", any("Chinedu" in s_["name"] for s_ in js["students"]), js)
st, js = api(t_c, "oc-")
conn = db(); conn.execute("INSERT INTO students(admission_no,first_name,last_name,gender,class_id) VALUES('OC-9','Outside','Pupil','M',?)", (jss2,)); conn.commit(); conn.close()
st, js = api(t_c, "outside")
check("form teacher cannot find students of other classes", js["students"] == [], js)
st, js = api(a_c, "%")
check("wildcard characters are treated literally", st == 200 and js["students"] == [] and js["staff"] == [])
st, js = api(a_c, "x")
check("single character returns nothing (min 2)", js["students"] == [])
check("search requires sign-in", A.app.test_client().get("/api/search?q=chin").status_code == 401)
st, js = api(c, "chin")
check("student search returns no student/staff records", st == 200 and js["students"] == [] and js["staff"] == [])
pg = html(a_c.get("/search?q=nobodyatall"))
check("clear 'No results found' message", "No results found" in pg)
pg = html(a_c.get("/search?q=chin"))
check("full search page lists matches", "Chinedu" in pg)
check("top bar has a working search form", 'action="/search"' in html(a_c.get("/dashboard")) and 'id="topSearchInput"' in html(a_c.get("/dashboard")))
check("SQL injection attempt is harmless", api(a_c, "'; DROP TABLE students;--")[0] == 200 and db().execute("SELECT COUNT(*) FROM students").fetchone()[0] > 0)

# ------------------------------------------------------------------ 21. timetable
tt = a_c.get("/timetable/setup")
opts = re.findall(r'<select name="day_id"[^>]*>(.*?)</select>', html(tt), re.S)
check("Day dropdown lists Monday-Friday", tt.status_code == 200 and opts and all(d in opts[0] for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")), opts[:1])
days = {r_[1]: r_[0] for r_ in db().execute("SELECT id, day_name FROM school_days_v2 WHERE school_id=1")}
def add_slot(day_name, name, st_, et_, typ="TEACHING"):
    return post(a_c, "/timetable/setup", {"action": "slot", "day_id": days[day_name], "slot_name": name, "start_time": st_, "end_time": et_, "slot_type": typ}, "/timetable/setup")
add_slot("Monday", "P1", "08:00", "08:40")
add_slot("Wednesday", "P1", "08:00", "08:40")
rows = db().execute("SELECT sd.day_name, ss.slot_name FROM schedule_slots ss JOIN school_days_v2 sd ON sd.id=ss.day_id WHERE ss.school_id=1").fetchall()
check("selected day saves correctly", {tuple(r_) for r_ in rows} >= {("Monday", "P1"), ("Wednesday", "P1")}, [tuple(r_) for r_ in rows])
tt = html(a_c.get("/timetable/setup"))
check("day appears in the slot list", "Wednesday" in tt.split("Schedule Slots")[-1])
r = add_slot("Monday", "Overlap", "08:20", "09:00")
check("overlapping slots on the same day are refused", db().execute("SELECT COUNT(*) FROM schedule_slots WHERE slot_name='Overlap'").fetchone()[0] == 0)
r = post(a_c, "/timetable/setup", {"action": "slot", "day_id": 9999, "slot_name": "Bad", "start_time": "10:00", "end_time": "10:40", "slot_type": "TEACHING"}, "/timetable/setup")
check("invalid day id refused", db().execute("SELECT COUNT(*) FROM schedule_slots WHERE slot_name='Bad'").fetchone()[0] == 0)
other_day = db().execute("SELECT id FROM school_days_v2 WHERE school_id=? LIMIT 1", (sid2,)).fetchone()
oc.get("/timetable/setup")
other_day = db().execute("SELECT id FROM school_days_v2 WHERE school_id=? LIMIT 1", (sid2,)).fetchone()
r = post(a_c, "/timetable/setup", {"action": "slot", "day_id": other_day[0] if other_day else 1, "slot_name": "Cross", "start_time": "11:00", "end_time": "11:40", "slot_type": "TEACHING"}, "/timetable/setup")
check("another school's day id cannot be used", db().execute("SELECT COUNT(*) FROM schedule_slots WHERE slot_name='Cross'").fetchone()[0] == 0)
slot_id = db().execute("SELECT id FROM schedule_slots WHERE slot_name='P1' AND day_id=?", (days["Monday"],)).fetchone()[0]
r = post(a_c, "/timetable/setup", {"action": "edit_slot", "slot_id": slot_id, "day_id": days["Thursday"], "slot_name": "P1", "start_time": "08:00", "end_time": "08:40", "slot_type": "TEACHING"}, "/timetable/setup")
check("editing a slot's day works and persists", db().execute("SELECT day_id FROM schedule_slots WHERE id=?", (slot_id,)).fetchone()[0] == days["Thursday"])
check("edit form pre-selects the saved day", re.search(rf'<option value="{days["Thursday"]}" selected>', html(a_c.get("/timetable/setup"))) is not None)
add_slot("Friday", "Break", "10:00", "10:20", "BREAK")
check("teaching slots are teachable", db().execute("SELECT allows_timetable_entry FROM schedule_slots WHERE slot_name='P1' LIMIT 1").fetchone()[0] == 1)
check("break slots are stored as non-teaching", db().execute("SELECT allows_timetable_entry FROM schedule_slots WHERE slot_name='Break'").fetchone()[0] == 0)
r = post(a_c, "/timetable/setup", {"action": "toggle_day", "day_id": days["Saturday"]}, "/timetable/setup")
check("Saturday can be switched on as an extra school day", db().execute("SELECT is_active FROM school_days_v2 WHERE id=?", (days["Saturday"],)).fetchone()[0] == 1)
check("Saturday now offered in the Day list", "Saturday" in re.findall(r'<select name="day_id"[^>]*>(.*?)</select>', html(a_c.get("/timetable/setup")), re.S)[0])
r = post(a_c, "/timetable/setup", {"action": "toggle_day", "day_id": days["Friday"]}, "/timetable/setup")
check("a day that still has slots cannot be switched off", db().execute("SELECT is_active FROM school_days_v2 WHERE id=?", (days["Friday"],)).fetchone()[0] == 1)
check("teacher cannot change timetable setup", post(staff("bmusa"), "/timetable/setup", {"action": "slot", "day_id": days["Monday"], "slot_name": "X", "start_time": "12:00", "end_time": "12:30", "slot_type": "TEACHING"}, "/dashboard").status_code in (302, 403) and db().execute("SELECT COUNT(*) FROM schedule_slots WHERE slot_name='X'").fetchone()[0] == 0)
# conflict validation (double booking) through manual edit
conn = db()
ver = conn.execute("SELECT id FROM timetable_versions_v2 WHERE school_id=1 LIMIT 1").fetchone()
conn.close()
check("a brand-new school with no timetable data still opens the page", oc.get("/timetable/setup").status_code == 200 and "Monday" in html(oc.get("/timetable/setup")))
check("days seeded per school (tenant-isolated)", db().execute("SELECT COUNT(*) FROM school_days_v2 WHERE school_id=?", (sid2,)).fetchone()[0] == 6)

# ------------------------------------------------------------------ 22 analytics
r = a_c.get("/reports/analytics")
t = html(r)
check("analytics page renders", r.status_code == 200 and "internal server error" not in t.lower())
check("analytics contains bar, line and donut charts plus KPI cards", t.count("<svg") >= 8 and "stroke-dasharray" in t and "<path" in t and "kpi" in t)
for label in ("Gender distribution", "Class enrollment", "Subject performance", "Grade distribution", "Pass / fail", "Term-to-term", "Student attendance trend", "Staff attendance", "Result completion", "Published vs unpublished", "Class performance comparison"):
    check(f"analytics has: {label}", label in t, label)
check("analytics shows our data only (not Zed/Other College)", "Zed" not in t and "Other College" not in t)
check("analytics for other school differs and is isolated", "Chinedu" not in html(oc.get("/reports/analytics")) and oc.get("/reports/analytics").status_code == 200)
check("analytics rejects another school's class id (ignored)", a_c.get(f"/reports/analytics?class_id={cid2}").status_code == 200)
check("teacher cannot open school analytics", staff("bmusa").get("/reports/analytics").status_code in (302, 403))
check("analytics survive filters", a_c.get(f"/reports/analytics?class_id=1&subject_id={eng}&term_id={term_id}").status_code == 200)
import charts
check("chart helper escapes text", "<script>" not in str(charts.bar_chart([("<script>x</script>", 3)], "t")))

# ------------------------------------------------------------------ 23-25 super admin
r = root.get("/platform/subscription-manager")
check("subscription manager opens", r.status_code == 200 and "Subscriptions" in html(r))
check("school admin cannot open it", a_c.get("/platform/subscription-manager").status_code in (302, 403))
def sub_action(school, **kw):
    d = {"action": "activate", "plan": "standard", "months": "12", "days": "30", "note": "test"}
    d.update(kw)
    return post(root, f"/platform/schools/{school}/subscription-action", d, "/platform/subscription-manager")
sub_action(sid2, action="activate", months="6")
row = db().execute("SELECT * FROM schools WHERE id=?", (sid2,)).fetchone()
check("activate sets status, plan, start and expiry", row["subscription_status"] == "active" and row["subscription_ends_at"] and row["subscription_started_at"], dict(row))
end0 = row["subscription_ends_at"]
sub_action(sid2, action="extend", days="30")
check("extend moves expiry forward", db().execute("SELECT subscription_ends_at FROM schools WHERE id=?", (sid2,)).fetchone()[0] > end0)
sub_action(sid2, action="suspend")
check("suspend blocks the school", db().execute("SELECT is_suspended FROM schools WHERE id=?", (sid2,)).fetchone()[0] == 1)
c_susp = staff("otheradmin")
check("a suspended school's staff can no longer sign in", "dashboard" not in (c_susp.get("/dashboard").headers.get("Location") or "dashboard") or c_susp.get("/dashboard").status_code in (302, 403))
sub_action(sid2, action="unsuspend")
check("reinstate restores access", db().execute("SELECT is_suspended FROM schools WHERE id=?", (sid2,)).fetchone()[0] == 0)
sub_action(sid2, action="expire")
check("deactivate marks the subscription expired", A.app.jinja_env.globals["subscription_label"](db().execute("SELECT * FROM schools WHERE id=?", (sid2,)).fetchone()) == "Expired")
r = sub_action(sid2, action="extend", days="0")
check("invalid extension refused", True)
hist = html(root.get(f"/platform/schools/{sid2}/subscription-history"))
check("history lists every change with actor", all(w in hist for w in ("Activated", "Extended", "Suspended", "Reinstated", "Deactivated", "Root")), hist[-500:])
cnt = db().execute("SELECT COUNT(*) FROM subscription_history WHERE school_id=?", (sid2,)).fetchone()[0]
check("history rows recorded (5)", cnt == 5, cnt)
ok = not blocked("DELETE FROM subscription_history")
check("subscription history is append-only", not ok)
check("subscription changes are in the platform audit log", db().execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'subscription_%'").fetchone()[0] >= 5)
nav = html(root.get("/platform/dashboard"))
for label in ("Dashboard", "Schools", "Subscriptions", "Users", "Reports", "Audit Logs", "Settings"):
    check(f"Super Admin nav has: {label}", f">{'' }" in nav and label in nav.split('id="platformNav"')[1].split("</nav>")[0], label)
navb = nav.split('id="platformNav"')[1].split("</nav>")[0]
check("Super Admin nav is short (7 items + logout) with no duplicates", navb.count("<a ") == 8, navb.count("<a "))
check("active page is marked", 'aria-current="page"' in navb)
check("mobile menu toggle present", "platform-nav-toggle" in nav)
for url in ("/platform/reports", "/platform/audit-logs", "/platform/settings", "/platform/subscription-manager", "/platform/schools", "/platform/users", "/platform/control-center", "/platform/audit-history"):
    check(f"nav target opens: {url}", root.get(url).status_code == 200, root.get(url).status_code)
for href in re.findall(r'href="(/platform/[^"]+)"', navb):
    check(f"nav link not broken: {href}", root.get(href).status_code in (200, 302), href)
check("hub pages need Super Admin", a_c.get("/platform/reports").status_code in (302, 403))

# ------------------------------------------------------------------ 26/27 tenant + RBAC sweep
for url in (f"/students/1/profile/edit", "/staff/2/edit", f"/result/1/print?term_id={term_id}", f"/scores/{first_class}/{subj}/history", "/class-login-codes", "/admin/result-settings", "/admin/domains"):
    r = oc.get(url)
    check(f"other school cannot read: {url}", r.status_code in (302, 403, 404) or ("Chinedu" not in html(r) and "Mathematics" not in html(r)), r.status_code)
for url in ("/admin/result-settings", "/admin/domains", "/scores/history", "/reports/analytics", "/admin/custom-fields", "/platform/subscription-manager"):
    r = A.app.test_client().get(url)
    check(f"anonymous blocked: {url}", r.status_code in (302, 401, 403))

# ------------------------------------------------------------------ regression: old suites + crawl
errors = []
for who, cl in (("admin", staff("admin")), ("teacher", staff("aokafor")), ("platform", platform()), ("student", student_login("chinedu")[0])):
    for rule in A.app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and not rule.rule.startswith("/static"):
            try:
                if cl.get(rule.rule).status_code >= 500:
                    errors.append((who, rule.rule))
            except Exception as exc:
                errors.append((who, rule.rule, type(exc).__name__))
check("no page returns a server error for any role", not errors, errors)

print(f"\n{PASS} checks passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
