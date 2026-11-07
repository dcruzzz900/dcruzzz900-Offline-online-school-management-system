"""Seed N schools (each: admin + form teacher, 1 class, 4 subjects, M students, scores) into DATA_DIR's database.
usage: DATA_DIR=/tmp/x python tests/load/seed_schools.py 200 40"""
import os, sys, random
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
from db import get_db, seed_school_defaults, ensure_school_v61_defaults, generate_school_id
from werkzeug.security import generate_password_hash
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
M = int(sys.argv[2]) if len(sys.argv) > 2 else 40
random.seed(1)
pw = generate_password_hash("Load12345")           # one hash for everybody (hashing 1000s of times is slow)
conn = get_db(); cur = conn.cursor()
have = cur.execute("SELECT COUNT(*) FROM schools").fetchone()[0]
for i in range(have + 1, N + 1):
    name = f"Load School {i}"
    cur.execute("INSERT INTO schools (name) VALUES (?)", (name,)); sid = cur.lastrowid
    cur.execute("UPDATE schools SET tenant_id=CAST(id AS TEXT) WHERE id=?", (sid,))
    cur.execute("UPDATE schools SET school_code=?, school_id_public=? WHERE id=?", (generate_school_id(conn, name),) * 2 + (sid,))
    cur.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role) VALUES (?,?,?,?,?,?)", (sid, str(sid), f"Admin {i}", f"admin{i}", pw, "admin"))
    cur.execute("INSERT INTO users (school_id, tenant_id, name, username, password_hash, role, position) VALUES (?,?,?,?,?,?,?)", (sid, str(sid), f"Teacher {i}", f"t{i}", pw, "teacher", "form_teacher"))
    tid = cur.lastrowid
    cur.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (sid, "2025/2026")); ses = cur.lastrowid
    cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('1st Term', ?, 1)", (ses,)); term = cur.lastrowid
    conn.commit(); seed_school_defaults(conn, sid); ensure_school_v61_defaults(conn, sid)
    cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'JSS1A')", (sid,)); cid = cur.lastrowid
    cur.execute("UPDATE classes SET form_teacher_id=? WHERE id=?", (tid, cid))
    subs = []
    for s in ("Mathematics", "English Language", "Basic Science", "Social Studies"):
        cur.execute("INSERT INTO subjects (school_id, name) VALUES (?,?)", (sid, s)); subs.append(cur.lastrowid)
        cur.execute("INSERT INTO class_subjects (class_id, subject_id, teacher_id) VALUES (?,?,?)", (cid, subs[-1], tid))
    for k in range(M):
        cur.execute("INSERT INTO students (school_id, tenant_id, admission_no, first_name, last_name, gender, class_id) VALUES (?,?,?,?,?,?,?)",
                    (sid, str(sid), f"{k+1:03d}", f"First{k}", f"Last{k}", "M" if k % 2 else "F", cid))
        stu = cur.lastrowid
        cur.execute("INSERT INTO enrollments (student_id, session_id, class_id) VALUES (?,?,?)", (stu, ses, cid))
        for sub in subs:
            cur.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, ca3, exam) VALUES (?,?,?,?,?,0,?)", (stu, sub, term, random.randint(5, 20), random.randint(0, 20), random.randint(10, 60)))
    conn.commit()
    if i % 50 == 0: print("seeded", i, flush=True)
print("schools:", cur.execute("SELECT COUNT(*) FROM schools").fetchone()[0], "students:", cur.execute("SELECT COUNT(*) FROM students").fetchone()[0])
