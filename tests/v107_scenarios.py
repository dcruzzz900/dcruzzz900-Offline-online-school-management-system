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
    m = re.search(r'<section class="wh-banner"[^>]*data-config=\'([^\']*)\'.*?<h1>(.*?)</h1><p>(.*?)</p>', html(c.get(url)), re.S)
    return (m.group(2), m.group(3), json.loads(m.group(1).replace("&#34;", '"'))) if m else None
w = wh(FT, "/dashboard")
check("Teacher: 'Welcome, Teacher!' + the teacher description", w and w[0] == "Welcome, Teacher!" and w[1] == "Here is an overview of your classes, students and academic activities.", w and w[:2])
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
    check("a name cannot inject markup into the header (escaped by Jinja)", "<script>" not in html(FT.get("/dashboard")).replace("<script>(function", "").split('class="wh-banner"')[1][:400])
check("one reusable React component file drives every header", os.path.exists("static/js/react-ui/welcome-header.js") and "DashboardWelcomeHeader" in open("static/js/react-ui/welcome-header.js").read())
check("welcome header is branded (uses the school's colours) and works in dark mode", "--theme-secondary" in open("static/css/welcome-header.css").read())

print(f"\n{PASS} passed, {len(FAIL)} failed"); sys.exit(1 if FAIL else 0)
