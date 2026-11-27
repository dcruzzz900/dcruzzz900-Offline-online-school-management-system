#!/usr/bin/env python3
"""Static table-DDL coverage scan; findings are candidates, not proof of absence."""
from __future__ import annotations
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
required = json.loads((ROOT / 'postgres_required_schema.json').read_text())['tables']
files = [ROOT / 'postgres_schema_base.sql', *sorted(ROOT.glob('postgres_migration_[0-9]*.py'))]
found = {}
for path in files:
    source = path.read_text(encoding='utf-8')
    for match in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?([A-Za-z_][\\w]*)', source, re.I):
        found.setdefault(match.group(1), []).append(path.name)
matched = sorted(set(required) & set(found))
missing = sorted(set(required) - set(found))
print(json.dumps({'required_tables': len(required), 'explicit_create_table_matches': len(matched), 'manual_review_candidates': missing, 'candidate_count': len(missing), 'warning': 'Static scan only; candidates are not confirmed missing PostgreSQL tables.'}, indent=2))
