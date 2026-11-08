"""V103 scenarios: subject position follows its switch on the cumulative table (HTML + PDF), cumulative broadsheet carries every term's
CA/exam/total, Start review opens the class's submitted results, approval notifies the class/form teacher, signature gap, Next Term
Resumes entered on the Academic Record page, status badge honest, download follows display settings. Run: python tests/v103_scenarios.py"""
import io, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v103_")
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
    d = dict(data or {}); d["csrf_token"] = tok(c, page or path); return c.post(path, data=d)
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client(); post(c, "/login", {"username": u, "password": "Pass1234"}, "/login"); return c
def one(q, *a):
    c = get_db(); r = c.execute(q, a).fetchone(); c.close(); return r[0] if r else None
def pdftext(b): return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)

c0 = get_db()
c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
sid = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
for n in ("2nd Term", "3rd Term"):
    c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,0)", (n, sid))
T1, T2, T3 = [r[0] for r in c0.execute("SELECT id FROM terms WHERE session_id=? ORDER BY id", (sid,))]
subs = [r[0] for r in c0.execute("SELECT id FROM subjects WHERE school_id=1")]
for t in (T1, T2, T3):
    for s in subs: c0.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,12,15,0,40)", (s, t))
c0.execute("UPDATE terms SET resumption_date='2027-05-05' WHERE id=?", (T3,))
c0.commit(); c0.close()
ADMIN, FT = login("admin"), login("aokafor")
with A.app.test_request_context():
    _u = (A.url_for("result_extra", student_id=1), A.url_for("result", student_id=1, term_id=T3), A.url_for("result_print", student_id=1, term_id=T3),
          A.url_for("result_pdf", student_id=1, term_id=T3), A.url_for("cumulative_broadsheet", class_id=1, session_id=sid, term_id=T3))
ex, pg_, prn_, pdf_, cbs = _u
pg = lambda t: pg_.replace(f"term_id={T3}", f"term_id={t}")
prn = lambda t: prn_.replace(f"term_id={T3}", f"term_id={t}")
pdf = lambda t: pdf_.replace(f"term_id={T3}", f"term_id={t}")
def setting(**kw):
    c = get_db()
    for k, v in kw.items(): c.execute(f"UPDATE result_display_settings SET {k}=?", (v,))
    c.commit(); c.close()
def sheet(t=T3): return html(ADMIN.get(prn(t)))
def fb(t=T3):
    html_pdf._state.update(checked=True, ok=False); r = ADMIN.get(pdf(t)); html_pdf._state.update(checked=False); return r

# ---- 1) subject position switch on the cumulative table
ADMIN.get("/admin/result-display-settings")      # creates the school's settings row
W.publish(A, T1); W.publish(A, T2); W.publish(A, T3)
setting(show_subject_position=1); s_on = sheet(); t_on = pdftext(fb().data)
setting(show_subject_position=0); s_off = sheet(); t_off = pdftext(fb().data)
check("cumulative table shows Pos. columns when 'Show subject position' is ON", s_on.count("<th>Pos.</th>") == 4, s_on.count("<th>Pos.</th>"))
check("cumulative table has NO Pos. column when it is OFF (print)", s_off.count("<th>Pos.</th>") == 0, s_off.count("<th>Pos.</th>"))
check("...nor in the downloaded PDF", t_off.count("Pos.") == 0 and t_on.count("Pos.") >= 4, (t_on.count("Pos."), t_off.count("Pos.")))
check("...and the Remark column is still fully there", "Remark" in s_off and "Remark" in t_off)
setting(show_subject_position=1)

# ---- 2) cumulative broadsheet carries every term's CA/exam/total
b = html(ADMIN.get(cbs))
check("broadsheet shows all 3 terms", all(x in b for x in ("1st Term", "2nd Term", "3rd Term")))
check("broadsheet has CA1, CA2, Exam and Total columns for each term", b.count("<th>CA1</th>") == 3 * len(subs) and b.count("<th>CA2</th>") == 3 * len(subs) and b.count("<th>Exam</th>") == 3 * len(subs) and b.count("<th>Total</th>") == 3 * len(subs), b.count("<th>CA1</th>"))
check("broadsheet shows the actual scores (12 / 15 / 40 / 67)", re.search(r"<td>12(\.0)?</td>", b) and re.search(r"<td>15(\.0)?</td>", b) and re.search(r"<td>40(\.0)?</td>", b) and re.search(r"<td class=\"tot\">67(\.0)?</td>", b))
check("broadsheet keeps cumulative average and position", "Cum. Avg" in b and "Position" in b)

