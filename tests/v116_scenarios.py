"""V116 scenarios (no browser): the unified online/offline login page is wired correctly. Browser behaviour: tests/v116_unified_login_e2e.py"""
import logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v116_"); sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, d)
def rd(p): return open(p, encoding="utf8").read()
c = A.app.test_client(); d = c.get("/login").get_data(as_text=True)
print("=== login page ===")
check("one login form posting to the Flask /login with a CSRF token", 'id="unifiedLoginForm"' in d and 'method="POST"' in d and 'name="csrf_token"' in d)
check("connection status area (announced to screen readers)", 'id="loginConn"' in d and 'aria-live="polite"' in d)
check("the unified login script is loaded on the login page", "offline/unified-login.js" in d)
check("login still has username, password, class code and school id fields (roles unchanged)", all(f'name="{n}"' in d for n in ("username", "password", "class_code", "school_code")))
check("the old separate offline sign-in is still only a fallback page", c.get("/offline").status_code == 200)
print("=== service worker ===")
sw = rd("static/service-worker.js")
check("login page is cached anonymously (no cookies sent)", "credentials: 'omit'" in sw and "refreshLoginShell" in sw)
check("login page is served when the server cannot be reached", "loginShell()" in sw and "isLogin" in sw)
check("login is still never cached as a person's page", re.search(r"NEVER_CACHE = /\^\\/\(api\\/\|login", sw) is not None)
check("people's cached pages are named by format, not worker version (update must not wipe them)", "PAGES_VERSION = 'v114'" in sw and "'sh-pages-' + PAGES_VERSION" in sw)
check("sign-out cancels the silent page download", "prepCtl.abort()" in sw and "sig.aborted" in sw)
check("unified-login.js is pre-cached", "/static/js/offline/unified-login.js" in sw)
check("everyone re-prepares once after this upgrade", 'OFFLINE_VERSION = "v117"' in rd("static/js/offline/offline-ui.js"))
print("=== unified-login.js ===")
js = rd("static/js/offline/unified-login.js")
check("never writes the password to persistent storage", "localStorage" not in js and "setItem" not in js)
check("clears the one-page-load password stash after an offline attempt", 'removeItem("sh-login")' in js)
check("refuses offline sign-in when no one is enrolled on the device", "listUsers" in js and "FIRST_TIME" in js and "if (!n)" in js)
check("a Class Login Code (first-time student) is refused offline", "class_code" in js and "needs an internet connection" in js)
check("uses the real device check (core.offlineLogin), not its own password logic", "core.offlineLogin(" in js)
check("detects connectivity from browser events and a server ping", 'addEventListener("online"' in js and "checkConnection" in js and "setInterval" in js)
print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL: print("Failures:", FAIL); sys.exit(1)
