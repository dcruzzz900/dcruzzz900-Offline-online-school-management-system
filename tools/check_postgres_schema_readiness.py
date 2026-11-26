#!/usr/bin/env python3
"""Read-only PostgreSQL schema shape check; does not migrate or change data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from postgres_schema import validate_schema_shape


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="postgres_required_schema.json")
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL must point to the PostgreSQL target")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        parser.error(f"psycopg 3 is required to run this check: {exc}")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        result = validate_schema_shape(conn, manifest["tables"], args.schema)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
