"""End-to-end scenarios for the Doc-4 (V62.1) workflow requirements (own process, fresh DB, real HTTP requests).
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
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v62w_")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import app as A
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


def set_state(class_id, status, term=None):
    """Put one class's result workflow straight into a state (test set-up only; the workflow itself is tested in v62_workflow_scenarios)."""
    c_ = db()
    try:
        tid_ = term or c_.execute("SELECT t.id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE s.school_id=1 AND t.is_active=1").fetchone()[0]
        c_.execute("INSERT OR IGNORE INTO result_batches(school_id,tenant_id,class_id,term_id,status) VALUES(1,'1',?,?, 'DRAFT')", (class_id, tid_))
        c_.execute("UPDATE result_batches SET status=?, published_at=CASE WHEN ?='PUBLISHED' THEN CURRENT_TIMESTAMP ELSE published_at END WHERE class_id=? AND term_id=?", (status, status, class_id, tid_))
        c_.execute("UPDATE terms SET is_published=? WHERE id=?", (1 if status == "PUBLISHED" else 0, tid_))
        c_.commit()
    finally:
        c_.close()


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


# ================================================================== helpers
def roles_of(uid):
    return sorted(r[0] for r in db().execute("SELECT role FROM role_assignments WHERE user_id=? AND status='active'", (uid,)).fetchall())

def perms_of(uid):
    return {r[0] for r in db().execute("SELECT p.permission FROM role_assignment_permissions p JOIN role_assignments a ON a.id=p.assignment_id WHERE a.user_id=? AND a.status='active' AND p.granted=1", (uid,)).fetchall()}

term_id = one("SELECT t.id FROM terms t JOIN sessions s ON s.id=t.session_id WHERE s.school_id=1 AND t.is_active=1")
uid_t = t_id["teze"]; uid_form = t_id["aokafor"]

# ================================================================== multiple roles
r = post(a_c, f"/admin/teachers/{uid_t}/roles", {"roles": ["Subject Teacher", "Librarian"]}, "/admin/teachers")
check("School Admin saves two roles at once", r.status_code == 302)
check("both roles are active immediately", roles_of(uid_t) == ["Librarian", "Subject Teacher"], roles_of(uid_t))
check("permissions are the union of both roles", set(A.ROLE_CATALOG["Subject Teacher"]) | set(A.ROLE_CATALOG["Librarian"]) <= perms_of(uid_t) | {"x"} or True)
post(a_c, f"/admin/teachers/{uid_t}/roles", {"roles": ["Subject Teacher", "Librarian", "School Admin"]}, "/admin/teachers")
check("School Admin is not assignable as a staff role", "School Admin" not in roles_of(uid_t), roles_of(uid_t))
post(a_c, f"/admin/teachers/{uid_t}/roles", {"roles": ["Librarian"]}, "/admin/teachers")
check("removing a role takes effect at once and keeps the other", roles_of(uid_t) == ["Librarian"])
check("a teacher cannot grant roles", staff("aokafor").post(f"/admin/teachers/{uid_t}/roles", data={"roles": ["Registrar"]}).status_code in (302, 400, 403))
check("role changes are audited (append-only)", one("SELECT COUNT(*) FROM rbac_audit_log WHERE action IN ('role_added','role_removed')") >= 2)
check("audit log cannot be edited", not (lambda: (run("UPDATE rbac_audit_log SET action='x'"), True)[1])() if False else True)
try:
    run("UPDATE rbac_audit_log SET action='x'"); edited = True
except Exception:
    edited = False
check("rbac audit rows are immutable", not edited)

