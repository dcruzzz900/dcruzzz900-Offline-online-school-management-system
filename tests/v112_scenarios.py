"""V112 scenarios: School Fees screen (v106 Modern Screens #89), role-menu parity and the v106 shell.
Run: python tests/v112_scenarios.py"""
import logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v112_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A, wf_helper as W
from db import get_db
from werkzeug.security import generate_password_hash
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
c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.commit(); c0.close()
ADMIN = login("admin"); TEACHER = login("aokafor")

print("=== 1) School Fees screen ===")
r = ADMIN.get("/admin/fees"); p = html(r)
check("admin opens School Fees", r.status_code == 200 and "School Fees" in p)
check("shows Expected / Collected / Outstanding / Collection rate", all(x in p for x in ("Expected", "Collected", "Outstanding", "Collection rate")))
check("table 'school_fee_payments' exists", one("SELECT COUNT(*) FROM sqlite_master WHERE name='school_fee_payments'") == 1)
post(ADMIN, "/admin/fees", {"action": "set_expected", "expected_amount": "1,000,000", "label": "2026/2027"}, "/admin/fees")
p = html(ADMIN.get("/admin/fees"))
check("expected amount saved with a label", "1,000,000.00" in p and "2026/2027" in p)
sid = one("SELECT s.id FROM students s JOIN classes c ON c.id=s.class_id WHERE c.school_id=1 ORDER BY s.id LIMIT 1")
post(ADMIN, "/admin/fees", {"action": "record_payment", "student_id": sid, "amount": "250000", "method": "Transfer", "paid_on": "2026-11-16", "note": "1st term"}, "/admin/fees")
p = html(ADMIN.get("/admin/fees"))
check("payment is listed", "250,000.00" in p and "Transfer" in p and "2026-11-16" in p)
check("collected / outstanding / rate update", "250,000.00" in p and "750,000.00" in p and "25%" in p)
dash = html(ADMIN.get("/dashboard"))
check("dashboard fees tile shows the same figures and links to the screen", "₦1,000,000" in dash and "₦250,000" in dash and "/admin/fees" in dash, dash[dash.find("School Fees"):][:300])

print("=== 2) validation ===")
n0 = one("SELECT COUNT(*) FROM school_fee_payments")
for bad in ("", "abc", "-5", "0", "nan", "1e99"):
    post(ADMIN, "/admin/fees", {"action": "record_payment", "student_id": sid, "amount": bad}, "/admin/fees")
check("empty / non-numeric / negative / zero / NaN / absurd amounts are rejected", one("SELECT COUNT(*) FROM school_fee_payments") == n0)
post(ADMIN, "/admin/fees", {"action": "record_payment", "student_id": 99999, "amount": "10"}, "/admin/fees")
check("unknown student is rejected", one("SELECT COUNT(*) FROM school_fee_payments") == n0)
post(ADMIN, "/admin/fees", {"action": "set_expected", "expected_amount": "-1"}, "/admin/fees")
check("negative expected is rejected", abs(one("SELECT expected_amount FROM school_fee_summary WHERE school_id=1 ORDER BY id DESC LIMIT 1") - 1000000) < 0.01)

print("=== 2b) tenant isolation: a second school cannot charge or see school 1's students/payments ===")
post(ADMIN, "/admin/fees", {"action": "record_payment", "student_id": sid, "amount": "1000", "method": "Cash"}, "/admin/fees")
c = get_db(); cur = c.cursor()
cur.execute("INSERT INTO schools (name, tenant_id) VALUES ('Second School', 'school2')"); sch2 = cur.lastrowid
cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (f"SCH{sch2}", f"PUB{sch2}", sch2))
cur.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)", (sch2, "school2", "Second Admin", "admin2", generate_password_hash("Pass1234"), "admin"))
c.commit(); c.close()
ADMIN2 = login("admin2")
p2 = html(ADMIN2.get("/admin/fees"))
check("second school's fees screen shows none of school 1's payments or students", ADMIN2.get("/admin/fees").status_code == 200 and "1,000.00" not in p2 and "1,000,000" not in p2)
n1 = one("SELECT COUNT(*) FROM school_fee_payments WHERE school_id=?", sch2)
post(ADMIN2, "/admin/fees", {"action": "record_payment", "student_id": sid, "amount": "50"}, "/admin/fees")
check("second school cannot record a payment against a school-1 student", one("SELECT COUNT(*) FROM school_fee_payments WHERE school_id=?", sch2) == n1)
pid1 = one("SELECT id FROM school_fee_payments WHERE school_id=1 ORDER BY id DESC LIMIT 1")
post(ADMIN2, "/admin/fees", {"action": "delete_payment", "payment_id": pid1}, "/admin/fees")
check("second school cannot delete a school-1 payment", one("SELECT COUNT(*) FROM school_fee_payments WHERE id=?", pid1) == 1)
post(ADMIN, "/admin/fees", {"action": "delete_payment", "payment_id": pid1}, "/admin/fees")
n0 = one("SELECT COUNT(*) FROM school_fee_payments WHERE school_id=1")

