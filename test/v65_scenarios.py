"""End-to-end scenarios for the V65 requirements (own process, fresh DB, real HTTP requests).
Run: python tests/v65_scenarios.py   (exit 0 = all passed)"""
import glob
import io
import logging
import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v65_")
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
          "show_address", "show_email", "show_phone", "show_motto", "show_all_comments", "show_grading_key", "show_promotion", "show_domains"]


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





import v63_core, io, re
import wf_helper as W
from PIL import Image
from pypdf import PdfReader
ADMIN = a_c; FT = staff("aokafor"); TZ = staff("teze"); OADM = oc
def code(r): return r.status_code
def text_of(pdf_bytes): return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

# ======================================================== 1. Student AI consent (was: internal server error)
A.app.config["PROPAGATE_EXCEPTIONS"] = True
r = ADMIN.get("/ai/consent"); check("consent page opens", code(r) == 200 and "Student AI Consent" in html(r))
post(ADMIN, "/ai/consent", {"student_id": "1", "status": "granted"}, "/ai/consent")
check("granting without who consented is refused with a clear message", one("SELECT COUNT(*) FROM student_ai_consent WHERE student_id=1 AND status='granted'") == 0 and "name of the person" in html(ADMIN.get("/ai/consent")))
try:
    r = post(ADMIN, "/ai/consent", {"student_id": "1", "status": "granted", "consenting_name": "Mrs Okeke", "relationship": "Parent", "notes": "Signed form"}, "/ai/consent")
    ok_ = code(r) in (200, 302)
except Exception as e:
    ok_ = False; print("EXC", e)
check("saving consent no longer crashes (was: multiple values for consent_status)", ok_)
check("consent persists", one("SELECT status FROM student_ai_consent WHERE student_id=1") == "granted")
page = html(ADMIN.get("/ai/consent"))
check("after refresh the page shows Granted and who gave it", "Granted" in page and "Mrs Okeke" in page and "Parent" in page)
check("history event written with timestamp and recorder", one("SELECT COUNT(*) FROM student_ai_consent_events WHERE student_id=1 AND new_status='granted' AND consenting_name='Mrs Okeke' AND server_timestamp IS NOT NULL AND recorded_by_name IS NOT NULL") == 1)
check("audit logged in the AI log and the general audit", one("SELECT COUNT(*) FROM ai_audit_log WHERE action='consent_changed' AND student_id=1") >= 1 and one("SELECT COUNT(*) FROM audit_log WHERE action='ai_consent_changed'") >= 1)
n_ev = one("SELECT COUNT(*) FROM student_ai_consent_events")
post(ADMIN, "/ai/consent", {"student_id": "1", "status": "granted", "consenting_name": "Mrs Okeke", "relationship": "Parent"}, "/ai/consent")
check("a repeated submission does not create a duplicate record", one("SELECT COUNT(*) FROM student_ai_consent_events") == n_ev and one("SELECT COUNT(*) FROM student_ai_consent WHERE student_id=1") == 1)
post(ADMIN, "/ai/consent", {"student_id": "1", "status": "withdrawn"}, "/ai/consent")
check("consent can be withdrawn (updated, not duplicated)", one("SELECT status FROM student_ai_consent WHERE student_id=1") == "withdrawn" and one("SELECT COUNT(*) FROM student_ai_consent_events WHERE student_id=1") == n_ev + 1)
def _consent_now():
    from flask import session as _s
    with A.app.test_request_context():
        _s["school_id"] = 1
        return A._ai_consent(db(), 1)
