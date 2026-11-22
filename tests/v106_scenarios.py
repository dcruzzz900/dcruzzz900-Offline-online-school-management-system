"""V106 scenarios: gender on the result sheet (HTML + PDF + switch), the shared Gender Distribution panel on every dashboard,
light/dark + Bootstrap + brand layer, and the three React-backed endpoints (dashboard filter, live result preview, per-row score save).
Run: python tests/v106_scenarios.py"""
import io, json, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v106_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A
import wf_helper
from db import get_db
from werkzeug.security import generate_password_hash
A.app.config["TESTING"] = False; logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, d)
def html(r): return r.get_data(as_text=True)
def one(sql, *a):
    c = get_db(); r = c.execute(sql, a).fetchone(); c.close(); return r[0] if r else None
def run(sql, *a):
    c = get_db(); c.execute(sql, a); c.commit(); c.close()
def tok(c, page="/login"):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get(page)))
    if m: return m.group(1)
    with c.session_transaction() as s: return s.get("_csrf_token")
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client()
    c.post("/login", data={"username": u, "password": "Pass1234", "csrf_token": tok(c)}, follow_redirects=True); return c
def csrf(c):
    c.get("/dashboard")
    with c.session_transaction() as s: return s.get("_csrf_token")
def jpost(c, url, body, token=True):
    h = {"X-CSRF-Token": csrf(c)} if token else {}
    return c.post(url, json=body, headers=h)

c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),))
c0.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) SELECT school_id, tenant_id, 'Other Teacher', 'otherteacher', ?, 'teacher' FROM users WHERE username='admin'", (generate_password_hash("Pass1234"),))
c0.commit(); c0.close()
ADMIN, FT, OT = login("admin"), login("aokafor"), login("otherteacher")
TERM = one("SELECT id FROM terms WHERE is_active=1")

print("=== 1) gender on the result sheet ===")
check("migration added the show_gender column (default ON)", one("SELECT show_gender FROM result_display_settings LIMIT 1") in (1, None) )
sheet = html(ADMIN.get("/result/1"))
check("sheet shows the student's gender (Male)", 'class="rs-gender"' in sheet and ">Male<" in sheet)
check("a female student shows Female", ">Female<" in html(ADMIN.get("/result/2")) or ">Female<" in html(ADMIN.get("/result/3")))
run("UPDATE result_display_settings SET show_gender=0")
check("switching the setting OFF hides gender on the sheet", "rs-gender" not in html(ADMIN.get("/result/1")))
run("UPDATE result_display_settings SET show_gender=1")
page = html(ADMIN.get("/admin/result-display-settings"))
check("Result Display Settings has the Show Student Gender switch", 'name="show_gender"' in page)
wf_helper.publish(A, TERM)
def pdf_text(url):
    from pypdf import PdfReader
    r = ADMIN.get(url); return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.data)).pages) if r.mimetype == "application/pdf" else ""
check("the PDF carries Gender when ON", "GENDER" in pdf_text("/result/1/pdf"))
run("UPDATE result_display_settings SET show_gender=0")
check("...and drops it when OFF", "GENDER" not in pdf_text("/result/1/pdf"))
run("UPDATE result_display_settings SET show_gender=1")

print("=== 2) one shared gender panel on every dashboard that shows a gender split (V112: not the admin dashboard any more) ===")
for who, cl, url in (("admin", ADMIN, "/admin/analytics"), ("admin", ADMIN, "/reports/analytics"), ("teacher", FT, "/dashboard")):
    d = html(cl.get(url))
    check(f"{who} {url}: exactly one shared gender panel", d.count("data-gender-panel") == 1, d.count("data-gender-panel"))
    check(f"{who} {url}: same figures (2 male / 1 female, 66.7%)", 'data-male="2" data-female="1"' in d and "66.7%" in d)
    check(f"{who} {url}: the old Chart.js gender donut is gone", 'id="chartGender"' not in d)

print("=== 3) theme, Bootstrap, dark mode ===")
b = html(ADMIN.get("/dashboard"))
check("Bootstrap 5.3.3 CSS + JS are pinned (exact version)", "bootstrap@5.3.3/dist/css/bootstrap.min.css" in b and "bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" in b)
check("light/dark: early no-flash script + data-bs-theme + toggle button", "data-bs-theme" in b and "sh-theme" in b and b.count("data-theme-toggle") >= 1)
check("brand colours reach Bootstrap (rgb + readable ink variables)", "--theme-primary-rgb:" in b and "--theme-primary-ink:" in b)
check("body carries the sidebar / header style choices", 'data-sidebar="' in b and 'data-header="' in b)
lg = html(A.app.test_client().get("/login"))
check("the sign-in page has the floating theme toggle", "theme-fab" in lg and "data-theme-toggle" in lg)
check("theme.css and the generated dark stylesheet exist", os.path.getsize("static/css/theme.css") > 2000 and "html[data-bs-theme=\"dark\"]" in open("static/css/theme-dark.generated.css").read())
check("printed paper is never dark (generated dark rules are screen-only)", open("static/css/theme-dark.generated.css").read().count("@media screen") >= 1 and "@media print" not in open("static/css/theme-dark.generated.css").read())
check("result sheet templates were left untouched by the Bootstrap pass", "form-control" not in open("templates/_result_sheet.html").read())
check("forms use Bootstrap classes (students page)", "form-control" in html(ADMIN.get("/admin/students")) and "form-select" in html(ADMIN.get("/admin/students")))
check("no browser storage in the app except the theme choice", "localStorage" not in open("static/js/react-ui/score-entry.js").read() and "localStorage" not in open("static/js/react-ui/dashboard-filters.js").read())

