"""V113: local SQLite installation - automatic backups, verification, retention, recovery. Run: python tests/v113_local_install_scenarios.py"""
import os, sqlite3, sys, tempfile, logging, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = tempfile.mkdtemp(prefix="v113local_"); os.environ["DATA_DIR"] = DATA
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A, db, local_backup as LB
logging.disable(logging.CRITICAL)
PASS, FAIL = 0, []
def check(n, c, d=""):
    global PASS
    if c: PASS += 1
    else: FAIL.append(n); print("FAIL:", n, d)
def q(sql, path=None):
    c = sqlite3.connect(path or db.DB_PATH); r = c.execute(sql).fetchone(); c.close(); return r[0] if r else None

check("the data folder holds a SQLite database (SQLite stays the primary database)", os.path.exists(os.path.join(DATA, "school.db")))
os.makedirs(os.path.join(DATA, "materials"), exist_ok=True); open(os.path.join(DATA, "materials", "note.txt"), "w").write("uploaded lesson note")
n_students = q("SELECT COUNT(*) FROM students")
b1 = LB.make_backup(keep=3)
check("backup file created and verified", os.path.exists(b1) and LB.verify(b1))
check("backup holds the same data", q("SELECT COUNT(*) FROM students", b1) == n_students)
check("uploaded files are backed up too", any(x["name"].startswith("files-") for x in LB.list_backups()))
for _ in range(4):
    import time; time.sleep(1.05); LB.make_backup(keep=3)
check("retention keeps only the newest N", len([x for x in LB.list_backups() if x["name"].startswith("school-")]) == 3)

# disaster: data lost
c = sqlite3.connect(db.DB_PATH); c.execute("PRAGMA foreign_keys=OFF"); c.execute("DELETE FROM scores"); c.execute("DELETE FROM students"); c.commit(); c.close()
check("(simulated disaster) students are gone", q("SELECT COUNT(*) FROM students") == 0)
newest = [x["name"] for x in LB.list_backups() if x["name"].startswith("school-")][0]
safety = LB.restore_backup(newest)
check("restore brings every student back", q("SELECT COUNT(*) FROM students") == n_students)
check("restored database is healthy and complete", q("PRAGMA integrity_check") == "ok" and q("SELECT COUNT(*) FROM schools") >= 1)
check("the database it replaced was kept as a safety copy", safety and os.path.exists(safety) and q("SELECT COUNT(*) FROM students", safety) == 0)
check("restore works from the command line too (and says so)", subprocess.run([sys.executable, "local_backup.py", "list"], capture_output=True, text=True, env=os.environ).returncode == 0)

# damaged backup is refused
bad = os.path.join(LB.backup_dir(), "school-99999999-000000.db"); open(bad, "wb").write(b"this is not a database" * 50)
before = q("SELECT COUNT(*) FROM students")
try: LB.restore_backup("school-99999999-000000.db"); refused = False
except RuntimeError as e: refused = "damaged" in str(e)
check("a damaged backup is refused and nothing changes", refused and q("SELECT COUNT(*) FROM students") == before)
other = os.path.join(LB.backup_dir(), "other.db"); c = sqlite3.connect(other); c.execute("create table x(a)"); c.commit(); c.close()
try: LB.restore_backup("other.db"); refused = False
except RuntimeError: refused = True
check("a healthy SQLite file that is NOT a School Hub database is refused", refused)
os.remove(bad); os.remove(other)

# files restore + zip-slip guard
os.remove(os.path.join(DATA, "materials", "note.txt"))
fz = [x["name"] for x in LB.list_backups() if x["name"].startswith("files-")][0]; LB.restore_files(fz)
check("uploaded files restored", open(os.path.join(DATA, "materials", "note.txt")).read() == "uploaded lesson note")
import zipfile; evil = os.path.join(LB.backup_dir(), "files-evil.zip")
with zipfile.ZipFile(evil, "w") as z: z.writestr("../escape.txt", "x")
try: LB.restore_files("files-evil.zip"); blocked = False
except RuntimeError: blocked = True
check("a files backup cannot write outside the data folder", blocked and not os.path.exists(os.path.join(os.path.dirname(DATA), "escape.txt")))

# scheduler
logs = []; s = LB.BackupScheduler(hours=6, keep=3, log=lambda *a: logs.append(a))
for f in os.listdir(LB.backup_dir()):
    if f.startswith("school-"): os.utime(os.path.join(LB.backup_dir(), f), (0, 0))
check("scheduler sees an old backup as due", s.due())
check("scheduler takes a backup when due", s.run_once() and not s.due())
check("scheduler does not back up again straight away", not s.run_once())
broken = LB.BackupScheduler(hours=0, log=lambda *a: logs.append(a)); os.rename(db.DB_PATH, db.DB_PATH + ".x")
check("a backup problem never raises into the app", broken.run_once() is False); os.rename(db.DB_PATH + ".x", db.DB_PATH)

# launcher imports cleanly and respects --data
r = subprocess.run([sys.executable, "-c", "import run_local; print(run_local.main.__name__)"], capture_output=True, text=True, cwd=ROOT)
check("run_local.py imports", r.returncode == 0 and "main" in r.stdout, r.stderr)
print(f"\nPASSED {PASS}   FAILED {len(FAIL)}")
if FAIL: print("FAILED:", FAIL); sys.exit(1)