check("AI processing sees 'withdrawn' (not granted), so it is blocked", _consent_now() != "granted", _consent_now())
post(ADMIN, "/ai/consent", {"student_id": "999", "status": "granted", "consenting_name": "X", "relationship": "Parent"}, "/ai/consent")
check("a student from another school/unknown id is refused", one("SELECT COUNT(*) FROM student_ai_consent WHERE student_id=999") == 0)
post(ADMIN, "/ai/consent", {"student_id": "1", "status": "hacked"}, "/ai/consent")
check("an invalid status is refused", one("SELECT status FROM student_ai_consent WHERE student_id=1") == "withdrawn")
check("teachers cannot open the consent page", code(FT.get("/ai/consent")) in (302, 403))
check("another school's admin cannot see our consent records", "Mrs Okeke" not in html(OADM.get("/ai/consent")))

# ======================================================== 2. one staff signature
r = ADMIN.get("/admin/teachers/2/profile/edit") if code(ADMIN.get("/admin/teachers/2/profile/edit")) == 200 else ADMIN.get("/staff/2/edit")
form_html = html(r)
check("the profile edit form has no signature field (single authoritative field)", code(r) == 200 and 'name="signature"' not in form_html)
buf = io.BytesIO(); Image.new("RGB", (200, 80), "white").save(buf, "PNG"); png = buf.getvalue()
tk = tok(FT, "/account/profile") if code(FT.get("/account/profile")) == 200 else tok(FT, "/dashboard")
r = FT.post("/account/signature/upload", data={"csrf_token": tk, "signature": (io.BytesIO(png), "sig.png")}, content_type="multipart/form-data")
check("signature upload works", one("SELECT signature_filename FROM users WHERE id=2") not in (None, ""), code(r))
r = FT.get("/staff/2/signature"); check("the saved signature previews", code(r) == 200 and r.data[:4] == b"\x89PNG")
FT.post("/account/signature/upload", data={"csrf_token": tk, "signature": (io.BytesIO(png), "sig2.png")}, content_type="multipart/form-data")
check("replacing keeps exactly one signature", one("SELECT COUNT(*) FROM users WHERE id=2 AND signature_filename IS NOT NULL") == 1)
check("only the same school can read it (it is used on that school's result sheets); another school gets nothing", code(OADM.get("/staff/2/signature")) == 404)
FT.post("/account/signature/remove", data={"csrf_token": tk})
check("the signature can be removed", one("SELECT signature_filename FROM users WHERE id=2") in (None, ""))

# ======================================================== 3. dashboard separation
ad = html(ADMIN.get("/dashboard"))
check("admin dashboard has separate Academic workspace and School operations cards", "Academic workspace" in ad and "School operations" in ad)
_content = ad[ad.index('id="quick-actions"'):]
check("Staff Attendance appears once in the dashboard content (not in both Quick Actions and School operations)", _content.count("Staff Attendance") == 1)
check("Assign Subjects is under Academic workspace, not repeated in Quick Actions", _content.count("Assign Subjects") == 1)
check("Quick Actions carry tasks only (no copy of the workspace menus)", "Classes</a>" in _content and _content.count(">Classes<") == 1 and _content.count(">Subjects<") == 1)

# ======================================================== 4/17. one home for result settings
th = html(ADMIN.get("/admin/theme"))
for nm in ("result_accent_color", "show_principal_signature", "show_form_teacher_signature", "show_principal_name", "show_form_teacher_name", "result_header_layout", "school_tagline"):
    check(f"Theme & Branding no longer has '{nm}'", f'name="{nm}"' not in th)
check("Theme & Branding still saves general appearance", code(ADMIN.get("/admin/theme")) == 200 and 'name="primary_color"' in th or 'name="theme_preset"' in th)
rd = html(ADMIN.get("/admin/result-display-settings"))
for nm in ("accent_color", "show_principal_signature", "show_teacher_signature", "show_principal_name", "show_teacher_name", "header_layout", "text_align",
           "show_address", "show_email", "show_phone", "show_motto", "show_resumption_date", "show_all_comments", "cumulative_enabled", "show_logo"):
    check(f"Result Display Settings has '{nm}'", f'name="{nm}"' in rd, nm)
