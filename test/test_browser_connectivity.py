"""Automatic, VERIFIED connectivity handling in a real browser. In none of these does the
browser itself say it is offline (navigator.onLine stays true) - the app has to notice
that the SERVER can't be reached, keep working from the local database, and go back
online by itself when the server answers again, syncing in the background."""
import re
import socket
import threading
import time

from helpers import fresh_app, LiveServer, wait_until

try:
    from playwright.sync_api import sync_playwright
except Exception:          # pragma: no cover
    sync_playwright = None


def _login(page, base, user="admin", password="admin123"):
    page.goto(base + "/login")
    page.fill("input[name=username]", user)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url(re.compile(r".*/app$"))
    page.wait_for_selector("h1")


def _wait_pill(page, fragment, timeout=45):
    wait_until(page, f"(document.getElementById('syncPill') && document.getElementById('syncPill').textContent.includes({fragment!r}))", timeout=timeout)


def _wait_db(fn, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.4)
    raise AssertionError("server never received it")


class Portal:
    """Answers EVERYTHING with a 200 HTML 'log in to the wifi' page, like a captive portal."""
    def __init__(self, port):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for _ in range(40):
            try:
                self.sock.bind(("127.0.0.1", port))
                break
            except OSError:
                time.sleep(0.25)
        self.sock.listen(20)
        self.running = True
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        body = b"<html><body><h1>Sign in to the wifi</h1></body></html>"
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                conn.recv(4096)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
            finally:
                conn.close()

    def stop(self):
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)      # wakes the thread blocked in accept()
        except OSError:
            pass
        self.sock.close()


def test_server_unreachable_while_browser_says_online_switches_modes_by_itself_and_recovers():
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
    portal = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login(page, server.base)
            wait_until(page, f"OfflineDB.getMeta({ids['school']}, 'last_sync_at').then(v => !!v)", timeout=40)
            _wait_pill(page, "Online — Synced")

            # ---- the server goes away; the wifi is still "connected" as far as the browser knows
            port = server.port
            server.down()
            assert page.evaluate("navigator.onLine") is True
            _wait_pill(page, "Offline — Saved Locally")                     # noticed by the monitor, nobody clicked anything
            assert page.evaluate("navigator.onLine") is True
            assert "Admin Dashboard" in page.locator("h1").first.inner_text()       # same screen, same layout

            # ---- keep working: same Score Entry screen, saved to the local database
            page.click("#dashWork >> text=Score Entry")
            page.select_option("#seClassSelect", str(ids["cls"]))
            wait_until(page, "document.querySelectorAll('#seSubjectSelect option').length > 1")
            page.select_option("#seSubjectSelect", str(ids["subj"]))
            page.wait_for_selector("tr[data-student] input.ca1")
            page.locator("tr[data-student] input.ca1").nth(0).fill("14")
            page.click("#saveScoresBtn")
            page.wait_for_function("document.querySelector('#scoreMsg').textContent.includes('Saved 1 score row')", timeout=10000)
            _wait_pill(page, "Offline — Saved Locally")

            # ---- a captive portal answers 200 HTML to everything: still NOT online
            portal = Portal(port)
            time.sleep(20)                                                   # longer than a probe cycle
            assert "Offline" in page.evaluate("document.getElementById('syncPill').textContent")
            portal.stop()
            portal = None

            # ---- the real server comes back: online again on its own, and the entry syncs in the background
            server.up()
            _wait_pill(page, "Online — Synced", timeout=60)
            _wait_db(lambda: __import__("db").get_db().execute("SELECT 1 FROM scores WHERE ca1=14").fetchone(), timeout=30)
            browser.close()
    finally:
        if portal:
            portal.stop()
        server.down()


def test_a_server_rendered_page_tells_you_when_the_connection_is_lost_and_leads_back_to_the_app():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    import db
    school = db.get_db().execute("SELECT id FROM schools").fetchone()[0]
    server = LiveServer(m.app).up()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login(page, server.base)
            wait_until(page, f"OfflineDB.getMeta({school}, 'last_sync_at').then(v => !!v)", timeout=40)
            page.wait_for_timeout(800)
            page.goto(server.base + "/admin/terms")                          # one of the pages that only the server can do
            page.wait_for_selector("#syncPill")
            server.down()
            page.wait_for_selector("#connBanner", timeout=45000)
            assert "Connection lost" in page.inner_text("#connBanner")
            assert "Offline" in page.inner_text("#syncPill")
            page.click("#connBanner a")                                      # "Return to the app" works with no server
            page.wait_for_url(re.compile(r".*/app$"))
            page.wait_for_selector("#pwInput, h1")
            browser.close()
    finally:
        server.down()
