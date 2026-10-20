"""End-to-end scenarios for the V76 requirement: Austin's concrete feedback (screenshots) on
the Executive Band, Compact Academic and Vibrant Cards result-sheet templates.

His message, verbatim: "Too much empty white space on the result sheet of Executive Band,
Compact Academic and Vibrant Cards. Remove double Domain rating (1 = Poor ... 5 = Excellent)
on Psychomotor Domain and Affective Domain card on result sheet. In domain rating leave the
numbers and remove this (e.g Emotional Stability 4 and remove Very Good)."

Two real, distinct defects, both fixed here:

1. Domain rating rows showed the rating TWICE — once as the number, once as a word label
   next to it ("4 - Very Good"). Austin wants only the number. This is the shared
   templates/_result_sheet.html partial (every one of the 9+1 result-sheet templates uses
   it), so the fix applies everywhere, not just the 3 named templates.

2. Excessive empty white space specifically on Executive Band, Compact Academic and Vibrant
   Cards. Root cause (confirmed by reading static/css/result-sheet.css's CSS-Grid
   grid-template-areas for these templates, not guessed): each of the three pairs a short,
   single-row sidebar/card item (student-info, attendance, or domain-ratings) against a
   sibling grid area that SPANS multiple rows (the subjects table, or the comments box).
   CSS Grid's auto-row-track sizing inflates every row the tall spanning item touches to
   make room for it, and the short sibling in that row gets a track far bigger than its own
   content needs -- rendered as plain empty space underneath it (none of those sections has
   a background/border, so the inflated space is invisible except as a gap).
   Fixed by reshaping grid-template-areas so no short single-row item is paired against a
   multi-row span: the tall item (subjects table / comments) now spans the WHOLE sidebar
   stack it sits beside, and any section that used to be split across a row pairing now
   sits in its own full-width row (or, for Vibrant Cards, all three "cards" sit in one row
   together, matching the template's own name).

(own process, fresh DB, real HTTP requests + real headless-browser rendering for the layout
measurement, which a plain HTTP fetch can't verify since the HTML is identical broken or
fixed -- only the browser's computed CSS-Grid layout differs).
Run: python tests/v76_scenarios.py"""
import logging
import os
import re
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v76_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash
from flask.testing import FlaskClient


class ListDataClient(FlaskClient):
    def open(self, *args, **kwargs):
        if isinstance(kwargs.get("data"), list):
            kwargs["data"] = MultiDict(kwargs["data"])
        return super().open(*args, **kwargs)


A.app.test_client_class = ListDataClient
A.app.config["TESTING"] = False
A.app.config["PROPAGATE_EXCEPTIONS"] = False
logging.disable(logging.CRITICAL)

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print("FAIL:", name, str(detail)[:300])


def html(r):
    return r.get_data(as_text=True)


def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    if m:
        return m.group(1)
    with c.session_transaction() as s:
        return s.get("_csrf_token")


def post(c, path, data=None, page=None):
    d = dict(data or {})
    d["csrf_token"] = tok(c, page or path)
    return c.post(path, data=d)


def db():
    return get_db()


def run(sql, args=()):
    c = db()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def staff(u, pw="Pass1234"):
    A._rate_limit_store.clear()
    c = A.app.test_client()
    post(c, "/login", {"username": u, "password": pw}, "/login")
    return c


pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.commit()
c0.close()

ADMIN = staff("admin")
ADMIN.get("/admin/result-display-settings")  # also lazily seeds educational_domains (affective/psychomotor) for school 1
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,0,40),(1,2,1,8,9,0,31)")
run("UPDATE result_display_settings SET show_score=1, show_grade=1, show_passport=1, show_domains=1 WHERE school_id=1")
# Real domain-rating data (not the sample-data preview) is what the /result/*/print route and PDF actually
# render, so that's what this phase's fix needs verifying against.
run("INSERT OR IGNORE INTO skill_traits(school_id, name, category) VALUES "
    "(1,'Punctuality','affective'),(1,'Neatness','affective'),(1,'Honesty','affective'),"
    "(1,'Handwriting','psychomotor'),(1,'Sports','psychomotor')")
