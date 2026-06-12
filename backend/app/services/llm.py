from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any


OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))

SYSTEM_PROMPT = """你是一个谨慎的A股公告研究助手。请只基于公告内容输出结构化研究提醒。
不要给出买入或卖出指令。输出必须是JSON。"""


class LLMProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    def analyze(self, announcement: dict[str, Any], content: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def screen(self, announcement: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def chat(self, announcement: dict[str, Any], content: str, message: str, history: list[dict[str, Any]]) -> str:
        raise NotImplementedError


class MockProvider(LLMProvider):
    provider_name = "mock"
    model = "mock-free-test"

    def analyze(self, announcement: dict[str, Any], content: str) -> dict[str, Any]:
        title = announcement["title"]
        sentiment = "neutral"
        if any(word in title for word in ["回购", "增持", "中标", "重大合同", "增长"]):
            sentiment = "positive"
        if any(word in title for word in ["风险", "减持", "处罚", "诉讼", "退市"]):
            sentiment = "negative"
        return {
            "summary": f"测试模型摘要：{announcement['name']}发布《{title}》，当前原文长度约 {len(content)} 字。",
            "sentiment": sentiment,
            "importance_score": 65 if announcement.get("is_important") else 35,
            "risk_points": ["mock 模型只用于流程测试", "正式判断需要切换到 Ollama/OpenAI 等真实模型"],
            "opportunities": ["可作为研究清单候选项", "适合继续查看财务和行业背景"],
            "watch_signals": ["公告后首个交易日成交量变化", "公司后续补充公告"],
            "action_suggestion": "mock 建议：只作为流程测试。真实使用时请切换到 Ollama/OpenAI，并结合公告原文复核。",
            "confidence": 0.55,
            "reasoning_short": "基于公告标题、类型和原文长度生成的本地测试结果。",
            "not_investment_advice": "仅供个人研究提醒，不构成投资建议。",
        }

    def screen(self, announcement: dict[str, Any]) -> dict[str, Any]:
        return {
            "worth_tracking": bool(announcement.get("is_important")),
            "importance_score": 65 if announcement.get("is_important") else 25,
            "event_type": announcement.get("announcement_type") or "未分类",
            "reason": "mock 初筛：基于公告标题、类型和关键词规则判断。",
        }

    def chat(self, announcement: dict[str, Any], content: str, message: str, history: list[dict[str, Any]]) -> str:
        preview = content[:300] if content else "未提取到原文。"
        return (
            f"这是 mock/free-test 回复。我可以确认后端传入了公告原文，长度约 {len(content)} 字，"
            f"并带入了 {len(history)} 条历史对话。\n\n"
            f"你问：{message}\n\n"
            f"原文开头片段：\n{preview}"
        )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, provider_name: str, model: str, api_key: str | None, base_url: str | None = None) -> None:
        self.provider_name = provider_name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def analyze(self, announcement: dict[str, Any], content: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=OPENAI_TIMEOUT_SECONDS,
            max_retries=OPENAI_MAX_RETRIES,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(announcement, content)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1400,
        )
        return normalize_analysis(json.loads(response.choices[0].message.content or "{}"))

    def screen(self, announcement: dict[str, Any]) -> dict[str, Any]:
        return {
            "worth_tracking": bool(announcement.get("is_important")),
            "importance_score": 65 if announcement.get("is_important") else 25,
            "event_type": announcement.get("announcement_type") or "未分类",
            "reason": "标题规则初筛，不调用大模型。",
        }

    def chat(self, announcement: dict[str, Any], content: str, message: str, history: list[dict[str, Any]]) -> str:
        from openai import OpenAI

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": "你是A股公告研究助手。只能基于用户提供的公告原文和本轮对话历史回答；如果原文没有依据，要明确说无法从原文确认。不要给买卖建议。",
            },
            {"role": "user", "content": build_chat_context_prompt(announcement, content)},
        ]
        for item in history:
            role = "assistant" if item.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": str(item.get("content", ""))[:3000]})
        messages.append({"role": "user", "content": message})

        client = OpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=OPENAI_TIMEOUT_SECONDS,
            max_retries=OPENAI_MAX_RETRIES,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            max_tokens=1400,
        )
        return response.choices[0].message.content or ""


def provider_from_settings(settings: dict[str, Any]) -> LLMProvider:
    provider = settings.get("provider", "mock")
    if provider == "mock":
        return MockProvider()
    if provider == "openai":
        return OpenAICompatibleProvider("openai", settings.get("model") or "gpt-4.1-mini", settings.get("api_key"))
    if provider == "openai-compatible":
        return OpenAICompatibleProvider(
            "openai-compatible",
            settings.get("model") or "qwen2.5:7b",
            settings.get("api_key"),
            settings.get("base_url"),
        )
    raise ValueError(f"Unsupported provider: {provider}")


def build_user_prompt(announcement: dict[str, Any], content: str) -> str:
    trimmed = content[:12000]
    return f"""
公告元数据：
- 股票代码：{announcement['code']}
- 股票名称：{announcement['name']}
- 标题：{announcement['title']}
- 类型：{announcement['announcement_type']}
- 日期：{announcement['announcement_date']}

公告正文：
{trimmed}

请输出JSON，字段固定为：
summary, sentiment, importance_score, risk_points, opportunities, watch_signals,
action_suggestion, confidence, reasoning_short, not_investment_advice。
sentiment 只能是 positive、negative、neutral 或 mixed。
importance_score 为 0-100 整数。
confidence 为 0-1 小数。
action_suggestion 必须给出明确结论，例如“继续关注：...”或“不需要继续关注：...”，但不要给买入/卖出指令。
"""


def build_chat_context_prompt(announcement: dict[str, Any], content: str) -> str:
    trimmed = content[:12000]
    return f"""
以下是当前对话必须依据的公告原文。后续回答只能基于这份原文和对话历史。

公告元数据：
- 股票代码：{announcement['code']}
- 股票名称：{announcement['name']}
- 标题：{announcement['title']}
- 类型：{announcement['announcement_type']}
- 日期：{announcement['announcement_date']}

公告原文，长度约 {len(content)} 字：
{trimmed}
"""


def normalize_screen(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "worth_tracking": bool(data.get("worth_tracking", False)),
        "importance_score": max(0, min(100, int(data.get("importance_score", 0)))),
        "event_type": str(data.get("event_type", "未分类")),
        "reason": str(data.get("reason", "")),
    }


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": str(data.get("summary", "")),
        "sentiment": str(data.get("sentiment", "neutral")),
        "importance_score": int(data.get("importance_score", 50)),
        "risk_points": _as_list(data.get("risk_points")),
        "opportunities": _as_list(data.get("opportunities")),
        "watch_signals": _as_list(data.get("watch_signals")),
        "action_suggestion": str(data.get("action_suggestion", "")),
        "confidence": float(data.get("confidence", 0.5)),
        "reasoning_short": str(data.get("reasoning_short", "")),
        "not_investment_advice": str(data.get("not_investment_advice", "仅供个人研究提醒，不构成投资建议。")),
    }


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]