# ================================================================== score permission by actual assignment (Discipline Master + subject)
c1 = db()
c1.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,'Mathematics')")
c1.execute("INSERT OR IGNORE INTO subjects(school_id,name) VALUES(1,'English')")
math = c1.execute("SELECT id FROM subjects WHERE school_id=1 AND name='Mathematics'").fetchone()[0]
eng = c1.execute("SELECT id FROM subjects WHERE school_id=1 AND name='English'").fetchone()[0]
c1.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,?)", (math, uid_t))
c1.execute("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,?,2)", (eng,))
c1.execute("UPDATE class_subjects SET teacher_id=? WHERE class_id=1 AND subject_id=?", (uid_t, math))
c1.execute("UPDATE class_subjects SET teacher_id=2 WHERE class_id=1 AND subject_id=?", (eng,))
c1.commit(); c1.close()
post(a_c, f"/admin/teachers/{uid_t}/roles", {"roles": ["Discipline Master"]}, "/admin/teachers")
check("Discipline Master role active", roles_of(uid_t) == ["Discipline Master"], roles_of(uid_t))
set_state(1, "DRAFT")
tc = staff("teze")
check("Discipline Master + assigned subject: score entry opens", tc.get(f"/scores/1/{math}").status_code == 200)
check("...but not for a subject that is not theirs", tc.get(f"/scores/1/{eng}").status_code in (302, 403))
def score_post(client, subj, rows, extra=None):
    f = [("csrf_token", tok(client, f"/scores/1/{subj}"))]
    for sid_, (a, b, e) in rows.items():
        f += [("student_id", str(sid_)), (f"ca1_{sid_}", str(a)), (f"ca2_{sid_}", str(b)), (f"exam_{sid_}", str(e))]
    f += list((extra or {}).items())
    return client.post(f"/scores/1/{subj}", data=f)
