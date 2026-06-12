from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "stockai.db"


def get_db_path() -> Path:
    return Path(os.getenv("STOCKAI_DB_PATH", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                title TEXT NOT NULL,
                announcement_type TEXT NOT NULL,
                announcement_date TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'eastmoney',
                is_important INTEGER NOT NULL DEFAULT 0,
                matched_keywords TEXT NOT NULL DEFAULT '[]',
                ai_screen_status TEXT NOT NULL DEFAULT 'pending',
                ai_worth_tracking INTEGER,
                ai_importance_score INTEGER,
                ai_event_type TEXT,
                ai_screen_reason TEXT,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                analysis_status TEXT NOT NULL DEFAULT 'pending',
                content TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(url, code, title, announcement_date)
            );

            CREATE INDEX IF NOT EXISTS idx_announcements_date
                ON announcements(announcement_date);
            CREATE INDEX IF NOT EXISTS idx_announcements_code
                ON announcements(code);
            CREATE INDEX IF NOT EXISTS idx_announcements_status
                ON announcements(parse_status, analysis_status);

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                announcement_id INTEGER NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                summary TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                importance_score INTEGER NOT NULL,
                risk_points TEXT NOT NULL,
                opportunities TEXT NOT NULL,
                watch_signals TEXT NOT NULL,
                action_suggestion TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL,
                reasoning_short TEXT NOT NULL,
                not_investment_advice TEXT NOT NULL,
                raw_response TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (announcement_id)
                    REFERENCES announcements(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                announcement_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                content_length INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (announcement_id)
                    REFERENCES announcements(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_announcement
                ON chat_messages(announcement_id, created_at);
            """
        )
        conn.execute(
            """
            UPDATE announcements
            SET announcement_date = replace(announcement_date, '-', '')
            WHERE announcement_date LIKE '____-__-__'
            """
        )
        for column_sql in [
            "ALTER TABLE announcements ADD COLUMN ai_screen_status TEXT NOT NULL DEFAULT 'pending'",
            "ALTER TABLE announcements ADD COLUMN ai_worth_tracking INTEGER",
            "ALTER TABLE announcements ADD COLUMN ai_importance_score INTEGER",
            "ALTER TABLE announcements ADD COLUMN ai_event_type TEXT",
            "ALTER TABLE announcements ADD COLUMN ai_screen_reason TEXT",
            "ALTER TABLE analyses ADD COLUMN action_suggestion TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                conn.execute(column_sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        conn.execute(
            """
            UPDATE announcements
            SET ai_screen_status = 'pending'
            WHERE ai_screen_status = 'running'
            """
        )
        conn.execute(
            """
            UPDATE announcements
            SET analysis_status = 'pending'
            WHERE analysis_status = 'running'
            """
        )
        cutoff = (date.today() - timedelta(days=2)).strftime("%Y%m%d")
        conn.execute("DELETE FROM announcements WHERE announcement_date < ?", (cutoff,))


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}
