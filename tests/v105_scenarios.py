"""V105 scenarios: School Administration dashboard redesign (cards, gender split, result compilation, trend, quick access, announcements),
removal of Academic workspace / School operations / Quick Actions, Quick Access on teacher dashboards, phone layout pieces.
Run: python tests/v105_scenarios.py"""
import datetime, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v105_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
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
def post(c, path, data=None, page=None):
    d = dict(data or {}); d["csrf_token"] = tok(c, page or path); return c.post(path, data=d, follow_redirects=True)
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client(); post(c, "/login", {"username": u, "password": "Pass1234"}, "/login"); return c

c0 = get_db(); h = generate_password_hash("Pass1234")
c0.execute("UPDATE users SET password_hash=?", (h,))
c0.execute("UPDATE users SET gender='Female' WHERE username='aokafor'")
c0.execute("UPDATE users SET gender='Male' WHERE username='admin'")
term = c0.execute("SELECT id FROM terms WHERE is_active=1").fetchone()[0]
subs = [r[0] for r in c0.execute("SELECT subject_id FROM class_subjects WHERE class_id=1")]
studs = [r[0] for r in c0.execute("SELECT id FROM students WHERE class_id=1 ORDER BY id")]
males = c0.execute("SELECT COUNT(*) FROM students WHERE gender='M'").fetchone()[0]; females = c0.execute("SELECT COUNT(*) FROM students WHERE gender='F'").fetchone()[0]
for sid_ in studs[:2]:                                   # two of three students have EVERY class subject scored this term
    for sub in subs: c0.execute("INSERT OR IGNORE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (?,?,?,10,10,0,40)", (sid_, sub, term))
c0.execute("INSERT INTO school_fee_summary(school_id,expected_amount,collected_amount) VALUES (1,2650000,1890000)")
tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
c0.commit(); c0.close()
ADMIN, FT = login("admin"), login("aokafor")
post(ADMIN, "/admin/announcements", {"title": "Result Release Soon", "message": "Results will be published shortly.", "audience": "all", "expires_at": tomorrow, "dismissible": "1"}, "/admin/announcements")
r = ADMIN.get("/dashboard"); d = html(r)
check("admin dashboard loads", r.status_code == 200)

# ---- removed blocks
check("Academic workspace, School operations and Quick Actions are gone from the admin dashboard", all(x not in d for x in ("Academic workspace", "School operations", "Quick Actions", "Quick actions")))

# ---- stat cards
check("Students card shows the total with male/female counts and percentages", f">{males + females}<" in d.replace(",", "") and "(66.7%)" in d and "(33.3%)" in d and "View Students" in d, (males, females))
check("Staff card shows total and gender split", re.search(r"Staff</span><b>2</b>", d) is not None and d.count("(50.0%)") >= 2, re.findall(r"\(\d+\.\d%\)", d))
check("Classes, Subjects and Parents cards", all(x in d for x in ("View Classes", "View Subjects", "View Parents")) and re.search(r"Classes</span><b>1</b>", d) and re.search(r"Subjects</span><b>4</b>", d) and re.search(r"Parents</span><b>0</b>", d))
check("School Fees card shows expected, collected and the percentage", "₦2,650,000" in d and "₦1,890,000" in d and "(71.3%)" in d)
fees_card = d[d.index('class="ad-kpi k-fees"'):d.index("</article>", d.index('class="ad-kpi k-fees"'))]
check("the School Fees card has no link (ignored for now)", "<a " not in fees_card and "href" not in fees_card, fees_card[-200:])
check("each stat card has its own colour from the design", all(c in d for c in ("k-blue", "k-green", "k-purple", "k-cyan", "k-orange", "k-fees")))

# ---- panels
check("Gender Distribution donut shows the male percentage and legend", "66.7%" in d and "Gender Distribution" in d and ">Male<" in d and ">Female<" in d)
check("Result Compilation shows 'N of M results compiled', a percentage and a progress bar", "2 of 3" in d and "results compiled" in d and "67%" in d and 'role="progressbar"' in d and 'aria-valuenow="67"' in d)
check("Enrollment Trend chart is drawn (students and staff series)", "Enrollment Trend" in d and "<polyline" in d and "Students" in d and "Staff" in d)
check("Recent Activities and Announcements panels, with the published announcement", "Recent Activities" in d and "Announcements" in d and "Result Release Soon" in d and "Tip:" in d)
check("the announcement is shown in its panel, not duplicated as a top banner", d.count("Result Release Soon") == 1)

