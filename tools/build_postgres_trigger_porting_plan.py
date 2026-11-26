#!/usr/bin/env python3
"""Create a reviewable PostgreSQL trigger-porting plan from the effective SQLite snapshot.

This tool does not translate trigger SQL. It classifies trigger intent and preserves
source SQL for a developer to implement and verify as PostgreSQL functions/triggers.
"""
from __future__ import annotations
import argparse, json, re
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'postgres_effective_schema_snapshot.json'
OUT_JSON = ROOT / 'postgres_trigger_porting_plan.json'
OUT_MD = ROOT / 'POSTGRES_TRIGGER_PORTING_PLAN.md'

def classify(name: str, sql: str) -> str:
    s = (name + ' ' + sql).lower()
    if 'no_delete' in s or 'no_update' in s or 'append-only' in s or 'immutable' in s:
        return 'immutability_guard'
    if 'tombstone' in s or 'after delete' in s:
        return 'soft_delete_or_sync_tombstone'
    if 'tenant_stamp' in s or 'tenant_id' in s:
        return 'tenant_scope_propagation'
    if 'sync_touch' in s or 'updated_at' in s:
        return 'offline_sync_timestamp'
    if 'sync_defaults' in s or 'client_uuid' in s:
        return 'offline_sync_defaults'
    if 'history' in s:
        return 'audit_or_history_capture'
    if 'unique' in s or 'identity' in s:
        return 'cross_row_uniqueness'
    return 'business_rule_or_other'

def build(snapshot: dict) -> dict:
    triggers = []
    for obj in snapshot.get('other_objects', []):
        if obj.get('type') != 'trigger':
            continue
        sql = obj.get('sql') or ''
        triggers.append({
            'name': obj['name'], 'table': obj.get('table'),
            'category': classify(obj['name'], sql),
            'timing': (re.search(r'\b(BEFORE|AFTER|INSTEAD OF)\b', sql, re.I) or [None, 'UNKNOWN'])[1].upper(),
            'event': (re.search(r'\b(INSERT|UPDATE|DELETE)\b', sql, re.I) or [None, 'UNKNOWN'])[1].upper(),
            'updates_of_columns': (re.search(r'\bUPDATE\s+OF\s+(.+?)\s+ON\b', sql, re.I|re.S).group(1).strip() if re.search(r'\bUPDATE\s+OF\s+(.+?)\s+ON\b', sql, re.I|re.S) else None),
            'uses_old': bool(re.search(r'\bOLD\.', sql, re.I)),
            'uses_new': bool(re.search(r'\bNEW\.', sql, re.I)),
            'uses_raise_abort': bool(re.search(r'RAISE\s*\(\s*ABORT', sql, re.I)),
            'source_sql': sql,
            'porting_note': 'Implement as a PostgreSQL trigger function and CREATE TRIGGER; preserve ordering, row scope, NULL semantics, and transaction behaviour. Review manually.'
        })
    counts = Counter(t['category'] for t in triggers)
    return {'source':'postgres_effective_schema_snapshot.json','trigger_count':len(triggers),
            'category_counts':dict(sorted(counts.items())), 'triggers':triggers,
            'safety_note':'Inventory only. No SQLite trigger body has been mechanically converted or declared PostgreSQL-ready.'}

def markdown(plan: dict) -> str:
    lines=['# PostgreSQL Trigger Porting Plan','', '> Review inventory generated from the effective v113 SQLite schema. This is not executable PostgreSQL trigger SQL.','',f"**Total triggers:** {plan['trigger_count']}",'','## Categories','', '| Category | Count |','|---|---:|']
    for k,v in plan['category_counts'].items(): lines.append(f'| `{k}` | {v} |')
    lines += ['', '## Trigger-by-trigger review', '', '| Trigger | Table | Category | Timing | Event | OLD | NEW | RAISE(ABORT) |','|---|---|---|---|---|---:|---:|---:|']
    for t in plan['triggers']:
        lines.append(f"| `{t['name']}` | `{t['table']}` | `{t['category']}` | {t['timing']} | {t['event']} | {'yes' if t['uses_old'] else 'no'} | {'yes' if t['uses_new'] else 'no'} | {'yes' if t['uses_raise_abort'] else 'no'} |")
    lines += ['', '## Conversion rules', '', '- Convert each trigger into a PostgreSQL PL/pgSQL function plus a trigger declaration.', '- Replace SQLite `RAISE(ABORT, ...)` with an appropriate PostgreSQL exception (`RAISE EXCEPTION`) and preserve user-facing error meaning.', '- Re-evaluate `IS` / `IS NOT` comparisons, empty-string checks, and NULL handling under PostgreSQL semantics.', '- Review `AFTER` triggers that update the same row; prefer `BEFORE` triggers that assign `NEW.column` where equivalent and safe.', '- Ensure tenant stamping cannot infer a tenant from an ambiguous parent row; enforce tenant consistency with constraints and explicit application context.', '- Preserve tombstone and audit/history behaviour, including append-only guarantees.', '- Add integration tests for every trigger before production cutover.', '', '**Do not apply this inventory as SQL.** Trigger bodies remain unconverted until reviewed and tested against PostgreSQL.','']
    return '\n'.join(lines)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',type=Path,default=SOURCE); ap.add_argument('--json',type=Path,default=OUT_JSON); ap.add_argument('--markdown',type=Path,default=OUT_MD); a=ap.parse_args()
    plan=build(json.loads(a.source.read_text(encoding='utf-8')))
    a.json.write_text(json.dumps(plan,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    a.markdown.write_text(markdown(plan),encoding='utf-8')
    print(json.dumps({'trigger_count':plan['trigger_count'],'category_counts':plan['category_counts']},sort_keys=True))
if __name__=='__main__': main()
