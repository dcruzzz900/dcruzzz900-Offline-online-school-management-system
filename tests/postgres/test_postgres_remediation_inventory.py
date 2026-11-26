import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'build_postgres_remediation_inventory', ROOT / 'tools' / 'build_postgres_remediation_inventory.py'
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_inventory_scans_runtime_modules_and_excludes_test_tree():
    data = MODULE.build()
    assert data['findings']
    assert all(not item['file'].startswith('tests/') for item in data['findings'])
    assert any(item['file'] == 'app.py' for item in data['findings'])


def test_inventory_reports_known_blocking_patterns():
    data = MODULE.build()
    assert data['categories']['lastrowid'] > 0
    assert data['categories']['insert_or_ignore_replace'] > 0
    assert data['categories']['sqlite_introspection'] > 0
    assert data['categories']['tenant_id_comparison'] > 0


def test_inventory_is_review_queue_not_claim_of_all_matches_being_defects():
    data = MODULE.build()
    assert any('require SQL-context review' in note for note in data['limitations'])
    assert 'by_file' in data and 'findings' in data
