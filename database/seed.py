"""Create and seed the local SQLite analytics database."""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).with_name("analytics.db")


def seed_database(path: Path = DB_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript("""
        PRAGMA foreign_keys = ON;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS sales;
        DROP TABLE IF EXISTS customers;
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            region TEXT NOT NULL, email TEXT NOT NULL UNIQUE
        );
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
            order_date TEXT NOT NULL, status TEXT NOT NULL,
            total_amount REAL NOT NULL CHECK(total_amount >= 0),
            FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
        );
        CREATE TABLE sales (
            sale_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL,
            product TEXT NOT NULL, category TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(order_id)
        );
        INSERT INTO customers VALUES
          (1,'Asha Patel','West','asha@example.test'),
          (2,'Noah Kim','East','noah@example.test'),
          (3,'Maya Singh','South','maya@example.test'),
          (4,'Liam Chen','North','liam@example.test'),
          (5,'Isha Rao','West','isha@example.test');
        INSERT INTO orders VALUES
          (1001,1,'2025-01-12','completed',240.00),
          (1002,2,'2025-01-19','completed',89.50),
          (1003,3,'2025-02-03','completed',510.00),
          (1004,1,'2025-02-17','shipped',155.00),
          (1005,4,'2025-03-08','completed',320.00),
          (1006,5,'2025-03-21','processing',75.00),
          (1007,2,'2025-04-02','completed',199.00),
          (1008,3,'2025-04-16','completed',420.00),
          (1009,4,'2025-05-05','cancelled',60.00),
          (1010,5,'2025-05-22','completed',275.00);
        INSERT INTO sales VALUES
          (1,1001,'Wireless Mouse','Accessories',2,40.00),
          (2,1001,'USB-C Hub','Accessories',2,80.00),
          (3,1002,'Notebook','Stationery',5,17.90),
          (4,1003,'Monitor','Electronics',1,350.00),
          (5,1003,'Keyboard','Accessories',2,80.00),
          (6,1004,'Desk Lamp','Home',1,55.00),
          (7,1004,'Headphones','Electronics',1,100.00),
          (8,1005,'Office Chair','Home',1,320.00),
          (9,1006,'Notebook','Stationery',3,25.00),
          (10,1007,'Keyboard','Accessories',1,99.00),
          (11,1007,'Webcam','Electronics',1,100.00),
          (12,1008,'Monitor','Electronics',1,350.00),
          (13,1008,'Wireless Mouse','Accessories',1,40.00),
          (14,1008,'Desk Lamp','Home',1,30.00),
          (15,1009,'Phone Stand','Accessories',2,30.00),
          (16,1010,'Headphones','Electronics',1,150.00),
          (17,1010,'USB-C Hub','Accessories',1,125.00);
        """)
    return path


if __name__ == "__main__":
    print(f"Seeded sample database at {seed_database()}")
