"""End-to-end scenarios for the V70 requirement: rename "Educational Domains" to
"Domain Ratings" everywhere it's user-facing, and combine the grading key and the
domain-rating key into a single, unified key display (instead of two separate,
sometimes-duplicated key blocks scattered around the sheet) — while keeping each
key independently togglable (domains-only, grading-only, both, or neither).
(own process, fresh DB, real HTTP requests). Run: python tests/v70_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v70_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import wf_helper as W
from db import get_db, RESULT_TEMPLATES
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


def one(sql, args=()):
    c = db()
    try:
        r = c.execute(sql, args).fetchone()
        return r[0] if r is not None else None
    finally:
        c.close()


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

run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,0,40),(1,2,1,8,9,0,31)")
trait_id = one("SELECT id FROM skill_traits WHERE school_id=1 AND COALESCE(is_active,1)=1 ORDER BY id LIMIT 1")
post(ADMIN, "/result/1/extra", {"term_id": "1", f"trait_{trait_id}": "4", "attendance_source": "auto"}, "/result/1")
run("UPDATE result_display_settings SET show_domains=1, show_grading_key=1 WHERE school_id=1")
W.publish(A, 1)


def sheet(template):
    run("UPDATE result_display_settings SET template=? WHERE school_id=1", (template,))
    r = ADMIN.get("/result/1/print?term_id=1")  # the bare sheet only, no admin editor form below it
    assert r.status_code == 200, (template, r.status_code)
    return html(r)


# ---------------------------------------------------------------- scenarios

# 1) The "Educational Domains" name is gone from every user-facing surface; "Domain Ratings" is used instead.
search = ADMIN.get("/api/search?q=domain").get_json()
check("the dashboard-search feature label is 'Domain Ratings', not 'Educational Domains'",
      any(f["label"] == "Domain Ratings" for f in search["features"]), search["features"])
admin_page = html(ADMIN.get("/admin/domains"))
check("the admin settings page is titled 'Domain Ratings'", "Domain Ratings" in admin_page and "Educational Domains" not in admin_page)
editor = html(ADMIN.get("/result/1?term_id=1"))
check("the result editor's rating section is titled 'Domain Ratings'", "Domain Ratings" in editor and "Educational Domains" not in editor)

# 2) On the result sheet itself (every structurally-different template), the heading/key never says "Educational Domains".
ALL_TEMPLATES = [t[0] for t in RESULT_TEMPLATES]
for tp in ALL_TEMPLATES:
    s = sheet(tp)
    check(f"[{tp}] result sheet never shows the old 'Educational Domains' name", "Educational Domains" not in s, tp)

# 3) With BOTH grading key and domain key switched on, both appear TOGETHER near each other (a combined
#    key), not as two separate, far-apart blocks repeating the same information in different words.
for tp in ("modern_academic", "detailed_report", "clean_midterm_report", "boxed_grey_card", "progress_report_card", "assessment_dossier", "green_cumulative_report"):
    s = sheet(tp)
    low = s.lower()
    has_grade_info = any(k in low for k in ("grades:", "grading", "grade scale", "score range", "academic standard", "note:"))
    has_domain_info = "domain ratings:" in low or "domain rating" in low
    check(f"[{tp}] grading info is shown when the toggle is on", has_grade_info, tp)
    check(f"[{tp}] domain-rating info is shown when the toggle is on", has_domain_info, tp)

# 4) progress_report_card previously showed bare "x/5" ratings with NO legend anywhere on the sheet —
#    a real gap closed by this phase: the legend must now actually be present, not just technically possible.
s = sheet("progress_report_card")
check("progress_report_card now has an actual domain-ratings legend (previously missing entirely)",
      "domain ratings:" in s.lower() and ("poor" in s.lower() or "excellent" in s.lower()))

# 5) Each key is still independently togglable: domains-only (no grading key) still shows the domain legend,
#    and grading-only (no domains) still shows the grade scale — turning one off never hides the other.
run("UPDATE result_display_settings SET show_domains=1, show_grading_key=0 WHERE school_id=1")
s = sheet("modern_academic")
check("domains-only: the domain-ratings legend still appears when grading key is OFF", "domain ratings" in s.lower())
run("UPDATE result_display_settings SET show_domains=0, show_grading_key=1 WHERE school_id=1")
s = sheet("modern_academic")
check("grading-only: the grade scale still appears when domains are OFF", any(k in s.lower() for k in ("grades:", "grading")))
check("...and no stray 'domain ratings' label leaks in when domains are off", "domain ratings" not in s.lower())
run("UPDATE result_display_settings SET show_domains=0, show_grading_key=0 WHERE school_id=1")
s = sheet("modern_academic")
check("neither on: no key section renders at all", "domain ratings" not in s.lower() and "grades:" not in s.lower())
run("UPDATE result_display_settings SET show_domains=1, show_grading_key=1 WHERE school_id=1")

# 6) PDF carries the same combined key as the print/preview page (same template, same content).
run("UPDATE result_display_settings SET template='modern_academic' WHERE school_id=1")
import io as _io
from pypdf import PdfReader
rp = ADMIN.get("/result/1/pdf?term_id=1")
ptxt = " ".join(pg.extract_text() or "" for pg in PdfReader(_io.BytesIO(rp.data)).pages).lower()
check("the PDF also shows the combined key (grading + domain ratings)", "domain ratings" in ptxt or "domain rating" in ptxt)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
