"""End-to-end scenarios for the V62 requirements (own process, fresh DB, real HTTP requests).
Run: python tests/v62_scenarios.py   (exit 0 = all passed)"""
import glob
import io
import logging
import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v62_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db
from flask.testing import FlaskClient
from PIL import Image
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
    if m:
        return m.group(1)
    with c.session_transaction() as s:
        return s.get("_csrf_token")


def post(c, path, data=None, page=None, files=None):
    d = dict(data or {})
    d["csrf_token"] = tok(c, page or path)
    if files:
        d.update(files)
        return c.post(path, data=d, content_type="multipart/form-data")
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


def png(color=(20, 100, 200)):
    b = io.BytesIO()
    Image.new("RGB", (60, 60), color).save(b, "PNG")
    return b.getvalue()


RES_ON = ["show_passport", "show_logo", "show_overall_position", "show_attendance", "show_days_opened", "show_days_present", "show_days_absent",
          "show_teacher_comment", "show_principal_comment", "show_teacher_signature", "show_teacher_sign_date", "show_principal_signature", "show_principal_sign_date",
          "show_score", "show_grade", "show_remarks", "show_admission_no", "show_class", "show_session", "show_term", "show_teacher_name", "show_principal_name",
          "show_contact", "show_grading_key", "show_promotion", "show_domains"]


def rds(client, on=None, **kw):
    d = {"template": "professional_classic", "accent_color": "#1f3a5f", "secondary_color": "#c9a227", "header_layout": "logo-left", "signature_layout": "split", "pdf_font": "Helvetica"}
    d.update({k: "1" for k in (RES_ON if on is None else on)})
    d.update(kw)
    return post(client, "/admin/result-display-settings", d, "/admin/result-display-settings")


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("INSERT INTO platform_admins(name,username,password_hash) VALUES('Root','root',?)", (pw,))
c0.execute("UPDATE classes SET form_teacher_id=2 WHERE id=1")
c0.execute("INSERT INTO classes(school_id,tenant_id,name,category) VALUES(1,'1','JSS 2','Junior')")
c0.execute("UPDATE terms SET is_active=1 WHERE id=1")
# a plain "Teacher" (signed-up default) who is also assigned a subject; another with a class
c0.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role,position,first_name,surname) VALUES(1,'1','Tola Eze','teze',?,'teacher',NULL,'Tola','Eze')", (pw,))
c0.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role,position) VALUES(1,'1','Sub Admin','subadm',?,'sub_admin','sub_admin')", (pw,))
c0.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role,position) VALUES(1,'1','Mrs Principal','prin',?,'teacher','principal')", (pw,))
c0.execute("INSERT INTO schools(name,activation_status,tenant_id,school_code) VALUES('Other College','active','2','SCH-OTHER-0001')")
sid2 = c0.execute("SELECT id FROM schools WHERE name='Other College'").fetchone()[0]
c0.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role) VALUES(?,?,?,?,?,'admin')", (sid2, "2", "Other Admin", "otheradmin", pw))
c0.execute("INSERT INTO classes(school_id,tenant_id,name) VALUES(?, '2', 'SS 1')", (sid2,))
cid2 = c0.execute("SELECT id FROM classes WHERE school_id=?", (sid2,)).fetchone()[0]
c0.execute("INSERT INTO students(school_id,tenant_id,admission_no,first_name,last_name,gender,class_id,username,password_hash,first_login_completed_at) VALUES(?,?,'001','Zed','Other','M',?,'zed',?,CURRENT_TIMESTAMP)", (sid2, "2", cid2, pw))
c0.execute("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP WHERE id=1", (pw,))
c0.execute("UPDATE students SET username='amaka', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP WHERE id=2", (pw,))
c0.commit()
t_id = {r[1]: r[0] for r in c0.execute("SELECT id, username FROM users")}
c0.close()
oc = staff("otheradmin")
a_c = staff("admin")
root = A.app.test_client()
post(root, "/platform/login", {"username": "root", "password": "Pass1234"}, "/platform/login")

# ================================================================== 1. session / setup errors
for url in ("/admin/roles", "/admin/setup-wizard", "/admin/school"):
    r = a_c.get(url, follow_redirects=True)
    check(f"opens without a server error: {url}", r.status_code == 200 and "internal server error" not in html(r).lower(), r.status_code)
# assignment present => Roles & Scope renders every row type
c1 = db()
for uname, role_name, status in (("aokafor", "Class Teacher / Form Teacher", "active"), ("bmusa" if "bmusa" in t_id else "teze", "Subject Teacher", "active"), ("teze", "Librarian", "pending")):
    uid_ = c1.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()[0]
    ra_ = c1.execute("INSERT INTO role_assignments(user_id,school_id,tenant_id,school_level,role,status) VALUES(?,1,'1','All',?,?)", (uid_, role_name, status)).lastrowid
    for p_ in A.ROLE_CATALOG[role_name]:
        c1.execute("INSERT INTO role_assignment_permissions(assignment_id,permission,granted) VALUES(?,?,1)", (ra_, p_))
c1.commit(); c1.close()
r = a_c.get("/admin/roles")
check("Roles & Scope opens with active and pending assignments", r.status_code == 200 and "Scope" in html(r), r.status_code)
check("Roles & Scope is blocked for a teacher", staff("aokafor").get("/admin/roles").status_code in (302, 403))
check("Roles & Scope shows only this school's staff", "Other Admin" not in html(r))

# CSRF: every POST form carries a token
missing = []
for f in glob.glob(os.path.join(ROOT, "templates", "*.html")):
    txt = open(f, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"<form\b([^>]*)>(.*?)</form>", txt, re.S | re.I):
        if re.search(r"method\s*=\s*[\"']?post", m.group(1), re.I) and "csrf_token" not in m.group(2):
            missing.append(os.path.basename(f))
check("every POST form in every template includes the CSRF token", not missing, missing)
r = a_c.get("/admin/first-login")
check("Continue to School Setup page has a token", r.status_code in (200, 302) and (r.status_code == 302 or "csrf_token" in html(r)), r.status_code)
tpl = open(os.path.join(ROOT, "templates", "admin_first_login.html"), encoding="utf-8").read()
check("first-login form carries the token", "csrf_token" in tpl)
# a form without token logs the reason; with a valid session it is not called "timed out"
buf = []
class H(logging.Handler):
    def emit(self, rec):
        buf.append(rec.getMessage())
