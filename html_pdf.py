"""PDF from the SAME HTML as the print view.

The result sheet is rendered once, by templates/result_print.html + static/css/result-sheet.css. The browser prints
that page; this module prints it too (headless Chromium, print media), so Preview = Print = PDF = Download. Nothing is
drawn a second time, so the layouts cannot drift apart.

Subresources (CSS, logo, passport, signatures) are fetched through the Flask app itself with the caller's own session, so
tenant isolation and permissions apply exactly as they do for the browser; any request to another host is refused.
If no Chromium is installed render_documents() returns None and the caller falls back to the older reportlab builder.
"""
import io
import logging
import threading
from urllib.parse import urlparse

log = logging.getLogger("html_pdf")
_lock = threading.Lock()
_state = {"checked": False, "ok": False}
HOST = "sheet.local"
DOC_URL = f"http://{HOST}/__document__"


def engine_available():
    if _state["checked"]:
        return _state["ok"]
    with _lock:
        if _state["checked"]:
            return _state["ok"]
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
                b.close()
            _state["ok"] = True
        except Exception as exc:
            log.warning("HTML->PDF engine unavailable (%s); falling back to the reportlab builder", str(exc)[:160])
            _state["ok"] = False
        _state["checked"] = True
    return _state["ok"]


def render_documents(app, session_data, documents):
    """documents: list of full HTML strings. Returns a list of PDF bytes (one per document) or None if unavailable."""
    if not documents or not engine_available():
        return None
    from playwright.sync_api import sync_playwright
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(session_data)
    current = {"html": ""}

    def handle(route):
        req = route.request
        u = urlparse(req.url)
        if u.netloc != HOST:
            return route.abort()
        if u.path == "/__document__":
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=current["html"])
        resp = client.get(u.path + (("?" + u.query) if u.query else ""))
        return route.fulfill(status=resp.status_code, headers={"content-type": resp.content_type}, body=resp.get_data())

    out = []
    try:
        with _lock, sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                ctx = browser.new_context()
                ctx.route("**/*", handle)
                for html in documents:
                    current["html"] = html
                    page = ctx.new_page()
                    page.goto(DOC_URL, wait_until="load")
                    page.emulate_media(media="print")
                    page.wait_for_timeout(120)      # let the one-page fit script run
                    out.append(page.pdf(format="A4", print_background=True, prefer_css_page_size=True,
                                        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}))
                    page.close()
            finally:
                browser.close()
    except Exception:
        log.exception("HTML->PDF failed; falling back to reportlab")
        return None
    return out


def merge(pdfs):
    from pypdf import PdfWriter, PdfReader
    w = PdfWriter()
    for b in pdfs:
        for pg in PdfReader(io.BytesIO(b)).pages:
            w.add_page(pg)
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf
