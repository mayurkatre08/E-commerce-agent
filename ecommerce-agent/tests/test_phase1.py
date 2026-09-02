"""
test_phase1.py -- Validates Phase 1: database integrity and policy files.
Run: python tests/test_phase1.py
"""

import sqlite3
import os
import sys

DB_PATH      = os.path.join(os.path.dirname(__file__), "..", "db", "ecommerce.db")
POLICIES_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "policies")
EXPECTED_POLICIES = ["returns.md", "shipping.md", "sizing.md", "cancellation.md", "payment.md", "exchanges.md"]

failures = []

def check(label, condition, detail=""):
    if condition:
        print(f"  [PASS] {label}")
    else:
        msg = f"  [FAIL] {label}"
        if detail:
            msg += f" -- {detail}"
        print(msg)
        failures.append(label)

# -- Policy Files --------------------------------------------------------------
print("\n[Policy Files]")
for fname in EXPECTED_POLICIES:
    path = os.path.join(POLICIES_DIR, fname)
    exists = os.path.isfile(path)
    check(f"{fname} exists", exists)
    if exists:
        size = os.path.getsize(path)
        check(f"{fname} non-empty (size={size}B)", size > 100, f"only {size} bytes")

# -- Database Existence --------------------------------------------------------
print("\n[Database]")
check("ecommerce.db exists", os.path.isfile(DB_PATH), f"expected at {DB_PATH}")

if not os.path.isfile(DB_PATH):
    print("\n[WARNING] Run `python data/seed_db.py` first.\n")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# -- Table Existence -----------------------------------------------------------
print("\n[Tables]")
for table in ["customers", "products", "orders"]:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    check(f"table '{table}' exists", cur.fetchone() is not None)

# -- Row Counts ----------------------------------------------------------------
print("\n[Row Counts]")
cur.execute("SELECT COUNT(*) FROM customers"); c = cur.fetchone()[0]
check(f"customers >= 10 (got {c})", c >= 10)

cur.execute("SELECT COUNT(*) FROM products");  p = cur.fetchone()[0]
check(f"products >= 15 (got {p})", p >= 15)

cur.execute("SELECT COUNT(*) FROM orders");    o = cur.fetchone()[0]
check(f"orders >= 30 (got {o})", o >= 30)

# -- Schema Columns ------------------------------------------------------------
print("\n[Schema]")
cur.execute("PRAGMA table_info(orders)")
order_cols = {row["name"] for row in cur.fetchall()}
required_cols = {"order_id","customer_id","product_id","product_name","size","quantity",
                 "total_price","status","created_at","updated_at","tracking_number"}
missing = required_cols - order_cols
check("orders has all required columns", not missing, f"missing: {missing}")

# -- Pinned Test Orders --------------------------------------------------------
print("\n[Pinned Test Orders]")
pinned_checks = [
    ("ORD9001", "C001", "processing", None),
    ("ORD9002", "C002", "shipped",    "TRK555001"),
    ("ORD9003", "C003", "delivered",  "TRK555002"),
    ("ORD9004", "C004", "processing", None),
    ("ORD9005", "C005", "cancelled",  None),
]
for order_id, customer_id, expected_status, expected_tracking in pinned_checks:
    cur.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
    row = cur.fetchone()
    check(f"{order_id} exists", row is not None)
    if row:
        check(f"{order_id} customer={customer_id}", row["customer_id"] == customer_id)
        check(f"{order_id} status={expected_status}", row["status"] == expected_status)
        check(f"{order_id} tracking correct", row["tracking_number"] == expected_tracking,
              f"got {row['tracking_number']!r}, expected {expected_tracking!r}")

# -- Business Logic Guards -----------------------------------------------------
print("\n[Business Logic Guards]")
cur.execute("SELECT COUNT(*) FROM orders WHERE status='processing'"); proc = cur.fetchone()[0]
check(f"at least 2 'processing' orders exist (got {proc})", proc >= 2)

cur.execute("SELECT COUNT(*) FROM orders WHERE status='shipped'"); ship = cur.fetchone()[0]
check(f"at least 2 'shipped' orders exist (got {ship})", ship >= 2)

cur.execute("SELECT COUNT(*) FROM orders WHERE status='delivered'"); deliv = cur.fetchone()[0]
check(f"at least 2 'delivered' orders exist (got {deliv})", deliv >= 2)

# -- Sample Data Preview -------------------------------------------------------
print("\n[Sample Data Preview]")
print("\n  Customers (first 3):")
for row in cur.execute("SELECT customer_id, name, email FROM customers LIMIT 3"):
    print(f"    {row['customer_id']} | {row['name']} | {row['email']}")

print("\n  Products (first 3):")
for row in cur.execute("SELECT product_id, name, category, price FROM products LIMIT 3"):
    print(f"    {row['product_id']} | {row['name']} | {row['category']} | ${row['price']}")

print("\n  Pinned Orders:")
for row in cur.execute("SELECT order_id, customer_id, product_name, size, status FROM orders WHERE order_id LIKE 'ORD9%'"):
    print(f"    {row['order_id']} | {row['customer_id']} | {row['product_name']} | {row['size']} | {row['status']}")

conn.close()

# -- Summary -------------------------------------------------------------------
print("\n" + "-" * 50)
if failures:
    print(f"[FAILED] {len(failures)} check(s) failed: {failures}")
    sys.exit(1)
else:
    print("[PASSED] All Phase 1 checks passed -- ready for Phase 2!")
print()
