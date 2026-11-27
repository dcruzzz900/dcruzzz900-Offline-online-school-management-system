from postgres_migration_145_role_assignment_permissions import MIGRATION_VERSION, MIGRATION_NAME, MIGRATION_STATEMENTS, migration

def test_metadata_and_ddl():
    m = migration()
    assert m.version == 145
    assert m.name == MIGRATION_NAME == "create_role_assignment_permissions"
    assert len(MIGRATION_STATEMENTS) == 2
    assert "REFERENCES role_assignments(id)" in MIGRATION_STATEMENTS[0]
    assert "permission TEXT NOT NULL" in MIGRATION_STATEMENTS[0]
    assert "granted INTEGER NOT NULL DEFAULT 1" in MIGRATION_STATEMENTS[0]
    assert "idx_role_assignment_permissions_assignment" in MIGRATION_STATEMENTS[1]

def test_registry_includes_migration_145():
    from postgres_migration_registry import POSTGRES_MIGRATIONS
    assert any(m.version == MIGRATION_VERSION and m.name == MIGRATION_NAME for m in POSTGRES_MIGRATIONS)
