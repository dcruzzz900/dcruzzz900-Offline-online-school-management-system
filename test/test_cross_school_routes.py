"""Cross-school isolation on the ONLINE routes: log in as School A staff and
call every route that takes an id, using School B's ids. Nothing of B's may be
shown and none of B's data may change. A positive control (B's own admin doing
the same) proves the probe can actually see and change B's data, so a pass
means something."""
import json
import re
from helpers import fresh_app, login, csrf, make_school

MARK = re.compile(r"Bola|B001|SS1A|Physics|School B|SECRETB|adminb")


def _world():
    m, _ = fresh_app()
    b = make_school(m)
    import db
    conn = db.get_db()
    conn.execute("INSERT INTO grade_scale (school_id, grade, min_score, max_score, remark) VALUES (?, 'Z', 0, 1, 'zz')", (b["school_id"],))
    b["scale_id"] = conn.execute("SELECT id FROM grade_scale WHERE school_id=? ORDER BY id DESC LIMIT 1", (b["school_id"],)).fetchone()[0]
    conn.execute("INSERT INTO class_subjects (class_id, subject_id) VALUES (?,?)", (b["class_id"], b["subject_id"]))
    conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,7,7,7)",
                 (b["student_id"], b["subject_id"], b["term_id"]))
    conn.execute("INSERT INTO student_term_info (student_id, term_id, teacher_comment) VALUES (?,?, 'SECRETB')",
                 (b["student_id"], b["term_id"]))
    b["session_id"] = conn.execute("SELECT id FROM sessions WHERE school_id=?", (b["school_id"],)).fetchone()[0]
    conn.commit()
    conn.close()
    return m, b


def _snapshot(b):
    import db
    c = db.get_db()
    queries = {
        "students": f"SELECT * FROM students WHERE class_id={b['class_id']}",
        "classes": f"SELECT id,name,form_teacher_id FROM classes WHERE school_id={b['school_id']}",
        "subjects": f"SELECT id,name FROM subjects WHERE school_id={b['school_id']}",
        "users": f"SELECT id,name,username,role,password_hash FROM users WHERE school_id={b['school_id']}",
        "scores": f"SELECT student_id,subject_id,term_id,ca1,ca2,ca3,exam FROM scores WHERE student_id={b['student_id']}",
        "info": f"SELECT student_id,term_id,teacher_comment,principal_comment FROM student_term_info WHERE student_id={b['student_id']}",
        "grade": f"SELECT id,grade,min_score,max_score,remark FROM grade_scale WHERE school_id={b['school_id']}",
        "cfg": f"SELECT ca1_max,ca2_max,ca3_max,exam_max FROM grading_config WHERE school_id={b['school_id']}",
        "sessions": f"SELECT id,name,is_active FROM sessions WHERE school_id={b['school_id']}",
        "terms": f"SELECT id,name,is_active FROM terms WHERE session_id={b['session_id']}",
        "school": f"SELECT id,name FROM schools WHERE id={b['school_id']}",
        "cs": f"SELECT * FROM class_subjects WHERE class_id={b['class_id']}",
    }
    out = {k: [tuple(r) for r in c.execute(q).fetchall()] for k, q in queries.items()}
    c.close()
    return out


def _probe(m, b, username, password):
    ids = {"student_id": b["student_id"], "class_id": b["class_id"], "subject_id": b["subject_id"],
           "term_id": b["term_id"], "session_id": b["session_id"], "scale_id": b["scale_id"],
           "teacher_id": b["admin_id"], "user_id": b["admin_id"], "school_id": b["school_id"]}
    c = m.app.test_client()
    assert login(c, username, password).status_code == 302
    before = _snapshot(b)
    leaks, errors, calls = [], [], 0
    for rule in sorted(m.app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.endpoint == "static" or rule.rule.startswith(("/api/", "/__")) or not rule.arguments:
            continue
        args = {a: ids.get(a, 1 if conv.__class__.__name__ == "IntegerConverter" else "x")
                for a, conv in rule._converters.items()}
        try:
            url = m.app.url_map.bind("localhost").build(rule.endpoint, args)
        except Exception:
            continue
        for method in sorted(rule.methods & {"GET", "POST"}):
            if method == "GET":
                r = c.get(url)
            else:
                r = c.post(url, data={"csrf_token": csrf(c), "name": "HACK", "ca1": "1", "title": "x", "comment": "x",
                                      "grade": "Q", "min_score": "0", "max_score": "1", "status": "present"})
            calls += 1
            body = r.get_data().decode("utf-8", "ignore")
            if r.status_code == 200 and MARK.search(body):
                leaks.append((method, url, MARK.search(body).group(0)))
            if r.status_code >= 500:
                errors.append((method, url, r.status_code))
            with c.session_transaction() as s:      # a route may log us out; keep probing
                needs_login = "user_id" not in s
            if needs_login:
                login(c, username, password)
    return leaks, errors, calls, before != _snapshot(b)


def test_school_a_staff_cannot_see_or_change_school_b_through_any_id_route():
    m, b = _world()
    for who, creds in (("A admin", ("admin", "admin123")), ("A teacher", ("aokafor", "teacher123"))):
        leaks, errors, calls, changed = _probe(m, b, *creds)
        assert calls > 50, calls               # the probe really did exercise the app
        assert not leaks, (who, leaks)
        assert not errors, (who, errors)
        assert not changed, who


def test_probe_positive_control_school_b_admin_does_see_and_change_its_own_data():
    m, b = _world()
    leaks, errors, calls, changed = _probe(m, b, *b["admin"])
    assert leaks and changed
