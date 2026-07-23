from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))

DEFAULT_ANALYSIS_SYSTEM_PROMPT = """你是一个谨慎的A股公告研究助手。请只基于公告内容输出研究分析。
不要给出买入或卖出指令。"""

DEFAULT_ANALYSIS_USER_INSTRUCTION = "请基于公告正文输出研究分析。"


class LLMProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    def analyze(self, announcement: dict[str, Any], content: str, prompt_settings: dict[str, Any] | None = None) -> dict[str, Any]:
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

    def analyze(self, announcement: dict[str, Any], content: str, prompt_settings: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "output_format": "free",
            "free_output": (
                f"测试模型自由输出：{announcement['name']}发布《{announcement['title']}》，"
                f"原文长度约 {len(content)} 字。\n\n这是 mock 模型的自由文本结果。"
            ),
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

    def analyze(self, announcement: dict[str, Any], content: str, prompt_settings: dict[str, Any] | None = None) -> dict[str, Any]:
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
                {"role": "system", "content": analysis_system_prompt(prompt_settings)},
                {"role": "user", "content": build_user_prompt(announcement, content, prompt_settings)},
            ],
            temperature=0.2,
            **self._token_limit_param(),
        )
        return {
            "output_format": "free",
            "free_output": response.choices[0].message.content or "",
        }

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
            **self._token_limit_param(),
        )
        return response.choices[0].message.content or ""

    def _token_limit_param(self) -> dict[str, int]:
        if self.provider_name == "openai":
            return {"max_completion_tokens": 1400}
        return {"max_tokens": 1400}


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


def analysis_system_prompt(prompt_settings: dict[str, Any] | None = None) -> str:
    if not prompt_settings:
        return DEFAULT_ANALYSIS_SYSTEM_PROMPT
    return str(prompt_settings.get("system_prompt") or DEFAULT_ANALYSIS_SYSTEM_PROMPT)


def build_user_prompt(announcement: dict[str, Any], content: str, prompt_settings: dict[str, Any] | None = None) -> str:
    trimmed = content[:12000]
    instruction = DEFAULT_ANALYSIS_USER_INSTRUCTION
    if prompt_settings:
        instruction = str(prompt_settings.get("user_instruction") or DEFAULT_ANALYSIS_USER_INSTRUCTION)
    if announcement.get("document_type") == "research_report":
        return f"""
{instruction}

研究报告元数据：
- 报告名称：{announcement['title']}
- 来源：{announcement['source']}

报告译文：
{trimmed}
"""
    return f"""
{instruction}

公告元数据：
- 股票代码：{announcement['code']}
- 股票名称：{announcement['name']}
- 标题：{announcement['title']}
- 类型：{announcement['announcement_type']}
- 日期：{announcement['announcement_date']}

公告正文：
{trimmed}
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
    free_output = str(data.get("free_output", data.get("summary", "")))
    return {
        "output_format": "free",
        "free_output": free_output,
        "summary": free_output[:240],
        "sentiment": "neutral",
        "importance_score": 50,
        "risk_points": [],
        "opportunities": [],
        "watch_signals": [],
        "action_suggestion": "",
        "confidence": 0.5,
        "reasoning_short": "",
        "not_investment_advice": "",
    }
