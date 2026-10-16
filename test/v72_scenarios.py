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


def sheet(template):
    run("UPDATE result_display_settings SET template=? WHERE school_id=1", (template,))
    r = ADMIN.get("/result/1/print?term_id=1")
    assert r.status_code == 200, (template, r.status_code)
    return html(r)


# ---------------------------------------------------------------- 1) Clean Mid-Term Report: "Highest" column gone
s = sheet("clean_midterm_report")
check("Clean Mid-Term Report no longer has a 'Highest' column header", "<th>Highest</th>" not in s, s)
check("...and no stray 'Highest' label appears anywhere on the sheet", "Highest" not in s)
check("...while 'Average' (the column next to it) is still there", "Average" in s)
check("...and the table still renders scores/grades normally (no broken row)", "<td>11</td>" in s or "<td>11.0</td>" in s, s)

# Regression: the OTHER sample templates that also show a "Highest" column were NOT touched by this phase.
for tp, label in (("boxed_grey_card", "Highest in subject"), ("progress_report_card", None)):
    s2 = sheet(tp)
    if label:
        check(f"[{tp}] its own 'Highest' column is untouched (this phase only changes Clean Mid-Term Report)", label in s2, s2)
    else:
        check(f"[{tp}] its own Highest/Lowest columns are untouched (still rendering a numeric 'Highest' value)",
              re.search(r"<td>\d", s2) is not None)

# ---------------------------------------------------------------- 2) Continuous Assessment Dossier: passport no longer overlaps the table
css = open(os.path.join(ROOT, "static", "css", "result-samples.css"), encoding="utf-8").read()
check("the identity section now reserves the passport's full height (prevents the table below from being overlapped)",
      re.search(r"\.rsx-dos-id\{[^}]*min-height:30mm", css) is not None, css[:400])
check("the passport is flush with the top of its container, not offset above it", ".rsx-dos-photo{position:absolute;right:0;top:0}" in css)
s3 = sheet("assessment_dossier")
check("Continuous Assessment Dossier still renders with its passport and identity section intact",
      'class="rsx-dos-photo"' in s3 and 'class="rsx-dos-id"' in s3 and 'class="rsx-dos-table"' in s3)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