# ---- 3) Start review -> the class's submitted results
c = get_db(); c.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('4th Term', ?, 0)", (sid,)); T4 = c.execute("SELECT MAX(id) FROM terms").fetchone()[0]; c.commit(); c.close()
c = get_db(); c.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,10,10,0,30)", (subs[0], T4)); c.commit(); c.close()
WF = "/results/workflow"
post(FT, f"{WF}/1/{T4}/submit", {}, f"{WF}?term_id={T4}")
check("form teacher submitted the class result", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T4) == "submitted")
r = post(ADMIN, f"{WF}/1/{T4}/start_review", {}, f"{WF}?term_id={T4}")
loc = r.headers.get("Location", "")
check("'Start review' takes the reviewer to that class's results", r.status_code == 302 and "/class/1/results" in loc and f"term_id={T4}" in loc, loc)
page = html(ADMIN.get(loc))
check("...which shows the submitted status and who submitted it", "Under review" in page and "submitted by" in page and "Terminal Results" in page, page[:300])
check("...and lists the class's students to open", "Obi" in page or "Chinedu" in page or "/result/" in page)

# ---- 4) approval notifies the class/form teacher
before = html(FT.get("/notifications"))
check("no approval message before approving", "Results approved" not in before)
post(ADMIN, f"{WF}/1/{T4}/approve", {}, f"{WF}?term_id={T4}")
check("result is approved", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T4) == "approved")
after = html(FT.get("/notifications"))
check("the class/form teacher gets a 'Results approved' notification naming the approver", "Results approved" in after and "approved by" in after and "admin" in after.lower(), after[-400:])
check("it is addressed to that teacher only (the approver does not get it)", "Results approved" not in html(ADMIN.get("/notifications")))
check("the notification shows in the teacher's unread count", one("SELECT COUNT(*) FROM notifications WHERE target_user_id=(SELECT id FROM users WHERE username='aokafor')") == 1)

# ---- 5) signature gap
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("blank space above the signature line is reduced (was 10mm)", ".rs-line{display:block;height:6.5mm" in css and "height:10mm" not in css.split("signatures")[1].split("/* keys */")[0])

# ---- 6) Next Term Resumes on the Academic Record page
setting(show_next_term_resumes=1)
pg3 = html(ADMIN.get(pg(T2)))
check("Academic Record page has a Next Term Resumes field", 'name="next_term_resumes"' in pg3 and "Next Term Resumes" in pg3)
check("...prefilled with the school's date for the next term", 'value="2027-05-05"' in pg3, re.findall(r'name="next_term_resumes"[^>]*', pg3))
check("sheet shows the school-wide date when the switch is on", "05/05/2027" in sheet(T2) or "5 May" in sheet(T2) or "2027" in sheet(T2))
# saving on an unpublished (draft) result stores the date...
c = get_db(); c.execute("UPDATE result_publication SET status='draft' WHERE term_id=?", (T4,)); c.commit(); c.close()
post(ADMIN, ex, {"term_id": T4, "next_term_resumes": "2027-01-11"}, pg(T4))
check("a date typed on the page is saved for that result", one("SELECT next_term_resumes FROM student_term_info WHERE student_id=1 AND term_id=?", T4) == "2027-01-11")
post(ADMIN, ex, {"term_id": T4, "next_term_resumes": ""}, pg(T4))
check("clearing it falls back to the school-wide date", one("SELECT next_term_resumes FROM student_term_info WHERE student_id=1 AND term_id=?", T4) is None)
# ...and a stored per-result date is what the printed sheet and the PDF show (published term, value set directly)
c = get_db(); c.execute("INSERT OR IGNORE INTO student_term_info(student_id,term_id) VALUES(1,?)", (T2,)); c.execute("UPDATE student_term_info SET next_term_resumes='2027-01-11' WHERE student_id=1 AND term_id=?", (T2,)); c.commit(); c.close()
s2 = sheet(T2)
check("...and the sheet shows it (switch ON)", "11/01/2027" in s2, re.findall(r"Next Term[^<]*<[^>]*>[^<]*", s2)[:2])
t2 = pdftext(fb(T2).data)
check("...and so does the downloaded PDF", "11/01/2027" in t2, t2[-300:])
setting(show_next_term_resumes=0)
check("switch OFF hides it on the sheet and in the PDF", "Next Term Resumes" not in sheet(T2) and "Next Term Resumes" not in pdftext(fb(T2).data))
setting(show_next_term_resumes=1)

