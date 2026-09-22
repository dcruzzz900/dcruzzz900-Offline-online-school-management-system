"""Opening the app with no working connection, in a real browser with a real
service worker and the server genuinely unreachable:
  - the installed app's start page goes straight to the offline app, which asks
    for the person's normal password (no account list when there is only one);
  - guessing is throttled;
  - a connection that hangs (signal bars but nothing arrives) falls back too;
  - a phone that stays offline for weeks is locked out locally with a clear
    message, keeps every unsynced entry, and one online login renews it."""
import re
import socket
import threading
import time
from urllib.parse import urlparse

from helpers import fresh_app, LiveServer, wait_until

try:
    from playwright.sync_api import sync_playwright
except Exception:          # pragma: no cover
    sync_playwright = None

# Shift this browser's clock forward by localStorage.__test_shift_days (0 = real time).
CLOCK_SHIFT = """
(() => {
  const R = Date;
  const shift = () => { try { return (+localStorage.getItem('__test_shift_days') || 0) * 86400000; } catch (e) { return 0; } };
  class F extends R {
    constructor(...a) { if (a.length === 0) super(R.now() + shift()); else super(...a); }
    static now() { return R.now() + shift(); }
  }
  window.Date = F;
})();
"""


def _login_online(page, base, school_id):
    page.goto(base + "/login")
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", "admin123")
    page.click("button[type=submit]")
    page.wait_for_url(re.compile(r".*/app$"))
    page.evaluate("navigator.serviceWorker.ready.then(() => true)")
    wait_until(page, f"OfflineDB.getMeta({school_id}, 'last_sync_at').then(v => !!v)", timeout=30.0)
    page.wait_for_timeout(800)        # let the service worker finish caching the shell


def _school_id(m):
    import db
    c = db.get_db()
    sid = c.execute("SELECT id FROM schools").fetchone()[0]
    c.close()
    return sid


def test_opening_the_app_offline_asks_for_the_password_and_throttles_guessing():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    sid = _school_id(m)
    server = LiveServer(m.app).up()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login_online(page, server.base, sid)
            page.close()
            page = ctx.new_page()
            ctx.set_offline(True)
            server.down()
            for entry in ("/dashboard", "/", "/login"):       # every way of opening the app
                page.goto(server.base + entry)
                assert urlparse(page.url).path == "/app", (entry, page.url)
                page.wait_for_selector("#pwInput")
            assert page.locator("#backBtn").count() == 0       # one account: no picker, no "choose another"
            # wrong passwords: clear message, then the device makes you wait
            for i in range(5):
                page.fill("#pwInput", f"wrong-{i}")
                page.click("#unlockBtn")
                page.wait_for_function("document.querySelector('#unlockBtn') && !document.querySelector('#unlockBtn').disabled", timeout=15000)
            assert "Incorrect password" in page.locator("#pwError").inner_text()
            page.fill("#pwInput", "wrong-again")
            page.click("#unlockBtn")
            page.wait_for_function("document.querySelector('#pwError').textContent.includes('Too many')", timeout=15000)
            # even the RIGHT password waits out the delay
            page.fill("#pwInput", "admin123")
            page.click("#unlockBtn")
            page.wait_for_function("document.querySelector('#pwError').textContent.includes('Too many')", timeout=15000)
            assert page.locator("text=Offline Menu").count() == 0
            # clear the throttle (as time passing would) and the right password opens it
            page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('srs_unlock_')).forEach(k => localStorage.removeItem(k))")
            page.fill("#pwInput", "admin123")
            page.click("#unlockBtn")
            page.wait_for_selector("h1:has-text('Admin Dashboard')")
            browser.close()
    finally:
        server.down()