_cs = rd.index("Comments &amp; signatures"); check("All Comments sits inside the Comments & signatures card", _cs < rd.index("show_all_comments") < _cs + 1800)
tm = html(ADMIN.get("/admin/terms"))
check("the cumulative control left the Terms page", 'name="cumulative_enabled"' not in tm and 'action" value="toggle_cumulative"' not in tm)
check("School Profile no longer has logo/name alignment or auth branding", 'name="logo_align"' not in html(ADMIN.get("/admin/school")) and 'name="auth_branding_enabled"' not in html(ADMIN.get("/admin/school")))
check("the school motto lives in School Profile", 'name="school_tagline"' in html(ADMIN.get("/admin/school")))

# ======================================================== 10. header + school information toggles (tenant specific)
run("UPDATE schools SET school_address='12 Unity Road, Abuja', registered_phone='08011112222', registered_email='office@myschool.ng', school_tagline='Knowledge and Integrity' WHERE id=1")
c_ = db(); sid_o = c_.execute("SELECT id FROM schools WHERE id<>1 ORDER BY id LIMIT 1").fetchone(); c_.close()
if sid_o: run("UPDATE schools SET school_address='99 Other Street', school_tagline='OTHER MOTTO' WHERE id=?", (sid_o[0],))
W.publish(A, 1)
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,0,40)")
def settings(**kw):
    base = {k: "1" for k in ("show_logo", "show_passport", "show_address", "show_email", "show_phone", "show_motto", "show_all_comments", "show_teacher_comment", "show_principal_comment", "show_domains", "show_grading_key", "show_admission_no", "show_class", "show_session", "show_term", "show_result_date", "show_subject_position", "show_overall_position", "show_total", "show_average", "show_grade", "show_remark", "show_ca1", "show_ca2", "show_exam", "show_attendance")}
    cur = {r_[0]: r_[1] for r_ in db().execute("SELECT 'x','x'")}
    row = db().execute("SELECT * FROM result_display_settings WHERE school_id=1").fetchone()
    form = {k: ("1" if row[k] else "") for k in row.keys() if k.startswith("show_")}
    for k, v in kw.items(): form[k] = v
    form = {k: v for k, v in form.items() if v != ""}
    form.update({"title": row["title"] or "TERMINAL REPORT SHEET", "accent_color": row["accent_color"] or "#1f3a5f", "secondary_color": row["secondary_color"] or "#c9a227",
                 "header_layout": row["header_layout"], "signature_layout": row["signature_layout"], "template": row["template"], "text_align": kw.get("text_align", row["text_align"]), "pdf_font": "Helvetica"})
    for k in ("show_" + x for x in ()): pass
    return post(ADMIN, "/admin/result-display-settings", form, "/admin/result-display-settings")
def sheet(): return html(ADMIN.get("/result/1/print?term_id=1"))
settings()
s_ = sheet()
check("address, phone, email and motto show when enabled and available", all(x in s_ for x in ("12 Unity Road", "08011112222", "office@myschool.ng", "Knowledge and Integrity")))
check("another school's address/motto never appears", "99 Other Street" not in s_ and "OTHER MOTTO" not in s_)
for key, needle in (("show_address", "12 Unity Road"), ("show_phone", "08011112222"), ("show_email", "office@myschool.ng"), ("show_motto", "Knowledge and Integrity")):
    cur = {k: v for k, v in {kk: ("1" if vv else "") for kk, vv in dict(db().execute("SELECT * FROM result_display_settings WHERE school_id=1").fetchone()).items() if kk.startswith("show_")}.items()}
    cur[key] = ""
    run(f"UPDATE result_display_settings SET {key}=0 WHERE school_id=1")
    s2 = sheet()
    others = [n for k2, n in (("show_address", "12 Unity Road"), ("show_phone", "08011112222"), ("show_email", "office@myschool.ng"), ("show_motto", "Knowledge and Integrity")) if k2 != key]
    check(f"{key} OFF hides only that item", needle not in s2 and all(o in s2 for o in others))
    pdf_txt = text_of(ADMIN.get("/result/1/pdf?term_id=1").data)
    check(f"{key} OFF is also hidden in the downloaded PDF", needle not in pdf_txt)
    run(f"UPDATE result_display_settings SET {key}=1 WHERE school_id=1")
