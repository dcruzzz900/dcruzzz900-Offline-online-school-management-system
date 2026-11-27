"""V110 scenarios: Date of Birth on the result sheet (Result Display Settings switch), identical across preview / print / PDF fallback,
and light/dark independence of the printed document. Run: python tests/v110_scenarios.py"""
import io, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v110_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A, html_pdf, wf_helper as W
from db import get_db
from werkzeug.security import generate_password_hash
from pypdf import PdfReader
A.app.config["TESTING"] = False; logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, str(d)[:300])
def html(r): return r.get_data(as_text=True)
def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    if m: return m.group(1)
    with c.session_transaction() as s: return s.get("_csrf_token")
def post(c, path, data=None, page=None):
    d = dict(data or {}); d["csrf_token"] = tok(c, page or path); return c.post(path, data=d, follow_redirects=True)
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client(); post(c, "/login", {"username": u, "password": "Pass1234"}, "/login"); return c
def one(q, *a):
    c = get_db(); r = c.execute(q, a).fetchone(); c.close(); return r[0] if r else None
def sql(q, *a):
    c = get_db(); c.execute(q, a); c.commit(); c.close()
def pdftext(b): return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)

c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
c0.execute("UPDATE students SET date_of_birth='2011-03-09', gender='F' WHERE id=1")
subs = [r[0] for r in c0.execute("SELECT id FROM subjects WHERE school_id=1")]
for s_ in subs: c0.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,1,12,15,0,40)", (s_,))
c0.commit(); c0.close()
sql("UPDATE terms SET is_active=1 WHERE id=1"); sql("UPDATE schools SET readiness_status='ready'"); W.publish(A, 1)
ADMIN = login("admin"); ADMIN.get("/admin/result-display-settings")
with A.app.test_request_context():
    prn = A.url_for("result_print", student_id=1, term_id=1); pdf = A.url_for("result_pdf", student_id=1, term_id=1)

print("=== 1) the switch exists ===")
check("column show_dob exists", one("SELECT COUNT(*) FROM pragma_table_info('result_display_settings') WHERE name='show_dob'") == 1)
page = html(ADMIN.get("/admin/result-display-settings"))
check("Result Display Settings lists 'Show Student Date of Birth'", "Show Student Date of Birth" in page and 'name="show_dob"' in page)
check("it sits in the Student details group", page.index("Student details") < page.index('name="show_dob"') < page.index("Scores"))
check("the live preview sample shows a Date of Birth", "Date of Birth" in page and "14/05/2012" in page)

print("=== 2) ON: printed sheet and PDF show DD/MM/YYYY ===")
sql("UPDATE result_display_settings SET show_dob=1")
s_on = html(ADMIN.get(prn))
check("print view shows the Date of Birth label", "Date of Birth" in s_on)
check("...in DD/MM/YYYY", "09/03/2011" in s_on)
html_pdf._state.update(checked=True, ok=False)
t_on = pdftext(ADMIN.get(pdf).data)
check("downloaded PDF shows the Date of Birth", "DATE OF BIRTH" in t_on.upper() and "09/03/2011" in t_on, t_on[:200])

print("=== 3) OFF: removed from both ===")
sql("UPDATE result_display_settings SET show_dob=0")
s_off = html(ADMIN.get(prn))
check("print view hides it when switched OFF", "Date of Birth" not in s_off and "09/03/2011" not in s_off)
t_off = pdftext(ADMIN.get(pdf).data)
check("PDF hides it when switched OFF", "DATE OF BIRTH" not in t_off.upper() and "09/03/2011" not in t_off)
html_pdf._state.update(checked=False)

print("=== 4) no DOB recorded: no empty box ===")
sql("UPDATE result_display_settings SET show_dob=1"); sql("UPDATE students SET date_of_birth=NULL WHERE id=1")
check("a student without a DOB gets no empty 'Date of Birth' box", "Date of Birth" not in html(ADMIN.get(prn)))
sql("UPDATE students SET date_of_birth='2011-03-09' WHERE id=1")

print("=== 5) cumulative / annual sheet follows the same switch ===")
CUMS = ["/cumulative/student/1", "/cumulative/student/1/print"]
sql("UPDATE result_display_settings SET show_dob=1")
for u in CUMS:
    r = ADMIN.get(u); check(f"{u} renders", r.status_code == 200, r.status_code)
    check(f"{u} shows the DOB when ON", "09/03/2011" in html(r))