def test_a_hanging_connection_falls_back_to_the_offline_app():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    sid = _school_id(m)
    server = LiveServer(m.app).up()
    hang = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login_online(page, server.base, sid)
            page.close()
            page = ctx.new_page()
            port = server.port
            server.down()
            # something is listening on the port and accepts connections, but never answers
            for attempt in range(40):                              # the port can take a moment to free up
                hang = socket.socket()
                hang.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    hang.bind(("127.0.0.1", port))
                    break
                except OSError:
                    hang.close()
                    time.sleep(0.25)
            else:
                raise AssertionError("could not take over the port")
            hang.listen(20)
            held = []
            threading.Thread(target=lambda: [held.append(hang.accept()) for _ in range(20)], daemon=True).start()
            t0 = time.time()
            page.goto(server.base + "/dashboard", timeout=45000)
            waited = time.time() - t0
            assert urlparse(page.url).path == "/app", page.url
            assert 6 < waited < 25, waited                       # gave the network its 8 seconds, then moved on
            page.wait_for_selector("#pwInput")
            browser.close()
    finally:
        if hang:
            hang.close()
        server.down()


def test_phone_offline_for_weeks_is_locked_locally_keeps_its_work_and_one_login_renews_it():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    ids = dict(school=conn.execute("SELECT id FROM schools").fetchone()[0],
               cls=conn.execute("SELECT id FROM classes").fetchone()[0],
               subj=conn.execute("SELECT id FROM subjects ORDER BY id").fetchone()[0])
    conn.close()
    server = LiveServer(m.app).up()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            ctx.add_init_script(CLOCK_SHIFT)
            page = ctx.new_page()
            _login_online(page, server.base, ids["school"])
            page.close()

            # --- day 1, no signal: enter a score
            page = ctx.new_page()
            ctx.set_offline(True)
            server.down()
            page.goto(server.base + "/dashboard")
            page.fill("#pwInput", "admin123")
            page.click("#unlockBtn")
            page.wait_for_selector("h1:has-text('Admin Dashboard')")
            page.click("#dashWork >> text=Score Entry")
            page.select_option("#seClassSelect", str(ids["cls"]))
            page.wait_for_function("document.querySelectorAll('#seSubjectSelect option').length > 1")
            page.select_option("#seSubjectSelect", str(ids["subj"]))
            page.wait_for_selector("tr[data-student] input.ca1")
            page.locator("tr[data-student] input.ca1").nth(0).fill("13")
            page.click("#saveScoresBtn")
            page.wait_for_function("document.querySelector('#scoreMsg').textContent.includes('Saved 1 score row')", timeout=10000)
            page.close()

            # --- 40 days later, still no signal: the app is closed and reopened
            page = ctx.new_page()
            page.goto(server.base + "/app")
            page.evaluate("localStorage.setItem('__test_shift_days', '40')")
            page.goto(server.base + "/dashboard")
            page.wait_for_selector("#pwInput")
            page.fill("#pwInput", "admin123")
            page.click("#unlockBtn")
            page.wait_for_function("document.querySelector('#pwError').textContent.includes('Log in online')", timeout=15000)
            assert page.locator("text=Offline Menu").count() == 0              # locked out locally
            msg = page.locator("#pwError").inner_text()
            assert "still saved" in msg or "saved here" in msg, msg           # ...with a reassuring, actionable message
            pending = page.evaluate(f"OfflineDB.getPendingCounts({ids['school']})")
            assert pending["pending"] == 1, pending                          # nothing was lost

            # --- signal returns, the person follows the link and logs in with their normal password
            ctx.set_offline(False)
            server.up()
            page.evaluate("localStorage.removeItem('__test_shift_days')")     # (the clock is real again)
            page.click("text=Log in online to renew")
            page.fill("input[name=username]", "admin")
            page.fill("input[name=password]", "admin123")
            page.click("button[type=submit]")
            page.wait_for_url(re.compile(r".*/app$"))
            wait_until(page, f"OfflineDB.getPendingCounts({ids['school']}).then(c => c.pending === 0)", timeout=30.0)
            accounts = page.evaluate("OfflineAuth.listAccounts().then(a => a.map(x => x.device_id))")
            assert len(accounts) == 1                                          # same device, renewed - not a second one
            browser.close()
    finally:
        server.down()

    conn = db.get_db()
    row = conn.execute("SELECT ca1 FROM scores WHERE subject_id=? AND ca1=13", (ids["subj"],)).fetchone()
    assert row is not None, "the score entered offline weeks earlier reached the server"
    assert conn.execute("SELECT COUNT(*) FROM device_credentials").fetchone()[0] == 1
    conn.close()