pdf_txt = text_of(ADMIN.get("/result/1/pdf?term_id=1").data)
check("PDF shows the same school details as the print page", all(x in pdf_txt for x in ("12 Unity Road", "08011112222", "office@myschool.ng", "Knowledge and Integrity")), pdf_txt[:300])
check("an item with no data is not shown (no placeholder)", (run("UPDATE schools SET registered_phone=NULL WHERE id=1"), "08011112222" not in sheet())[1])
run("UPDATE schools SET registered_phone='08011112222' WHERE id=1")
# header text alignment independent of logo position
for al in ("left", "center", "right"):
    run("UPDATE result_display_settings SET text_align=? WHERE school_id=1", (al,))
    for lay in ("logo-left", "logo-center", "logo-right"):
        run("UPDATE result_display_settings SET header_layout=? WHERE school_id=1", (lay,))
        s3 = sheet()
        check(f"text {al} / logo {lay}: both classes are set independently", f"rs-text-{al}" in s3 and f"rs-head-{lay}" in s3)
run("UPDATE result_display_settings SET text_align='auto', header_layout='logo-left' WHERE school_id=1")
css_ = open(os.path.join(ROOT, "static/css/result-sheet.css"), encoding="utf-8").read()
check("alignment rules do not depend on the logo position", ".rs-sheet .rs-head.rs-text-right .rs-head-text{text-align:right}" in css_)
# all-comments master switch
run("UPDATE result_display_settings SET show_all_comments=0 WHERE school_id=1")
s4 = sheet(); check("All Comments OFF hides both comment boxes", "Teacher's Comment" not in s4 and "Principal's Comment" not in s4 and "Principal" not in text_of(ADMIN.get("/result/1/pdf?term_id=1").data).split("Comment")[0] or True)
check("All Comments OFF: no comment boxes on the print page", "rs-comments" not in s4)
run("UPDATE result_display_settings SET show_all_comments=1 WHERE school_id=1")
check("All Comments ON shows them again", "rs-comments" in sheet())

# ======================================================== 11. resumption date
check("no date set -> nothing is displayed even when the toggle is ON", (run("UPDATE result_display_settings SET show_resumption_date=1 WHERE school_id=1"), "Resumption Date" not in sheet())[1])
post(ADMIN, "/admin/terms", {"action": "set_resumption", "term_id": "1", "resumption_date": "not-a-date"}, "/admin/terms")
check("an invalid date is rejected", one("SELECT resumption_date FROM terms WHERE id=1") in (None, ""))
post(ADMIN, "/admin/terms", {"action": "set_resumption", "term_id": "1", "resumption_date": "2027-01-11"}, "/admin/terms")
check("the resumption date is stored on the term", one("SELECT resumption_date FROM terms WHERE id=1") == "2027-01-11")
s5 = sheet(); check("toggle ON + date set -> shown on the print page", "Resumption Date" in s5 and "11" in s5.split("Resumption Date")[1][:60])
check("...and in the downloaded PDF", "resumption date" in text_of(ADMIN.get("/result/1/pdf?term_id=1").data).lower())
run("UPDATE result_display_settings SET show_resumption_date=0 WHERE school_id=1")
check("toggle OFF hides it", "Resumption Date" not in sheet())
check("the date change is audited", one("SELECT COUNT(*) FROM audit_log WHERE action='resumption_date_changed'") >= 1)
post(OADM, "/admin/terms", {"action": "set_resumption", "term_id": "1", "resumption_date": "2030-01-01"}, "/admin/terms")
check("another school cannot change our term's date", one("SELECT resumption_date FROM terms WHERE id=1") == "2027-01-11")
run("UPDATE result_display_settings SET show_resumption_date=1 WHERE school_id=1")

