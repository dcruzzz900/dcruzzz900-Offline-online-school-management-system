import pytest

from postgres_compat import qmark_to_format, quote_identifier


def test_converts_only_qmarks_outside_sql_literals_and_comments():
    sql = "SELECT ?, '?', \"?\", col -- ?\nFROM t WHERE x=? /* ? */"
    assert qmark_to_format(sql, (1, 2)) == (
        "SELECT %s, '?', \"?\", col -- ?\nFROM t WHERE x=%s /* ? */"
    )


def test_preserves_dollar_quoted_function_body():
    sql = "SELECT ?, $$ body ? $$, $tag$ ? $tag$, ?"
    assert qmark_to_format(sql, (1, 2)) == "SELECT %s, $$ body ? $$, $tag$ ? $tag$, %s"


def test_handles_doubled_quote_escapes():
    sql = "SELECT 'it''s ?' AS value, ?"
    assert qmark_to_format(sql, (7,)) == "SELECT 'it''s ?' AS value, %s"


def test_requires_exact_parameter_count():
    with pytest.raises(ValueError, match="2 qmark"):
        qmark_to_format("SELECT ?, ?", (1,))


def test_none_params_does_not_rewrite():
    assert qmark_to_format("SELECT ?") == "SELECT ?"


def test_quotes_identifiers_safely():
    assert quote_identifier('odd"name') == '"odd""name"'
    with pytest.raises(ValueError):
        quote_identifier("schema.table")
