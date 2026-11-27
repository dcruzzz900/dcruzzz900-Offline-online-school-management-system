from postgres_migration_146_staff_name_history import migration, MIGRATION_STATEMENTS, MIGRATION_VERSION

def test_migration_identity_and_table_statement():
    m = migration()
    assert m.version == 146
    assert "staff_name_history" in MIGRATION_STATEMENTS[0]
    assert "idx_staff_name_history_user" in MIGRATION_STATEMENTS[1]
    assert MIGRATION_VERSION == 146

def test_expected_schema_columns_and_defaults_in_source():
    sql = MIGRATION_STATEMENTS[0]
    for col in ("school_id", "tenant_id", "user_id", "previous_first_name", "new_name", "changed_at", "admin_notified"):
        assert col in sql
    assert "DEFAULT CURRENT_TIMESTAMP" in sql
    assert "DEFAULT 0" in sql
