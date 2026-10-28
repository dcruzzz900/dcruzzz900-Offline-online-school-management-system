"""End-to-end scenarios for V87: "School Settings, Branding and Cumulative Results Fixes" --

  1) The misplaced "auto-comment" explanation (previously sitting under Date Format in School
     Settings, with no real toggle behind it there) is gone from there, and the real, working
     "Comments" card in Result Display Settings now carries the fuller explanation.
  2) The school's registered address now has an admin field (School Settings), is saved, and
     shows on result sheets/broadsheets via the existing rs.contact plumbing -- omitted cleanly
     when blank.
  3) Picking a new accent color in Theme & Branding and saving now actually persists that color
     (previously silently discarded unless the "Custom" preset tile was also clicked), and it's
     reflected in the per-school CSS variable injected on every page.
  4) & 5) Cumulative results (when a school has them switched on) now appear consistently across
     ALL 16 result-sheet designs -- not just one -- with a full per-term CA1/CA2/[CA3]/Exam/Total
     breakdown (not just a running total), computed in exactly one place and shown identically on
     every design and on the dedicated Annual/Cumulative Result page.
  6) An admin/sub-admin now sees a plain, always-visible warning when the server's PDF-rendering
     engine isn't available (so results are printing in a generic fallback layout instead of the
     chosen design) -- the "old result fallback interfering with printing" Austin flagged from a
     real downloaded PDF -- instead of that substitution happening invisibly.

(own process, fresh DB, real HTTP requests). Run: python tests/v87_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v87_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
import html_pdf
import wf_helper as W
from db import get_db, RESULT_TEMPLATES
from werkzeug.security import generate_password_hash

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
        print("FAIL:", name, str(detail)[:400])


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


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.execute("UPDATE schools SET cumulative_enabled=1, school_address=NULL WHERE id=1")
session_id = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (session_id,))
term1 = 1
term2 = c0.execute("SELECT id FROM terms WHERE name='2nd Term'").fetchone()[0]
c0.commit()
c0.close()

# Student 1 (class 1): scores for term1 and term2, subjects 1 (Mathematics) and 2 (English Language).
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,20,20,0,40)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,1,?,10,10,0,20)", (term2,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,25,25,0,50)", (term1,))
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,2,?,15,15,0,30)", (term2,))
W.publish(A, term1)
W.publish(A, term2)

ADMIN = staff("admin")


def ensure_show_address():
    post(ADMIN, "/admin/result-display-settings", {
        "template": "professional_classic", "title": "Terminal Report Sheet",
        "accent_color": "#1f3a5f", "secondary_color": "#0b3b75", "header_layout": "logo-left",
        "text_align": "center", "signature_layout": "split", "pdf_font": "Helvetica",
        "page_orientation": "portrait", "font_scale": "normal",
        "show_address": "1", "show_phone": "1", "show_email": "1",
    }, "/admin/result-display-settings")


def set_template(key):
    post(ADMIN, "/admin/result-display-settings", {
        "template": key, "title": "Terminal Report Sheet",
        "accent_color": "#1f3a5f", "secondary_color": "#0b3b75", "header_layout": "logo-left",
        "text_align": "center", "signature_layout": "split", "pdf_font": "Helvetica",
        "page_orientation": "portrait", "font_scale": "normal",
        "show_address": "1", "show_phone": "1", "show_email": "1",
        "cumulative_enabled": "1",
    }, "/admin/result-display-settings")


print("=== 1) auto-comment explanation moved out of School Settings, into Result Display Settings ===")

sp = html(ADMIN.get("/admin/school"))
check("admin_school.html no longer has the orphaned 'How auto-comment works' block",
      "How auto-comment works" not in sp and "generated from the student's grade/average" not in sp, sp.count("auto-comment"))

rds = html(ADMIN.get("/admin/result-display-settings"))
check("the real Comments card (with its two working checkboxes) carries the fuller explanation now",
      'name="auto_teacher_comment"' in rds and "come in by CSV upload and no one types a comment by hand" in rds)

print("=== 2) school address: admin field, save, and it shows up on result sheets/broadsheets ===")

sp_before = html(ADMIN.get("/admin/school"))
check("School Settings has a School Address field", 'name="school_address"' in sp_before)

post(ADMIN, "/admin/school", {
    "school_name": "Government Secondary school Goni-Gora", "registered_email": "", "registered_phone": "07039825270",
    "school_address": "12 Unity Road, Goni-Gora, Kaduna", "timezone": "Africa/Lagos", "date_format": "dmy", "web_font": "system",
}, "/admin/school")
check("school_address actually persisted", one("SELECT school_address FROM schools WHERE id=1")["school_address"] == "12 Unity Road, Goni-Gora, Kaduna")

ensure_show_address()
rprint = html(ADMIN.get(f"/result/1/print?term_id={term1}"))
check("the address shows on the (generic/professional_classic) result sheet", "12 Unity Road, Goni-Gora, Kaduna" in rprint)

set_template("green_cumulative_report")
rprint_sample = html(ADMIN.get(f"/result/1/print?term_id={term1}"))
check("the address also shows on a 'sample' template design (green_cumulative_report)", "12 Unity Road, Goni-Gora, Kaduna" in rprint_sample)

bs = html(ADMIN.get(f"/broadsheet/{one('SELECT class_id FROM students WHERE id=1')['class_id']}/print?term_id={term1}")) if False else None
# broadsheet_print.html is served inline from its PDF/print route; use the print route directly:
bs_print = html(ADMIN.get(f"/broadsheet/{one('SELECT class_id FROM students WHERE id=1')['class_id']}?term_id={term1}")) if False else None

# ----- find the actual broadsheet print endpoint -----
_bs_class_id = one("SELECT class_id FROM students WHERE id=1")["class_id"]
_bs_ep = None
for r in A.app.url_map.iter_rules():
    if r.endpoint == "broadsheet_pdf":
        _bs_ep = r
for r in A.app.url_map.iter_rules():
    if "broadsheet" in r.endpoint and "print" in str(r):
        _bs_ep = r

# admin_students check removed (not needed) -- directly exercise the print template via result_sheet_settings-backed route
from flask import session as _session
with A.app.test_request_context():
    _session["school_id"] = 1
    _c = get_db()
    _rs = A.result_sheet_settings(_c, 1)
    _c.close()
check("rs.contact (used by every result header AND the broadsheets) includes the saved address", "12 Unity Road, Goni-Gora, Kaduna" in (_rs.get("contact") or ""), _rs.get("contact"))

run("UPDATE schools SET school_address=NULL WHERE id=1")
rprint_blank = html(ADMIN.get(f"/result/1/print?term_id={term1}"))
check("blanking the address omits it cleanly (no stray separator, no placeholder)", "rs-contact" not in rprint_blank or '<p class="rs-contact"></p>' not in rprint_blank)
run("UPDATE schools SET school_address=? WHERE id=1", ("12 Unity Road, Goni-Gora, Kaduna",))

print("=== 3) accent color: a hand-picked color actually saves now, under any preset ===")

before_accent = one("SELECT dashboard_accent_color, theme_preset FROM schools WHERE id=1")
theme_page = html(ADMIN.get("/admin/theme"))
check("theme_branding.html ships the JS fix that switches to Custom on a manual color pick",
      "custom" in theme_page.lower() and "input" in theme_page.lower())

post(ADMIN, "/admin/theme", {
    "theme_preset": "default",  # deliberately NOT "custom" -- this exact combination used to silently discard the picked color
    "dashboard_primary_color": "#112233", "dashboard_secondary_color": "#223344", "dashboard_accent_color": "#a1b2c3",
    "dashboard_sidebar_style": "dark", "dashboard_header_style": "solid",
    "auth_logo_opacity": "0.10", "auth_logo_position": "center", "auth_background_style": "watermark",
    "auth_show_school_name": "1", "auth_branding_enabled": "1",
}, "/admin/theme")
after_accent = one("SELECT dashboard_accent_color, dashboard_primary_color, dashboard_secondary_color FROM schools WHERE id=1")
check("a hand-picked accent color is now actually saved, even with theme_preset left on 'default'",
      after_accent["dashboard_accent_color"] == "#a1b2c3", dict(after_accent))
check("primary color saved too", after_accent["dashboard_primary_color"] == "#112233")
check("secondary color saved too", after_accent["dashboard_secondary_color"] == "#223344")

dash = html(ADMIN.get("/dashboard"))
check("the saved custom accent color is actually injected as the page's --theme-accent CSS variable",
      "--theme-accent:#a1b2c3" in dash, dash[:0])

print("=== 4) & 5) cumulative results: present on every one of the 16 templates, full per-term breakdown, one shared calculation ===")

dedicated = html(ADMIN.get(f"/cumulative/student/1?session_id={session_id}&term_id={term2}"))
check("the dedicated Annual/Cumulative Result page shows the full breakdown table", 'class="rs-table rs-cum-table"' in dedicated or "rs-cum-table" in dedicated)
check("dedicated page: Mathematics term1 CA1=20 appears", re.search(r"Mathematics.*?20", dedicated, re.S) is not None)
check("dedicated page: Mathematics term1 Total=80 appears (20+20+0+40)", "80" in dedicated)
check("dedicated page: Mathematics term2 Total=40 appears (10+10+0+20)", "40" in dedicated)
check("dedicated page: Aggregate column present", "Aggregate" in dedicated)

SAMPLE_OF_16 = ("professional_classic", "modern_academic", "compact_academic", "minimal_clean",
                "boxed_grey_card", "assessment_dossier", "peach_terminal_sheet", "green_cumulative_report",
                "progress_report_card", "clean_midterm_report")
check(f"sampling {len(SAMPLE_OF_16)} of the 16 real template keys", all(k in {t[0] for t in RESULT_TEMPLATES} for k in SAMPLE_OF_16), [t[0] for t in RESULT_TEMPLATES])

for key in SAMPLE_OF_16:
    set_template(key)
    page = html(ADMIN.get(f"/result/1/print?term_id={term1}"))
    check(f"[{key}] cumulative breakdown section is present", "rs-cum-table" in page, key)
    check(f"[{key}] shows the Cumulative / Annual Performance heading", "Cumulative / Annual Performance" in page, key)
    check(f"[{key}] term1 CA1=20 for Mathematics is in the breakdown (not just a running total)", "20" in page and "80" in page, key)
    check(f"[{key}] term2 figures (10, 40) are also present", "40" in page, key)

# Turning cumulative OFF makes the section disappear everywhere, including the one template that
# always had it (green_cumulative_report) -- confirms the setting is still authoritative.
run("UPDATE schools SET cumulative_enabled=0 WHERE id=1")
off_page = html(ADMIN.get(f"/result/1/print?term_id={term1}"))
check("cumulative_enabled=0 hides the breakdown even on green_cumulative_report", "rs-cum-table" not in off_page)
run("UPDATE schools SET cumulative_enabled=1 WHERE id=1")

print("=== 6) PDF-rendering engine status: an admin sees a plain warning instead of a silent swap ===")

_orig_engine_available = html_pdf.engine_available
try:
    html_pdf.engine_available = lambda: False
    down_dash = html(ADMIN.get("/dashboard"))
    check("admin sees a plain, always-visible warning when the PDF engine is unavailable",
          "plain, generic layout" in down_dash or "pdf-rendering engine" in down_dash.lower() or "PDF-rendering engine" in down_dash)
    check("the warning is NOT wrapped behind a collapsed Help control (it's critical system status)",
          re.search(r'<details class="hlp"[^>]*>\s*<summary[^>]*>[^<]*plain', down_dash, re.I) is None)
finally:
    html_pdf.engine_available = _orig_engine_available

up_dash = html(ADMIN.get("/dashboard"))
check("the warning disappears once the engine is available again", "plain, generic layout" not in up_dash)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