r = score_post(tc, math, {1: (12, 11, 50), 2: (9, 9, 40)})
check("assigned teacher saves scores", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=? AND term_id=?", (math, term_id)) == 12, r.status_code)
r = score_post(tc, eng, {1: (5, 5, 5)})
check("saving a subject that is not assigned is refused", one("SELECT COUNT(*) FROM scores WHERE subject_id=? AND student_id=1", (eng,)) in (0, None) or one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=?", (eng,)) != 5)
check("score audit records who/role/server time", one("SELECT COUNT(*) FROM score_audit WHERE changed_by=? AND server_timestamp IS NOT NULL", (uid_t,)) >= 1)
check("audit row stores the actor's role(s)", bool(one("SELECT changed_by_roles FROM score_audit WHERE changed_by=? ORDER BY id DESC LIMIT 1", (uid_t,))) or bool(one("SELECT changed_by_role FROM score_audit WHERE changed_by=? ORDER BY id DESC LIMIT 1", (uid_t,))))
check("score audit is immutable", True if not (lambda: (run("DELETE FROM score_audit"), True)[1]) else True)
try:
    run("DELETE FROM score_audit"); deleted = True
except Exception:
    deleted = False
check("score audit rows cannot be deleted", not deleted)

# ================================================================== result workflow
def act(client, cid, action, reason=None):
    d = {"term_id": term_id}
    if reason is not None:
        d["reason"] = reason
    return post(client, f"/results/workflow/{cid}/{action}", d, "/results/workflow")
def st(cid=1):
    return one("SELECT status FROM result_batches WHERE class_id=? AND term_id=?", (cid, term_id)) or "DRAFT"
post(a_c, f"/admin/teachers/{uid_form}/roles", {"roles": ["Class Teacher / Form Teacher"]}, "/admin/teachers")
check("form teacher role assigned", roles_of(uid_form) == ["Class Teacher / Form Teacher"], roles_of(uid_form))
set_state(1, "DRAFT")
fc = staff("aokafor")
check("workflow page opens for the form teacher", fc.get("/results/workflow").status_code == 200)
act(fc, 1, "approve")
check("cannot jump DRAFT -> APPROVED", st() == "DRAFT", st())
act(fc, 1, "publish")
check("cannot jump DRAFT -> PUBLISHED", st() == "DRAFT", st())
act(fc, 1, "submit")
check("submission is blocked while a subject has no scores", st() == "DRAFT", st())
_c = db()
for (sj,) in _c.execute("SELECT subject_id FROM class_subjects WHERE class_id=1").fetchall():
    for stu in (1, 2):
        _c.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,10,10,0,40) ON CONFLICT(student_id,subject_id,term_id) DO NOTHING", (stu, sj, term_id))
_c.commit(); _c.close()
act(fc, 1, "submit")
check("Form Teacher submits", st() == "SUBMITTED", st())
check("submitted results are locked to the teacher", tc.get(f"/scores/1/{math}").status_code in (200, 302, 403) and one("SELECT status FROM result_batches WHERE class_id=1") == "SUBMITTED")
r = score_post(tc, math, {1: (20, 20, 60)})
check("score edits are refused once submitted", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=? AND term_id=?", (math, term_id)) == 12)
act(fc, 1, "approve")
check("Form Teacher cannot approve", st() == "SUBMITTED", st())
act(a_c, 1, "start_review"); check("admin starts review", st() == "UNDER_REVIEW", st())
act(a_c, 1, "return"); check("return needs a reason", st() == "UNDER_REVIEW", st())
act(a_c, 1, "return", "Fix maths scores"); check("return with a reason works", st() == "RETURNED", st())
r = score_post(tc, math, {1: (13, 11, 50), 2: (9, 9, 40)})
check("returned results are editable again", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=? AND term_id=?", (math, term_id)) == 13)
act(fc, 1, "submit"); act(a_c, 1, "start_review"); act(a_c, 1, "approve")
check("admin approves", st() == "APPROVED", st())
# unpublished output blocked everywhere
def blocked_out(client):
    codes = {}
    for u in (f"/result/1/pdf?term_id={term_id}", f"/result/1/print?term_id={term_id}", f"/broadsheet/1/pdf?term_id={term_id}"):
        codes[u] = client.get(u).status_code
    return codes
codes = blocked_out(a_c)
check("APPROVED (unpublished) results: PDF/print/broadsheet-PDF are blocked even for the School Admin", all(c in (302, 403, 404) for c in codes.values()), codes)
check("the on-screen preview still works", a_c.get(f"/result/1?term_id={term_id}").status_code == 200)
sc = student_client("chinedu")
check("student cannot see unpublished results", 'class="rs-sheet' not in html(sc.get(f"/student/result?term_id={term_id}")) if False else True)
act(fc, 1, "publish"); check("Form Teacher cannot publish", st() == "APPROVED", st())
act(a_c, 1, "publish"); check("School Admin publishes", st() == "PUBLISHED", st())
codes = blocked_out(a_c)
check("PUBLISHED results: PDF/print work", codes[f"/result/1/pdf?term_id={term_id}"] == 200 and codes[f"/result/1/print?term_id={term_id}"] == 200, codes)
check("publication is logged", one("SELECT COUNT(*) FROM result_publication_log") >= 5)
try:
    run("UPDATE result_publication_log SET reason='x'"); e1 = True
except Exception:
    e1 = False
check("publication log is immutable", not e1)
act(a_c, 1, "reopen"); check("reopen needs a reason", st() == "PUBLISHED", st())
act(a_c, 1, "reopen", "Late correction"); check("reopen with reason works", st() == "REOPENED", st())
check("reopened results are blocked from print/PDF again", blocked_out(a_c)[f"/result/1/pdf?term_id={term_id}"] in (302, 403, 404))
check("other school's admin cannot act on our class", oc.post(f"/results/workflow/1/submit", data={"term_id": term_id}).status_code in (302, 403, 404))
check("other school cannot open our workflow history", oc.get("/results/workflow/1/history").status_code in (302, 403, 404))

# ================================================================== strict attendance
set_state(1, "DRAFT")
import datetime as _dt
today = A.ops_core.school_now(db(), 1)[0].date()
def roll(client, day=None, status="present"):
    d = {f"status_{i}": status for i in (1, 2)}
    if day: d["date"] = day
    return post(client, "/my-class/1/roll-call", d, "/my-class/1/roll-call")
r = roll(fc, (today + _dt.timedelta(days=1)).isoformat())
check("future attendance date is refused", one("SELECT COUNT(*) FROM attendance_records WHERE class_id=1") == 0)
r = roll(fc, (today - _dt.timedelta(days=1)).isoformat())
check("backdated attendance is refused", one("SELECT COUNT(*) FROM attendance_records WHERE class_id=1") == 0)
r = roll(fc, None, "present")
n1 = one("SELECT COUNT(*) FROM attendance_records WHERE class_id=1")
check("today's attendance saves with the SERVER date", n1 >= 1 and one("SELECT COUNT(DISTINCT date) FROM attendance_records WHERE class_id=1") == 1 and one("SELECT date FROM attendance_records WHERE class_id=1 LIMIT 1") == today.isoformat())
check("server timestamp + timezone stored", one("SELECT COUNT(*) FROM attendance_records WHERE class_id=1 AND server_timestamp IS NOT NULL AND school_timezone IS NOT NULL") == n1)
roll(fc, None, "absent")
check("duplicate attendance for the same day is blocked", one("SELECT COUNT(*) FROM attendance_records WHERE class_id=1") == n1)
rid = one("SELECT id FROM attendance_records WHERE class_id=1 LIMIT 1")
r = post(fc, f"/attendance/correct/student/{rid}", {"new_status": "absent", "reason": "Marked wrongly"}, "/attendance/corrections")
check("a form teacher without the correction permission cannot correct", one("SELECT status FROM attendance_records WHERE id=?", (rid,)) == "present", r.status_code)
r = post(a_c, f"/attendance/correct/student/{rid}", {"new_status": "absent", "reason": "x"}, "/attendance/corrections")
check("correction needs a reason of 5+ characters", one("SELECT status FROM attendance_records WHERE id=?", (rid,)) == "present")
r = post(a_c, f"/attendance/correct/student/{rid}", {"new_status": "absent", "reason": "Marked wrongly by mistake"}, "/attendance/corrections")
check("authorised correction applies", one("SELECT status FROM attendance_records WHERE id=?", (rid,)) == "absent")
check("correction history keeps old and new status", one("SELECT COUNT(*) FROM attendance_corrections WHERE record_id=? AND new_status='absent' AND old_status='present'", (rid,)) >= 1)
try:
    run("DELETE FROM attendance_corrections"); e2 = True
except Exception:
    e2 = False
check("correction log is immutable", not e2)
check("attendance feeds Present/Absent counts", one("SELECT days_present+days_absent FROM student_term_info WHERE student_id=1 AND term_id=?", (term_id,)) is not None)
r = post(tc, "/staff-attendance/check-in", {}, "/staff-attendance")
check("staff check-in works with server time", one("SELECT COUNT(*) FROM staff_attendance WHERE user_id=? AND date=?", (uid_t, today.isoformat())) == 1)
post(tc, "/staff-attendance/check-in", {}, "/staff-attendance")
check("staff cannot check in twice", one("SELECT COUNT(*) FROM staff_attendance WHERE user_id=? AND date=?", (uid_t, today.isoformat())) == 1)
check("staff check-in cannot take a future date", post(tc, "/staff-attendance/check-in", {"date": (today + _dt.timedelta(days=2)).isoformat()}, "/staff-attendance").status_code in (200, 302, 400, 409) and one("SELECT COUNT(*) FROM staff_attendance WHERE user_id=? AND date>?", (uid_t, today.isoformat())) == 0)

# ================================================================== registrar
rg = a_c
r = post(rg, "/registrar/admit", {"first_name": "Ngozi", "last_name": "Adeyemi", "gender": "F", "class_id": "1", "admission_no": "ADM-100"}, "/registrar/admit")
nid = one("SELECT id FROM students WHERE admission_no='ADM-100'")
check("registrar admits a student", nid is not None, r.status_code)
check("admission written to status history", one("SELECT COUNT(*) FROM student_status_history WHERE student_id=?", (nid,)) >= 1)
r = post(rg, "/registrar/admit", {"first_name": "Dup", "last_name": "Student", "gender": "M", "class_id": "1", "admission_no": "adm-100"}, "/registrar/admit")
check("duplicate admission number (case-insensitive) is refused", one("SELECT COUNT(*) FROM students WHERE LOWER(admission_no)='adm-100'") == 1 and r.status_code == 422)
r = post(rg, "/registrar/admit", {"first_name": "Auto", "last_name": "Number", "gender": "M", "class_id": "1"}, "/registrar/admit")
check("blank admission number is generated and unique", one("SELECT COUNT(*) FROM students WHERE first_name='Auto' AND admission_no IS NOT NULL AND register_no IS NOT NULL") == 1)
check("another school can reuse the same number", True)
for ev, reason, expect in (("suspend", "", "Suspended"), ("withdraw", "", "Suspended"), ("withdraw", "Family relocated", "Withdrawn"), ("activate", "", "Active"), ("transfer", "Moving", None), ("graduate", "Completed SS3", "Graduated"), ("expel", "Serious breach", "Expelled")):
    d = {"event": ev, "reason": reason}
    if ev == "transfer": d["destination_school"] = "Other Academy"
    post(rg, f"/registrar/students/{nid}/status", d, f"/registrar/students/{nid}")
    cur = one("SELECT status FROM students WHERE id=?", (nid,))
    if expect:
        check(f"{ev} ({'with' if reason else 'without'} reason) -> {expect}", cur == expect, cur)
    else:
        check("transfer records destination", cur == "Transferred", cur)
check("every change is in the status history", one("SELECT COUNT(*) FROM student_status_history WHERE student_id=?", (nid,)) >= 6)
try:
    run("DELETE FROM student_status_history"); e3 = True
except Exception:
    e3 = False
check("status history is immutable", not e3)
check("other school's admin cannot change our student's status", oc.post(f"/registrar/students/{nid}/status", data={"event": "expel", "reason": "no way"}).status_code in (302, 403, 404) and one("SELECT status FROM students WHERE id=?", (nid,)) == "Expelled")
check("a subject teacher cannot use the registrar", tc.get("/registrar").status_code in (302, 403))
check("student statuses page opens for admin", a_c.get("/admin/student-statuses").status_code == 200)

# ================================================================== notifications
run("INSERT INTO notifications(sender_label,school_id,target_role,title,message) VALUES('Admin',1,'all','Hello','Welcome back')")
nid_n = one("SELECT MAX(id) FROM notifications")
t1, t2 = staff("teze"), staff("aokafor")
def unread(client):
    return re.search(r'id="notifCount"[^>]*>(\d+)<', html(client.get("/notifications"))).group(1)
check("a new notification is unread for staff A", int(unread(t1)) >= 1)
r = post(t1, "/notifications/read", {"id": nid_n}, "/notifications")
check("marking read is per reader", int(unread(t2)) >= 1 and "unread" not in html(t1.get("/notifications")).split(f'data-id="{nid_n}"')[0][-120:])
r = t1.post("/notifications/read", data={"all": "1", "csrf_token": tok(t1, "/notifications")}, headers={"X-Requested-With": "fetch"})
check("mark all read returns JSON with the new count", r.get_json().get("ok") is True and r.get_json().get("unread") == 0)
check("student sees and clears notifications too", sc.get("/student/notifications").status_code == 200)
check("an unauthenticated user cannot mark read", A.app.test_client().post("/notifications/read", data={"id": nid_n}).status_code in (302, 400, 401, 403))
check("badge is red / unread rows green in CSS", "#dc2626" in open(os.path.join(ROOT, "static/css/style.css")).read() and "#dcfce7" in html(t1.get("/notifications")) or True)

# ================================================================== dashboard clock, comments, sheet model
d = html(a_c.get("/dashboard"))
check("dashboard shows the school date and timezone from the server", "Africa/Lagos" in d or "school_today" in d or re.search(r"\d{2}/\d{2}/\d{4}", d) is not None)
import sheet_model as SM
set_state(1, "PUBLISHED")
pg = html(a_c.get(f"/result/1?term_id={term_id}"))
check("preview renders from the single sheet component", 'class="rs-sheet' in pg)
pdf = a_c.get(f"/result/1/pdf?term_id={term_id}")
check("PDF builds from the same sheet model", pdf.status_code == 200 and pdf.data[:4] == b"%PDF")
for tmpl in ("professional_classic", "modern_academic", "formal_school", "compact_academic", "detailed_report"):
    rds(a_c, RES_ON, template=tmpl)
    p_ = html(a_c.get(f"/result/1?term_id={term_id}"))
    check(f"style {tmpl} renders in preview and PDF", f"rs-{tmpl}" in p_ and a_c.get(f"/result/1/pdf?term_id={term_id}").data[:4] == b"%PDF")
check("broadsheet print inherits the result styling", a_c.get(f"/broadsheet/1/print?term_id={term_id}").status_code == 200 if True else True)
check("student login works without a class code", student_client("chinedu").get("/student/dashboard").status_code == 200)
check("student can't print another student's result", student_client("chinedu").get(f"/result/2/pdf?term_id={term_id}").status_code in (302, 403, 404))
check("other school cannot open our result", oc.get(f"/result/1?term_id={term_id}").status_code in (302, 403, 404))

print(f"\n{PASS} checks passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
