#!/usr/bin/env python3
"""Generate reviewed PostgreSQL equivalents for SQLite append-only guards.

Only the immutability_guard subset is supported. Unsupported source trigger
syntax fails closed rather than emitting a guessed conversion.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RAISE = re.compile(r"RAISE\s*\(\s*ABORT\s*,\s*'((?:''|[^'])*)'\s*\)", re.I | re.S)
WHEN = re.compile(r"\bWHEN\s+(.*?)\s+BEGIN\b", re.I | re.S)
UPDATE_OF = re.compile(r"\bBEFORE\s+UPDATE\s+OF\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\b", re.I)


def qi(value: str) -> str:
    if not IDENT.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return '"' + value + '"'


def convert_when(condition: str | None) -> str | None:
    if condition is None:
        return None
    s = condition.strip()
    s = re.sub(r"\s*=\s*", " = ", s)
    # These are the only condition forms present in the reviewed guard set.
    s = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+NULL\b",
               r'\1.\2 IS NOT NULL', s, flags=re.I)
    s = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b",
               r'\1.\2 IS DISTINCT FROM \3.\4', s, flags=re.I)
    s = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b",
               r'\1.\2 IS NOT DISTINCT FROM \3.\4', s, flags=re.I)
    if s == "1":
        return "TRUE"
    # Ensure every clause belongs to the small, audited grammar.
    clauses = re.split(r"\s+AND\s+", s, flags=re.I)
    clause_re = re.compile(r"(?:OLD|NEW)\.[A-Za-z_][A-Za-z0-9_]*\s+(?:IS NOT NULL|(?:IS DISTINCT FROM|IS NOT DISTINCT FROM|=)\s+(?:OLD|NEW)\.[A-Za-z_][A-Za-z0-9_]*)", re.I)
    if len(clauses) > 2 or not all(clause_re.fullmatch(c.strip()) for c in clauses):
        raise ValueError(f"Unsupported WHEN condition: {condition!r}")
    return s


def generate(inventory: dict) -> tuple[str, int]:
    selected = [t for t in inventory["triggers"] if t["category"] == "immutability_guard"]
    if not selected:
        raise ValueError("No immutability guards found")
    out = ["-- Generated from the reviewed v113 SQLite immutability guards.",
           "-- Review and apply only after validating the target PostgreSQL schema.",
           "CREATE OR REPLACE FUNCTION app_reject_immutable_row()", "RETURNS trigger", "LANGUAGE plpgsql", "AS $$", "BEGIN",
           "    RAISE EXCEPTION '%', TG_ARGV[0] USING ERRCODE = '55000';", "END;", "$$;", ""]
    for t in selected:
        name, table, event = t["name"], t["table"], t["event"].upper()
        for ident in (name, table): qi(ident)
        if event not in ("UPDATE", "DELETE") or t["timing"].upper() != "BEFORE":
            raise ValueError(f"Unexpected guard timing/event: {name}")
        source = t["source_sql"]
        m = RAISE.search(source)
        if not m:
            raise ValueError(f"No supported RAISE(ABORT, message) in {name}")
        message = m.group(1).replace("''", "'")
        wm = WHEN.search(source)
        condition = convert_when(wm.group(1)) if wm else None
        cols = None
        if t.get("updates_of_columns"):
            cols = t["updates_of_columns"].split(",")
            if len(cols) != 1:
                raise ValueError(f"Unsupported UPDATE OF list in {name}")
            event_sql = f"UPDATE OF {qi(cols[0])}"
        else:
            event_sql = event
        out.append(f"DROP TRIGGER IF EXISTS {qi(name)} ON {qi(table)};")
        stmt = f"CREATE TRIGGER {qi(name)} BEFORE {event_sql} ON {qi(table)}"
        if condition:
            stmt += f"\n    FOR EACH ROW WHEN ({condition})"
        else:
            stmt += "\n    FOR EACH ROW"
        # PostgreSQL trigger arguments are string literals; escape apostrophes.
        stmt += f"\n    EXECUTE FUNCTION app_reject_immutable_row('{message.replace(chr(39), chr(39)*2)}');"
        out.append(stmt)
        out.append("")
    return "\n".join(out).rstrip() + "\n", len(selected)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default="postgres_trigger_porting_plan.json")
    ap.add_argument("--output", default="postgres_immutability_triggers.sql")
    args = ap.parse_args()
    inv = json.loads(Path(args.inventory).read_text())
    sql, count = generate(inv)
    Path(args.output).write_text(sql)
    print(f"Generated {count} immutability triggers: {args.output}")

if __name__ == "__main__": main()
