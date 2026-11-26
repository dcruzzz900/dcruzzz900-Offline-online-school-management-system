import json, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from build_postgres_business_rule_triggers import generate, validate
PLAN=json.loads((ROOT/'postgres_trigger_porting_plan.json').read_text())
SNAP=json.loads((ROOT/'postgres_effective_schema_snapshot.json').read_text())
SQL=generate(PLAN,SNAP)

def test_exact_inventory_and_two_triggers():
    validate(PLAN,SNAP)
    assert SQL.count('CREATE TRIGGER') == 2

def test_school_code_is_permanent_only_after_initial_value():
    assert "OLD.school_code IS NOT NULL" in SQL
    assert "OLD.school_code <> ''" in SQL
    assert 'NEW.school_code IS DISTINCT FROM OLD.school_code' in SQL
    assert "MESSAGE = 'The School ID is permanent'" in SQL

def test_school_guard_only_runs_for_school_code_updates():
    assert 'BEFORE UPDATE OF school_code ON schools' in SQL

def test_signup_name_initialization_is_after_insert_and_empty_only():
    assert 'AFTER INSERT ON users' in SQL
    assert "NEW.signup_name = ''" in SQL
    assert 'UPDATE users SET signup_name = NEW.name WHERE id = NEW.id' in SQL

def test_signup_name_initialization_is_transactional_trigger_work():
    assert 'FOR EACH ROW EXECUTE FUNCTION app_initialize_signup_name()' in SQL

def test_generator_rejects_missing_trigger():
    altered=json.loads(json.dumps(PLAN))
    altered['triggers']=[x for x in altered['triggers'] if x['name']!='trg_users_signup_name_init']
    with pytest.raises(ValueError,match='exactly the two reviewed'):
        generate(altered,SNAP)

def test_generator_rejects_missing_schema_column():
    altered=json.loads(json.dumps(SNAP))
    table=next(t for t in altered['tables'] if t['name']=='schools')
    table['columns']=[c for c in table['columns'] if c['name']!='school_code']
    with pytest.raises(ValueError,match='missing required columns'):
        generate(PLAN,altered)