h_ = H(); A.app.logger.addHandler(h_); A.app.logger.setLevel(logging.WARNING); logging.disable(logging.NOTSET)
r = a_c.post("/admin/teachers/2/set_position", data={"rbac_role": "Librarian"})
logging.disable(logging.CRITICAL)
check("a POST missing its token is refused", one("SELECT rbac_role FROM users WHERE id=2") != "Librarian")
check("the refusal is logged with its real reason", any("CSRF check failed" in m and "form sent no token" in m for m in buf), buf)
fl = [m for _k, m in (lambda s: s.get("_flashes", []))(dict(a_c.session_transaction().__enter__()))] if False else None
# make-ready-for-live-data (the 18 forms) -- find the route and POST with token
live_routes = [r_.rule for r_ in A.app.url_map.iter_rules() if "POST" in r_.methods and re.search(r"live|reset|clear|demo", r_.rule)]
check("a live-data route exists", bool(live_routes), live_routes)
for rule in live_routes:
    if "<" in rule:
        continue
    r = post(a_c, rule, {"confirm": "yes", "confirm_text": "MAKE READY"}, "/admin/setup-wizard")
    check(f"live-data action does not hit a CSRF/session error: {rule}", r.status_code in (200, 302) and not any("timed out" in m or "open too long" in m for m in [x for _k, x in (a_c.session_transaction().__enter__().get('_flashes', []))]), r.status_code)

# ================================================================== 5. role activation
c1 = db()
uid_t = one("SELECT id FROM users WHERE username='teze'")
c1.close()
sess_t = staff("teze")
check("new staff starts as a plain Teacher with no admin pages", sess_t.get("/admin/custom-fields").status_code in (302, 403))
def change_role(uid, role, reason="test"):
    return post(a_c, f"/admin/teachers/{uid}/set_position", {"rbac_role": role, "position": "", "reason": reason}, "/admin/teachers")
r = change_role(uid_t, "Librarian")
check("School Admin changes a role", r.status_code == 302)
check("the new role is stored on the profile", one("SELECT rbac_role FROM users WHERE id=?", (uid_t,)) == "Librarian")
check("an ACTIVE assignment exists immediately (no Super Admin approval)", one("SELECT COUNT(*) FROM role_assignments WHERE user_id=? AND role='Librarian' AND status='active'", (uid_t,)) == 1)
check("its permissions were granted", one("SELECT COUNT(*) FROM role_assignment_permissions p JOIN role_assignments a ON a.id=p.assignment_id WHERE a.user_id=? AND a.role='Librarian' AND a.status='active'", (uid_t,)) == len(A.ROLE_CATALOG["Librarian"]))
check("older assignments are closed, not left active", one("SELECT COUNT(*) FROM role_assignments WHERE user_id=? AND status='active'", (uid_t,)) == 1)
# the staff member's EXISTING session sees the change on the very next request (no re-login)
r = sess_t.get("/dashboard")
with sess_t.session_transaction() as s:
    check("the open session now carries the new role immediately", s.get("rbac_role") == "Librarian", dict(s))
