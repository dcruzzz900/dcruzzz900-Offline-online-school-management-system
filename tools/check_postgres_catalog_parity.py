#!/usr/bin/env python3
"""Catalog parity check: SQLite effective-schema snapshot vs. a LIVE PostgreSQL catalog.

Read-only. Connects with psycopg 3, reads pg_catalog / information_schema for one
schema, and compares it with ``postgres_effective_schema_snapshot.json``. It never
creates, alters or deletes anything.

Compared: tables, columns (presence, type family, nullability, defaults, identity),
primary keys, foreign keys (columns, target, ON DELETE), explicit indexes (name,
columns, uniqueness), UNIQUE-constraint counts, trigger names.
NOT compared: CHECK constraints, trigger/function bodies, row data, sequences'
current values. A clean result therefore means "structurally comparable", not "the
application works on PostgreSQL".

Severity: ERROR = structural mismatch that will break or corrupt behaviour,
WARN = differs and needs a human decision, INFO = expected / cosmetic.
Exit codes: 0 no ERROR (and no WARN if --fail-on warn), 2 findings, 3 could not connect/read.

Usage (from the repository root):
    DATABASE_URL=postgresql://user:pw@host/scratchdb python tools/check_postgres_catalog_parity.py \
        --schema public --json-out parity.json --md-out parity.md
Offline re-check of a saved catalog:  --dump-catalog cat.json  then  --catalog-json cat.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Tables that exist in the source on purpose-not-ported / PostgreSQL-only bookkeeping.
EXCLUDED_SOURCE_TABLES = {"schema_steps"}          # see Stage 117
POSTGRES_ONLY_TABLES = {"app_schema_migrations"}   # PostgreSQL runner bookkeeping

TYPE_FAMILIES = {
    "INTEGER": {"integer", "bigint", "smallint"},
    "TEXT": {"text", "character varying", "character"},
    "REAL": {"double precision", "real", "numeric"},
    "BLOB": {"bytea"},
    "NUMERIC": {"numeric", "double precision", "real"},
}
FK_ACTIONS = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}


# --------------------------------------------------------------------------- helpers
def _balanced_outer_parens(s: str) -> bool:
    if not (s.startswith("(") and s.endswith(")")):
        return False
    depth = 0
    for i, ch in enumerate(s):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and i < len(s) - 1:
            return False
    return depth == 0


def norm_default(value: str | None) -> str | None:
    """Normalise a column default so SQLite and PostgreSQL spellings compare equal."""
    if value is None:
        return None
    s = str(value).strip()
    while _balanced_outer_parens(s):
        s = s[1:-1].strip()
    # strip PostgreSQL casts such as 'x'::text, 0::bigint, 'a'::character varying
    s = re.sub(r"::\s*[a-zA-Z_][a-zA-Z0-9_ ]*(\[\])?", "", s)
    while _balanced_outer_parens(s):
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s).lower()
    if s in {"now()", "current_timestamp()", "transaction_timestamp()"}:
        s = "current_timestamp"
    return s


def split_top_level(text: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


_PLAIN_IDENT = re.compile(r'^"?([A-Za-z_][A-Za-z0-9_]*)"?(\s+(ASC|DESC))?(\s+COLLATE\s+\S+)?$', re.I)


def index_columns(raw: str) -> tuple[list[str], bool]:
    """Return (column list, is_plain). Expression elements keep their normalised text."""
    cols, plain = [], True
    for part in split_top_level(raw):
        m = _PLAIN_IDENT.match(part.strip())
        if m:
            cols.append(m.group(1).lower())
        else:
            plain = False
            cols.append(re.sub(r"\s+", " ", part.strip()).lower())
    return cols, plain


_SQLITE_IDX = re.compile(r"ON\s+\"?[A-Za-z0-9_]+\"?\s*\((.*)\)\s*(?:WHERE\s+(.*))?$", re.I | re.S)
_PG_IDX = re.compile(r"USING\s+\w+\s*\((.*)\)\s*(?:WHERE\s+(.*))?$", re.I | re.S)


# --------------------------------------------------------------------------- expected side
def load_expected(snapshot_path: Path) -> dict[str, Any]:
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    idx_sql: dict[str, str] = {}
    triggers: dict[str, str] = {}
    for obj in snap["other_objects"]:
        if obj["type"] == "index":
            idx_sql[obj["name"]] = obj["sql"]
        elif obj["type"] == "trigger":
            triggers[obj["name"]] = obj["table"]

    tables: dict[str, Any] = {}
    for t in snap["tables"]:
        cols = {}
        pk = []
        for c in sorted(t["columns"], key=lambda c: c["cid"]):
            cols[c["name"]] = {
                "type": (c["type"] or "").upper(), "notnull": bool(c["notnull"]),
                "default": c["default"], "pk_pos": c["primary_key_position"], "cid": c["cid"],
            }
            if c["primary_key_position"]:
                pk.append((c["primary_key_position"], c["name"]))
        fks: dict[int, dict[str, Any]] = {}
        for fk in sorted(t["foreign_keys"], key=lambda f: (f["id"], f["sequence"])):
            e = fks.setdefault(fk["id"], {"from": [], "to": [], "table": fk["referenced_table"],
                                          "on_delete": (fk.get("on_delete") or "NO ACTION").upper()})
            e["from"].append(fk["from_column"])
            e["to"].append(fk["to_column"])
        indexes, auto_unique = {}, 0
        for ix in t["indexes"]:
            if ix["origin"] == "c":
                sql = idx_sql.get(ix["name"], "")
                m = _SQLITE_IDX.search(sql.strip().rstrip(";"))
                cols_, plain = index_columns(m.group(1)) if m else ([], False)
                indexes[ix["name"]] = {"unique": bool(ix["unique"]), "cols": cols_, "plain": plain,
                                       "partial": bool(ix["partial"])}
            elif ix["origin"] == "u":
                auto_unique += 1
        tables[t["name"]] = {"columns": cols, "pk": [n for _, n in sorted(pk)],
                             "fks": list(fks.values()), "indexes": indexes,
                             "auto_unique_count": auto_unique}
    # resolve implicit FK targets (to_column NULL means the parent's primary key)
    for t in tables.values():
        for fk in t["fks"]:
            if any(x is None for x in fk["to"]):
                fk["to"] = list(tables.get(fk["table"], {}).get("pk", [])) or fk["to"]
    return {"tables": tables, "triggers": triggers, "counts": snap.get("counts", {})}


# --------------------------------------------------------------------------- actual side
def read_catalog(conn, schema: str) -> dict[str, Any]:
    """Read the live catalog with a plain psycopg connection (tuple rows)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT c.table_name, c.column_name, c.data_type, c.is_nullable, c.column_default, "
        "c.is_identity, c.ordinal_position FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name "
        "WHERE c.table_schema=%s AND t.table_type='BASE TABLE' ORDER BY c.table_name, c.ordinal_position",
        (schema,))
    tables: dict[str, Any] = {}
    for tname, col, dtype, nullable, default, ident, pos in cur.fetchall():
        tables.setdefault(tname, {"columns": {}, "pk": [], "fks": [], "uniques": [], "indexes": {}})
        tables[tname]["columns"][col] = {"type": dtype, "nullable": nullable == "YES", "default": default,
                                         "identity": ident == "YES", "pos": pos}
    cur.execute(
        "SELECT cl.relname, con.conname, con.contype::text, "
        " ARRAY(SELECT a.attname::text FROM unnest(con.conkey) WITH ORDINALITY k(n, o) "
        "       JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.n ORDER BY k.o), "
        " rcl.relname, "
        " ARRAY(SELECT a.attname::text FROM unnest(con.confkey) WITH ORDINALITY k(n, o) "
        "       JOIN pg_attribute a ON a.attrelid=con.confrelid AND a.attnum=k.n ORDER BY k.o), "
        " con.confdeltype::text "
        "FROM pg_constraint con JOIN pg_class cl ON cl.oid=con.conrelid "
        "JOIN pg_namespace n ON n.oid=cl.relnamespace LEFT JOIN pg_class rcl ON rcl.oid=con.confrelid "
        "WHERE n.nspname=%s AND con.contype IN ('p','f','u')", (schema,))
    for rel, conname, ctype, cols, reftable, refcols, deltype in cur.fetchall():
        t = tables.get(rel)
        if t is None:
            continue
        if ctype == "p":
            t["pk"] = list(cols)
        elif ctype == "u":
            t["uniques"].append({"name": conname, "cols": list(cols)})
        elif ctype == "f":
            t["fks"].append({"name": conname, "from": list(cols), "table": reftable, "to": list(refcols),
                             "on_delete": FK_ACTIONS.get(deltype, deltype)})
    cur.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname=%s", (schema,))
    for tname, iname, idef in cur.fetchall():
        t = tables.get(tname)
        if t is None:
            continue
        m = _PG_IDX.search(idef.strip())
        cols_, plain = index_columns(m.group(1)) if m else ([], False)
        t["indexes"][iname] = {"unique": " UNIQUE INDEX " in idef.upper(), "cols": cols_, "plain": plain,
                               "partial": bool(m and m.group(2)), "def": idef}
    cur.execute(
        "SELECT t.tgname, cl.relname FROM pg_trigger t JOIN pg_class cl ON cl.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=cl.relnamespace WHERE NOT t.tgisinternal AND n.nspname=%s", (schema,))
    triggers = {name: rel for name, rel in cur.fetchall()}
    cur.execute("SHOW server_version")
    version = cur.fetchone()[0]
    return {"schema": schema, "server_version": version, "tables": tables, "triggers": triggers}


