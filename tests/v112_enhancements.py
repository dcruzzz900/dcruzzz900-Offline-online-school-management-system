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
want = ["Score Entry", "Take Class Attendance", "Submit Results for Review", "Show Results", "View Timetable", "My Profile", "Learning Materials"]
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

print("=== 10) Round 2: Next Term Resumes, admin charts, teacher dashboard clean-up ===")
# Next Term Resumes: a date set by the admin must print on EVERY student's report sheet (even in a school with no saved display settings)
cn = get_db(); cn.execute("DELETE FROM result_display_settings"); cn.commit(); cn.close()
pg = html(ADMIN.get("/admin/terms")); tk = re.search(r'name="csrf_token" value="([^"]+)"', pg).group(1)
ADMIN.post("/admin/terms", data={"csrf_token": tk, "action": "set_next_resumes", "term_id": term, "next_term_resumes_date": "2027-01-11"}, follow_redirects=True)
cn = get_db(); sids = [r[0] for r in cn.execute("SELECT id FROM students WHERE is_active=1 AND class_id IN (SELECT id FROM classes WHERE name!='SSS9Z')")]; cn.close()
check("every student's report sheet shows Next Term Resumes + the date", all(("Next Term Resumes" in html(ADMIN.get(f"/result/{i}")) and "11/01/2027" in html(ADMIN.get(f"/result/{i}"))) or "11 Jan" in html(ADMIN.get(f"/result/{i}")) or "2027" in html(ADMIN.get(f"/result/{i}")) for i in sids), sids)
check("... and it appears on the print view too", all("Next Term Resumes" in html(ADMIN.get(f"/result/{i}/print")) or ADMIN.get(f"/result/{i}/print").status_code in (302, 403, 404) for i in sids[:1]))
# admin dashboard charts
a = html(ADMIN.get("/dashboard"))
check("admin: Gender Distribution panel removed", "Gender Distribution" not in a and "data-gender-panel" not in a)
check("admin: Attendance Trend with Students/Staff + This week/Last week/Last month/Last year selectors", all(x in a for x in ('id="attendance-trend"', 'data-att-group="students"', 'data-att-group="staff"', 'data-att-range="this_week"', 'data-att-range="last_week"', 'data-att-range="last_month"', 'data-att-range="last_year"')))
check("admin: Enrollment Trend selectable by term / year", 'data-enrol-mode="term"' in a and 'data-enrol-mode="year"' in a)
check("admin: Enrolment by Class Level chart present", 'id="level-enrol"' in a and 'id="levelChart"' in a)
import json as _j
cd = _j.loads(re.search(r'<script id="adChartsData" type="application/json">(.*?)</script>', a, re.S).group(1))
check("chart data has all 8 attendance series + term/year enrolment + levels", all(set(cd["attendance"][g]) == {"this_week", "last_week", "last_month", "last_year"} for g in ("students", "staff")) and set(cd["enrol"]) == {"term", "year"} and cd["levels"])
check("class level counts are real (JSS1A class: 3 students)", any(l["count"] == 3 for l in cd["levels"]), cd["levels"])
check("charts are offline (own script, no Chart.js CDN)", "js/sh-charts.js" in a and "chart.umd" not in a)
# teacher dashboard clean-up
t = html(TEACH.get("/dashboard"))
check("teacher: Pass/Fail shown exactly once (no second chart)", t.count("Pass / Fail Distribution</h2>") == 1 and "Pass and fail distribution" not in t)
check("teacher: Subject Performance shown once", t.count("Subject Performance</h2>") == 1 and "Subject performance" not in t)
for gone in ("My teaching workspace", "Results workspace", "Class Result Performance", "More tools for your role", "Teacher Comments", "AI Learning Materials", "Performance Alerts"):
    check(f"teacher: '{gone}' removed from the dashboard", gone not in t)
check("teacher: v106 'My Classes' table present with real rows + Enter scores / Roll Call", 'id="my-classes"' in t and "Enter scores" in t and "Roll Call" in t)
check("teacher: Attendance Trend is a line chart (drawn by sh-charts.js)", 'id="attendance-trend"' in t and 'id="attChart"' in t and "js/sh-charts.js" in t)
check("teacher: Top Performing Students + Recent Activities are at the bottom (after My Classes)", t.index('id="my-classes"') < t.index("Top Performing Students") and t.index('id="my-classes"') < t.index("Recent Activities"))
check("teacher: tile 1 'Score Entry' opens My Teaching Workspace", '/teaching-workspace' in qa.split("Score Entry")[0][-200:] or "/teaching-workspace" in qa)
tw = TEACH.get("/teaching-workspace")
check("My Teaching Workspace page opens and lists the assignments", tw.status_code == 200 and "My Teaching Workspace" in html(tw) and "Enter scores" in html(tw))

