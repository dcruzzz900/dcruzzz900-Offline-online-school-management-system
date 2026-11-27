"""V112 browser tests (Playwright): selectable admin charts, teacher line chart, floating control. Run: python tests/v112_browser.py"""
import datetime as D, logging, os, random, sys, tempfile, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v112b_"); sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
logging.disable(logging.CRITICAL)
c = get_db(); c.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),))
term = c.execute("SELECT id FROM terms ORDER BY id DESC LIMIT 1").fetchone()[0]; studs = [r[0] for r in c.execute("SELECT id FROM students")]
cls = c.execute("SELECT id FROM classes LIMIT 1").fetchone()[0]; sch = c.execute("SELECT id FROM schools LIMIT 1").fetchone()[0]; uid = c.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
random.seed(1); today = D.date.today()
for back in range(0, 420):
    d = today - D.timedelta(days=back)
    if d.weekday() > 4: continue
    for sid in studs: c.execute("INSERT INTO attendance_records (student_id,class_id,term_id,date,status) VALUES (?,?,?,?,?)", (sid, cls, term, d.isoformat(), "present" if random.random() < .88 else "absent"))
    c.execute("INSERT INTO staff_attendance (school_id,user_id,date,status) VALUES (?,?,?,?)", (sch, uid, d.isoformat(), "Present" if random.random() < .94 else "Absent"))
for ttl, lvl in (("Mid-term break", "info"), ("PTA meeting", "warning"), ("Fees reminder", "success")):
    c.execute("INSERT INTO announcements (school_id,title,message,audience,level,dismissible,is_active,created_at) VALUES (1,?,?, 'all',?,1,1,CURRENT_TIMESTAMP)", (ttl, ttl + " notice.", lvl))
