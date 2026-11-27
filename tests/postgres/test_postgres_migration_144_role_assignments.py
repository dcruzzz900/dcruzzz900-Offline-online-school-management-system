from postgres_migration_144_role_assignments import MIGRATION_VERSION, MIGRATION_NAME, MIGRATION_STATEMENTS, migration

def test_registered_metadata_and_statements():
    m=migration()
    assert m.version == 144
    assert m.name == MIGRATION_NAME == 'create_role_assignments'
    assert len(MIGRATION_STATEMENTS) == 7
    assert 'REFERENCES users(id)' in MIGRATION_STATEMENTS[0]
    assert 'REFERENCES schools(id)' in MIGRATION_STATEMENTS[0]
    assert "CHECK(status IN ('pending','active','rejected','revoked','expired'))" in MIGRATION_STATEMENTS[0]
    assert "CHECK(school_level IN ('All','Nursery','Primary','Secondary'))" in MIGRATION_STATEMENTS[0]

def test_registry_includes_migration_144():
    from postgres_migration_registry import POSTGRES_MIGRATIONS
    assert any(m.version == MIGRATION_VERSION and m.name == MIGRATION_NAME for m in POSTGRES_MIGRATIONS)
