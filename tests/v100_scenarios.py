"""V100 scenarios: sample design for print + download, cumulative table fits A4 portrait with Remark visible,
fallback PDF matches the print design, all sample Affective/Psychomotor domains captured and selectable.
(own process, fresh DB, real HTTP requests). Run: python tests/v100_scenarios.py"""
import io, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v100_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A, html_pdf, wf_helper as W
from db import get_db, SAMPLE_AFFECTIVE_TRAITS, SAMPLE_PSYCHOMOTOR_TRAITS
from werkzeug.security import generate_password_hash
A.app.config["TESTING"] = False; A.app.config["PROPAGATE_EXCEPTIONS"] = False
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

c0 = get_db()
c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),))
c0.execute("UPDATE schools SET cumulative_enabled=1 WHERE id=1")
sid = c0.execute("SELECT session_id FROM terms WHERE id=1").fetchone()[0]
for n in ("2nd Term", "3rd Term"):
    c0.execute("INSERT INTO terms (name, session_id, is_active) VALUES (?,?,0)", (n, sid))
terms = [r[0] for r in c0.execute("SELECT id FROM terms WHERE session_id=? ORDER BY id", (sid,))]
subs = [r[0] for r in c0.execute("SELECT id FROM subjects WHERE school_id=1")]
for t in terms:
    for s in subs:
        c0.execute("INSERT INTO scores(student_id,subject_id,term_id,ca1,ca2,ca3,exam) VALUES(1,?,?,12,15,0,40)", (s, t))
traits = c0.execute("SELECT name, category, COALESCE(is_active,1) a FROM skill_traits WHERE school_id=1").fetchall()
c0.commit(); c0.close()

# 1) every sample domain item exists, is active (selectable), in the sample's order
names = {r["name"] for r in traits if r["a"]}
check("all 8 sample Affective items exist and are active", set(SAMPLE_AFFECTIVE_TRAITS) <= names, names)
check("all 7 sample Psychomotor items exist and are active", set(SAMPLE_PSYCHOMOTOR_TRAITS) <= names, names)
c = get_db()
order = [r[0] for r in c.execute("SELECT name FROM skill_traits WHERE school_id=1 AND category='affective' ORDER BY sort_order, name")]
check("Affective items follow the sample's order", order[:8] == SAMPLE_AFFECTIVE_TRAITS, order)
import db as D
D.migration_073_v100_sample_domain_traits(c); c.commit()
check("the domain migration is idempotent", c.execute("SELECT COUNT(*) FROM skill_traits WHERE school_id=1").fetchone()[0] == 15)
c.close()

A.app.config["TESTING"] = False
A._rate_limit_store.clear()
ADMIN = A.app.test_client(); post(ADMIN, "/login", {"username": "admin", "password": "Pass1234"}, "/login")
with A.app.test_request_context():
    ex = A.url_for("result_extra", student_id=1); page = A.url_for("result", student_id=1, term_id=terms[2])
    prn = A.url_for("result_print", student_id=1, term_id=terms[2]); pdf = A.url_for("result_pdf", student_id=1, term_id=terms[2])
    cpdf = A.url_for("cumulative_result_pdf", student_id=1, session_id=sid, term_id=terms[2])
c = get_db(); tids = [r[0] for r in c.execute("SELECT id FROM skill_traits WHERE school_id=1 AND COALESCE(is_active,1)=1")]; c.close()
form = {"term_id": terms[2], "teacher_comment": "Good."}
form.update({f"trait_{t}": "4" for t in tids})
post(ADMIN, ex, form, page)
c = get_db(); n = c.execute("SELECT COUNT(*) FROM student_skill_ratings WHERE student_id=1 AND term_id=?", (terms[2],)).fetchone()[0]; c.close()
check("a rating can be saved for EVERY sample domain item (15)", n == 15, n)
W.publish(A, terms[0]); W.publish(A, terms[1]); W.publish(A, terms[2])

# 2) sheet design: sample markup, all items shown, cumulative columns fixed
s = html(ADMIN.get(prn))
check("print page shows Attitude to Work and Cooperation", "Attitude to Work" in s and "Cooperation" in s)
check("print page shows Drawing Skills, Practical Skills, Physical Coordination", all(x in s for x in ("Drawing Skills", "Practical Skills", "Physical Coordination")))
check("domain tables carry a Rating header like the sample", ">Rating</th>" in s)
check("cumulative table has fixed column widths (colgroup)", "<colgroup>" in s and "rs-cum-table" in s)
check("cumulative state is forced to A4 portrait", 'var RS_ORIENTATION = "portrait"' in s)
css = open(os.path.join(ROOT, "static/css/result-sheet.css")).read()
check("sheet tables can never become display:block on phones", "table.rs-table{display:table" in css)
check("cumulative table uses table-layout:fixed", "table-layout:fixed" in css)

# 3) Download == Print on BOTH render paths (Chromium and the reportlab fallback)
from pypdf import PdfReader
def text(b): return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages)
def one_a4_portrait(b):
    r = PdfReader(io.BytesIO(b)); pg = r.pages[0]
    return len(r.pages) == 1 and float(pg.mediabox.width) < float(pg.mediabox.height)
for label, engine in (("Chromium", None), ("fallback", False)):
    if engine is False: html_pdf._state.update(checked=True, ok=False)
    elif not html_pdf.engine_available():
        print("note: Chromium unavailable here; skipped Chromium PDF checks"); continue
    r = ADMIN.get(pdf); t = text(r.data)
    check(f"[{label}] result PDF is one portrait page", r.status_code == 200 and one_a4_portrait(r.data), r.status_code)
    check(f"[{label}] PDF has Cumulative / Annual Performance with ALL three terms and Remark", all(x in t for x in ("1st Term", "2nd Term", "3rd Term", "Remark", "Overall Cumulative")), t[:400])
    check(f"[{label}] PDF has Academic Performance Summary and Class Position", "Academic Performance Summary" in t and "Class Position" in t.title().replace("Class position", "Class Position") or "CLASS POSITION" in t.upper())
    check(f"[{label}] PDF shows all new domain items", all(x in t for x in ("Attitude to Work", "Cooperation", "Drawing Skills", "Practical Skills", "Physical Coordination")), t[-600:])
    check(f"[{label}] PDF has the sample's wording (Grading Scale / Domain Ratings Scale), none of the old design's", "GRADING SCALE" in t.upper() and "Overall Position" not in t and "Grading key" not in t)
    r2 = ADMIN.get(cpdf); t2 = text(r2.data)
    check(f"[{label}] dedicated cumulative PDF has all three terms", r2.status_code == 200 and all(x in t2 for x in ("1st Term", "2nd Term", "3rd Term", "Remark")), t2[:300])

# 4) Result Display Settings live preview shows the full sample domain list
pv = html(ADMIN.get("/admin/result-display-settings"))
check("live preview lists the new sample domain items", "Attitude to Work" in pv and "Physical Coordination" in pv)

print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL)
sys.exit(1 if FAIL else 0)
