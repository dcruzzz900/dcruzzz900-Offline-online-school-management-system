import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from build_postgres_uniqueness import generate, validate

PLAN=json.loads((ROOT/'postgres_trigger_porting_plan.json').read_text())
SCHEMA=json.loads((ROOT/'postgres_effective_schema_snapshot.json').read_text())

def test_generates_four_unique_indexes_and_five_guards():
    sql=generate(PLAN,SCHEMA)
    assert sql.count('CREATE UNIQUE INDEX IF NOT EXISTS') == 4
    assert sql.count('CREATE TRIGGER ') == 5
    assert 'lower(btrim(admission_no))' in sql
    assert 'lower(username)' in sql
    assert 'lower(email)' in sql
    assert 'lower(staff_id)' in sql

def test_indexes_exclude_null_scope_where_sqlite_equality_did():
    sql=generate(PLAN,SCHEMA)
    assert 'WHERE class_id IS NOT NULL AND admission_no IS NOT NULL' in sql
    assert 'WHERE school_id IS NOT NULL AND staff_id IS NOT NULL' in sql

def test_staff_school_change_is_checked():
    sql=generate(PLAN,SCHEMA)
    assert 'UPDATE OF username, email, staff_id, school_id' in sql

def test_signup_name_permanent_identity_guard_is_preserved():
    sql=generate(PLAN,SCHEMA)
    assert 'NEW.signup_name IS DISTINCT FROM OLD.signup_name' in sql
    assert 'The signup name is a permanent identity record' in sql

def test_duplicate_preflight_runs_before_indexes():
    sql=generate(PLAN,SCHEMA)
    assert sql.index('DO $preflight$') < sql.index('CREATE UNIQUE INDEX IF NOT EXISTS')
    for phrase in ('Duplicate usernames exist','Duplicate email addresses exist','Duplicate staff IDs exist','Duplicate admission numbers exist'):
        assert phrase in sql

def test_unknown_trigger_inventory_fails_closed():
    broken=json.loads(json.dumps(PLAN))
    broken['triggers']=[x for x in broken['triggers'] if x.get('name')!='trg_users_signup_name_lock']
    try: validate(broken,SCHEMA)
    except ValueError: pass
    else: raise AssertionError('Expected fail-closed validation')

def test_unique_indexes_are_authoritative_for_concurrent_writes():
    sql=generate(PLAN,SCHEMA)
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_students_class_admission_ci' in sql
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_ci' in sql
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_ci' in sql
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_users_school_staff_id_ci' in sql
