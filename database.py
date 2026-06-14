import sqlite3
import aiosqlite
import os

DB_PATH = "bot.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

async def get_async_db_connection():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. signals tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            reasoning TEXT
        )
    """)
    
    # 2. trades tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            total_value REAL NOT NULL,
            reasoning TEXT
        )
    """)
    
    # 3. portfolio tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            ticker TEXT PRIMARY KEY,
            quantity REAL NOT NULL,
            average_cost REAL NOT NULL
        )
    """)
    
    # Migration block (eski veritabanlari icin)
    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN reasoning TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN reasoning TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Baslangic bakiyesi "TRY" tanimlama (eger yoksa)
    cursor.execute("SELECT * FROM portfolio WHERE ticker = 'TRY'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO portfolio (ticker, quantity, average_cost) VALUES ('TRY', 500000.0, 1.0)")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Veritabani basariyla baslatildi.")
