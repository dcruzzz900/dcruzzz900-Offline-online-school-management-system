"""End-to-end scenarios for the V75 requirement: mobile/tablet/desktop responsiveness pass.

Audit first (see V75_IMPLEMENTATION_NOTES.md for the full writeup): the app shell (sidebar +
hamburger toggle) already had working responsive collapse/expand logic, and the viewport meta
tag, table-overflow handling and grid breakpoints were already in reasonable shape almost
everywhere. The ONE genuine, concretely verified defect — found by actually rendering the
page in a real browser at a sweep of viewport widths, not by guessing — was a ~49px "dead
zone" (viewport widths from 1001px to 1049px, which includes 1024px, the standard tablet
landscape width) where THREE separate, slightly-drifted `@media` breakpoints across
style.css/style.css/ai-ui.css disagreed with each other: the sidebar collapsed off-screen at
<=1050px, but the hamburger button needed to bring it back only appeared at <=1000px — so in
that gap, navigation was completely unreachable without manually resizing the browser window.

Fixed by changing the one drifted breakpoint (1050px -> 1000px) so all three agree. This file
verifies the fix two ways:
1. Static source checks — the drifted breakpoint is gone, every sidebar-collapse @media rule
   across the app now uses the same value.
2. Live rendering checks, via a real headless browser (the bug was invisible to a plain HTTP
   fetch — the HTML is byte-identical whether broken or fixed, only the *computed* CSS
   differs) — sweeping a range of viewport widths including the exact widths that were
   broken before the fix, confirming the sidebar is never left off-screen with no way to
   reopen it, and that clicking the toggle actually opens the sidebar at mobile/tablet widths
   without breaking the normal desktop layout above the breakpoint.

(own process, fresh DB). Run: python tests/v75_scenarios.py"""
import logging
import os
import re
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v75_")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import app as A
from db import get_db
from werkzeug.security import generate_password_hash

logging.disable(logging.CRITICAL)

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print("FAIL:", name, str(detail)[:300])


# ---------------------------------------------------------------- 1) static source checks
css = open(os.path.join(ROOT, "static", "css", "style.css"), encoding="utf-8").read()
ai_css = open(os.path.join(ROOT, "static", "css", "ai-ui.css"), encoding="utf-8").read()

check("the drifted 1050px sidebar-collapse breakpoint is gone from style.css", "@media(max-width:1050px)" not in css, css.count("@media(max-width:1050px)"))
sidebar_breakpoints = set(re.findall(r"@media\s*\(max-width:(\d+)px\)\{[^}]*\.app-sidebar\{transform", css + ai_css))
check("every remaining .app-sidebar collapse @media rule (style.css + ai-ui.css) now agrees on exactly one breakpoint value",
      sidebar_breakpoints == {"1000"}, sidebar_breakpoints)

# ---------------------------------------------------------------- 2) live rendering checks (real headless browser)
pw = generate_password_hash("Pass1234")
c0 = get_db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.commit()
c0.close()

A.app.config["TESTING"] = False
A.app.config["PROPAGATE_EXCEPTIONS"] = False
PORT = 18611


def _run_server():
    A.app.run(host="127.0.0.1", port=PORT, use_reloader=False)


server_thread = threading.Thread(target=_run_server, daemon=True)
server_thread.start()
time.sleep(1.5)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Pass1234")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Sweep a wide range of viewport widths, including every width that was previously inside the
        # 1001-1049px dead zone (1010, 1024 — standard tablet landscape, 1040), plus the boundary (1000,
        # 1001) and clearly-desktop/clearly-mobile widths as controls.
        widths = [1300, 1100, 1060, 1050, 1049, 1040, 1024, 1010, 1001, 1000, 999, 900, 768, 600, 400, 375]
        broken_widths = []
        for w in widths:
            page.set_viewport_size({"width": w, "height": 800})
            page.goto(f"http://127.0.0.1:{PORT}/dashboard")
            page.wait_for_load_state("networkidle")
            toggle_display = page.eval_on_selector(".sidebar-toggle", "el => getComputedStyle(el).display")
            sidebar_transform = page.eval_on_selector(".app-sidebar", "el => getComputedStyle(el).transform")
            sidebar_hidden = sidebar_transform != "none"
            toggle_visible = toggle_display != "none"
            # The invariant: the sidebar is NEVER off-screen while its reopen button is also hidden.
            if sidebar_hidden and not toggle_visible:
                broken_widths.append(w)
        check("no viewport width leaves the sidebar off-screen with the hamburger button also hidden (checked across 16 widths, 1001-1049px most important)",
              not broken_widths, broken_widths)

        # Clicking the toggle actually opens the sidebar at mobile/tablet widths (not just CSS that LOOKS right).
        for w in (1000, 768, 375):
            page.set_viewport_size({"width": w, "height": 800})
            page.goto(f"http://127.0.0.1:{PORT}/dashboard")
            page.wait_for_load_state("networkidle")
            before = page.eval_on_selector(".app-sidebar", "el => getComputedStyle(el).transform")
            page.click(".sidebar-toggle")
            page.wait_for_timeout(250)
            after = page.eval_on_selector(".app-sidebar", "el => getComputedStyle(el).transform")
            nav_link_visible = page.is_visible(".app-sidebar nav a")
            check(f"at width={w}, clicking the hamburger actually opens the sidebar (nav links become reachable)",
                  before != "none" and after == "none" and nav_link_visible, (before, after, nav_link_visible))

        # Desktop (above the breakpoint) must be unaffected: toggle hidden, sidebar in its normal fixed position.
        page.set_viewport_size({"width": 1300, "height": 800})
        page.goto(f"http://127.0.0.1:{PORT}/dashboard")
        page.wait_for_load_state("networkidle")
        check("desktop width (1300px) still shows the sidebar normally with no hamburger button",
              page.eval_on_selector(".sidebar-toggle", "el => getComputedStyle(el).display") == "none"
              and page.eval_on_selector(".app-sidebar", "el => getComputedStyle(el).transform") == "none")

        browser.close()
except ImportError:
    print("Playwright not available in this environment — skipping live rendering checks (static checks above still ran).")
except Exception as e:
    check("live rendering checks completed without an unexpected error", False, repr(e))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
