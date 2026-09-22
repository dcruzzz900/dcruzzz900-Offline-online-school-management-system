"""The offline result engine (static/js/offline-results.js) must produce the
same numbers as the server. Builds a class with ties, half-cent averages, a
missing score and CA3 turned on, has the SERVER compute the broadsheet and
each result, then has Node recompute them from the device's synced records."""
import json
import os
import subprocess
import tempfile
from helpers import fresh_app, new_device, bootstrap, ROOT


def _server_expectations(m, class_id, term_id, sid):
    import db
    from flask import session
    with m.app.test_request_context():
        session["school_id"] = sid
        conn = db.get_db()
        subjects, rows = m.build_broadsheet_data(conn, class_id, term_id)
        exp = {"broadsheet": [], "results": []}
        for r in rows:
            exp["broadsheet"].append({
                "student_id": r["student"]["id"], "total": r["total"], "average": r["average"],
                "position": r["position"],
                "scores": {str(k): {"total": v["total"], "grade": v["grade"]} for k, v in r["scores"].items()},
            })
            data = m.build_result_data(conn, r["student"]["id"], term_id)
            exp["results"].append({
                "student_id": r["student"]["id"], "total": data["total"], "average": data["average"],
                "position": data["position"], "show_ca3": data["show_ca3"],
                "subjects": [[s["name"], s["ca1"], s["ca2"], s["ca3"], s["exam"], s["total"], s["grade"], s["remark"]]
                             for s in data["subjects"]],
                "info": [(data["info"]["teacher_comment"] if data["info"] else None) or None,
                         (data["info"]["principal_comment"] if data["info"] else None) or None,
                         (data["info"]["teacher_signed_date"] if data["info"] else None) or None,
                         (data["info"]["principal_signed_date"] if data["info"] else None) or None],
                "ratings": [[x["name"], x["category"], x["rating"]] for x in data["ratings"]],
                "has_result_date": bool(data["result_date"]),
            })
        session_id = conn.execute("SELECT session_id FROM terms WHERE id=?", (term_id,)).fetchone()[0]
        c_subjects, c_terms, c_rows = m.build_cumulative_broadsheet_data(conn, class_id, session_id)
        exp["cumulative"] = {
            "sessionId": session_id, "terms": [t["id"] for t in c_terms],
            "rows": [{"student_id": r["student"]["id"], "average": r["average"], "position": r["position"],
                      "subjects": {str(k): {"v": v["term_values"], "a": v["average"], "g": v["grade"]} for k, v in r["subjects"].items()}}
                     for r in c_rows],
        }
        conn.close()
    return exp


def test_offline_engine_matches_server_numbers():
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    sid = conn.execute("SELECT id FROM schools").fetchone()[0]
    cls = conn.execute("SELECT id FROM classes").fetchone()[0]
    term = conn.execute("SELECT id FROM terms").fetchone()[0]
    subjects = [r[0] for r in conn.execute("SELECT id FROM subjects ORDER BY name")]
    students = [r[0] for r in conn.execute("SELECT id FROM students ORDER BY id")]
    conn.execute("UPDATE grading_config SET ca1_max=10, ca2_max=10, ca3_max=10, exam_max=70")
    # add two more students so there are ties and a student with no scores
    for adm, fn, ln in (("004", "Ngozi", "Adeyemi"), ("005", "Ibrahim", "Bello")):
        cur = conn.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES (?,?,?,?,?)",
                           (adm, fn, ln, "M", cls))
        conn.execute("INSERT INTO enrollments (student_id, session_id, class_id) SELECT ?, id, ? FROM sessions", (cur.lastrowid, cls))
        students.append(cur.lastrowid)
    conn.commit()
    data = {
        students[0]: [(9, 8, 7, 60), (10, 10, 10, 70), (5.5, 5.5, 5.5, 33.25), (0, 0, 0, 0)],
        students[1]: [(9, 8, 7, 60), (10, 10, 10, 70), (5.5, 5.5, 5.5, 33.25), (0, 0, 0, 0)],   # exact tie with student 0
        students[2]: [(7.25, 7.25, 7.25, 39.375), (6, 6, 6, 41), (8, 8, 8, 44.5), None],          # .125 tie average territory
        students[3]: [(1, 2, 3, 4), None, None, None],
        # students[4]: nothing at all
    }
    for stu, cells in data.items():
        for subj, cell in zip(subjects, cells):
            if cell:
                conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, ca3, exam) VALUES (?,?,?,?,?,?,?)",
                             (stu, subj, term, *cell[:3], cell[3]))
    # comments, signed dates and skill ratings
    traits = [r[0] for r in conn.execute("SELECT id FROM skill_traits ORDER BY id LIMIT 4")]
    assert len(traits) >= 2
    for stu, rating in ((students[0], 5), (students[2], 3)):
        for t in traits:
            conn.execute("INSERT INTO student_skill_ratings (student_id, term_id, trait_id, rating) VALUES (?,?,?,?)",
                         (stu, term, t, rating))
    conn.execute("INSERT INTO student_term_info (student_id, term_id, teacher_comment, principal_comment, teacher_signed_date, principal_signed_date) "
                 "VALUES (?,?,?,?,?,?)", (students[0], term, "Hardworking <b>pupil</b>", "Well done", "2026-07-15", "2026-07-16"))
    conn.execute("UPDATE schools SET show_result_date=1")
    session_id = conn.execute("SELECT session_id FROM terms WHERE id=?", (term,)).fetchone()[0]
    conn.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (session_id,))
    term2 = conn.execute("SELECT id FROM terms WHERE name='2nd Term' AND session_id=?", (session_id,)).fetchone()[0]
    for stu, sb, vals in ((students[0], subjects[0], (8, 9, 6, 55)), (students[0], subjects[1], (10, 10, 10, 60)),
                          (students[2], subjects[0], (7, 7, 7, 41.5)), (students[3], subjects[2], (3, 3, 3, 33))):
        conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, ca3, exam) VALUES (?,?,?,?,?,?,?)", (stu, sb, term2, *vals))
    conn.commit()
    conn.close()

    def run_parity(label):
        dev, cred = new_device(m, "admin", "admin123")
        boot = bootstrap(dev, cred)
        exp = _server_expectations(m, cls, term, sid)
        tmp = tempfile.mkdtemp()
        fx, ex = os.path.join(tmp, "fx.json"), os.path.join(tmp, "ex.json")
        json.dump({"entities": boot["entities"], "school": boot["school"], "classId": cls, "termId": term}, open(fx, "w"))
        json.dump(exp, open(ex, "w"))
        out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "parity.js"), fx, ex], capture_output=True, text=True)
        assert out.returncode == 0, label + "\n" + out.stdout + out.stderr
        assert "parity OK" in out.stdout

    run_parity("stored comments")
    conn = db.get_db()
    conn.execute("UPDATE schools SET auto_teacher_comment=1, auto_principal_comment=1")
    conn.commit()
    conn.close()
    run_parity("auto-generated comments")
