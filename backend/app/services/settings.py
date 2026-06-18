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

DEFAULT_ANALYSIS_PROMPT_SETTINGS = {
    "system_prompt": """你是一个谨慎的A股公告研究助手。请只基于公告内容输出结构化研究提醒。
不要给出买入或卖出指令。输出必须是JSON。""",
    "user_instruction": """请基于公告正文，输出结构化研究提醒。
重点提炼：关键事实、涉及金额/比例/时间点、直接影响、风险点、待验证线索和下一步观察信号。
action_suggestion 必须给出“继续关注”或“不需要继续关注”的明确结论，但不要给买入或卖出指令。""",
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


def get_analysis_prompt_settings() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'analysis_prompt'").fetchone()
    if row is None:
        return DEFAULT_ANALYSIS_PROMPT_SETTINGS.copy()
    return {**DEFAULT_ANALYSIS_PROMPT_SETTINGS, **json.loads(row["value"])}


def save_analysis_prompt_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_ANALYSIS_PROMPT_SETTINGS, **settings}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, updated_at)
            VALUES ('analysis_prompt', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(merged, ensure_ascii=False),),
        )
    return merged
