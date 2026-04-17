import sqlite3
from pathlib import Path

DB_PATH = Path("mlops.db")


def get_conn():
    # Use 30 second timeout to avoid database locked errors
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS models (
        model_id TEXT PRIMARY KEY,
        model_name TEXT,
        created_at TEXT,
        active_version INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT,
        version INTEGER,
        status TEXT,
        folder_path TEXT,
        image_tag TEXT,
        container_id TEXT,
        internal_port INTEGER,
        created_at TEXT,
        error_log TEXT,
        FOREIGN KEY(model_id) REFERENCES models(model_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT,
        version INTEGER,
        request_time TEXT,
        latency_ms REAL
    )
    """)

    # Lightweight migration for existing databases.
    cur.execute("PRAGMA table_info(models)")
    model_columns = {row[1] for row in cur.fetchall()}
    if "model_name" not in model_columns:
        cur.execute("ALTER TABLE models ADD COLUMN model_name TEXT")

    # Migration: add is_active column to versions table
    cur.execute("PRAGMA table_info(versions)")
    version_columns = {row[1] for row in cur.fetchall()}
    if "is_active" not in version_columns:
        cur.execute("ALTER TABLE versions ADD COLUMN is_active INTEGER DEFAULT 0")
        # Initialize is_active based on status='RUNNING'
        cur.execute("UPDATE versions SET is_active = 1 WHERE status = 'RUNNING'")

    conn.commit()
    conn.close()
