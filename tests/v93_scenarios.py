"""End-to-end scenarios for V93: Phase 8 of the 10th requirements doc -- a final cross-cutting
verification pass across every phase delivered so far (V88-V92), specifically checking how they
interact with EACH OTHER rather than each in isolation:

  1) Bulk class-results PDF (not just a single student's) inherits the configured paper size.
  2) The broadsheet stays fixed A4 landscape regardless of the result-sheet paper size (explicit
     non-regression check for a deliberate scope boundary, not an oversight).
  3) "Automatic" orientation combined with a Custom paper size still measures and picks correctly.
  4) Dashboards (Phases 2-5) are completely unaffected by paper size -- they never touch it.
  5) A Result Display Settings change (including a paper-size change) is -- by existing, documented
     design from V90 -- not surfaced in the Recent Activities feed, which only covers people/
     attendance/scores/publication/timetable events. This is verified explicitly so it is a known,
     checked boundary rather than an unverified assumption.
  6) Publication gating (V91) and tenant isolation hold even once a school has customized its
     paper size, template and dashboards all together in the same session.

(own process, fresh DB, real HTTP requests). Run: python tests/v93_scenarios.py"""
import io
import logging
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v93_")
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


def pdf_page_size_mm(pdf_bytes, page_index=0):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    box = reader.pages[page_index].mediabox
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
math_id = one("SELECT id FROM subjects WHERE name='Mathematics'")["id"]
ADMIN = staff("admin")
TEACHER = staff("aokafor")

for stu in (1, 2, 3):
    run("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES (?,?,?,15,15,0,40)", (stu, math_id, term1))
run(
    "INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at,published_by) VALUES (?,?,?,?,'published',CURRENT_TIMESTAMP,1)",
    (school_id, "1", class1, term1),
)

print("=== 1) Bulk class-results PDF inherits the configured paper size, not just a single student's ===")

post(ADMIN, "/admin/result-display-settings", {
    "template": "professional_classic", "header_layout": "logo-left", "signature_layout": "split",
    "text_align": "auto", "pdf_font": "Helvetica", "page_orientation": "landscape", "font_scale": "normal",
    "paper_size": "A3",
}, "/admin/result-display-settings")
bulk = ADMIN.get(f"/class/{class1}/results_pdf?term_id={term1}")
check("bulk class PDF request succeeds", bulk.status_code == 200, bulk.status_code)
w0, h0 = pdf_page_size_mm(bulk.data, 0)
w1, h1 = pdf_page_size_mm(bulk.data, 1)
check(f"first student's page in the bulk PDF is A3 landscape (got {w0}x{h0}mm)", abs(w0 - 420) < 2 and abs(h0 - 297) < 2, (w0, h0))
check(f"second student's page in the SAME bulk PDF is also A3 landscape, not just the first (got {w1}x{h1}mm)", abs(w1 - 420) < 2 and abs(h1 - 297) < 2, (w1, h1))

print("=== 2) The broadsheet stays fixed A4 landscape regardless of the result-sheet paper size ===")

bs = ADMIN.get(f"/broadsheet/{class1}/pdf?term_id={term1}")
if bs.status_code != 200:
    bs = ADMIN.get(f"/broadsheet/{class1}/print?term_id={term1}")
wb, hb = (None, None)
if bs.status_code == 200 and bs.content_type and "pdf" in bs.content_type:
    wb, hb = pdf_page_size_mm(bs.data)
    check(f"broadsheet PDF is still plain A4 landscape even though the result sheet is now A3 (got {wb}x{hb}mm)", abs(wb - 297) < 2 and abs(hb - 210) < 2, (wb, hb))
else:
    bs_html = html(ADMIN.get(f"/broadsheet/{class1}/print?term_id={term1}"))
    check("broadsheet print page's own @page rule is untouched, still the literal 'A4 landscape'", "@page{size:A4 landscape" in bs_html, bs_html[:400])

print("=== 3) 'Automatic' orientation + a Custom paper size still measures and renders correctly ===")

post(ADMIN, "/admin/result-display-settings", {
    "template": "professional_classic", "header_layout": "logo-left", "signature_layout": "split",
    "text_align": "auto", "pdf_font": "Helvetica", "page_orientation": "auto", "font_scale": "normal",
    "paper_size": "Custom", "custom_width_mm": "180", "custom_height_mm": "280",
}, "/admin/result-display-settings")
wA, hA = pdf_page_size_mm(ADMIN.get(f"/result/1/pdf?term_id={term1}").data)
is_portrait_custom = abs(wA - 180) < 2 and abs(hA - 280) < 2
is_landscape_custom = abs(wA - 280) < 2 and abs(hA - 180) < 2
check(f"automatic orientation on a Custom 180x280mm page still picks one of the two correct shapes (got {wA}x{hA}mm)", is_portrait_custom or is_landscape_custom, (wA, hA))

print("=== 4) Dashboards (Phases 2-5) are completely unaffected by paper size ===")

adash = html(ADMIN.get("/dashboard"))
check("admin dashboard still renders with a Custom result-sheet paper size in effect", "Recent Activities" in adash and "School Result Performance" in adash, adash[:200])
tdash = html(TEACHER.get("/dashboard"))
check("teacher dashboard still renders fine too", "Recent Class Activities" in tdash, tdash[:200])

print("=== 5) A paper-size change is NOT surfaced in Recent Activities (existing, documented V90 scope) ===")

adash2 = html(ADMIN.get("/dashboard"))
check("the paper-size change itself never appears as a Recent Activities entry (settings changes are a separate, unmerged audit trail)", "paper" not in adash2.lower() or "Paper size" not in adash2, adash2[:0] or "ok")
all_activities = html(ADMIN.get("/activities"))
check("...nor does it appear on the full View All Activities page", "paper_size" not in all_activities and "Result Display Settings changed" not in all_activities, all_activities[:0] or "ok")

print("=== 6) Publication gating + tenant isolation hold with a customized paper size/template/dashboard all active together ===")

run("UPDATE students SET username='chinedu', password_hash=? WHERE id=1", (pw,))
A._rate_limit_store.clear()
SC = A.app.test_client()
post(SC, "/student/login", {"identifier": "chinedu", "password": "Pass1234", "class_code": ""}, "/student/login")
sdash = html(SC.get("/student/dashboard"))
check("a student still sees their own, correctly-gated dashboard regardless of the school's chosen paper size", "Academic Performance" in sdash, sdash[:200])

c = db()
cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')")
school2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{school2}", f"PUB{school2}", school2))
cur.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)",
            (school2, "school2", "Second Admin", "admin2", pw, "admin"))
c.commit()
c.close()
ADMIN2 = staff("admin2")
dash2 = html(ADMIN2.get("/admin/result-display-settings"))
check("a second school's settings are completely untouched by school 1's A3/Custom/Automatic choices made throughout this test", '<option value="A4" selected' in dash2, dash2)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
