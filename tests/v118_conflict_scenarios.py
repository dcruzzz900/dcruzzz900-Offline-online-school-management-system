"""V118: a score nobody else changed is never a conflict. Run: python tests/v118_conflict_scenarios.py"""
import os, sys, tempfile, uuid, runpy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v118_"); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests")); os.chdir(ROOT)
import app as A, logging, datetime, re
from db import get_db
from werkzeug.security import generate_password_hash
logging.disable(logging.CRITICAL); A.app.config["TESTING"] = False
bad = []
def check(n, c):
    print(("ok   " if c else "FAIL ") + n)
    if not c: bad.append(n)
c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.execute("DELETE FROM result_publication"); c0.commit(); c0.close()
def tok(c):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").get_data(as_text=True)); return m.group(1)
A._rate_limit_store.clear(); FT = A.app.test_client(); FT.post("/login", data={"username": "aokafor", "password": "Pass1234", "csrf_token": tok(FT)}, follow_redirects=True)
def csrf():
    FT.get("/dashboard")
    with FT.session_transaction() as s: return s.get("_csrf_token")
def replay(body, base, dev="dev-A"):
    return FT.post("/api/scores/1/1/row", json=body, headers={"X-Change-Id": str(uuid.uuid4()), "X-Offline-Replay": "1", "X-Device-Id": dev, "X-CSRF-Token": csrf(),
        "X-Captured-At": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "X-Base-Version": base})
b = lambda ca1: {"student_id": 1, "ca1": str(ca1), "ca2": "5", "exam": "20"}
c = get_db(); c.execute("DELETE FROM scores WHERE student_id=1 AND subject_id=1"); c.commit(); c.close()
r1 = replay(b(10), ""); check("first score on an empty row: applied, no conflict", r1.status_code == 200 and not r1.json.get("conflict"))
v1 = r1.json.get("updated_at")
r2 = replay(b(12), "")   # the same device's second change was queued before it learned the new version
check("the same device's own second change is NOT a conflict", r2.status_code == 200 and not r2.json.get("conflict"))
r3 = replay(b(14), "stale-version", dev="dev-B")
check("a different device with an old version IS still a conflict", r3.status_code == 409 and r3.json.get("conflict"))
c = get_db(); c.execute("DELETE FROM scores WHERE student_id=2 AND subject_id=1"); 
c.execute("INSERT INTO scores (student_id,subject_id,term_id,ca1,ca2,exam,updated_at) VALUES (2,1,(SELECT id FROM terms WHERE is_active=1),0,0,0,'2026-11-26 10:00:00')"); c.commit(); c.close()
body = dict(b(9)); body["student_id"] = 2
r4 = replay(body, "")
check("a blank row (nothing ever entered) never blocks the first score", r4.status_code == 200 and not r4.json.get("conflict"))
print("\nPASSED" if not bad else "\nFAILED: %s" % bad); sys.exit(1 if bad else 0)
