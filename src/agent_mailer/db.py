import sqlite3

import aiosqlite

DB_PATH = "agent_mailer.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('send', 'reply', 'forward')),
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    attachments TEXT NOT NULL DEFAULT '[]',
    is_read INTEGER NOT NULL DEFAULT 0,
    parent_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES messages(id)
);
"""

# Thread archive (operator console); additive migration — existing DBs keep all message rows.
ARCHIVED_THREADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS archived_threads (
    thread_id TEXT PRIMARY KEY,
    archived_at TEXT NOT NULL
);
"""

TRASHED_THREADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trashed_threads (
    thread_id TEXT PRIMARY KEY,
    trashed_at TEXT NOT NULL
);
"""

TRASHED_MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS trashed_messages (
    message_id TEXT PRIMARY KEY,
    trashed_at TEXT NOT NULL
);
"""

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_superadmin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

INVITE_CODES_SCHEMA = """
CREATE TABLE IF NOT EXISTS invite_codes (
    code TEXT PRIMARY KEY,
    created_by TEXT NOT NULL,
    used_by TEXT,
    used_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (used_by) REFERENCES users(id)
);
"""

API_KEYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

# Inbox listings (agent + admin) hide messages in archived or trashed threads.
INBOX_THREAD_VISIBILITY_SQL = (
    "thread_id NOT IN (SELECT thread_id FROM archived_threads) "
    "AND thread_id NOT IN (SELECT thread_id FROM trashed_threads)"
)

# Hide individually trashed messages (operator soft-delete per message).
MESSAGE_NOT_TRASHED_SQL = "id NOT IN (SELECT message_id FROM trashed_messages)"

# Combined filter for inbox-style queries (no table alias).
INBOX_VISIBILITY_SQL = f"({INBOX_THREAD_VISIBILITY_SQL}) AND ({MESSAGE_NOT_TRASHED_SQL})"

# Per-message row filter when using alias `m` (thread summaries).
MESSAGE_ROW_VISIBLE_SQL = f"m.id NOT IN (SELECT message_id FROM trashed_messages)"


async def get_db(db_path: str = DB_PATH) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def _add_column_if_missing(
    db: aiosqlite.Connection, table: str, column: str, col_def: str
):
    """Additive migration helper — silently skips if column already exists."""
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            pass
        else:
            raise


async def init_db(db: aiosqlite.Connection):
    await db.executescript(SCHEMA)
    await db.executescript(ARCHIVED_THREADS_SCHEMA)
    await db.executescript(TRASHED_THREADS_SCHEMA)
    await db.executescript(TRASHED_MESSAGES_SCHEMA)
    await db.executescript(USERS_SCHEMA)
    await db.executescript(INVITE_CODES_SCHEMA)
    await db.executescript(API_KEYS_SCHEMA)
    await _add_column_if_missing(db, "agents", "tags", "TEXT NOT NULL DEFAULT '[]'")
    await _add_column_if_missing(db, "agents", "user_id", "TEXT")
    await _add_column_if_missing(db, "users", "filter_tags", "TEXT NOT NULL DEFAULT '[]'")
    await db.commit()
