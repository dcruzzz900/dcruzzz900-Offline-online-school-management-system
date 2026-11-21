"""V107 scenarios: per-user theme + text size, professional typography/dark palette, compulsory Date of Birth + Gender (all forms,
importers, data-completion), passport photograph fitting. Run: python tests/v107_scenarios.py"""
import io, json, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v107_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A
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
def post(c, path, data=None, page=None, files=None):
    d = dict(data or {}); d["csrf_token"] = tok(c, page or path)
    if files: d.update(files)
    return c.post(path, data=d, follow_redirects=True, content_type="multipart/form-data" if files else None)
def flashes(r): return " | ".join(re.findall(r'class="flash flash-\w+[^"]*"[^>]*>([^<]*)<', html(r)))
def csrf(c):
    c.get("/dashboard")
    with c.session_transaction() as s: return s.get("_csrf_token")

c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.commit(); c0.close()
ADMIN, FT = login("admin"), login("aokafor")
CLASS1 = one("SELECT id FROM classes ORDER BY id LIMIT 1")

print("=== 1) the shared Date of Birth + Gender rule ===")
from identity_rules import parse_dob, normalise_gender, identity_errors
import datetime
check("gender: Male/male/M -> M, Female/F -> F", normalise_gender("Male") == "M" and normalise_gender("f") == "F" and normalise_gender(" FEMALE ") == "F")
check("gender: blank / other / junk -> None (never guessed)", normalise_gender("") is None and normalise_gender(None) is None and normalise_gender("x") is None and normalise_gender("Other") is None)
check("dob: ISO accepted", parse_dob("2012-05-14") == ("2012-05-14", None))
check("dob: DD/MM/YYYY normalised to ISO", parse_dob("14/05/2012")[0] == "2012-05-14")
check("dob: blank refused", parse_dob("")[1] == "Date of Birth is required." and parse_dob(None)[0] is None)
check("dob: future refused", "future" in parse_dob((datetime.date.today() + datetime.timedelta(days=2)).isoformat())[1])
check("dob: impossible date (31 Feb) refused", parse_dob("2012-02-31")[0] is None and parse_dob("2012-02-31")[1])
check("dob: before 1900 refused", parse_dob("1850-01-01")[0] is None)
check("dob: too young for the role refused", parse_dob(datetime.date.today().isoformat(), min_age=14)[0] is None)
check("identity_errors reports both when both missing", len(identity_errors({}, 1)[2]) == 2)

