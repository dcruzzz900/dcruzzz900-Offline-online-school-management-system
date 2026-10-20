"""Test shortcut for the publication workflow: puts every class of a term into the state a COMPLETED workflow would leave it in
(and runs the same side effects the real publish step runs). The real workflow is exercised end-to-end in v63_scenarios.py."""
import v63_core


def _all(conn, term_id):
    school = conn.execute("SELECT se.school_id FROM terms t JOIN sessions se ON se.id=t.session_id WHERE t.id=?", (term_id,)).fetchone()[0]
    return school, [r[0] for r in conn.execute("SELECT id FROM classes WHERE school_id=?", (school,))]


def publish(A, term_id):
    from db import get_db
    conn = get_db()
    school, classes = _all(conn, term_id)
    tenant = conn.execute("SELECT tenant_id FROM schools WHERE id=?", (school,)).fetchone()[0]
    for cid in classes:
        conn.execute("INSERT INTO result_publication(school_id,tenant_id,class_id,term_id,status,published_at) VALUES (?,?,?,?, 'published', CURRENT_TIMESTAMP) "
                     "ON CONFLICT(school_id,class_id,term_id) DO UPDATE SET status='published', published_at=CURRENT_TIMESTAMP", (school, tenant, cid, term_id))
    flipped = v63_core.sync_term_flag(conn, school, term_id)
    conn.commit()
    if flipped:
        from flask import session
        with A.app.test_request_context():
            session["school_id"] = school
            session["user_id"] = 1
            session["name"] = "test"
            A.AUTO_ADVANCE(conn, int(term_id))
        conn.commit()
    try:
        import profile_core as pc
        pc.audit(conn, {"type": "staff", "id": 1, "name": "test", "role": "School Admin", "school_id": school, "tenant_id": tenant},
                 "results_published", "term", term_id, {"term": term_id})
        conn.commit()
    except Exception:
        pass
    conn.close()


def unpublish(A, term_id):
    from db import get_db
    conn = get_db()
    school, classes = _all(conn, term_id)
    conn.execute("UPDATE result_publication SET status='reopened' WHERE school_id=? AND term_id=?", (school, term_id))
    v63_core.sync_term_flag(conn, school, term_id)
    conn.commit(); conn.close()
