"""V102 scenarios: login limiter is per username (a school behind one IP is not locked out), brute-forcing one account is
still blocked, the IP-wide ceiling exists. Run: python tests/v102_scenarios.py"""
import logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v102_")
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
A.app.config["TESTING"] = False; logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, d)
def tok(c): return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
c0 = get_db(); h = generate_password_hash("Pass1234")
c0.execute("UPDATE users SET password_hash=?", (h,))
users = [r[0] for r in c0.execute("SELECT username FROM users")]
for i in range(30):                       # 30 more people at the same school (same IP)
    c0.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) SELECT school_id, tenant_id, ?, ?, ?, 'teacher' FROM users WHERE username='admin'", (f"T{i}", f"staff{i}", h))
c0.commit(); c0.close()
A._rate_limit_store.clear()
ok = 0
for i in range(30):                       # all from the SAME ip (127.0.0.1)
    c = A.app.test_client(); r = c.post("/login", data={"username": f"staff{i}", "password": "Pass1234", "csrf_token": tok(c)})
    ok += 1 if r.status_code == 302 and "/login" not in r.headers.get("Location", "") else 0
check("30 different people on ONE IP can all log in (used to lock out after 10)", ok == 30, ok)
A._rate_limit_store.clear()
blocked = 0
for i in range(14):                       # brute force ONE account
    c = A.app.test_client(); r = c.post("/login", data={"username": "admin", "password": "wrong", "csrf_token": tok(c)})
    blocked += 1 if "Too many attempts" in c.get("/login").get_data(as_text=True) or r.status_code == 302 and False else 0
c = A.app.test_client(); r = c.post("/login", data={"username": "admin", "password": "Pass1234", "csrf_token": tok(c)}, follow_redirects=True)
check("guessing one account is still blocked after 10 tries (even with the right password)", "Too many attempts" in r.get_data(as_text=True), r.status_code)
c = A.app.test_client(); r = c.post("/login", data={"username": "staff1", "password": "Pass1234", "csrf_token": tok(c)})
check("...and that does not affect a different account on the same IP", r.status_code == 302 and "/login" not in r.headers.get("Location", ""))
A._rate_limit_store.clear()
for i in range(601): A._is_rate_limited("login:127.0.0.1", 600, 300)
c = A.app.test_client(); r = c.post("/login", data={"username": "staff2", "password": "Pass1234", "csrf_token": tok(c)}, follow_redirects=True)
check("the whole-IP ceiling (600 per 5 min) still protects against a flood", "Too many attempts" in r.get_data(as_text=True))
print(f"\n{PASS} passed, {len(FAIL)} failed"); sys.exit(1 if FAIL else 0)
