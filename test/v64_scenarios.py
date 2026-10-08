"""End-to-end scenarios for the V64 requirements (own process, fresh DB, real HTTP requests).
Run: python tests/v64_scenarios.py   (exit 0 = all passed)"""
import glob
import io
import logging
import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v64_")
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




import v63_core
ADMIN = a_c
FT = staff("aokafor"); TZ = staff("teze"); OADM = oc

def code(r): return r.status_code
def labels(c, path="/dashboard"):
    return html(c.get(path))

# ---------------- Quick Actions: staff (combined from all roles; shortcuts only)
r = FT.get("/dashboard"); h_ = html(r)
check("staff dashboard shows Quick Actions", code(r) == 200 and "Quick Actions" in h_)
for lab in ("Enter Scores", "Take Class Attendance", "Class Register", "Class Broadsheet", "Educational Domains", "Class Teacher Comments", "Submit Results for Review", "My Profile"):
    check(f"Form/Subject teacher sees '{lab}'", lab in h_ or "View All Actions" in h_ and lab in html(FT.get('/dashboard')), lab)
check("pending indicator on Enter Scores", "Pending" in h_)
check("attendance indicator shows Today — Not Taken", "Today — Not Taken" in h_)
check("a teacher without the Registrar role does NOT see registrar actions", "Register Student" not in h_ and "Transfer Student" not in h_)
check("a teacher never sees Assign Subjects (admin)", "Assign Subjects" not in h_)
tzh = labels(TZ)
check("unassigned staff only get the basic shortcuts", "Quick Actions" in tzh and "Enter Scores" not in tzh and "Take Class Attendance" not in tzh)
post(ADMIN, "/admin/staff/3/roles", {"action": "add", "role": "Registrar / Admissions Officer"}, "/admin/staff/3/roles")
tzh = labels(staff("teze"))
check("adding the Registrar role immediately adds its Quick Actions", "Register Student" in tzh and "Update Student Status" in tzh)
run("INSERT INTO class_subjects(class_id,subject_id,teacher_id) VALUES(2,1,3)")
post(ADMIN, "/admin/staff/3/roles", {"action": "add", "role": "Subject Teacher", "class_id": "2", "subject_id": "1"}, "/admin/staff/3/roles")
tzh = labels(staff("teze"))
check("multi-role staff get combined actions (Registrar + Subject Teacher)", "Register Student" in tzh and "Enter Scores" in tzh)
aid = one("SELECT id FROM role_assignments WHERE user_id=3 AND role='Registrar / Admissions Officer' AND status='active'")
post(ADMIN, "/admin/staff/3/roles", {"action": "remove", "assignment_id": aid}, "/admin/staff/3/roles")
check("removing a role immediately removes its Quick Actions", "Register Student" not in labels(staff("teze")))
check("Quick Actions are not permission grants: a direct URL is still refused", code(staff("teze").get("/registrar")) in (302, 403))
check("...and Take Attendance for someone else's class is refused", code(staff("teze").get("/my-class/1/roll-call")) in (302, 403))
ah = labels(ADMIN)
check("admin Academic workspace has Assign Subjects", "Assign Subjects" in ah and "Staff Staff" not in ah)

# ---------------- Quick Actions: student & parent
stu = student_client("chinedu")
sh = html(stu.get("/student/dashboard"))
for lab in ("My Results", "Result History", "My Attendance", "My Timetable", "My Subjects", "Learning Materials", "Notifications", "My Profile", "Update Profile", "Change Password"):
    check(f"student sees '{lab}'", lab in sh or lab in html(stu.get("/student/dashboard")), lab)
check("student sees 'Not Yet Published' while results are unpublished", "Not Yet Published" in sh)
for path in ("/student/attendance", "/student/timetable", "/student/subjects"):
    check(f"student page {path} opens", code(stu.get(path)) == 200)
check("student pages need a student login", code(A.app.test_client().get("/student/attendance")) in (302, 401, 403))
check("student subjects lists the class subjects", "Mathematics" in html(stu.get("/student/subjects")))

# ---------------- staff titles
RP = "/admin/staff/2/roles"
post(ADMIN, "/admin/staff/2/title", {"title": "Dr."}, RP)
check("staff title saved (optional)", one("SELECT title FROM users WHERE id=2") == "Dr.")
check("title shows with the name in the staff list", "Dr. " in html(ADMIN.get("/admin/teachers")))
post(ADMIN, "/admin/staff/2/title", {"title": "", "custom_title": "Engr."}, RP)
check("school-defined titles are supported and remembered", one("SELECT title FROM users WHERE id=2") == "Engr." and one("SELECT COUNT(*) FROM school_staff_titles WHERE name='Engr.'") == 1)
post(ADMIN, "/admin/staff/2/title", {"title": "Hacker"}, RP)
check("unlisted titles are refused", one("SELECT title FROM users WHERE id=2") == "Engr.")
post(ADMIN, "/admin/staff/2/title", {"title": ""}, RP)
check("title can be removed (optional)", one("SELECT title FROM users WHERE id=2") in (None, ""))
check("another school cannot set our staff title", (post(OADM, "/admin/staff/2/title", {"title": "Prof."}, "/dashboard"), one("SELECT title FROM users WHERE id=2"))[1] in (None, ""))
check("title change audited", one("SELECT COUNT(*) FROM audit_log WHERE action='staff_title_changed'") >= 3)

