"""End-to-end scenarios for the V73 requirement: print/PDF page orientation, a Fit to Page
toggle, and a font-size (zoom) scale for result sheets and broadsheets.

Architecture note this phase relies on: app.py overrides pdf_utils.py's ReportLab PDF
builders with Chromium-based ones that render the SAME HTML used for on-screen print/preview
("Preview = Print = PDF"), so the real implementation surface is templates/result_print.html
(and its fit() JS + inline @page CSS) and templates/broadsheet_print.html, not pdf_utils.py.

Three new, independent result_display_settings columns, each additive and defaulted to
reproduce today's exact behaviour when untouched:
  - page_orientation ('portrait'|'landscape'): the printed/PDF page size for the individual
    result sheet. Defaults to 'portrait' (today's only behaviour). Broadsheets stay landscape
    regardless of this setting (they're a different, always-landscape document).
  - fit_to_page (bool, via the existing RESULT_BOOL_SETTINGS pattern): whether an overflowing
    sheet is auto-shrunk to stay on one page (today's only behaviour, default ON) or left to
    flow onto a second page at full size.
  - font_scale ('small'|'normal'|'large'): a flat print-size preference applied via CSS zoom
    (templates use absolute pt font sizes, which zoom scales uniformly but a parent
    font-size percentage would not). Composes multiplicatively with fit_to_page's auto-shrink:
    once a sheet overflows with fit_to_page on, the auto-shrink ratio wins over the chosen
    font_scale (same as it always has), so a shrunk sheet never explodes back past one page
    just because "Large" was chosen.

(own process, fresh DB, real HTTP requests). Run: python tests/v73_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v73_")
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


def one(sql, args=()):
    c = db()
    try:
        return c.execute(sql, args).fetchone()
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
# result_display_settings is created lazily (INSERT OR IGNORE) the first time it's read — touch it once so the
# direct SQL UPDATEs below have a row to act on.
ADMIN.get("/admin/result-display-settings")
run("INSERT OR REPLACE INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,1,11,12,0,40),(1,2,1,8,9,0,31)")
run("UPDATE result_display_settings SET show_score=1, show_grade=1, show_passport=1 WHERE school_id=1")
W.publish(A, 1)


def sheet():
    r = ADMIN.get("/result/1/print?term_id=1")
    assert r.status_code == 200, r.status_code
    return html(r)


def broadsheet():
    r = ADMIN.get("/broadsheet/1/print?term_id=1")
    assert r.status_code == 200, r.status_code
    return html(r)


# ---------------------------------------------------------------- 0) defaults reproduce today's exact behaviour
row = one("SELECT page_orientation, fit_to_page, font_scale FROM result_display_settings WHERE school_id=1")
check("page_orientation defaults to 'portrait' (unchanged behaviour)", row["page_orientation"] == "portrait", dict(row))
check("fit_to_page defaults to ON (unchanged behaviour: auto-shrink stays the only behaviour until an admin opts out)", row["fit_to_page"] == 1, dict(row))
check("font_scale defaults to 'normal' (unchanged behaviour: today's fixed per-template sizes)", row["font_scale"] == "normal", dict(row))

s = sheet()
check("default sheet's @page rule has no 'landscape' (still portrait)", "@page{size:A4;margin:0}" in s or re.search(r"@page\{size:A4;margin:0\}", s), s[:600])
check("RS_LANDSCAPE is false by default", "var RS_LANDSCAPE = false" in s, s)
check("RS_FONT_SCALE is 1.0 by default", "var RS_FONT_SCALE = 1.0" in s, s)
check("RS_FIT_TO_PAGE is true by default", "var RS_FIT_TO_PAGE = true" in s, s)

# ---------------------------------------------------------------- 1) orientation
run("UPDATE result_display_settings SET page_orientation='landscape' WHERE school_id=1")
s = sheet()
check("landscape setting renders an '@page{size:A4 landscape...}' override", "@page{size:A4 landscape;margin:0}" in s, s[:800])
check("RS_LANDSCAPE flips to true", "var RS_LANDSCAPE = true" in s, s)

bs = broadsheet()
check("the broadsheet stays landscape regardless of the per-sheet orientation setting (it's a separate, always-landscape document)",
      "@page{size:A4 landscape;margin:10mm}" in bs, bs[:600])

run("UPDATE result_display_settings SET page_orientation='portrait' WHERE school_id=1")

# ---------------------------------------------------------------- 2) fit_to_page toggle
run("UPDATE result_display_settings SET fit_to_page=0 WHERE school_id=1")
s = sheet()
check("turning Fit to Page off is reflected in the print page's JS flag", "var RS_FIT_TO_PAGE = false" in s, s)
run("UPDATE result_display_settings SET fit_to_page=1 WHERE school_id=1")
s = sheet()
check("turning Fit to Page back on restores the flag", "var RS_FIT_TO_PAGE = true" in s, s)

# ---------------------------------------------------------------- 3) font_scale
for val, factor in (("small", "0.9"), ("normal", "1.0"), ("large", "1.12")):
    run("UPDATE result_display_settings SET font_scale=? WHERE school_id=1", (val,))
    s = sheet()
    check(f"font_scale={val} maps to a {factor} zoom factor on the print page", f"var RS_FONT_SCALE = {factor}" in s, s)
    bs = broadsheet()
    check(f"the broadsheet picks up the same font_scale={val} ({factor}) preference", f"var RS_FONT_SCALE = {factor}" in bs, bs)
run("UPDATE result_display_settings SET font_scale='normal' WHERE school_id=1")

# ---------------------------------------------------------------- 4) the fit() composition formula itself (read, not executed — JS isn't run by this
#    harness) is present and unchanged in shape, so the auto-shrink ratio still wins over font_scale once a sheet
#    overflows with Fit to Page on (today's exact shrink math, now reached only when `overflow` is true).
tmpl = open(os.path.join(ROOT, "templates", "result_print.html"), encoding="utf-8").read()
# V79 raised the floor from 0.28 to a real legibility floor (FIT_FLOOR=0.72) and added a
# flow-to-a-second-page-instead-of-over-shrinking path when even that floor isn't enough -- see
# tests/v79_scenarios.py. The auto-shrink FORMULA itself ((max/h)*0.965) is unchanged; only the
# floor value changed, so check for that instead of the old literal 0.28.
check("the auto-shrink formula (max/h)*0.965 is unchanged (only the floor value changed in V79)", "(max/h)*0.965" in tmpl, tmpl)
check("the shrink branch is gated on fit_to_page being on AND the sheet actually overflowing", "if(fitOn&&overflow){" in tmpl, tmpl)
check("overflow is computed against the font_scale-projected height (h*base), not the raw height", "overflow=(h*base)>max" in tmpl, tmpl)

# ---------------------------------------------------------------- 5) admin settings page: controls exist, options round-trip
r = ADMIN.get("/admin/result-display-settings")
check("the settings page now has a Page orientation select", 'name="page_orientation"' in html(r))
check("...with Portrait and Landscape options", "Portrait" in html(r) and "Landscape" in html(r))
check("the settings page now has a Print / PDF font size select", 'name="font_scale"' in html(r))
check("...with Small / Normal / Large options", all(x in html(r) for x in ("Small", "Normal", "Large")))
check("Fit to Page appears as an ordinary ON/OFF switch alongside the other display toggles", "Automatically Shrink to Fit One Page" in html(r))

# Build a full, valid form payload from the school's CURRENT settings (so nothing else changes), then flip
# orientation/font_scale through the real admin route and confirm it's saved and reflected in the dropdown state.
cfg_row = one("SELECT * FROM result_display_settings WHERE school_id=1")
school_row = one("SELECT pdf_font FROM schools WHERE id=1")
from db import RESULT_BOOL_SETTINGS
form = {k: "1" for k, _l, _d in RESULT_BOOL_SETTINGS if cfg_row[k]}
form.update(template=cfg_row["template"], title=cfg_row["title"] or "", footer_text=cfg_row["footer_text"] or "",
            watermark_text=cfg_row["watermark_text"] or "", accent_color=cfg_row["accent_color"] or "#1f3a5f",
            secondary_color=cfg_row["secondary_color"] or "#c9a227", header_layout=cfg_row["header_layout"],
            signature_layout=cfg_row["signature_layout"], text_align=cfg_row["text_align"], pdf_font=school_row["pdf_font"] or "Helvetica",
            page_orientation="landscape", font_scale="large")
r = post(ADMIN, "/admin/result-display-settings", form, "/admin/result-display-settings")
check("saving the form through the real admin route succeeds (redirect, no validation errors)", r.status_code == 302, (r.status_code, html(r)[:400]))
row = one("SELECT page_orientation, font_scale FROM result_display_settings WHERE school_id=1")
check("...and the new orientation/font_scale values are actually persisted", row["page_orientation"] == "landscape" and row["font_scale"] == "large", dict(row))
r = ADMIN.get("/admin/result-display-settings")
check("...and the settings page now shows Landscape selected", re.search(r'value="landscape"\s+selected', html(r)) is not None, html(r)[:2000])
check("...and Large selected for font size", re.search(r'value="large"\s+selected', html(r)) is not None, html(r)[:2000])
run("UPDATE result_display_settings SET page_orientation='portrait', font_scale='normal' WHERE school_id=1")

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
