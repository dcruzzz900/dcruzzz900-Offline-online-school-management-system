"""End-to-end scenarios for V92: "Result Display Settings -- Paper Sizes" --
  Phases 6-7 of the 10th requirements doc ("Complete Feature Enhancement Specification").

  1) Result Display Settings gains a Paper Size control (A4 default, A3, A5, Letter, Legal,
     Foolscap, Custom mm dimensions), independent of the existing orientation setting.
  2) Automatic layout adjustment: the printed/previewed result sheet and cumulative result
     both size themselves to whatever paper size + orientation is configured.
  3) Matching print/PDF pagination: the actual downloaded PDF's page size matches the
     configured paper size (and swaps on landscape), verified on the real PDF bytes, not
     just the HTML.
  4) A4 Portrait remains the unchanged default for a school that never opens this setting.
  5) Tenant isolation holds -- one school's paper size never affects another's.

(own process, fresh DB, real HTTP requests). Run: python tests/v92_scenarios.py"""
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v92_")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

import app as A
from db import get_db
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


def pdf_page_size_mm(pdf_bytes):
    """The first page's media box, converted from PDF points (1/72in) to mm."""
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(pdf_bytes))
    box = reader.pages[0].mediabox
    pt_to_mm = 25.4 / 72.0
    return round(float(box.width) * pt_to_mm, 1), round(float(box.height) * pt_to_mm, 1)


# ------------------------------------------------------------------ fixtures
pw = generate_password_hash("Pass1234")
c0 = db()
c0.execute("UPDATE users SET password_hash=?", (pw,))
c0.commit()
c0.close()

school_id = 1
term1 = one("SELECT id FROM terms WHERE is_active=1")["id"]
class1 = one("SELECT class_id FROM students WHERE id=1")["class_id"]
ADMIN = staff("admin")

# A couple of scores for student 1 so the result sheet has something to render, and the class's
# result published for this term -- print/PDF are blocked by the publication guard otherwise.
math_id = one("SELECT id FROM subjects WHERE name='Mathematics'")["id"]
run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (1,?,?,15,15,0,40)", (math_id, term1))
run(
    "INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at,published_by) VALUES (?,?,?,?,'published',CURRENT_TIMESTAMP,1)",
    (school_id, "1", class1, term1),
)

print("=== 1) A school that never opens this setting still defaults to A4 Portrait ===")

settings_page = html(ADMIN.get("/admin/result-display-settings"))
check("Paper size control is present and defaults to A4", 'name="paper_size"' in settings_page and '<option value="A4" selected' in settings_page, settings_page)
w, h = pdf_page_size_mm(ADMIN.get(f"/result/1/pdf?term_id={term1}").data)
check(f"a never-configured school's result PDF is A4 portrait (got {w}x{h}mm)", abs(w - 210) < 2 and abs(h - 297) < 2, (w, h))

print("=== 2) Changing Paper Size to A3 (with Landscape) is saved and reflected everywhere ===")

post(ADMIN, "/admin/result-display-settings", {
    "template": "professional_classic", "header_layout": "logo-left", "signature_layout": "split",
    "text_align": "auto", "pdf_font": "Helvetica", "page_orientation": "landscape", "font_scale": "normal",
    "paper_size": "A3",
}, "/admin/result-display-settings")
row = one("SELECT paper_size, page_orientation FROM result_display_settings WHERE school_id=?", (school_id,))
check("paper_size=A3 saved to the database", row["paper_size"] == "A3", dict(row))

# The regular (non-cumulative) result sheet has no standalone print-preview URL of its own --
# "Print" and "Download PDF" both open the one real PDF (V78), rendered internally from
# result_print.html by html_pdf.py -- so the actual downloaded PDF's own page size IS the
# correct, most direct thing to verify here, not a separately-fetched HTML page.
w2, h2 = pdf_page_size_mm(ADMIN.get(f"/result/1/pdf?term_id={term1}").data)
check(f"the actual downloaded PDF is now A3 landscape (got {w2}x{h2}mm)", abs(w2 - 420) < 2 and abs(h2 - 297) < 2, (w2, h2))

print("=== 3) The cumulative result print page picks up the same paper size ===")

run("UPDATE schools SET cumulative_enabled=1 WHERE id=?", (school_id,))
cum_page = html(ADMIN.get(f"/cumulative/student/1/print?session_id={one('SELECT session_id FROM terms WHERE id=?', (term1,))['session_id']}"))
check("cumulative result print page also uses A3 landscape", "RS_PAGE_W_MM = 297" in cum_page and "RS_PAGE_H_MM = 420" in cum_page, cum_page)

print("=== 4) Custom mm dimensions: entered either way round, always stored portrait (narrower first) ===")