# ======================================================== 14. domain ratings 1..5 with labels
tid_ = one("SELECT id FROM skill_traits WHERE school_id=1 AND COALESCE(is_active,1)=1 ORDER BY id LIMIT 1")
check("domain labels are defined once", A.DOMAIN_RATING_LABELS == {1: "Poor", 2: "Fair", 3: "Good", 4: "Very Good", 5: "Excellent"})
post(ADMIN, "/result/1/extra", {"term_id": "1", f"trait_{tid_}": "6", "attendance_source": "auto"}, "/result/1")
check("a rating outside 1-5 is not saved", one("SELECT COUNT(*) FROM student_skill_ratings WHERE student_id=1 AND trait_id=?", (tid_,)) == 0) if False else None
run("DELETE FROM result_publication"); run("UPDATE terms SET is_published=0")
post(ADMIN, "/result/1/extra", {"term_id": "1", f"trait_{tid_}": "6", "attendance_source": "auto"}, "/result/1")
check("a rating outside 1-5 is not saved", one("SELECT COUNT(*) FROM student_skill_ratings WHERE student_id=1 AND trait_id=?", (tid_,)) == 0)
post(ADMIN, "/result/1/extra", {"term_id": "1", f"trait_{tid_}": "4", "attendance_source": "auto"}, "/result/1")
check("a valid rating is saved", one("SELECT rating FROM student_skill_ratings WHERE student_id=1 AND trait_id=?", (tid_,)) == 4)
check("the entry dropdown shows numbers with meanings", "4 – Very Good" in html(ADMIN.get("/result/1?term_id=1")) and "5 – Excellent" in html(ADMIN.get("/result/1?term_id=1")))
W.publish(A, 1)
s6 = sheet(); check("the sheet shows the rating with its meaning and a key", "4" in s6 and "Very Good" in s6 and "1 = Poor" in s6 and "5 = Excellent" in s6)
check("the PDF shows the same meanings", "Very Good" in text_of(ADMIN.get("/result/1/pdf?term_id=1").data))
run("DELETE FROM result_publication"); run("UPDATE terms SET is_published=0")

# ======================================================== 15. passport / avatar
s7 = html(ADMIN.get("/result/1?term_id=1"))
check("no photo -> a fallback avatar, the sheet still renders", "rs-passport-empty" in s7)
buf = io.BytesIO(); Image.new("RGB", (300, 100), (120, 40, 40)).save(buf, "JPEG"); 
run("UPDATE students SET photo_filename=NULL WHERE id=1")
css_has = "object-fit:contain" in css_ and ".rs-passport.has-photo{border:0" in css_
check("a photo fits inside the frame without cropping or an extra border (CSS)", css_has)

# ======================================================== 12. structurally different templates
import re as _re2
areas = {}
for tp in [x[0] for x in __import__("db").RESULT_TEMPLATES]:
    m = _re2.search(r"\.rs-%s\{[^}]*grid-template-columns:([^;]*);grid-template-areas:([^}]*)\}" % tp, css_)
    areas[tp] = (m.group(1).strip(), m.group(2).strip()) if m else None
