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
            timestamp DATETIME DEFAULT (datetime('now')),
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
            timestamp DATETIME DEFAULT (datetime('now')),
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

    # 4. open_positions tablosu (v2 Kisa Vadeli Stratejiler & TP/SL Yonetimi)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS open_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            strategy TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_time DATETIME DEFAULT (datetime('now')),
            initial_quantity REAL NOT NULL,
            current_quantity REAL NOT NULL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            sl REAL NOT NULL,
            trailing_sl REAL,
            highest_price REAL,
            stage TEXT DEFAULT 'STAGE_INITIAL',
            expire_time DATETIME,
            status TEXT DEFAULT 'OPEN',
            close_time DATETIME,
            close_price REAL,
            realized_pnl REAL DEFAULT 0.0,
            reasoning TEXT
        )
    """)

    # 5. bot_settings tablosu (Aktif strateji modu vb.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
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

    # Varsayilan Strateji Modu ('auto')
    cursor.execute("SELECT * FROM bot_settings WHERE key = 'strategy_mode'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO bot_settings (key, value) VALUES ('strategy_mode', 'auto')")
        
    conn.commit()
    conn.close()


async def get_setting(key: str, default: str = "") -> str:
    """Asenkron olarak ayar degerini dondurur."""
    conn = await get_async_db_connection()
    try:
        async with conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else default
    finally:
        await conn.close()


async def set_setting(key: str, value: str):
    """Asenkron olarak ayar degerini kaydeder veya gunceller."""
    conn = await get_async_db_connection()
    try:
        await conn.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        await conn.commit()
    finally:
        await conn.close()


if __name__ == "__main__":
    init_db()
    print("Veritabani basariyla baslatildi ve sema guncellendi.")