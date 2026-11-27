import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'build_postgres_trigger_porting_plan.py'
spec = importlib.util.spec_from_file_location('trigger_plan', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_classifies_core_trigger_behaviours():
    assert module.classify('trg_x_no_delete', 'BEFORE DELETE ... RAISE(ABORT)') == 'immutability_guard'
    assert module.classify('trg_x_tombstone', 'AFTER DELETE') == 'soft_delete_or_sync_tombstone'
    assert module.classify('trg_x_tenant_stamp', 'NEW.tenant_id') == 'tenant_scope_propagation'
    assert module.classify('trg_x_sync_touch', 'NEW.updated_at') == 'offline_sync_timestamp'

def test_plan_preserves_sql_and_detects_old_new():
    snap={'other_objects':[{'type':'trigger','name':'trg_test','table':'records','sql':'CREATE TRIGGER trg_test AFTER UPDATE ON records BEGIN SELECT NEW.id, OLD.id; END'}]}
    plan=module.build(snap)
    assert plan['trigger_count']==1
    item=plan['triggers'][0]
    assert item['uses_old'] and item['uses_new']
    assert 'CREATE TRIGGER' in item['source_sql']
    assert item['category']=='business_rule_or_other'
