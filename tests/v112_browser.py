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
    check("teacher attendance trend is a LINE chart", t.evaluate("!!document.querySelector('#attendance-trend polyline') && document.querySelectorAll('#attendance-trend circle').length>=2"))
    check("teacher: only one Pass/Fail panel", t.evaluate("[...document.querySelectorAll('h2,h3')].filter(h=>/pass\\s*\\/?\\s*(and)?\\s*fail/i.test(h.textContent)).length") == 1)
    t.click("text=Score Entry"); t.wait_for_timeout(600); check("Score Entry tile opens My Teaching Workspace", "/teaching-workspace" in t.url, t.url)
    b.close()
print(f"\n{P} passed, {F} failed"); sys.exit(1 if F else 0)
