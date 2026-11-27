#!/usr/bin/env python3
"""Live PostgreSQL run of the reviewed migration series on a SCRATCH schema.

What it does (all inside one brand-new schema, so nothing existing is touched):
  1. base      apply postgres_schema_base.sql (24 baseline tables)
  2. migrate   run migrations 100-187 through the real runner (postgres_migrations.py)
  3. rerun     run the runner again; it must apply nothing (checksum/idempotency path)
  4. reapply   call every migration's apply() a second time; each must be idempotent
  5. sql       apply the generated SQL files (defaults, uniqueness, triggers) one by one
  6. probes    a few behavioural checks in a rolled-back transaction
  7. parity    catalog parity against postgres_effective_schema_snapshot.json
and writes live_run_report.json / live_run_report.txt (+ parity files) to --out-dir.

Safety: refuses to run without --confirm-scratch, refuses an existing schema, never
drops anything unless --drop-schema is given and then only the schema it created.

Usage (repository root; needs `pip install -r requirements-postgres.txt`):
    DATABASE_URL=postgresql://user:pw@localhost/scratchdb \
        python tools/run_postgres_migrations_live.py --confirm-scratch --out-dir live_run_output
    python tools/run_postgres_migrations_live.py --dry-run        # no database needed
Modes: --mode all   one atomic transaction (production path; reports the first failing version)
       --mode each  one transaction per migration, continues past failures (lists ALL failures)
       --sql-before-sync  also apply the SQL files after migration 183 and again at the end
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

from postgres_migrations import PostgresMigration, run_postgres_migrations  # noqa: E402

SYNC_FIRST_VERSION = 184
# Order follows the dependencies: defaults/uniqueness first, then triggers.
DEFAULT_SQL_FILES = (
    "postgres_timestamp_defaults.sql",
    "postgres_uniqueness.sql",
    "postgres_tenant_triggers.sql",
    "postgres_immutability_triggers.sql",
    "postgres_sync_timestamp_triggers.sql",
    "postgres_tombstone_triggers.sql",
    "postgres_audit_history.sql",
    "postgres_business_rule_triggers.sql",
)


# --------------------------------------------------------------------------- errors / connection
def describe_error(exc: BaseException) -> dict[str, Any]:
    """Pull SQLSTATE/message/hint out of the ORIGINAL psycopg error (the adapter re-raises sqlite3 ones)."""
    orig = exc
    while getattr(orig, "__cause__", None) is not None:
        orig = orig.__cause__
    diag = getattr(orig, "diag", None)
    out = {"type": type(exc).__name__, "message": str(exc).strip()[:1500]}
    if orig is not exc:
        out["original_type"] = type(orig).__name__
    if diag is not None:
        out.update({"sqlstate": getattr(orig, "sqlstate", None), "primary": diag.message_primary,
                    "detail": diag.message_detail, "hint": diag.message_hint,
                    "table": diag.table_name, "constraint": diag.constraint_name,
                    "statement_position": diag.statement_position})
    return {k: v for k, v in out.items() if v not in (None, "")}


class LiveConn:
    """sqlite-style connection (qmark params, hybrid rows) over one raw psycopg connection.

    Reuses the project's own PostgresCursorAdapter, so migrations run through the same
    translation layer the application will use.
    """

    def __init__(self, raw):
        from postgres_dbapi import PostgresCursorAdapter
        self.raw = raw
        self._adapter = PostgresCursorAdapter

    def execute(self, sql, params=None):
        return self._adapter(self.raw.cursor()).execute(sql, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


def quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"unsafe schema name: {name!r}")
    return '"' + name + '"'


# --------------------------------------------------------------------------- stages
class Report:
    def __init__(self):
        self.data: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat(), "stages": []}

    def stage(self, name: str, ok: bool, seconds: float, **details):
        entry = {"stage": name, "ok": ok, "seconds": round(seconds, 3), **details}
        self.data["stages"].append(entry)
        flag = "PASS" if ok else "FAIL"
        extra = details.get("headline", "")
        print(f"[{flag}] {name} ({seconds:.2f}s) {extra}", flush=True)
        return entry


def load_migrations() -> list[PostgresMigration]:
    from postgres_migration_registry import POSTGRES_MIGRATIONS
    return sorted(POSTGRES_MIGRATIONS, key=lambda m: m.version)


def run_script_file(raw, path: Path) -> dict[str, Any]:
    """Execute a whole .sql file in its own transaction via the raw cursor (no placeholder rewriting)."""
    t0 = time.time()
    try:
        raw.cursor().execute(path.read_text(encoding="utf-8"))
        raw.commit()
        return {"file": path.name, "ok": True, "seconds": round(time.time() - t0, 3)}
    except Exception as exc:
        raw.rollback()
        return {"file": path.name, "ok": False, "seconds": round(time.time() - t0, 3), "error": describe_error(exc)}


def migrate(conn: LiveConn, migs: list[PostgresMigration], mode: str) -> dict[str, Any]:
    """Run migrations through the real runner. Returns applied versions and failures."""
    applied: list[int] = []
    failures: list[dict[str, Any]] = []
    timings: dict[int, float] = {}
    if mode == "each":
        for m in migs:
            t0 = time.time()
            try:
                applied += run_postgres_migrations(conn, [m])
            except Exception as exc:
                failures.append({"version": m.version, "name": m.name, "error": describe_error(exc)})
            timings[m.version] = round(time.time() - t0, 3)
        return {"applied": applied, "failures": failures, "timings": timings}

    current = {"v": None, "t": 0.0}

    def wrap(m: PostgresMigration) -> PostgresMigration:
        def apply(c, _m=m):
            current["v"], current["t"] = _m.version, time.time()
            _m.apply(c)
            timings[_m.version] = round(time.time() - current["t"], 3)
        return replace(m, apply=apply)  # same source -> same checksum

    try:
        applied = run_postgres_migrations(conn, [wrap(m) for m in migs])
    except Exception as exc:
        v = current["v"]
        name = next((m.name for m in migs if m.version == v), None)
        failures.append({"version": v, "name": name, "error": describe_error(exc),
                         "note": "atomic mode: the whole transaction was rolled back; nothing is applied"})
    return {"applied": applied, "failures": failures, "timings": timings}


def reapply_each(conn: LiveConn, migs: list[PostgresMigration]) -> list[dict[str, Any]]:
    failures = []
    for m in migs:
        try:
            m.apply(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            failures.append({"version": m.version, "name": m.name, "error": describe_error(exc)})
    return failures


PROBES = (
    ("schools.created_at TEXT default is populated",
     "INSERT INTO schools (name) VALUES ('live-run probe') RETURNING id, created_at",
     lambda rows: rows and rows[0][1] not in (None, "")),
)


def run_probes(conn: LiveConn) -> list[dict[str, Any]]:
    """Behavioural checks; always rolled back. Failures are reported, not fatal."""
    results = []
    try:
        for label, sql, check in PROBES:
            try:
                rows = conn.execute(sql).fetchall()
                results.append({"probe": label, "ok": bool(check(rows))})
            except Exception as exc:
                conn.rollback()
                results.append({"probe": label, "ok": False, "error": describe_error(exc)})
        # sync_changes: the application upserts with ON CONFLICT (school_id, change_id)
        try:
            sid = conn.execute("INSERT INTO schools (name) VALUES ('live-run probe 2') RETURNING id").fetchone()[0]
            up = ("INSERT INTO sync_changes (change_id, school_id, entity) VALUES (?, ?, 'x') "
                  "ON CONFLICT (school_id, change_id) DO UPDATE SET attempts = sync_changes.attempts + 1 "
                  "RETURNING attempts, received_at, state")
            conn.execute(up, ("probe-1", sid)).fetchall()
            row = conn.execute(up, ("probe-1", sid)).fetchone()
            ok = row is not None and row[0] == 2 and row[1] not in (None, "") and row[2] == "applied"
            results.append({"probe": "sync_changes ON CONFLICT(school_id, change_id) upsert", "ok": ok,
                            "observed": [str(x) for x in (row or [])]})
        except Exception as exc:
            results.append({"probe": "sync_changes ON CONFLICT(school_id, change_id) upsert", "ok": False,
                            "error": describe_error(exc)})
    finally:
        conn.rollback()
    return results


# --------------------------------------------------------------------------- dry run
def dry_run(sql_files: list[str]) -> int:
    migs = load_migrations()
    versions = [m.version for m in migs]
    print(f"migrations loaded: {len(migs)} (versions {versions[0]}-{versions[-1]})")
    gaps = sorted(set(range(versions[0], versions[-1] + 1)) - set(versions))
    print(f"version gaps: {gaps or 'none'}   duplicate versions: {len(versions) != len(set(versions))}")
    print(f"every migration has a checksum: {all(len(m.checksum) == 64 for m in migs)}")
    for name in ("postgres_schema_base.sql", *sql_files):
        p = ROOT / name
        print(f"{'ok ' if p.exists() else 'MISSING'} {name}" + (f" ({p.stat().st_size} bytes)" if p.exists() else ""))
    try:
        import psycopg  # noqa: F401
        print("psycopg: installed")
    except ImportError:
        print("psycopg: NOT installed (pip install -r requirements-postgres.txt) - required for a live run")
    return 0 if not gaps and all((ROOT / n).exists() for n in sql_files) else 1


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN"))
    ap.add_argument("--schema", default="live_run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--mode", choices=("all", "each"), default="all")
    ap.add_argument("--sql-files", nargs="*", default=list(DEFAULT_SQL_FILES))
    ap.add_argument("--sql-before-sync", action="store_true",
                    help="apply the SQL files after migration 183, run 184-187, then apply them again")
    ap.add_argument("--skip-sql", action="store_true")
    ap.add_argument("--skip-parity", action="store_true")
    ap.add_argument("--out-dir", default="live_run_output")
    ap.add_argument("--confirm-scratch", action="store_true", help="required: acknowledges this is a scratch database")
    ap.add_argument("--drop-schema", action="store_true", help="drop the created schema at the end")
    ap.add_argument("--dry-run", action="store_true", help="validate inputs only; no database needed")
    args = ap.parse_args(argv)

    if args.dry_run:
        return dry_run(args.sql_files)
    if not args.dsn:
        ap.error("set DATABASE_URL (or pass --dsn)")
    if not args.confirm_scratch:
        ap.error("pass --confirm-scratch to confirm the target database is disposable")
    try:
        import psycopg
        from postgres_dbapi import hybrid_row_factory
    except ImportError as exc:
        print(f"psycopg 3 is required: {exc}. Run: pip install -r requirements-postgres.txt", file=sys.stderr)
        return 3

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = Report()
    schema_q = quote_ident(args.schema)

    try:
        raw = psycopg.connect(args.dsn, row_factory=hybrid_row_factory, prepare_threshold=0,
                              connect_timeout=10, options=f"-c search_path={args.schema}")
    except Exception as exc:
        print(f"cannot connect: {describe_error(exc)}", file=sys.stderr)
        return 3

    exit_code = 0
    try:
        t0 = time.time()
        exists = raw.cursor().execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (args.schema,)).fetchone()
        if exists:
            print(f"schema {args.schema!r} already exists; refusing to reuse it", file=sys.stderr)
            return 3
        raw.cursor().execute(f"CREATE SCHEMA {schema_q}")
        raw.commit()
        version = raw.cursor().execute("SHOW server_version").fetchone()[0]
        rep.data.update({"server_version": version, "schema": args.schema, "mode": args.mode,
                         "psycopg": psycopg.__version__})
        rep.stage("connect", True, time.time() - t0, headline=f"PostgreSQL {version}, schema {args.schema}")

        conn = LiveConn(raw)
        migs = load_migrations()

        t0 = time.time()
        base = run_script_file(raw, ROOT / "postgres_schema_base.sql")
        rep.stage("base", base["ok"], time.time() - t0, result=base,
                  headline="" if base["ok"] else "baseline schema failed; later stages are meaningless")
        if not base["ok"]:
            exit_code = 2
        else:
            sql_paths = [] if args.skip_sql else [ROOT / n for n in args.sql_files]
            if args.sql_before_sync:
                first, second = [m for m in migs if m.version < SYNC_FIRST_VERSION], \
                                [m for m in migs if m.version >= SYNC_FIRST_VERSION]
            else:
                first, second = migs, []

            t0 = time.time()
            res = migrate(conn, first, args.mode)
            if args.sql_before_sync and not res["failures"]:
                mid = [run_script_file(raw, p) for p in sql_paths]
                rep.stage("sql_before_sync", all(r["ok"] for r in mid), 0.0, files=mid)
                res2 = migrate(conn, second, args.mode)
                res["applied"] += res2["applied"]
                res["failures"] += res2["failures"]
                res["timings"].update(res2["timings"])
            ok = not res["failures"]
            slow = sorted(res["timings"].items(), key=lambda kv: -kv[1])[:5]
            rep.stage("migrate", ok, time.time() - t0, applied_count=len(res["applied"]),
                      failures=res["failures"], slowest=slow,
                      headline=f"applied {len(res['applied'])}/{len(migs)}, failures {len(res['failures'])}")
            exit_code = exit_code or (0 if ok else 2)

            if ok:
                t0 = time.time()
                try:
                    again = run_postgres_migrations(conn, migs)
                    rep.stage("rerun_is_noop", again == [], time.time() - t0, applied_on_rerun=again)
                    exit_code = exit_code or (0 if again == [] else 2)
                except Exception as exc:
                    rep.stage("rerun_is_noop", False, time.time() - t0, error=describe_error(exc))
                    exit_code = 2

                t0 = time.time()
                fails = reapply_each(conn, migs)
                rep.stage("reapply_idempotent", not fails, time.time() - t0, failures=fails,
                          headline=f"{len(fails)} migration(s) not re-runnable")
                exit_code = exit_code or (0 if not fails else 2)

                if sql_paths:
                    t0 = time.time()
                    results = [run_script_file(raw, p) for p in sql_paths]
                    bad = [r for r in results if not r["ok"]]
                    rep.stage("sql_files", not bad, time.time() - t0, files=results,
                              headline=f"{len(results) - len(bad)}/{len(results)} files applied")
                    exit_code = exit_code or (0 if not bad else 2)

                t0 = time.time()
                probes = run_probes(conn)
                rep.stage("probes", all(p["ok"] for p in probes), time.time() - t0, probes=probes)
                exit_code = exit_code or (0 if all(p["ok"] for p in probes) else 2)

        if not args.skip_parity:
            t0 = time.time()
            try:
                import check_postgres_catalog_parity as parity
                raw.rollback()
                actual = parity.read_catalog(raw, args.schema)
                report = parity.build_report(parity.load_expected(ROOT / "postgres_effective_schema_snapshot.json"), actual)
                (out_dir / "parity_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
                (out_dir / "parity_report.md").write_text(parity.render_markdown(report), encoding="utf-8")
                (out_dir / "live_catalog.json").write_text(json.dumps(actual, indent=1, default=str), encoding="utf-8")
                s = report["summary"]
                rep.stage("parity", s["ERROR"] == 0, time.time() - t0, summary=s,
                          headline=f"ERROR {s['ERROR']} WARN {s['WARN']} INFO {s['INFO']}")
                exit_code = exit_code or (0 if s["ERROR"] == 0 else 2)
            except Exception as exc:
                rep.stage("parity", False, time.time() - t0, error=describe_error(exc),
                          trace=traceback.format_exc()[-1500:])
                exit_code = exit_code or 2
    finally:
        try:
            raw.rollback()
            if args.drop_schema:
                raw.cursor().execute(f"DROP SCHEMA {schema_q} CASCADE")
                raw.commit()
                rep.data["schema_dropped"] = True
            else:
                print(f"\nschema {args.schema!r} kept for inspection. Drop it with:  DROP SCHEMA {schema_q} CASCADE;")
        finally:
            raw.close()

    rep.data["finished_at"] = datetime.now(timezone.utc).isoformat()
    rep.data["overall_ok"] = exit_code == 0
    (out_dir / "live_run_report.json").write_text(json.dumps(rep.data, indent=1, default=str), encoding="utf-8")
    lines = [f"live run: {'PASS' if exit_code == 0 else 'FAIL'}  server {rep.data.get('server_version')}  "
             f"schema {rep.data.get('schema')}  mode {args.mode}"]
    for st in rep.data["stages"]:
        lines.append(f"  [{'PASS' if st['ok'] else 'FAIL'}] {st['stage']:<20} {st.get('headline', '')}")
        for f in st.get("failures", []) or []:
            lines.append(f"      v{f.get('version')} {f.get('name')}: {f['error'].get('sqlstate', '')} "
                         f"{f['error'].get('primary') or f['error'].get('message')}")
    (out_dir / "live_run_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
