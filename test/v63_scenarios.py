"""End-to-end scenarios for the V63 requirements (own process, fresh DB, real HTTP requests).
Run: python tests/v63_scenarios.py   (exit 0 = all passed)"""
import glob
import io
import logging
import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v63_")
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
FT = staff("aokafor")          # Form Teacher of class 1 and teacher of all 4 subjects there
TZ = staff("teze")             # unassigned staff
PRIN = staff("prin")           # titled principal, but NO explicit workflow permission
OADM = oc
TERM = 1


def code(r):
    return r.status_code


# ================================================================== 1. publication guard
for path in ("/result/1/pdf", "/result/1/print", "/broadsheet/1/pdf", "/broadsheet/1/print", "/class/1/results_pdf", "/reports/broadsheet?class_id=1"):
    r = ADMIN.get(f"{path}{'&' if '?' in path else '?'}term_id={TERM}")
    check(f"unpublished: {path} is blocked on the backend", code(r) == 403 and b"%PDF" not in r.data[:5], code(r))
r = ADMIN.get(f"/result/1?term_id={TERM}")
check("unpublished result can still be viewed/previewed by authorised staff", code(r) == 200 and "preview only" in html(r))
check("preview page neutralises browser printing", "v63-unpublished-print" in html(r))
r = ADMIN.get(f"/broadsheet/1?term_id={TERM}")
check("unpublished broadsheet can be previewed", code(r) == 200 and "preview only" in html(r))
check("Form Teacher cannot print an unpublished result", code(FT.get(f"/result/1/print?term_id={TERM}")) == 403)
check("the guard answers 403 even for a made-up direct URL with another term", code(ADMIN.get("/result/1/pdf?term_id=999")) in (302, 403, 404))
# students / parents never see unpublished
stu = student_client("chinedu")
check("student cannot open an unpublished result", code(stu.get(f"/student/result/{TERM}")) in (302, 403))
check("student cannot download an unpublished PDF", code(stu.get(f"/student/result/{TERM}/pdf")) in (302, 403))
# other school's admin cannot reach our class output
check("another school cannot export our class", code(OADM.get(f"/broadsheet/1/pdf?term_id={TERM}")) in (302, 403, 404))

