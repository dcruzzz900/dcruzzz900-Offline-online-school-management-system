"""Stage 118: trigger coverage reconciliation is complete and fails closed."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import reconcile_postgres_trigger_coverage as rc  # noqa: E402


def _copy_repo_inputs():
    tmp = Path(tempfile.mkdtemp())
    for f in list(ROOT.glob("postgres_*.sql")) + list(ROOT.glob("postgres_migration_1*.py")) + [
            ROOT / "postgres_trigger_porting_plan.json"]:
        shutil.copy(f, tmp / f.name)
    return tmp


def _kinds(result):
    return {e["kind"] for e in result["errors"]}


def test_repository_state_is_fully_covered():
    r = rc.reconcile(ROOT)
    assert r["ok"], r["errors"][:3]
    assert r["source_trigger_count"] == r["plan_declared_count"] == 158
    assert r["mapped_source_triggers"] == 158 and r["unmapped_source_triggers"] == 0
    assert r["postgres_trigger_count"] == 121 and r["sync_pairs_consolidated"] == 36


def test_committed_report_matches_a_fresh_run():
    committed = json.loads((ROOT / "POSTGRES_TRIGGER_COVERAGE_STAGE118.json").read_text("utf-8"))
    fresh = rc.reconcile(ROOT)
    assert committed["mapping"] == fresh["mapping"] and committed["ok"] is True


def test_students_tenant_triggers_are_a_reviewed_consolidation():
    r = rc.reconcile(ROOT)
    assert r["mapping"]["trg_students_tenant_stamp"] == r["mapping"]["trg_students_stamp_tenant"] == ["trg_students_tenant_stamp_pg"]


def test_update_columns_accept_string_or_list():
    assert rc.source_update_columns("admission_no, class_id") == {"admission_no", "class_id"}
    assert rc.source_update_columns(["A"]) == {"a"} and rc.source_update_columns(None) == set()


def test_missing_port_fails_closed():
    tmp = _copy_repo_inputs()
    f = tmp / "postgres_immutability_triggers.sql"
    f.write_text(f.read_text("utf-8").replace("trg_audit_log_no_delete", "trg_renamed_elsewhere"), "utf-8")
    kinds = _kinds(rc.reconcile(tmp))
    assert "unmapped_source_trigger" in kinds and "unmapped_postgres_trigger" in kinds


def test_wrong_table_or_undefined_function_fails_closed():
    tmp = _copy_repo_inputs()
    f = tmp / "postgres_tombstone_triggers.sql"
    text = f.read_text("utf-8")
    f.write_text(text.replace("EXECUTE FUNCTION app_record_sync_tombstone", "EXECUTE FUNCTION app_missing_fn", 1), "utf-8")
    assert "function_not_defined" in _kinds(rc.reconcile(tmp))


def test_narrowed_update_of_columns_fail_closed():
    tmp = _copy_repo_inputs()
    f = tmp / "postgres_uniqueness.sql"
    f.write_text(f.read_text("utf-8").replace("UPDATE OF admission_no, class_id", "UPDATE OF admission_no"), "utf-8")
    assert "update_columns_not_covered" in _kinds(rc.reconcile(tmp))


def test_trigger_on_uncreated_table_fails_closed():
    tmp = _copy_repo_inputs()
    f = tmp / "postgres_business_rule_triggers.sql"
    f.write_text(f.read_text("utf-8").replace("UPDATE OF school_code ON schools", "UPDATE OF school_code ON ghost_table"), "utf-8")
    kinds = _kinds(rc.reconcile(tmp))
    assert {"table_not_created", "table_mismatch"} <= kinds
