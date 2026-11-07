"""V101 scenarios: six selectable result sheet designs (settings-driven, print + PDF on both render paths), passport fills
its frame without a border, tick-box domain rating table (blank clears), submit-for-review needs only ONE saved score,
form teachers can save ratings while the Principal's comment is shown. Run: python tests/v101_scenarios.py"""
import io, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v101_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A, html_pdf, wf_helper as W
from db import get_db, RESULT_TEMPLATES
from werkzeug.security import generate_password_hash
A.app.config["TESTING"] = False
logging.disable(logging.CRITICAL)
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

c0 = get_db()
c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
sid = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
for n in ("2nd Term", "3rd Term", "4th Term", "5th Term"):
    c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,0)", (n, sid))
terms = [r[0] for r in c0.execute("SELECT id FROM terms WHERE session_id=? ORDER BY id", (sid,))]
T1, T2, T3, T4, T5 = terms
subs = [r[0] for r in c0.execute("SELECT id FROM subjects WHERE school_id=1")]
for t in (T1, T2, T3):
    for s in subs:
        c0.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,12,15,0,40)", (s, t))
c0.commit(); c0.close()
ADMIN, FT = login("admin"), login("aokafor")
ex = lambda: "/result/1/extra"
pg = lambda t: f"/result/1?term_id={t}"
prn = lambda t: f"/result/1/print?term_id={t}"
pdf = lambda t: f"/result/1/pdf?term_id={t}"
with A.app.test_request_context():
    _chk = (A.url_for("result_extra", student_id=1), A.url_for("result", student_id=1, term_id=T3), A.url_for("result_print", student_id=1, term_id=T3), A.url_for("result_pdf", student_id=1, term_id=T3))
ex = lambda: _chk[0]
pg = lambda t: _chk[1].replace(f"term_id={T3}", f"term_id={t}")
prn = lambda t: _chk[2].replace(f"term_id={T3}", f"term_id={t}")
pdf = lambda t: _chk[3].replace(f"term_id={T3}", f"term_id={t}")
c = get_db(); tids = [r[0] for r in c.execute("SELECT id FROM skill_traits WHERE school_id=1 AND COALESCE(is_active,1)=1")]; c.close()

# ---- A) rating table with ticks instead of dropdowns, blank clears
r = ADMIN.get(pg(T3)); s = html(r)
check("domain ratings use a tick-box table (no dropdown)", 'class="rt"' in s and 'type="radio"' in s and '<select name="trait_' not in s)
check("every domain item has five tick boxes (1-5)", s.count('class="rt-box"') == 15 * 5, s.count('class="rt-box"'))
check("the legend and 'leave blank' wording is kept", "1 = Poor" in s and "leave blank for no rating" in s)
form = {"term_id": T3}; form.update({f"trait_{t}": "4" for t in tids})
post(ADMIN, ex(), form, pg(T3))
check("ticked ratings are saved (15)", one("SELECT COUNT(*) FROM student_skill_ratings WHERE student_id=1 AND term_id=?", T3) == 15)
form = {"term_id": T3}; form.update({f"trait_{t}": ("" if i == 0 else "4") for i, t in enumerate(tids)})
post(ADMIN, ex(), form, pg(T3))
check("a blank (un-ticked) row clears that rating only", one("SELECT COUNT(*) FROM student_skill_ratings WHERE student_id=1 AND term_id=?", T3) == 14)
check("the saved ticks come back ticked on the page", html(ADMIN.get(pg(T3))).count("checked") >= 14)
post(ADMIN, ex(), {"term_id": T3, "principal_comment": "Excellent.", **{f"trait_{t}": "3" for t in tids}}, pg(T3))

