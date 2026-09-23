import os, tempfile, sqlite3
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='srs-tenant-test-')
os.environ['SKIP_DEMO_SEED'] = '1'
from db import get_db, init_db, generate_tenant_id, generate_school_id

init_db()
c=get_db()
c.execute("INSERT INTO schools (name, school_code, tenant_id, school_level) VALUES (?,?,?,?)",
          ("Test School A", generate_school_id(c,"Test School A"), generate_tenant_id(c), "primary"))
a=c.execute("SELECT * FROM schools WHERE name='Test School A'").fetchone()
assert a["tenant_id"] and a["school_code"]
c.execute("INSERT INTO schools (name, school_code, tenant_id, school_level) VALUES (?,?,?,?)",
          ("Test School B", generate_school_id(c,"Test School B"), generate_tenant_id(c), "secondary"))
b=c.execute("SELECT * FROM schools WHERE name='Test School B'").fetchone()
assert a["tenant_id"] != b["tenant_id"]
c.execute("INSERT INTO users (school_id, name, username, password_hash, role) VALUES (?,?,?,?,?)",
          (a["id"],"User A","tenant_test_a","x","teacher"))
u=c.execute("SELECT tenant_id FROM users WHERE username='tenant_test_a'").fetchone()
assert u["tenant_id"] == a["tenant_id"]
# Tampering with tenant_id is overwritten by the server-side trigger.
c.execute("UPDATE users SET tenant_id=? WHERE username='tenant_test_a'", (b["tenant_id"],))
u=c.execute("SELECT tenant_id FROM users WHERE username='tenant_test_a'").fetchone()
assert u["tenant_id"] == a["tenant_id"]
print("TENANT/RBAC TESTS PASSED")
