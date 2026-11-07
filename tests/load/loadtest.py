"""Concurrent-user load test against a real HTTP server.
usage: DATA_DIR=/tmp/loaddb python tests/load/loadtest.py [slots] [secs] [vus,vus,...]
  slots = simultaneous requests the server handles (production today = gunicorn 1 worker x 8 threads -> 8)
Each virtual user logs in as a form teacher of one of the seeded schools, then loops: 60% open a student's result
page, 25% open the dashboard, 15% save ratings + a comment (a DB write). Prints throughput, errors, latency."""
import os, re, sys, time, threading, sqlite3, random, statistics, subprocess, signal
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.environ["DATA_DIR"]; PORT = 5099
SLOTS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
WORKERS = int(os.environ.get("WORKERS", "1"))      # separate server processes sharing the one database (like gunicorn --workers N)
WRITE_PCT = float(os.environ.get("WRITE_PCT", "0.15"))
SECS = int(sys.argv[2]) if len(sys.argv) > 2 else 25
LEVELS = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "50,200,500,1000").split(",")]
import requests
SERVER = f'''
import os, sys, threading
sys.path.insert(0, {ROOT!r}); os.chdir({ROOT!r})
os.environ["RATE_LIMIT_DISABLED"]="1"
import app as A
from werkzeug.serving import run_simple
sem = threading.BoundedSemaphore({SLOTS})
def limited(environ, start):
    with sem:                      # emulates gunicorn --threads N: only N requests run at once, the rest queue
        body = b"".join(A.app(environ, start))
    return [body]
run_simple("127.0.0.1", int(sys.argv[1]), limited, threaded=True, use_reloader=False)
'''
con = sqlite3.connect(f"{DATA}/school.db"); con.row_factory = sqlite3.Row
schools = []
for r in con.execute("SELECT u.username, s.id sid FROM users u JOIN schools s ON s.id=u.school_id WHERE u.username LIKE 't%' AND u.username GLOB 't[0-9]*'"):
    stu = [x[0] for x in con.execute("SELECT id FROM students WHERE school_id=? LIMIT 30", (r["sid"],))]
    term = con.execute("SELECT t.id FROM terms t JOIN sessions se ON se.id=t.session_id WHERE se.school_id=? LIMIT 1", (r["sid"],)).fetchone()[0]
    tr = [x[0] for x in con.execute("SELECT id FROM skill_traits WHERE school_id=? LIMIT 15", (r["sid"],))]
    schools.append((r["username"], stu, term, tr))
con.close()
print(f"{len(schools)} schools available; workers={WORKERS} x slots={SLOTS}; write share={WRITE_PCT:.0%}; {SECS}s per level", flush=True)

def vu(i, stop, lat, errs, kinds, go, ready):
    uname, stu, term, traits = schools[i % len(schools)]
    s = requests.Session(); base = f"http://127.0.0.1:{PORT + i % WORKERS}"
    try:
        r = s.get(base + "/login", timeout=60); tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
        r = s.post(base + "/login", data={"username": uname, "password": "Load12345", "csrf_token": tok}, timeout=60)
        if "/login" in r.url: errs.append("login"); ready.append(0); return
    except Exception as e:
        errs.append("login:" + type(e).__name__); ready.append(0); return
    ready.append(1)
    go.wait()                                  # measured window starts once everyone is logged in
    rnd = random.Random(i)
    while not stop.is_set():
        x = rnd.random(); sid = rnd.choice(stu)
        t0 = time.time()
        try:
            if x < .60:
                kind = "result"; r = s.get(f"{base}/result/{sid}?term_id={term}", timeout=60)
            elif x < 1 - WRITE_PCT:
                kind = "dashboard"; r = s.get(base + "/", timeout=60)
            else:
                kind = "write"
                p = s.get(f"{base}/result/{sid}?term_id={term}", timeout=60)
                m = re.search(r'name="csrf_token" value="([^"]+)"', p.text); tk = m.group(1) if m else ""
                d = {"csrf_token": tk, "term_id": term, "teacher_comment": "Load test."}
                d.update({f"trait_{t}": str(rnd.randint(1, 5)) for t in traits})
                r = s.post(f"{base}/result/{sid}/extra", data=d, timeout=60)
            dt = time.time() - t0
            if r.status_code >= 500: errs.append(f"{kind}:{r.status_code}")
            else: lat.append(dt); kinds[kind] = kinds.get(kind, 0) + 1
        except Exception as e:
            errs.append(f"{kind}:{type(e).__name__}")
        time.sleep(rnd.uniform(.3, 1.0))      # think time

for n in LEVELS:
    srvs = [subprocess.Popen([sys.executable, "-c", SERVER, str(PORT + w)], env={**os.environ, "DATA_DIR": DATA}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for w in range(WORKERS)]
    for w in range(WORKERS):
        for _ in range(60):
            try:
                if requests.get(f"http://127.0.0.1:{PORT + w}/healthz", timeout=2).status_code == 200: break
            except Exception: time.sleep(.5)
    stop, go = threading.Event(), threading.Event(); lat, errs, kinds, ready = [], [], {}, []
    ths = [threading.Thread(target=vu, args=(i, stop, lat, errs, kinds, go, ready), daemon=True) for i in range(n)]
    for t in ths: t.start(); time.sleep(0.005)
    tl = time.time()
    while len(ready) < n and time.time() - tl < 240: time.sleep(.5)
    print(f"   logged in {sum(ready)}/{n} in {time.time()-tl:.0f}s", flush=True)
    t0 = time.time(); go.set()
    time.sleep(SECS); stop.set(); el = time.time() - t0
    for t in ths: t.join(timeout=15)
    lat.sort(); q = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))] if lat else float("nan")
    logins = sum(1 for e in errs if e.startswith("login"))
    print(f"VUs={n:5d} ok={len(lat):6d} err={len(errs):5d} (login-fail {logins}) rps={len(lat)/el:6.1f}  p50={q(.5):6.2f}s p95={q(.95):6.2f}s p99={q(.99):6.2f}s  mix={kinds}", flush=True)
    for srv in srvs: srv.send_signal(signal.SIGTERM)
    for srv in srvs: srv.wait(timeout=20)