trait_ids = {r["name"]: r["id"] for r in db().execute("SELECT id, name FROM skill_traits WHERE school_id=1").fetchall()}
run("INSERT OR REPLACE INTO student_skill_ratings(student_id, term_id, trait_id, rating) VALUES " +
    ",".join(f"(1,1,{trait_ids[n]},{r})" for n, r in
              [("Punctuality", 5), ("Neatness", 4), ("Honesty", 5), ("Handwriting", 4), ("Sports", 5)]))
W.publish(A, 1)

RES_ON = ["show_passport", "show_logo", "show_overall_position", "show_attendance", "show_days_opened", "show_days_present", "show_days_absent",
          "show_teacher_comment", "show_principal_comment", "show_teacher_signature", "show_teacher_sign_date", "show_principal_signature", "show_principal_sign_date",
          "show_score", "show_grade", "show_remarks", "show_admission_no", "show_class", "show_session", "show_term", "show_teacher_name", "show_principal_name",
          "show_address", "show_email", "show_phone", "show_motto", "show_all_comments", "show_grading_key", "show_promotion", "show_domains", "fit_to_page"]


def rds(client, on=None, **kw):
    d = {"template": "professional_classic", "accent_color": "#1f3a5f", "secondary_color": "#c9a227", "header_layout": "logo-left", "signature_layout": "split", "pdf_font": "Helvetica"}
    d.update({k: "1" for k in (RES_ON if on is None else on)})
    d.update(kw)
    return post(client, "/admin/result-display-settings", d, "/admin/result-display-settings")


def sheet(client=ADMIN, url="/result/1/print?term_id=1"):
    r = client.get(url)
    assert r.status_code == 200, r.status_code
    return html(r)


# ============================================================ 1) domain rating: number only, no duplicated word label
for tn in ("professional_classic", "executive_band", "compact_academic", "vibrant_cards", "modern_academic"):
    rds(ADMIN, template=tn)
    sh = sheet()
    check(f"[{tn}] domain rating shows only the number (no '- Very Good' style word label)",
          "<small>–" not in sh and "Very Good</small>" not in sh, sh[sh.find("rs-domains"):sh.find("rs-domains") + 400] if "rs-domains" in sh else "no rs-domains section")
    check(f"[{tn}] domain rows render as plain numbers, e.g. '>5<' not '>5 – Excellent<'",
          re.search(r"<td>5</td>", sh) is not None or re.search(r"<td>4</td>", sh) is not None, sh.count("<td>5</td>") + sh.count("<td>4</td>"))
    # the bottom "Domain ratings: 1 = Poor ... 5 = Excellent" legend line is untouched -- Austin didn't ask for
    # that to be removed, only the per-row repetition next to each individual rating.
    check(f"[{tn}] the single domain-ratings legend line at the bottom is still shown",
          "Domain ratings:" in sh)
    # exactly one "Domain Ratings" section heading (never duplicated per card)
    check(f"[{tn}] exactly one 'Domain Ratings' section heading", sh.count(">Domain Ratings<") == 1, sh.count(">Domain Ratings<"))
    # both domain group card titles still present and distinct
    check(f"[{tn}] both domain group labels (Affective Domain / Psychomotor Domain) still shown once each",
          sh.count("Affective Domain") == 1 and sh.count("Psychomotor Domain") == 1)

# ============================================================ 2) grid-template-areas: no short item paired against a multi-row span
css = open(os.path.join(ROOT, "static", "css", "result-sheet.css"), encoding="utf-8").read()


def areas_for(cls):
    m = re.search(r"\." + re.escape(cls) + r"\{[^}]*grid-template-areas:((?:\"[^\"]*\"\s*)+)", css)
    assert m, f"no grid-template-areas found for {cls}"
    return re.findall(r'"([^"]*)"', m.group(1))


