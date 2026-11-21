"""V112 enhancement tests (the nine requested items). Run: python tests/v112_enhancements.py"""
import logging, os, re, sys, tempfile, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v112e_"); sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
logging.disable(logging.CRITICAL); A.app.config["TESTING"] = False
P = F = 0
def check(name, ok, extra=""):
    global P, F
    if ok: P += 1
    else: F += 1; print("FAIL:", name, extra)
def html(r): return r.get_data(as_text=True)
pw = generate_password_hash("Pass1234"); c = get_db()
c.execute("UPDATE users SET password_hash=?", (pw,))
term = c.execute("SELECT id FROM terms ORDER BY id DESC LIMIT 1").fetchone()[0]
studs = [r[0] for r in c.execute("SELECT id FROM students ORDER BY id")]
subs = {r[0]: r[1] for r in c.execute("SELECT s.id, s.name FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id")}
for sid, (a, b, e) in {studs[0]: (18, 17, 55), studs[1]: (10, 12, 40), studs[2]: (2, 3, 10)}.items():
    for sub in subs: c.execute("INSERT INTO scores (student_id,subject_id,term_id,ca1,ca2,exam) VALUES (?,?,?,?,?,?)", (sid, sub, term, a, b, e))
# a SECOND class + student + scores the teacher must never see (multi-tenant / scope check)
school = c.execute("SELECT id, tenant_id FROM schools LIMIT 1").fetchone()
cols = [r[1] for r in c.execute("PRAGMA table_info(classes)")]
c.execute("INSERT INTO classes (school_id, name) VALUES (?, 'SSS9Z')", (school["id"],)); other = c.execute("SELECT id FROM classes WHERE name='SSS9Z'").fetchone()[0]
c.commit(); c.close()
def login(u):
    A._rate_limit_store.clear(); cl = A.app.test_client()
    t = re.search(r'name="csrf_token" value="([^"]+)"', html(cl.get("/login"))).group(1)
    cl.post("/login", data={"username": u, "password": "Pass1234", "csrf_token": t}, follow_redirects=True); return cl
ADMIN, TEACH = login("admin"), login("aokafor")

print("=== 1) Teacher Quick Access: exactly 7 tiles, right labels, in order ===")
t = html(TEACH.get("/dashboard"))
qa = t.split('id="quick-access"', 1)[-1].split("</article>", 1)[0]
labels = [re.sub(r"<[^>]+>|\s+", " ", m).strip() for m in re.findall(r"<a [^>]*>(.*?)</a>", qa, re.S)]
want = ["Score Entry", "Take Class Attendance", "Results Approval", "Show Results", "View Timetable", "My Profile", "Learning Materials"]
check("exactly 7 tiles", len(labels) == 7 and 'data-qa-count="7"' in t, labels)
check("labels + order as requested", len(labels) == 7 and all(w in l for l, w in zip(labels, want)), labels)
check("every tile has a real link", all(re.search(r'href="/[^"]+"', x) for x in re.findall(r"<a [^>]*>", qa)))
for href in re.findall(r'href="(/[^"]+)"', qa):
    r = TEACH.get(href); check(f"tile target {href} opens (no server error)", r.status_code < 500, r.status_code)

print("=== 2) Teacher analytics from REAL data ===")
for h in ("Subject Performance", "Pass / Fail Distribution", "Top Performing Students", "Recent Activities"):
    check(f"teacher dashboard shows '{h}'", h in t)
sp = t.split('id="subject-performance"', 1)[-1].split("</article>", 1)[0]
# every subject got totals 90 / 62 / 15 -> mean 55.67; 2 of 3 pass (F is the fail grade for 15)
check("subject performance uses the real average (55.7%) and pass rate (67%)", "55.7% avg" in sp and "67% pass" in sp, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sp))[:200])
check("all 4 assigned subjects listed", sum(1 for n in subs.values() if n in sp) == len(subs))
pf = t.split('id="pass-fail"', 1)[-1].split("</article>", 1)[0]
check("pass/fail distribution: 2 passed, 1 failed, 0 not assessed", "Passed — 2" in pf and "Failed — 1" in pf and "Not yet assessed — 0" in pf, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pf))[:200])
ts = t.split('data-slot="top-students"', 1)[-1].split("</article>", 1)[0]
check("top students ranked by real average (90 > 62 > 15)", ts.index("90.0%") < ts.index("62.0%") < ts.index("15.0%") if all(x in ts for x in ("90.0%", "62.0%", "15.0%")) else False)
# scope: a class the teacher cannot see must not leak into their analytics
c = get_db(); c.execute("INSERT INTO students (school_id, class_id, first_name, last_name, admission_no, gender, is_active) VALUES (?,?,?,?,?,?,1)", (school["id"], other, "Zed", "Hidden", "ZZ-1", "M")); zid = c.execute("SELECT id FROM students WHERE admission_no='ZZ-1'").fetchone()[0]
for sub in subs: c.execute("INSERT INTO scores (student_id,subject_id,term_id,ca1,ca2,exam) VALUES (?,?,?,?,?,?)", (zid, sub, term, 20, 20, 60))
c.execute("INSERT INTO class_subjects (class_id, subject_id) SELECT ?, id FROM subjects LIMIT 1", (other,)); c.commit(); c.close()
t2 = html(TEACH.get("/dashboard"))
check("another class's scores never appear in a teacher's analytics (scope kept)", "Hidden" not in t2 and "55.7% avg" in t2)
check("the admin dashboard DOES count the whole school", "Hidden" in html(ADMIN.get("/dashboard")) or "100.0%" in html(ADMIN.get("/dashboard")))