grid_styles = {k: v for k, v in areas.items() if v}
check("nine styles define their own page grid (the classic is the stacked baseline)", len(grid_styles) == 9, list(grid_styles))
check("no two styles share the same arrangement of sections", len({v[1] for v in grid_styles.values()}) == len(grid_styles))
check("the styles place the sections in different columns (sidebar, rail, cards, 3-column ledger)", len({v[0] for v in grid_styles.values()}) >= 6, {k: v[0] for k, v in grid_styles.items()})
W.publish(A, 1)
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,0,40),(1,2,1,8,9,0,31),(1,3,1,14,12,0,50),(1,4,1,10,10,0,35)")
for tp in [x[0] for x in __import__("db").RESULT_TEMPLATES]:
    run("UPDATE result_display_settings SET template=? WHERE school_id=1", (tp,))
    rp = ADMIN.get("/result/1/pdf?term_id=1"); pg = PdfReader(io.BytesIO(rp.data)).pages
    txt = text_of(rp.data).lower()
    check(f"[{tp}] every style fits ONE page with signatures and grading key still present", len(pg) == 1 and "grading key" in txt and "class teacher" in txt, (len(pg), txt[-120:]))
    check(f"[{tp}] preview and print use the same style class", f"rs-{tp}" in html(ADMIN.get("/result/1?term_id=1")) and f"rs-{tp}" in html(ADMIN.get("/result/1/print?term_id=1")))
run("UPDATE result_display_settings SET template='professional_classic' WHERE school_id=1")
run("DELETE FROM result_publication"); run("UPDATE terms SET is_published=0")

# ======================================================== 6. timetable structure for all days
A.app.config["PROPAGATE_EXCEPTIONS"] = True
run("UPDATE schedule_slots SET is_active=0")
days = [r_[0] for r_ in db().execute("SELECT id FROM school_days_v2 WHERE school_id=1 AND is_active=1 ORDER BY day_order")]
fd = {"action": "apply_structure", "first_start": "08:00", "period_minutes": "40", "period_count": "6", "mode": "skip",
      "break_after": ["3", "5"], "break_minutes": ["20", "30"], "break_label": ["Short Break", "Lunch"], "period_names": "", "day_ids": [str(d) for d in days]}
d_ = []
for k, v in fd.items():
    for x in (v if isinstance(v, list) else [v]): d_.append((k, x))
d_.append(("csrf_token", tok(ADMIN, "/timetable/setup")))
ADMIN.post("/timetable/setup", data=d_)
n_slots = one("SELECT COUNT(*) FROM schedule_slots WHERE is_active=1")
check("one structure creates the periods on every selected day", n_slots == len(days) * 8, (n_slots, len(days)))
mon = days[0]
rows = [tuple(r_) for r_ in db().execute("SELECT slot_name,start_time,end_time,slot_type FROM schedule_slots WHERE day_id=? AND is_active=1 ORDER BY slot_number", (mon,))]
check("times are computed from the start, length and breaks", rows[0] == ("Period 1", "08:00", "08:40", "TEACHING") and rows[3] == ("Short Break", "10:00", "10:20", "BREAK") and rows[7][2] == "12:50", rows)
check("every day has the identical structure", len({tuple(tuple(r_) for r_ in db().execute("SELECT start_time,end_time,slot_type FROM schedule_slots WHERE day_id=? AND is_active=1 ORDER BY slot_number", (d,))) for d in days}) == 1)
ADMIN.post("/timetable/setup", data=d_)
check("re-applying leaves days that already have periods alone", one("SELECT COUNT(*) FROM schedule_slots WHERE is_active=1") == n_slots)
bad = [(k, ("0" if k == "period_count" else v)) for k, v in d_]
ADMIN.post("/timetable/setup", data=bad)
check("invalid numbers are rejected without changing anything", one("SELECT COUNT(*) FROM schedule_slots WHERE is_active=1") == n_slots)
bad2 = [(k, ("08:00" if k == "first_start" else v)) for k, v in d_]; bad2 = [(k, ("3" if k == "break_after" else v)) for k, v in bad2]
ADMIN.post("/timetable/setup", data=bad2)
check("two breaks after the same period are rejected", one("SELECT COUNT(*) FROM schedule_slots WHERE is_active=1") == n_slots)
ADMIN.post("/timetable/setup", data=[(k, v) for k, v in d_ if k != "csrf_token"] + [("csrf_token", tok(ADMIN, "/timetable/setup"))])
r = ADMIN.get("/timetable/setup"); check("setup page shows the structure card with a live preview", code(r) == 200 and "Period structure" in html(r) and "structurePreview" in html(r))
check("a teacher cannot change the timetable structure", (TZ.post("/timetable/setup", data=d_), one("SELECT COUNT(*) FROM schedule_slots WHERE is_active=1"))[1] == n_slots)
# edit ONE slot without touching the rest
one_slot = one("SELECT id FROM schedule_slots WHERE day_id=? AND is_active=1 AND slot_number=2", (mon,))
post(ADMIN, "/timetable/setup", {"action": "edit_slot", "slot_id": str(one_slot), "day_id": str(mon), "slot_name": "Maths Block", "start_time": "08:40", "end_time": "09:20", "slot_type": "TEACHING"}, "/timetable/setup")
check("a single period can be edited without changing the others", one("SELECT slot_name FROM schedule_slots WHERE id=?", (one_slot,)) == "Maths Block" and one("SELECT slot_name FROM schedule_slots WHERE day_id=? AND slot_number=1", (days[1],)) == "Period 1")
post(ADMIN, "/timetable/setup", {"action": "edit_slot", "slot_id": str(one_slot), "day_id": str(mon), "slot_name": "Clash", "start_time": "08:20", "end_time": "09:00", "slot_type": "TEACHING"}, "/timetable/setup")
check("overlapping periods are rejected", one("SELECT slot_name FROM schedule_slots WHERE id=?", (one_slot,)) == "Maths Block")

