"""V113 end-to-end in a real browser: sign in -> offline pages are prepared automatically -> server goes down -> the header turns
red and cached pages still open -> attendance + a score are saved offline -> server returns -> everything syncs automatically.
Run: python tests/v113_offline_e2e.py   (needs playwright + chromium)"""
import os, re, sys, tempfile, threading, time, logging
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v113e2e_"); sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, d)
c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.execute("DELETE FROM result_publication"); c0.commit(); c0.close()
A.app.config["TESTING"] = False; PORT = 18613; BASE = f"http://localhost:{PORT}"
srv = None
def start():
    global srv
    srv = make_server("127.0.0.1", PORT, A.app, threaded=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
def stop():
    srv.shutdown(); srv.server_close()
def q(sql, *a):
    c = get_db(); r = c.execute(sql, a).fetchone(); c.close(); return r[0] if r else None
# an existing score for student 3 (typed online earlier), so an offline edit has a real "version I started from"
import re as _re
_cl = A.app.test_client(); _cl.post("/login", data={"username": "admin", "password": "Pass1234", "csrf_token": _re.search(r'name="csrf_token" value="([^"]+)"', _cl.get("/login").get_data(as_text=True)).group(1)})
_cl.get("/dashboard")
with _cl.session_transaction() as _s: _tok = _s["_csrf_token"]
assert _cl.post("/api/scores/1/1/row", json={"student_id": 3, "ca1": "5", "ca2": "5", "exam": "20"}, headers={"X-CSRF-Token": _tok}).json["ok"]
start()
cls = q("SELECT class_id FROM students WHERE id=1")
n_att = q("SELECT COUNT(*) FROM attendance_records")
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(); page = ctx.new_page()
    ctx.add_init_script("new MutationObserver(() => { if (document.querySelector('.sh-prep')) sessionStorage.setItem('prepSeen', '1'); }).observe(document, {childList: true, subtree: true});")
    page.goto(f"{BASE}/login"); page.fill('input[name="username"]', "aokafor"); page.fill('input[name="password"]', "Pass1234"); page.click('button[type="submit"]')
    page.wait_for_selector("#shConn", timeout=15000)
    print("signed in; waiting for background preparation")
    page.wait_for_function("() => localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('sh-ready-')) || 'x')", timeout=90000)
    check("offline preparation finished by itself, with no page clicks", True)
    check("the preparation screen was NEVER shown to the user (silent, in the background)", page.evaluate("() => sessionStorage.getItem('prepSeen')") is None and page.locator(".sh-prep").count() == 0)
    check("the header does not announce 'preparing offline' either", "preparing" not in page.locator("#shConn").inner_text().lower())
    keys = page.evaluate("async () => (await (await caches.open('sh-pages-v113')).keys()).map(r => new URL(r.url).pathname)")
    print("cached pages:", len(keys))
    check("dashboard cached", "/dashboard" in keys, keys)
    check("the roll-call page (one click away from the menu) is cached", f"/my-class/{cls}/roll-call" in keys, keys)
    check("score-entry pages were crawled", any(k.startswith("/scores") or "/score" in k for k in keys), keys[:30])
    check("many pages cached, not just the page we opened", len(keys) >= 8, len(keys))
    check("no action links were cached", not [k for k in keys if re.search(r"logout|delete|approve|export|download", k)], keys)
    chip = page.locator("#shConn")
    check("header indicator is shown and says Online", "Online" in chip.inner_text() and chip.get_attribute("data-state") in ("online", "completed"))
    bg = page.evaluate("() => getComputedStyle(document.getElementById('shConn')).backgroundColor"); i_bg = page.evaluate("() => getComputedStyle(document.querySelector('#shConn i')).backgroundColor")
    rgb = [int(x) for x in re.findall(r"\d+", i_bg)[:3]]
    check("online indicator is GREEN", rgb[1] > rgb[0] and rgb[1] > rgb[2], i_bg)
    check("it sits inside the header", page.evaluate("() => !!document.querySelector('header.topbar #shConn')"))

    print("--- the school server goes down ---")
    stop()
    page.wait_for_function("() => document.getElementById('shConn').dataset.state === 'offline'", timeout=30000)
    check("indicator turns to Offline", "Offline" in chip.inner_text())
    i_bg = page.evaluate("() => getComputedStyle(document.querySelector('#shConn i')).backgroundColor"); rgb = [int(x) for x in re.findall(r"\d+", i_bg)[:3]]
    check("offline indicator is RED", rgb[0] > 180 and rgb[1] < 100 and rgb[2] < 100, i_bg)
    r = page.goto(f"{BASE}/my-class/{cls}/roll-call")
    check("roll-call opens offline from the prepared cache (never visited by the user)", "Save Roll Call" in page.content() or "Roll Call" in page.content(), page.title())
    check("it is styled (shell assets cached)", page.evaluate("() => document.styleSheets.length") >= 1)
    page.goto(f"{BASE}/dashboard"); check("dashboard opens offline", page.locator("header.topbar").count() == 1)
    page.goto(f"{BASE}/some-page-never-visited-xyz"); check("an unknown page shows the friendly offline page, not a browser error", "offline" in page.content().lower())

    page.goto(f"{BASE}/my-class/{cls}/roll-call"); page.wait_for_selector("#shConn")
    page.click('button[type="submit"]')
    page.wait_for_function("() => /pending/.test(document.getElementById('shConn').innerText)", timeout=15000)
    check("attendance saved on the device while offline (header shows 1 pending)", "1 pending" in chip.inner_text(), chip.inner_text())
    check("nothing reached the server yet", q("SELECT COUNT(*) FROM attendance_records") == n_att)
    page.click('button[type="submit"]'); time.sleep(0.8)
    check("saving twice offline keeps ONE queued attendance (latest wins)", "1 pending" in chip.inner_text(), chip.inner_text())

    print("--- the server comes back ---")
    start()
    page.wait_for_function("() => /^(Online|Sync Completed)/.test(document.getElementById('shConn').innerText) && !/pending/.test(document.getElementById('shConn').innerText)", timeout=60000)
    check("indicator back to green automatically, nothing pending", "pending" not in chip.inner_text() and chip.get_attribute("data-state") in ("online", "completed"), chip.inner_text())
    check("ATTENDANCE SYNCHRONIZED: records now exist on the server", q("SELECT COUNT(*) FROM attendance_records") > n_att)
    check("exactly one set was recorded (no duplicate from saving twice / retrying)", q("SELECT COUNT(*) FROM attendance_records WHERE class_id=? AND date=?", cls, A.v63_core.school_today(get_db(), 1)) == q("SELECT COUNT(*) FROM students WHERE class_id=? AND is_active=1", cls))
    check("server logged the replay as applied", q("SELECT state FROM sync_changes WHERE entity='attendance' ORDER BY id DESC LIMIT 1") == "applied")
    page.goto(f"{BASE}/sync"); page.wait_for_selector("[data-sync-center]")
    check("Sync Center shows nothing waiting", page.locator("[data-k=pending]").inner_text() == "0")

    print("--- editing an EXISTING score offline, on a page opened from the prepared cache (used to cause a false conflict) ---")
    score_url = page.evaluate("""async () => { const c = await caches.open('sh-pages-v113'); for (const r of await c.keys()) { const t = await (await c.match(r)).text(); if (t.includes('id="scoreApp"')) return new URL(r.url).pathname + new URL(r.url).search; } return null; }""")
    check("a score-entry page is among the prepared pages", bool(score_url), score_url)
    n_conf = q("SELECT COUNT(*) FROM sync_conflicts")
    stop(); page.goto(f"{BASE}/dashboard") if False else None
    page.wait_for_timeout(500)
    page.goto(f"{BASE}{score_url}"); page.wait_for_selector("#scoreApp", state="attached", timeout=15000); page.wait_for_timeout(800)
    page.wait_for_function("() => document.getElementById('shConn').dataset.state === 'offline'", timeout=30000)
    res = page.evaluate("""async () => { const r = await fetch('/api/scores/1/1/row', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({student_id:3, ca1:'7', ca2:'7', exam:'7'})}); return [r.status, await r.json()]; }""")
    check("the offline edit of an existing score is queued", res[0] == 202 and res[1]["queued"], res)
    start()
    page.wait_for_function("() => !/pending/.test(document.getElementById('shConn').innerText) && /^(Online|Sync Completed)/.test(document.getElementById('shConn').innerText)", timeout=60000)
    check("NO conflict was raised: the teacher's own edit simply applied", q("SELECT COUNT(*) FROM sync_conflicts") == n_conf, q("SELECT reason FROM sync_conflicts ORDER BY id DESC LIMIT 1"))
    check("the new score is on the server", q("SELECT ca1 FROM scores WHERE student_id=3 AND subject_id=1 AND term_id=(SELECT id FROM terms WHERE is_active=1)") == 7)

    print("--- a score typed while the server is down ---")
    ctx.add_init_script("")  # no-op, keeps context alive
    page.goto(f"{BASE}/dashboard"); stop()
    page.wait_for_function("() => document.getElementById('shConn').dataset.state === 'offline'", timeout=30000)
    res = page.evaluate("""async () => { const r = await fetch('/api/scores/1/1/row', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({student_id:2, ca1:'8', ca2:'9', exam:'31'})}); return [r.status, await r.json()]; }""")
    check("offline score save is accepted into the queue (202, queued)", res[0] == 202 and res[1]["queued"], res)
    start()
    page.wait_for_function("() => !/pending/.test(document.getElementById('shConn').innerText) && /^(Online|Sync Completed)/.test(document.getElementById('shConn').innerText)", timeout=60000)
    check("score synchronized to the server", q("SELECT ca1 FROM scores WHERE student_id=2 AND subject_id=1 AND term_id=(SELECT id FROM terms WHERE is_active=1)") == 8)
    b.close()
print(f"\nPASSED {PASS}   FAILED {len(FAIL)}")
if FAIL: print("FAILED:", FAIL); os._exit(1)
os._exit(0)