# ---- B) form teacher saves ratings while the Principal's comment is shown
check("the form teacher sees the rating table", 'class="rt"' in html(FT.get(pg(T3))))
c = get_db(); c.execute("INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status) SELECT 1,tenant_id,1,?,'draft' FROM schools WHERE id=1", (T4,)); c.commit(); c.close()
c = get_db(); c.execute("INSERT INTO student_term_info(student_id,term_id,principal_comment) VALUES(1,?,?)", (T4, "Principal wrote this.")); c.commit(); c.close()
form = {"term_id": T4, "teacher_comment": "Teacher note.", "principal_comment": "tampered\r\ntext"}; form.update({f"trait_{t}": "5" for t in tids})
post(FT, ex(), form, pg(T4))
check("form teacher's ratings ARE saved with the Principal's box present", one("SELECT COUNT(*) FROM student_skill_ratings WHERE student_id=1 AND term_id=?", T4) == 15)
check("form teacher's own comment is saved", one("SELECT teacher_comment FROM student_term_info WHERE student_id=1 AND term_id=?", T4) == "Teacher note.")
check("the Principal's comment is left untouched", one("SELECT principal_comment FROM student_term_info WHERE student_id=1 AND term_id=?", T4) == "Principal wrote this.")
form = {"term_id": T4, "principal_comment": "Principal wrote this.", "teacher_comment": "Teacher note."}; form.update({f"trait_{t}": "2" for t in tids})
post(FT, ex(), form, pg(T4))
check("saving again unchanged also works", one("SELECT rating FROM student_skill_ratings WHERE student_id=1 AND term_id=? LIMIT 1", T4) == 2)

# ---- C) submit / approve / publish needs only ONE saved score
WF = "/results/workflow"
r = post(ADMIN, f"{WF}/1/{T5}/submit", {}, f"{WF}?term_id={T5}")
check("a class with NO saved score still cannot be submitted", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T5) in (None, "draft"))
c = get_db(); c.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,10,10,0,30)", (subs[0], T5)); c.commit(); c.close()
post(ADMIN, f"{WF}/1/{T5}/submit", {}, f"{WF}?term_id={T5}")
check("ONE saved score (one student, one subject) is enough to submit", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T5) == "submitted")
check("submit was recorded in the audit trail", one("SELECT COUNT(*) FROM result_publication_audit WHERE class_id=1 AND term_id=? AND action='submit'", T5) == 1)
for act in ("start_review", "approve"):
    post(ADMIN, f"{WF}/1/{T5}/{act}", {}, f"{WF}?term_id={T5}")
check("it can then be reviewed and approved", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T5) == "approved", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T5))
c = get_db(); c.execute("UPDATE schools SET readiness_status='ready' WHERE id=1"); c.commit(); c.close()
post(ADMIN, f"{WF}/1/{T5}/publish", {}, f"{WF}?term_id={T5}")
check("and published", one("SELECT status FROM result_publication WHERE class_id=1 AND term_id=?", T5) == "published")

# ---- D) six designs: registry, selection, and every design honours the settings
keys = [k for k, _l, _d in RESULT_TEMPLATES]
check("six designs are offered", len(keys) == 6 and keys[0] == "professional_classic", keys)
for t in (T1, T2, T3): W.publish(A, t)
sp = html(ADMIN.get("/admin/result-display-settings"))
check("the settings page shows a card + live preview for every design", sp.count('class="sty-card') >= 6 and sp.count('name="template"') == 6)
c = get_db(); c.execute("UPDATE result_display_settings SET show_passport=1"); c.commit(); c.close()
r = post(ADMIN, "/admin/result-display-settings", {"template": "sidebar_profile", "title": "Terminal Report Sheet", "accent_color": "#0b2a6f", "secondary_color": "#29a9e0",
        "header_layout": "logo-left", "signature_layout": "split", "page_orientation": "portrait", "font_scale": "normal", "paper_size": "A4", "pdf_font": "Helvetica",
        **{k: "1" for k in ("show_passport", "show_logo", "show_domains", "show_attendance", "show_days_opened", "show_days_present", "show_days_absent", "show_days_late", "show_teacher_comment",
                            "show_principal_comment", "show_all_comments", "show_teacher_signature", "show_teacher_sign_date", "show_principal_signature", "show_principal_sign_date",
                            "show_score", "show_grade", "show_remarks", "show_admission_no", "show_class", "show_session", "show_term", "show_overall_position", "show_grading_key", "show_promotion")}},
        "/admin/result-display-settings")