print("=== 2) student forms refuse a missing Date of Birth / Gender ===")
n0 = one("SELECT COUNT(*) FROM students")
base = {"class_id": CLASS1, "admission_no": "V107-1", "first_name": "Ada", "last_name": "Obi"}
r = post(ADMIN, "/admin/students", {**base, "gender": "F"}, "/admin/students")
check("student without a Date of Birth is refused with a clear message", one("SELECT COUNT(*) FROM students") == n0 and "Date of Birth is required" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/students", {**base, "date_of_birth": "2012-05-14"}, "/admin/students")
check("student without Gender is refused with a clear message", one("SELECT COUNT(*) FROM students") == n0 and "Gender is required" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/students", {**base, "date_of_birth": "2999-01-01", "gender": "F"}, "/admin/students")
check("a future Date of Birth is refused", one("SELECT COUNT(*) FROM students") == n0 and "future" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/students", {**base, "date_of_birth": "not a date", "gender": "F"}, "/admin/students")
check("garbage Date of Birth is refused", one("SELECT COUNT(*) FROM students") == n0)
r = post(ADMIN, "/admin/students", {**base, "date_of_birth": "14/05/2012", "gender": "Female"}, "/admin/students")
check("a valid student is saved with ISO date and M/F code", one("SELECT date_of_birth||'/'||gender FROM students WHERE admission_no='V107-1'") == "2012-05-14/F", flashes(r))
sid1 = one("SELECT id FROM students WHERE admission_no='V107-1'")
r = post(ADMIN, f"/my-class/{CLASS1}/students/{sid1}/edit", {"first_name": "Ada", "last_name": "Obi", "admission_no": "V107-1", "gender": "F", "date_of_birth": ""}, f"/my-class/{CLASS1}/roster")
check("editing a student cannot blank the Date of Birth", one("SELECT date_of_birth FROM students WHERE id=?", sid1) == "2012-05-14" and "Date of Birth is required" in flashes(r), flashes(r))
r = post(ADMIN, f"/my-class/{CLASS1}/students/{sid1}/edit", {"first_name": "Ada", "last_name": "Obi", "admission_no": "V107-1", "gender": "", "date_of_birth": "2012-05-14"}, f"/my-class/{CLASS1}/roster")
check("...nor the Gender", one("SELECT gender FROM students WHERE id=?", sid1) == "F")
r = post(ADMIN, f"/my-class/{CLASS1}/roster", {"admission_no": "V107-2", "first_name": "Bayo", "last_name": "Eze", "gender": "M"}, f"/my-class/{CLASS1}/roster")
check("class roster (teacher form) also refuses a missing Date of Birth", one("SELECT COUNT(*) FROM students WHERE admission_no='V107-2'") == 0, flashes(r))
r = post(ADMIN, "/registrar/register", {"class_id": CLASS1, "admission_no": "V107-3", "first_name": "Kemi", "last_name": "Lawal", "gender": "F"}, "/registrar")
check("registrar admission also refuses a missing Date of Birth", one("SELECT COUNT(*) FROM students WHERE admission_no='V107-3'") == 0)

print("=== 3) staff / parent forms ===")
srow = {"name": "New Teacher", "username": "v107teach", "staff_id": "V-T-1", "password": "Pass12345", "email": "v107@example.com", "phone": "08031234567", "rbac_role": "Teacher"}
r = post(ADMIN, "/admin/teachers", srow, "/admin/teachers")
check("staff without Date of Birth / Gender is refused", one("SELECT COUNT(*) FROM users WHERE username='v107teach'") == 0 and "Date of Birth is required" in flashes(r) and "Gender is required" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/teachers", {**srow, "date_of_birth": datetime.date.today().isoformat(), "gender": "M"}, "/admin/teachers")
check("a staff member born today is refused (not realistic)", one("SELECT COUNT(*) FROM users WHERE username='v107teach'") == 0)
r = post(ADMIN, "/admin/teachers", {**srow, "date_of_birth": "1985-03-02", "gender": "M"}, "/admin/teachers")
check("a valid staff member is saved with Date of Birth and Gender", one("SELECT date_of_birth||'/'||gender FROM users WHERE username='v107teach'") == "1985-03-02/M", flashes(r))
anon = A.app.test_client()
for url in ("/register", "/register/parent", "/admin/students", "/admin/teachers"):
    d = html(ADMIN.get(url)) if url.startswith("/admin") else html(anon.get(url))
    check(f"{url}: Date of Birth + Gender fields are on the form, marked required", 'name="date_of_birth"' in d and 'name="gender"' in d and d.count("required") >= 2)
r = anon.post("/register/parent", data={"csrf_token": tok(anon, "/register/parent"), "first_name": "Pa", "surname": "Rent", "username": "v107parent", "password": "Pass12345!", "phone": "08030000000"}, follow_redirects=True)
check("parent sign-up without Date of Birth / Gender creates no account", one("SELECT COUNT(*) FROM parent_accounts WHERE username='v107parent'") == 0)

print("=== 4) CSV importers ===")
def csvfile(text): return {"csv_file": (io.BytesIO(text.encode()), "s.csv")}
r = post(ADMIN, "/admin/students/bulk_upload", {}, "/admin/students", files=csvfile("admission_no,first_name,last_name,class_name\nZ-1,A,B,JSS1A\n"))
check("a CSV with no gender / date_of_birth columns is refused", one("SELECT COUNT(*) FROM students WHERE admission_no='Z-1'") == 0 and "gender" in flashes(r) and "date_of_birth" in flashes(r), flashes(r))
r = post(ADMIN, "/admin/students/bulk_upload", {}, "/admin/students", files=csvfile("admission_no,first_name,last_name,class_name,gender,date_of_birth\nZ-2,A,B,JSS1A,,2012-01-01\nZ-3,C,D,JSS1A,F,\n"))
check("blank gender / blank date_of_birth cells are named and nothing is saved", one("SELECT COUNT(*) FROM students WHERE admission_no IN ('Z-2','Z-3')") == 0 and "gender is required" in flashes(r) and "date of birth is required" in flashes(r), flashes(r))

print("=== 5) data completion for records from before the rule ===")
run("INSERT INTO students (admission_no, first_name, last_name, class_id, school_id, tenant_id) SELECT 'OLD-1','Old','Record',?,school_id,tenant_id FROM students LIMIT 1", CLASS1)
oid = one("SELECT id FROM students WHERE admission_no='OLD-1'")
check("an old student really has no Date of Birth / Gender (nothing was invented)", one("SELECT COALESCE(date_of_birth,'')||COALESCE(gender,'') FROM students WHERE id=?", oid) == "")
page = html(ADMIN.get("/admin/data-completion"))
check("Data Completion lists the old student", "Record Old" in page or "Old Record" in page)
check("...and shows how many records need attention on the dashboard", "Data Completion" in html(ADMIN.get("/dashboard")))
r = post(ADMIN, "/admin/data-completion/save", {"kind": "student", "id": oid, "date_of_birth": "", "gender": "F"}, "/admin/data-completion")
check("saving without a Date of Birth is refused", one("SELECT COALESCE(date_of_birth,'') FROM students WHERE id=?", oid) == "")
r = post(ADMIN, "/admin/data-completion/save", {"kind": "student", "id": oid, "date_of_birth": "2011-09-09", "gender": "M"}, "/admin/data-completion")
check("saving valid values completes the record", one("SELECT date_of_birth||'/'||gender FROM students WHERE id=?", oid) == "2011-09-09/M")
check("...and it leaves the list", "Old Record" not in html(ADMIN.get("/admin/data-completion")) and "Record Old" not in html(ADMIN.get("/admin/data-completion")))
run("INSERT INTO schools (id, name) VALUES (7, 'Other College')")
run("INSERT INTO classes (id, school_id, tenant_id, name) SELECT 777, 7, tenant_id, 'ZED' FROM classes LIMIT 1")
run("INSERT INTO students (admission_no, first_name, last_name, class_id, school_id, tenant_id) SELECT 'FOREIGN-1','Far','Away',777,7,tenant_id FROM students LIMIT 1")
fid = one("SELECT id FROM students WHERE admission_no='FOREIGN-1'")
check("another school's records are never listed", "Away" not in html(ADMIN.get("/admin/data-completion")))
post(ADMIN, "/admin/data-completion/save", {"kind": "student", "id": fid, "date_of_birth": "2010-01-01", "gender": "F"}, "/admin/data-completion")
check("...and cannot be edited through this page (multi-tenant isolation)", one("SELECT COALESCE(date_of_birth,'') FROM students WHERE id=?", fid) == "")
check("a teacher cannot open the data-completion page", FT.get("/admin/data-completion").status_code in (302, 403))

print("=== 6) per-user theme + text size ===")
H = lambda c: {"X-CSRF-Token": csrf(c)}
check("signed-out: preferences API refuses (401)", anon.get("/api/preferences").status_code == 401)
check("default preference is light-agnostic, 100%", ADMIN.get("/api/preferences").get_json()["font_scale"] == 100)
r = ADMIN.post("/api/preferences", json={"theme": "dark", "font_scale": 130}, headers=H(ADMIN))
check("saving dark + 130% works", r.status_code == 200 and r.get_json()["font_scale"] == 130)
fresh = login("admin"); d = html(fresh.get("/dashboard"))
check("a brand-new session of the same person gets dark mode from the SERVER (no flash)", 'data-bs-theme="dark"' in d and 'data-server-theme="dark"' in d)
check("...and the saved text size", 'data-font-scale="130"' in d)
check("another person is unaffected", 'data-font-scale="100"' in html(FT.get("/dashboard")) and 'data-server-theme=""' in html(FT.get("/dashboard")))
check("invalid text size is refused", ADMIN.post("/api/preferences", json={"font_scale": 400}, headers=H(ADMIN)).status_code == 400)
check("invalid theme is refused", ADMIN.post("/api/preferences", json={"theme": "neon"}, headers=H(ADMIN)).status_code == 400)
check("no CSRF header -> refused", ADMIN.post("/api/preferences", json={"font_scale": 115}).status_code == 403)
check("text-size controls are in the header", d.count("data-fs-step") >= 3)
ADMIN.post("/api/preferences", json={"theme": "light", "font_scale": 100}, headers=H(ADMIN))

print("=== 7) typography + dark palette ===")
import glob
leftovers = []
for f in glob.glob("static/css/*.css") + glob.glob("templates/*.html") + glob.glob("templates/partials/*.html"):
    b = os.path.basename(f)
    if b == "result-sheet.css" or re.match(r"(_result_sheet|_cumulative|_print|.*_print\.html|.*pdf.*|email_.*)", b): continue
    leftovers += re.findall(r"font-size\s*:\s*\d+(?:\.\d+)?px(?!\s*!important)", open(f, encoding="utf-8").read())   # (the print rule pins 16px on purpose)
check("all app text sizes are in rem, so one control scales everything", not leftovers, leftovers[:3])
css = open("static/css/theme.css").read()
check("desktop default text is larger than mobile", "--fs-root:17px" in css and "--fs-root:18px" in css and "--fs-root:16px" in css)
check("five text-size steps 90-150%", all(f'data-font-scale="{n}"' in css for n in (90, 100, 115, 130, 150)))
check("print is always 16px-based regardless of the chosen size", "@media print{html{font-size:16px!important" in css)
for name, val in (("background", "#0B1120"), ("sidebar", "#111827"), ("cards", "#182235"), ("inputs", "#202D40"), ("text", "#F1F5F9"), ("muted text", "#B0BDCE"), ("borders", "#334155"),
                  ("accent", "#38BDF8"), ("success", "#34D399"), ("warning", "#FBBF24"), ("error", "#F87171")):
    check(f"dark palette: {name} {val}", val.lower() in css.lower())
def lum(h):
    h = h.lstrip("#"); r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)); f = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)
def ratio(a, b): la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + .05) / (lb + .05)
for fg, bg, label in (("#F1F5F9", "#0B1120", "text on background"), ("#F1F5F9", "#182235", "text on cards"), ("#F1F5F9", "#202D40", "text on inputs"), ("#B0BDCE", "#182235", "secondary text on cards"),
                      ("#B0BDCE", "#0B1120", "secondary text on background"), ("#38BDF8", "#182235", "accent on cards"), ("#34D399", "#182235", "success on cards"), ("#FBBF24", "#182235", "warning on cards"), ("#F87171", "#182235", "error on cards")):
    check(f"WCAG AA contrast >= 4.5: {label} ({ratio(fg, bg):.1f}:1)", ratio(fg, bg) >= 4.5, ratio(fg, bg))
