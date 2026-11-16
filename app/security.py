"""SQL AST and input safety checks."""
from __future__ import annotations

import sqlglot
from sqlglot import exp


class UnsafeQueryError(ValueError):
    """Raised when SQL is not a single read-only query."""


def validate_read_only_sql(sql: str) -> str:
    if not sql or not sql.strip():
        raise UnsafeQueryError("The generated SQL query is empty.")
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeQueryError("The generated SQL could not be parsed safely.") from exc
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("Only one SQL statement is allowed.")
    tree = statements[0]
    allowed_roots = (exp.Select, exp.Union, exp.Intersect, exp.Except)
    if not isinstance(tree, allowed_roots):
        raise UnsafeQueryError("Only read-only SELECT queries are allowed.")
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create,
                 exp.Command, exp.Transaction, exp.Pragma, exp.Attach, exp.Detach)
    if any(isinstance(node, forbidden) for node in tree.walk()):
        raise UnsafeQueryError("The query contains a prohibited SQL operation.")
    # SELECT INTO and table-valued side effects are rejected explicitly.
    if tree.find(exp.Into):
        raise UnsafeQueryError("SELECT INTO is not allowed.")
    return sql.strip().rstrip(";").strip()


def inspect_user_input(text: str) -> tuple[bool, str]:
    """Small deterministic front gate; NeMo adds policy-based inspection in the graph."""
    if not text or not text.strip():
        return False, "Enter a question about the available sales data."
    if len(text) > 2000:
        return False, "The question is too long. Keep it under 2,000 characters."
    return True, ""