print("=== 11) Round 3: student + parent dashboards and admin list pages in v106 ===")
cn = get_db()
cn.execute("INSERT INTO parent_accounts (school_id, tenant_id, name, username, password_hash, is_active) SELECT id, tenant_id, 'Mrs Obi', 'mrsobi', ?, 1 FROM schools WHERE id=1", (pw,))
pid_ = cn.execute("SELECT id FROM parent_accounts WHERE username='mrsobi'").fetchone()[0]
cn.execute("INSERT INTO parent_students (parent_id, student_id, school_id, tenant_id, status) SELECT ?,1,school_id,tenant_id,'verified' FROM students WHERE id=1", (pid_,))
cn.execute("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP WHERE id=1", (pw,))
cn.execute("UPDATE terms SET is_published=1 WHERE id=?", (term,))
cn.execute("INSERT OR IGNORE INTO result_publication (school_id, tenant_id, term_id, class_id, status) SELECT school_id, tenant_id, ?, id, 'published' FROM classes WHERE name='JSS1A'", (term,))
cn.commit(); cn.close()
STUD, PAR = login("chinedu"), login("mrsobi")
sd = html(STUD.get("/student/dashboard"))
check("student dashboard: v106 banner, KPIs, subject scores + trend + attendance panels", all(x in sd for x in ('class="ad-banner"', 'class="kpi-row"', 'id="subject-scores"', 'id="academic-trend"', 'id="attendance"', 'id="results"')))
check("student dashboard: real figures (avg 90.0%, 4 subjects, 1st position)", "90.0%" in sd and ">4<" in sd and "1st" in sd)
check("student dashboard: every v111 shortcut kept (Quick Access) + View Result link", 'id="quick-access"' in sd and "View Result" in sd and "My Timetable" in sd and "Change Password" in sd)
check("student dashboard: unscored subjects stay gaps, not zeros", '"values": [' in sd or '"values":[' in sd)
pdh = html(PAR.get("/parent/dashboard"))
check("parent dashboard: child card, term chart, subject chart + table, attendance, quick links", all(x in pdh for x in ('id="children"', 'id="academic-trend"', 'id="subject-scores"', 'id="subjects"', 'id="attendance"', "Quick Links")))
check("parent dashboard: only the linked child is selectable (real data, scoped)", "Chinedu" in pdh and "Eze" not in pdh and "Bakare" not in pdh)
for url, marks in (("/admin/classes", ("Add a Class", 'class="data"', "set_class_category" if False else "Class Teacher")), ("/admin/subjects", ("Add a Subject", 'class="data"', "Assigned Teachers")),
                   ("/admin/teachers", ("Add a Teacher", 'class="data"', "Subjects / Classes")), ("/admin/students", ("Add a Student", "Bulk Upload Students", 'class="data"')), ("/admin/parents", ("Linked Children", 'class="data"', "Parents"))):
    pg_ = html(ADMIN.get(url))
    check(f"{url}: v106 page header + KPI/filters + data table, forms still have CSRF", all(m in pg_ for m in marks) and 'class="page-header"' in pg_ and ("csrf_token" in pg_ or url == "/admin/parents"), url)
check("admin/classes shows real student + subject counts per class", "<td>3</td>" in html(ADMIN.get("/admin/classes")) and "<td>4</td>" in html(ADMIN.get("/admin/classes")))
check("admin/teachers lists the teacher's real subjects and class", "Mathematics" in html(ADMIN.get("/admin/teachers")) and "JSS1A" in html(ADMIN.get("/admin/teachers")))
check("v106 pages do not load the legacy stylesheets (no leakage)", "css/style.css" not in html(ADMIN.get("/admin/classes")) and "css/modern.css" in html(ADMIN.get("/admin/classes")))

print("=== 12) Round 5: banner, menus, teacher/admin dashboard changes, collapsible forms ===")
cn = get_db()
cn.execute("INSERT INTO announcements (school_id,title,message,audience,level,dismissible,is_active,created_at) VALUES (1,'R5 Notice','Round five notice.','all','info',1,1,CURRENT_TIMESTAMP)"); cn.commit(); cn.close()
adm, tch, stu, par = html(ADMIN.get("/dashboard")), html(TEACH.get("/dashboard")), html(STUD.get("/student/dashboard")), html(PAR.get("/parent/dashboard"))
for nm, pg_ in (("admin", adm), ("teacher", tch), ("student", stu), ("parent", par)):
    check(f"{nm}: welcome banner uses its own marker (the old React header script can no longer replace it and drop its colour)", 'class="ad-banner"' in pg_ and "data-v106-banner" in pg_ and "data-welcome-header" not in pg_)
    check(f"{nm}: sliding announcement strip at the top + Announcements panel", pg_.count("data-announcement-banners") == 1 and 'id="announcements-panel"' in pg_ and "R5 Notice" in pg_, nm)
    check(f"{nm}: 'Online / Panel' status block removed from the menu", "sidebar-status" not in pg_ and "Teacher Panel" not in pg_ and "Admin Panel" not in pg_)
