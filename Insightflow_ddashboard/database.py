import os
import shutil
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DB_PATH = os.path.join(BASE_DIR, "dashboard.db")

if os.environ.get("VERCEL") == "1":
    DB_PATH = "/tmp/dashboard.db"
    if not os.path.exists(DB_PATH):
        shutil.copy2(SOURCE_DB_PATH, DB_PATH)
else:
    DB_PATH = SOURCE_DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_date TEXT NOT NULL,
            region TEXT,
            category TEXT,
            product TEXT,
            quantity INTEGER,
            unit_price REAL,
            unit_cost REAL,
            revenue REAL,
            cost REAL,
            profit REAL
        )
    """)

    existing_cols = [row[1] for row in cur.execute("PRAGMA table_info(sales)").fetchall()]
    for col in ["unit_cost", "cost", "profit"]:
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE sales ADD COLUMN {col} REAL DEFAULT NULL")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            row_count INTEGER,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