check("sidebar width follows the text size (rem) so labels are never crushed", "--sidebar-w:min(15.5rem,30vw)" in css)

print("=== 8) passport photographs ===")
from PIL import Image, ImageDraw
import passport_fit as P
def make(w, h, mode="RGB", fmt="PNG"):
    m = "RGBA" if mode == "RGBA" else "RGB"
    im = Image.new(m, (w, h), (200, 210, 230) if m == "RGB" else (0, 0, 0, 0)); d = ImageDraw.Draw(im); r = min(w, h) // 4
    d.ellipse((w // 2 - r, int(h * .3) - r, w // 2 + r, int(h * .3) + r), fill=(220, 60, 60, 255) if m == "RGBA" else (220, 60, 60)); b = io.BytesIO(); im.save(b, fmt); return b.getvalue()
def circle(jpg):
    im = Image.open(io.BytesIO(jpg)).convert("RGB"); px = im.load(); pts = [(x, y) for y in range(0, im.height, 3) for x in range(0, im.width, 3) if px[x, y][0] > 170 and px[x, y][1] < 110]
    return pts and ((max(p[0] for p in pts) - min(p[0] for p in pts)) / max(1, (max(p[1] for p in pts) - min(p[1] for p in pts))))
for label, data in (("landscape", make(1600, 900)), ("near 4:5", make(900, 1200)), ("very tall", make(400, 1200)), ("square", make(800, 800)), ("transparent PNG", make(700, 900, "RGBA")), ("GIF", make(500, 625, "P", "GIF"))):
    out = P.fit_passport(data); im = Image.open(io.BytesIO(out)); ar = circle(out)
    check(f"{label}: exactly {P.PASSPORT_W}x{P.PASSPORT_H} JPEG", im.size == (P.PASSPORT_W, P.PASSPORT_H) and im.format == "JPEG")
    check(f"{label}: not stretched and the face region is kept", ar and 0.94 <= ar <= 1.06, ar)
big = make(1600, 900)
sidu = one("SELECT id FROM students WHERE admission_no='V107-1'")
r = ADMIN.post(f"/students/{sidu}/photo/upload", data={"csrf_token": tok(ADMIN, f"/students/{sidu}/profile"), "photo": (io.BytesIO(big), "wide.png")}, content_type="multipart/form-data", follow_redirects=True)
fn = one("SELECT photo_filename FROM students WHERE id=?", sidu)
path = os.path.join(A.STUDENT_PHOTOS_DIR, fn) if fn else ""
check("a student upload is stored normalised (4:5 JPEG)", fn and fn.endswith(".jpg") and os.path.exists(path) and Image.open(path).size == (600, 750), (fn, flashes(r)))
check("...and served to the profile page", ADMIN.get(f"/students/{sidu}/photo").status_code == 200)
check("passport frame CSS: 4:5 frame, photo never stretched", "aspect-ratio:4/5" in css and ".passport-img" in css and "object-fit:contain" in css)
check("upload preview component is loaded", "passport-preview.js" in html(ADMIN.get("/dashboard")))

print("=== 9) shared dashboard welcome header ===")
import zoneinfo
def wh(c, url):
    m = re.search(r'<section class="(?:wh-banner|ad-banner)"[^>]*data-config=\'([^\']*)\'.*?<h1>(.*?)</h1><p>(.*?)</p>', html(c.get(url)), re.S)
    return (m.group(2), m.group(3), json.loads(m.group(1).replace("&#34;", '"'))) if m else None
w = wh(FT, "/dashboard")
check("Teacher: personalised v106 welcome ('Welcome, <name>!') + the teaching-overview description", w and w[0].startswith("Welcome, ") and w[0].endswith("!") and "your teaching overview." in w[1], w and w[:2])
check("the header carries the school timezone and a server clock anchor", w and w[2]["tz"] == "Africa/Lagos" and abs(w[2]["utc_ms"] - __import__("time").time() * 1000) < 60000)
check("12-hour time with AM/PM in the server render", w and re.fullmatch(r"\d{1,2}:\d{2} (AM|PM)", w[2]["time"]))
check("full day, date, month and year", w and re.fullmatch(r"\w+day, \d{1,2} \w+ \d{4}", w[2]["date"]), w and w[2]["date"])
w = wh(ADMIN, "/registrar")
check("Registrar: 'Welcome, Registrar!'", w and w[0] == "Welcome, Registrar!" and "admissions and registration" in w[1])
run("UPDATE schools SET timezone='Asia/Tokyo' WHERE id=1")
w = wh(FT, "/dashboard")
check("the clock follows the SCHOOL's timezone (Tokyo), not the server's", w and w[2]["tz"] == "Asia/Tokyo" and w[2]["time"] == datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo")).strftime("%I:%M %p").lstrip("0") or (w and w[2]["tz"] == "Asia/Tokyo"))
run("UPDATE schools SET timezone='Africa/Lagos' WHERE id=1")
from app import welcome_header_data
with A.app.test_request_context():
    from flask import session as _s
    _s["school_id"] = 1
    check("Super Admin copy", welcome_header_data("platform")["heading"] == "Welcome, Super Administrator!" and "all registered schools" in welcome_header_data("platform")["description"])
    check("Student / Parent / other staff use the person's name", welcome_header_data("student", "Ada Obi")["heading"] == "Welcome, Ada Obi!" and welcome_header_data("parent", "Mr Obi")["heading"] == "Welcome, Mr Obi!" and welcome_header_data("staff", "Sam")["description"] == "Here is an overview of your assigned duties and activities.")
    check("Accountant copy", welcome_header_data("accountant")["description"] == "Here is an overview of school fees, payments and financial activities.")
    check("a name cannot inject markup into the header (escaped by Jinja)", "<script>" not in html(FT.get("/dashboard")).replace("<script>(function", "").split('data-welcome-header')[1][:400])
check("one reusable React component file drives every header", os.path.exists("static/js/react-ui/welcome-header.js") and "DashboardWelcomeHeader" in open("static/js/react-ui/welcome-header.js").read())
check("welcome header is branded (uses the school's colours) and works in dark mode", "--theme-secondary" in open("static/css/welcome-header.css").read())

print("=== 10) Theme & Branding backgrounds ===")
import branding_backgrounds as B, random, subprocess
check("standard look builds nothing", B.build("default") is None)
check("every preset: text contrast >= 4.5:1 in light AND dark", all(B.worst_contrast("preset", k) >= 4.5 for k in B.PRESETS), min(B.worst_contrast("preset", k) for k in B.PRESETS))
random.seed(5); worst = 99
for _ in range(1500):
    rc = lambda: "#%06x" % random.randrange(1 << 24)
    for m in ("solid", "gradient"): worst = min(worst, B.worst_contrast(m, c1=rc(), c2=rc()))
check("3000 random custom backgrounds: text contrast never below 4.5:1 (a scrim is added automatically)", worst >= 4.5, worst)
check("garbage colours / modes / angles fall back safely (no CSS injection)", B.clean("evil", "x", "red;}body{display:none", "url(javascript:1)", "abc") == ("default", "sky", "#e6f0ff", "#ffffff", 160) and "javascript" not in str(B.build("gradient", c1="url(javascript:1)", c2="#fff;}")))
# the browser preview is a port of the server builder: identical output on random inputs
js = f"""
global.window = {{}}; global.document = {{ getElementById: () => null }};
const src = require('fs').readFileSync('static/js/react-ui/theme-bg-preview.js','utf8'); eval(src);
const P = JSON.parse(process.argv[1]); window.SchoolHubBg.setPresets(P);
const cases = JSON.parse(process.argv[2]); console.log(JSON.stringify(cases.map(c => window.SchoolHubBg.build(c[0],c[1],c[2],c[3],c[4]))));
"""
random.seed(9); cases = []
for _ in range(600):
    rc = lambda: "#%06x" % random.randrange(1 << 24)
    cases.append([random.choice(["default", "preset", "solid", "gradient", "weird"]), random.choice(list(B.PRESETS) + ["nope"]), rc(), rc(), random.choice([0, 45, 135, 160, 360, 999, "x"])])
presets_js = {k: [v[0], v[1], v[2], v[3], v[4], v[5]] for k, v in B.PRESETS.items()}
try:
    out = subprocess.run(["node", "-e", js, json.dumps(presets_js), json.dumps(cases)], capture_output=True, text=True, timeout=60)
    got = json.loads(out.stdout); want = [B.build(*c) for c in cases]
    check("live-preview JavaScript == server builder on 600 random inputs", got == want, (out.stderr[:200], sum(1 for g, w in zip(got, want) if g != w)))
except Exception as e:
    check("live-preview JavaScript == server builder", False, repr(e)[:200])
row = lambda: one("SELECT bg_mode||'|'||bg_preset||'|'||bg_apply_auth FROM schools WHERE id=1")
check("new schools keep the standard look, sign-in switch OFF", row() == "default|sky|0")
base_form = {"theme_preset": "default", "dashboard_primary_color": "#1f6feb", "dashboard_secondary_color": "#0b3b75", "dashboard_accent_color": "#7c4dff", "dashboard_sidebar_style": "dark", "dashboard_header_style": "solid",
             "auth_branding_enabled": "1", "auth_logo_opacity": "0.1", "auth_logo_position": "center", "auth_background_style": "watermark", "auth_show_school_name": "1"}
post(ADMIN, "/admin/theme", {**base_form, "bg_mode": "preset", "bg_preset": "ocean", "bg_apply_auth": "1"}, "/admin/theme")
check("saving a preset + the sign-in switch stores them", row() == "preset|ocean|1", row())
d = html(ADMIN.get("/dashboard"))
check("dashboards get the custom background (light + dark values, readable text colours)", "data-custom-bg" in d and "--custom-bg-light:" in d and "--custom-bg-dark:" in d and "--custom-ink-light:" in d)
code = one("SELECT school_code FROM schools WHERE id=1")
check("switch ON: the sign-in page of THAT school uses the background", "data-auth-bg" in html(anon.get("/login?school_code=" + code)) and "data-auth-bg" in html(anon.get("/register?school_code=" + code)))
check("...an unidentified visitor still sees the standard page (no cross-school leak)", "data-auth-bg" not in html(anon.get("/login")))
post(ADMIN, "/admin/theme", {**base_form, "bg_mode": "preset", "bg_preset": "ocean"}, "/admin/theme")
check("switch OFF: sign-in keeps the standard background, dashboards keep the custom one", "data-auth-bg" not in html(anon.get("/login?school_code=" + code)) and "data-custom-bg" in html(ADMIN.get("/dashboard")))
post(ADMIN, "/admin/theme", {**base_form, "bg_mode": "gradient", "bg_color1": "#ff0000", "bg_color2": "#0000ff", "bg_angle": "45"}, "/admin/theme")
check("custom gradient is stored and rendered", row().startswith("gradient|") and "linear-gradient(" in html(ADMIN.get("/dashboard")).split("--custom-bg-light:")[1][:200])
post(ADMIN, "/admin/theme", {**base_form, "bg_mode": "solid", "bg_color1": "x;}body{display:none"}, "/admin/theme")
check("a malicious colour value is rejected, never reaches the page", "display:none" not in html(ADMIN.get("/dashboard")).split("</style>")[0])
post(ADMIN, "/admin/theme/reset", {}, "/admin/theme")
check("Reset to default theme restores colours, standard background and switch OFF", row() == "default|sky|0" and one("SELECT dashboard_primary_color FROM schools WHERE id=1") == "#1f6feb")
check("a teacher cannot change or reset the theme", FT.post("/admin/theme/reset", data={"csrf_token": csrf(FT)}).status_code in (302, 403))
pg = html(ADMIN.get("/admin/theme"))
check("Theme page: backgrounds card, presets, custom colour/gradient, auth switch, live preview, reset", all(x in pg for x in ('id="bgCard"', 'name="bg_preset"', 'name="bg_color1"', 'name="bg_apply_auth"', 'id="bgPreview"', "Reset to default theme", "Apply Custom Background to Authentication Pages")))

print("=== 11) shared notification banner on every dashboard ===")
pwh = generate_password_hash("Pass1234")
run("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role, rbac_role, is_active) SELECT school_id, tenant_id, 'Acc Ountant', 'acct107', ?, 'teacher', 'Bursar / Accountant', 1 FROM users WHERE username='admin'", pwh)
run("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role, rbac_role, is_active) SELECT school_id, tenant_id, 'Reg Istrar', 'regi107', ?, 'teacher', 'Registrar / Admissions Officer', 1 FROM users WHERE username='admin'", pwh)
run("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role, rbac_role, is_active) SELECT school_id, tenant_id, 'Guide Counsel', 'guid107', ?, 'teacher', 'Guidance/Counselling Officer', 1 FROM users WHERE username='admin'", pwh)
ACC, REG, GUID = login("acct107"), login("regi107"), login("guid107")
exp = (datetime.datetime.utcnow() + datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
for aud in ("all", "admin", "teacher", "accountant", "registrar", "staff", "student", "parent", "platform"):
    run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,created_by_label) VALUES (1,?,?,?,?,1,?,'t')", f"BN-{aud}", "m", aud, "info", exp)
def seen(c, url):
    d = html(c.get(url)); return {m for m in re.findall(r"BN-(\w+)", d)}
check("School Admin sees: everyone + admin", seen(ADMIN, "/dashboard") >= {"all", "admin"} and not (seen(ADMIN, "/dashboard") & {"teacher", "accountant", "registrar", "student", "parent", "platform"}), seen(ADMIN, "/dashboard"))
check("Teacher sees: everyone + teacher only", seen(FT, "/dashboard") == {"all", "teacher"}, seen(FT, "/dashboard"))
check("Accountant (not a teacher) sees: everyone + accountant only", seen(ACC, "/dashboard") == {"all", "accountant"}, seen(ACC, "/dashboard"))
check("Registrar sees: everyone + registrar only", seen(REG, "/dashboard") == {"all", "registrar"} and seen(REG, "/registrar") == {"all", "registrar"}, (seen(REG, "/dashboard"), seen(REG, "/registrar")))
check("Other staff sees: everyone + other staff only", seen(GUID, "/dashboard") == {"all", "staff"}, seen(GUID, "/dashboard"))
ST = A.app.test_client()
with ST.session_transaction() as s:
    s.update({"student_id": 1, "role": "student", "school_id": 1, "tenant_id": one("SELECT tenant_id FROM schools WHERE id=1"), "login_time": datetime.datetime.utcnow().isoformat(timespec="seconds")})
check("Student sees: everyone + students only", seen(ST, "/student/dashboard") == {"all", "student"}, seen(ST, "/student/dashboard"))
run("INSERT INTO parent_accounts (school_id, tenant_id, name, username, password_hash, is_active, account_status, signup_status) SELECT id, tenant_id, 'Par Ent', 'par107', ?, 1, 'active', 'approved' FROM schools WHERE id=1", pwh)
PID = one("SELECT id FROM parent_accounts WHERE username='par107'")
PR = A.app.test_client()
with PR.session_transaction() as s:
    s.update({"parent_id": PID, "role": "parent", "school_id": 1, "name": "Par Ent", "tenant_id": one("SELECT tenant_id FROM schools WHERE id=1"), "login_time": datetime.datetime.utcnow().isoformat(timespec="seconds"), "account_status": "active"})
check("Parent sees: everyone + parents only", seen(PR, "/parent/dashboard") == {"all", "parent"}, seen(PR, "/parent/dashboard"))
run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,created_by_label) VALUES (NULL,'BN-platformwide','m','platform','info',1,?,'Platform Admin: Root')", exp)
PA = A.app.test_client()
with PA.session_transaction() as s: s["platform_admin_id"] = 1; s["platform_admin_name"] = "Root"
check("Super Admin sees the platform-level banner (and no school's banners)", seen(PA, "/platform/dashboard") == {"platformwide"}, seen(PA, "/platform/dashboard"))
check("a school-level 'platform' announcement never reaches a Super Admin dashboard or any school user", "platformwide" not in seen(ADMIN, "/dashboard") and "platform" not in seen(PA, "/platform/dashboard"))
r = post(ADMIN, "/admin/announcements", {"title": "Sneaky", "message": "m", "audience": "platform", "level": "info", "expires_at": (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")}, "/admin/announcements")
check("a School Admin cannot address Super Administrators (coerced to everyone in their own school)", one("SELECT audience FROM announcements WHERE title='Sneaky'") == "all")
check("the school form does not even offer the Super Administrator audience", 'value="platform"' not in html(ADMIN.get("/admin/announcements")))
check("...the platform form does", 'value="platform"' in html(PA.get("/platform/announcements")))
# isolation + priority + duration
run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,created_by_label) VALUES (7,'BN-otherschool','m','all','info',1,?,'t')", exp)
check("another school's banner is never shown (tenant isolation)", "otherschool" not in seen(FT, "/dashboard") | seen(ADMIN, "/dashboard") | seen(ST, "/student/dashboard"))
run("DELETE FROM announcements WHERE title LIKE 'BN-%'")
for lvl in ("info", "warning", "danger", "success"):
    run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,display_seconds,created_by_label) VALUES (1,?,?,?,?,1,?,?,'t')", f"BN-{lvl}", "m", "teacher", lvl, exp, 30 if lvl == "danger" else 0)
order = re.findall(r"BN-(\w+)", html(FT.get("/dashboard"))); order = [o for i, o in enumerate(order) if o not in order[:i]]
check("priorities are ordered Urgent, Important, Good news, Information", order == ["danger", "warning", "success", "info"], order)
d = html(FT.get("/dashboard"))
check("Urgent banners are announced assertively (role=alert) and carry their auto-hide seconds", 'role="alert"' in d and 'data-ann-seconds="30"' in d and "Urgent</span>" in d)
rr = post(ADMIN, "/admin/announcements", {"title": "Timed", "message": "m", "audience": "teacher", "level": "info", "display_seconds": "45", "expires_at": (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")}, "/admin/announcements")
check("administrators can configure the display duration", one("SELECT display_seconds FROM announcements WHERE title='Timed'") == 45)
post(ADMIN, "/admin/announcements", {"title": "Silly", "message": "m", "audience": "teacher", "level": "info", "display_seconds": "999999", "expires_at": (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")}, "/admin/announcements")
check("...within sensible limits (max 600 s)", one("SELECT display_seconds FROM announcements WHERE title='Silly'") == 600)
did = one("SELECT id FROM announcements WHERE title='BN-info'")
FT.post(f"/announcements/{did}/dismiss", data={"csrf_token": csrf(FT)})
check("a person can dismiss a banner and it stays dismissed for them only", "info" not in seen(FT, "/dashboard") and "BN-info" not in html(ACC.get("/dashboard")))
check("the ONE shared banner partial is included by the base layout, so every dashboard shows it", '_announcement_banners.html' in open("templates/base.html").read())
check("...and no dashboard template adds a second copy", not any("_announcement_banners.html" in open(f"templates/{n}").read() for n in ("teacher_dashboard.html", "student_dashboard.html", "parent_dashboard.html", "platform_dashboard.html", "registrar_dashboard.html")))
run("INSERT INTO announcements(school_id,title,message,audience,level,dismissible,expires_at,created_by_label) VALUES (1,'BN-once','m','all','info',1,?,'t')", exp)
check("each banner is rendered exactly once on every dashboard", all(html(c).count("BN-once") == 1 for c in (ADMIN.get("/dashboard"), FT.get("/dashboard"), ACC.get("/dashboard"), REG.get("/registrar"), ST.get("/student/dashboard"), PR.get("/parent/dashboard"))))

print("=== 12) role-based dashboard charts (real records only) ===")
import role_charts as RC
cx = get_db()
sids = [r[0] for r in cx.execute("SELECT id FROM students WHERE school_id=1 AND admission_no NOT LIKE 'V107-%' AND admission_no NOT LIKE 'OLD-%' ORDER BY id")][:3]
today = datetime.date.today()
mo = lambda back: (today.replace(day=1) - datetime.timedelta(days=30 * back)).strftime("%Y-%m")
for sid_, back in zip(sids, (1, 1, 3)): cx.execute("UPDATE students SET date_of_admission=? WHERE id=?", (mo(back) + "-10", sid_))
cx.execute("DELETE FROM student_status_history")
for sid_, st, back in ((sids[0], "Transferred", 1), (sids[1], "Withdrawn", 1), (sids[2], "Transferred", 2)):
    cx.execute("INSERT INTO student_status_history(school_id,tenant_id,student_id,previous_status,new_status,effective_date,changed_by_name,changed_by_role) SELECT school_id,tenant_id,?,'Active',?,?,'t','admin' FROM students WHERE id=?", (sid_, st, mo(back) + "-15", sid_))
cx.commit()
cx.row_factory = __import__("sqlite3").Row
sp = {s["id"]: s for s in RC.registrar_specs(cx, 1)}
lab = lambda back: RC._label(mo(back))
adm = dict(zip(sp["rcAdmissions"]["labels"], sp["rcAdmissions"]["datasets"][0]["data"]))
check("registrar: admissions per month are the real admission dates (2 last month, 1 three months ago)", adm[lab(1)] == 2 and adm[lab(3)] == 1 and sum(adm.values()) >= 3, adm)
mv = {d["label"]: dict(zip(sp["rcMovements"]["labels"], d["data"])) for d in sp["rcMovements"]["datasets"]}
check("registrar: transfers and withdrawals come from the status history", mv["Transferred"][lab(1)] == 1 and mv["Transferred"][lab(2)] == 1 and mv["Withdrawn"][lab(1)] == 1, mv)
cx.execute("UPDATE students SET date_of_admission=NULL WHERE id=?", (sids[2],)); cx.commit()
sp2 = {s["id"]: s for s in RC.registrar_specs(cx, 1)}
check("registrar: students with no admission date are COUNTED in a note, never invented into a month", "no admission date recorded" in sp2["rcAdmissions"]["subtitle"] and sum(sp2["rcAdmissions"]["datasets"][0]["data"]) == sum(adm.values()) - 1)
check("registrar: enrolment by class equals the real active head-count", dict(zip(sp["rcEnrolment"]["labels"], sp["rcEnrolment"]["datasets"][0]["data"])).get("JSS1A") == one("SELECT COUNT(*) FROM students WHERE class_id=? AND is_active=1", CLASS1))
check("registrar: a school with no students/history shows empty states, not fake numbers", all(s["empty"] for s in RC.registrar_specs(cx, 7) if s["id"] != "rcEnrolment") and RC.registrar_specs(cx, 7)[0]["empty"])
check("registrar: another school's students never appear (tenant isolation)", "ZED" not in sp["rcEnrolment"]["labels"])
run("INSERT INTO schools (id, name, is_suspended, activation_status, created_at) VALUES (8, 'Gone School', 1, 'active', ?)", mo(2) + "-05 10:00:00")
run("INSERT INTO schools (id, name, is_suspended, activation_status, created_at) VALUES (9, 'Pending School', 0, 'pending', ?)", mo(0) + "-01 10:00:00")
ps = {s["id"]: s for s in RC.platform_specs(cx)}
st = dict(zip(ps["rcSchoolStatus"]["labels"], ps["rcSchoolStatus"]["datasets"][0]["data"]))
check("super admin: schools by status = real counts (active / suspended / inactive)", st["Suspended"] == 1 and st["Inactive"] >= 1 and st["Active"] >= 1 and sum(st.values()) == one("SELECT COUNT(*) FROM schools"), st)
check("super admin: registration trend counts schools in their registration month", dict(zip(ps["rcRegistrations"]["labels"], ps["rcRegistrations"]["datasets"][0]["data"]))[lab(2)] >= 1)
g = ps["rcGrowth"]["datasets"][0]["data"]
check("super admin: growth is cumulative and never decreases, ending at the total number of schools", all(a <= b for a, b in zip(g, g[1:])) and g[-1] == one("SELECT COUNT(*) FROM schools"), g)
check("super admin: enrolment per school is each school's own active head-count", dict(zip(ps["rcEnrolmentSchools"]["labels"], ps["rcEnrolmentSchools"]["datasets"][0]["data"])).get("My School", dict(zip(ps["rcEnrolmentSchools"]["labels"], ps["rcEnrolmentSchools"]["datasets"][0]["data"])).get(one("SELECT name FROM schools WHERE id=1"))) == one("SELECT COUNT(*) FROM students WHERE school_id=1 AND is_active=1 AND COALESCE(is_deleted,0)=0"))
from app import class_term_result_stats, compute_total, current_term
with A.app.test_request_context():
    from flask import session as _s
    _s["school_id"] = 1
    term = current_term(cx)
    tspecs = {s["id"]: s for s in RC.teaching_specs(cx, 1, term, [CLASS1], class_term_result_stats, compute_total)}
rows = cx.execute("SELECT sub.name n, sc.ca1, sc.ca2, sc.ca3, sc.exam FROM scores sc JOIN students st ON st.id=sc.student_id AND st.is_active=1 JOIN subjects sub ON sub.id=sc.subject_id WHERE sc.term_id=? AND st.class_id=?", (term["id"], CLASS1)).fetchall()
manual = {}
for r in rows: manual.setdefault(r["n"], []).append(compute_total(r["ca1"], r["ca2"], r["exam"], r["ca3"]))
want = {k: round(sum(v) / len(v), 1) for k, v in manual.items()}
check("teacher: subject performance equals an independent calculation from the scores table", dict(zip(tspecs["rcSubjects"]["labels"], tspecs["rcSubjects"]["datasets"][0]["data"])) == want, (want, tspecs["rcSubjects"]["datasets"]))
pf = tspecs["rcPassFail"]["datasets"][0]["data"]
check("teacher: pass / fail / not-assessed add up to the class head-count", sum(pf) == one("SELECT COUNT(*) FROM students WHERE class_id=? AND is_active=1", CLASS1), pf)
check("no term or no classes -> an explanatory empty state, not zeros", all(s["empty"] for s in RC.teaching_specs(cx, 1, None, [CLASS1], class_term_result_stats, compute_total)) and all(s["empty"] for s in RC.teaching_specs(cx, 1, term, [], class_term_result_stats, compute_total)))
cx.close()
pg_t, pg_a, pg_r = html(FT.get("/dashboard")), html(ADMIN.get("/admin/analytics")), html(ADMIN.get("/registrar"))
check("Teacher dashboard shows subject performance + pass/fail charts", "rcSubjects" in pg_t and "rcPassFail" in pg_t and "role-charts.js" in pg_t)
check("School Analytics shows them too", "rcSubjects" in pg_a and "rcPassFail" in pg_a)
check("Registrar dashboard shows admissions, movements and enrolment charts", all(x in pg_r for x in ("rcAdmissions", "rcMovements", "rcEnrolment")) and "chart.umd" in pg_r)
pg_p = html(PA.get("/platform/dashboard"))
check("Super Admin dashboard shows school status, registration trend, growth and enrolment charts", all(x in pg_p for x in ("rcSchoolStatus", "rcRegistrations", "rcGrowth", "rcEnrolmentSchools")))
check("a school admin's pages never contain platform-wide figures", "rcSchoolStatus" not in pg_a and "Gone School" not in pg_a and "Gone School" not in pg_t)
check("every chart has an accessible name and a 'view as table' text alternative", pg_r.count('aria-label="New admissions"') == 1 and "View as table" in pg_r)
j = FT.get("/api/dashboard/analytics?class_id=%d" % CLASS1).get_json()
check("the dashboard filter API returns refreshed role charts for the chosen class", [s["id"] for s in j["role_charts"]] == ["rcSubjects", "rcPassFail"] and sum(j["role_charts"][1]["datasets"][0]["data"]) == one("SELECT COUNT(*) FROM students WHERE class_id=? AND is_active=1", CLASS1), j.get("role_charts"))
check("...and refuses a class outside the user's scope", FT.get("/api/dashboard/analytics?class_id=777").status_code == 403)
js = open("static/js/role-charts.js").read()
check("charts follow light/dark and the text size, redraw in place, with integer axes", "sh-theme-change" in js and "sh-font-change" in js and "precision: 0" in js and "update:" in js)
check("fees charts are NOT faked: no fee ledger exists, so none of the Accountant charts are drawn", not any(("payment" in s["id"].lower() or "fee" in s["id"].lower()) for fn in (lambda: RC.registrar_specs(get_db(), 1), lambda: RC.platform_specs(get_db())) for s in fn()))

print("=== 13) parent + student charts ===")
PTERM = one("SELECT id FROM terms WHERE is_active=1")
run("INSERT OR IGNORE INTO scores (student_id, subject_id, term_id, ca1, ca2, exam, tenant_id) SELECT 1, 1, ?, 15, 18, 55, tenant_id FROM students WHERE id=1", PTERM)
run("INSERT OR IGNORE INTO scores (student_id, subject_id, term_id, ca1, ca2, exam, tenant_id) SELECT 1, 2, ?, 10, 12, 40, tenant_id FROM students WHERE id=1", PTERM)
__import__("wf_helper").publish(A, PTERM)
run("INSERT INTO parent_students (parent_id, student_id, school_id, tenant_id, status) SELECT ?, 1, school_id, tenant_id, 'verified' FROM students WHERE id=1", PID)
pd = html(PR.get("/parent/dashboard")); sd = html(ST.get("/student/dashboard"))
def _arr(d, key):
    m = re.search(key + r":\s*(\[[^\]]*\])", d); return json.loads(m.group(1)) if m else None
check("Student dashboard has academic trend and subject-score charts", all(x in sd for x in ('id="chartAcademicTrend"', 'id="chartSubjectScores"')))
check("Parent dashboard has trend and subject-performance charts", all(x in pd for x in ('id="chartAcademicTrend"', 'id="chartSubjectScores"')))
real = lambda d: [v for v in (_arr(d, "subjectScores") or []) if v is not None]
check("...showing the SAME real figures the child sees (88 and 62); subjects with no score are gaps (null), never zeros", _arr(pd, "subjectScores") == _arr(sd, "subjectScores") and sorted(real(pd)) == [62, 88] and None in _arr(pd, "subjectScores"), (_arr(pd, "subjectScores"), _arr(sd, "subjectScores")))
check("no attendance recorded -> no attendance chart is drawn (nothing invented)", 'id="chartAttendance"' not in pd and 'id="chartAttendance"' not in sd)
run("INSERT INTO attendance_records (student_id, class_id, term_id, date, status) SELECT 1, class_id, ?, date('now'), 'present' FROM students WHERE id=1", PTERM)
check("once attendance is recorded, both dashboards chart it", 'id="chartAttendance"' in html(PR.get("/parent/dashboard")) and 'id="chartAttendance"' in html(ST.get("/student/dashboard")))

print(f"\n{PASS} passed, {len(FAIL)} failed"); sys.exit(1 if FAIL else 0)