check("choosing a design saves it", one("SELECT template FROM result_display_settings WHERE school_id=1") == "sidebar_profile", r.status_code)
post(ADMIN, "/admin/result-display-settings", {"template": "not_a_design", "title": "Terminal Report Sheet", "accent_color": "#0b2a6f", "secondary_color": "#29a9e0", "header_layout": "logo-left",
     "signature_layout": "split", "page_orientation": "portrait", "font_scale": "normal", "paper_size": "A4", "pdf_font": "Helvetica", "show_passport": "1"}, "/admin/result-display-settings")
check("an unknown design name is refused (kept as before)", one("SELECT template FROM result_display_settings WHERE school_id=1") == "sidebar_profile")
import db as _db
c = get_db()
for _k, _l, _d in _db.RESULT_BOOL_SETTINGS:
    try: c.execute(f"UPDATE result_display_settings SET {_k}=?", (1 if _d else 0,))
    except Exception: pass
c.commit(); c.close()
from pypdf import PdfReader
def text(b): return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)
def one_page(b): return len(PdfReader(io.BytesIO(b)).pages) == 1
c = get_db(); c.execute("UPDATE result_display_settings SET show_attendance=1,show_domains=1,show_principal_comment=1,show_teacher_comment=1,show_all_comments=1"); c.commit(); c.close()
for key in keys:
    c = get_db(); c.execute("UPDATE result_display_settings SET template=?", (key,)); c.commit(); c.close()
    s = html(ADMIN.get(prn(T3)))
    check(f"[{key}] print page uses the design", f"rs-style-{key}" in s)
    for engine in ("chromium", "fallback"):
        if engine == "fallback": html_pdf._state.update(checked=True, ok=False)
        elif not html_pdf.engine_available(): continue
        r = ADMIN.get(pdf(T3)); t = text(r.data)
        check(f"[{key}/{engine}] PDF is one page", r.status_code == 200 and one_page(r.data), len(PdfReader(io.BytesIO(r.data)).pages) if r.status_code == 200 else r.status_code)
        check(f"[{key}/{engine}] PDF has the results table, summary and every domain item", all(x.lower() in t.lower() for x in ("Remark", "Cooperation", "Physical Coordination", "Total Subjects")), t[:200])
html_pdf._state.update(checked=False)
# settings are obeyed by EVERY design
for key in keys:
    c = get_db(); c.execute("UPDATE result_display_settings SET template=?, show_domains=0, show_attendance=0, show_teacher_comment=0, show_principal_comment=0, show_passport=0, watermark_text='ZZWM', show_watermark=1", (key,)); c.commit(); c.close()
    s = html(ADMIN.get(prn(T3)))
    check(f"[{key}] domains/attendance/comments/passport switches are obeyed", "Domain Ratings" not in s and "Days Present" not in s and "Comment" not in s and "rs-passport" not in s)
    check(f"[{key}] watermark setting is obeyed", "ZZWM" in s)
    html_pdf._state.update(checked=True, ok=False)
    t = text(ADMIN.get(pdf(T3)).data)
    check(f"[{key}/fallback] PDF obeys the same switches", "Domain Ratings" not in t and "Days Present" not in t.replace("DAYS PRESENT", "Days Present") and "Cooperation" not in t, t[-300:])
    html_pdf._state.update(checked=False)
c = get_db(); c.execute("UPDATE result_display_settings SET show_domains=1, show_attendance=1, show_teacher_comment=1, show_principal_comment=1, show_passport=1, show_watermark=0, template='professional_classic'"); c.commit(); c.close()
c = get_db(); c.execute("UPDATE schools SET pdf_font='Times-Roman'"); c.commit(); c.close()
s = html(ADMIN.get(prn(T3)))
check("the PDF/report font setting now also drives the on-screen/print sheet", "Times New Roman" in s)
c = get_db(); c.execute("UPDATE schools SET pdf_font='Helvetica'"); c.commit(); c.close()

# ---- E) passport fills its frame, no border
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("passport photo covers its frame (no letterboxing)", ".rs-passport.has-photo img{width:100%;height:100%;object-fit:cover" in css)
check("passport frame has no border line", ".rs-passport.has-photo{border:0" in css and "border:1.5px solid var(--rs-line);border-radius:1.5mm" not in css)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