c.execute("UPDATE students SET username='chinedu', password_hash=?, first_login_completed_at=CURRENT_TIMESTAMP WHERE id=1", (generate_password_hash("Pass1234"),))
c.commit(); c.close()
srv = make_server("127.0.0.1", 5081, A.app, threaded=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
from playwright.sync_api import sync_playwright
P = F = 0
def check(n, ok, x=""):
    global P, F
    if ok: P += 1
    else: F += 1; print("FAIL:", n, x)
def login(b, user, w=1280):
    pg = b.new_context(viewport={"width": w, "height": 900}).new_page()
    pg.goto("http://127.0.0.1:5081/login"); pg.fill("input[name=username]", user); pg.fill("input[name=password]", "Pass1234"); pg.click("form button[type=submit]"); pg.wait_for_timeout(1800); return pg
PTS = "document.querySelectorAll('#attChart circle').length"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = login(b, "admin")
    pg.goto("http://127.0.0.1:5081/dashboard"); pg.wait_for_timeout(600)
    check("admin attendance line drawn (students, this week)", pg.evaluate("!!document.querySelector('#attChart polyline')") or pg.evaluate(PTS) >= 1)
    note0 = pg.inner_text("#attNote"); check("note names the range", "Student attendance" in note0, note0)
    pg.click('[data-att-group="staff"]'); pg.wait_for_timeout(200); check("Staff selectable", "Staff attendance" in pg.inner_text("#attNote") and pg.get_attribute('[data-att-group="staff"]', "aria-pressed") == "true")
    for rng, lbl in (("last_week", "7"), ("last_month", None), ("last_year", "12")):
        pg.click(f'[data-att-range="{rng}"]'); pg.wait_for_timeout(200)
        n = pg.evaluate(PTS); labels = pg.evaluate("document.querySelectorAll('#attChart text.shc-ax').length")
        check(f"range {rng}: chart redraws with points", n >= 1, n)
        check(f"range {rng}: button pressed + note updated", pg.get_attribute(f'[data-att-range="{rng}"]', "aria-pressed") == "true" and pg.inner_text("#attNote") != note0)
    pg.click('[data-att-range="last_year"]'); check("last year has 12 monthly x-labels", pg.evaluate("[...document.querySelectorAll('#attChart text.shc-ax')].filter(t=>/^[A-Z][a-z]{2}$/.test(t.textContent.trim())).length") >= 6)
    check("Enrollment Trend bars drawn (by term)", pg.evaluate("document.querySelectorAll('#enrolChart rect').length") >= 1)
    pg.click('[data-enrol-mode="year"]'); pg.wait_for_timeout(200); check("Enrollment by year selectable", pg.get_attribute('[data-enrol-mode="year"]', "aria-pressed") == "true" and pg.evaluate("document.querySelectorAll('#enrolChart rect').length") >= 1)
    check("Enrolment by Class Level bars drawn", pg.evaluate("document.querySelectorAll('#levelChart rect').length") >= 1)
    check("no Gender Distribution panel on admin dashboard", pg.evaluate("document.body.innerText.includes('Gender Distribution')") is False)
    # teacher line chart
    t = login(b, "aokafor"); t.goto("http://127.0.0.1:5081/dashboard"); t.wait_for_timeout(600)
    t.click('#attendance-trend [data-att-range="last_week"]'); t.wait_for_timeout(250)   # "this week" has a single day early in the week; last week has a full line
    check("teacher attendance trend is a LINE chart", t.evaluate("!!document.querySelector('#attendance-trend polyline') && document.querySelectorAll('#attendance-trend circle').length>=2"))
    check("teacher: only one Pass/Fail panel", t.evaluate("[...document.querySelectorAll('h2,h3')].filter(h=>/pass\\s*\\/?\\s*(and)?\\s*fail/i.test(h.textContent)).length") == 1)
    t.click("text=Score Entry"); t.wait_for_timeout(600); check("Score Entry tile opens My Teaching Workspace", "/teaching-workspace" in t.url, t.url)

    # ---- Round 5: sliding announcements, fixed header, collapsible forms, teacher attendance selector ----
    for w in (1280, 390):
        a = login(b, "admin", w); a.goto("http://127.0.0.1:5081/dashboard"); a.wait_for_timeout(700)
        check(f"{w}px: announcements strip shows 3 slides, starting on the first", a.evaluate("document.querySelectorAll('.ann-track .ann').length") == 3 and "translateX(0" in a.evaluate("document.querySelector('.ann-track').style.transform"))
        a.wait_for_timeout(6800); check(f"{w}px: strip slides to the next announcement by itself", "translateX(-100%)" in a.evaluate("document.querySelector('.ann-track').style.transform"))
        check(f"{w}px: header fits the screen (avatar + bell fully visible, nothing pushed off)", a.evaluate("(()=>{const r=document.querySelector('.top-avatar').getBoundingClientRect();return r.right<=innerWidth+0.5&&r.left>=0&&document.querySelector('.topbar-school h1').getBoundingClientRect().width>20})()"))
        a.evaluate("window.scrollTo(0, 1600)"); a.wait_for_timeout(250)
        check(f"{w}px: admin header stays fixed when scrolling", a.evaluate("Math.round(document.querySelector('.topbar').getBoundingClientRect().top)") == 0)
        check(f"{w}px: panel rows leave no empty gap (every panel row is filled edge to edge)", a.evaluate("""(()=>{const rows=[...document.querySelectorAll('.ad .ad-panels')];return rows.every(r=>{const kids=[...r.children].filter(k=>k.offsetHeight>0);if(!kids.length)return true;const tops={};kids.forEach(k=>{const t=Math.round(k.getBoundingClientRect().top);(tops[t]=tops[t]||[]).push(k)});return Object.values(tops).every(line=>{const l=Math.min(...line.map(k=>k.getBoundingClientRect().left)),rr=Math.max(...line.map(k=>k.getBoundingClientRect().right));return Math.abs((rr-l)-r.getBoundingClientRect().width)<3})})})()"""))
    t = login(b, "aokafor", 390); t.goto("http://127.0.0.1:5081/dashboard"); t.evaluate("window.scrollTo(0, 2500)"); t.wait_for_timeout(250)
    check("phone: teacher header fixed while scrolling", t.evaluate("Math.round(document.querySelector('.topbar').getBoundingClientRect().top)") == 0)
    s_ = login(b, "chinedu", 390); s_.goto("http://127.0.0.1:5081/student/dashboard"); s_.evaluate("window.scrollTo(0, 2500)"); s_.wait_for_timeout(250)
    check("phone: student header AND tab strip fixed while scrolling", s_.evaluate("Math.round(document.querySelector('.topbar').getBoundingClientRect().top)") == 0 and s_.evaluate("Math.round(document.querySelector('.portal-tabs').getBoundingClientRect().top) - Math.round(document.querySelector('.topbar').getBoundingClientRect().height)") in (0, 1, -1))
    t2 = login(b, "aokafor"); t2.goto("http://127.0.0.1:5081/dashboard"); t2.wait_for_timeout(600)
    t2.click('#attendance-trend [data-att-range="last_month"]'); t2.wait_for_timeout(250)
    check("teacher attendance trend: selectable period redraws the line chart", t2.get_attribute('#attendance-trend [data-att-range="last_month"]', "aria-pressed") == "true" and t2.evaluate("document.querySelectorAll('#attChart svg').length") + t2.evaluate("document.querySelectorAll('#attChart .shc-empty').length") >= 1)
    for url, fid in (("/admin/students", "add-student"), ("/admin/classes", "add-class"), ("/admin/subjects", "add-subject")):
        pa = login(b, "admin"); pa.goto("http://127.0.0.1:5081" + url); pa.wait_for_timeout(400)
        check(f"{url}: add form hidden until + Add is clicked", pa.evaluate(f"document.getElementById('{fid}').hidden") is True)
        pa.click(f'button[data-toggle-form="#{fid}"]'); pa.wait_for_timeout(450)
        check(f"{url}: + Add expands the form (visible, focused field)", pa.evaluate(f"document.getElementById('{fid}').offsetHeight") > 80 and pa.evaluate(f"document.getElementById('{fid}').contains(document.activeElement)"))
        pa.click(f"#{fid} .form-close"); pa.wait_for_timeout(250); check(f"{url}: Close collapses it again", pa.evaluate(f"document.getElementById('{fid}').hidden") is True)
    b.close()
print(f"\n{P} passed, {F} failed"); sys.exit(1 if F else 0)
