"""
seed_db.py — Creates and seeds the SQLite database with dummy data.
Tables: customers, products, orders
"""

import sqlite3
import os
from datetime import datetime, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "ecommerce.db")

CUSTOMERS = [
    ("C001", "Alice Johnson",    "alice@example.com",   "555-0101"),
    ("C002", "Bob Smith",        "bob@example.com",     "555-0102"),
    ("C003", "Carol White",      "carol@example.com",   "555-0103"),
    ("C004", "David Brown",      "david@example.com",   "555-0104"),
    ("C005", "Eva Martinez",     "eva@example.com",     "555-0105"),
    ("C006", "Frank Lee",        "frank@example.com",   "555-0106"),
    ("C007", "Grace Kim",        "grace@example.com",   "555-0107"),
    ("C008", "Henry Davis",      "henry@example.com",   "555-0108"),
    ("C009", "Isla Thompson",    "isla@example.com",    "555-0109"),
    ("C010", "Jack Wilson",      "jack@example.com",    "555-0110"),
]

PRODUCTS = [
    ("P001", "Classic White Tee",        "Tops",      19.99,  ["XS","S","M","L","XL","XXL"]),
    ("P002", "Slim Fit Jeans",           "Bottoms",   59.99,  ["28","30","32","34","36"]),
    ("P003", "Floral Summer Dress",      "Dresses",   49.99,  ["XS","S","M","L","XL"]),
    ("P004", "Wool Blend Coat",          "Outerwear", 129.99, ["S","M","L","XL"]),
    ("P005", "Running Sneakers",         "Footwear",  89.99,  ["7","8","9","10","11","12"]),
    ("P006", "Leather Belt",             "Accessories",24.99, ["S","M","L"]),
    ("P007", "Striped Polo Shirt",       "Tops",      34.99,  ["XS","S","M","L","XL","XXL"]),
    ("P008", "High-Waist Leggings",      "Bottoms",   44.99,  ["XS","S","M","L","XL"]),
    ("P009", "Denim Jacket",             "Outerwear", 79.99,  ["XS","S","M","L","XL"]),
    ("P010", "Canvas Tote Bag",          "Accessories",29.99, ["ONE SIZE"]),
    ("P011", "Merino Wool Sweater",      "Tops",      69.99,  ["XS","S","M","L","XL","XXL"]),
    ("P012", "Chino Shorts",             "Bottoms",   39.99,  ["28","30","32","34","36"]),
    ("P013", "Ankle Boots",              "Footwear",  109.99, ["6","7","8","9","10","11"]),
    ("P014", "Puffer Vest",              "Outerwear", 59.99,  ["XS","S","M","L","XL"]),
    ("P015", "Silk Scarf",               "Accessories",39.99, ["ONE SIZE"]),
]

STATUSES = ["processing", "processing", "shipped", "shipped", "delivered", "delivered", "cancelled"]

def random_date(days_ago_max=60, days_ago_min=1):
    delta = random.randint(days_ago_min, days_ago_max)
    return (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d %H:%M:%S")

def seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            customer_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL,
            phone         TEXT
        );

        CREATE TABLE products (
            product_id    TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            category      TEXT NOT NULL,
            price         REAL NOT NULL,
            available_sizes TEXT NOT NULL
        );

        CREATE TABLE orders (
            order_id      TEXT PRIMARY KEY,
            customer_id   TEXT NOT NULL,
            product_id    TEXT NOT NULL,
            product_name  TEXT NOT NULL,
            size          TEXT NOT NULL,
            quantity      INTEGER NOT NULL,
            total_price   REAL NOT NULL,
            status        TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            tracking_number TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (product_id)  REFERENCES products(product_id)
        );
    """)

    cur.executemany(
        "INSERT INTO customers VALUES (?,?,?,?)",
        CUSTOMERS
    )

    for p in PRODUCTS:
        cur.execute(
            "INSERT INTO products VALUES (?,?,?,?,?)",
            (p[0], p[1], p[2], p[3], ",".join(p[4]))
        )

    orders = []
    for i in range(1, 31):
        order_id   = f"ORD{i:04d}"
        customer   = random.choice(CUSTOMERS)
        product    = random.choice(PRODUCTS)
        size       = random.choice(product[4])
        qty        = random.randint(1, 3)
        total      = round(product[3] * qty, 2)
        status     = random.choice(STATUSES)
        created    = random_date(60, 2)
        updated    = created
        tracking   = f"TRK{random.randint(100000,999999)}" if status in ("shipped", "delivered") else None
        orders.append((order_id, customer[0], product[0], product[1], size, qty, total, status, created, updated, tracking))

    # Pin a few predictable orders for testing
    pinned = [
        ("ORD9001", "C001", "P001", "Classic White Tee",   "M",  1, 19.99,  "processing", "2025-01-10 10:00:00", "2025-01-10 10:00:00", None),
        ("ORD9002", "C002", "P002", "Slim Fit Jeans",       "32", 1, 59.99,  "shipped",    "2025-01-08 09:00:00", "2025-01-09 08:00:00", "TRK555001"),
        ("ORD9003", "C003", "P003", "Floral Summer Dress",  "S",  2, 99.98,  "delivered",  "2024-12-20 14:00:00", "2024-12-25 11:00:00", "TRK555002"),
        ("ORD9004", "C004", "P009", "Denim Jacket",         "L",  1, 79.99,  "processing", "2025-01-11 08:30:00", "2025-01-11 08:30:00", None),
        ("ORD9005", "C005", "P005", "Running Sneakers",     "10", 1, 89.99,  "cancelled",  "2025-01-05 12:00:00", "2025-01-05 13:00:00", None),
    ]

    cur.executemany(
        "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        orders + pinned
    )

    conn.commit()
    conn.close()
    print(f"[OK] Database seeded at: {os.path.abspath(DB_PATH)}")
    print(f"   customers : {len(CUSTOMERS)}")
    print(f"   products  : {len(PRODUCTS)}")
    print(f"   orders    : {len(orders) + len(pinned)} (30 random + 5 pinned)")

if __name__ == "__main__":
    seed()
