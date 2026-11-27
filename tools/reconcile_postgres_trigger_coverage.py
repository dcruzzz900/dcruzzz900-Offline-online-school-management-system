#!/usr/bin/env python3
"""Stage 118: trigger-level coverage reconciliation (static, no database needed).

Maps each of the SQLite triggers in postgres_trigger_porting_plan.json to the PostgreSQL
``CREATE TRIGGER`` statements in the generated postgres_*.sql files, using only explicit,
reviewed rules, and FAILS CLOSED:

  * a source trigger with no mapping, or whose mapped port is on a different table or
    does not cover its event(s) / UPDATE OF columns        -> error
  * a PostgreSQL trigger that no source trigger maps to    -> error (stale/unreviewed port)
  * a trigger's EXECUTE FUNCTION target not defined in any SQL file -> error
  * a trigger on a table that no migration/baseline creates          -> error
  * a consolidation not listed in CONSOLIDATIONS                      -> error

Timing differences (SQLite AFTER INSERT stamping -> PostgreSQL BEFORE INSERT assignment) are
reported as information; they are intentional and documented in the per-category .md files.

This is FILE-LEVEL coverage. It does not prove the trigger bodies behave like the SQLite ones;
that needs the live run (tools/run_postgres_migrations_live.py) and behavioural tests.

Usage:  python tools/reconcile_postgres_trigger_coverage.py [--write] [--stage 118]
  --write   write POSTGRES_TRIGGER_COVERAGE_STAGE<N>.json / .md
Exit code 0 only when there are no errors.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reviewed many-to-one ports. key = PostgreSQL trigger -> the exact set of SQLite triggers it replaces.
CONSOLIDATIONS = {
    "trg_students_tenant_stamp_pg": {"trg_students_tenant_stamp", "trg_students_stamp_tenant"},
}
_SYNC = re.compile(r"^(trg_.+)_sync_(?:defaults|touch)$")

_TRIGGER = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+"?(\w+)"?\s+(BEFORE|AFTER|INSTEAD\s+OF)\s+(.*?)\s+ON\s+"?(\w+)"?'
    r'(.*?)EXECUTE\s+(?:FUNCTION|PROCEDURE)\s+"?(\w+)"?\s*\(', re.I | re.S)
_FUNCTION = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"?(\w+)"?', re.I)


def strip_sql_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def parse_events(clause: str) -> tuple[set[str], set[str]]:
    """'INSERT OR UPDATE OF a, b' -> ({'INSERT','UPDATE'}, {'a','b'}); no columns => all columns."""
    events = set(re.findall(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", clause.upper()))
    cols: set[str] = set()
    m = re.search(r"UPDATE\s+OF\s+(.+?)(?:\s+OR\s+(?:INSERT|DELETE|TRUNCATE)\b|$)", clause, re.I | re.S)
    if m:
        cols = {c.strip().strip('"').lower() for c in m.group(1).split(",") if c.strip()}
    return events, cols


def source_update_columns(value) -> set[str]:
    """The plan stores UPDATE OF columns as 'a, b' (a string); accept a list too."""
    if not value:
        return set()
    items = value.split(",") if isinstance(value, str) else list(value)
    return {str(c).strip().strip('"').lower() for c in items if str(c).strip()}


def load_pg(root: Path) -> tuple[dict[str, dict], set[str]]:
    triggers: dict[str, dict] = {}
    functions: set[str] = set()
    for path in sorted(glob.glob(str(root / "postgres_*.sql"))):
        text = strip_sql_comments(Path(path).read_text(encoding="utf-8"))
        functions |= set(_FUNCTION.findall(text))
        for m in _TRIGGER.finditer(text):
            events, cols = parse_events(m.group(3))
            triggers[m.group(1)] = {"file": Path(path).name, "table": m.group(4), "timing": re.sub(r"\s+", " ", m.group(2).upper()),
                                    "events": sorted(events), "update_of": sorted(cols), "function": m.group(6)}
    return triggers, functions


def created_tables(root: Path) -> set[str]:
    names = set(re.findall(r'CREATE TABLE IF NOT EXISTS\s+"?(\w+)"?', (root / "postgres_schema_base.sql").read_text("utf-8")))
    for p in glob.glob(str(root / "postgres_migration_1*.py")):
        ddl = Path(p).read_text("utf-8").split("\ndef ")[0]
        names |= set(re.findall(r'CREATE TABLE IF NOT EXISTS\s+"?(\w+)"?', ddl))
    return names


def candidates(name: str, pg: dict[str, dict]) -> list[str]:
    """Explicit, reviewed naming rules (no fuzzy matching)."""
    out = []
    if name in pg:
        out.append(name)
    if name + "_pg" in pg:
        out.append(name + "_pg")
    m = _SYNC.match(name)
    if m and m.group(1) + "_sync_timestamp" in pg:
        out.append(m.group(1) + "_sync_timestamp")
    for pgname, sources in CONSOLIDATIONS.items():
        if name in sources and pgname in pg:
            out.append(pgname)
    return list(dict.fromkeys(out))


def reconcile(root: Path = ROOT) -> dict:
    plan = json.loads((root / "postgres_trigger_porting_plan.json").read_text("utf-8"))
    source = {t["name"]: t for t in plan["triggers"]}
    pg, functions = load_pg(root)
    tables = created_tables(root)
    errors: list[dict] = []
    info: list[dict] = []
    mapping: dict[str, list[str]] = {}
    reverse: dict[str, set[str]] = defaultdict(set)

    for name, t in sorted(source.items()):
        c = candidates(name, pg)
        mapping[name] = c
        if len(c) != 1:
            errors.append({"kind": "unmapped_source_trigger" if not c else "ambiguous_mapping", "trigger": name,
                           "table": t["table"], "category": t["category"], "candidates": c})
            continue
        port = pg[c[0]]
        reverse[c[0]].add(name)
        if port["table"] != t["table"]:
            errors.append({"kind": "table_mismatch", "trigger": name, "source_table": t["table"], "pg_table": port["table"]})
        if t["event"] not in port["events"]:
            errors.append({"kind": "event_not_covered", "trigger": name, "source_event": t["event"], "pg_events": port["events"]})
        src_cols = source_update_columns(t.get("updates_of_columns"))
        if src_cols and "UPDATE" in port["events"] and port["update_of"] and not src_cols <= set(port["update_of"]):
            errors.append({"kind": "update_columns_not_covered", "trigger": name,
                           "source_columns": sorted(src_cols), "pg_columns": port["update_of"]})
        if t["timing"] != port["timing"]:
            info.append({"kind": "timing_changed", "trigger": name, "from": t["timing"], "to": port["timing"]})

    for pgname, port in sorted(pg.items()):
        if pgname not in reverse:
            errors.append({"kind": "unmapped_postgres_trigger", "trigger": pgname, "table": port["table"], "file": port["file"]})
        if port["function"] not in functions:
            errors.append({"kind": "function_not_defined", "trigger": pgname, "function": port["function"]})
        if port["table"] not in tables:
            errors.append({"kind": "table_not_created", "trigger": pgname, "table": port["table"]})
    for pgname, expected in CONSOLIDATIONS.items():
        got = reverse.get(pgname, set())
        if got != expected:
            errors.append({"kind": "consolidation_mismatch", "trigger": pgname, "expected": sorted(expected), "mapped": sorted(got)})
    for pgname, srcs in reverse.items():
        if len(srcs) > 1 and pgname not in CONSOLIDATIONS and not all(_SYNC.match(s) for s in srcs):
            errors.append({"kind": "unreviewed_consolidation", "trigger": pgname, "sources": sorted(srcs)})

    by_cat = Counter(t["category"] for t in source.values())
    return {
        "source_trigger_count": len(source), "plan_declared_count": plan["trigger_count"],
        "postgres_trigger_count": len(pg), "postgres_functions": len(functions),
        "mapped_source_triggers": sum(1 for c in mapping.values() if len(c) == 1),
        "unmapped_source_triggers": sum(1 for c in mapping.values() if not c),
        "category_counts": dict(sorted(by_cat.items())),
        "consolidations": {k: sorted(v) for k, v in CONSOLIDATIONS.items()},
        "sync_pairs_consolidated": sum(1 for s in reverse.values() if len(s) == 2 and all(_SYNC.match(x) for x in s)),
        "timing_changes": Counter(f"{i['from']}->{i['to']}" for i in info if i["kind"] == "timing_changed"),
        "mapping": mapping, "errors": errors, "ok": not errors,
    }


def render_md(r: dict, stage: int) -> str:
    lines = [f"# PostgreSQL Trigger Coverage - Stage {stage}", "",
             f"Source (SQLite) triggers: **{r['source_trigger_count']}**  |  PostgreSQL triggers: **{r['postgres_trigger_count']}**  "
             f"|  PostgreSQL functions: {r['postgres_functions']}", "",
             "| Result | Count |", "|---|---:|",
             f"| Source triggers mapped to exactly one port | {r['mapped_source_triggers']} |",
             f"| Source triggers unmapped | {r['unmapped_source_triggers']} |",
             f"| Errors | {len(r['errors'])} |", "",
             "## Source categories", "", "| Category | Count |", "|---|---:|"]
    lines += [f"| `{k}` | {v} |" for k, v in r["category_counts"].items()]
    lines += ["", "## Reviewed consolidations", ""]
    lines += [f"- `{k}` replaces {', '.join('`' + s + '`' for s in v)}" for k, v in r["consolidations"].items()]
    lines += [f"- {r['sync_pairs_consolidated']} pairs of `_sync_defaults` + `_sync_touch` triggers are each replaced by one "
              "`_sync_timestamp` trigger (`INSERT OR UPDATE`).", "", "## Intentional timing changes", ""]
    lines += [f"- {k}: {v} trigger(s)" for k, v in sorted(r["timing_changes"].items())] or ["- none"]
    lines += ["", "## Errors", ""]
    lines += [f"- `{e['kind']}` {json.dumps({k: v for k, v in e.items() if k != 'kind'})}" for e in r["errors"]] or ["None."]
    lines += ["", "## What this does and does not mean", "",
              "Coverage is **file-level only**: every SQLite trigger has an explicit, reviewed PostgreSQL port on the same "
              "table covering the same event, each port's function is defined, and each target table is created by the "
              "baseline or a migration. It does **not** show that any trigger body behaves like its SQLite original, nor that "
              "the SQL files apply on a real server. Run `tools/run_postgres_migrations_live.py` for that.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--stage", type=int, default=118)
    args = ap.parse_args(argv)
    r = reconcile()
    print(render_md(r, args.stage))
    if args.write:
        slim = {k: v for k, v in r.items() if k != "timing_changes"}
        slim["timing_changes"] = dict(r["timing_changes"])
        (ROOT / f"POSTGRES_TRIGGER_COVERAGE_STAGE{args.stage}.json").write_text(json.dumps(slim, indent=1, sort_keys=True) + "\n", "utf-8")
        (ROOT / f"POSTGRES_TRIGGER_COVERAGE_STAGE{args.stage}.md").write_text(render_md(r, args.stage), "utf-8")
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