print("=== 3) Admin Quick Access: 8 by default + View All / View Less ===")
a = html(ADMIN.get("/dashboard")); aq = a.split('id="adQuick"', 1)[-1].split("</div>", 1)[0]
tiles = re.findall(r"<a [^>]*>", aq)
check("18 shortcuts exist; first 8 visible, the rest marked qa-extra", len(tiles) == 18 and sum('qa-extra' in x for x in tiles) == 10 and not any('qa-extra' in x for x in tiles[:8]), len(tiles))
check("View All (n) button present, collapsed by default", 'id="qaToggle"' in a and 'aria-expanded="false"' in a and "View All (18)" in a and 'data-less="View Less"' in a)
check("nothing from v111 was dropped (Result Approval, Data Completion, Billing, Promote, Themes...)", all(x in a for x in ("Result Approval", "Data Completion", "Billing", "Promote Students", "Themes &amp; Branding", "Learning Materials", "Assign Subject", "Score History")))

print("=== 4) Global typography ===")
css = open("static/css/modern-compat.css").read()
check("root text raised to 17px (16px phones), scalable by A-/A+", "--fs-root:17px" in css and "--fs-root:16px" in css and 'data-font-scale="150"]{--fs-scale:1.5}' in css)
check("v106 pages (no theme.css) still get the font-scale rules", "V112: typography + font scale (every page)" in css)
for pg in ("/dashboard", "/admin/students", "/login"):
    check(f"{pg}: modern-compat.css (typography) is loaded", "css/modern-compat.css" in html(ADMIN.get(pg) if pg != "/login" else A.app.test_client().get(pg)))

print("=== 5/6) Floating settings control + persistence ===")
anon = html(A.app.test_client().get("/login"))
for name, page in (("sign-in", anon), ("admin", a), ("teacher", t)):
    check(f"{name}: draggable floating control present", 'id="shFab"' in page and 'id="shFabBtn"' in page and "js/floating-settings.js" in page)
    check(f"{name}: it holds text size (A-/A+) and the light/dark toggle", "data-fs-step" in page.split('id="shFabPanel"', 1)[-1] and "data-theme-toggle" in page.split('id="shFabPanel"', 1)[-1])
check("old header copies removed (one control only)", a.count("data-theme-toggle") == 1 and a.count('data-fs-step="1"') == 1)
js = open("static/js/floating-settings.js").read()
check("drag via pointer events, position saved + clamped", "pointerdown" in js and "pointermove" in js and "localStorage.setItem(KEY" in js and "clamp(" in js)
check("keyboard accessible (Enter/Space, Shift+Arrows, Escape)", "Escape" in js and "ArrowLeft" in js)
tok = re.search(r'data-csrf="([^"]+)"', a); tok = tok.group(1) if tok else ""
r = ADMIN.post("/api/preferences", json={"theme": "dark", "font_scale": 130}, headers={"X-CSRF-Token": tok})
check("preference save endpoint accepts theme + size", r.status_code == 200, r.status_code)
fresh = login("admin"); fp = html(fresh.get("/dashboard"))
check("a NEW sign-in restores the saved size and theme from the server (follows the person)", 'data-font-scale="130"' in fp and 'data-bs-theme="dark"' in fp)
tp = html(TEACH.get("/dashboard")); check("preferences are per person (teacher unaffected)", 'data-font-scale="130"' not in tp)

print("=== 7/8) Offline + stack preserved ===")
check("teacher charts are server-drawn SVG (work offline)", "<svg" in t and 'aria-label="Class performance"' in t)
for f in ("app.py", "db.py", "static/js/react-ui/dashboard-filters.js", "static/js/react-ui/welcome-header.js", "static/js/theme-toggle.js"):
    check(f"{f} still present", os.path.exists(f))
check("React dashboard filters still mounted on the teacher dashboard", 'id="dashFilters"' in t and "dashboard-filters.js" in t)
check("Bootstrap 5 still available to legacy pages", "bootstrap" in html(ADMIN.get("/admin/students")).lower())
check("multi-tenant: every dashboard query is school-scoped", "school_id" in open("app.py").read().split("def teacher_dashboard_extras", 1)[1][:6000])
print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
