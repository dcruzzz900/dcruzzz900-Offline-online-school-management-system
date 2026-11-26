"""V115 scenarios: collapsed Add-Teacher form, Student dashboard order + mobile bottom menu, all announcements on every dashboard card,
v106 headers everywhere. Run: python tests/v115_scenarios.py"""
import datetime, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v115_")
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
A.app.config["TESTING"] = False; logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, d)
def html(r): return r.get_data(as_text=True)
def run(sql, *a):
    c = get_db(); c.execute(sql, a); c.commit(); c.close()
def one(sql, *a):
    c = get_db(); r = c.execute(sql, a).fetchone(); c.close(); return r[0] if r else None
def tok(c, page="/login"):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    if m: return m.group(1)
    with c.session_transaction() as s: return s.get("_csrf_token")
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client()
    c.post("/login", data={"username": u, "password": "Pass1234", "csrf_token": tok(c)}, follow_redirects=True); return c
run("UPDATE users SET password_hash=?", generate_password_hash("Pass1234"))
ADMIN, FT = login("admin"), login("aokafor")

print("=== 1) Teachers & Staff: the Add-a-teacher form starts collapsed ===")
d = html(ADMIN.get("/admin/teachers"))
check("form card is rendered but hidden + collapsible", re.search(r'id="add-teacher"[^>]*data-collapsible[^>]*hidden', d) is not None)
check("'+ Add Teacher' is a toggle button for it", 'data-toggle-form="#add-teacher"' in d and 'aria-controls="add-teacher"' in d)
check("page loads the toggle script", "toggle-form.js" in d)
r = ADMIN.post("/admin/teachers", data={"csrf_token": tok(ADMIN, "/admin/teachers"), "full_name": "", "username": "", "password": ""}, follow_redirects=True)
check("after a failed submit the form stays OPEN so the error can be fixed", re.search(r'id="add-teacher"[^>]*data-collapsible[^>]*hidden', html(r)) is None)

print("=== 2) announcements: the card lists ALL of them, in every dashboard ===")
sch = one("SELECT id FROM schools LIMIT 1")
exp = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
for i in range(8):
    run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,created_by_label) VALUES (?,?,?,?,?,1,?,'t')", sch, f"CARD-{i}", "m", "all", "info", exp)
run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,created_by_label) VALUES (?,?,?,?,?,1,?,'t')", sch, "CARD-teacheronly", "m", "teacher", "warning", exp)
for who, c in (("teacher", FT), ("admin", ADMIN)):
    d = html(c.get("/dashboard")); card = d.split('id="announcements-panel"')[-1]
    check(f"{who}: the card shows all 8 'everyone' announcements (the strip is capped at 5)", all(f"CARD-{i}" in card for i in range(8)), re.findall(r"CARD-\w+", card))
check("teacher: audience still respected (teacher-only one shown to the teacher)", "CARD-teacheronly" in html(FT.get("/dashboard")).split('id="announcements-panel"')[-1])
check("admin: ...and NOT shown to the admin", "CARD-teacheronly" not in html(ADMIN.get("/dashboard")).split('id="announcements-panel"')[-1])
check("the top strip is still limited to 5", html(FT.get("/dashboard")).split('id="announcements-panel"')[0].count("data-ann-seconds") <= 5)

print("=== 3) Student dashboard: order + mobile bottom menu ===")
st = one("SELECT id FROM students ORDER BY id LIMIT 1"); tn = one("SELECT tenant_id FROM schools WHERE id=?", sch); sc = one("SELECT school_code FROM schools WHERE id=?", sch)
S = A.app.test_client()
with S.session_transaction() as s:
    s.update({"student_id": st, "role": "student", "school_id": sch, "tenant_id": tn, "school_code": sc, "login_time": datetime.datetime.utcnow().isoformat()})
d = html(S.get("/student/dashboard"))
check("student dashboard renders", 'id="attendance"' in d and 'id="academic-trend"' in d, d[:200])
if 'id="attendance"' in d:
    pos = {k: d.index(f'id="{k}"') for k in ("subject-scores", "academic-trend", "attendance", "quick-access", "results")}
    check("Attendance comes immediately after Academic Performance", pos["academic-trend"] < pos["attendance"] < pos["quick-access"], pos)
    check("order: Scores, Academic, Attendance, Quick Access, Results", sorted(pos, key=pos.get) == ["subject-scores", "academic-trend", "attendance", "quick-access", "results"], pos)
    check("student card lists all 8 announcements too", all(f"CARD-{i}" in d.split('id="announcements-panel"')[-1] for i in range(8)))
    check("student gets the mobile bottom menu (Home / Results / Materials / Alerts / More)", 'class="mobile-tabs student-tabs' in d and 'id="studentMore"' in d and 'id="studentMoreSheet"' in d)
    check("...with AI Tutor, Timetable, Profile, Account, Logout in the More sheet", all(x in d.split('id="studentMoreSheet"')[-1] for x in ("AI Tutor", "My Timetable", "My Profile", "My Account", "Logout")))
    check("student pages load the More-sheet script", "student-more.js" in d)
check("staff bottom menu unchanged (no student sheet for staff)", 'id="studentMore"' not in html(FT.get("/dashboard")) and 'class="mobile-tabs"' in html(FT.get("/dashboard")).replace("mobile-tabs no-print", "mobile-tabs"))

print("=== 4) v106 headers + final stylesheet on every screen ===")
for who, c, path in (("admin", ADMIN, "/dashboard"), ("admin", ADMIN, "/admin/students"), ("teacher", FT, "/dashboard"), ("student", S, "/student/dashboard")):
    check(f"{who} {path}: v115 layout stylesheet is loaded last", "css/v115-layout.css" in html(c.get(path)))
for who, c, path in (("registrar", ADMIN, "/registrar"),):
    d = html(c.get(path)); check("Registrar dashboard uses the v106 banner + announcements card", 'class="ad-banner' in d and 'id="announcements-panel"' in d)
check("service worker cache version bumped so phones fetch the new CSS", "const VERSION = 'v115'" in open("static/service-worker.js").read())

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL); sys.exit(1)
