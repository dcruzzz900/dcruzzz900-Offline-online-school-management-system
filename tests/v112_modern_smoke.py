"""v112 smoke: every parameter-free GET route renders (no 5xx) through the v106 modern shell as admin / teacher / platform.
Run: python tests/v112_modern_smoke.py"""
import logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v112_")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A
from db import get_db
from werkzeug.security import generate_password_hash
A.app.config["TESTING"] = False; logging.disable(logging.CRITICAL)
c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.commit()
users = [r[0] for r in c0.execute("SELECT username||'|'||role FROM users")]; c0.close()
print("users:", users[:6])
def tok(c, page):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get(page).get_data(as_text=True))
    return m.group(1) if m else ""
def login(u):
    A._rate_limit_store.clear(); c = A.app.test_client()
    c.post("/login", data={"username": u, "password": "Pass1234", "csrf_token": tok(c, "/login")}, follow_redirects=True); return c
routes = [r.rule for r in A.app.url_map.iter_rules() if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith("/static") and "logout" not in r.rule and "download" not in r.rule and "pdf" not in r.rule and "export" not in r.rule]
bad_total = 0
for who in sorted({u.split("|")[0] for u in users})[:3]:
    c = login(who); ok = shell = bad = 0; fails = []
    for rule in routes:
        r = c.get(rule)
        if r.status_code >= 500: bad += 1; fails.append((rule, r.status_code))
        elif r.status_code == 200:
            ok += 1; t = r.get_data(as_text=True)
            if 'class="sidebar app-sidebar"' in t and 'class="hamburger' in t: shell += 1
    print(f"{who}: routes={len(routes)} 200={ok} modern-shell={shell} 5xx={bad}", fails[:8]); bad_total += bad
sys.exit(1 if bad_total else 0)
