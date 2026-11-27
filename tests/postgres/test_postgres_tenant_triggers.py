import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build_postgres_tenant_triggers import generate


def load():
    return (json.loads((ROOT/'postgres_trigger_porting_plan.json').read_text()),
            json.loads((ROOT/'postgres_effective_schema_snapshot.json').read_text()))


def test_generates_28_pg_triggers_from_29_sqlite_entries():
    sql, count = generate(*load())
    assert count == 28
    assert sql.count('CREATE TRIGGER') == 28
    assert 'trg_students_tenant_stamp_pg' in sql
    assert 'trg_students_stamp_tenant_pg' not in sql


def test_direct_tenant_relationships_use_before_insert_and_preserve_existing_value():
    sql, _ = generate(*load())
    assert 'BEFORE INSERT ON "classes"' in sql
    assert "IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN" in sql
    assert 'SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;' in sql
    assert 'NEW.tenant_id := v_tenant_id;' in sql


def test_join_based_relationships_are_explicit():
    sql, _ = generate(*load())
    assert 'WHERE c.id = NEW.class_id;' in sql
    assert 'WHERE st.id = NEW.student_id;' in sql
    assert 'JOIN classes c ON c.id = st.class_id JOIN schools s ON s.id = c.school_id' in sql


def test_student_trigger_stamps_school_and_tenant_together():
    sql, _ = generate(*load())
    assert 'SELECT c.school_id, s.tenant_id INTO NEW.school_id, v_tenant_id' in sql
    assert 'IF NEW.school_id IS NULL OR NEW.tenant_id IS NULL OR NEW.tenant_id =' in sql


def test_generator_fails_closed_when_source_relationship_changes():
    inv, snap = load()
    item = next(t for t in inv['triggers'] if t['name'] == 'trg_classes_tenant_stamp')
    item['source_sql'] = item['source_sql'].replace('NEW.school_id', 'NEW.other_id')
    try:
        generate(inv, snap)
    except ValueError as exc:
        assert 'Unexpected source relationship' in str(exc)
    else:
        raise AssertionError('Changed source relationship was not rejected')


def test_generator_fails_closed_when_schema_column_missing():
    inv, snap = load()
    table = next(t for t in snap['tables'] if t['name'] == 'classes')
    table['columns'] = [c for c in table['columns'] if c['name'] != 'school_id']
    try:
        generate(inv, snap)
    except ValueError as exc:
        assert 'lacks school_id' in str(exc)
    else:
        raise AssertionError('Missing required column was not rejected')