# --------------------------------------------------------------------------- comparison
def compare(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(sev: str, kind: str, obj: str, msg: str) -> None:
        findings.append({"severity": sev, "kind": kind, "object": obj, "message": msg})

    etabs, atabs = expected["tables"], actual["tables"]
    for name in sorted(etabs):
        if name in EXCLUDED_SOURCE_TABLES:
            add("INFO", "table_excluded", name, "deliberately not ported (Stage 117)")
            continue
        if name not in atabs:
            add("ERROR", "table_missing", name, "table not present in PostgreSQL")
    for name in sorted(set(atabs) - set(etabs)):
        if name in POSTGRES_ONLY_TABLES:
            add("INFO", "table_postgres_only", name, "PostgreSQL migration bookkeeping")
        else:
            add("WARN", "table_extra", name, "table exists in PostgreSQL but not in the source snapshot")

    for tname in sorted(set(etabs) & set(atabs)):
        et, at = etabs[tname], atabs[tname]
        pk_cols = set(et["pk"])
        for cname, ec in et["columns"].items():
            obj = f"{tname}.{cname}"
            ac = at["columns"].get(cname)
            if ac is None:
                add("ERROR", "column_missing", obj, "column not present in PostgreSQL")
                continue
            fam = TYPE_FAMILIES.get(ec["type"])
            if fam is None:
                add("WARN", "type_unmapped", obj, f"source type {ec['type']!r} has no mapping rule")
            elif ac["type"] not in fam:
                add("ERROR", "type_mismatch", obj, f"source {ec['type']} -> PostgreSQL {ac['type']} "
                                                  f"(accepted: {sorted(fam)})")
            if cname not in pk_cols:
                if ec["notnull"] and ac["nullable"]:
                    add("ERROR", "nullability", obj, "source is NOT NULL, PostgreSQL column is nullable")
                elif not ec["notnull"] and not ac["nullable"]:
                    add("WARN", "nullability", obj, "source is nullable, PostgreSQL column is NOT NULL")
            ed, ad = norm_default(ec["default"]), norm_default(ac["default"])
            auto = ac["identity"] or (ad or "").startswith("nextval(")
            if ed is None and ad is not None and not auto:
                add("WARN", "default_extra", obj, f"PostgreSQL has default {ad!r}; source has none")
            elif ed is not None and ad is None:
                add("ERROR", "default_missing", obj, f"source default {ed!r} missing in PostgreSQL")
            elif ed is not None and ed != ad:
                add("WARN", "default_differs", obj, f"source {ed!r} vs PostgreSQL {ad!r}")
            if cname in pk_cols and len(et["pk"]) == 1 and ec["type"] == "INTEGER" and not auto:
                add("WARN", "pk_not_generated", obj,
                    "single INTEGER primary key has no identity/serial; inserts must supply ids")
        for cname in sorted(set(at["columns"]) - set(et["columns"])):
            add("WARN", "column_extra", f"{tname}.{cname}", "column exists in PostgreSQL but not in the source")
        shared = [c for c in sorted(et["columns"], key=lambda c: et["columns"][c]["cid"]) if c in at["columns"]]
        if shared != sorted(shared, key=lambda c: at["columns"][c]["pos"]):
            add("INFO", "column_order", tname, "physical column order differs from the source")

        if et["pk"] != at["pk"]:
            add("ERROR", "pk_mismatch", tname, f"source PK {et['pk']} vs PostgreSQL PK {at['pk']}")

        efk = {(tuple(f["from"]), f["table"], tuple(f["to"])): f for f in et["fks"]}
        afk = {(tuple(f["from"]), f["table"], tuple(f["to"])): f for f in at["fks"]}
        for key, f in efk.items():
            if key not in afk:
                add("ERROR", "fk_missing", tname, f"FK {list(key[0])} -> {key[1]}{list(key[2])} missing")
            elif f["on_delete"] != afk[key]["on_delete"]:
                add("WARN", "fk_on_delete", tname, f"FK {list(key[0])}: source ON DELETE {f['on_delete']} vs "
                                                   f"PostgreSQL {afk[key]['on_delete']}")
        for key in set(afk) - set(efk):
            add("WARN", "fk_extra", tname, f"FK {list(key[0])} -> {key[1]}{list(key[2])} not in the source")

        used = set()
        for iname, ei in et["indexes"].items():
            ai = at["indexes"].get(iname)
            if ai is None:
                twin = next((n for n, x in at["indexes"].items() if n not in used and x["unique"] == ei["unique"]
                             and x["cols"] == ei["cols"]), None)
                if twin:
                    used.add(twin)
                    add("INFO", "index_renamed", f"{tname}.{iname}", f"present as {twin}")
                else:
                    add("ERROR", "index_missing", f"{tname}.{iname}",
                        f"{'UNIQUE ' if ei['unique'] else ''}index on {ei['cols']} missing")
                continue
            used.add(iname)
            if ei["unique"] != ai["unique"]:
                add("ERROR", "index_uniqueness", f"{tname}.{iname}",
                    f"source unique={ei['unique']} vs PostgreSQL unique={ai['unique']}")
            if ei["plain"] and ai["plain"] and ei["cols"] != ai["cols"]:
                add("ERROR", "index_columns", f"{tname}.{iname}", f"source {ei['cols']} vs PostgreSQL {ai['cols']}")
            elif not (ei["plain"] and ai["plain"]):
                add("INFO", "index_expression", f"{tname}.{iname}", "expression index: existence checked, not text")
            if ei["partial"] != ai["partial"]:
                add("WARN", "index_partial", f"{tname}.{iname}",
                    f"source partial={ei['partial']} vs PostgreSQL partial={ai['partial']}")
        if et["auto_unique_count"] != len(at["uniques"]):
            add("WARN", "unique_count", tname, f"source has {et['auto_unique_count']} UNIQUE constraint index(es); "
                                               f"PostgreSQL has {len(at['uniques'])} UNIQUE constraint(s) "
                                               "(may be implemented as plain unique indexes)")

    missing_trg = sorted(set(expected["triggers"]) - set(actual["triggers"]))
    if missing_trg:
        add("WARN", "trigger_names_missing", "triggers",
            f"{len(missing_trg)} of {len(expected['triggers'])} source trigger names have no same-named PostgreSQL "
            f"trigger (ports may be renamed or consolidated; first 10: {missing_trg[:10]})")
    else:
        add("INFO", "trigger_names_ok", "triggers", "all source trigger names are present")
    add("INFO", "trigger_counts", "triggers",
        f"source {len(expected['triggers'])} vs PostgreSQL {len(actual['triggers'])} (bodies not compared)")
    return findings


def summarise(findings: list[dict[str, str]]) -> dict[str, int]:
    out = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for f in findings:
        out[f["severity"]] += 1
    return out


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = ["# PostgreSQL catalog parity report", "",
             f"- Server: `{report.get('server_version', 'unknown')}`  Schema: `{report.get('schema')}`",
             f"- Source tables: {report['source_tables']}  PostgreSQL tables: {report['actual_tables']}",
             f"- **ERROR {s['ERROR']}**  WARN {s['WARN']}  INFO {s['INFO']}", "",
             "Not compared: CHECK constraints, trigger/function bodies, row data.", ""]
    for sev in ("ERROR", "WARN", "INFO"):
        rows = [f for f in report["findings"] if f["severity"] == sev]
        if not rows:
            continue
        lines += [f"## {sev} ({len(rows)})", ""]
        lines += [f"- `{f['kind']}` **{f['object']}** - {f['message']}" for f in rows]
        lines.append("")
    return "\n".join(lines)


def build_report(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    findings = compare(expected, actual)
    return {"schema": actual.get("schema"), "server_version": actual.get("server_version"),
            "source_tables": len(expected["tables"]), "actual_tables": len(actual["tables"]),
            "summary": summarise(findings), "findings": findings}


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN"))
    ap.add_argument("--schema", default="public")
    ap.add_argument("--snapshot", default=str(ROOT / "postgres_effective_schema_snapshot.json"))
    ap.add_argument("--json-out")
    ap.add_argument("--md-out")
    ap.add_argument("--dump-catalog", help="save the raw live catalog as JSON (re-check later with --catalog-json)")
    ap.add_argument("--catalog-json", help="compare a previously dumped catalog instead of connecting")
    ap.add_argument("--fail-on", choices=("error", "warn"), default="error")
    args = ap.parse_args(argv)

    expected = load_expected(Path(args.snapshot))
    try:
        if args.catalog_json:
            actual = json.loads(Path(args.catalog_json).read_text(encoding="utf-8"))
        else:
            if not args.dsn:
                ap.error("set DATABASE_URL (or pass --dsn) or use --catalog-json")
            import psycopg  # lazy: SQLite-only installs do not need it
            with psycopg.connect(args.dsn, connect_timeout=10) as conn:
                conn.read_only = True
                actual = read_catalog(conn, args.schema)
    except Exception as exc:  # connection / permission / missing driver
        print(f"cannot read PostgreSQL catalog: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    if args.dump_catalog:
        Path(args.dump_catalog).write_text(json.dumps(actual, indent=1, default=str), encoding="utf-8")

    report = build_report(expected, actual)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    md = render_markdown(report)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    print(md)
    s = report["summary"]
    return 2 if s["ERROR"] or (args.fail_on == "warn" and s["WARN"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
