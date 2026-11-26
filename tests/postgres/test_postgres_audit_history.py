import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build_postgres_audit_history import generate, validate

PLAN = json.loads((ROOT / 'postgres_trigger_porting_plan.json').read_text())
SNAPSHOT = json.loads((ROOT / 'postgres_effective_schema_snapshot.json').read_text())
SQL = generate(PLAN, SNAPSHOT)

def test_inventory_has_exactly_two_reviewed_history_triggers():
    validate(PLAN, SNAPSHOT)
    assert SQL.count('CREATE TRIGGER') == 2

def test_insert_history_preserves_created_values_and_actor_fallback():
    assert "'created', NULL, NEW.status" in SQL
    assert 'NEW.amount_ngn, NEW.payment_reference, COALESCE(NEW.confirmed_by, \'system\')' in SQL

def test_update_history_uses_null_safe_comparisons():
    assert SQL.count('IS DISTINCT FROM') >= 5
    assert 'OLD.amount_ngn, NEW.amount_ngn' in SQL
    assert 'OLD.payment_reference, NEW.payment_reference' in SQL

def test_action_mapping_is_preserved():
    assert "THEN 'confirmed'" in SQL
    assert "THEN 'status_changed'" in SQL
    assert "ELSE 'changed'" in SQL

def test_provider_only_update_does_not_create_history():
    assert 'provider, invoice_id ON billing_payments' in SQL
    predicate = SQL.split('IF OLD.status IS DISTINCT FROM NEW.status', 1)[1].split('THEN', 1)[0]
    assert 'provider' not in predicate

def test_history_insert_is_transactional_trigger_work():
    assert 'AFTER INSERT ON billing_payments' in SQL
    assert 'AFTER UPDATE OF status' in SQL
    assert 'FOR EACH ROW EXECUTE FUNCTION app_capture_billing_payment_history()' in SQL

def test_generator_fails_closed_when_trigger_is_missing():
    altered = json.loads(json.dumps(PLAN))
    altered['triggers'] = [x for x in altered['triggers'] if x['name'] != 'trg_billing_payment_update_history']
    with pytest.raises(ValueError, match='exactly the two reviewed'):
        generate(altered, SNAPSHOT)

def test_generator_fails_closed_when_required_column_is_missing():
    altered = json.loads(json.dumps(SNAPSHOT))
    table = next(t for t in altered['tables'] if t['name'] == 'billing_payment_history')
    table['columns'] = [c for c in table['columns'] if c['name'] != 'actor']
    with pytest.raises(ValueError, match='missing required columns'):
        generate(PLAN, altered)