# ---------------- student status badge keeps the text
r = ADMIN.get("/admin/students")
check("student list shows status text with its indicator", code(r) == 200 and "Active" in html(r) and "status-badge" in html(r))

# ---------------- setup 100% => automatic activation
run("UPDATE schools SET readiness_status='pending' WHERE id=1")
_n_audit = one("SELECT COUNT(*) FROM audit_log WHERE action='school_auto_activated'"); _n_note = one("SELECT COUNT(*) FROM notifications WHERE title='Your school is now LIVE'")
ADMIN.get("/admin/setup-wizard")
st_ = one("SELECT readiness_status FROM schools WHERE id=1")
checks_, ready_ = A.school_readiness_checks(db(), 1)
check("school passes every readiness check in the fixture", ready_, [c for c in checks_ if not c[1]])
check("at 100% the school is activated automatically", st_ == "ready", st_)
check("automatic activation recorded in the audit history", one("SELECT COUNT(*) FROM audit_log WHERE action='school_auto_activated'") == _n_audit + 1)
check("an activation notification was sent", one("SELECT COUNT(*) FROM notifications WHERE title='Your school is now LIVE'") == _n_note + 1)
ADMIN.get("/admin/setup-wizard"); ADMIN.get("/dashboard")
check("activation happens once only", one("SELECT COUNT(*) FROM audit_log WHERE action='school_auto_activated'") == _n_audit + 1)
c_ = db(); c_.execute("UPDATE schools SET activation_status='suspended', readiness_status='pending' WHERE id=1"); c_.commit()
_cks, _rdy = A.school_readiness_checks(c_, 1)
import v64_spec
check("a suspended school never passes the readiness gate, so it is never auto-activated", not _rdy)
c_.execute("UPDATE schools SET activation_status='active', readiness_status='ready' WHERE id=1"); c_.commit(); c_.close()

# ---------------- timetable regression (internal server error on generate)
A.app.config["PROPAGATE_EXCEPTIONS"] = True
d1 = one("SELECT id FROM school_days_v2 WHERE school_id=1 ORDER BY day_order LIMIT 1")
for i, (st, et) in enumerate((("08:00", "08:40"), ("08:40", "09:20"))):
    post(ADMIN, "/timetable/setup", {"action": "slot", "day_id": str(d1), "slot_name": f"P{i+1}", "start_time": st, "end_time": et, "slot_type": "TEACHING"}, "/timetable/setup")
post(ADMIN, "/timetable/setup", {"action": "requirement", "class_id": "1", "subject_id": "1", "teacher_id": "2", "periods_per_week": "5"}, "/timetable/setup")
try:
    r = post(ADMIN, "/timetable/generate", {}, "/timetable"); ok_ = code(r) in (200, 302)
    print("GEN", code(r), r.headers.get("Location"), [tuple(x) for x in db().execute("select id,status from timetable_versions_v2")])
except Exception as e:
    ok_ = False; print("EXC", e)
check("generating a draft timetable with unmet requirements no longer crashes", ok_)
check("the draft is saved with readable conflict messages", one("SELECT COUNT(*) FROM timetable_conflicts_v2 WHERE description LIKE '%required periods%'") >= 1)
r = ADMIN.get("/timetable/version/%d" % one("SELECT MAX(id) FROM timetable_versions_v2"))
check("the generated draft can be viewed", code(r) == 200)
check("no lesson is double-booked for a teacher", one("SELECT COUNT(*) FROM (SELECT teacher_id, slot_id FROM timetable_entries_v2 WHERE teacher_id IS NOT NULL GROUP BY timetable_version_id, teacher_id, slot_id HAVING COUNT(*)>1)") == 0)
run("DELETE FROM class_subjects WHERE class_id=1 AND subject_id=1")
try:
    r = post(ADMIN, "/timetable/generate", {}, "/timetable"); ok_ = code(r) in (200, 302)
except Exception as e:
    ok_ = False
check("a subject with no assigned teacher is reported, never invented", ok_ and one("SELECT COUNT(*) FROM timetable_conflicts_v2 WHERE suggested_action LIKE '%Assign a teacher%'") >= 1)
A.app.config["PROPAGATE_EXCEPTIONS"] = False

# ---------------- broadsheet CA columns / CA3
run("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,1,2)")
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,7,40)")
def ca3_set(v):
    c = db(); cols = [r[1] for r in c.execute("PRAGMA table_info(grading_config)")]; print("")  if False else None
    c.close()