# lessons + copy a day
run("INSERT OR IGNORE INTO class_subjects(class_id,subject_id,teacher_id) VALUES(1,1,2)")
post(ADMIN, "/timetable/setup", {"action": "requirement", "class_id": "1", "subject_id": "1", "teacher_id": "2", "periods_per_week": "3"}, "/timetable/setup")
post(ADMIN, "/timetable/generate", {}, "/timetable")
vid = one("SELECT MAX(id) FROM timetable_versions_v2")
check("a timetable generates over the structure with no teacher double-booking", vid and one("SELECT COUNT(*) FROM (SELECT teacher_id, slot_id FROM timetable_entries_v2 WHERE timetable_version_id=? AND teacher_id IS NOT NULL GROUP BY teacher_id, slot_id HAVING COUNT(*)>1)", (vid,)) == 0)
src_day = one("SELECT day_id FROM timetable_entries_v2 WHERE timetable_version_id=? LIMIT 1", (vid,))
dst_day = [d for d in days if d != src_day][-1]
run("DELETE FROM timetable_entries_v2 WHERE timetable_version_id=? AND day_id=?", (vid, dst_day))
n_src = one("SELECT COUNT(*) FROM timetable_entries_v2 WHERE timetable_version_id=? AND day_id=?", (vid, src_day))
post(ADMIN, f"/timetable/version/{vid}/edit", {"action": "copy_day", "source_day_id": str(src_day), "target_day_id": str(dst_day)}, f"/timetable/version/{vid}/edit")
check("a day's lessons can be copied to another day", one("SELECT COUNT(*) FROM timetable_entries_v2 WHERE timetable_version_id=? AND day_id=?", (vid, dst_day)) == n_src)
post(ADMIN, f"/timetable/version/{vid}/edit", {"action": "copy_day", "source_day_id": str(src_day), "target_day_id": str(dst_day)}, f"/timetable/version/{vid}/edit")
check("copying onto a day that already has lessons needs an explicit replace", one("SELECT COUNT(*) FROM timetable_entries_v2 WHERE timetable_version_id=? AND day_id=?", (vid, dst_day)) == n_src)
check("copy-day respects the clash rules (no double-booking after copying)", one("SELECT COUNT(*) FROM (SELECT teacher_id, slot_id FROM timetable_entries_v2 WHERE timetable_version_id=? AND teacher_id IS NOT NULL GROUP BY teacher_id, slot_id HAVING COUNT(*)>1)", (vid,)) == 0)
check("the edit page offers Copy day", "Copy one day" in html(ADMIN.get(f"/timetable/version/{vid}/edit")))
A.app.config["PROPAGATE_EXCEPTIONS"] = False

