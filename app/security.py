"""SQL AST and input safety checks."""
from __future__ import annotations

import sqlglot
from sqlglot import exp


class UnsafeQueryError(ValueError):
    """Raised when SQL is not a single read-only query."""


def validate_read_only_sql(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeQueryError("The generated SQL query is empty.")
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except Exception as exc:
        raise UnsafeQueryError("The generated SQL could not be parsed safely.") from exc
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("Only one SQL statement is allowed.")
    tree = statements[0]
    allowed_roots = (exp.Select, exp.Union, exp.Intersect, exp.Except)
    if not isinstance(tree, allowed_roots):
        raise UnsafeQueryError("Only read-only SELECT queries are allowed.")
    # The SELECT-only root check rejects every standalone write statement. This
    # additional AST denylist catches nested/embedded write and locking nodes.
    forbidden_names = (
        "Insert", "Update", "Delete", "Drop", "Alter", "Create", "TruncateTable",
        "Merge", "Replace", "Copy", "LoadData", "Command", "Transaction", "Pragma",
        "Attach", "Detach", "Lock", "Use", "Grant", "Revoke",
    )
    forbidden = tuple(getattr(exp, name) for name in forbidden_names if hasattr(exp, name))
    if any(isinstance(node, forbidden) for node in tree.walk()):
        raise UnsafeQueryError("The query contains a prohibited SQL operation.")
    # SELECT INTO and SQLite extension/file functions can have side effects or
    # expose local files even though the outer statement is a SELECT.
    if tree.find(exp.Into):
        raise UnsafeQueryError("SELECT INTO is not allowed.")
    # A tautological OR can turn a constrained query into an unbounded data
    # disclosure. Check the parsed expression tree, not SQL text heuristics.
    for disjunction in tree.find_all(exp.Or):
        for equality in disjunction.find_all(exp.EQ):
            left, right = equality.this, equality.expression
            if (isinstance(left, exp.Literal) and isinstance(right, exp.Literal)
                    and left.this.casefold() == right.this.casefold()):
                raise UnsafeQueryError("Tautological OR conditions are not allowed.")
    unsafe_functions = {"load_extension", "readfile", "writefile"}
    for node in tree.find_all(exp.Func):
        name = getattr(node, "name", "") or node.sql_name()
        if name.lower() in unsafe_functions:
            raise UnsafeQueryError("The query contains a prohibited SQL function.")
    return sql.strip().rstrip(";").strip()


def inspect_user_input(text: str) -> tuple[bool, str]:
    """Small deterministic front gate; NeMo adds policy-based inspection in the graph."""
    if not text or not text.strip():
        return False, "Enter a question about the available sales data."
    if len(text) > 2000:
        return False, "The question is too long. Keep it under 2,000 characters."
    return True, ""
