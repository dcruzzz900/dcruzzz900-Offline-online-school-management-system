"""V116 end-to-end in a real browser: ONE login page for online and offline use.
 1. device never used online by anybody: the login page still opens offline, says so, and REFUSES offline sign-in (no first-time offline login)
 2. online: the same page signs in through Flask (teacher and admin keep their own dashboards / roles)
 3. offline afterwards: the SAME page signs in on the device - wrong password and unknown people refused with a neutral message
 4. connectivity is detected automatically (badge flips when the server stops / returns) and a stale offline copy gets a fresh CSRF token
Run: python tests/v116_unified_login_e2e.py   (needs playwright + chromium)"""
import os, re, sys, tempfile, threading, time, logging
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v116e2e_"); sys.path.insert(0, ROOT); os.chdir(ROOT)
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
c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.commit(); c0.close()
A.app.config["TESTING"] = False; PORT = 18616; BASE = f"http://localhost:{PORT}"
srv = None
def start():
    global srv
    srv = make_server("127.0.0.1", PORT, A.app, threaded=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
def stop(): srv.shutdown(); srv.server_close()
F = "#unifiedLoginForm"
def badge(page): return page.locator("#loginConn").get_attribute("data-state")
def mode(page): return page.locator(F).get_attribute("data-mode")
def wait_mode(page, m, t=25000): page.wait_for_selector(f'{F}[data-mode="{m}"]', timeout=t)
def shell_cached(page, t=30):
    end = time.time() + t
    while time.time() < end:
        if page.evaluate("async () => { const ks = await caches.keys(); for (const k of ks) { if (await (await caches.open(k)).match('/login')) return true } return false }"): return True
        time.sleep(0.5)
    return False
def submit(page, user, pw):
    page.fill(f'{F} input[name="username"]', user); page.fill(f'{F} input[name="password"]', pw); page.click(f'{F} button[type="submit"]')
def logout(page): page.evaluate("() => document.querySelector('a[href$=\"/logout\"]').click()")
start()
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(); page = ctx.new_page(); page.on("dialog", lambda d: d.accept())

    print("=== 1. a device nobody has signed in on yet ===")
    page.goto(f"{BASE}/login"); wait_mode(page, "online")
    check("online: the page shows the Online state", badge(page) == "online" and "school server" in page.locator("#loginConn").inner_text())
    page.evaluate("async () => { await navigator.serviceWorker.ready }")
    check("the login page is kept for offline use (anonymous copy)", shell_cached(page))
    page.reload(); wait_mode(page, "online"); page.wait_for_timeout(1500)     # now under service-worker control
    stop()
    page.reload(); wait_mode(page, "offline")
    check("offline: the SAME login page still opens", page.locator(F).count() == 1 and "Sign in" in page.content())
    check("offline + nobody enrolled: told the device is not set up", badge(page) == "offline_new" and "not been set up" in page.locator("#loginConn").inner_text(), badge(page))
    submit(page, "aokafor", "Pass1234"); page.wait_for_selector("#loginOfflineMsg:not([hidden])", timeout=10000)
    check("first-time OFFLINE sign-in is refused", "Connect to the internet and sign in once" in page.locator("#loginOfflineMsg").inner_text() and "/login" in page.url)
    stored = page.evaluate("() => sessionStorage.getItem('sh-login')")
    check("the typed password is not left in the browser after an offline attempt", stored is None, stored)

    print("=== 2. online sign-in goes through Flask; roles are untouched ===")
    start(); wait_mode(page, "online", 30000)
    check("the page notices the school server is back by itself", badge(page) == "online")
    submit(page, "aokafor", "Pass1234"); page.wait_for_url("**/dashboard", timeout=20000); page.wait_for_selector("#shConn", timeout=20000)
    check("the teacher lands on HER dashboard (server-side sign-in)", "Okafor" in page.content() and page.evaluate("async () => (await (await fetch('/api/sync/session')).json()).role") == "teacher")
    page.wait_for_function("() => document.getElementById('shConn').dataset.state === 'online'", timeout=20000); page.wait_for_timeout(2500)
    logout(page); page.wait_for_selector(F, timeout=15000); wait_mode(page, "online")
    submit(page, "admin", "Pass1234"); page.wait_for_url("**/dashboard", timeout=20000); page.wait_for_selector("#shConn", timeout=20000)
    check("the administrator signs in on the same page and keeps the admin role", page.evaluate("async () => (await (await fetch('/api/sync/session')).json()).role") == "admin")
    page.wait_for_timeout(2500); logout(page); page.wait_for_selector(F, timeout=15000); wait_mode(page, "online")
    submit(page, "aokafor", "WrongPassword!"); page.wait_for_selector(".alert, .flash, [role=alert]", timeout=10000)
    check("online: a wrong password is still refused by the server", page.locator(F).count() == 1 and "/dashboard" not in page.url)

    print("=== 3. the same page, now offline, for people who signed in here before ===")
    page.goto(f"{BASE}/login"); wait_mode(page, "online"); page.wait_for_timeout(1500)
    stop()
    page.reload(); wait_mode(page, "offline")
    check("offline + enrolled people: told they can sign in with this device", badge(page) == "offline_ok", badge(page))
    submit(page, "aokafor", "WrongPassword!"); page.wait_for_selector("#loginOfflineMsg:not([hidden])", timeout=10000)
    check("wrong password refused with the neutral message", "Wrong username or password" in page.locator("#loginOfflineMsg").inner_text() and "/login" in page.url)
    submit(page, "nosuchperson", "Pass1234"); page.wait_for_function("() => { const m = document.getElementById('loginOfflineMsg'); return m && !m.hidden && m.textContent.length > 0 }", timeout=10000)
    check("an unknown person gets the same message (no account probing)", "Wrong username or password" in page.locator("#loginOfflineMsg").inner_text())
    submit(page, "aokafor", "Pass1234"); page.wait_for_url("**/dashboard", timeout=20000); page.wait_for_selector("#shConn", timeout=20000)
    check("the teacher signs in OFFLINE on the same page and gets her own dashboard", "Okafor" in page.content() and page.evaluate("() => document.querySelector('meta[name=sh-user]').content") != "")
    page.wait_for_function("() => document.getElementById('shConn').dataset.state === 'offline'", timeout=30000)
    check("header shows Offline", True)
    logout(page); page.wait_for_selector(F, timeout=20000); wait_mode(page, "offline")
    submit(page, "admin", "Pass1234"); page.wait_for_url("**/dashboard", timeout=20000); page.wait_for_selector("#shConn", timeout=20000)
    check("the administrator signs in offline too (own key, own role)", "Okafor" not in page.content())

    print("=== 4. back online: the offline copy of the page gets a fresh token ===")
    logout(page); page.wait_for_selector(F, timeout=20000); wait_mode(page, "offline")
    tok_before = page.locator(f'{F} input[name="csrf_token"]').input_value()
    start(); wait_mode(page, "online", 40000); page.wait_for_timeout(1200)
    tok_after = page.locator(f'{F} input[name="csrf_token"]').input_value()
    check("a stale token from the cached copy is replaced when the connection returns", tok_before != tok_after, (tok_before[:8], tok_after[:8]))
    submit(page, "aokafor", "Pass1234"); page.wait_for_url("**/dashboard", timeout=20000)
    check("and the online sign-in then works from that same page", "Okafor" in page.content())
    b.close()
stop()
print(f"\nPASSED {PASS}   FAILED {len(FAIL)}")
if FAIL: print("Failures:", FAIL); sys.exit(1)
