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
    "system_prompt": """你是一个谨慎的A股公告研究助手。请只基于公告内容输出研究分析。
不要给出买入或卖出指令。""",
    "user_instruction": """请基于公告正文自由输出研究分析。
可以按你认为合适的结构组织内容，但必须只使用公告原文能支持的信息。""",
}

DEFAULT_RESEARCH_PROMPT_SETTINGS = {
    "system_prompt": "你是一个严谨的投资研究报告分析助手。只能依据报告译文总结观点、证据、风险与待验证事项，不得编造信息或给出买卖指令。",
    "user_instruction": "请分析这篇研究报告译文，提炼核心观点、关键数据与论据、主要风险，以及后续需要验证的问题。",
}

DEFAULT_ANALYSIS_PROMPT_PRESETS = [
    {
        "id": "default",
        "title": "默认公告研究",
        "system_prompt": DEFAULT_ANALYSIS_PROMPT_SETTINGS["system_prompt"],
        "user_instruction": DEFAULT_ANALYSIS_PROMPT_SETTINGS["user_instruction"],
        "free_output": True,
        "is_active": True,
    }
]


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
    presets = get_analysis_prompt_presets()
    for item in presets["items"]:
        if item.get("is_active"):
            return {
                "system_prompt": item["system_prompt"],
                "user_instruction": item["user_instruction"],
                "free_output": True,
            }
    first = presets["items"][0]
    return {
        "system_prompt": first["system_prompt"],
        "user_instruction": first["user_instruction"],
        "free_output": True,
    }


def get_analysis_prompt_presets() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'analysis_prompts'").fetchone()
        legacy_row = conn.execute("SELECT value FROM settings WHERE key = 'analysis_prompt'").fetchone()
    if row is not None:
        return _normalize_analysis_prompt_presets(json.loads(row["value"]))
    if legacy_row is not None:
        legacy = {**DEFAULT_ANALYSIS_PROMPT_SETTINGS, **json.loads(legacy_row["value"])}
        return _normalize_analysis_prompt_presets(
            {
                "items": [
                    {
                        "id": "default",
                        "title": "默认公告研究",
                        "system_prompt": legacy["system_prompt"],
                        "user_instruction": legacy["user_instruction"],
                        "free_output": True,
                        "is_active": True,
                    }
                ]
            }
        )
    return {"items": [item.copy() for item in DEFAULT_ANALYSIS_PROMPT_PRESETS]}


def save_analysis_prompt_settings(settings: dict[str, Any]) -> dict[str, Any]:
    presets = get_analysis_prompt_presets()
    first = {**presets["items"][0], **settings, "is_active": True}
    save_analysis_prompt_presets({"items": [first, *presets["items"][1:]]})
    return get_analysis_prompt_settings()


def get_research_prompt_settings() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'research_prompt'").fetchone()
    if row is None:
        return {**DEFAULT_RESEARCH_PROMPT_SETTINGS, "free_output": True}
    return {**DEFAULT_RESEARCH_PROMPT_SETTINGS, **json.loads(row["value"]), "free_output": True}


def save_research_prompt_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "system_prompt": str(settings.get("system_prompt") or DEFAULT_RESEARCH_PROMPT_SETTINGS["system_prompt"]),
        "user_instruction": str(settings.get("user_instruction") or DEFAULT_RESEARCH_PROMPT_SETTINGS["user_instruction"]),
        "free_output": True,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, updated_at)
            VALUES ('research_prompt', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(normalized, ensure_ascii=False),),
        )
    return normalized


def save_analysis_prompt_presets(presets: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_analysis_prompt_presets(presets)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, updated_at)
            VALUES ('analysis_prompts', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(normalized, ensure_ascii=False),),
        )
    return normalized


def _normalize_analysis_prompt_presets(presets: dict[str, Any]) -> dict[str, Any]:
    items = presets.get("items")
    if not isinstance(items, list):
        items = []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        system_prompt = str(item.get("system_prompt") or "").strip()
        user_instruction = str(item.get("user_instruction") or "").strip()
        if not item_id or item_id in seen_ids or not title or not system_prompt or not user_instruction:
            continue
        seen_ids.add(item_id)
        normalized.append(
            {
                "id": item_id,
                "title": title,
                "system_prompt": system_prompt,
                "user_instruction": user_instruction,
                "free_output": True,
                "is_active": bool(item.get("is_active")),
            }
        )
    if not normalized:
        normalized = [item.copy() for item in DEFAULT_ANALYSIS_PROMPT_PRESETS]
    active_seen = False
    for item in normalized:
        if item["is_active"] and not active_seen:
            active_seen = True
        else:
            item["is_active"] = False
    if not active_seen:
        normalized[0]["is_active"] = True
    return {"items": normalized}
