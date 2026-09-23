"""Dashboard date/time card: shows immediately, updates on its own every
second, and doesn't leak a duplicate ticking timer when navigating away
and back to the dashboard."""
import re
import time

from helpers import fresh_app, LiveServer

try:
    from playwright.sync_api import sync_playwright
except Exception:          # pragma: no cover
    sync_playwright = None


def _login(page, base, user, password):
    page.goto(base + "/login")
    page.fill("input[name=username]", user)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url(re.compile(r".*/app$"))
    page.wait_for_selector("h1")


def test_dashboard_datetime_card_renders_and_ticks_for_admin_and_teacher():
    if sync_playwright is None:
        return
    m, _ = fresh_app()
    server = LiveServer(m.app).up()
    base = server.base
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()

            _login(page, base, "admin", "admin123")
            page.wait_for_selector("#datetime-card")
            first = page.locator("#datetime-card-time").inner_text()
            assert re.match(r"\d{2}:\d{2}:\d{2} \(WAT\)", first)
            date_text = page.locator("#datetime-card-date").inner_text()
            assert re.match(r"[A-Za-z]+, \d{2}/\d{2}/\d{4}", date_text)

            time.sleep(2.2)
            second = page.locator("#datetime-card-time").inner_text()
            assert second != first, "clock did not tick"

            # Navigate away and back — must not leave two clocks ticking
            # (which would otherwise show garbled/duplicate updates).
            page.click("#navbarLinks >> text=Classes")
            page.wait_for_selector("h1")
            page.click("#navbarLinks >> text=Dashboard")
            page.wait_for_selector("#datetime-card")
            assert page.locator("#datetime-card").count() == 1

            ctx.close()
            browser.close()

            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            _login(page, base, "aokafor", "teacher123")
            page.wait_for_selector("#datetime-card")
            assert re.match(r"\d{2}:\d{2}:\d{2} \(WAT\)", page.locator("#datetime-card-time").inner_text())
    finally:
        server.down()
