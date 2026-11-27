from postgres_catalog import table_exists, column_names, index_exists

class Row(dict):
    pass

class FakeConnection:
    def __init__(self, one=None, many=None):
        self.one, self.many, self.calls = one, many or [], []
    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self
    def fetchone(self): return self.one
    def fetchall(self): return self.many


def test_table_exists_binds_schema_and_table():
    c = FakeConnection(Row(present=True))
    assert table_exists(c, "students", "tenant_a") is True
    assert c.calls[0][1] == ("tenant_a", "students")
    assert "information_schema.tables" in c.calls[0][0]


def test_column_names_preserve_ordinal_order():
    c = FakeConnection(many=[Row(column_name="id"), Row(column_name="school_id")])
    assert column_names(c, "students") == ["id", "school_id"]
    assert "ORDER BY ordinal_position" in c.calls[0][0]


def test_index_exists_uses_catalog_and_bound_values():
    c = FakeConnection((True,))
    assert index_exists(c, "ix_students_school") is True
    assert c.calls[0][1] == ("public", "ix_students_school")


def test_missing_table_and_index_are_false():
    assert table_exists(FakeConnection((False,)), "missing") is False
    assert index_exists(FakeConnection({"present": False}), "missing") is False
