"""Small, deliberately conservative SQL compatibility helpers.

The application currently uses SQLite's ``?`` parameter markers.  Psycopg 3
uses ``%s`` markers.  This module provides a lexical conversion helper for
statements whose parameter markers are qmarks; it does not attempt to translate
SQLite SQL dialect features, schema DDL, or SQLite JSON ``?`` operators.
"""
from __future__ import annotations


def qmark_to_format(sql: str, params=None) -> str:
    """Convert SQL qmark placeholders to psycopg ``%s`` markers.

    Question marks inside quoted strings/identifiers, line comments, block
    comments, and PostgreSQL dollar-quoted strings are preserved.  If a
    parameter sequence is supplied, its length must match the number of
    converted markers.  With ``params=None`` the SQL is returned unchanged;
    callers must explicitly supply parameters to opt into conversion.

    This is not a general SQL parser.  In particular, do not pass SQL using
    PostgreSQL's JSON question-mark operators through this helper.
    """
    if params is None:
        return sql

    out: list[str] = []
    i = 0
    n = len(sql)
    count = 0
    state = "normal"
    dollar_tag = None

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if state == "normal":
            if ch == "'":
                state = "single"
                out.append(ch)
                i += 1
                continue
            if ch == '"':
                state = "double"
                out.append(ch)
                i += 1
                continue
            if ch == "-" and nxt == "-":
                state = "line_comment"
                out.extend((ch, nxt))
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                out.extend((ch, nxt))
                i += 2
                continue
            if ch == "$":
                j = i + 1
                while j < n and (sql[j].isalnum() or sql[j] == "_"):
                    j += 1
                if j < n and sql[j] == "$":
                    dollar_tag = sql[i:j + 1]
                    state = "dollar"
                    out.append(dollar_tag)
                    i = j + 1
                    continue
            if ch == "?":
                out.append("%s")
                count += 1
            else:
                out.append(ch)
            i += 1
            continue

        if state == "single":
            out.append(ch)
            i += 1
            if ch == "'":
                if i < n and sql[i] == "'":
                    out.append(sql[i])
                    i += 1
                else:
                    state = "normal"
            elif ch == "\\" and i < n:
                # Preserve backslash-escaped characters in SQLite-style strings.
                out.append(sql[i])
                i += 1
            continue

        if state == "double":
            out.append(ch)
            i += 1
            if ch == '"':
                if i < n and sql[i] == '"':
                    out.append(sql[i])
                    i += 1
                else:
                    state = "normal"
            continue

        if state == "line_comment":
            out.append(ch)
            i += 1
            if ch == "\n":
                state = "normal"
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                out.extend((ch, nxt))
                i += 2
                state = "normal"
            else:
                out.append(ch)
                i += 1
            continue

        if state == "dollar":
            if dollar_tag and sql.startswith(dollar_tag, i):
                out.append(dollar_tag)
                i += len(dollar_tag)
                state = "normal"
                dollar_tag = None
            else:
                out.append(ch)
                i += 1
            continue

    if count != len(params):
        raise ValueError(
            f"SQL has {count} qmark placeholder(s), but {len(params)} parameter(s) were supplied"
        )
    return "".join(out)


def quote_identifier(identifier: str) -> str:
    """Quote one PostgreSQL identifier; reject qualified/multi-part input."""
    if not isinstance(identifier, str) or not identifier or "\x00" in identifier:
        raise ValueError("identifier must be a non-empty string without NUL")
    if "." in identifier:
        raise ValueError("quote_identifier accepts one identifier, not a qualified name")
    return '"' + identifier.replace('"', '""') + '"'
