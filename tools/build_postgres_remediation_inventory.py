"""Build a source-level PostgreSQL remediation inventory without modifying app code."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.venv', 'venv', '__pycache__', '.pytest_cache', 'tests'}
RULES = {
    'lastrowid': re.compile(r'\.lastrowid\b'),
    'insert_or_ignore_replace': re.compile(r'\bINSERT\s+OR\s+(?:IGNORE|REPLACE)\b', re.I),
    'sqlite_introspection': re.compile(r'sqlite_master|PRAGMA\s+table_info', re.I),
    'sqlite_datetime': re.compile(r"\b(?:datetime|date)\s*\(\s*'now'|\bstrftime\s*\(", re.I),
    'sqlite_trigger_ddl': re.compile(r'\bCREATE\s+TRIGGER\b', re.I),
    'qmark_sql': re.compile(r'\.execute(?:many)?\s*\(\s*(?:f?"|f?\')[^"\']*\?'),
    'case_insensitive_like': re.compile(r'\bLIKE\b', re.I),
    'group_by': re.compile(r'\bGROUP\s+BY\b', re.I),
    'tenant_id_comparison': re.compile(r'\btenant_id\s*=\s*\?', re.I),
}

def source_files():
    # Runtime Python modules only: migration generators, tests and utility
    # scripts have their own SQL dialect and must not inflate app findings.
    yield from sorted(ROOT.glob('*.py'))

def build():
    records=[]; totals={k:0 for k in RULES}
    for path in sorted(source_files()):
        rel=path.relative_to(ROOT).as_posix()
        try: lines=path.read_text(encoding='utf-8').splitlines()
        except UnicodeDecodeError: continue
        for n,line in enumerate(lines,1):
            for category,rx in RULES.items():
                if rx.search(line):
                    totals[category]+=1
                    records.append({'file':rel,'line':n,'category':category,'excerpt':line.strip()[:240]})
    by_file={}
    for item in records:
        by_file.setdefault(item['file'],{}).setdefault(item['category'],0)
        by_file[item['file']][item['category']]+=1
    return {'scope':'Python source excluding tests, virtual environments and caches',
            'categories':totals,'findings':records,'by_file':by_file,
            'limitations':['Regex-based inventory; findings require SQL-context review.',
             'Qmark count is a line-level indicator, not a count of bound parameters.',
             'GROUP BY and LIKE are review candidates, not automatically invalid PostgreSQL SQL.']}

def main():
    data=build()
    (ROOT/'postgres_remediation_inventory.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    rows=['# PostgreSQL application remediation inventory','',
      f"Scope: {data['scope']}.",'',
      'This is a review queue, not evidence that every match is a defect. The SQL adapter already handles positional qmark conversion; dialect-specific constructs and generated IDs still need explicit remediation.','',
      '## Findings by category','', '| Category | Matches |','|---|---:|']
    rows += [f'| `{k}` | {v} |' for k,v in data['categories'].items()]
    rows += ['', '## Highest-volume files','', '| File | Findings |','|---|---:|']
    for f,cats in sorted(data['by_file'].items(),key=lambda x:-sum(x[1].values()))[:20]:
        rows.append(f'| `{f}` | {sum(cats.values())} |')
    rows += ['', '## Required remediation order','',
      '1. Replace application `lastrowid` dependencies with explicit `INSERT ... RETURNING id` and test every insert path.',
      '2. Port SQLite schema introspection and runtime migration execution to the versioned PostgreSQL migration runner.',
      '3. Convert `INSERT OR IGNORE` / `INSERT OR REPLACE` individually after identifying intended conflict keys and delete/replace semantics.',
      '4. Review date/time expressions, trigger DDL, and table rebuild migrations against PostgreSQL equivalents.',
      '5. Review each `LIKE`, `GROUP BY`, and tenant comparison in its query context; preserve case and tenant isolation semantics.',
      '6. Only then enable PostgreSQL selection in `get_db()` behind an explicit deployment setting and run the full application suite against both engines.',
      '', '## Limitations','']
    rows += [f'- {x}' for x in data['limitations']]
    (ROOT/'POSTGRES_REMEDIATION_INVENTORY.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print('PostgreSQL remediation inventory generated')
    for k,v in data['categories'].items(): print(f'{k}: {v}')
    print(f"findings: {len(data['findings'])}")
if __name__=='__main__': main()