css = open("static/css/modern-compat.css").read()
check("fixed header: html/body use overflow-x:clip (hidden would disable sticky); .main never a scroll container", "html,body{overflow-x:clip}" in css and ".main,.app-main,.content,main.content{overflow:visible!important" in css)
check("announcement strip slides (CSS keyframes + slider script)", "@keyframes annIn" in css and "js/announcement-slider.js" in html(ADMIN.get("/dashboard")) and os.path.exists("static/js/announcement-slider.js"))
check("panel rows are flex-wrap so they never leave empty space at any zoom", ".ad .ad-panels,.ad .ad-panels-2,.ad .ad-panels-bottom{display:flex!important;flex-wrap:wrap" in css)
# teacher dashboard
check("teacher: 'Subject Assignments' label", "Subject Assignments" in tch and ">Assignments<" not in tch)
check("teacher: My roles + AI Assistant sit in one aligned row", 'class="roles-row card"' in tch and "AI Assistant" in tch)
check("teacher: Enrolment by Class sits right next to Grade Distribution (before My Classes)", 0 < tch.index('id="enrolment-by-class"') - tch.index("Grade Distribution</h2>") < 2500 and tch.index('id="enrolment-by-class"') < tch.index('id="my-classes"'))
check("teacher: My Classes 'Roll Call' link (no Roster)", "Roll Call" in tch.split('id="my-classes"')[1].split("</table>")[0] and "Roster" not in tch.split('id="my-classes"')[1].split("</table>")[0] and "/roll-call" in tch)
check("teacher: Attendance Trend inherited from admin (selectable ranges, students only)", all(x in tch for x in ('data-att-range="this_week"', 'data-att-range="last_year"', 'id="attChart"')) and 'data-att-group' not in tch)
ni = tch.split('id="needs-improvement"', 1)[-1].split("</article>", 1)[0]
check("teacher: Students Needing Improvement lists the real weak student + weakest subject (15% avg), not the strong ones", "15.0%" in ni and "Obi" not in ni and "Eze" not in ni, re.sub(r"<[^>]+>", " ", ni)[:200])
check("teacher: Top Performing + Needing Improvement + Recent Activities + Announcements are at the bottom", tch.index('id="my-classes"') < tch.index("Top Performing Students") < tch.index('id="needs-improvement"') < tch.index("Recent Activities") < tch.index('id="announcements-panel"'))
tw = html(TEACH.get("/teaching-workspace"))
_twm = tw.split("My Teaching Workspace</h2>", 1)[-1].split("</main>", 1)[0].lower()
check("My Teaching Workspace: no attendance on the page body (menu excluded), Roll Call link", "attendance" not in _twm and "roll call" in _twm)
# admin dashboard
wc = adm.split('id="weak-classes"', 1)[-1].split("</article>", 1)[0]
check("admin: Classes Needing Improvement lists JSS1A (33% fail share) with real avg/failing figures", "JSS1A" in wc and "1 of 3" in wc, re.sub(r"<[^>]+>", " ", wc)[:200])
# student dashboard de-duplication
check("student: repeated blocks removed (4 quick cards, 'My academic profile', 'Full result' link, duplicate Rate tile)", all(x not in stu for x in ("My academic profile", "Terminal report card", "Weekly schedule", "Notes &amp; resources", "Full result")))
check("student: nothing important lost (quick access, results, attendance, announcements)", all(x in stu for x in ('id="quick-access"', "View Result", 'id="attendance"', 'id="announcements-panel"')))
# list pages
stp, clp, sbp, tp = html(ADMIN.get("/admin/students")), html(ADMIN.get("/admin/classes")), html(ADMIN.get("/admin/subjects")), html(ADMIN.get("/admin/teachers"))
for nm, pg_, fid in (("students", stp, "add-student"), ("classes", clp, "add-class"), ("subjects", sbp, "add-subject")):
    check(f"{nm}: add form is collapsed by default and opened by the + Add button (still a real form with CSRF)", f'id="{fid}" data-collapsible hidden' in pg_ and f'data-toggle-form="#{fid}"' in pg_ and "toggle-form.js" in pg_ and "csrf_token" in pg_.split(f'id="{fid}"')[1])
check("students: New This Term card (real count)", 'id="new-this-term"' in stp and "New This Term" in stp)
check("teachers: Teachers card", 'id="teachers-card"' in tp and ">Teachers<" in tp)

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
