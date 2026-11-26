#!/usr/bin/env python3
"""Conservative, resumeless SQLite -> PostgreSQL data copier.

Requires a pre-created, PostgreSQL-compatible schema. Dry-run is the default.
The tool refuses non-empty target tables and never drops/truncates data.
Use --apply only during a controlled cutover with a verified backup.
"""
from __future__ import annotations
import argparse
import datetime as dt
import decimal
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict, deque
from typing import Any


def qi(identifier: str) -> str:
    """Quote a SQL identifier; identifiers are never accepted as raw SQL."""
    return '"' + identifier.replace('"', '""') + '"'


def canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, memoryview):
        return {"__bytes_hex__": bytes(value).hex()}
    return value


def row_digest(rows) -> str:
    # Order-independent so the digest is stable across SQLite rowid and
    # PostgreSQL physical/primary-key ordering differences.
    payloads = [json.dumps([canonical(v) for v in row], ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"), default=str)
                for row in rows]
    h = hashlib.sha256()
    for payload in sorted(payloads):
        h.update(payload.encode("utf-8")); h.update(b"\n")
    return h.hexdigest()


def sqlite_tables(src):
    return [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def pg_tables(pg):
    with pg.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema() AND table_type='BASE TABLE'")
        return {r[0] for r in cur.fetchall()}


def pg_columns(pg, table):
    with pg.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position", (table,))
        return [r[0] for r in cur.fetchall()]


def pg_count(pg, table):
    with pg.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {qi(table)}")
        return cur.fetchone()[0]


def dependency_order(src, tables):
    """Parent-before-child ordering; reject FK cycles instead of bypassing constraints."""
    table_set = set(tables)
    deps = {t: set() for t in tables}
    for child in tables:
        for row in src.execute(f"PRAGMA foreign_key_list({qi(child)})"):
            parent = row[2]
            if parent in table_set and parent != child:
                deps[child].add(parent)
            elif parent == child:
                deps[child].add(parent)
    ready = deque(sorted(t for t, d in deps.items() if not d))
    ordered = []
    while ready:
        parent = ready.popleft(); ordered.append(parent)
        for child in sorted(deps):
            if parent in deps[child]:
                deps[child].remove(parent)
                if not deps[child] and child not in ordered and child not in ready:
                    ready.append(child)
    if len(ordered) != len(tables):
        cyclic = sorted(t for t in tables if t not in ordered)
        raise RuntimeError("Foreign-key cycle detected; provision DEFERRABLE constraints and handle explicitly: " + ", ".join(cyclic))
    return ordered


def inspect(src, pg):
    tables = sqlite_tables(src)
    missing = sorted(set(tables) - pg_tables(pg))
    if missing:
        raise RuntimeError("Target schema is missing tables: " + ", ".join(missing))
    plan = []
    for table in dependency_order(src, tables):
        src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({qi(table)})")]
        dst_cols = pg_columns(pg, table)
        absent = [c for c in src_cols if c not in dst_cols]
        if absent:
            raise RuntimeError(f"Target table {table} is missing source columns: {', '.join(absent)}")
        count = src.execute(f"SELECT count(*) FROM {qi(table)}").fetchone()[0]
        target_count = pg_count(pg, table)
        if target_count:
            raise RuntimeError(f"Target table {table} is not empty ({target_count} rows); refusing to merge or overwrite")
        plan.append((table, src_cols, count))
    return plan


def transfer(src, pg, plan):
    report = []
    with pg.transaction():
        # Constraints are not disabled. Parent-before-child ordering is enforced above.
        for table, cols, expected_count in plan:
            col_sql = ", ".join(qi(c) for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            insert_sql = f"INSERT INTO {qi(table)} ({col_sql}) VALUES ({placeholders})"
            source_rows = src.execute(f"SELECT {col_sql} FROM {qi(table)}").fetchall()
            before_hash = row_digest(source_rows)
            with pg.cursor() as cur:
                if source_rows:
                    cur.executemany(insert_sql, [tuple(row) for row in source_rows])
                cur.execute(f"SELECT {col_sql} FROM {qi(table)}")
                target_rows = cur.fetchall()
            after_hash = row_digest(target_rows)
            if len(target_rows) != expected_count or before_hash != after_hash:
                raise RuntimeError(f"Verification failed for {table}: source={expected_count}, target={len(target_rows)}, checksum_match={before_hash == after_hash}")
            report.append({"table": table, "rows": expected_count, "sha256": before_hash})
        # Reset serial/identity sequences to at least the copied maximum value.
        with pg.cursor() as cur:
            for table, cols, _ in plan:
                if "id" not in cols:
                    continue
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                seq = cur.fetchone()[0]
                if seq:
                    cur.execute(f"SELECT setval(%s, COALESCE((SELECT MAX({qi('id')}) FROM {qi(table)}), 1), "
                                f"EXISTS (SELECT 1 FROM {qi(table)}))", (seq,))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sqlite", required=True, help="Path to source SQLite database")
    ap.add_argument("--apply", action="store_true", help="Actually copy rows; default is dry-run")
    ap.add_argument("--report", default="sqlite_to_postgres_report.json")
    args = ap.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
    if not dsn:
        ap.error("Set DATABASE_URL or POSTGRES_DSN; credentials must not be placed on the command line")
    if not os.path.isfile(args.sqlite):
        ap.error(f"SQLite file not found: {args.sqlite}")
    try:
        import psycopg
    except ImportError:
        ap.error("Install PostgreSQL dependencies: pip install -r requirements-postgres.txt")
    src = sqlite3.connect(f"file:{os.path.abspath(args.sqlite)}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        with psycopg.connect(dsn) as pg:
            plan = inspect(src, pg)
            print(f"Validated {len(plan)} tables; {sum(x[2] for x in plan)} source rows.")
            for table, _, count in plan:
                print(f"  {table}: {count} rows; target empty; columns compatible")
            if not args.apply:
                print("DRY RUN ONLY. No PostgreSQL data was changed. Re-run with --apply during cutover.")
                return 0
            report = transfer(src, pg, plan)
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump({"source": os.path.abspath(args.sqlite), "tables": report}, f, indent=2)
            print(f"Copied and checksum-verified {sum(x['rows'] for x in report)} rows across {len(report)} tables.")
            print(f"Report: {args.report}")
    finally:
        src.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