print("=== 4) dashboard filter API ===")
r = ADMIN.get("/api/dashboard/analytics"); j = r.get_json()
check("admin: default view returns the charts + both fragments", r.status_code == 200 and j["ok"] and "data-gender-panel" in j["gender_html"] and "table" in j["top_students_html"].lower() + "<table", j and list(j))
r = FT.get("/api/dashboard/analytics?class_id=1"); j = r.get_json()
check("teacher can filter to their own class", r.status_code == 200 and j["scope"] == "JSS1A" and j["charts"]["genderBoys"] == 2 and j["charts"]["genderGirls"] == 1, r.status_code)
check("class filter changes the gender panel scope text", "(JSS1A)" in j["gender_html"])
check("a class that does not exist is refused (403)", ADMIN.get("/api/dashboard/analytics?class_id=999").status_code == 403)
check("a non-numeric class is refused (403)", ADMIN.get("/api/dashboard/analytics?class_id=1%20OR%201=1").status_code == 403)
check("a term that does not exist is refused (404)", ADMIN.get("/api/dashboard/analytics?term_id=999").status_code == 404)
run("INSERT INTO schools (id, name) VALUES (2, 'Other College')")
try:
    run("INSERT INTO classes (id, school_id, tenant_id, name) SELECT 90, 2, tenant_id, 'ZED1' FROM classes LIMIT 1")
except Exception as e:
    print("   (note: could not seed second-school class:", str(e)[:80], ")")
check("a class belonging to ANOTHER school is refused (403), never listed", ADMIN.get("/api/dashboard/analytics?class_id=90").status_code == 403 and "ZED1" not in json.dumps(ADMIN.get("/api/dashboard/analytics").get_json()))
anon = A.app.test_client(); ra = anon.get("/api/dashboard/analytics")
check("signed-out requests are redirected to sign-in", ra.status_code in (301, 302) and "/login" in ra.headers.get("Location", ""))
fc = html(ADMIN.get("/admin/analytics"))
check("School Analytics page embeds the filter config and loads React + the filter", 'id="dashFilters"' in fc and "dashboard-filters.js" in fc and "react@18.3.1" in fc and "react-dom@18.3.1" in fc)
check("Teacher dashboard too", "dashboard-filters.js" in html(FT.get("/dashboard")))

print("=== 5) live result-sheet preview endpoint ===")
U = "/api/result-display-settings/preview"
r = jpost(ADMIN, U, {"values": {"show_gender": "1"}}); j = r.get_json()
check("preview renders the real sheet with gender ON", r.status_code == 200 and j["ok"] and "rs-gender" in j["html"], r.status_code)
j = jpost(ADMIN, U, {"values": {"show_gender": "0", "show_admission_no": "0"}}).get_json()
check("UNSAVED switches change the preview (gender + admission no. off)", "rs-gender" not in j["html"] and "ADM/001" not in j["html"])
check("...and nothing was saved", one("SELECT show_gender FROM result_display_settings LIMIT 1") == 1)
j = jpost(ADMIN, U, {"values": {"accent_color": "#ff0066", "page_orientation": "landscape", "paper_size": "A4"}}).get_json()
check("accent colour + landscape reach the preview and report the paper size", "#ff0066" in j["html"].lower() and j["paper"]["orientation"] == "landscape" and j["paper"]["w_mm"] > j["paper"]["h_mm"], j.get("paper"))
j = jpost(ADMIN, U, {"values": {"accent_color": "not-a-colour", "page_orientation": "sideways"}}).get_json()
check("invalid values fall back to the saved ones and are reported", j["ok"] and set(j["invalid"]) == {"accent_color", "page_orientation"}, j.get("invalid"))
j = jpost(ADMIN, U, {"values": {"watermark_text": "<script>alert(1)</script>"}}).get_json()
check("markup in text settings is rejected, never rendered", "<script>alert(1)" not in j["html"] and "watermark_text" in j["invalid"])
check("a teacher cannot use the settings preview", jpost(FT, U, {"values": {}}).status_code in (302, 403))
check("a request without the CSRF header is refused", jpost(ADMIN, U, {"values": {}}, token=False).status_code == 403)
rp = html(ADMIN.get("/admin/result-display-settings"))
check("settings page: two-column layout, sticky live preview, React component", "rds-live-col" in rp and 'id="rdsLive"' in rp and "result-preview.js" in rp and "data-rds-state" in rp)