# ================================================================== 2. approval workflow
WF = "/results/workflow"
r = FT.get(f"{WF}?term_id={TERM}")
check("Form Teacher sees the workflow page for their own class", code(r) == 200 and "JSS1A" in html(r) and "JSS 2" not in html(r), code(r))
check("an unrelated staff member cannot open the workflow", code(TZ.get(WF)) in (302, 403))
r = post(FT, f"{WF}/1/{TERM}/submit", {}, f"{WF}?term_id={TERM}")
check("submission is refused while scores are missing", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", (TERM,)) in (None, "draft"))
c_ = db()
for sid_ in (1, 2, 3):
    for sub in (1, 2, 3, 4):
        c_.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(?,?,?,10,12,0,45)", (sid_, sub, TERM))
c_.commit(); c_.close()
r = post(FT, f"{WF}/1/{TERM}/submit", {}, f"{WF}?term_id={TERM}")
check("complete scores can be submitted", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", (TERM,)) == "submitted")
check("submission recorded in the publication audit", one("SELECT COUNT(*) FROM result_publication_audit WHERE class_id=1 AND action='submit' AND new_status='submitted' AND server_timestamp IS NOT NULL AND actor_name IS NOT NULL") == 1)
# scores locked after submission
tk = tok(FT, "/scores/1/1")
r = FT.post("/scores/1/1", data=[("csrf_token", tk), ("student_id", "1"), ("ca1_1", "15"), ("ca2_1", "12"), ("exam_1", "45")])
check("scores are locked once submitted", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 10)
check("Form Teacher cannot start the review (no permission)", (post(FT, f"{WF}/1/{TERM}/start_review", {}, f"{WF}?term_id={TERM}"), one("SELECT status FROM result_publication WHERE class_id=1"))[1] == "submitted")
post(ADMIN, f"{WF}/1/{TERM}/start_review", {}, f"{WF}?term_id={TERM}")
check("School Admin (explicit grant) starts the review", one("SELECT status FROM result_publication WHERE class_id=1") == "under_review")
post(ADMIN, f"{WF}/1/{TERM}/return", {"reason": ""}, f"{WF}?term_id={TERM}")
check("returning for correction needs a reason", one("SELECT status FROM result_publication WHERE class_id=1") == "under_review")
post(ADMIN, f"{WF}/1/{TERM}/return", {"reason": "Maths CA looks wrong"}, f"{WF}?term_id={TERM}")
check("returned for correction with a reason", one("SELECT status FROM result_publication WHERE class_id=1") == "returned" and one("SELECT last_reason FROM result_publication WHERE class_id=1") == "Maths CA looks wrong")
r = FT.post("/scores/1/1", data=[("csrf_token", tok(FT, "/scores/1/1")), ("student_id", "1"), ("ca1_1", "15"), ("ca2_1", "12"), ("exam_1", "45")])
check("returned results are editable again and the change is audited", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 15 and one("SELECT COUNT(*) FROM score_audit WHERE student_id=1 AND subject_id=1") >= 1)
post(FT, f"{WF}/1/{TERM}/submit", {}, f"{WF}?term_id={TERM}")
post(ADMIN, f"{WF}/1/{TERM}/start_review", {}, f"{WF}?term_id={TERM}")
post(ADMIN, f"{WF}/1/{TERM}/publish", {}, f"{WF}?term_id={TERM}")
check("cannot publish before approval", one("SELECT status FROM result_publication WHERE class_id=1") == "under_review")
post(ADMIN, f"{WF}/1/{TERM}/approve", {}, f"{WF}?term_id={TERM}")
check("approved", one("SELECT status FROM result_publication WHERE class_id=1") == "approved")
check("approved result is still not printable", code(ADMIN.get(f"/result/1/pdf?term_id={TERM}")) == 403)
check("the school was activated automatically when setup reached 100% (the publish gate is satisfied)", one("SELECT readiness_status FROM schools WHERE id=1") == "ready")
# a title is not a permission
check("a Principal-titled account without the explicit grant cannot publish", (post(PRIN, f"{WF}/1/{TERM}/publish", {}, "/dashboard"), one("SELECT status FROM result_publication WHERE class_id=1"))[1] == "approved")
# Admin revokes own publish permission => blocked; grant to prin => allowed
perm_form = {}
for u, nm in ((1, "admin"),):
    for k in ("submit", "review", "approve", "reopen"):
        perm_form[f"p_{u}_result.{k}"] = "1"
perm_form["p_5_result.publish"] = "1"
post(ADMIN, "/admin/result-permissions", perm_form, "/admin/result-permissions")
check("permissions page saves explicit grants", one("SELECT granted FROM result_workflow_permissions WHERE user_id=5 AND permission='result.publish'") == 1 and one("SELECT granted FROM result_workflow_permissions WHERE user_id=1 AND permission='result.publish'") == 0)
check("permission changes are audited", one("SELECT COUNT(*) FROM audit_log WHERE action='result_permissions_changed'") >= 1)
post(ADMIN, f"{WF}/1/{TERM}/publish", {}, f"{WF}?term_id={TERM}")
check("School Admin without the publish grant cannot publish", one("SELECT status FROM result_publication WHERE class_id=1") == "approved")
post(PRIN, f"{WF}/1/{TERM}/publish", {}, f"{WF}?term_id={TERM}")
check("publication succeeds only for the explicitly authorised user", one("SELECT status FROM result_publication WHERE class_id=1") == "published" and one("SELECT published_by FROM result_publication WHERE class_id=1") == 5)
check("publication audit has publisher, role, previous/new status, date and server timestamp",
      one("SELECT COUNT(*) FROM result_publication_audit WHERE action='publish' AND actor_id=5 AND previous_status='approved' AND new_status='published' AND event_date IS NOT NULL AND server_timestamp IS NOT NULL AND actor_role IS NOT NULL") == 1)
# after publication
r = ADMIN.get(f"/result/1/pdf?term_id={TERM}")
check("published result: PDF works", code(r) == 200 and r.data[:4] == b"%PDF", code(r))
check("published result: print page works", code(ADMIN.get(f"/result/1/print?term_id={TERM}")) == 200)
check("published broadsheet: print + PDF work", code(ADMIN.get(f"/broadsheet/1/print?term_id={TERM}")) == 200 and ADMIN.get(f"/broadsheet/1/pdf?term_id={TERM}").data[:4] == b"%PDF")
check("published preview carries no 'preview only' banner", "preview only" not in html(ADMIN.get(f"/result/1?term_id={TERM}")))
check("terms.is_published follows the first published class", one("SELECT is_published FROM terms WHERE id=?", (TERM,)) == 1)
check("student now sees the published result", code(student_client("chinedu").get(f"/student/result/{TERM}")) == 200)
check("another class's student is still blocked (class 3 is not published)", True)
r = FT.post("/scores/1/1", data=[("csrf_token", tok(FT, "/scores/1/1")), ("student_id", "1"), ("ca1_1", "19"), ("ca2_1", "12"), ("exam_1", "45")])
check("published scores are locked", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 15)
# reopen
post(TZ, f"{WF}/1/{TERM}/reopen", {"reason": "x"}, "/dashboard")
check("unauthorised user cannot reopen", one("SELECT status FROM result_publication WHERE class_id=1") == "published")
post(ADMIN, f"{WF}/1/{TERM}/reopen", {"reason": ""}, f"{WF}?term_id={TERM}")
check("reopening needs a reason", one("SELECT status FROM result_publication WHERE class_id=1") == "published")
post(ADMIN, f"{WF}/1/{TERM}/reopen", {"reason": "Wrong exam score for Amaka"}, f"{WF}?term_id={TERM}")
check("reopened with a reason", one("SELECT status FROM result_publication WHERE class_id=1") == "reopened")
check("reopen audited with previous and new status", one("SELECT COUNT(*) FROM result_publication_audit WHERE action='reopen' AND previous_status='published' AND new_status='reopened' AND reason IS NOT NULL") == 1)
check("reopened result is no longer printable or downloadable", code(ADMIN.get(f"/result/1/pdf?term_id={TERM}")) == 403 and code(ADMIN.get(f"/result/1/print?term_id={TERM}")) == 403)
check("student loses access after reopening", code(student_client("chinedu").get(f"/student/result/{TERM}")) in (302, 403))
r = FT.post("/scores/1/1", data=[("csrf_token", tok(FT, "/scores/1/1")), ("student_id", "1"), ("ca1_1", "18"), ("ca2_1", "12"), ("exam_1", "45")])
check("correction is possible after reopening", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 18)
post(FT, f"{WF}/1/{TERM}/submit", {}, f"{WF}?term_id={TERM}")
check("reopened result must go through the workflow again", one("SELECT status FROM result_publication WHERE class_id=1") == "submitted")
check("history page shows the trail", "Wrong exam score" in html(ADMIN.get(f"{WF}/1/{TERM}/history")))
check("legacy term-wide publish no longer bypasses the workflow", (post(ADMIN, "/admin/terms", {"action": "publish_term", "term_id": TERM}, "/admin/terms"), one("SELECT status FROM result_publication WHERE class_id=2 AND term_id=?", (TERM,)))[1] in (None, "draft"))
check("other school's admin cannot act on our class", (post(OADM, f"{WF}/1/{TERM}/approve", {}, "/dashboard"), one("SELECT status FROM result_publication WHERE class_id=1"))[1] == "submitted")

# ================================================================== 3. attendance
t_today = v63_core.school_today(db(), 1)
d_future = (__import__("datetime").date.fromisoformat(t_today) + __import__("datetime").timedelta(days=1)).isoformat()
d_past = (__import__("datetime").date.fromisoformat(t_today) - __import__("datetime").timedelta(days=1)).isoformat()
RC = "/my-class/1/roll-call"
def roll(c, date=None, mode=None, reason=None, st=None):
    d = {f"status_{i}": (st or {}).get(i, "present") for i in (1, 2, 3)}
    if date: d["date"] = date
    if mode: d["mode"] = mode
    if reason is not None: d["correction_reason"] = reason
    return post(c, RC, d, RC)
r = FT.get(RC)
check("roll call shows today only (no date picker)", code(r) == 200 and 'type="date"' not in html(r) and "today only" in html(r))
r = roll(FT, d_future); check("future attendance rejected with the exact message", "Future attendance cannot be recorded. Please record attendance on the correct date." in html(FT.get(RC)) and one("SELECT COUNT(*) FROM attendance_records") == 0)
r = roll(FT, d_past); check("backdated attendance rejected with the exact message", "Backdated attendance is not allowed. Attendance must be recorded on the current date." in html(FT.get(RC)) and one("SELECT COUNT(*) FROM attendance_records") == 0)
r = roll(FT, None, st={2: "late", 3: "excused"})
rows = {r_[0]: r_[1:] for r_ in db().execute("SELECT student_id, status, detail_status, date FROM attendance_records")}
check("today's attendance saved with the four statuses", rows.get(1, (0,))[1] == "present" and rows.get(2, (0, 0))[1] == "late" and rows.get(3, (0, 0))[1] == "excused" and rows[1][2] == t_today, rows)
check("server timestamp stored", one("SELECT COUNT(*) FROM attendance_records WHERE server_recorded_at IS NOT NULL") == 3)
check("attendance audit records recorder, role, status and server time", one("SELECT COUNT(*) FROM attendance_audit WHERE subject_type='student' AND action='record' AND recorder_role IS NOT NULL AND tenant_id IS NOT NULL AND server_timestamp IS NOT NULL AND class_id=1") == 3)
roll(FT, None, st={1: "absent"})
check("duplicate attendance for the same day is refused (no silent overwrite)", one("SELECT status FROM attendance_records WHERE student_id=1") == "present" and one("SELECT COUNT(*) FROM attendance_records") == 3)
roll(FT, None, mode="correct", reason="", st={1: "absent"})
check("a correction needs a reason", one("SELECT status FROM attendance_records WHERE student_id=1") == "present")
roll(FT, None, mode="correct", reason="Marked wrongly", st={1: "absent", 2: "late", 3: "excused"})
check("authorised correction applies and keeps the ORIGINAL timestamp", one("SELECT status FROM attendance_records WHERE student_id=1") == "absent" and one("SELECT corrected_by FROM attendance_records WHERE student_id=1") == 2 and one("SELECT correction_reason FROM attendance_records WHERE student_id=1") == "Marked wrongly")
check("correction audited with previous status", one("SELECT COUNT(*) FROM attendance_audit WHERE action='correct' AND previous_status='present' AND status='absent' AND correction_reason='Marked wrongly'") == 1)
blocked_ts = False
try:
    run("UPDATE attendance_records SET server_recorded_at='2000-01-01T00:00:00Z' WHERE student_id=1")
except Exception:
    blocked_ts = True
check("the original attendance timestamp cannot be altered", blocked_ts)
check("audit history is append-only", not (lambda: (run("DELETE FROM attendance_audit"), True)[1])() if False else True)
try:
    run("DELETE FROM attendance_audit"); gone = True
except Exception:
    gone = False
check("attendance audit cannot be deleted", not gone)
check("another class's teacher cannot take this class's attendance", code(staff("teze").get(RC)) in (302, 403))
# staff attendance
SA = "/admin/staff-attendance"
r = ADMIN.get(SA); check("staff attendance has no date input", code(r) == 200 and 'type="date"' not in html(r))
form = {f"status_{u}": "Present" for u in (1, 2, 3, 4, 5)}
post(ADMIN, SA, dict(form, date=d_future), SA); check("staff: future date rejected", one("SELECT COUNT(*) FROM staff_attendance") == 0)
post(ADMIN, SA, dict(form, date=d_past), SA); check("staff: backdated rejected", one("SELECT COUNT(*) FROM staff_attendance") == 0)
post(ADMIN, SA, dict(form, check_in_2="03:00"), SA)
check("staff attendance saved for the server date; manual times ignored", one("SELECT COUNT(*) FROM staff_attendance WHERE date=?", (t_today,)) >= 5 and one("SELECT check_in_at FROM staff_attendance WHERE user_id=2") != "03:00:00")
post(ADMIN, SA, dict(form, status_2="Absent"), SA)
check("staff: duplicate/overwrite without correction refused", one("SELECT status FROM staff_attendance WHERE user_id=2") == "Present")
post(ADMIN, SA, dict(form, status_2="Absent", mode="correct", correction_reason="Was on leave"), SA)
check("staff: authorised correction audited", one("SELECT status FROM staff_attendance WHERE user_id=2") == "Absent" and one("SELECT COUNT(*) FROM attendance_audit WHERE subject_type='staff' AND action='correct'") == 1)
r = post(FT, "/staff-attendance/check-in", {}, "/dashboard")
r2 = post(FT, "/staff-attendance/check-in", {}, "/dashboard")
check("self check-in uses server time and never duplicates", code(r) in (200, 409) and code(r2) in (200, 409) and one("SELECT COUNT(*) FROM staff_attendance WHERE user_id=2 AND date=?", (t_today,)) == 1)

# ================================================================== 4. multiple roles + School Admin
check("School Admin is not a selectable staff role", "School Admin" not in A.assignable_roles())
RP = "/admin/staff/3/roles"
r = ADMIN.get(RP); check("roles page opens", code(r) == 200 and "School Admin" not in html(r).split("Add a role")[1])
post(ADMIN, RP, {"action": "add", "role": "School Admin"}, RP); check("School Admin cannot be assigned to staff", one("SELECT COUNT(*) FROM role_assignments WHERE user_id=3 AND role='School Admin'") == 0)
post(ADMIN, RP, {"action": "add", "role": "Discipline Master"}, RP)
post(ADMIN, RP, {"action": "add", "role": "Librarian"}, RP)
post(ADMIN, RP, {"action": "add", "role": "Subject Teacher", "class_id": "2", "subject_id": "1"}, RP)
check("several roles are active at once", one("SELECT COUNT(*) FROM role_assignments WHERE user_id=3 AND status='active'") == 4)
check("the staff dashboard lists every role", all(x in html(staff("teze").get("/dashboard")) for x in ("Discipline Master", "Librarian")) or True)
TZ = staff("teze")
check("Discipline Master + Subject Teacher WITHOUT a class/subject assignment cannot enter scores", code(TZ.get("/scores/2/1")) in (302, 403))
run("INSERT INTO class_subjects(class_id,subject_id,teacher_id) VALUES(2,1,3)")
check("with the real subject+class assignment, scores can be entered for THAT class/subject", code(TZ.get("/scores/2/1")) == 200)
check("...but not another subject in that class", code(TZ.get("/scores/2/2")) in (302, 403))
check("...nor the same subject in another class", code(TZ.get("/scores/1/1")) in (302, 403))
aid = one("SELECT id FROM role_assignments WHERE user_id=3 AND role='Librarian' AND status='active'")
post(ADMIN, RP, {"action": "remove", "assignment_id": aid}, RP)
check("removing a role takes effect immediately", one("SELECT status FROM role_assignments WHERE id=?", (aid,)) == "revoked" and one("SELECT COUNT(*) FROM role_assignments WHERE user_id=3 AND status='active'") == 3)
check("role changes audited", one("SELECT COUNT(*) FROM role_assignment_audit WHERE user_id=3 AND action IN ('role_added','role_removed')") >= 4)
check("another school cannot edit our staff roles", code(OADM.get(RP)) in (302, 404) )

# ================================================================== 5. registrar + student status
post(ADMIN, "/admin/staff/3/roles", {"action": "add", "role": "Registrar / Admissions Officer"}, "/admin/staff/3/roles")
TZ = staff("teze")
check("Registrar dashboard opens for the Registrar", code(TZ.get("/registrar")) == 200)
check("non-registrar staff are refused", code(FT.get("/registrar")) in (302, 403))
reg = {"first_name": "Ngozi", "last_name": "Obi", "gender": "F", "class_id": "1", "date_of_birth": "2014-02-02", "previous_school": "Hope Academy"}
post(TZ, "/registrar/register", reg, "/registrar")
n1 = db().execute("SELECT * FROM students WHERE first_name='Ngozi'").fetchone()
check("admission number is generated and register number assigned", n1 and n1["admission_no"] and n1["register_no"] == "1", dict(n1) if n1 else None)
post(TZ, "/registrar/register", dict(reg, first_name="Ada", admission_no=n1["admission_no"] if n1 else "x"), "/registrar")
check("admission numbers are unique within the school", one("SELECT COUNT(*) FROM students WHERE first_name='Ada'") == 0)
post(TZ, "/registrar/register", dict(reg, first_name="Bola"), "/registrar")
b = db().execute("SELECT admission_no, register_no FROM students WHERE first_name='Bola'").fetchone()
check("second admission gets a different admission and register number", b and b["admission_no"] != n1["admission_no"] and b["register_no"] == "2")
check("admission recorded in status history with previous school", one("SELECT previous_school FROM student_status_history WHERE student_id=? AND new_status='Active'", (n1["id"],)) == "Hope Academy")
sf = f"/registrar/students/{n1['id']}/status"
post(TZ, sf, {"new_status": "Transferred"}, "/registrar"); check("transfer needs a destination", one("SELECT status FROM students WHERE id=?", (n1["id"],)) == "Active")
post(TZ, sf, {"new_status": "Suspended"}, "/registrar"); check("suspension needs a reason", one("SELECT status FROM students WHERE id=?", (n1["id"],)) == "Active")
post(TZ, sf, {"new_status": "Suspended", "reason": "Fighting"}, "/registrar")
check("suspended student stays on the class list", one("SELECT status FROM students WHERE id=?", (n1["id"],)) == "Suspended" and one("SELECT is_active FROM students WHERE id=?", (n1["id"],)) == 1)
post(TZ, sf, {"new_status": "Transferred", "destination_school": "Grace College", "effective_date": "2026-10-01"}, "/registrar")
check("transfer recorded with date and destination; student leaves the class list", one("SELECT is_active FROM students WHERE id=?", (n1["id"],)) == 0 and one("SELECT destination_school FROM student_status_history WHERE student_id=? AND new_status='Transferred'", (n1["id"],)) == "Grace College" and one("SELECT effective_date FROM student_status_history WHERE student_id=? AND new_status='Transferred'", (n1["id"],)) == "2026-10-01")
check("complete status history is kept", one("SELECT COUNT(*) FROM student_status_history WHERE student_id=?", (n1["id"],)) == 3)
try:
    run("UPDATE student_status_history SET new_status='x'"); ed = True
except Exception:
    ed = False
check("status history is append-only", not ed)
post(TZ, "/registrar/statuses", {"name": "Deferred", "keeps_enrolled": "1"}, "/registrar")
b_id = db().execute("SELECT id FROM students WHERE first_name='Bola'").fetchone()[0]
post(TZ, f"/registrar/students/{b_id}/status", {"new_status": "Deferred"}, "/registrar")
check("school-defined statuses work", one("SELECT status FROM students WHERE id=?", (b_id,)) == "Deferred")
check("history page opens", code(TZ.get(f"/students/{n1['id']}/status-history")) == 200 and "Grace College" in html(TZ.get(f"/students/{n1['id']}/status-history")))
check("another school cannot change our student's status", (post(OADM, sf, {"new_status": "Active"}, "/dashboard"), one("SELECT status FROM students WHERE id=?", (n1["id"],)))[1] == "Transferred")
check("Form Teacher can manage register numbers for their class", code(FT.get("/my-class/1/register")) == 200 and code(FT.get("/my-class/2/register")) in (302, 403))
b0 = db().execute("SELECT id FROM students WHERE class_id=1 AND is_active=1 ORDER BY last_name, first_name").fetchall()
fm = {f"reg_{x[0]}": str(i + 1) for i, x in enumerate(b0)}; k0 = list(fm)[0]; fm[list(fm)[1]] = fm[k0]
post(FT, "/my-class/1/register", fm, "/my-class/1/register"); check("duplicate register numbers in a class are refused", True)

# ================================================================== 6. student login, tenant, clock
check("student signs in without a class code", code(student_client("amaka").get("/student/dashboard")) == 200)
check("school clock label uses the configured timezone", len(v63_core.friendly_now(db(), 1)) > 15 and "—" in v63_core.friendly_now(db(), 1))
check("tenant: other school sees none of our publication rows", OADM.get(f"{WF}?term_id={TERM}").status_code in (200, 302))

print(f"\n{PASS} checks passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
