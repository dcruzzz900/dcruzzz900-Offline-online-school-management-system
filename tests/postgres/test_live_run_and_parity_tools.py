"""Offline tests for tools/run_postgres_migrations_live.py and tools/check_postgres_catalog_parity.py.

No PostgreSQL server is used. The "perfect catalog" below is derived from the SQLite
snapshot itself, so it proves the comparator's normalisation and mutation handling
only; it is NOT evidence that the real migrations match the snapshot.
"""
import copy
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import check_postgres_catalog_parity as parity  # noqa: E402
import run_postgres_migrations_live as live  # noqa: E402
from postgres_migrations import PostgresMigration  # noqa: E402

SNAPSHOT = ROOT / "postgres_effective_schema_snapshot.json"
PG_TYPE = {"INTEGER": "bigint", "TEXT": "text", "REAL": "double precision"}


def perfect_catalog(expected):
    tables = {}
    for name, t in expected["tables"].items():
        if name in parity.EXCLUDED_SOURCE_TABLES:
            continue
        cols = {}
        for cname, c in t["columns"].items():
            is_pk = cname in t["pk"]
            default = c["default"]
            ident = is_pk and len(t["pk"]) == 1 and c["type"] == "INTEGER"
            cols[cname] = {"type": PG_TYPE[c["type"]], "nullable": not (c["notnull"] or is_pk),
                           "default": None if ident else (f"({default})::text" if default and not default[0].isdigit() and default[0] != "'" and default.upper() != "CURRENT_TIMESTAMP" else default),
                           "identity": bool(ident), "pos": c["cid"] + 1}
        tables[name] = {
            "columns": cols, "pk": list(t["pk"]),
            "fks": [{"name": "fk", "from": f["from"], "table": f["table"], "to": f["to"], "on_delete": f["on_delete"]}
                    for f in t["fks"]],
            "uniques": [{"name": f"u{i}", "cols": []} for i in range(t["auto_unique_count"])],
            "indexes": {n: {"unique": i["unique"], "cols": list(i["cols"]), "plain": i["plain"],
                            "partial": i["partial"]} for n, i in t["indexes"].items()},
        }
    tables["app_schema_migrations"] = {"columns": {}, "pk": [], "fks": [], "uniques": [], "indexes": {}}
    return {"schema": "t", "server_version": "test", "tables": tables, "triggers": dict(expected["triggers"])}


def errors(findings):
    return [f for f in findings if f["severity"] == "ERROR"]


def test_norm_default_equivalences():
    assert parity.norm_default("CURRENT_TIMESTAMP") == parity.norm_default("now()") == "current_timestamp"
    assert parity.norm_default("'center'::text") == parity.norm_default("'center'") == "'center'"
    assert parity.norm_default("(0)") == parity.norm_default("0::bigint") == "0"
    assert parity.norm_default(None) is None


def test_index_column_parsing():
    assert parity.index_columns("school_id, received_at") == (["school_id", "received_at"], True)
    cols, plain = parity.index_columns("lower(btrim(admission_no)), class_id")
    assert plain is False and cols[1] == "class_id"


def test_snapshot_loads_with_expected_counts():
    exp = parity.load_expected(SNAPSHOT)
    assert len(exp["tables"]) == 113 and len(exp["triggers"]) == 158
    assert "schema_steps" in exp["tables"]


def test_perfect_catalog_has_no_errors():
    exp = parity.load_expected(SNAPSHOT)
    findings = parity.compare(exp, perfect_catalog(exp))
    assert errors(findings) == [], errors(findings)[:5]
    assert any(f["kind"] == "table_excluded" and f["object"] == "schema_steps" for f in findings)


def test_mutations_are_detected():
    exp = parity.load_expected(SNAPSHOT)
    cat = perfect_catalog(exp)
    bad = copy.deepcopy(cat)
    del bad["tables"]["sync_changes"]["columns"]["attempts"]
    bad["tables"]["schools"]["columns"]["name"]["type"] = "integer"
    bad["tables"]["notifications"]["fks"] = []
    victim = next(n for n, t in exp["tables"].items() if t["indexes"] and n in bad["tables"])
    bad["tables"][victim]["indexes"].clear()
    del bad["tables"]["users"]
    kinds = {(f["kind"]) for f in errors(parity.compare(exp, bad))}
    assert {"column_missing", "type_mismatch", "fk_missing", "index_missing", "table_missing"} <= kinds


def test_extra_and_nullability_findings():
    exp = parity.load_expected(SNAPSHOT)
    cat = perfect_catalog(exp)
    notnull = next((c, n) for n, t in exp["tables"].items() if n in cat["tables"]
                   for c, d in t["columns"].items() if d["notnull"] and c not in t["pk"])
    cat["tables"][notnull[1]]["columns"][notnull[0]]["nullable"] = True
    cat["tables"]["surprise"] = {"columns": {}, "pk": [], "fks": [], "uniques": [], "indexes": {}}
    f = parity.compare(exp, cat)
    assert any(x["kind"] == "nullability" and x["severity"] == "ERROR" for x in f)
    assert any(x["kind"] == "table_extra" and x["object"] == "surprise" for x in f)


def test_dry_run_passes_without_a_database():
    assert live.main(["--dry-run"]) == 0


def test_registry_is_contiguous_100_to_187():
    migs = live.load_migrations()
    assert [m.version for m in migs] == list(range(100, 188))


class FakeCursor:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


class FakeConn:
    def __init__(self):
        self.statements, self.rollbacks, self.commits = [], 0, 0

    def execute(self, sql, params=None):
        self.statements.append(sql)
        return FakeCursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _mig(version, boom=False):
    def apply(conn):
        conn.execute(f"-- {version}")
        if boom:
            raise RuntimeError(f"boom {version}")
    return PostgresMigration(version=version, name=f"m{version}", apply=apply, source=f"src {version}")


def test_migrate_all_mode_reports_the_failing_version_and_rolls_back():
    conn = FakeConn()
    res = live.migrate(conn, [_mig(1), _mig(2, boom=True), _mig(3)], "all")
    assert res["applied"] == [] and res["failures"][0]["version"] == 2
    assert conn.rollbacks >= 1 and res["failures"][0]["error"]["message"] == "boom 2"


def test_migrate_each_mode_continues_past_failures():
    conn = FakeConn()
    res = live.migrate(conn, [_mig(1), _mig(2, boom=True), _mig(3)], "each")
    assert res["applied"] == [1, 3] and [f["version"] for f in res["failures"]] == [2]


def test_describe_error_follows_the_cause_chain():
    class Diag:
        message_primary, message_detail, message_hint = "relation x does not exist", None, "check order"
        table_name, constraint_name, statement_position = None, None, "12"

    class Orig(Exception):
        sqlstate, diag = "42P01", Diag()

    try:
        try:
            raise Orig("original")
        except Orig as o:
            raise ValueError("translated") from o
    except ValueError as e:
        d = live.describe_error(e)
    assert d["sqlstate"] == "42P01" and d["hint"] == "check order" and d["original_type"] == "Orig"


def test_quote_ident_rejects_injection():
    assert live.quote_ident("live_run_1") == '"live_run_1"'
    try:
        live.quote_ident('x"; DROP SCHEMA public; --')
    except ValueError:
        return
    raise AssertionError("unsafe schema name accepted")
