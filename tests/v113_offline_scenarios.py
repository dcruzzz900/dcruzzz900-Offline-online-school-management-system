"""V113 scenarios: offline-first sync on the server (idempotent replay, conflict detection, administrator resolution,
stale attendance, locked results, isolation, Sync Center, PWA files). Run: python tests/v113_offline_scenarios.py"""
import datetime, json, logging, os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="v113_")
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
def csrf(c):
    c.get("/dashboard")
    with c.session_transaction() as s: return s.get("_csrf_token")
def replay(c, url, body, cid, base=None, captured=None, extra=None, token=True):
    h = {"X-Change-Id": cid, "X-Offline-Replay": "1", "X-Device-Id": "dev-test",
         "X-Captured-At": captured or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if token: h["X-CSRF-Token"] = csrf(c)
    if base is not None: h["X-Base-Version"] = base
    h.update(extra or {})
    return c.post(url, json=body, headers=h)

c0 = get_db(); c0.execute("UPDATE users SET password_hash=?", (generate_password_hash("Pass1234"),)); c0.commit(); c0.close()
ADMIN, FT = login("admin"), login("aokafor")
run("DELETE FROM result_publication")
S = "/api/scores/1/1/row"
def score(sid=1): 
    c = get_db(); r = c.execute("SELECT ca1,ca2,ca3,exam,updated_at FROM scores WHERE student_id=? AND subject_id=1 AND term_id=(SELECT id FROM terms WHERE is_active=1)", (sid,)).fetchone(); c.close(); return r
def body(ca1, ca2=5, exam=20, sid=1): return {"student_id": sid, "ca1": str(ca1), "ca2": str(ca2), "exam": str(exam)}
def online_save(cl, b):
    return cl.post(S, json=b, headers={"X-CSRF-Token": csrf(cl)})

print("=== 1) plumbing ===")
for t in ("sync_changes", "sync_conflicts", "sync_log"):
    check(f"table {t} exists", one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", t) == t)
anon = A.app.test_client()
r = anon.get("/api/sync/ping"); check("ping is public, JSON and never cached", r.status_code == 200 and r.json["ok"] and "no-store" in r.headers["Cache-Control"])
check("ping answers HEAD too", anon.head("/api/sync/ping").status_code == 200)
check("session endpoint says 'not authenticated' to strangers and hands out no token", anon.get("/api/sync/session").json == {**anon.get("/api/sync/session").json, "authenticated": False, "csrf": ""})
s = FT.get("/api/sync/session").json
check("session endpoint gives a signed-in user a fingerprint + csrf", s["authenticated"] and len(s["fingerprint"]) == 16 and len(s["csrf"]) > 20, s)
page = FT.get("/dashboard")
check("pages carry X-SH-User and the same fingerprint as /api/sync/session", page.headers.get("X-SH-User") == s["fingerprint"])
check("pages load the offline scripts and the sh-user meta", all(x in html(page) for x in ("offline-core.js", "offline-ui.js", 'name="sh-user"', "offline.css")))
check("the old online-only script is no longer loaded", "online-only.js" not in html(page))
check("different users get different fingerprints", ADMIN.get("/api/sync/session").json["fingerprint"] != s["fingerprint"])
sw = anon.get("/service-worker.js")
check("service worker is served at root scope, uncached by HTTP, and really caches", sw.status_code == 200 and sw.headers["Service-Worker-Allowed"] == "/" and "no-store" in sw.headers["Cache-Control"] and b"caches.open" in sw.data and b"NEVER_CACHE" in sw.data)
check("offline fallback page is public", anon.get("/offline").status_code == 200 and b"offline" in anon.get("/offline").data.lower())
check("manifest still valid", anon.get("/manifest.json").json["display"] == "standalone")
check("Sync Center renders for a teacher (device panel only)", FT.get("/sync").status_code == 200 and "data-sync-center" in html(FT.get("/sync")) and "Conflicts for administrator" not in html(FT.get("/sync")))
check("Sync Center shows conflicts section to the administrator", "Conflicts for administrator" in html(ADMIN.get("/sync")))
check("Sync Center needs a login", anon.get("/sync").status_code in (302, 401))

print("=== 2) idempotent replay: a change can never be applied twice ===")
r = replay(FT, S, body(7), "chg-aaaa-0001", base="")
check("first replay applied (200, ok)", r.status_code == 200 and r.json["ok"], r.get_data(as_text=True))
check("response is acknowledged with the same change id", r.headers.get("X-Sync-Ack") == "chg-aaaa-0001")
check("response carries the new row version for the device", r.json.get("updated_at"))
check("score stored", score()["ca1"] == 7)
v1 = score()["updated_at"]
run("UPDATE scores SET ca1=9 WHERE student_id=1 AND subject_id=1")        # someone else edits online afterwards
r2 = replay(FT, S, body(7), "chg-aaaa-0001", base="")
check("the retry is answered from the record (duplicate header) and acknowledged", r2.headers.get("X-Sync-Duplicate") == "1" and r2.headers.get("X-Sync-Ack") == "chg-aaaa-0001" and r2.json["ok"])
check("the retry did NOT run again (later online edit survives)", score()["ca1"] == 9)
check("exactly one sync_changes row for that change id", one("SELECT COUNT(*) FROM sync_changes WHERE change_id='chg-aaaa-0001'") == 1)
check("attempts counted", one("SELECT attempts FROM sync_changes WHERE change_id='chg-aaaa-0001'") == 2)
check("device id recorded", one("SELECT device_id FROM sync_changes WHERE change_id='chg-aaaa-0001'") == "dev-test")
check("a malformed change id is refused", replay(FT, S, body(1), "bad id!!", base="").status_code == 400)
check("replay without a CSRF token is refused and recorded nowhere", replay(FT, S, body(1), "chg-nocsrf-01", base=None, token=False).status_code == 403 and one("SELECT COUNT(*) FROM sync_changes WHERE change_id='chg-nocsrf-01'") == 0)
check("a replay from a signed-out device is not accepted", anon.post(S, json=body(3), headers={"X-Change-Id": "chg-anon-0001", "X-Offline-Replay": "1"}).status_code in (302, 403))

print("=== 3) no conflict when the device saw the latest version ===")
cur = score()["updated_at"]
r = replay(FT, S, body(11), "chg-bbbb-0002", base=cur)
check("up-to-date base version: applied normally", r.status_code == 200 and score()["ca1"] == 11)

print("=== 4) conflict: someone else changed the row while the device was offline ===")
stale = score()["updated_at"]
run("UPDATE scores SET exam=33 WHERE student_id=1 AND subject_id=1")       # online edit bumps updated_at
before = dict(score())
r = replay(FT, S, body(2, 3, 4), "chg-cccc-0003", base=stale, captured="2026-11-20T08:00:00Z")
check("stale base version -> 409 conflict, not applied", r.status_code == 409 and r.json["conflict"] and r.json["conflict_id"], r.get_data(as_text=True))
check("the server value is untouched", dict(score()) == before)
cf = get_db(); row = cf.execute("SELECT * FROM sync_conflicts WHERE change_id='chg-cccc-0003'").fetchone(); cf.close()
check("conflict parked: sensitive, unresolved, both versions kept", row and row["sensitive"] == 1 and row["resolved"] == 0 and row["kind"] == "score" and json.loads(row["server_payload"])["exam"] == 33 and json.loads(row["client_payload"])["body"]["ca1"] == "2")
check("conflict acknowledged to the device so it stops retrying", r.headers.get("X-Sync-Ack") == "chg-cccc-0003" and one("SELECT state FROM sync_changes WHERE change_id='chg-cccc-0003'") == "conflict")
r_again = replay(FT, S, body(2, 3, 4), "chg-cccc-0003", base=stale)
check("retrying a parked conflict does not create a second conflict", r_again.status_code == 409 and one("SELECT COUNT(*) FROM sync_conflicts WHERE change_id='chg-cccc-0003'") == 1)
check("conflict detection wrote an audit entry", one("SELECT COUNT(*) FROM audit_log WHERE action='offline_conflict_detected'") >= 1)
check("device with NO knowledge of an existing row also conflicts (base '' but row exists)", replay(FT, S, body(1, 1, 1), "chg-cccc-0004", base="").status_code == 409)

print("=== 5) identical values resolve automatically ===")
same = score()
r = replay(FT, S, {"student_id": 1, "ca1": str(same["ca1"]), "ca2": str(same["ca2"]), "exam": str(same["exam"])}, "chg-dddd-0005", base=stale)
check("same values on both sides: auto-resolved, no conflict row", r.status_code == 200 and r.json.get("auto_resolved") and r.json.get("grade") and one("SELECT COUNT(*) FROM sync_conflicts WHERE change_id='chg-dddd-0005'") == 0)
check("auto-resolution is audited", one("SELECT COUNT(*) FROM audit_log WHERE action='offline_conflict_auto_resolved'") >= 1)

print("=== 6) administrator approval ===")
cid = row["id"]
check("a teacher cannot resolve conflicts", FT.post(f"/api/sync/conflicts/{cid}/resolve", json={"resolution": "apply_offline"}, headers={"X-CSRF-Token": csrf(FT)}).status_code in (302, 403))
check("an invalid choice is refused", ADMIN.post(f"/api/sync/conflicts/{cid}/resolve", json={"resolution": "yolo"}, headers={"X-CSRF-Token": csrf(ADMIN)}).status_code == 400)
r = ADMIN.post(f"/api/sync/conflicts/{cid}/resolve", json={"resolution": "apply_offline"}, headers={"X-CSRF-Token": csrf(ADMIN)})
check("administrator applies the offline version", r.status_code == 200 and r.json["ok"], r.get_data(as_text=True))
sc = score(); check("score now equals the offline value", (sc["ca1"], sc["ca2"], sc["exam"]) == (2, 3, 4), dict(sc))
check("applied through the real route: score_audit has it", one("SELECT COUNT(*) FROM score_audit WHERE new_ca1=2 AND new_exam=4") >= 1 if one("SELECT name FROM sqlite_master WHERE name='score_audit'") else True)
check("conflict is closed with who/when/what", one("SELECT resolved FROM sync_conflicts WHERE id=?", cid) == 1 and one("SELECT resolution FROM sync_conflicts WHERE id=?", cid) == "apply_offline" and one("SELECT resolved_by FROM sync_conflicts WHERE id=?", cid))
check("resolving twice is refused", ADMIN.post(f"/api/sync/conflicts/{cid}/resolve", json={"resolution": "keep_server"}, headers={"X-CSRF-Token": csrf(ADMIN)}).status_code == 409)
check("resolution audited", one("SELECT COUNT(*) FROM audit_log WHERE action='offline_conflict_resolved'") == 1)
# keep_server
st2 = score()["updated_at"]; run("UPDATE scores SET exam=40 WHERE student_id=1 AND subject_id=1")
replay(FT, S, body(5, 5, 5), "chg-eeee-0006", base=st2)
cid2 = one("SELECT id FROM sync_conflicts WHERE change_id='chg-eeee-0006'")
r = ADMIN.post(f"/api/sync/conflicts/{cid2}/resolve", json={"resolution": "keep_server"}, headers={"X-CSRF-Token": csrf(ADMIN)})
check("keep_server leaves the server value alone", r.json["ok"] and score()["exam"] == 40)
check("Sync Center lists the conflicts and who resolved them", "apply_offline" in html(ADMIN.get("/sync")))

print("=== 7) result workflow lock is still respected on replay ===")
cur = score()["updated_at"]
tid = one("SELECT id FROM terms WHERE is_active=1")
run("INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status) SELECT school_id,tenant_id,1,?, 'approved' FROM classes WHERE id=1", tid)
r = replay(FT, S, body(1, 1, 1), "chg-ffff-0007", base=cur)
check("a locked class rejects the replay with 423", r.status_code == 423 and r.headers.get("X-Sync-Ack") == "chg-ffff-0007")
check("it is recorded as failed (not conflict) so the device shows the server's message", one("SELECT state FROM sync_changes WHERE change_id='chg-ffff-0007'") == "failed")
run("DELETE FROM result_publication")
r = replay(FT, S, body(1, 1, 1), "chg-ffff-0007", base=cur)
check("once unlocked, the same change id can be retried (failures are not remembered as done)", r.status_code == 200 and r.json["ok"])

print("=== 8) permissions and validation still apply to replays ===")
check("out-of-range value rejected like online (400)", replay(FT, S, body(99), "chg-gggg-0008", base=score()["updated_at"]).status_code == 400)
check("unknown student rejected (404)", replay(FT, S, body(1, sid=9999), "chg-gggg-0009", base="").status_code == 404)

print("=== 9) attendance taken offline on an earlier day is parked, today's goes through the normal route ===")
ft_class = one("SELECT class_id FROM students WHERE id=1")
RC = f"/my-class/{ft_class}/roll-call"
three_days = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
form = {"csrf_token": csrf(FT), "mode": "new"}
n_before = one("SELECT COUNT(*) FROM attendance_records")
r = FT.post(RC, data=form, headers={"X-CSRF-Token": csrf(FT), "X-Change-Id": "chg-hhhh-0010", "X-Offline-Replay": "1", "X-Captured-At": three_days})
check("old attendance -> 409 conflict, nothing recorded", r.status_code == 409 and r.json["conflict"] and one("SELECT COUNT(*) FROM attendance_records") == n_before, r.get_data(as_text=True)[:200])
check("parked as attendance_stale_date with the date it was taken", one("SELECT kind FROM sync_conflicts WHERE change_id='chg-hhhh-0010'") == "attendance_stale_date" and "attendance:" in one("SELECT entity_key FROM sync_conflicts WHERE change_id='chg-hhhh-0010'"))
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
r = FT.post(RC, data={**form, "csrf_token": csrf(FT)}, headers={"X-CSRF-Token": csrf(FT), "X-Change-Id": "chg-hhhh-0011", "X-Offline-Replay": "1", "X-Captured-At": now})
check("attendance captured today is handled by the normal route (redirect) and acknowledged", r.status_code in (302, 303) and r.headers.get("X-Sync-Ack") == "chg-hhhh-0011")
check("...and was really recorded under today's server date", one("SELECT COUNT(*) FROM attendance_records") > n_before)
dup = FT.post(RC, data={**form, "csrf_token": csrf(FT)}, headers={"X-CSRF-Token": csrf(FT), "X-Change-Id": "chg-hhhh-0011", "X-Offline-Replay": "1", "X-Captured-At": now})
check("replaying that form again is a duplicate (redirect answered from the record)", dup.headers.get("X-Sync-Duplicate") == "1" and dup.status_code in (302, 303))

print("=== 10) isolation between schools ===")
run("INSERT INTO sync_conflicts (school_id, entity, client_uuid, client_payload, server_payload, change_id, kind) VALUES (999,'score','x','{}','{}','other-school-1','score')")
oid = one("SELECT id FROM sync_conflicts WHERE change_id='other-school-1'")
check("an administrator cannot resolve another school's conflict (404)", ADMIN.post(f"/api/sync/conflicts/{oid}/resolve", json={"resolution": "dismiss"}, headers={"X-CSRF-Token": csrf(ADMIN)}).status_code == 404)
check("another school's conflicts are not listed in my Sync Center", "other-school-1" not in html(ADMIN.get("/sync")) and f">{oid}<" not in html(ADMIN.get("/sync")))
run("INSERT INTO sync_changes (change_id, school_id, state) VALUES ('shared-id-0001', 999, 'applied')")
r = replay(FT, S, body(8), "shared-id-0001", base=score()["updated_at"])
check("the same change id in ANOTHER school is not a duplicate of mine", r.status_code == 200 and not r.headers.get("X-Sync-Duplicate"))

print("=== 11) status endpoints ===")
st = FT.get("/api/sync/status").json
check("status counts applied / failed / conflicts for my school only", st["ok"] and st["applied"] >= 3 and st["conflicts"] >= 2 and st["failed"] >= 1, st)
r = FT.post("/api/sync/report", json={"device_id": "dev-test", "synced": 3, "failed": 1, "conflicts": 2}, headers={"X-CSRF-Token": csrf(FT)})
check("device sync reports are stored for administrators", r.json["ok"] and one("SELECT record_count FROM sync_log WHERE device_id='dev-test'") == 3)

print(f"\nPASSED {PASS}   FAILED {len(FAIL)}")
if FAIL: print("FAILED:", FAIL); sys.exit(1)