post(ADMIN, "/admin/result-display-settings", {
    "template": "professional_classic", "header_layout": "logo-left", "signature_layout": "split",
    "text_align": "auto", "pdf_font": "Helvetica", "page_orientation": "portrait", "font_scale": "normal",
    "paper_size": "Custom", "custom_width_mm": "250", "custom_height_mm": "160",  # given backwards (wider first)
}, "/admin/result-display-settings")
row2 = one("SELECT paper_size, custom_width_mm, custom_height_mm FROM result_display_settings WHERE school_id=?", (school_id,))
check("custom dims are normalized to width <= height regardless of entry order", row2["custom_width_mm"] == 160.0 and row2["custom_height_mm"] == 250.0, dict(row2))

w3, h3 = pdf_page_size_mm(ADMIN.get(f"/result/1/pdf?term_id={term1}").data)
check(f"the PDF now matches the custom 160x250mm size (got {w3}x{h3}mm)", abs(w3 - 160) < 2 and abs(h3 - 250) < 2, (w3, h3))

print("=== 5) Custom size is rejected when out of range, and nothing is silently saved ===")

r = post(ADMIN, "/admin/result-display-settings", {
    "template": "professional_classic", "header_layout": "logo-left", "signature_layout": "split",
    "text_align": "auto", "pdf_font": "Helvetica", "page_orientation": "portrait", "font_scale": "normal",
    "paper_size": "Custom", "custom_width_mm": "5", "custom_height_mm": "5000",
}, "/admin/result-display-settings")
check("an out-of-range custom size is refused (422)", r.status_code == 422, r.status_code)
row3 = one("SELECT paper_size, custom_width_mm, custom_height_mm FROM result_display_settings WHERE school_id=?", (school_id,))
check("the previously-saved valid custom size is untouched by the rejected attempt", row3["custom_width_mm"] == 160.0 and row3["custom_height_mm"] == 250.0, dict(row3))

print("=== 6) Other paper sizes (Letter, Legal, Foolscap, A5) all come through correctly ===")

for size, (pw_mm, ph_mm) in {"Letter": (215.9, 279.4), "Legal": (215.9, 355.6), "Foolscap": (215.9, 330.2), "A5": (148.0, 210.0)}.items():
    post(ADMIN, "/admin/result-display-settings", {
        "template": "professional_classic", "header_layout": "logo-left", "signature_layout": "split",
        "text_align": "auto", "pdf_font": "Helvetica", "page_orientation": "portrait", "font_scale": "normal",
        "paper_size": size,
    }, "/admin/result-display-settings")
    wN, hN = pdf_page_size_mm(ADMIN.get(f"/result/1/pdf?term_id={term1}").data)
    check(f"{size} PDF page size matches ({pw_mm}x{ph_mm}mm, got {wN}x{hN}mm)", abs(wN - pw_mm) < 2 and abs(hN - ph_mm) < 2, (size, wN, hN))

print("=== 7) Tenant isolation: a second school's own paper size is independent ===")

c = db()
cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')")
school2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{school2}", f"PUB{school2}", school2))
cur.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)",
            (school2, "school2", "Second Admin", "admin2", pw, "admin"))
cur.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (school2, "2025/2026"))
sess2 = cur.lastrowid
cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,1)", ("1st Term", sess2))
term2_id = cur.lastrowid
cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'Basic 1')", (school2,))
class2 = cur.lastrowid
cur.execute("INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) VALUES (?,?,?,?,?,?,?)",
            (school2, "school2", "S2-001", "Bola", "Second", "F", class2))
stu2 = cur.lastrowid
cur.execute(
    "INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at,published_by) VALUES (?,?,?,?,'published',CURRENT_TIMESTAMP,1)",
    (school2, "school2", class2, term2_id),
)
c.commit()
c.close()

ADMIN2 = staff("admin2")
dash2 = html(ADMIN2.get("/admin/result-display-settings"))
check("second school's own settings still default to A4 (unaffected by school 1's Foolscap choice)", '<option value="A4" selected' in dash2, dash2)
w4, h4 = pdf_page_size_mm(ADMIN2.get(f"/result/{stu2}/pdf?term_id={term2_id}").data)
check(f"second school's own result PDF is still A4 portrait (got {w4}x{h4}mm)", abs(w4 - 210) < 2 and abs(h4 - 297) < 2, (w4, h4))
w5, h5 = pdf_page_size_mm(ADMIN.get(f"/result/1/pdf?term_id={term1}").data)
check("school 1's own choice (A5, left set last in the loop above) is still unaffected by school 2's activity", abs(w5 - 148) < 2 and abs(h5 - 210) < 2, (w5, h5))

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