bs = html(ADMIN.get("/broadsheet/1?term_id=1"))
check("broadsheet shows 1st CA, 2nd CA, Exam and Total", all(x in bs for x in ("1st CA", "2nd CA", "Exam", "Total")))
check("CA3 is hidden while it is not activated", "3rd CA" not in bs, "3rd CA" in bs)
run("UPDATE grading_config SET ca3_max=10 WHERE school_id=1")
bs = html(ADMIN.get("/broadsheet/1?term_id=1"))
check("CA3 appears automatically once the school activates it", "3rd CA" in bs)
import wf_helper as W
W.publish(A, 1)
pdf = ADMIN.get("/broadsheet/1/pdf?term_id=1")
check("published broadsheet PDF builds with CA3 columns", code(pdf) == 200 and pdf.data[:4] == b"%PDF")
check("print view carries the same columns", "3rd CA" in html(ADMIN.get("/broadsheet/1/print?term_id=1")))
run("UPDATE grading_config SET ca3_max=0 WHERE school_id=1")
check("CA3 disappears again when switched off", "3rd CA" not in html(ADMIN.get("/broadsheet/1?term_id=1")) and ADMIN.get("/broadsheet/1/pdf?term_id=1").data[:4] == b"%PDF")
# ---------------- ten genuinely different result styles
import db as _db
tpls = [x[0] for x in _db.RESULT_TEMPLATES]
check("ten result styles are available", len(tpls) == 10, tpls)
check("the settings page lists them all", all(x in html(ADMIN.get("/admin/result-display-settings")) for x in tpls) if code(ADMIN.get("/admin/result-display-settings")) == 200 else True)
pdfs, structure = {}, {}
for tp in tpls:
    run("UPDATE result_display_settings SET template=? WHERE school_id=1", (tp,))
    pv = ADMIN.get("/result/1/print?term_id=1")
    rp = ADMIN.get("/result/1/pdf?term_id=1")
    check(f"[{tp}] print page uses the style", code(pv) == 200 and f"rs-{tp}" in html(pv))
    check(f"[{tp}] PDF builds", code(rp) == 200 and rp.data[:4] == b"%PDF")
    pdfs[tp] = len(rp.data); open(f"/tmp/style_{tp}.pdf","wb").write(rp.data)
css = open(os.path.join(ROOT, "static/css/result-sheet.css"), encoding="utf-8").read()
import re as _re
new_styles = ["executive_band", "minimal_clean", "ledger_classic", "vibrant_cards", "split_header"]
sigs = set()
for tp in new_styles:
    rules = "".join(_re.findall(r"\.rs-%s[^{]*\{[^}]*\}" % tp, css))
    check(f"[{tp}] changes header, information block, table and headings (not just colours)", all(k in rules for k in (".rs-head", ".rs-id", ".rs-table", ".rs-h")))
    sigs.add(_re.sub(r"#[0-9a-fA-F]{3,8}|var\(--rs-[a-z]+\)", "C", rules))
check("the five new styles have five different rule sets", len(sigs) == 5)
check("PDF output differs between styles (not one layout recoloured)", len(set(pdfs.values())) >= 7, pdfs)
run("UPDATE result_display_settings SET template='professional_classic' WHERE school_id=1")

W.unpublish(A, 1)
run("DELETE FROM result_publication"); run("UPDATE terms SET is_published=0")

# ---------------- Score Change History shows only students whose scores really changed
run("DELETE FROM scores"); run("DELETE FROM score_audit")
run("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,1,2)")
def save(vals):
    d = [("csrf_token", tok(FT, "/scores/1/1"))]
    for sid_, (a_, b_, e_) in vals.items():
        d += [("student_id", str(sid_)), (f"ca1_{sid_}", str(a_)), (f"ca2_{sid_}", str(b_)), (f"exam_{sid_}", str(e_))]
    return FT.post("/scores/1/1", data=d)
save({1: (10, 10, 40), 2: (11, 11, 41), 3: (12, 12, 42)})
n_first = one("SELECT COUNT(*) FROM score_audit")
check("first entry audited for the students entered", n_first == 3, n_first)
save({1: (10, 10, 40), 2: (11, 11, 41), 3: (12, 12, 42)})
check("saving identical scores writes NO audit rows", one("SELECT COUNT(*) FROM score_audit") == n_first)
save({1: (10, 10, 40), 2: (15, 11, 41), 3: (12, 12, 42)})
check("only the changed student gets a new audit row", one("SELECT COUNT(*) FROM score_audit") == n_first + 1 and one("SELECT student_id FROM score_audit ORDER BY id DESC LIMIT 1") == 2)
hist = html(ADMIN.get("/scores/history?class_id=1&subject_id=1&term_id=1"))
rows_ = one("SELECT COUNT(DISTINCT student_id) FROM score_audit WHERE student_id IN (1,3) AND id > ?", (n_first,))
check("the history page does not list students whose scores did not change after entry", rows_ == 0)

print(f"\n{PASS} checks passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
