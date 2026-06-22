from __future__ import annotations

import logging
import os
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .models import (
    AnalysisPromptPresetList,
    AnalysisPromptSettings,
    AnalysisResult,
    AnalysisJobStatus,
    AnalysisRunRequest,
    AnalysisRunResponse,
    AnnouncementDetail,
    AnnouncementListResponse,
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    CleanupDateRequest,
    CleanupOldRequest,
    CleanupResponse,
    DatabaseSummary,
    FetchAnnouncementsRequest,
    FetchAnnouncementsResponse,
    FilterOptions,
    ModelSettings,
    ParseResponse,
    PublicModelSettings,
    ScreenRunRequest,
    ScreenRunResponse,
)
from .repository import (
    cleanup_analyzed_content,
    cleanup_all_data,
    cleanup_old_announcements,
    cleanup_untracked_announcements,
    count_important_by_date,
    database_summary,
    filter_options,
    get_analysis,
    get_analysis_candidates,
    get_announcement,
    get_announcements_by_ids,
    get_screen_candidates,
    list_chat_messages,
    list_announcements,
    mark_analysis_status,
    mark_screen_status,
    reset_screening,
    save_chat_message,
    save_analysis,
    save_screen_result,
    update_parse_result,
    upsert_announcements,
)
from .services.akshare_client import fetch_announcements_by_date
from .services.llm import normalize_analysis, normalize_screen, provider_from_settings
from .services.parser import extract_announcement_text, should_reextract_content
from .services.rules import screen_by_title
from .services.settings import (
    get_analysis_prompt_settings,
    get_analysis_prompt_presets,
    get_model_settings,
    public_model_settings,
    save_analysis_prompt_presets,
    save_analysis_prompt_settings,
    save_model_settings,
)


app = FastAPI(title="StockAI", version="0.1.0")
logger = logging.getLogger("stockai")
analysis_job = {
    "running": False,
    "cancel_requested": False,
    "requested": 0,
    "analyzed": 0,
    "failed": 0,
    "current_id": None,
    "message": "",
}
analysis_lock = threading.Lock()


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):\d+"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/fetch-announcements", response_model=FetchAnnouncementsResponse)
def fetch_announcements(payload: FetchAnnouncementsRequest) -> FetchAnnouncementsResponse:
    items = fetch_announcements_by_date(payload.date)
    inserted, updated = upsert_announcements(items)
    _, screened, _ = _screen_announcements(payload.date, limit=max(len(items), 1), reset=True)
    return FetchAnnouncementsResponse(
        date=payload.date,
        fetched=len(items),
        inserted=inserted,
        updated=updated,
        important=count_important_by_date(payload.date),
        screened=screened,
    )


