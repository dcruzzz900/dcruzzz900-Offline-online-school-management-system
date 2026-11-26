#!/usr/bin/env python3
"""Extract the real ordered SQLite migration registry for PostgreSQL port planning.

This is an inventory only. It does not execute, translate, or claim to port migrations.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "db.py"
DEFAULT_OUTPUT = ROOT / "postgres_migration_inventory.json"

PATTERNS = {
    "sqlite_catalog": r"sqlite_master|sqlite_temp_master",
    "pragma": r"\bPRAGMA\b|table_info\s*\(",
    "trigger_ddl": r"\bCREATE\s+(?:TEMP\s+)?TRIGGER\b",
    "rowid": r"\browid\b|\b_lastrowid\b",
    "lastrowid": r"\.lastrowid\b",
    "executescript": r"\.executescript\s*\(",
    "sqlite_upsert": r"\bINSERT\s+OR\s+(?:IGNORE|REPLACE)\b",
    "sqlite_date_functions": r"\b(?:date|datetime|strftime|julianday)\s*\(",
    "table_rebuild": r"\bALTER\s+TABLE\b.*\bRENAME\s+TO\b",
    "ensure_column": r"\bensure_column\s*\(",
}


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def extract_registry(tree: ast.Module) -> tuple[list[str], list[tuple[str, str]]]:
    migrations: list[str] = []
    steps: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(_name(t) == "MIGRATIONS" for t in node.targets):
            if isinstance(node.value, ast.List):
                migrations = [elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
        if isinstance(node, ast.Assign) and any(_name(t) == "STEPS" for t in node.targets):
            if isinstance(node.value, ast.List):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Tuple) and len(elt.elts) == 2:
                        a, b = elt.elts
                        if isinstance(a, ast.Constant) and isinstance(a.value, str) and isinstance(b, ast.Name):
                            steps.append((a.value, b.id))
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "STEPS" and call.func.attr == "append" and call.args:
                arg = call.args[0]
                if isinstance(arg, ast.Tuple) and len(arg.elts) == 2:
                    a, b = arg.elts
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and isinstance(b, ast.Name):
                        steps.append((a.value, b.id))
    return migrations, steps


def build_inventory(source: str) -> dict:
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    migrations, steps = extract_registry(tree)
    if not migrations or not steps:
        raise ValueError("Could not locate both MIGRATIONS and STEPS registries in db.py")

    def entry(registry: str, order: int, key: str, fn_name: str) -> dict:
        fn = functions.get(fn_name)
        if fn is None:
            raise ValueError(f"Registered migration function not found: {fn_name}")
        source_text = ast.get_source_segment(source, fn) or ""
        doc = ast.get_docstring(fn) or ""
        features = {name: len(re.findall(pattern, source_text, re.I | re.S)) for name, pattern in PATTERNS.items()}
        features = {k: v for k, v in features.items() if v}
        return {
            "registry": registry,
            "order": order,
            "key": key,
            "function": fn_name,
            "line_start": fn.lineno,
            "line_end": fn.end_lineno,
            "docstring": doc.strip(),
            "features": features,
            "review_required": bool(features),
        }

    records = [entry("MIGRATIONS", i, f"version_{i:03d}", fn) for i, fn in enumerate(migrations, 1)]
    records += [entry("STEPS", i, name, fn) for i, (name, fn) in enumerate(steps, 1)]
    duplicate_step_keys = sorted({n for n, _ in steps if sum(1 for x, _ in steps if x == n) > 1})
    duplicate_step_functions = sorted({f for _, f in steps if sum(1 for _, x in steps if x == f) > 1})
    totals: dict[str, int] = {}
    for record in records:
        for feature, count in record["features"].items():
            totals[feature] = totals.get(feature, 0) + count
    return {
        "source": "db.py",
        "scope_warning": "Static inventory only. Entries are not PostgreSQL migrations and must not be executed against PostgreSQL.",
        "registry_counts": {"MIGRATIONS": len(migrations), "STEPS": len(steps)},
        "duplicate_step_keys": duplicate_step_keys,
        "duplicate_step_functions": duplicate_step_functions,
        "feature_occurrences_by_registry_entry": dict(sorted(totals.items())),
        "entries": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inventory = build_inventory(args.source.read_text(encoding="utf-8"))
    args.output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}: {inventory['registry_counts']['MIGRATIONS']} numbered migrations, "
          f"{inventory['registry_counts']['STEPS']} named steps")
    print("Review-required entries:", sum(x["review_required"] for x in inventory["entries"]))
    print("Static feature occurrences:", json.dumps(inventory["feature_occurrences_by_registry_entry"], sort_keys=True))
    print("WARNING: inventory only; no PostgreSQL migration was generated or executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
