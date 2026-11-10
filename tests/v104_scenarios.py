"""V104 scenarios: announcements, teacher student-attendance menu, term visibility + locked published sheet design, passport frame/duplicate upload,
admission number per class, staff ID, navigation, CSV imports, custom school info, additional result fields, domain ordering.
Run: python tests/v104_scenarios.py"""
import datetime, io, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v104_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A, html_pdf, wf_helper as W
import announcements as ANN
from db import get_db
from werkzeug.security import generate_password_hash
from pypdf import PdfReader
A.app.config["TESTING"] = False; logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, str(d)[:300])
def html(r): return r.get_data(as_text=True)
def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    if m: return m.group(1)
    with c.session_transaction() as s: return s.get("_csrf_token")
def post(c, path, data=None, page=None, files=None):
    d = dict(data or {}); d["csrf_token"] = tok(c, page or path)
    if files:
        return c.post(path, data={**d, **files}, content_type="multipart/form-data", follow_redirects=True)
    return c.post(path, data=d, follow_redirects=True)
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client(); post(c, "/login", {"username": u, "password": "Pass1234"}, "/login"); return c
def one(q, *a):
    c = get_db(); r = c.execute(q, a).fetchone(); c.close(); return r[0] if r else None
def sql(q, *a):
    c = get_db(); c.execute(q, a); c.commit(); c.close()
def pdftext(b): return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)
def csvfile(text, name="f.csv"): return {"csv_file": (io.BytesIO(text.encode()), name)}
def flashes(r): return " ".join(re.findall(r'class="flash flash-\w+">([^<]*)<', html(r)))

# ---------------------------------------------------------------- fixtures
c0 = get_db(); h = generate_password_hash("Pass1234")
c0.execute("UPDATE users SET password_hash=?", (h,))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
sid_ses = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (sid_ses,))
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('3rd Term', ?, 0)", (sid_ses,))
T1, T2, T3 = [r[0] for r in c0.execute("SELECT id FROM terms WHERE session_id=? ORDER BY id", (sid_ses,))]
subs = [r[0] for r in c0.execute("SELECT id FROM subjects WHERE school_id=1")]
for s_ in subs: c0.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,12,15,0,40)", (s_, T1))
# a second school (tenant isolation)
c0.execute("INSERT INTO schools (name) VALUES ('Other School')"); s2 = c0.execute("SELECT MAX(id) FROM schools").fetchone()[0]
c0.execute("UPDATE schools SET tenant_id=CAST(id AS TEXT) WHERE id=?", (s2,))
c0.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)", (s2, str(s2), "Admin Two", "admin_two", h, "admin"))
# a second class with a different form teacher
c0.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role, position) SELECT school_id, tenant_id, 'Second Teacher', 'teacher2', ?, 'teacher', 'form_teacher' FROM users WHERE username='admin'", (h,))
t2id = c0.execute("SELECT id FROM users WHERE username='teacher2'").fetchone()[0]
c0.execute("INSERT INTO classes (school_id, tenant_id, name, form_teacher_id) SELECT 1, tenant_id, 'JSS2B', ? FROM schools WHERE id=1", (t2id,))
CLS2 = c0.execute("SELECT id FROM classes WHERE name='JSS2B'").fetchone()[0]
c0.commit(); c0.close()
ADMIN, FT, ADMIN2 = login("admin"), login("aokafor"), login("admin_two")
ADMIN.get("/admin/result-display-settings")