@app.get("/api/announcements", response_model=AnnouncementListResponse)
def announcements(
    date: str | None = Query(default=None, pattern=r"^\d{8}$"),
    code: str | None = None,
    announcement_type: str | None = None,
    important: bool | None = None,
    ai_worth_tracking: bool | None = None,
    ai_screen_status: str | None = None,
    analysis_status: str | None = None,
    parse_status: str | None = None,
    sentiment: str | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> AnnouncementListResponse:
    items, total = list_announcements(
        {
            "date": date,
            "code": code,
            "announcement_type": announcement_type,
            "important": important,
            "ai_worth_tracking": ai_worth_tracking,
            "ai_screen_status": ai_screen_status,
            "analysis_status": analysis_status,
            "parse_status": parse_status,
            "sentiment": sentiment,
            "keyword": keyword,
        },
        page,
        page_size,
    )
    return AnnouncementListResponse(items=items, total=total, page=page, page_size=page_size)


@app.get("/api/database/summary", response_model=DatabaseSummary)
def database() -> DatabaseSummary:
    return DatabaseSummary(**database_summary())


@app.post("/api/database/cleanup/old", response_model=CleanupResponse)
def cleanup_old(payload: CleanupOldRequest) -> CleanupResponse:
    return CleanupResponse(affected=cleanup_old_announcements(payload.days))


@app.post("/api/database/cleanup/untracked", response_model=CleanupResponse)
def cleanup_untracked(payload: CleanupDateRequest) -> CleanupResponse:
    return CleanupResponse(affected=cleanup_untracked_announcements(payload.date))


@app.post("/api/database/cleanup/content", response_model=CleanupResponse)
def cleanup_content() -> CleanupResponse:
    return CleanupResponse(affected=cleanup_analyzed_content())


@app.post("/api/database/cleanup/all", response_model=CleanupResponse)
def cleanup_all() -> CleanupResponse:
    return CleanupResponse(affected=cleanup_all_data())


@app.get("/api/filter-options", response_model=FilterOptions)
def options() -> FilterOptions:
    return FilterOptions(**filter_options())


@app.get("/api/announcements/{announcement_id}", response_model=AnnouncementDetail)
def announcement_detail(announcement_id: int) -> AnnouncementDetail:
    announcement = get_announcement(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    content = announcement.get("content") or ""
    announcement["content"] = content
    announcement["content_length"] = len(content)
    return AnnouncementDetail(**announcement)


@app.post("/api/announcements/{announcement_id}/parse", response_model=ParseResponse)
def parse_announcement(announcement_id: int) -> ParseResponse:
    announcement = get_announcement(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    update_parse_result(announcement_id, "running", None)
    try:
        content = extract_announcement_text(announcement["url"])
        status = "succeeded" if content else "parse_failed"
        update_parse_result(announcement_id, status, content, None if content else "No text extracted")
        return ParseResponse(announcement_id=announcement_id, parse_status=status, content_length=len(content))
    except Exception as exc:
        update_parse_result(announcement_id, "parse_failed", None, str(exc))
        return ParseResponse(announcement_id=announcement_id, parse_status="parse_failed", content_length=0, error_message=str(exc))


@app.post("/api/screen/run", response_model=ScreenRunResponse)
def run_screening(payload: ScreenRunRequest) -> ScreenRunResponse:
    requested, screened, failed = _screen_announcements(payload.date, payload.limit, payload.reset)
    return ScreenRunResponse(requested=requested, screened=screened, failed=failed)


def _screen_announcements(date: str | None, limit: int, reset: bool) -> tuple[int, int, int]:
    if reset:
        reset_screening(date)
    candidates = get_screen_candidates(limit, date)
    screened = 0
    failed = 0
    for announcement in candidates:
        announcement_id = announcement["id"]
        mark_screen_status(announcement_id, "running")
        try:
            result = screen_by_title(
                announcement["title"],
                announcement["announcement_type"],
                announcement.get("matched_keywords"),
            )
            save_screen_result(announcement_id, result)
            screened += 1
        except Exception as exc:
            failed += 1
            mark_screen_status(announcement_id, "failed", str(exc))
    return len(candidates), screened, failed


@app.post("/api/announcements/{announcement_id}/analyze", response_model=AnalysisResult)
def analyze_announcement(announcement_id: int) -> AnalysisResult:
    announcement = get_announcement(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    provider = provider_from_settings(get_model_settings())
    mark_analysis_status(announcement_id, "running")
    try:
        content = announcement.get("content")
        if should_reextract_content(content):
            content = extract_announcement_text(announcement["url"])
            update_parse_result(announcement_id, "succeeded" if content else "parse_failed", content, None if content else "No text extracted")
        analysis_data = normalize_analysis(provider.analyze(announcement, content or announcement["title"], get_analysis_prompt_settings()))
        save_analysis(announcement_id, provider.provider_name, provider.model, analysis_data)
        saved = get_analysis(announcement_id)
        if not saved:
            raise HTTPException(status_code=500, detail="Analysis was not saved")
        return AnalysisResult(**saved)
    except Exception as exc:
        logger.exception("Manual analysis failed for announcement_id=%s", announcement_id)
        mark_analysis_status(announcement_id, "failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analysis/auto/start", response_model=AnalysisJobStatus)
def start_auto_analysis(payload: AnalysisRunRequest) -> AnalysisJobStatus:
    with analysis_lock:
        if analysis_job["running"]:
            return AnalysisJobStatus(**analysis_job)
        analysis_job.update(
            {
                "running": True,
                "cancel_requested": False,
                "requested": 0,
                "analyzed": 0,
                "failed": 0,
                "current_id": None,
                "message": "分析任务启动中",
            }
        )
    thread = threading.Thread(target=_analysis_worker, args=(payload.date, payload.limit, payload.announcement_ids), daemon=True)
    thread.start()
    return AnalysisJobStatus(**analysis_job)


@app.post("/api/analysis/auto/cancel", response_model=AnalysisJobStatus)
def cancel_auto_analysis() -> AnalysisJobStatus:
    with analysis_lock:
        analysis_job["cancel_requested"] = True
        if analysis_job["running"]:
            analysis_job["message"] = "已请求取消，当前公告分析完成后停止"
        else:
            analysis_job["message"] = "当前没有运行中的分析任务"
        return AnalysisJobStatus(**analysis_job)


@app.get("/api/analysis/auto/status", response_model=AnalysisJobStatus)
def auto_analysis_status() -> AnalysisJobStatus:
    with analysis_lock:
        return AnalysisJobStatus(**analysis_job)


def _analysis_worker(target_date: str | None, limit: int, announcement_ids: list[int] | None = None) -> None:
    provider = provider_from_settings(get_model_settings())
    prompt_settings = get_analysis_prompt_settings()
    candidates = get_announcements_by_ids(announcement_ids) if announcement_ids else get_analysis_candidates(limit, target_date)
    with analysis_lock:
        analysis_job["requested"] = len(candidates)
        source = "选中公告" if announcement_ids else "AI 关注公告"
        analysis_job["message"] = f"待分析 {len(candidates)} 条 {source}"
    try:
        for announcement in candidates:
            with analysis_lock:
                if analysis_job["cancel_requested"]:
                    analysis_job["message"] = "分析已取消"
                    break
                analysis_job["current_id"] = announcement["id"]
            ok = _analyze_one(announcement, provider, prompt_settings)
            with analysis_lock:
                if ok:
                    analysis_job["analyzed"] += 1
                else:
                    analysis_job["failed"] += 1
        with analysis_lock:
            if not analysis_job["cancel_requested"]:
                analysis_job["message"] = "分析完成"
    finally:
        with analysis_lock:
            analysis_job["running"] = False
            analysis_job["current_id"] = None


def _analyze_one(announcement: dict, provider, prompt_settings: dict | None = None) -> bool:
    announcement_id = announcement["id"]
    mark_analysis_status(announcement_id, "running")
    try:
        content = announcement.get("content")
        if should_reextract_content(content):
            try:
                content = extract_announcement_text(announcement["url"])
            except Exception as exc:
                update_parse_result(announcement_id, "parse_failed", None, str(exc))
                raise
            update_parse_result(announcement_id, "succeeded" if content else "parse_failed", content, None if content else "No text extracted")
        analysis = normalize_analysis(provider.analyze(announcement, content or announcement["title"], prompt_settings))
        save_analysis(announcement_id, provider.provider_name, provider.model, analysis)
        return True
    except Exception as exc:
        logger.exception("Auto analysis failed for announcement_id=%s", announcement_id)
        mark_analysis_status(announcement_id, "failed", str(exc))
        return False


@app.post("/api/announcements/{announcement_id}/chat", response_model=ChatResponse)
def chat_with_announcement(announcement_id: int, payload: ChatRequest) -> ChatResponse:
    announcement = get_announcement(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    try:
        content = announcement.get("content")
        if should_reextract_content(content):
            try:
                content = extract_announcement_text(announcement["url"])
            except Exception as exc:
                update_parse_result(announcement_id, "parse_failed", None, str(exc))
                raise
            update_parse_result(announcement_id, "succeeded" if content else "parse_failed", content, None if content else "No text extracted")
        history = list_chat_messages(announcement_id, 12)
        provider = provider_from_settings(get_model_settings())
        save_chat_message(announcement_id, "user", payload.message, content_length=len(content or ""))
        answer = provider.chat(announcement, content or "", payload.message, history)
        save_chat_message(
            announcement_id,
            "assistant",
            answer,
            provider=provider.provider_name,
            model=provider.model,
            content_length=len(content or ""),
        )
        return ChatResponse(
            announcement_id=announcement_id,
            answer=answer,
            content_length=len(content or ""),
            content_preview=(content or "")[:800],
            provider=provider.provider_name,
            model=provider.model,
        )
    except Exception as exc:
        logger.exception("Chat failed for announcement_id=%s", announcement_id)
        update_parse_result(announcement_id, "parse_failed", None, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/announcements/{announcement_id}/chat", response_model=ChatHistoryResponse)
def chat_history(announcement_id: int) -> ChatHistoryResponse:
    if not get_announcement(announcement_id):
        raise HTTPException(status_code=404, detail="Announcement not found")
    return ChatHistoryResponse(items=list_chat_messages(announcement_id, 50))


@app.post("/api/analysis/run", response_model=AnalysisRunResponse)
def run_analysis(payload: AnalysisRunRequest) -> AnalysisRunResponse:
    provider = provider_from_settings(get_model_settings())
    prompt_settings = get_analysis_prompt_settings()
    candidates = get_announcements_by_ids(payload.announcement_ids) if payload.announcement_ids else get_analysis_candidates(payload.limit, payload.date)
    analyzed = 0
    failed = 0
    for announcement in candidates:
        announcement_id = announcement["id"]
        if _analyze_one(announcement, provider, prompt_settings):
            analyzed += 1
        else:
            failed += 1
    return AnalysisRunResponse(requested=len(candidates), analyzed=analyzed, failed=failed)


@app.get("/api/analysis/{announcement_id}", response_model=AnalysisResult)
def analysis(announcement_id: int) -> AnalysisResult:
    data = get_analysis(announcement_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisResult(**data)


@app.get("/api/settings/models", response_model=PublicModelSettings)
def get_models() -> PublicModelSettings:
    return PublicModelSettings(**public_model_settings())


@app.post("/api/settings/models", response_model=PublicModelSettings)
def save_models(payload: ModelSettings) -> PublicModelSettings:
    save_model_settings(payload.model_dump())
    return PublicModelSettings(**public_model_settings())


@app.get("/api/settings/analysis-prompt", response_model=AnalysisPromptSettings)
def get_analysis_prompt() -> AnalysisPromptSettings:
    return AnalysisPromptSettings(**get_analysis_prompt_settings())


@app.post("/api/settings/analysis-prompt", response_model=AnalysisPromptSettings)
def save_analysis_prompt(payload: AnalysisPromptSettings) -> AnalysisPromptSettings:
    return AnalysisPromptSettings(**save_analysis_prompt_settings(payload.model_dump()))


@app.get("/api/settings/analysis-prompts", response_model=AnalysisPromptPresetList)
def get_analysis_prompts() -> AnalysisPromptPresetList:
    return AnalysisPromptPresetList(**get_analysis_prompt_presets())


@app.post("/api/settings/analysis-prompts", response_model=AnalysisPromptPresetList)
def save_analysis_prompts(payload: AnalysisPromptPresetList) -> AnalysisPromptPresetList:
    return AnalysisPromptPresetList(**save_analysis_prompt_presets(payload.model_dump()))
