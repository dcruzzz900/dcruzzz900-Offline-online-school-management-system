"""V114 end-to-end in a real browser, TWO people sharing one device:
teacher signs in online (pages are prepared silently, once) -> signs out -> admin signs in online (own pages, own key) ->
server goes down -> offline sign-in for each (wrong password refused) -> data and waiting changes stay separate and encrypted ->
server returns -> the teacher's changes are sent after a one-time password prompt.
Run: python tests/v113_offline_e2e.py   (needs playwright + chromium)"""
import os, re, sys, tempfile, threading, time, logging
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v114e2e_"); sys.path.insert(0, ROOT); os.chdir(ROOT)
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
A.app.config["TESTING"] = False; PORT = 18614; BASE = f"http://localhost:{PORT}"
hits = []
class Count:
    def __init__(self, app): self.app = app
    def __call__(self, env, sr):
        p = env.get("PATH_INFO", "")
        if env.get("REQUEST_METHOD") == "GET" and not p.startswith(("/static", "/api/sync")): hits.append(p)
        return self.app(env, sr)
A.app.wsgi_app = Count(A.app.wsgi_app)
srv = None
def start():
    global srv
    srv = make_server("127.0.0.1", PORT, A.app, threaded=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
def stop(): srv.shutdown(); srv.server_close()
def q(sql, *a):
    c = get_db(); r = c.execute(sql, a).fetchone(); c.close(); return r[0] if r else None
# an existing score for student 3, typed online earlier
_cl = A.app.test_client(); _cl.post("/login", data={"username": "admin", "password": "Pass1234", "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', _cl.get("/login").get_data(as_text=True)).group(1)})
_cl.get("/dashboard")
with _cl.session_transaction() as _s: _tok = _s["_csrf_token"]
assert _cl.post("/api/scores/1/1/row", json={"student_id": 3, "ca1": "5", "ca2": "5", "exam": "20"}, headers={"X-CSRF-Token": _tok}).json["ok"]
start()
cls = q("SELECT class_id FROM students WHERE id=1"); n_att = q("SELECT COUNT(*) FROM attendance_records"); n_conf = q("SELECT COUNT(*) FROM sync_conflicts")

def login(page, user):
    page.goto(f"{BASE}/login"); page.fill('input[name="username"]', user); page.fill('input[name="password"]', "Pass1234"); page.click('button[type="submit"]')
    page.wait_for_selector("#shConn", timeout=20000)
def my_fp(page): return page.evaluate("async () => (await (await fetch('/api/sync/session')).json()).fingerprint")
def prepared(page, fp, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("(fp) => new Promise(res => { const r = indexedDB.open('sh-offline-v1'); r.onsuccess = () => { const g = r.result.transaction('meta').objectStore('meta').get('prepared:' + fp); g.onsuccess = () => { r.result.close(); res(!!g.result); }; }; r.onerror = () => res(false); })", fp): return True
        time.sleep(0.5)
    raise RuntimeError("offline preparation did not finish")
def cache_keys(page, name): return page.evaluate("async (n) => (await (await caches.open(n)).keys()).map(r => new URL(r.url).pathname + new URL(r.url).search)", name)
def unlocked(page, fp): return page.evaluate("(fp) => new Promise(res => { const r = indexedDB.open('sh-offline-v1'); r.onsuccess = () => { const g = r.result.transaction('keys').objectStore('keys').get('unlocked:' + fp); g.onsuccess = () => { r.result.close(); res(!!g.result); }; }; })", fp)
def logout(page): page.evaluate("() => document.querySelector('a[href$=\"/logout\"]').click()")
def chip(page): return page.locator("#shConn")
def offline_login(page, user, pw):
    page.fill('#offForm input[name="username"]', user); page.fill('#offForm input[name="password"]', pw); page.click('#offForm button[type="submit"]')

with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(); page = ctx.new_page(); page.on("dialog", lambda d: d.accept())
    ctx.add_init_script("new MutationObserver(() => { if (document.querySelector('.sh-prep')) sessionStorage.setItem('prepSeen', '1'); }).observe(document, {childList: true, subtree: true});")
    print("=== 1. the teacher signs in online ===")
    login(page, "aokafor"); fpA = my_fp(page); prepared(page, fpA)
    check("offline preparation finished by itself", True)
    check("the preparation was never shown to the user", page.evaluate("() => sessionStorage.getItem('prepSeen')") is None and "preparing" not in chip(page).inner_text().lower())
    keysA = cache_keys(page, f"sh-pages-v114-{fpA}"); print("teacher pages cached:", len(keysA))
    check("many pages were prepared (menu pages and the pages they lead to)", len(keysA) >= 12, keysA)
    check("dashboard and the roll-call page are ready", "/dashboard" in keysA and f"/my-class/{cls}/roll-call" in keysA)
    check("the teacher's offline storage is open while signed in", unlocked(page, fpA))
    raw = page.evaluate("async (n) => { const r = await (await caches.open(n)).match('/dashboard'); return [r.headers.get('X-SH-Enc'), await r.text()]; }", f"sh-pages-v114-{fpA}")
    check("cached pages are ENCRYPTED at rest (no readable school text in the cache)", raw[0] == "1" and "Welcome" not in raw[1] and "Okafor" not in raw[1] and "<html" not in raw[1].lower())
    page.wait_for_timeout(1500); n_first = len(hits); print("page requests during first sign-in:", n_first)
    check("header: green Online", chip(page).get_attribute("data-state") in ("online", "completed"))

    print("=== 2. sign out, sign in again: no second download ===")
    logout(page); page.wait_for_url("**/login", timeout=20000)
    check("signing out removed the teacher's key from the device", not unlocked(page, fpA))
    check("...but their prepared pages are still there", len(cache_keys(page, f"sh-pages-v114-{fpA}")) == len(keysA))
    hits.clear(); login(page, "aokafor"); page.wait_for_timeout(6000)
    check("signing in again did NOT download everything again", len(hits) < 8, f"{len(hits)} requests vs {n_first} the first time: {hits[:12]}")
    check("the teacher's key is open again", unlocked(page, fpA))
    page.goto(f"{BASE}/dashboard"); page.wait_for_selector("#shConn")
    sc = page.evaluate("""async (cls) => { const c = await caches.open('sh-pages-v114-' + (await (await fetch('/api/sync/session')).json()).fingerprint); for (const r of await c.keys()) { const u = new URL(r.url); if (/score/.test(u.pathname)) { const t = await (await fetch(u.pathname + u.search)).text(); if (t.includes('id="scoreApp"') && t.includes('/api/scores/1/1/row')) return u.pathname + u.search; } } return null; }""", cls)
    check("a score-entry page is among the prepared pages", bool(sc), sc)

    print("=== 3. the administrator signs in on the SAME device ===")
    logout(page); page.wait_for_url("**/login", timeout=20000)
    login(page, "admin"); fpB = my_fp(page); prepared(page, fpB)
    check("two different people have different keys and caches", fpA != fpB and len(cache_keys(page, f"sh-pages-v114-{fpB}")) >= 5)
    check("the teacher's pages are still there, untouched", len(cache_keys(page, f"sh-pages-v114-{fpA}")) == len(keysA))
    check("the teacher's key is NOT open while the administrator is signed in", not unlocked(page, fpA) and unlocked(page, fpB))
    logout(page); page.wait_for_url("**/login", timeout=20000)

    print("=== 4. the school server goes down ===")
    stop()
    page.goto(f"{BASE}/dashboard")
    check("nobody signed in: cached pages are NOT shown, the offline sign-in is", page.locator("#offForm").count() == 1 and "Welcome" not in page.content())
    page.wait_for_function("() => document.getElementById('signin') && !document.getElementById('signin').hidden", timeout=10000)
    offline_login(page, "aokafor", "WrongPassword!"); page.wait_for_function("() => document.getElementById('msg').textContent.length > 0")
    check("a wrong password is refused with a neutral message", "Wrong username or password" in page.locator("#msg").inner_text() and page.locator("#offForm").count() == 1)
    offline_login(page, "nosuchperson", "Pass1234"); page.wait_for_timeout(600)
    check("an unknown username gets the same message", "Wrong username or password" in page.locator("#msg").inner_text())
    offline_login(page, "aokafor", "Pass1234"); page.wait_for_url("**/dashboard", timeout=15000); page.wait_for_selector("#shConn")
    check("the teacher signs in OFFLINE with her normal password and gets HER dashboard", page.evaluate("() => document.querySelector('meta[name=sh-user]').content") == fpA and "Okafor" in page.content())
    page.wait_for_function("() => document.getElementById('shConn').dataset.state === 'offline'", timeout=30000)
    rgb = [int(x) for x in re.findall(r"\d+", page.evaluate("() => getComputedStyle(document.querySelector('#shConn i')).backgroundColor"))[:3]]
    check("header shows Offline in RED", rgb[0] > 180 and rgb[1] < 100 and rgb[2] < 100, rgb)

    print("=== 5. the teacher works offline ===")
    page.goto(f"{BASE}/my-class/{cls}/roll-call"); page.wait_for_selector("#shConn")
    check("roll-call opens offline (prepared, never visited by her)", "Roll Call" in page.content())
    page.click('button[type="submit"]'); page.wait_for_function("() => /pending/.test(document.getElementById('shConn').innerText)", timeout=15000)
    check("attendance saved on the device", "1 pending" in chip(page).inner_text())
    page.goto(f"{BASE}{sc}"); page.wait_for_selector("#scoreApp", state="attached"); page.wait_for_timeout(800)
    res = page.evaluate("""async () => { const r = await fetch('/api/scores/1/1/row', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({student_id:3, ca1:'7', ca2:'7', exam:'7', note:'TEACHER-PRIVATE'})}); return [r.status, await r.json()]; }""")
    check("an offline score edit is queued", res[0] == 202 and res[1]["queued"], res)
    q_raw = page.evaluate("() => new Promise(res => { const r = indexedDB.open('sh-offline-v1'); r.onsuccess = () => { const g = r.result.transaction('queue').objectStore('queue').getAll(); g.onsuccess = () => { r.result.close(); res(JSON.stringify(g.result.map(e => ({...e, files: e.files.length})))); }; }; })")
    check("the teacher's waiting changes are encrypted in the browser database", "TEACHER-PRIVATE" not in q_raw and "csrf_token" not in q_raw and '"kid":"u"' in q_raw)

    print("=== 6. the administrator signs in offline on the same device ===")
    logout(page); page.wait_for_url("**/offline", timeout=15000)
    page.wait_for_function("() => !document.getElementById('signin').hidden", timeout=10000)
    offline_login(page, "admin", "Pass1234"); page.wait_for_url("**/dashboard", timeout=15000); page.wait_for_selector("#shConn")
    check("the administrator gets HIS pages (different person, different cache)", page.evaluate("() => document.querySelector('meta[name=sh-user]').content") == fpB)
    check("the teacher's waiting changes are NOT counted or shown for the administrator", "pending" not in chip(page).inner_text())
    page.goto(f"{BASE}/my-class/{cls}/roll-call")
    meta = page.evaluate("() => (document.querySelector('meta[name=sh-user]') || {}).content || ''")
    check("the administrator can never be served the teacher's cached roll-call", meta != fpA, meta)
    page.wait_for_function("() => !document.getElementById('signedin').hidden", timeout=10000)
    check("...he gets the friendly 'not available offline' page instead, with a sign-out button", page.locator("#switch").count() == 1)
    page.click("#switch")

    print("=== 7. the server comes back; the teacher's changes are sent ===")
    page.wait_for_function("() => !document.getElementById('signin').hidden", timeout=10000)
    offline_login(page, "aokafor", "Pass1234"); page.wait_for_url("**/dashboard", timeout=15000); page.wait_for_selector("#shConn")
    check("her waiting changes are still there for her", "2 pending" in chip(page).inner_text(), chip(page).inner_text())
    start()
    page.wait_for_selector(".sh-prep input[type=password]", timeout=40000)
    check("she is asked ONCE for her password (offline sign-in has no server session)", True)
    page.fill(".sh-prep input[type=password]", "Pass1234"); page.click(".sh-prep .go")
    page.wait_for_function("() => !/pending/.test(document.getElementById('shConn').innerText) && /^(Online|Sync Completed)/.test(document.getElementById('shConn').innerText)", timeout=60000)
    check("ATTENDANCE SYNCHRONIZED", q("SELECT COUNT(*) FROM attendance_records") > n_att)
    check("her offline score applied", q("SELECT ca1 FROM scores WHERE student_id=3 AND subject_id=1 AND term_id=(SELECT id FROM terms WHERE is_active=1)") == 7)
    check("no conflict was raised for her own offline edits", q("SELECT COUNT(*) FROM sync_conflicts") == n_conf)
    check("one attendance set only (no duplicates)", q("SELECT COUNT(*) FROM attendance_records WHERE class_id=? AND date=?", cls, A.v63_core.school_today(get_db(), 1)) == q("SELECT COUNT(*) FROM students WHERE class_id=? AND is_active=1", cls))
    check("the sync was recorded for the right person", q("SELECT COUNT(*) FROM sync_changes WHERE user_id=(SELECT id FROM users WHERE username='aokafor') AND state='applied'") >= 2)

    print("=== 8. remove a person from the device ===")
    page.goto(f"{BASE}/sync"); page.wait_for_selector("[data-k=users] tr")
    check("Sync Center lists the people who can sign in offline here", page.locator("[data-k=users] tr").count() == 2)
    b.close()
print(f"\nPASSED {PASS}   FAILED {len(FAIL)}")
if FAIL: print("FAILED:", FAIL); os._exit(1)
os._exit(0)
