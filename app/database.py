"""
SQLite database initialisation and connection factory.

Creates tables on startup, enables WAL mode and foreign keys.

CHANGELOG:
- 2026-03-01: Add migration to backfill summary column on existing databases
- 2026-02-28: Add summary column to conversations (STORY-046)
- 2026-02-28: Add preferences table (STORY-045)
"""

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    summary     TEXT DEFAULT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user', 'agent')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_preferences_user ON preferences(user_id);
"""

# Migrations for existing databases where CREATE TABLE IF NOT EXISTS is a no-op.
# Each entry: (column_check_table, column_name, ALTER statement)
_MIGRATIONS = [
    (
        "conversations",
        "summary",
        "ALTER TABLE conversations ADD COLUMN summary TEXT DEFAULT NULL",
    ),
]


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Add columns that may be missing from tables created before schema updates."""
    for table, column, alter_sql in _MIGRATIONS:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in await cursor.fetchall()}
        if column not in columns:
            await db.execute(alter_sql)


async def init_db(db_path: str) -> None:
    """Create tables if they don't exist. Enables WAL mode and foreign keys."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(_SCHEMA)
        await _run_migrations(db)
        await db.commit()


async def get_connection(db_path: str) -> aiosqlite.Connection:
    """Open a new async SQLite connection with foreign keys enabled."""
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON")
    return db