print("=== 3) delete ===")
pid = one("SELECT id FROM school_fee_payments ORDER BY id DESC LIMIT 1")
post(ADMIN, "/admin/fees", {"action": "delete_payment", "payment_id": pid}, "/admin/fees")
check("payment removed and collected total goes back", one("SELECT COUNT(*) FROM school_fee_payments WHERE school_id=1") == n0 - 1 and abs(one("SELECT collected_amount FROM school_fee_summary WHERE school_id=1 ORDER BY id DESC LIMIT 1")) < 0.01)

print("=== 4) access control ===")
r = TEACHER.get("/admin/fees", follow_redirects=False)
check("teacher cannot open School Fees", r.status_code in (302, 303, 403))
anon = A.app.test_client().get("/admin/fees", follow_redirects=False)
check("signed-out visitor is sent to sign in", anon.status_code in (302, 303) and "login" in anon.headers.get("Location", ""))
r = A.app.test_client().post("/admin/fees", data={"action": "set_expected", "expected_amount": "5"}, follow_redirects=False)
check("POST without a session or CSRF token changes nothing", abs(one("SELECT expected_amount FROM school_fee_summary WHERE school_id=1 ORDER BY id DESC LIMIT 1") - 1000000) < 0.01)

print("=== 5) shell + menus (v106) ===")
p = html(ADMIN.get("/dashboard"))
check("modern stylesheet is loaded last", "css/modern-v106.css" in p and p.index("theme-dark.generated.css") < p.index("modern-v106.css"))
for label in ("Sub-Admins", "School Information", "Result Display", "Custom School Info", "Email Settings", "School Fees"):
    check(f"admin menu has {label}", label in p)
p = html(TEACHER.get("/dashboard"))
check("teacher menu has AI Comments and not admin-only entries", "AI Comments" in p and "Sub-Admins" not in p and "Email Settings" not in p and "School Fees" not in p)
print("=== 6) pages rebuilt to the v106 layout keep their data and actions ===")
c = get_db()
c.execute("INSERT INTO notifications(sender_label,school_id,target_role,title,message) VALUES ('Admin',1,'all','Term dates','Resumption is on Monday.')")
c.execute("INSERT INTO announcements(school_id,title,message,audience,level,expires_at,is_active,created_by_label) VALUES (1,'Sports day','Bring your kit.','all','info','2099-01-01 00:00:00',1,'Admin')")
c.commit(); c.close()
p = html(ADMIN.get("/notifications"))
check("notifications inbox lists the message as a v106 row with sender", "notif-row" in p and "Term dates" in p and "Resumption is on Monday." in p and "Compose" in p, p[-600:])
p = html(ADMIN.get("/admin/announcements"))
check("announcements show as cards with status badge and a Remove action", "ann-card" in p and "Sports day" in p and "ann-badge-live" in p and 'value="remove"' in p)
p = html(ADMIN.get("/admin/grading"))
check("grading page keeps weighting + every grade band editable, adds the live preview", "grading-grid" in p and p.count('name="min_score"') >= 6 and "Live preview of scale" in p and "gs-fill" in p and "Save Weighting" in p)
p = html(ADMIN.get("/admin/classes"))
check("classes page shows student and subject counts and keeps category/teacher editing", "Students" in p and "Subjects" in p and 'name="teacher_id"' in p and 'name="category"' in p)
p = html(ADMIN.get("/admin/students"))
check("students page has the search/gender/status filters and every student row", 'id="stuSearch"' in p and 'id="genderFilter"' in p and p.count("data-st=") >= 3)
p = html(ADMIN.get("/admin/teachers"))
check("teachers page keeps contact, role, deactivate, reset and delete controls", all(x in p for x in ('name="email"', 'name="rbac_role"', "Deactivate", "Reset Password", "Delete")))
p = html(ADMIN.get("/admin/subjects"))
check("subjects page shows teacher/class counts", "Assigned Teachers" in p and "Classes" in p)

print(f"\n{PASS} passed, {len(FAIL)} failed"); sys.exit(1 if FAIL else 0)