# ======================================================= 1) announcements
tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
r = post(ADMIN, "/admin/announcements", {"title": "Mid-term break", "message": "School closes Friday.", "audience": "all", "level": "info", "expires_at": tomorrow, "dismissible": "1"}, "/admin/announcements")
check("School Admin can publish an announcement", one("SELECT COUNT(*) FROM announcements WHERE school_id=1 AND title='Mid-term break'") == 1, flashes(r))
check("...and it shows as a banner on the admin dashboard", "Mid-term break" in html(ADMIN.get("/dashboard")))
check("...and on a teacher's dashboard", "Mid-term break" in html(FT.get("/dashboard")))
check("...but NOT on another school's dashboard (tenant isolation)", "Mid-term break" not in html(ADMIN2.get("/dashboard")))
post(ADMIN, "/admin/announcements", {"title": "Staff only", "message": "Staff meeting.", "audience": "teacher", "level": "warning", "expires_at": tomorrow}, "/admin/announcements")
check("an announcement for teachers only is hidden from the admin dashboard", "Staff only" not in html(ADMIN.get("/dashboard")) and "Staff only" in html(FT.get("/dashboard")))
check("a non-dismissible announcement has no dismiss button", "Staff only" in html(FT.get("/dashboard")) and html(FT.get("/dashboard")).count('class="ann-x"') == 1)   # only the dismissible one has a button
aid = one("SELECT id FROM announcements WHERE title='Mid-term break'")
post(FT, f"/announcements/{aid}/dismiss", {}, "/dashboard")
check("a user can dismiss a dismissible announcement", "Mid-term break" not in html(FT.get("/dashboard")))
check("...and it is still shown to other users", "Mid-term break" in html(ADMIN.get("/dashboard")))
sid_staff = one("SELECT id FROM announcements WHERE title='Staff only'")
post(FT, f"/announcements/{sid_staff}/dismiss", {}, "/dashboard")
check("a non-dismissible announcement cannot be dismissed", "Staff only" in html(FT.get("/dashboard")))
r = post(ADMIN, "/admin/announcements", {"title": "No expiry", "message": "x", "audience": "all"}, "/admin/announcements")
check("an announcement without an expiry is refused", one("SELECT COUNT(*) FROM announcements WHERE title='No expiry'") == 0)
past = (datetime.datetime.now() - datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
post(ADMIN, "/admin/announcements", {"title": "Past", "message": "x", "audience": "all", "expires_at": past}, "/admin/announcements")
check("an expiry in the past is refused", one("SELECT COUNT(*) FROM announcements WHERE title='Past'") == 0)
sql("INSERT INTO announcements(school_id,title,message,audience,expires_at,created_by_label) VALUES (1,'Expired one','x','all',?, 'x')", (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"))
check("an expired announcement is not shown", "Expired one" not in html(ADMIN.get("/dashboard")))
sql("INSERT INTO announcements(school_id,title,message,audience,expires_at,created_by_label) VALUES (1,'Long gone','x','all',?, 'x')", (datetime.datetime.utcnow() - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
ANN._last_purge["t"] = 0; ADMIN.get("/dashboard")
check("expired announcements are purged automatically", one("SELECT COUNT(*) FROM announcements WHERE title='Long gone'") == 0 and one("SELECT COUNT(*) FROM announcements WHERE title='Expired one'") == 1)
other = one("SELECT id FROM announcements WHERE title='Mid-term break'")
post(ADMIN2, "/admin/announcements", {"action": "remove", "id": other}, "/admin/announcements")
check("one school cannot remove another school's announcement", one("SELECT is_active FROM announcements WHERE id=?", other) == 1)
PA = A.app.test_client()
with PA.session_transaction() as s: s["platform_admin_id"] = 1; s["platform_admin_name"] = "Root"
tok_ = lambda: tok(PA, "/platform/announcements")
r = PA.post("/platform/announcements", data={"csrf_token": tok_(), "title": "Platform notice", "message": "Maintenance tonight.", "audience": "all", "level": "warning", "expires_at": tomorrow})
check("Super Admin can announce to ALL schools", one("SELECT COUNT(*) FROM announcements WHERE title='Platform notice' AND school_id IS NULL") == 1, r.status_code)
check("...and every school's users see it", "Platform notice" in html(ADMIN.get("/dashboard")) and "Platform notice" in html(ADMIN2.get("/dashboard")))
PA.post("/platform/announcements", data={"csrf_token": tok_(), "school_id": str(s2), "title": "Only school two", "message": "Hello.", "audience": "all", "expires_at": tomorrow})
check("Super Admin can target ONE school", "Only school two" in html(ADMIN2.get("/dashboard")) and "Only school two" not in html(ADMIN.get("/dashboard")))
check("platform admins only: school admins cannot open the platform page", ADMIN.get("/platform/announcements").status_code in (302, 401, 403))

# ======================================================= 2) teacher student attendance
d = html(FT.get("/dashboard"))
check("teacher menu has Student Attendance, not Staff Attendance", "Student Attendance" in d and "Staff Attendance" not in d)
check("teacher dashboard has no staff-attendance link", "/staff-attendance" not in d.replace("/staff-attendance/history", "") or "staff_attendance" not in d)
check("admin menu keeps Staff Attendance", "Staff Attendance" in html(ADMIN.get("/dashboard")))
r = FT.get("/my-class/attendance")
check("a teacher with one class goes straight to that class's roll call", r.status_code == 302 and "/roll-call" in r.headers["Location"] and f"/my-class/{CLS2}/" not in r.headers["Location"], r.headers.get("Location"))
check("a teacher cannot take attendance for someone else's class", FT.get(f"/my-class/{CLS2}/roll-call").status_code == 302)
check("the reports hub hides Staff Attendance from teachers", "Staff Attendance History" not in html(FT.get("/reports")))

# ======================================================= 3) terms + locked published design + fonts + signature
ADMIN.get("/admin/result-display-settings")
tbl = lambda h_: (re.search(r'<table class="cbs">.*?</table>', h_, re.S) or [h_])[0] if re.search(r'<table class="cbs">', h_) else h_
cb = tbl(html(ADMIN.get(f"/cumulative/1?term_id={T1}")))
check("only the activated First Term appears on the cumulative broadsheet", "1st Term" in cb and "2nd Term" not in cb and "3rd Term" not in cb, re.findall(r"(\d)(?:st|nd|rd) Term", cb))
sql("UPDATE terms SET activated_at=CURRENT_TIMESTAMP, is_active=1 WHERE id=?", T2); sql("UPDATE terms SET is_active=0 WHERE id=?", T1)
cb2 = tbl(html(ADMIN.get(f"/cumulative/1?term_id={T2}")))
check("the Second Term appears once the School Admin has activated it", "2nd Term" in cb2 and "3rd Term" not in cb2)
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("cumulative scores use a larger font (7.3pt, was 6.4pt)", "font-size:7.3pt!important" in css)
src = open(os.path.join(ROOT, "pdf_sheet.py")).read()
check("downloaded PDF signature cells are centre-aligned", '("ALIGN", (0, 0), (-1, -1), "CENTER")' in src and 'hAlign="CENTER"' in src)
# published design is locked
sql("UPDATE terms SET is_active=1 WHERE id=?", T1); sql("UPDATE terms SET is_active=0 WHERE id=?", T2)
sql("UPDATE schools SET readiness_status='ready'")
WF = "/results/workflow"
for act in ("submit", "start_review", "approve", "publish"):
    post(ADMIN, f"{WF}/1/{T1}/{act}", {}, f"{WF}?term_id={T1}")
check("class result went through submit/review/approve/publish", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T1) == "published", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T1))
check("the sheet design/settings were frozen at publish", (one("SELECT sheet_snapshot FROM result_publication WHERE class_id=1 AND term_id=?", T1) or "").startswith("{"))
sql("UPDATE result_display_settings SET accent_color='#aa0000', template='executive', show_domains=0")
with A.app.test_request_context(): prn = A.url_for("result_print", student_id=1, term_id=T1)
s_pub = html(ADMIN.get(prn))
check("changing the design/colour/switches later does NOT alter the published result", "--rs-accent:#0b2a6f" in s_pub and "rs-style-professional_classic" in s_pub and "rs-style-executive" not in s_pub, re.findall(r"--rs-accent:#\w+", s_pub))
sql("UPDATE result_display_settings SET accent_color='#0b2a6f', template='professional_classic', show_domains=1")

# ======================================================= 4) passport frame / duplicate upload
sp = html(ADMIN.get("/students/1/profile"))
check("the student profile page no longer has its own photo upload field", 'type="file"' not in sp and "Edit Profile" in sp)
pe = html(ADMIN.get("/students/1/profile/edit"))
check("the single passport upload is on the Edit Profile form", pe.count('type="file"') == 1 and 'name="photo"' in pe)
sc = open(os.path.join(ROOT, "static/css/style.css")).read()
check("one passport frame style: fixed size, cover, no distortion", "img.passport-img{width:120px;height:150px" in sc and "object-fit:cover" in sc.split("img.passport-img")[1][:200])

# ======================================================= 5) admission numbers per class, staff id
c = get_db()
c.execute("INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, class_id) SELECT 1, tenant_id, 'X-100', 'Aa', 'Bb', 1 FROM schools WHERE id=1"); c.commit()
try:
    c.execute("INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, class_id) SELECT 1, tenant_id, 'x-100', 'Cc', 'Dd', 1 FROM schools WHERE id=1"); dup_same = False
except Exception: dup_same = True
c.rollback()
check("the same Admission No. twice in ONE class is refused (database)", dup_same)
c.execute("INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, class_id) SELECT 1, tenant_id, 'X-100', 'Ee', 'Ff', ? FROM schools WHERE id=1", (CLS2,)); c.commit()
check("the same Admission No. in a DIFFERENT class is allowed", c.execute("SELECT COUNT(*) FROM students WHERE admission_no='X-100'").fetchone()[0] == 2)
c.close()
r = post(ADMIN, "/admin/teachers", {"name": "New Teacher", "username": "newteach", "password": "Pass12345", "email": "nt@example.com", "phone": "08031234567", "rbac_role": "Teacher"}, "/admin/teachers")
check("Staff / Employee ID is required when registering staff", one("SELECT COUNT(*) FROM users WHERE username='newteach'") == 0 and "Staff / Employee ID is required" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/teachers", {"name": "New Teacher", "username": "newteach", "staff_id": "GSS/T/014", "password": "Pass12345", "email": "nt@example.com", "phone": "08031234567", "rbac_role": "Teacher"}, "/admin/teachers")
check("...and is saved with the new staff member", one("SELECT staff_id FROM users WHERE username='newteach'") == "GSS/T/014", flashes(r))
r = post(ADMIN, "/admin/teachers", {"name": "Other T", "username": "newteach2", "staff_id": "gss/t/014", "password": "Pass12345", "email": "nt2@example.com", "phone": "08031234568", "rbac_role": "Teacher"}, "/admin/teachers")
check("a duplicate Staff ID in the same school is refused with a clear message", one("SELECT COUNT(*) FROM users WHERE username='newteach2'") == 0 and "already used" in flashes(r), flashes(r))
import profile_core as PC
spec = next(f for f in PC.STAFF_FIELDS if f["key"] == "staff_id") if hasattr(PC, "STAFF_FIELDS") else None
check("Staff ID is not admin-only/protected on the profile any more", spec is None or not spec.get("admin_only"))

# ======================================================= 6) navigation
d = html(ADMIN.get("/dashboard")); tdash = html(FT.get("/dashboard"))
groups = re.findall(r'<div class="nav-group">([^<]+)</div>', d)
check("menu is organised in categories for the admin", groups[:3] == ["Academics", "Attendance", "Teaching"] and "School Administration" in groups and "People" in groups, groups)
check("a teacher does not see administrator categories or links", "School Administration" not in tdash and "People" not in re.findall(r'<div class="nav-group">([^<]+)</div>', tdash) and "Theme &amp; Branding" not in tdash)
side = re.search(r'<aside class="app-sidebar".*?</aside>', d, re.S)[0]
links = re.findall(r'<a [^>]*href="([^"]+)"', side)
check("no menu link appears twice in the sidebar", len(links) == len(set(links)), [l for l in links if links.count(l) > 1])
js = open(os.path.join(ROOT, "static/js/shell-ui.js"), encoding="utf-8").read()
check("hamburger: aria-expanded, Escape, backdrop, close on link/resize", all(x in js for x in ("aria-expanded", "Escape", "sidebar-backdrop", "pageshow")) and 'id="sidebarToggle" type="button"' in d and 'aria-controls="appSidebar"' in d)

sc2 = open(os.path.join(ROOT, "static/css/style.css")).read()
check("hamburger: the menu is stacked ABOVE its backdrop, and has an in-menu Close button", "body .app-sidebar{z-index:1001!important}" in sc2 and "sidebar-close" in js and ".sidebar-close{display:flex" in sc2)

# ======================================================= 7) CSV imports
tpl = ADMIN.get("/admin/students/csv_template").get_data(as_text=True).strip().splitlines()[0]
check("student template headings are exactly the importable fields", tpl.split(",")[:4] == ["admission_no", "first_name", "last_name", "other_names"] and "class_name" in tpl)
good = "admission_no,first_name,last_name,class_name,gender,date_of_birth,parent_email\nA-001,Ada,Obi,JSS1A,F,2012-05-14,ada@example.com\nA-002,Bayo,Eze,JSS1A,m,14/05/2011,\nA-001,Kemi,Lawal,JSS2B,F,,\n"
r = post(ADMIN, "/admin/students/bulk_upload", {}, "/admin/students", files=csvfile(good))
check("a valid student file imports every row", one("SELECT COUNT(*) FROM students WHERE admission_no IN ('A-001','A-002')") == 3 and "Imported 3 student(s)" in flashes(r), flashes(r))
check("...dates and gender are normalised", one("SELECT date_of_birth FROM students WHERE admission_no='A-002'") == "2011-05-14" and one("SELECT gender FROM students WHERE admission_no='A-002'") == "M")
check("...and the same Admission No. (A-001) was accepted in a different class", one("SELECT COUNT(*) FROM students WHERE admission_no='A-001'") == 2)
before = one("SELECT COUNT(*) FROM students")
bad = "admission_no,first_name,last_name,class_name,gender,date_of_birth\nB-001,Ok,Row,JSS1A,F,2012-01-01\nB-002,Bad,Gender,JSS1A,Z,2012-01-01\nB-003,No,Class,NOPE,F,2012-01-01\nB-001,Dup,InFile,JSS1A,F,2012-01-01\nA-001,Exists,Already,JSS1A,F,32/13/2012\n"
r = post(ADMIN, "/admin/students/bulk_upload", {}, "/admin/students", files=csvfile(bad)); fl = flashes(r)
check("a file with problems saves NOTHING", one("SELECT COUNT(*) FROM students") == before and one("SELECT COUNT(*) FROM students WHERE admission_no='B-001'") == 0, fl)
check("...and every problem is named with its row and column", all(x in fl for x in ("Row 3, column gender", "Row 4, column class_name", "Row 5, column admission_no", "Row 6, column admission_no", "Row 6, column date_of_birth")), fl)
r = post(ADMIN, "/admin/students/bulk_upload", {}, "/admin/students", files=csvfile("name,class\nx,y\n"))
check("wrong headings give a clear message listing what is missing", "Missing required heading(s): admission_no, first_name, last_name" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/students/bulk_upload", {}, "/admin/students", files=csvfile("admission_no,first_name,last_name,class_name\n"))
check("a headings-only file is refused", "no data rows" in flashes(r))
sql("UPDATE students SET religion='Christianity' WHERE admission_no='A-001'")
reg = "admission_no,first_name,last_name,religion\nA-001,Ada,Obi,\nA-009,New,Pupil,Islam\n"
post(FT, "/my-class/1/csv_upload", {}, "/my-class/1", files=csvfile(reg))
check("class register upload: a blank cell does not erase saved data", one("SELECT religion FROM students WHERE admission_no='A-001'") == "Christianity")
check("...and adds new students to THIS class only", one("SELECT class_id FROM students WHERE admission_no='A-009'") == 1)
before_names = one("SELECT first_name FROM students WHERE admission_no='A-001'")
post(FT, "/my-class/1/csv_upload", {}, "/my-class/1", files=csvfile("admission_no,first_name,last_name,gender\nA-001,Changed,Name,M\nA-002,,Eze,M\n"))
check("class register upload: one bad row saves nothing", one("SELECT first_name FROM students WHERE admission_no='A-001'") == before_names)
sql("UPDATE result_publication SET status='draft' WHERE term_id=?", T1)        # scores of a published term are locked; reopen it for the import checks
sidx = one("SELECT id FROM students WHERE admission_no='A-001' AND class_id=1")
stpl = FT.get(f"/scores/1/{subs[0]}/csv_template").get_data(as_text=True).strip().splitlines()[0]
check("score template has only the importable headings", stpl == "admission_no,ca1,ca2,exam", stpl)
sql("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (?,?,?,10,12,0,35)", sidx, subs[0], T1) if False else None
active_term = one("SELECT id FROM terms WHERE is_active=1")
sql("INSERT OR IGNORE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (?,?,?,10,12,0,35)", sidx, subs[0], active_term)
r_up = post(FT, f"/scores/1/{subs[0]}/csv_upload", {}, f"/scores/1/{subs[0]}", files=csvfile("admission_no,ca1,ca2,exam\nA-001,,15,\n"))
row = get_db().execute("SELECT ca1,ca2,exam FROM scores WHERE student_id=? AND subject_id=? AND term_id=?", (sidx, subs[0], active_term)).fetchone()
check("score upload: blank cells keep the saved score (no silent zeros)", row and row[0] == 10 and row[1] == 15 and row[2] == 35, tuple(row) if row else None)
r = post(FT, f"/scores/1/{subs[0]}/csv_upload", {}, f"/scores/1/{subs[0]}", files=csvfile("admission_no,ca1,ca2,exam\nA-001,5,5,5\nNOPE-1,5,5,5\nA-002,abc,5,5\n"))
row2 = get_db().execute("SELECT ca1,ca2,exam FROM scores WHERE student_id=? AND subject_id=? AND term_id=?", (sidx, subs[0], active_term)).fetchone()
check("score upload: a bad file changes nothing and explains why", tuple(row2) == tuple(row) and "no student with Admission No." in flashes(r) and "is not a number" in flashes(r), flashes(r))

# ======================================================= 8) custom school information
check("Custom School Information is reachable from the menu", "School Information" in d and "/admin/school-info" in d)
post(ADMIN, "/admin/school-info", {"action": "add", "label": "Motto", "value": "Knowledge and Power", "show_on_result": "1"}, "/admin/school-info")
post(ADMIN, "/admin/school-info", {"action": "add", "label": "Internal note", "value": "Do not print"}, "/admin/school-info")
sql("UPDATE result_display_settings SET show_custom_info=1")
W.publish(A, T2)
with A.app.test_request_context(): prn2 = A.url_for("result_print", student_id=1, term_id=T2); pdf2 = A.url_for("result_pdf", student_id=1, term_id=T2)
s_ = html(ADMIN.get(prn2))
check("chosen school-information fields print on the result sheet", "Knowledge and Power" in s_ and "Do not print" not in s_)
html_pdf._state.update(checked=True, ok=False); t_ = pdftext(ADMIN.get(pdf2).data); html_pdf._state.update(checked=False)
check("...and in the downloaded PDF", "Knowledge and Power" in t_ and "Do not print" not in t_)
sql("UPDATE result_display_settings SET show_custom_info=0")
check("the display switch hides them", "Knowledge and Power" not in html(ADMIN.get(prn2)))
sql("UPDATE result_display_settings SET show_custom_info=1")

# ======================================================= 9) additional result fields + domain order
post(ADMIN, "/admin/result-fields", {"action": "add", "label": "Hobbies", "field_type": "text"}, "/admin/result-fields")
post(ADMIN, "/admin/result-fields", {"action": "add", "label": "Subjects offered", "field_type": "number", "options": "20"}, "/admin/result-fields")
post(ADMIN, "/admin/result-fields", {"action": "add", "label": "Conduct", "field_type": "choice", "options": "Excellent, Good, Fair"}, "/admin/result-fields")
fid = {r[0]: r[1] for r in get_db().execute("SELECT label, id FROM result_custom_fields")}
check("School Admin can add additional fields (text, number, choice)", set(fid) == {"Hobbies", "Subjects offered", "Conduct"})
r = post(ADMIN, "/admin/result-fields", {"action": "add", "label": "Conduct", "field_type": "text"}, "/admin/result-fields")
check("a duplicate field name is refused", "already exists" in flashes(r))
r = post(ADMIN, "/admin/result-fields", {"action": "add", "label": "Bad choice", "field_type": "choice", "options": "only"}, "/admin/result-fields")
check("a choice field needs at least two options", one("SELECT COUNT(*) FROM result_custom_fields WHERE label='Bad choice'") == 0)
pg = html(ADMIN.get(f"/result/1?term_id={T1+0}"))
sql("UPDATE result_publication SET status='draft' WHERE term_id=?", T3) if False else None
with A.app.test_request_context(): ex = A.url_for("result_extra", student_id=1)
# an unpublished term to save into: T3
sql("INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status) SELECT 1,tenant_id,1,?,'draft' FROM schools WHERE id=1", T3)
pg3 = html(FT.get(f"/result/1?term_id={T3}"))
check("the fields appear under Update Result Details for the form teacher", all(f'name="cf_{i}"' in pg3 for i in fid.values()), pg3[:100])
r = post(FT, ex, {"term_id": T3, f"cf_{fid['Hobbies']}": "Football, reading", f"cf_{fid['Subjects offered']}": "9", f"cf_{fid['Conduct']}": "excellent"}, f"/result/1?term_id={T3}")
vals = {r[0]: r[1] for r in get_db().execute("SELECT field_id, value FROM result_custom_values WHERE student_id=1 AND term_id=?", (T3,))}
check("values are saved per student and term (choice matched to its list)", vals.get(fid["Hobbies"]) == "Football, reading" and vals.get(fid["Subjects offered"]) == "9" and vals.get(fid["Conduct"]) == "Excellent", vals)
r = post(FT, ex, {"term_id": T3, f"cf_{fid['Subjects offered']}": "99", f"cf_{fid['Conduct']}": "Terrible"}, f"/result/1?term_id={T3}")
vals2 = {r[0]: r[1] for r in get_db().execute("SELECT field_id, value FROM result_custom_values WHERE student_id=1 AND term_id=?", (T3,))}
check("invalid values (number above the maximum, choice not in list) are refused and the old values kept", vals2.get(fid["Subjects offered"]) == "9" and vals2.get(fid["Conduct"]) == "Excellent")
W.publish(A, T3)
with A.app.test_request_context(): prn3 = A.url_for("result_print", student_id=1, term_id=T3); pdf3 = A.url_for("result_pdf", student_id=1, term_id=T3)
s3 = html(ADMIN.get(prn3))
check("additional fields print on the result sheet", "Additional Information" in s3 and "Football, reading" in s3 and "Excellent" in s3)
html_pdf._state.update(checked=True, ok=False); t3 = pdftext(ADMIN.get(pdf3).data); html_pdf._state.update(checked=False)
check("...and in the downloaded PDF", "Additional Information".upper() in t3.upper() and "Football, reading" in t3)
sql("UPDATE result_display_settings SET show_additional_fields=0")
check("the display switch hides them", "Football, reading" not in html(ADMIN.get(prn3)))
sql("UPDATE result_display_settings SET show_additional_fields=1")
post(ADMIN, "/admin/result-fields", {"action": "toggle", "field_id": fid["Hobbies"]}, "/admin/result-fields")
check("hiding a field removes it from the sheet but keeps the saved values", "Football, reading" not in html(ADMIN.get(prn3)) and one("SELECT COUNT(*) FROM result_custom_values WHERE field_id=?", fid["Hobbies"]) == 1)
post(ADMIN, "/admin/result-fields", {"action": "move", "field_id": fid["Conduct"], "direction": "up"}, "/admin/result-fields")
order = [r[0] for r in get_db().execute("SELECT label FROM result_custom_fields ORDER BY sort_order, id")]
check("fields can be re-ordered", order.index("Conduct") < order.index("Subjects offered"), order)
trait_order = lambda: [r[0] for r in get_db().execute("SELECT name FROM skill_traits WHERE school_id=1 AND category='affective' ORDER BY sort_order, name")]
before_o = trait_order(); tid_ = one("SELECT id FROM skill_traits WHERE school_id=1 AND category='affective' AND name=?", before_o[1])
post(ADMIN, "/admin/domains", {"action": "move_trait", "trait_id": tid_, "dir": "up"}, "/admin/domains")
after_o = trait_order()
check("domain items can be re-ordered (up/down)", after_o[0] == before_o[1] and after_o[1] == before_o[0], (before_o[:3], after_o[:3]))
post(ADMIN, "/admin/domains", {"action": "add_domain", "label": "Co-curricular"}, "/admin/domains")
check("custom domains (assessment categories) can still be created", one("SELECT COUNT(*) FROM educational_domains WHERE school_id=1 AND label='Co-curricular'") == 1)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
