from __future__ import annotations

import json
from typing import Any

from ..db import get_connection, row_to_dict


DEFAULT_MODEL_SETTINGS = {
    "provider": "mock",
    "model": "mock-free-test",
    "base_url": None,
    "api_key": None,
}


def get_model_settings() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'model'").fetchone()
    if row is None:
        return DEFAULT_MODEL_SETTINGS.copy()
    return {**DEFAULT_MODEL_SETTINGS, **json.loads(row["value"])}


def save_model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_MODEL_SETTINGS, **settings}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, updated_at)
            VALUES ('model', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(merged, ensure_ascii=False),),
        )
    return merged


def public_model_settings() -> dict[str, Any]:
    settings = get_model_settings()
    return {
        "provider": settings["provider"],
        "model": settings["model"],
        "base_url": settings.get("base_url"),
        "has_api_key": bool(settings.get("api_key")),
    }