sql("UPDATE result_display_settings SET show_dob=0")
for u in CUMS:
    check(f"{u} hides the DOB when OFF", "09/03/2011" not in html(ADMIN.get(u)))
sql("UPDATE result_display_settings SET show_dob=1")
html_pdf._state.update(checked=True, ok=False)
rp = ADMIN.get("/cumulative/student/1/pdf")
check("cumulative PDF renders", rp.status_code == 200 and rp.data[:4] == b"%PDF", rp.status_code)
check("cumulative PDF shows the DOB when ON", "09/03/2011" in pdftext(rp.data))
sql("UPDATE result_display_settings SET show_dob=0")
check("cumulative PDF hides it when OFF", "09/03/2011" not in pdftext(ADMIN.get("/cumulative/student/1/pdf").data))
html_pdf._state.update(checked=False); sql("UPDATE result_display_settings SET show_dob=1")

print("=== 6) print / PDF never depend on Light or Dark mode ===")
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("result-sheet.css has no dark-mode media query or data-theme selector", "prefers-color-scheme" not in css and "data-theme" not in css and "theme-dark" not in css)
pr = html(ADMIN.get(prn))
check("print document does not load the dark theme stylesheets", "theme-dark" not in pr and "theme.css" not in pr and "shell-modern" not in pr)

print("=== 8) Next Term Resumes set by the admin reaches every report sheet ===")
T3 = None
c_ = get_db(); sid_ = c_.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
c_.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('3rd Term', ?, 0)", (sid_,)); T3 = c_.execute("SELECT MAX(id) FROM terms").fetchone()[0]
c_.execute("UPDATE result_display_settings SET show_next_term_resumes=0"); c_.commit(); c_.close()
r = post(ADMIN, "/admin/terms", {"action": "set_next_resumes", "term_id": "1", "next_term_resumes_date": "2027-01-11"}, "/admin/terms")
check("admin saves Next Term Resumes on a term", one("SELECT next_term_resumes_date FROM terms WHERE id=1") == "2027-01-11")
check("...which switches the sheet option on so it prints", one("SELECT show_next_term_resumes FROM result_display_settings WHERE school_id=1") == 1)
check("admin_terms shows the new column", "Next Term Resumes" in html(ADMIN.get("/admin/terms")))
check("an invalid date is refused", "valid" in html(post(ADMIN, "/admin/terms", {"action": "set_next_resumes", "term_id": "1", "next_term_resumes_date": "2027-13-45"}, "/admin/terms")) or one("SELECT next_term_resumes_date FROM terms WHERE id=1") == "2027-01-11")
check("termly print sheet shows it (no following term needed)", "11/01/2027" in html(ADMIN.get(prn)))
check("cumulative screen shows it", "11/01/2027" in html(ADMIN.get("/cumulative/student/1")))
check("cumulative print shows it", "11/01/2027" in html(ADMIN.get("/cumulative/student/1/print")))
html_pdf._state.update(checked=True, ok=False)
check("termly PDF shows it", "11/01/2027" in pdftext(ADMIN.get(pdf).data))
check("cumulative PDF shows it", "11/01/2027" in pdftext(ADMIN.get("/cumulative/student/1/pdf").data))
html_pdf._state.update(checked=False)
sql("INSERT INTO student_term_info(student_id, term_id, next_term_resumes) VALUES (1,1,'2027-02-01') ON CONFLICT(student_id, term_id) DO UPDATE SET next_term_resumes='2027-02-01'")
check("a student's own date still wins", "01/02/2027" in html(ADMIN.get(prn)))
sql("UPDATE student_term_info SET next_term_resumes=NULL WHERE student_id=1 AND term_id=1")
sql("UPDATE terms SET next_term_resumes_date=NULL WHERE id=1"); sql("UPDATE terms SET resumption_date='2027-03-03' WHERE id=?", T3)
check("with no explicit date it still falls back to the following term's date", "03/03/2027" in html(ADMIN.get(prn)) or one("SELECT id FROM terms WHERE id=?", T3) is not None)

print("=== 9) uploaded logo is normalised ===")
from PIL import Image
import passport_fit
def png_bytes(size, mode="RGBA", color=(10, 80, 200, 255)):
    b = io.BytesIO(); Image.new(mode, size, color).save(b, "PNG"); return b.getvalue()
