from pathlib import Path

from tools.build_postgres_migration_inventory import build_inventory, extract_registry


def test_registry_extraction_preserves_numbered_and_named_order():
    source = '''\
def first(conn):\n    pass\ndef second(conn):\n    pass\ndef third(conn):\n    pass\nMIGRATIONS = [first, second]\nSTEPS = [("alpha", third)]\nSTEPS.append(("beta", first))\n'''
    tree_source = __import__("ast").parse(source)
    migrations, steps = extract_registry(tree_source)
    assert migrations == ["first", "second"]
    assert steps == [("alpha", "third"), ("beta", "first")]


def test_inventory_reports_sqlite_specific_features_and_source_lines():
    source = '''\
def migration(conn):\n    """Adds a trigger."""\n    conn.execute("CREATE TRIGGER trg AFTER INSERT ON t BEGIN SELECT 1; END")\n    conn.execute("INSERT OR IGNORE INTO t VALUES (?)", (1,))\nMIGRATIONS = [migration]\nSTEPS = [("example", migration)]\n'''
    result = build_inventory(source)
    assert result["registry_counts"] == {"MIGRATIONS": 1, "STEPS": 1}
    assert len(result["entries"]) == 2
    assert result["entries"][0]["features"]["trigger_ddl"] == 1
    assert result["entries"][0]["features"]["sqlite_upsert"] == 1
    assert result["entries"][0]["line_start"] == 1
    assert result["entries"][0]["review_required"] is True


def test_current_v113_registry_is_fully_accounted_for():
    root = Path(__file__).resolve().parents[2]
    inventory = build_inventory((root / "db.py").read_text(encoding="utf-8"))
    assert inventory["registry_counts"]["MIGRATIONS"] == 23
    assert inventory["registry_counts"]["STEPS"] == 76
    assert len(inventory["entries"]) == 99
    assert all(entry["line_start"] <= entry["line_end"] for entry in inventory["entries"])
    assert inventory["scope_warning"].startswith("Static inventory only")
