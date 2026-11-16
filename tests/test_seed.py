import sqlite3

from database.seed import seed_database


def test_seed_database_can_rebuild_existing_related_tables(tmp_path):
    database = seed_database(tmp_path / "existing.db")
    seed_database(database)

    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(orders)")}
        count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]

    assert {"id", "order_date"}.issubset(columns)
    assert count == 10
