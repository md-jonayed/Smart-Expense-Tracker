import sqlite3
import os

DB_PATH = "data/expenses.db"

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_expense(date, description, amount, category):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (date, description, amount, category) VALUES (?, ?, ?, ?)",
        (date, description, amount, category)
    )
    conn.commit()
    conn.close()

def get_expenses():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM expenses ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows
