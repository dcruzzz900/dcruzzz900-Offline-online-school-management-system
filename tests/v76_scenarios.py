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


# V97 note: Austin later asked for the 16-style picker (including Executive Band, Compact
# Academic and Vibrant Cards, named throughout this file) to be removed entirely in favor of one
# fixed design built from his own reference sheets -- so the per-template grid-whitespace fix and
# live-browser height comparison this file used to guard (sections 2 and 3 below) no longer apply;
# those templates, and the CSS grid-template-areas they used, don't exist any more. What's still
# true and still worth guarding is requirement #1 -- a domain rating shows only its number, never
# a duplicated word label next to it -- which lives in the one shared _result_sheet.html partial
# every design (now just the one) has always used.

# ============================================================ 1) domain rating: number only, no duplicated word label
rds(ADMIN, template="professional_classic")
sh = sheet()
check("domain rating shows only the number (no '- Very Good' style word label)",
      "<small>–" not in sh and "Very Good</small>" not in sh, sh[sh.find("rs-domains"):sh.find("rs-domains") + 400] if "rs-domains" in sh else "no rs-domains section")
check("domain rows render as plain numbers, e.g. '>5<' not '>5 – Excellent<'",
      re.search(r"<td>5</td>", sh) is not None or re.search(r"<td>4</td>", sh) is not None, sh.count("<td>5</td>") + sh.count("<td>4</td>"))
# the bottom "Domain ratings: 1 = Poor ... 5 = Excellent" legend line is untouched -- Austin didn't ask for
# that to be removed, only the per-row repetition next to each individual rating.
check("the single domain-ratings legend line at the bottom is still shown",
      "Domain Ratings Scale:" in sh)
# exactly one "Domain Ratings" section heading (never duplicated per card)
check("exactly one 'Domain Ratings' section heading", sh.count(">Domain Ratings<") == 1, sh.count(">Domain Ratings<"))
# both domain group card titles still present and distinct
check("both domain group labels (Affective Domain / Psychomotor Domain) still shown once each",
      sh.count("Affective Domain") == 1 and sh.count("Psychomotor Domain") == 1)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
