import json
from pathlib import Path


def test_stage83_report_records_current_static_coverage():
    report = json.loads(Path('POSTGRES_RECONCILIATION_STAGE83.json').read_text())
    assert report['stage'] == 83
    assert report['source_table_count'] == 113
    assert report['postgres_explicit_create_table_coverage'] == 79
    assert report['unresolved_table_candidate_count'] == 34
    assert report['unresolved_column_count'] == 471
    assert report['unresolved_foreign_key_declaration_count'] == 36
    assert report['unresolved_index_count'] == 49
    assert report['registry_version_range'] == [100, 154]
    assert report['live_postgres_catalog_checked'] is False