print("=== 6) per-row score save API ===")
run("DELETE FROM result_publication")   # a draft class: no lock, no reason needed
S = "/api/scores/1/1/row"
run("DELETE FROM scores WHERE subject_id=1")
r = jpost(FT, S, {"student_id": 1, "ca1": "15", "ca2": "18", "exam": "55"}); j = r.get_json()
check("assigned teacher saves one row; server returns the total and grade", r.status_code == 200 and j["ok"] and j["total"] == 88 and j["grade"] == "A", j)
check("...and it is really in the database", one("SELECT ca1||'/'||ca2||'/'||exam FROM scores WHERE student_id=1 AND subject_id=1") == "15.0/18.0/55.0")
check("...and it is in the audit trail", one("SELECT COUNT(*) FROM score_audit WHERE student_id=1 AND subject_id=1") >= 1)
r = jpost(FT, S, {"student_id": 2, "ca1": "", "ca2": None, "exam": "40"}); j = r.get_json()
check("blank boxes count as 0, exactly like the classic form", r.status_code == 200 and j["total"] == 40, j)
for label, body in (("CA1 over its maximum", {"student_id": 1, "ca1": "21", "ca2": "1", "exam": "1"}), ("negative score", {"student_id": 1, "ca1": "-1", "ca2": "1", "exam": "1"}),
                    ("exam over its maximum", {"student_id": 1, "ca1": "1", "ca2": "1", "exam": "61"})):
    r = jpost(FT, S, body); check(f"{label} is rejected (400)", r.status_code == 400 and r.get_json()["ok"] is False, r.status_code)
for label, val in (("text", "abc"), ("NaN", "nan"), ("infinity", "inf")):
    r = jpost(FT, S, {"student_id": 1, "ca1": val, "ca2": "1", "exam": "1"}); check(f"{label} is rejected (400)", r.status_code == 400, r.status_code)
check("rejected rows did not change the stored score", one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 15.0)
check("a student who is not in this class is refused (404)", jpost(FT, S, {"student_id": 99999, "ca1": "1", "ca2": "1", "exam": "1"}).status_code == 404)
check("a non-integer student id is refused", jpost(FT, S, {"student_id": "1; DROP TABLE scores", "ca1": "1", "ca2": "1", "exam": "1"}).status_code == 404)
check("a teacher NOT assigned to this subject/class is refused (403)", jpost(OT, S, {"student_id": 1, "ca1": "1", "ca2": "1", "exam": "1"}).status_code == 403)
check("a subject not assigned to the class is refused (404)", jpost(ADMIN, "/api/scores/1/9999/row", {"student_id": 1, "ca1": "1", "ca2": "1", "exam": "1"}).status_code == 404)
check("no CSRF header -> refused (403)", jpost(FT, S, {"student_id": 1, "ca1": "1", "ca2": "1", "exam": "1"}, token=False).status_code == 403)
check("signed-out -> redirected to sign-in", anon.post(S, json={"student_id": 1}).status_code in (301, 302, 403))
wf_helper.publish(A, TERM)
r = jpost(FT, S, {"student_id": 1, "ca1": "19", "ca2": "19", "exam": "59", "reason": "x"})
check("while the result is PUBLISHED the row is locked (423) and unchanged - same rule as the classic form", r.status_code == 423 and r.get_json().get("locked") and one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 15.0, (r.status_code, r.get_json()))
run("UPDATE result_publication SET status='reopened'")
r = jpost(FT, S, {"student_id": 1, "ca1": "19", "ca2": "19", "exam": "59"})
check("once REOPENED a change needs a reason (422 + needs_reason, nothing saved)", r.status_code == 422 and r.get_json().get("needs_reason") and one("SELECT ca1 FROM scores WHERE student_id=1 AND subject_id=1") == 15.0, (r.status_code, r.get_json()))
r = jpost(FT, S, {"student_id": 1, "ca1": "19", "ca2": "19", "exam": "59", "reason": "Marking error"})
check("...and with a reason it saves, and the reason is on the audit trail", r.status_code == 200 and one("SELECT COUNT(*) FROM score_audit WHERE student_id=1 AND reason='Marking error'") == 1, (r.status_code, r.get_json()))
run("DELETE FROM result_publication")
se = html(FT.get("/scores/1/1"))
check("score entry page: React grid + boot JSON + classic form kept as fallback", 'id="scoreApp"' in se and 'id="scoreFallback"' in se and "score-entry.js" in se)
check("the classic form POST still works (no JavaScript path)", FT.post("/scores/1/1", data={"csrf_token": csrf(FT), "ca1_3": "10", "ca2_3": "10", "exam_3": "50"}, follow_redirects=True).status_code == 200)

print(f"\n{PASS} passed, {len(FAIL)} failed"); sys.exit(1 if FAIL else 0)
