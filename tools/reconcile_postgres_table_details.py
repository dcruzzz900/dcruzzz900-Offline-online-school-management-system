#!/usr/bin/env python3
"""Build a detailed, conservative table-level PostgreSQL gap report.

Compares the effective SQLite schema inventory with explicit CREATE TABLE
statements in the PostgreSQL baseline and numbered PostgreSQL migrations.
References from helper/trigger files are recorded separately and never count as
proof that a table is created. This tool does not execute or modify migrations.
"""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "postgres_effective_schema_snapshot.json"
BASE = ROOT / "postgres_schema_base.sql"
OUT_JSON = ROOT / "POSTGRES_TABLE_GAP_DETAILS_STAGE80.json"
OUT_MD = ROOT / "POSTGRES_TABLE_GAP_DETAILS_STAGE80.md"
# Tables that exist in the effective SQLite schema but are deliberately NOT ported, with the
# reason. An entry must name a real snapshot table and must not also have an explicit
# PostgreSQL CREATE TABLE; otherwise build() raises, so a stale exclusion cannot hide a gap.
EXCLUDED_TABLES = {
    "schema_steps": (
        "SQLite's own named-migration bookkeeping (read and written only by the SQLite migration "
        "runner in db.py). PostgreSQL tracks applied migrations in its own app_schema_migrations "
        "table, which carries a checksum per migration."
    ),
}
CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([A-Za-z_]\w*)", re.I)

def build() -> dict:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    tables = {t["name"]: t for t in snapshot["tables"]}
    ddl_files = [BASE, *sorted(ROOT.glob("postgres_migration_[0-9]*.py"))]
    all_pg_files = [*ddl_files, *sorted(ROOT.glob("postgres_*.sql")), *sorted((ROOT / "tools").glob("*.py"))]
    creates: dict[str, list[str]] = {}
    for path in ddl_files:
        source = path.read_text(encoding="utf-8")
        for match in CREATE_RE.finditer(source):
            creates.setdefault(match.group(1), []).append(path.name)
    unknown = sorted(set(EXCLUDED_TABLES) - set(tables))
    if unknown:
        raise ValueError(f"EXCLUDED_TABLES names tables not in the effective schema: {unknown}")
    rows = []
    excluded = []
    for name, table in sorted(tables.items()):
        if name in creates:
            if name in EXCLUDED_TABLES:
                raise ValueError(f"{name} is listed in EXCLUDED_TABLES but has an explicit PostgreSQL CREATE TABLE")
            continue
        if name in EXCLUDED_TABLES:
            excluded.append({
                "table": name,
                "column_count": len(table["columns"]),
                "index_count": len(table["indexes"]),
                "reason": EXCLUDED_TABLES[name],
            })
            continue
        refs = []
        for path in all_pg_files:
            source = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\b" + re.escape(name) + r"\b", source, re.I):
                refs.append(path.name if path.parent == ROOT else f"{path.parent.name}/{path.name}")
        rows.append({
            "table": name,
            "column_count": len(table["columns"]),
            "columns": table["columns"],
            "foreign_key_count": len(table["foreign_keys"]),
            "foreign_keys": table["foreign_keys"],
            "index_count": len(table["indexes"]),
            "indexes": table["indexes"],
            "sqlite_create_sql": table["create_sql"],
            "postgres_non_ddl_references": refs,
            "classification": "NO_EXPLICIT_POSTGRES_CREATE_TABLE_FOUND",
        })
    return {
        "stage": 80,
        "source_schema_version": snapshot["migration_state"]["schema_version"],
        "source_table_count": snapshot["counts"]["tables"],
        "postgres_explicit_create_table_coverage": snapshot["counts"]["tables"] - len(rows) - len(excluded),
        "deliberately_excluded_table_count": len(excluded),
        "deliberately_excluded_tables": excluded,
        "unresolved_table_candidate_count": len(rows),
        "unresolved_column_count": sum(r["column_count"] for r in rows),
        "unresolved_foreign_key_declaration_count": sum(r["foreign_key_count"] for r in rows),
        "unresolved_index_count": sum(r["index_count"] for r in rows),
        "live_postgres_catalog_checked": False,
        "rows": rows,
        "limitations": [
            "A missing explicit CREATE TABLE match is a confirmed source-to-file DDL gap, not proof that a live PostgreSQL database lacks the table.",
            "The scan records references in helper and trigger files separately; references do not create tables.",
            "Column type/nullability/default equivalence for the 76 explicitly matched tables is not assessed by this stage.",
            "SQLite trigger semantics, application SQL compatibility, and live PostgreSQL execution remain outside this static report.",
        ],
    }