# ---- 7) status badge is honest
c = get_db(); c.execute("UPDATE result_publication SET status='approved' WHERE term_id=?", (T4,)); c.commit(); c.close()
d = html(ADMIN.get(pg(T4)))
check("an approved-but-unpublished result does NOT say 'Published' on its card", 'status-badge success">Published' not in d and "Approved" in d, re.findall(r'status-badge[^<]*<', d))
check("a published result says Published", 'status-badge success">Published' in html(ADMIN.get(pg(T3))))
c = get_db(); c.execute("UPDATE result_publication SET status='draft' WHERE term_id=?", (T4,)); c.commit(); c.close()
check("a draft shows Draft", ">Draft<" in html(ADMIN.get(pg(T4))))

# ---- 8) download follows display settings (spot checks; tests/audit covers every switch)
setting(show_attendance=0, show_teacher_comment=0, show_principal_comment=0, show_domains=0)
tt = pdftext(fb().data)
check("PDF honours attendance / comments / domains switches like print", "Days Present" not in tt.title().replace("DAYS PRESENT", "Days Present") and "Domain Ratings" not in tt and "Comment" not in tt.title(), tt[-300:])
setting(show_attendance=1, show_teacher_comment=1, show_principal_comment=1, show_domains=1)

# ---- 9) accent colour lives in Result Display Settings and applies to the sheet
th = html(ADMIN.get("/admin/theme"))
check("Theme & Branding no longer has an Accent colour or a result-sheet preview", th and 'id="accentColor"' not in th and "RESULT SHEET" not in th and "previewResult" not in th, th[:100])
rds = html(ADMIN.get("/admin/result-display-settings"))
check("Result Display Settings has the Accent colour (with live preview script)", 'name="accent_color"' in rds and "Accent colour" in rds and "rsAccentInput" in rds)
base_form = {"template": "professional_classic", "title": "Terminal Report Sheet", "secondary_color": "#29a9e0", "header_layout": "logo-left", "signature_layout": "split",
             "page_orientation": "portrait", "font_scale": "normal", "paper_size": "A4", "pdf_font": "Helvetica", "show_term": "1", "show_session": "1", "show_class": "1", "show_score": "1", "show_grade": "1", "show_remarks": "1"}
post(ADMIN, "/admin/result-display-settings", {**base_form, "accent_color": "#aa0000"}, "/admin/result-display-settings")
check("a changed accent colour is saved", one("SELECT accent_color FROM result_display_settings WHERE school_id=1") == "#aa0000")
check("...and is applied to the printed sheet at once", "--rs-accent:#aa0000" in sheet())
check("...and to the downloaded PDF engine settings", A.result_sheet_settings(get_db(), 1)["accent"] == "#aa0000")
post(ADMIN, "/admin/result-display-settings", {**base_form, "accent_color": "#0b2a6f"}, "/admin/result-display-settings")
setting(show_subject_position=1, show_attendance=1, show_teacher_comment=1, show_principal_comment=1, show_domains=1, show_teacher_signature=1, show_principal_signature=1)

# ---- 10) the PDF-engine warning is gone; the signature line keeps its width
html_pdf._state.update(checked=True, ok=False)
dash = html(ADMIN.get("/dashboard")); html_pdf._state.update(checked=False)
check("the 'printing in a plain, generic layout' banner no longer appears", "plain, generic layout" not in dash and "PythonAnywhere" not in dash)
tpl = open(os.path.join(ROOT, "templates/_result_sheet.html")).read()
check("an uploaded signature sits ON a full-width line (wrapper keeps the width)", tpl.count('<i class="rs-line rs-line-img"><img') == 2)
check("the signature image itself has no border that would shrink the line", ".rs-sign .rs-line img{" in css and "border:0" in css.split(".rs-sign .rs-line img{")[1].split("}")[0])

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
