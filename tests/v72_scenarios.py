"""End-to-end scenarios for the V72 requirement: two concrete, previously-specified result-sheet
template fixes from the eighth requirements document's template-fix list:

1. Clean Mid-Term Report: remove its "Highest" (class highest score per subject) column
   entirely — the only one of the sample-sheet templates asked to drop it (Boxed Grey Card,
   Progress Report Card and Peach Terminal Sheet all keep their own Highest/Lowest columns
   unchanged; this phase does not touch those).
2. Continuous Assessment Dossier: fix the passport photo's positioning. The photo sits
   absolutely-positioned over a short, two-line identity block so the two lines can wrap
   around it, but because an absolutely-positioned element never contributes to its parent's
   height, the identity section's box was only as tall as its text (~12mm) while the photo
   itself is 30mm tall — so the bottom third of the passport photo hung down past the identity
   section and collided with the assessment table directly below it. Fixed by reserving the
   photo's full height on the parent and removing the odd -1mm top offset that made it worse.

(own process, fresh DB, real HTTP requests). Run: python tests/v72_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v72_")
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
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,0,40),(1,2,1,8,9,0,31)")
run("UPDATE result_display_settings SET show_score=1, show_grade=1, show_passport=1 WHERE school_id=1")
W.publish(A, 1)


def sheet():
    r = ADMIN.get("/result/1/print?term_id=1")
    assert r.status_code == 200, r.status_code
    return html(r)


# ---------------------------------------------------------------- V97: the 16-style picker (the
# "Clean Mid-Term Report", "Boxed Grey Card", "Progress Report Card", "Continuous Assessment
# Dossier" and 12 other designs this file used to regression-test) was removed per Austin's
# explicit request; there is now exactly one fixed design (templates/_result_sheet.html, class
# "rs-classic") for every school. The passport-overlap and stray-column regressions this file used
# to guard against were specific to those now-deleted bespoke layouts' own markup/CSS
# (static/css/result-samples.css, also removed), so this file now just confirms the one remaining
# design still renders its own Avg./Total columns and its passport correctly.
s = sheet()
check("the fixed design shows an 'Avg.' column next to the subject totals", "<th>Avg.</th>" in s, s)
check("...and the table still renders scores/grades normally (no broken row)", "<td>11</td>" in s or "<td>11.0</td>" in s, s)
check("the fixed design has no leftover per-style markup from the removed designs", "rsx-" not in s, s)

css_path = os.path.join(ROOT, "static", "css", "result-sheet.css")
check("the old per-style sample stylesheet was removed", not os.path.exists(os.path.join(ROOT, "static", "css", "result-samples.css")))
css = open(css_path, encoding="utf-8").read()
check("the passport frame still has its no-crop, centred rules (now on the one fixed design)",
      ".rs-passport.has-photo{border:0" in css and "object-fit:contain" in css, css[:400])
s3 = sheet()
check("the fixed design still renders with its passport and identity section intact",
      'class="rs-passport' in s3 and 'class="rs-id"' in s3)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
