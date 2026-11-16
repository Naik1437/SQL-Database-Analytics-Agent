import pytest

from app.security import UnsafeQueryError, validate_read_only_sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM customers",
    "UPDATE customers SET name='x'",
    "INSERT INTO customers VALUES (9,'x','x','x')",
    "DROP TABLE customers",
    "ALTER TABLE customers ADD COLUMN secret TEXT",
    "CREATE TABLE x (id INT)",
    "TRUNCATE TABLE customers",
    "DROP TABLE orders; --",
    "SELECT * FROM orders WHERE id = 1 OR 1=1",
    "SELECT * FROM orders INTO OUTFILE 'x'",
    "SELECT * FROM orders FOR UPDATE",
    "SELECT load_extension('malicious')",
    "SELECT * FROM orders WHERE (",
    "SELECT 1; DELETE FROM customers",
    "SELECT * FROM customers; SELECT * FROM orders",
    "PRAGMA table_info(customers)",
])
def test_rejects_mutation_and_multiple_statements(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)


def test_accepts_select_and_removes_trailing_semicolon():
    assert validate_read_only_sql("SELECT name FROM customers;") == "SELECT name FROM customers"


def test_accepts_safe_business_select():
    assert validate_read_only_sql("SELECT COUNT(*) FROM orders") == "SELECT COUNT(*) FROM orders"
