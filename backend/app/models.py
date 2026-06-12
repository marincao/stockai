from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Status = Literal["pending", "running", "succeeded", "failed", "parse_failed"]
ProviderName = Literal["mock", "openai", "openai-compatible"]


class FetchAnnouncementsRequest(BaseModel):
    date: str = Field(pattern=r"^\d{8}$")


class FetchAnnouncementsResponse(BaseModel):
    date: str
    fetched: int
    inserted: int
    updated: int
    important: int
    screened: int = 0


class Announcement(BaseModel):
    id: int
    code: str
    name: str
    title: str
    announcement_type: str
    announcement_date: str
    url: str
    source: str
    is_important: bool
    matched_keywords: list[str]
    ai_screen_status: str
    ai_worth_tracking: bool | None = None
    ai_importance_score: int | None = None
    ai_event_type: str | None = None
    ai_screen_reason: str | None = None
    parse_status: str
    analysis_status: str
    content_preview: str | None = None


class AnnouncementListResponse(BaseModel):
    items: list[Announcement]
    total: int
    page: int
    page_size: int


class CountItem(BaseModel):
    name: str
    count: int


class DatabaseSummary(BaseModel):
    total_announcements: int
    important_announcements: int
    ai_tracking_announcements: int = 0
    analyzed_announcements: int
    parsed_announcements: int
    content_announcements: int = 0
    chat_messages: int = 0
    dates: list[CountItem]
    announcement_types: list[CountItem]
    parse_statuses: list[CountItem]
    analysis_statuses: list[CountItem]
    ai_screen_statuses: list[CountItem] = []
    sentiments: list[CountItem]


class FilterOptions(BaseModel):
    dates: list[str]
    announcement_types: list[str]
    parse_statuses: list[str]
    analysis_statuses: list[str]
    ai_screen_statuses: list[str] = []
    sentiments: list[str]


class ParseResponse(BaseModel):
    announcement_id: int
    parse_status: str
    content_length: int
    error_message: str | None = None


class AnnouncementDetail(Announcement):
    content: str | None = None
    content_length: int = 0


class AnalysisRunRequest(BaseModel):
    limit: int = Field(default=500, ge=1, le=5000)
    date: str | None = Field(default=None, pattern=r"^\d{8}$")


class AnalysisRunResponse(BaseModel):
    requested: int
    analyzed: int
    failed: int


class ScreenRunRequest(BaseModel):
    limit: int = Field(default=500, ge=1, le=5000)
    date: str | None = Field(default=None, pattern=r"^\d{8}$")
    reset: bool = False


class ScreenRunResponse(BaseModel):
    requested: int
    screened: int
    failed: int


class AnalysisResult(BaseModel):
    announcement_id: int
    provider: str
    model: str
    summary: str
    sentiment: str
    importance_score: int
    risk_points: list[str]
    opportunities: list[str]
    watch_signals: list[str]
    action_suggestion: str = ""
    confidence: float
    reasoning_short: str
    not_investment_advice: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    announcement_id: int
    answer: str
    content_length: int
    content_preview: str
    provider: str
    model: str


class ChatMessage(BaseModel):
    id: int
    announcement_id: int
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    content_length: int = 0
    created_at: str


class ChatHistoryResponse(BaseModel):
    items: list[ChatMessage]


class CleanupOldRequest(BaseModel):
    days: int = Field(default=3, ge=1, le=30)


class CleanupDateRequest(BaseModel):
    date: str | None = Field(default=None, pattern=r"^\d{8}$")


class CleanupResponse(BaseModel):
    affected: int


class AnalysisJobStatus(BaseModel):
    running: bool
    cancel_requested: bool
    requested: int = 0
    analyzed: int = 0
    failed: int = 0
    current_id: int | None = None
    message: str = ""


class ModelSettings(BaseModel):
    provider: ProviderName = "mock"
    model: str = "mock-free-test"
    base_url: str | None = None
    api_key: str | None = None


class PublicModelSettings(BaseModel):
    provider: ProviderName
    model: str
    base_url: str | None = None
    has_api_key: bool