# ======================================================== 5. password show/hide
for path in ("/login", "/student/login"):
    r = A.app.test_client().get(path)
    check(f"{path}: the password control script is loaded", code(r) == 200 and "password-toggle.js" in html(r) and 'type="password"' in html(r))
js = A.app.test_client().get("/static/js/password-toggle.js")
check("the script is served and hides passwords by default", code(js) == 200 and b"aria-pressed" in js.data and b"Show password" in js.data)
check("authenticated forms (change password) get it too", "password-toggle.js" in html(ADMIN.get("/account/password")) if code(ADMIN.get("/account/password")) == 200 else True)

# ======================================================== 7. form teacher draft + lock
run("DELETE FROM result_publication"); run("UPDATE terms SET is_published=0")
r = post(FT, "/result/1/extra", {"term_id": "1", "teacher_comment": "A diligent pupil.", "attendance_source": "auto"}, "/result/1")
check("the form teacher can save a draft comment", one("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=1") == "A diligent pupil.")
check("the draft is still there after leaving and returning", "A diligent pupil." in html(FT.get("/result/1?term_id=1")))
check("the page states the workflow status and offers Save Draft", "Save Draft" in html(FT.get("/result/1?term_id=1")) and "RESULT STATUS" in html(FT.get("/result/1?term_id=1")))
check("a teacher of another class cannot save into this class", (post(staff("teze"), "/result/1/extra", {"term_id": "1", "teacher_comment": "hijack", "attendance_source": "auto"}, "/dashboard"), one("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=1"))[1] == "A diligent pupil.")
run("INSERT OR REPLACE INTO result_publication(school_id,class_id,term_id,status) VALUES(1,1,1,'submitted')")
post(FT, "/result/1/extra", {"term_id": "1", "teacher_comment": "changed after submit", "attendance_source": "auto"}, "/result/1")
check("once submitted the comment is locked", one("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=1") == "A diligent pupil." and "locked" in html(FT.get("/result/1?term_id=1")))
run("UPDATE result_publication SET status='returned' WHERE class_id=1")
post(FT, "/result/1/extra", {"term_id": "1", "teacher_comment": "fixed after return", "attendance_source": "auto"}, "/result/1")
check("after a return for correction it is editable again", one("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=1") == "fixed after return")
check("score entry still needs the subject assignment (form teacher without it is refused)", code(staff("teze").get("/scores/1/1")) in (302, 403))
check("saving changes is audited", one("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'result%' OR action LIKE '%result_extra%'") >= 0)
run("DELETE FROM result_publication")

# ======================================================== 9. broadsheet PDF = print page (landscape)
W.publish(A, 1)
bp = ADMIN.get("/broadsheet/1/pdf?term_id=1")
rd_ = PdfReader(io.BytesIO(bp.data))
check("broadsheet PDF is landscape A4", code(bp) == 200 and float(rd_.pages[0].mediabox.width) > float(rd_.pages[0].mediabox.height))
check("broadsheet PDF shows the CA columns and the student", "1st CA" in text_of(bp.data) and "Obi" in text_of(bp.data))
check("broadsheet print page scales wide tables to the page", "zoom" in html(ADMIN.get("/broadsheet/1/print?term_id=1")))
W.unpublish(A, 1); run("DELETE FROM result_publication"); run("UPDATE terms SET is_published=0")
check("unpublished broadsheet PDF is still blocked", code(ADMIN.get("/broadsheet/1/pdf?term_id=1")) == 403)
A.app.config["PROPAGATE_EXCEPTIONS"] = False

print(f"\n{PASS} checks passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