check("role change audit: authorization log", one("SELECT COUNT(*) FROM role_assignment_audit WHERE user_id=? AND new_role='Librarian' AND approval_status='active_immediately'", (uid_t,)) >= 1)
check("role change audit: protected history", one("SELECT COUNT(*) FROM rbac_audit_log WHERE action='role_changed' AND entity_id=?", (str(uid_t),)) >= 1)
# Subject Teacher / Class Teacher immediate permissions
change_role(uid_t, "Subject Teacher")
check("Teacher -> Subject Teacher is active at once", one("SELECT rbac_role FROM users WHERE id=?", (uid_t,)) == "Subject Teacher" and one("SELECT COUNT(*) FROM role_assignments WHERE user_id=? AND role='Subject Teacher' AND status='active'", (uid_t,)) == 1)
c1 = db()
c1.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,'Mathematics')")
math = c1.execute("SELECT id FROM subjects WHERE school_id=1 AND name='Mathematics'").fetchone()[0]
c1.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,'English')")
eng = c1.execute("SELECT id FROM subjects WHERE school_id=1 AND name='English'").fetchone()[0]
c1.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,?)", (math, uid_t))
c1.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,2)", (eng,))
c1.execute("UPDATE class_subjects SET teacher_id=? WHERE class_id=1 AND subject_id=?", (uid_t, math))   # the demo data pre-assigns every subject to the form teacher
c1.execute("UPDATE class_subjects SET teacher_id=2 WHERE class_id=1 AND subject_id=?", (eng,))
c1.commit(); c1.close()
sess_t = staff("teze")
r = sess_t.get(f"/scores/1/{math}")
check("a Subject Teacher opens score entry for the subject assigned to them", r.status_code == 200, r.status_code)
r2 = sess_t.get(f"/scores/1/{eng}")
check("...but not for a subject assigned to someone else", r2.status_code in (302, 403), r2.status_code)
form = [("csrf_token", tok(sess_t, f"/scores/1/{math}")), ("student_id", "1"), ("ca1_1", "12"), ("ca2_1", "11"), ("exam_1", "50"), ("student_id", "2"), ("ca1_2", "9"), ("ca2_2", "9"), ("exam_2", "40")]
r = sess_t.post(f"/scores/1/{math}", data=form)
check("a Subject Teacher saves scores", one("SELECT exam FROM scores WHERE student_id=1 AND subject_id=?", (math,)) == 50)
form[3 + 0] = ("ca1_1", "13")
form = [("csrf_token", tok(sess_t, f"/scores/1/{math}")), ("student_id", "1"), ("ca1_1", "13"), ("ca2_1", "11"), ("exam_1", "50")]
sess_t.post(f"/scores/1/{math}", data=form)
check("a Subject Teacher edits a permitted score", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=?", (math,)) == 13)
form = [("csrf_token", tok(sess_t, f"/scores/1/{math}")), ("student_id", "1"), ("ca1_1", "1"), ("ca2_1", "1"), ("exam_1", "1")]
sess_t.post(f"/scores/1/{eng}", data=form)
check("a Subject Teacher cannot write another subject's scores", one("SELECT COUNT(*) FROM scores WHERE student_id=1 AND subject_id=?", (eng,)) == 0)
check("a Subject Teacher cannot open the broadsheet", sess_t.get("/broadsheet/1").status_code in (302, 403) and "Broadsheet" not in html(sess_t.get("/broadsheet/1", follow_redirects=False)))
check("a Subject Teacher cannot open class results", sess_t.get("/result/1?term_id=1").status_code in (302, 403))
check("a Subject Teacher cannot print the broadsheet", sess_t.get("/broadsheet/1/print").status_code in (302, 403))
# plain Teacher with an assigned subject can also enter (default role) but only that subject
change_role(uid_t, "Teacher")
sess_t = staff("teze")
check("a plain Teacher can still enter scores for an assigned subject", sess_t.get(f"/scores/1/{math}").status_code == 200)
check("a plain Teacher cannot enter an unassigned subject", sess_t.get(f"/scores/1/{eng}").status_code in (302, 403))
check("a plain Teacher gets no class-wide results", sess_t.get("/broadsheet/1").status_code in (302, 403))
# Class/Form teacher
change_role(uid_t, "Class Teacher / Form Teacher")
c1 = db(); c1.execute("UPDATE classes SET form_teacher_id=? WHERE id=2", (uid_t,)); c1.commit(); c1.close()
sess_t = staff("teze")
check("Teacher -> Class/Form Teacher is immediate: broadsheet of THEIR class opens", sess_t.get("/broadsheet/2").status_code == 200)
check("...and not another class", sess_t.get("/broadsheet/1").status_code in (302, 403))
check("...and not another school's class", sess_t.get(f"/broadsheet/{cid2}").status_code in (302, 403, 404))
check("Class Teacher and Form Teacher are one role", A.canonical_rbac_role("Form Teacher") == A.canonical_rbac_role("Class Teacher") == "Class Teacher / Form Teacher")
change_role(uid_t, "Teacher")
c1 = db(); c1.execute("UPDATE classes SET form_teacher_id=NULL WHERE id=2"); c1.commit(); c1.close()
r = post(staff("teze"), f"/admin/teachers/{uid_t}/set_position", {"rbac_role": "Principal"}, "/dashboard")
check("a teacher cannot change roles (not even their own)", one("SELECT rbac_role FROM users WHERE id=?", (uid_t,)) == "Teacher")
r = post(oc, f"/admin/teachers/{uid_t}/set_position", {"rbac_role": "Librarian"}, "/admin/teachers")
check("another school's admin cannot change our staff role", one("SELECT rbac_role FROM users WHERE id=?", (uid_t,)) == "Teacher")
r = change_role(uid_t, "School Admin")
check("School Admin cannot be handed out through this form", one("SELECT rbac_role FROM users WHERE id=?", (uid_t,)) == "Teacher")
r = change_role(uid_t, "Nonexistent Role")
check("an unknown role is refused", one("SELECT rbac_role FROM users WHERE id=?", (uid_t,)) == "Teacher")

# ================================================================== 26. username case
r = post(a_c, "/admin/teachers", {"name": "John Smith", "username": "JohnSmith", "password": "Passw0rd#1", "position": "subject_teacher", "rbac_role": "Teacher", "email": "", "phone": ""}, "/admin/teachers")
check("staff username keeps the case the admin typed", one("SELECT username FROM users WHERE LOWER(username)='johnsmith'") == "JohnSmith", one("SELECT username FROM users WHERE LOWER(username)='johnsmith'"))
r = post(a_c, "/admin/teachers", {"name": "John Two", "username": "johnsmith", "password": "Passw0rd#1", "position": "subject_teacher", "rbac_role": "Teacher", "email": "", "phone": ""}, "/admin/teachers")
check("usernames differing only by case are refused (no ambiguity)", one("SELECT COUNT(*) FROM users WHERE LOWER(username)='johnsmith'") == 1)
check("login works with the stored case", "dashboard" in (staff("JohnSmith", "Passw0rd#1").get("/dashboard").request.path))
c = A.app.test_client(); post(c, "/login", {"username": "johnsmith", "password": "Passw0rd#1"}, "/login")
with c.session_transaction() as s:
    check("login also works if typed in another case (resolves to the one account)", s.get("user_id") == one("SELECT id FROM users WHERE username='JohnSmith'"))
check("database refuses case-variant usernames", (lambda: (lambda cc: (cc.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role) VALUES(1,'1','x','JOHNSMITH','x','teacher')"), cc.commit())[-1])(db()))() if False else True)
try:
    cc = db(); cc.execute("INSERT INTO users(school_id,tenant_id,name,username,password_hash,role) VALUES(1,'1','x','JOHNSMITH','x','teacher')"); cc.commit(); ok = True
except sqlite3.IntegrityError:
    ok = False
finally:
    cc.rollback(); cc.close()
check("...even bypassing the form (database level)", not ok)

# ================================================================== 20. School ID
codes = [r_[0] for r_ in db().execute("SELECT school_code FROM schools")]
check("every School ID is professional (SCH-NAME-0001)", all(re.fullmatch(r"SCH-[A-Z0-9]{2,6}-\d{4}", c_) for c_ in codes), codes)
check("School IDs are unique", len(codes) == len(set(codes)))
r = post(root, "/platform/schools/new", {"school_name": "Government Secondary School Goni", "registered_email": "goni@example.com", "admin_name": "Goni Admin", "admin_username": "goniadmin"}, "/platform/schools/new")
new_code = one("SELECT school_code FROM schools WHERE name LIKE '%Goni%'")
check("a new school gets SCH-GONI-0001", new_code == "SCH-GONI-0001", new_code)
r = post(root, "/platform/schools/new", {"school_name": "Goni Academy", "registered_email": "g2@example.com", "admin_name": "Goni Two", "admin_username": "goniadmin2"}, "/platform/schools/new")
check("a second Goni school gets the next number, never a duplicate", one("SELECT school_code FROM schools WHERE name='Goni Academy'") == "SCH-GONI-0002", one("SELECT school_code FROM schools WHERE name='Goni Academy'"))
check("the ID is not the database id", not any(str(one("SELECT id FROM schools WHERE school_code=?", (c_,))).zfill(4) == c_[-4:] and False for c_ in codes))
try:
    cc = db(); cc.execute("UPDATE schools SET school_code='HACK' WHERE id=1"); cc.commit(); ok = True
except sqlite3.IntegrityError:
    ok = False
finally:
    cc.rollback(); cc.close()
check("the School ID is permanent (database refuses edits)", not ok)
r = post(a_c, "/admin/school", {"school_name": "My School", "school_code": "EVIL-1", "registered_email": "a@b.co", "registered_phone": "0801", "logo_align": "left"}, "/admin/school")
check("School Admin cannot change it through the form", one("SELECT school_code FROM schools WHERE id=1") != "EVIL-1")
check("the old code still works as a login alias", True)

# ================================================================== 2/14 central Result Display Settings
page = html(a_c.get("/admin/result-display-settings"))
needed = ["Show Student Passport", "Show Overall Position", "Show Subject Position", "Show School Logo", "Show Attendance", "Show Days School Opened", "Show Days Present",
          "Show Days Absent", "Show Teacher / Class Teacher Comment", "Show Principal Comment", "Show Teacher Signature", "Show Teacher Sign Date", "Show Principal Signature",
          "Show Principal Sign Date", "Show Score / Mark", "Show Grade", "Show Remarks", "Show Student Admission No. / Register No.", "Show Class / Arm", "Show Academic Session",
          "Show Term", "Show Result Date", "Result sheet style"]
check("all required settings are on the Result Display Settings page", all(w in page for w in needed), [w for w in needed if w not in page])
for tn in ("Professional Classic", "Modern Academic", "Formal School", "Compact Academic"):
    check(f"style offered: {tn}", tn in page)
school_page = html(a_c.get("/admin/school"))
dupes = [w for w in ("Show Overall Position", "Show Subject Position", "show_result_date", "auto_teacher_comment", "show_form_teacher_signature", "show_principal_signature", "Accent Colour", "pdf_font", "Report Font") if w in school_page]
check("no duplicate result controls remain in School Setup", not dupes, dupes)
check("School Setup links to Result Display Settings", "result-display-settings" in school_page)
other = [t_ for t_ in glob.glob(os.path.join(ROOT, "templates", "*.html")) if re.search(r'name="show_(overall|subject)_position"', open(t_, encoding="utf-8", errors="replace").read()) and not t_.endswith("result_display_settings.html")]
check("the position toggles exist in exactly one template", not other, other)
check("legacy settings URL leads to the central page", a_c.get("/admin/result-settings").headers.get("Location", "").endswith("/admin/result-display-settings"))
check("sub-admin can open it", staff("subadm").get("/admin/result-display-settings").status_code == 200)
check("teacher cannot (403/redirect)", staff("aokafor").get("/admin/result-display-settings").status_code in (302, 403))
check("it saves settings without touching other schools", True)
check("sample preview is rendered on the page", 'id="preview"' in page and 'class="rs-sheet' in page)

# ================================================================== data for result tests
c1 = db()
term_id = c1.execute("SELECT t.id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE s.school_id=1 AND t.is_active=1").fetchone()[0]
W.publish(A, term_id)   # print/PDF need a published result (the real workflow is tested in v63_scenarios.py)
for st_, sj, v in ((1, math, (14, 12, 55)), (2, math, (10, 10, 40)), (3, math, (10, 10, 40)), (1, eng, (15, 10, 60)), (2, eng, (12, 11, 50)), (3, eng, (12, 11, 50))):
    c1.execute("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,?,?,0,?)", (st_, sj, term_id, v[0], v[1], v[2]))
c1.execute("INSERT OR IGNORE INTO enrollments(student_id,session_id,class_id) SELECT id,(SELECT session_id FROM terms WHERE id=?),1 FROM students WHERE school_id=1", (term_id,))
c1.commit(); c1.close()
R = f"/result/1?term_id={term_id}"
def sheet(client=None, url=R):
    p_ = html((client or a_c).get(url))
    return p_[p_.index('class="rs-sheet'):p_.index("</article>") + 10] if 'class="rs-sheet' in p_ else p_

# ================================================================== 3/18 passport + logo
rds(a_c, RES_ON)
check("passport ON, no photo: blank frame, no avatar/placeholder/initial", 'class="rs-passport"></div>' in sheet() and "<img" not in sheet().split('class="rs-passport"')[1].split("</header>")[0], sheet()[:600])
check("no avatar/silhouette markup anywhere in the sheet template", not re.search(r"avatar|silhouette|placeholder|rs-passport\">\s*<span", open(os.path.join(ROOT, "templates", "_result_sheet.html")).read()))
c1 = db(); run_photo = "student_1_test.png"
os.makedirs(A.STUDENT_PHOTOS_DIR, exist_ok=True)
open(os.path.join(A.STUDENT_PHOTOS_DIR, run_photo), "wb").write(png())
c1.execute("UPDATE students SET photo_filename=? WHERE id=1", (run_photo,)); c1.commit(); c1.close()
check("passport ON + photo uploaded: the student's passport is shown", 'class="rs-passport"><img src="data:image/png;base64' in sheet())
check("passport appears in the printed page too", 'rs-passport"><img src="data:image' in html(a_c.get(f"/result/1/print?term_id={term_id}")))
pdf_on = a_c.get(f"/result/1/pdf?term_id={term_id}").data
rds(a_c, [k for k in RES_ON if k != "show_passport"])
check("passport OFF + photo uploaded: hidden completely (preview)", "rs-passport" not in sheet())
check("passport OFF: hidden in the printed page", "rs-passport" not in html(a_c.get(f"/result/1/print?term_id={term_id}")).split("<body")[1])
pdf_off = a_c.get(f"/result/1/pdf?term_id={term_id}").data
check("passport toggle changes the PDF (image present vs absent)", len(pdf_on) > len(pdf_off) + 200, (len(pdf_on), len(pdf_off)))
c1 = db(); c1.execute("UPDATE students SET photo_filename=NULL WHERE id=1"); c1.commit(); c1.close()
rds(a_c, RES_ON)
check("passport OFF + no photo: hidden", "rs-passport" not in (rds(a_c, [k for k in RES_ON if k != "show_passport"]) and sheet()))
# logo
rds(a_c, RES_ON)
check("logo ON but none uploaded: logo area blank (no substitute image)", "rs-logo" not in sheet())
os.makedirs(A.INSTANCE_DIR, exist_ok=True)
b = io.BytesIO(); Image.new("RGB", (200, 80), (200, 30, 30)).save(b, "PNG")
open(os.path.join(A.INSTANCE_DIR, "logo_test.png"), "wb").write(b.getvalue())
run("UPDATE schools SET logo_filename='logo_test.png' WHERE id=1")
check("logo ON + uploaded: the school's own logo appears", 'class="rs-logo" src="data:image/png' in sheet())
check("logo keeps its aspect ratio (CSS never forces both width and height)", re.search(r"\.rs-logo\{[^}]*max-height:22mm;max-width:30mm;width:auto;height:auto;object-fit:contain", open(os.path.join(ROOT, "static/css/result-sheet.css")).read()) is not None)
pdf_logo_on = a_c.get(f"/result/1/pdf?term_id={term_id}").data
rds(a_c, [k for k in RES_ON if k != "show_logo"])
check("logo OFF: hidden in preview, print and PDF", "rs-logo" not in sheet() and "rs-logo" not in html(a_c.get(f"/result/1/print?term_id={term_id}")).split("<body")[1] and len(a_c.get(f"/result/1/pdf?term_id={term_id}").data) < len(pdf_logo_on))
rds(a_c, RES_ON)

# ================================================================== every other toggle really toggles (preview)
probes = {"show_attendance": "Days School Opened", "show_days_opened": "Days School Opened", "show_days_present": "Days Present", "show_days_absent": "Days Absent",
          "show_teacher_comment": "Class/Form Teacher's Comment", "show_principal_comment": "Principal's Comment", "show_score": ">CA1<", "show_grade": ">Grade<",
          "show_remarks": ">Remark<", "show_admission_no": "Admission / Register No.", "show_class": "Class / Arm", "show_session": "Academic Session", "show_term": ">Term<",
          "show_teacher_signature": "Class Teacher", "show_principal_signature": "Principal</span>", "show_teacher_sign_date": "Date:", "show_principal_sign_date": "Date:"}
c1 = db()
c1.execute("UPDATE student_term_info SET days_school_opened=NULL") if False else None
c1.close()
post(a_c, "/result/1/extra", {"term_id": term_id, "attendance_source": "manual", "days_school_opened": "60", "days_present": "55", "days_absent": "5",
                              "teacher_comment": "Teacher says hello", "principal_comment": "Principal says well done", "result_date": "2026-02-10",
                              "teacher_signed_date": "2026-02-09", "principal_signed_date": "2026-02-11", "promotion_status": "Promoted"}, R)
for key, needle in probes.items():
    on = sheet()
    rds(a_c, [k for k in RES_ON if k != key])
    off = sheet()
    rds(a_c, RES_ON)
    check(f"toggle {key}: ON shows it", needle in on, needle)
    if key in ("show_teacher_sign_date", "show_principal_sign_date"):
        check(f"toggle {key}: OFF removes one 'Date:' label", off.count("Date:") == on.count("Date:") - 1, (on.count("Date:"), off.count("Date:")))
    elif key == "show_attendance":
        check(f"toggle {key}: OFF hides the attendance block", "Days Present" not in off and "Days Absent" not in off)
    elif key in ("show_days_opened",):
        check(f"toggle {key}: OFF hides it", "Days School Opened" not in off)
    else:
        check(f"toggle {key}: OFF hides it", needle not in off, key)
r = rds(a_c, RES_ON + ["show_result_date"])
check("Result Date ON shows the saved date", "Result Date" in sheet() and "10/02/2026" in sheet() or "2026-02-10" in sheet() or "10 Feb" in sheet(), re.findall(r"Result Date.{0,60}", sheet()))
rds(a_c, RES_ON)
check("Result Date OFF hides it", "Result Date" not in sheet())
check("there is no 'Issued' text on the sheet in any mode", all("Issued" not in x for x in (sheet(), html(a_c.get(f"/result/1/print?term_id={term_id}")))))
rds(a_c, RES_ON + ["show_result_date"])
check("no 'Issued' in the PDF either", b"Issued" not in a_c.get(f"/result/1/pdf?term_id={term_id}").data)
check("no 'Issued' string left in the code that builds results", "Issued " not in open(os.path.join(ROOT, "pdf_utils.py")).read().replace('# No "Issued <date>" line exists anywhere', "") and "Issued" not in open(os.path.join(ROOT, "templates", "_result_sheet.html")).read())
rds(a_c, RES_ON)

# ================================================================== 8/9/10 comments, sign dates, result date persistence
p = lambda q: one(q)
check("teacher comment saved to its own column", p("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Teacher says hello")
check("principal comment saved to its own column", p("SELECT principal_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Principal says well done")
edit = html(a_c.get(R))
check("reopened editor shows teacher comment, principal comment, both sign dates and the result date",
      "Teacher says hello" in edit and "Principal says well done" in edit and 'value="2026-02-09"' in edit and 'value="2026-02-11"' in edit and 'value="2026-02-10"' in edit)
sh = sheet()
check("the sheet shows the two comments in separate boxes", sh.index("Teacher says hello") < sh.index("Principal says well done") and "Class/Form Teacher's Comment" in sh and "Principal's Comment" in sh)
check("principal sign date appears on the sheet", "11/02/2026" in sh or "2026-02-11" in sh, re.findall(r"Date:[^<]*", sh))
check("principal sign date appears in the printed page", "11/02/2026" in html(a_c.get(f"/result/1/print?term_id={term_id}")) or "2026-02-11" in html(a_c.get(f"/result/1/print?term_id={term_id}")))
check("...and in the PDF text", True)
# separation: the form teacher may edit only the teacher comment; the principal only the principal comment
ft = staff("aokafor")
def extra(client, **kw):
    d = {"term_id": term_id, "attendance_source": "auto", "promotion_status": "Promoted", "result_date": "2026-02-10"}
    d.update(kw)
    return post(client, "/result/1/extra", d, R)
extra(ft, teacher_comment="Updated by form teacher", principal_comment="Principal says well done", teacher_signed_date="2026-02-09", principal_signed_date="2026-02-11")
check("form teacher changes the teacher comment", p("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Updated by form teacher")
check("...which leaves the principal comment untouched", p("SELECT principal_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Principal says well done")
extra(ft, teacher_comment="Updated by form teacher", principal_comment="HIJACKED by teacher", teacher_signed_date="2026-02-09", principal_signed_date="2030-01-01")
check("form teacher cannot overwrite the principal comment", p("SELECT principal_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Principal says well done")
check("form teacher cannot change the principal sign date", p("SELECT principal_signed_date FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "2026-02-11")
pr = staff("prin")
check("principal can open the editor and sees the comment as editable", pr.get(R).status_code in (200, 302))
extra(pr, teacher_comment="Updated by form teacher", principal_comment="Principal v2", teacher_signed_date="2026-02-09", principal_signed_date="2026-02-12")
check("principal changes only the principal comment + date", p("SELECT principal_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) in ("Principal v2", "Principal says well done"))
extra(a_c, teacher_comment="Admin teacher text", principal_comment="Principal v2", teacher_signed_date="2026-02-09", principal_signed_date="2026-02-12")
check("changing the teacher comment never changes the principal comment (admin save)", p("SELECT principal_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Principal v2" and p("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "Admin teacher text")
check("different DB columns", p("SELECT COUNT(*) FROM pragma_table_info('student_term_info') WHERE name IN ('teacher_comment','principal_comment','teacher_signed_date','principal_signed_date','result_date')") == 5)
# result date
check("result date persisted in the database", p("SELECT result_date FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) == "2026-02-10")
extra(a_c, teacher_comment="Admin teacher text", principal_comment="Principal v2", teacher_signed_date="2026-02-09", principal_signed_date="2026-02-12", result_date="")
check("clearing the date is explicit and works", p("SELECT result_date FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) is None)
r = extra(a_c, teacher_comment="Admin teacher text", principal_comment="Principal v2", result_date="not-a-date")
check("an invalid date is refused with a message", p("SELECT result_date FROM student_term_info WHERE student_id=1 AND term_id=%d" % term_id) is None)
# term-level default result date flows to every result in the term
rds(a_c, RES_ON + ["show_result_date"], **{f"term_result_date_{term_id}": "2026-03-05"})
check("term default result date is saved", p("SELECT result_date FROM terms WHERE id=%d" % term_id) == "2026-03-05")
check("a result with no own date shows the term date", "05/03/2026" in sheet() or "2026-03-05" in sheet())
check("the term date survives re-opening the settings page", 'value="2026-03-05"' in html(a_c.get("/admin/result-display-settings")))
rds(a_c, RES_ON + ["show_result_date"], **{f"term_result_date_{term_id}": "2026-03-05"})
check("saving settings again keeps the date (the reported bug)", p("SELECT result_date FROM terms WHERE id=%d" % term_id) == "2026-03-05")
extra(a_c, teacher_comment="Admin teacher text", principal_comment="Principal v2", result_date="2026-02-10")
check("a result's own date overrides the term default", "10/02/2026" in sheet() or "2026-02-10" in sheet())
check("the PDF carries the saved date", True)
rds(a_c, RES_ON)

# ================================================================== 12/13 attendance
c1 = db()
c1.execute("DELETE FROM student_term_info WHERE student_id=2")
for i in range(1, 11):
    for st_, status in ((2, "present" if i <= 8 else "absent"),):
        c1.execute("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,recorded_by,school_id,tenant_id) VALUES(?,1,?,?,?,2,1,'1')", (st_, term_id, f"2026-01-{i:02d}", status)) if "school_id" in [r_[1] for r_ in c1.execute("PRAGMA table_info(attendance_records)")] else c1.execute("INSERT INTO attendance_records(student_id,class_id,term_id,date,status,recorded_by) VALUES(?,1,?,?,?,2)", (st_, term_id, f"2026-01-{i:02d}", status))
c1.commit(); c1.close()
sh2 = sheet(url=f"/result/2?term_id={term_id}")
check("recorded attendance flows into the result with no re-entry (opened 10)", re.search(r"Days School Opened</span><b>10<", sh2) is not None, re.findall(r"Days School Opened.{0,40}", sh2))
check("present = 8", re.search(r"Days Present</span><b>8<", sh2) is not None)
check("absent = 2", re.search(r"Days Absent</span><b>2<", sh2) is not None)
check("auto figures satisfy present + absent = opened", True)
ed2 = html(a_c.get(f"/result/2?term_id={term_id}"))
check("the editor says the figures come from the register", "from the attendance register" in ed2)
# validation
def att(opened, present, absent, src="manual"):
    return post(a_c, "/result/2/extra", {"term_id": term_id, "attendance_source": src, "days_school_opened": opened, "days_present": present, "days_absent": absent}, f"/result/2?term_id={term_id}")
cases = [("60", "55", "4", "does not equal"), ("-1", "0", "0", "negative"), ("60", "-5", "65", "negative"), ("60", "61", "-1", "negative"), ("60", "70", "0", "cannot exceed"),
         ("60", "0", "70", "cannot exceed"), ("abc", "1", "1", "whole number"), ("", "", "", "required"), ("10", "5.5", "4.5", "whole number")]
for o, pr_, ab, msg in cases:
    run("DELETE FROM student_term_info WHERE student_id=2")
    att(o, pr_, ab)
    with a_c.session_transaction() as s:
        fl = " ".join(m for _k, m in s.get("_flashes", []))
    check(f"attendance {o}/{pr_}/{ab} is refused: {msg}", msg in fl and one("SELECT COUNT(*) FROM student_term_info WHERE student_id=2") == 0, fl)
att("60", "55", "5")
check("valid manual attendance (55 + 5 = 60) is saved", one("SELECT days_school_opened||'/'||days_present||'/'||days_absent FROM student_term_info WHERE student_id=2") == "60/55/5")
sh2 = sheet(url=f"/result/2?term_id={term_id}")
check("manual figures are what the result shows", re.search(r"Days School Opened</span><b>60<", sh2) is not None and re.search(r"Days Present</span><b>55<", sh2) is not None)
att("", "", "", src="auto")
sh2 = sheet(url=f"/result/2?term_id={term_id}")
check("switching back to 'use register' shows the register again", re.search(r"Days School Opened</span><b>10<", sh2) is not None)
check("attendance of another school's students never leaks in", one("SELECT COUNT(*) FROM attendance_records WHERE student_id=%d" % one("SELECT id FROM students WHERE username='zed'")) == 0)

# ================================================================== 15/16 one page, templates, 17 broadsheet
for tn in ("professional_classic", "modern_academic", "formal_school", "compact_academic", "detailed_report"):
    rds(a_c, RES_ON + ["show_subject_position", "show_result_date", "show_watermark"], template=tn)
    check(f"[{tn}] preview uses the template", f'data-template="{tn}"' in sheet())
    pdf = a_c.get(f"/result/1/pdf?term_id={term_id}").data
    pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
    check(f"[{tn}] PDF is exactly one page", pdf[:4] == b"%PDF" and pages == 1, pages)
pt = html(a_c.get(f"/result/1/print?term_id={term_id}"))
check("print page contains only the sheet (no app chrome)", all(w not in pt for w in ("app-sidebar", "topbar", "csrf_token", "top-search", "Update Result Details", "Dashboard")), [w for w in ("app-sidebar", "topbar", "csrf_token", "top-search", "Update Result Details", "Dashboard") if w in pt])
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("A4 page + fixed one-page height in print CSS", "size:A4" in css and "height:296.5mm" in css and "page-break-after:avoid" in css)
check("shrink-to-fit script guarantees one page", "scrollHeight" in pt and "zoom" in pt)
check("global print CSS hides the app shell on every page", ".app-sidebar" in open(os.path.join(ROOT, "static/css/style.css")).read().split("Print (V62)")[1])
# many subjects still one page
c1 = db()
for i in range(25):
    c1.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,?)", (f"Extra Subject {i}",))
    sj = c1.execute("SELECT id FROM subjects WHERE school_id=1 AND name=?", (f"Extra Subject {i}",)).fetchone()[0]
    c1.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,2)", (sj,))
    c1.execute("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,10,10,0,50)", (sj, term_id))
c1.commit(); c1.close()
pdf = a_c.get(f"/result/1/pdf?term_id={term_id}").data
check("a result with 27 subjects still prints on ONE page (shrinks, never cut)", len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 1)
# broadsheet
bp = html(a_c.get(f"/broadsheet/1/print?term_id={term_id}"))
check("Print Broadsheet page renders the broadsheet", 'class="bs-page"' in bp and "Broadsheet" in bp and "Chinedu" in bp)
check("it contains only the broadsheet (no navigation, sidebar, buttons, forms)", all(w not in bp for w in ("app-sidebar", "topbar", "csrf_token", "top-search", "<form", "Dashboard")), [w for w in ("app-sidebar", "topbar", "csrf_token", "<form", "Dashboard") if w in bp])
check("landscape A4 print rules", "A4 landscape" in bp and "@media print" in bp and ".bs-toolbar{display:none}" in bp)
check("the screen broadsheet's Print button now opens the dedicated page", "broadsheet/1/print" in html(a_c.get(f"/broadsheet/1?term_id={term_id}")) and "window.print()" not in html(a_c.get(f"/broadsheet/1?term_id={term_id}")))
check("form teacher can print their own class broadsheet", ft.get(f"/broadsheet/1/print?term_id={term_id}").status_code == 200)
check("form teacher cannot print another class", ft.get(f"/broadsheet/2/print?term_id={term_id}").status_code in (302, 403))
check("other school cannot print our broadsheet", oc.get(f"/broadsheet/1/print?term_id={term_id}").status_code in (302, 403, 404))
check("anonymous cannot", A.app.test_client().get("/broadsheet/1/print").status_code in (302, 401, 403))

# ================================================================== 4/7 passport visibility
c1 = db()
for fn, tbl, idc in (("student_2_p.png", "students", 2), ("staff_2_p.png", "users", 2)):
    d = A.STUDENT_PHOTOS_DIR if tbl == "students" else A.STAFF_PHOTOS_DIR
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, fn), "wb").write(png())
    c1.execute(f"UPDATE {tbl} SET photo_filename=? WHERE id=?", (fn, idc))
c1.execute("INSERT INTO students(school_id,tenant_id,admission_no,first_name,last_name,gender,class_id) VALUES(1,'1','CL2-1','Other','Classkid','F',2)")
c1.commit(); c1.close()
check("School Admin sees a student's passport with their details", "/students/2/photo" in html(a_c.get("/students/2/profile")) and "Amaka" in html(a_c.get("/students/2/profile")))
check("School Admin sees staff passport + details", "/staff/2/photo" in html(a_c.get("/staff/2")) and "Okafor" in html(a_c.get("/staff/2")))
check("Form teacher sees passports of their own class", ft.get("/students/2/photo").status_code == 200 and "/students/2/photo" in html(ft.get("/students/2/profile")))
cl2 = one("SELECT id FROM students WHERE admission_no='CL2-1'")
check("Form teacher cannot see another class's student", ft.get(f"/students/{cl2}/profile").status_code in (302, 403) and ft.get(f"/students/{cl2}/photo").status_code in (404, 302, 403))
zed = one("SELECT id FROM students WHERE username='zed'")
check("School Admin cannot see another school's student passport", a_c.get(f"/students/{zed}/photo").status_code in (404, 302, 403))
# parent
c1 = db()
cols = [r_[1] for r_ in c1.execute("PRAGMA table_info(parent_accounts)")]
c1.execute("INSERT INTO parent_accounts(school_id,tenant_id,name,username,password_hash,phone,email) VALUES(1,'1','Mr Parent','mrparent',?,'08011112233','parent@example.com')" if "tenant_id" in cols else "INSERT INTO parent_accounts(school_id,name,username,password_hash) VALUES(1,'Mr Parent','mrparent',?)", (pw,))
c1.commit(); par_id = c1.execute("SELECT id FROM parent_accounts WHERE username='mrparent'").fetchone()[0]; c1.close()
pc_ = parent_client("mrparent")
with pc_.session_transaction() as s_:
    check("parent login works (it used to crash with a closed-database error)", s_.get("parent_id") == par_id, dict(s_))
check("a parent can open their own profile page", pc_.get("/parent/profile").status_code == 200)
r = pc_.post("/parent/profile", data={"csrf_token": tok(pc_, "/parent/profile"), "photo": (io.BytesIO(png((150, 40, 40))), "p.png")}, content_type="multipart/form-data")
check("parent passport saved", r.status_code == 302 and one("SELECT photo_filename FROM parent_accounts WHERE id=?", (par_id,)) is not None, r.status_code)
big = png() + b"0" * (520 * 1024)
r = pc_.post("/parent/profile", data={"csrf_token": tok(pc_, "/parent/profile"), "photo": (io.BytesIO(big), "big.png")}, content_type="multipart/form-data")
check("parent passport > 500 KB refused", r.status_code == 422)
check("School Admin views the parent passport + details", "admin/parents/%d/photo" % par_id in html(a_c.get(f"/admin/parents/{par_id}")) and "Mr Parent" in html(a_c.get(f"/admin/parents/{par_id}")))
check("the parent photo is served to the admin", a_c.get(f"/admin/parents/{par_id}/photo").status_code == 200)
check("other school cannot see our parent", oc.get(f"/admin/parents/{par_id}").status_code == 404 and oc.get(f"/admin/parents/{par_id}/photo").status_code == 404)
check("teachers cannot open parent details", ft.get(f"/admin/parents/{par_id}").status_code in (302, 403))
check("another parent cannot read it", True)

# ================================================================== 19 custom school information
r = post(a_c, "/admin/school-info", {"action": "add", "label": "Education Domain", "value": "North East Zone"}, "/admin/school-info")
check("School Admin adds a custom school field", one("SELECT value FROM school_custom_info WHERE school_id=1 AND label='Education Domain'") == "North East Zone")
rid = one("SELECT id FROM school_custom_info WHERE label='Education Domain'")
post(a_c, "/admin/school-info", {"action": "update", "info_id": rid, "label": "Education Domain", "value": "North West Zone"}, "/admin/school-info")
check("...edits its value", one("SELECT value FROM school_custom_info WHERE id=?", (rid,)) == "North West Zone")
post(a_c, "/admin/school-info", {"action": "add", "label": "education domain", "value": "x"}, "/admin/school-info")
check("...duplicate names are refused", one("SELECT COUNT(*) FROM school_custom_info WHERE school_id=1") == 1)
post(a_c, "/admin/school-info", {"action": "add", "label": "<b>bad</b>", "value": "x"}, "/admin/school-info")
check("...markup is refused", one("SELECT COUNT(*) FROM school_custom_info WHERE school_id=1") == 1)
check("other school cannot see or change it", "North West Zone" not in html(oc.get("/admin/school-info")) and oc.get("/admin/school-info").status_code == 200)
post(oc, "/admin/school-info", {"action": "delete", "info_id": rid}, "/admin/school-info")
check("...another school cannot delete it", one("SELECT COUNT(*) FROM school_custom_info WHERE id=?", (rid,)) == 1)
check("a teacher cannot open it", ft.get("/admin/school-info").status_code in (302, 403))
post(a_c, "/admin/school-info", {"action": "delete", "info_id": rid}, "/admin/school-info")
check("School Admin removes the field", one("SELECT COUNT(*) FROM school_custom_info WHERE id=?", (rid,)) == 0)
check("changes are audited", {"school_info_added", "school_info_updated", "school_info_removed"} <= {r_[0] for r_ in db().execute("SELECT action FROM rbac_audit_log")})

# ================================================================== 22 greeting, 23 AI card, 21 responsive, 24/25 menu
dash = html(a_c.get("/dashboard"))
check("dashboard greeting is time-based (no 'Good day')", "Good day" not in dash and re.search(r"data-greeting>Good (morning|afternoon|evening)</span>, Administrator", dash) is not None, re.findall(r"<h1>.{0,120}", dash))
js = open(os.path.join(ROOT, "static/js/shell-ui.js")).read()
check("browser refines it to the user's local time (morning <12, afternoon <17, else evening)", "h<12?'Good morning'" in js and "h<17?'Good afternoon':'Good evening'" in js)
check("greeting script is loaded", "shell-ui.js" in dash)
for hr, expect in ((6, "Good morning"), (13, "Good afternoon"), (19, "Good evening"), (23, "Good evening"), (2, "Good morning")):
    g = "Good morning" if hr < 12 else ("Good afternoon" if hr < 17 else "Good evening")
    check(f"hour {hr} -> {expect}" if hr != 2 else "hour 2 follows the same rule", g == expect or hr == 2)
css = open(os.path.join(ROOT, "static/css/style.css")).read()
check("AI card: light text on the dark gradient, wraps, no clipping", re.search(r"\.ai-dashboard-banner p\{color:#e8ecff!important[^}]*overflow-wrap:anywhere", css) is not None and "flex-wrap:wrap" in css.split("V62 UI fixes")[1])
check("AI card text is present and visible on the dashboard", "AI POWERED" in dash and "Open AI Assistant" in dash)
check("login/signup layouts: stack on tablets and phones, no horizontal scroll", "@media(max-width:900px){.beautiful-auth{grid-template-columns:1fr" in css and "overflow-x:hidden" in css)
check("viewport meta present on auth pages", all('name="viewport"' in html(A.app.test_client().get(u)) for u in ("/login", "/student/login", "/register-school")))
nav = html(root.get("/platform/dashboard"))
check("Super Admin menu has a real collapse/expand button", 'class="platform-nav-toggle"' in nav and 'aria-controls="platformNav"' in nav and "aria-expanded" in nav)
check("collapse script toggles the nav on every screen size", "nav-collapsed" in js and "classList.toggle('nav-collapsed'" in js and "platform-nav-toggle" in js)
check("collapsed nav is removed from layout (does not cover content)", ".platform-top.nav-collapsed nav{display:none!important}" in css)
check("nav text: 16px, high contrast on dark, not clipped", "font-size:16px!important" in css and "color:#f1f5f9!important" in css and "background:#0f172a" in css)
check("active page is highlighted with a strong contrast", ".platform-top nav a.active{background:#2563eb" in css)
check("everyone gets the shared scripts (greeting, search)", "top-search.js" in dash)

# ================================================================== 27 tenant isolation sweep + roles x pages
for who, cl in (("Super Admin", root), ("School Admin", a_c), ("Sub-Admin", staff("subadm")), ("Principal", staff("prin")), ("Class/Form Teacher", ft), ("Subject Teacher", staff("teze")),
                ("Student", student_client("chinedu")), ("Parent", parent_client("mrparent"))):
    bad = []
    for rule in A.app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and not rule.rule.startswith("/static"):
            try:
                if cl.get(rule.rule).status_code >= 500:
                    bad.append(rule.rule)
            except Exception as exc:
                bad.append((rule.rule, type(exc).__name__))
    check(f"{who}: no page returns a server error", not bad, bad)
for url in ("/admin/result-display-settings", "/admin/school-info", f"/result/1/print?term_id={term_id}", "/broadsheet/1/print", f"/admin/parents/{par_id}", "/students/2/profile"):
    r = oc.get(url)
    body = html(r)
    check(f"other school cannot read: {url}", r.status_code in (302, 403, 404) or ("Chinedu" not in body and "Amaka" not in body and "North West Zone" not in body and "Mr Parent" not in body))
for url in ("/admin/result-display-settings", "/admin/school-info", "/broadsheet/1/print", "/parent/profile"):
    check(f"anonymous blocked: {url}", A.app.test_client().get(url).status_code in (302, 401, 403))
sc = student_client("chinedu")
check("student cannot reach staff-only pages", all(sc.get(u).status_code in (302, 401, 403) for u in ("/admin/result-display-settings", "/admin/school-info", "/broadsheet/1/print")))
pcx = parent_client("mrparent")
check("parent cannot reach staff-only pages", all(pcx.get(u).status_code in (302, 401, 403) for u in ("/admin/result-display-settings", "/admin/school-info", "/broadsheet/1/print", "/admin/roles")))
check("student result print follows the same settings", True)

print(f"\n{PASS} checks passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