# ---- quick access
tiles = ["My Profile", "Assign Subject", "Result", "Broadsheet", "Score History", "Session &amp; Terms", "Register New Student", "Promote Students", "Staff Attendance", "Themes &amp; Branding", "Learning Materials", "Timetable", "Result Approval", "Billings"]
check("Quick Access has all 14 tiles from the design", "Quick Access" in d and all(f">{t}<" in d for t in tiles), [t for t in tiles if f">{t}<" not in d])
mvals = {m.group(2).replace("&amp;", "&"): int(m.group(1)) for m in re.finditer(r'--m:(\d+)"[^>]*>.*?<span class="t-lbl">([^<]+)</span>', d, re.S)}
check("phone order: My Profile, Promote Students, CBT, Assign Subject, Result, Broadsheet, Score History, Session & Terms are the first eight", [k for k, v in sorted(mvals.items(), key=lambda kv: kv[1])][:8] == ["My Profile", "Promote Students", "CBT", "Assign Subject", "Result", "Broadsheet", "Score History", "Session & Terms"], sorted(mvals.items(), key=lambda kv: kv[1])[:9])
cbt = d[d.index(">CBT<") - 400:d.index(">CBT<")]
check("CBT is a placeholder, not a link (later feature)", "<a " not in cbt.split("ad-tile")[-1] and "coming soon" in cbt)
check("phone: bottom tab bar with Home / Reports / Notifications / More for staff", all(x in d for x in ('class="mobile-tabs', ">Home<", ">Reports<", ">Notifications<", ">More<")))
sql_ = get_db(); sql_.execute("UPDATE schools SET name='Government Secondary School Goni-Gora', school_address='No 10 wake Street, Goni-Gora, Bauchi State' WHERE id=1"); sql_.commit(); sql_.close()
d_ = html(ADMIN.get("/dashboard"))
check("top bar shows the school name and address", 'class="top-school"><b>Government Secondary School Goni-Gora</b><small>No 10 wake Street, Goni-Gora, Bauchi State</small>' in d_, re.findall(r'class="top-school".{0,200}', d_)[:1])
check("one live clock in the banner plus the phone clock bar", d.count('data-school-ms="') == 2 and "ad-clockbar" in d)
css = open(os.path.join(ROOT, "static/css/admin-dashboard.css")).read()
check("phone/tablet CSS exists (breakpoints 1280 / 700 / 560)", all(x in css for x in ("max-width:1280px", "max-width:700px", "max-width:560px")))
check("the approved colours are used (blue/green/purple/cyan/orange gradients)", all(x in css for x in ("#1d78f2", "#27c25a", "#a259f0", "#1ec3f7", "#ffae1a", "#3ed45e")))

# ---- other dashboards: Quick Access instead of Quick Actions
t = html(FT.get("/dashboard"))
check("teacher dashboard shows Quick Access and no Quick Actions", "Quick Access" in t and "Quick Actions" not in t and "qa-tile" in t)
check("teacher Quick Access has no Staff Attendance, has Student Attendance", "Staff Attendance" not in t and "Student Attendance" in t)
sub = html(ADMIN.get("/dashboard?x=1"))
check("sub-pages are unaffected by the dashboard styles (settings page still renders)", ADMIN.get("/admin/result-display-settings").status_code == 200)

# ---- data builder
conn = get_db()
ov = A.admin_dashboard_overview(conn, 1, conn.execute("SELECT * FROM terms WHERE is_active=1").fetchone())
conn.close()
check("overview: compilation counts only students with EVERY class subject scored", ov["compilation"] == {"compiled": 2, "total": 3, "pct": 67}, ov["compilation"])
check("overview: gender percentages are of the total", abs(ov["students"]["male_pct"] + ov["students"]["female_pct"] - 100) < 0.2, ov["students"])
check("overview: fee percentage = collected / expected", ov["fees"]["pct"] == 71.3, ov["fees"])
check("overview: trend has at least one point with geometry", ov["trend"] and ov["chart"]["line_s"])
conn = get_db(); conn.execute("DELETE FROM school_fee_summary"); conn.commit(); conn.close()
d2 = html(ADMIN.get("/dashboard"))
check("no fee figures yet -> the card shows zeros instead of inventing numbers", "₦0" in d2 and "(0.0%)" in d2)
print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
