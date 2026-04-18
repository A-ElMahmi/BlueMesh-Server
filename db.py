import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bluemesh.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT    NOT NULL UNIQUE,
    from_app_id TEXT    NOT NULL,
    to_app_id   TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    received_at INTEGER NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_to_app_id ON messages(to_app_id);
"""

MIGRATIONS = [
    "ALTER TABLE messages ADD COLUMN delivered INTEGER NOT NULL DEFAULT 0",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c["name"] == column for c in cols)


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        if not _column_exists(conn, "messages", "delivered"):
            for stmt in MIGRATIONS:
                conn.execute(stmt)