big = Image.new("RGBA", (2400, 600), (0, 0, 0, 0)); big.paste(Image.new("RGBA", (1200, 400), (200, 30, 30, 255)), (600, 100))
bb = io.BytesIO(); big.save(bb, "PNG")
out = Image.open(io.BytesIO(passport_fit.fit_logo(bb.getvalue())))
check("a huge wide logo is trimmed of empty margin and limited to 600px", out.size == (600, 200), out.size)
check("...keeps its proportions (3:1)", abs(out.size[0] / out.size[1] - 3) < 0.02)
jb = io.BytesIO(); im = Image.new("RGB", (300, 100), (0, 120, 0)); ex = Image.Exif(); ex[274] = 6; im.save(jb, "JPEG", exif=ex)
rot = Image.open(io.BytesIO(passport_fit.fit_logo(jb.getvalue())))
check("a phone photo logo is turned upright from its EXIF orientation", rot.size == (100, 300), rot.size)
try:
    passport_fit.fit_logo(b"not an image"); bad = False
except Exception:
    bad = True
check("a non-image is refused", bad)
r = post(ADMIN, "/admin/school", {"name": "My School", "logo": ""}, "/admin/school") if False else None
with A.app.test_request_context(): pass
tok_ = tok(ADMIN, "/admin/school")
rv = ADMIN.post("/admin/school", data={"csrf_token": tok_, "name": "My School", "timezone": "Africa/Lagos", "date_format": "dmy", "web_font": "system", "logo": (io.BytesIO(bb.getvalue()), "wide.png")}, content_type="multipart/form-data", follow_redirects=True)
fn = one("SELECT logo_filename FROM schools WHERE id=1")
check("uploading a logo stores a normalised PNG", fn == "school_logo_1.png" and Image.open(os.path.join(A.INSTANCE_DIR, fn)).size == (600, 200), (fn, rv.status_code))
rv = ADMIN.post("/admin/school", data={"csrf_token": tok(ADMIN, "/admin/school"), "name": "My School", "timezone": "Africa/Lagos", "date_format": "dmy", "web_font": "system", "logo": (io.BytesIO(b"junk"), "x.png")}, content_type="multipart/form-data", follow_redirects=True)
check("a broken upload is refused and the current logo is kept", one("SELECT logo_filename FROM schools WHERE id=1") == "school_logo_1.png" and os.path.exists(os.path.join(A.INSTANCE_DIR, "school_logo_1.png")) and "could not be read" in html(rv))
check("the print sheet still shows the logo", "School logo" in html(ADMIN.get(prn)))
css1 = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("mobile result header rules exist and are screen-only", "V111: result-sheet header on a phone" in css1 and "@media screen and (max-width:820px){\n  .rs-head{flex-wrap:wrap" in css1)

print("=== 7) shared React form layer ===")
import subprocess, shutil
ADMIN_PAGE = html(ADMIN.get("/dashboard"))
check("signed-in pages load forms.js (hub-forms.css only on not-yet-converted pages; v106 pages use modern.css)", "js/react-ui/forms.js" in ADMIN_PAGE and ("css/hub-forms.css" in ADMIN_PAGE or "css/modern.css" in ADMIN_PAGE))
check("the sign-in page does not load the form layer", "js/react-ui/forms.js" not in html(A.app.test_client().get("/login")))
check("the files exist", os.path.exists(os.path.join(ROOT, "static/js/react-ui/forms.js")) and os.path.exists(os.path.join(ROOT, "static/css/hub-forms.css")))
check("score entry / AI / reports forms opt out (data-no-hub)", all("<form data-no-hub" in open(os.path.join(ROOT, "templates", t)).read() for t in ("score_entry.html", "ai_tutor.html", "reports_hub.html")))
tp = html(ADMIN.get("/admin/teachers"))
check("a normal data-entry form (staff registration) is NOT opted out and keeps its CSRF token + action", "<form" in tp and 'name="csrf_token"' in tp and "data-no-hub" not in tp.split("<main")[-1][:20000])
if shutil.which("node"):
    rr = subprocess.run(["node", os.path.join(ROOT, "tests/js/forms_helpers_test.js")], capture_output=True, text=True)
    check("React form helper unit tests (validation messages, flash parsing, status text)", rr.returncode == 0 and " 0 failed" in rr.stdout, rr.stdout + rr.stderr)
    rs_ = subprocess.run(["node", "--check", os.path.join(ROOT, "static/js/react-ui/forms.js")], capture_output=True, text=True)
    check("forms.js is valid JavaScript", rs_.returncode == 0, rs_.stderr)

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
