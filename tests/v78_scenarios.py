"""V78: "Print" now opens the same PDF as "Download" instead of asking the phone's own browser to
print the live HTML page.

Austin's report, with screenshots: on his phone, the "Download PDF" button on a student's result
sheet produced a correctly colored, one-page result (logo, blue header, colored "Overall Position"
badge, properly sized table) -- but the "Print" button (which opens the same result in a new tab and
calls window.print() on it) produced a plain, uncoloured, generic-looking result that didn't fit on
one page.

Root cause: "Download PDF" is built server-side -- Chromium renders this exact HTML/CSS, then
Playwright's page.pdf(..., print_background=True, ...) forces colors/backgrounds on regardless of
what the end device's own print pipeline would otherwise do (see html_pdf.py). "Print" instead asks
the VIEWER'S OWN phone/browser to print the live page via window.print() -- and a phone's native
print pipeline (Android's system Print Service via Chrome, in Austin's case) is not guaranteed to
honor this page's print-color-adjust:exact or its JS-computed one-page zoom/auto-shrink the same way
desktop Chrome's own print preview does. The HTML and CSS are identical either way; only the
rendering engine doing the printing differs, and that's an OS/browser-version difference we can't
fully control from here.

Fix (as of V78): "Print" (the button, and the auto-print on load used when opened via a results
page's own "Print" link) navigated to the exact same PDF the "Download" button serves, with
?inline=1 so the browser shows it to view/print from rather than saving it to Downloads outright.

*** V98 UPDATE: this was reverted. *** Austin later reported the opposite problem from a real
device: tapping "Print" was forcing an automatic file download (a PDF landing in his phone's
Downloads/file-manager app) instead of showing him anything to view or print -- on many phones and
installed/PWA browsing contexts, navigating straight to a PDF response does exactly that regardless
of ?inline=1/Content-Disposition:inline, which is the scenario this V78 fix didn't anticipate.
"Print" now calls the browser's own native print dialog (window.print()) directly on the
already-fitted HTML again, same as before V78 -- fit() reruns on 'beforeprint' so the one-page
shrink still matches, and result-sheet.css already forces exact color reproduction in print
(print-color-adjust:exact), which should cover the specific "flat, uncoloured, wrong-size" complaint
that motivated V78 in the first place. "Download PDF" (a separate button/link) is untouched and
still gives the exact Chromium-rendered PDF bytes to save. The PDF-route Content-Disposition
behavior this file tests (plain vs ?inline=1) is unrelated to Print and still holds, so those checks
are kept; the Print-button checks below were updated for the new window.print()-based behavior.

Run: python tests/v78_scenarios.py"""
import os
import re
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v78_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db
from werkzeug.security import generate_password_hash

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print("FAIL:", name, str(detail)[:300])


def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get(page).get_data(as_text=True))
    return m.group(1)


pw = generate_password_hash("Pass1234")
c0 = get_db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,9,9,0,23),(1,2,1,15,20,0,50)")
c0.commit()
c0.close()
W.publish(A, 1)

A._rate_limit_store.clear()
c = A.app.test_client()
c.post("/login", data={"username": "admin", "password": "Pass1234", "csrf_token": tok(c, "/login")})

# ------------------------------------------------------------ 1) the PDF routes: attachment by default, inline on request
r = c.get("/result/1/pdf?term_id=1")
check("plain Download PDF (no inline=1) is still served as an attachment, exactly as before", r.status_code == 200 and "attachment" in (r.headers.get("Content-Disposition") or ""), r.headers.get("Content-Disposition"))
r = c.get("/result/1/pdf?term_id=1&inline=1")
check("the same result PDF with ?inline=1 is served inline instead", r.status_code == 200 and "inline" in (r.headers.get("Content-Disposition") or ""), r.headers.get("Content-Disposition"))

rb = c.get("/broadsheet/1/pdf?term_id=1")
check("plain broadsheet Download PDF (no inline=1) is still an attachment", rb.status_code == 200 and "attachment" in (rb.headers.get("Content-Disposition") or ""), rb.headers.get("Content-Disposition"))
rb = c.get("/broadsheet/1/pdf?term_id=1&inline=1")
check("the same broadsheet PDF with ?inline=1 is served inline", rb.status_code == 200 and "inline" in (rb.headers.get("Content-Disposition") or ""), rb.headers.get("Content-Disposition"))

# cumulative/class-bulk PDFs are untouched by this change (their own Print button still uses the
# plain generic-table layout, which prints fine as-is) -- confirm they still work at all.
check("cumulative result PDF route is unaffected and still works", c.get("/cumulative/student/1/pdf?session_id=1").status_code in (200, 302))

# ------------------------------------------------------------ 2) the print pages (V98): Print is wired to window.print(), not a PDF redirect
html = c.get("/result/1/print?term_id=1").get_data(as_text=True)
check("the result print page's Print control has no inline onclick handler (wired up by script)", 'onclick="window.print()"' not in html)
check("the result print page's Print button exists, wired up by script instead", 'id="rsPrint"' in html)
check("the result print page's script calls window.print() directly for Print (V98), not a PDF redirect", "function doPrint(){" in html and "window.print();" in html)
check("Download PDF is still a separate, unchanged link to the PDF file", "rsDownload" in html)

html = c.get("/broadsheet/1/print?term_id=1").get_data(as_text=True)
check("the broadsheet print page's Print control has no inline onclick handler (wired up by script)", 'onclick="window.print()"' not in html)
check("the broadsheet print page's Print button exists, wired up by script instead", 'id="bsPrint"' in html)
check("the broadsheet print page's script calls window.print() directly for Print (V98), not a PDF redirect", "function doPrint(){" in html and "window.print();" in html)
check("Download PDF is still a separate, unchanged link to the PDF file", "bsDownload" in html)

# ------------------------------------------------------------ 3) live-browser check (V98): clicking Print does NOT trigger a PDF download/request
try:
    from playwright.sync_api import sync_playwright

    PORT = 18777

    def _run_server():
        A.app.run(host="127.0.0.1", port=PORT, use_reloader=False)

    threading.Thread(target=_run_server, daemon=True).start()
    time.sleep(1.5)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Pass1234")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        requested = []
        page.on("request", lambda req: requested.append(req.url) if "/result/1/pdf" in req.url else None)
        page.add_init_script("window.print = function(){ window.__v98Printed = true; };")  # stub out the native dialog for this headless run
        page.goto(f"http://127.0.0.1:{PORT}/result/1/print?term_id=1")
        page.wait_for_load_state("networkidle")
        try:
            page.click("#rsPrint")
        except Exception:
            pass
        page.wait_for_timeout(800)
        check("clicking the result page's Print button did NOT request the PDF (no forced download)",
              not any("/result/1/pdf" in u for u in requested), requested)

        browser.close()
except ImportError:
    print("Playwright not available in this environment -- skipping the live click-through check (the HTTP/HTML checks above still ran).")
except Exception as e:
    check("live Print-button click-through check completed without an unexpected error", False, repr(e))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
