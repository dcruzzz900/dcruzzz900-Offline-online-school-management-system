from postgres_migration_147_score_audit import migration, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS


def test_migration_identity_and_objects():
    item = migration()
    assert item.version == 147
    assert item.name == "create_score_audit"
    assert MIGRATION_VERSION == 147
    assert "CREATE TABLE IF NOT EXISTS score_audit" in MIGRATION_STATEMENTS[0]
    assert "idx_score_audit_school" in MIGRATION_STATEMENTS[1]
    assert "idx_score_audit_student" in MIGRATION_STATEMENTS[2]
    assert len(MIGRATION_STATEMENTS) == 7


def test_source_schema_matches_effective_sqlite_definition():
    sql = MIGRATION_STATEMENTS[0]
    assert len(_EXPECTED_COLUMNS) == 32
    for name in ("old_ca1", "old_exam", "old_total", "new_ca1", "new_exam", "new_total", "difference", "changed_at", "result_status", "reason", "source"):
        assert name in sql
    assert "DOUBLE PRECISION" in sql
    assert "DEFAULT CURRENT_TIMESTAMP" in sql


def test_audit_history_is_append_only():
    assert "BEFORE UPDATE" in MIGRATION_STATEMENTS[4]
    assert "BEFORE DELETE" in MIGRATION_STATEMENTS[6]
    assert "app_reject_immutable_row" in MIGRATION_STATEMENTS[4]
    assert "app_reject_immutable_row" in MIGRATION_STATEMENTS[6]