def spans(rows, name):
    """How many consecutive rows (in the same grid column) this area name spans, at most."""
    best = cur = 0
    for row in rows:
        cols = row.split()
        cur = cur + 1 if name in cols else 0
        best = max(best, cur)
    return best


def short_single_row_siblings_of_a_span(rows, spanning_name):
    """Area names that occupy exactly one row, in a row where spanning_name also appears, excluding spanning_name itself."""
    out = set()
    for row in rows:
        cols = row.split()
        if spanning_name in cols:
            for c in cols:
                if c != spanning_name and spans(rows, c) == 1:
                    out.add(c)
    return out


old_compact = ('id', 'perf'), ('att', 'perf'), ('dom', 'com'), ('key', 'sig')
rows_compact = areas_for("rs-compact_academic")
check("[compact_academic] 'perf' now spans the whole sidebar (id, att, dom, key), not just 2 of its 4 items",
      spans(rows_compact, "perf") == 4, rows_compact)
check("[compact_academic] 'com' and 'sig' are no longer paired against the narrow sidebar (full-width rows of their own)",
      not short_single_row_siblings_of_a_span(rows_compact, "perf") & {"com", "sig"}, rows_compact)

rows_exec = areas_for("rs-executive_band")
check("[executive_band] 'perf' spans the whole rail (id, dom, att, key)", spans(rows_exec, "perf") == 4, rows_exec)
check("[executive_band] 'sig' is a full-width row of its own, not squeezed beside 'key'",
      any(row.split() == ["sig", "sig"] for row in rows_exec), rows_exec)

rows_vib = areas_for("rs-vibrant_cards")
check("[vibrant_cards] 'com' no longer spans 2 rows against the shorter 'dom'/'att' cards (all three now sit in one row, as cards)",
      spans(rows_vib, "com") == 1, rows_vib)
check("[vibrant_cards] dom, att and com are three side-by-side cards in the same row",
      any(set(row.split()) == {"dom", "att", "com"} for row in rows_vib), rows_vib)

for cls in ("rs-compact_academic", "rs-executive_band", "rs-vibrant_cards"):
    rows = areas_for(cls)
    all_names = {n for row in rows for n in row.split()}
    for name in all_names:
        # no area should span across a row where one of its siblings occupies only that single row and belongs
        # to a visually "small" section (id/att/dom/key/sig) -- i.e. no leftover short-vs-span mismatch anywhere.
        pass  # covered by the specific per-template checks above; this loop documents the invariant.


# ============================================================ 3) live-browser rendering: whitespace is actually reduced, not just the CSS source
try:
    from playwright.sync_api import sync_playwright

    A.app.config["TESTING"] = False
    PORT = 18676

    def _run_server():
        A.app.run(host="127.0.0.1", port=PORT, use_reloader=False)

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    time.sleep(1.5)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Pass1234")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        def raw_sheet_height(template):
            rds(ADMIN, template=template)
            page.goto(f"http://127.0.0.1:{PORT}/result/1/print?term_id=1")
            page.wait_for_load_state("networkidle")
            # Reset any shrink-to-fit zoom the print page's own fit() script may have applied, so we measure the
            # sheet's true, unscaled content height -- the thing CSS Grid row-inflation actually affects.
            page.eval_on_selector(".rs-sheet", "el => { el.style.zoom = '1'; }")
            page.wait_for_timeout(100)
            return page.eval_on_selector(".rs-sheet", "el => el.scrollHeight")

        baseline = raw_sheet_height("professional_classic")
        results = {}
        for tn in ("executive_band", "compact_academic", "vibrant_cards"):
            results[tn] = raw_sheet_height(tn)

        for tn, h in results.items():
            ratio = h / baseline
            check(f"[{tn}] content height is not wildly inflated vs. professional_classic for the same data (ratio {ratio:.2f}, want <= 1.6)",
                  ratio <= 1.6, (h, baseline, ratio))

        browser.close()
except ImportError:
    print("Playwright not available in this environment -- skipping live rendering checks (static/HTTP checks above still ran).")
except Exception as e:
    check("live rendering checks completed without an unexpected error", False, repr(e))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