def render(data: dict) -> str:
    lines = [
        f"# Stage {data['stage']} — Detailed PostgreSQL Table Gap Report", "",
        f"- Source schema version: **{data['source_schema_version']}**",
        f"- Required source tables: **{data['source_table_count']}**",
        f"- Tables with explicit PostgreSQL CREATE TABLE: **{data['postgres_explicit_create_table_coverage']}**",
        f"- Tables deliberately excluded (not to be ported): **{data['deliberately_excluded_table_count']}**",
        f"- Tables without explicit PostgreSQL CREATE TABLE: **{data['unresolved_table_candidate_count']}**",
        f"- Columns in unresolved tables: **{data['unresolved_column_count']}**",
        f"- Foreign-key declarations in unresolved tables: **{data['unresolved_foreign_key_declaration_count']}**",
        f"- Indexes in unresolved tables: **{data['unresolved_index_count']}**", "",
        "## Table-by-table findings", "",
        "These are source tables for which no explicit CREATE TABLE statement was found in the numbered PostgreSQL migration files or `postgres_schema_base.sql`. A reference from a trigger/helper file is not counted as table creation.", "",
        "| Table | Columns | FKs | Indexes | Other PostgreSQL references |", "|---|---:|---:|---:|---|",
    ]
    for row in data["rows"]:
        refs = ", ".join(f"`{r}`" for r in row["postgres_non_ddl_references"]) or "None found"
        lines.append(f"| `{row['table']}` | {row['column_count']} | {row['foreign_key_count']} | {row['index_count']} | {refs} |")
    if not data["rows"]:
        lines.append("| _none_ | 0 | 0 | 0 | |")
    if data["deliberately_excluded_tables"]:
        lines += ["", "## Deliberately excluded tables", "",
                  "These source tables are intentionally not ported. Each exclusion is declared in `EXCLUDED_TABLES` with a reason, and the report fails if an excluded table does not exist or later gains an explicit PostgreSQL CREATE TABLE.", "",
                  "| Table | Columns | Indexes | Reason |", "|---|---:|---:|---|"]
        for row in data["deliberately_excluded_tables"]:
            lines.append(f"| `{row['table']}` | {row['column_count']} | {row['index_count']} | {row['reason']} |")
    if data["rows"]:
        interp = f"The table-level result is a concrete file-level gap list: **{data['unresolved_table_candidate_count']} source tables / {data['unresolved_column_count']} columns** have no explicit PostgreSQL table-creation statement in the scanned baseline and migration files. The report also inventories source foreign keys, indexes, and non-DDL references."
        caveat = "It is still not a live-catalog result. The listed tables are outstanding PostgreSQL DDL candidates unless another externally provisioned schema mechanism is documented. Do not mark them migrated based only on trigger/helper references."
    else:
        interp = f"Table-level coverage is complete at the file level: every one of the {data['source_table_count']} source tables either has an explicit PostgreSQL CREATE TABLE ({data['postgres_explicit_create_table_coverage']}) or is deliberately excluded with a stated reason ({data['deliberately_excluded_table_count']})."
        caveat = "This is still not a live-catalog result: no explicit CREATE TABLE statement has been executed against a PostgreSQL server, and matching a statement in a file does not prove type, default, constraint or index parity."
    lines += ["", "## Interpretation", "", interp, "", caveat, "",
        "## Scope not yet reconciled", "",
        f"- Column-level parity for the {data['postgres_explicit_create_table_coverage']} tables with explicit CREATE TABLE statements.",
        "- PostgreSQL type, nullability, default, identity, CHECK and UNIQUE parity for every table.",
        "- Foreign-key and index parity for all 113 tables.",
        "- Conversion/validation of all 158 SQLite triggers and any views.",
        "- Application query compatibility and live PostgreSQL catalog/integration tests.", "",
        "## Safety boundary", "",
        "This report is generated from the current PostgreSQL baseline and numbered migrations. It does not change SQLite startup, SQLite migrations, database selection, or offline storage/synchronization. Live PostgreSQL execution has not been performed.", "",
    ]
    return "\n".join(lines)

if __name__ == "__main__":
    data = build()
    OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(render(data), encoding="utf-8")
    print(json.dumps({k: data[k] for k in ("source_table_count", "postgres_explicit_create_table_coverage", "unresolved_table_candidate_count", "unresolved_column_count", "unresolved_foreign_key_declaration_count", "unresolved_index_count")}, indent=2))
