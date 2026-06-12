from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from .db import get_connection, row_to_dict
from .services.akshare_client import RawAnnouncement


def upsert_announcements(items: list[RawAnnouncement]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    with get_connection() as conn:
        for item in items:
            exists = conn.execute(
                """
                SELECT id FROM announcements
                WHERE url = ? AND code = ? AND title = ? AND announcement_date = ?
                """,
                (item.url, item.code, item.title, item.announcement_date),
            ).fetchone()
            params = (
                item.code,
                item.name,
                item.title,
                item.announcement_type,
                item.announcement_date,
                item.url,
                item.source,
                int(item.is_important),
                json.dumps(item.matched_keywords, ensure_ascii=False),
            )
            if exists:
                conn.execute(
                    """
                    UPDATE announcements SET
                        name = ?,
                        announcement_type = ?,
                        is_important = ?,
                        matched_keywords = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (item.name, item.announcement_type, int(item.is_important), json.dumps(item.matched_keywords, ensure_ascii=False), exists["id"]),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO announcements (
                        code, name, title, announcement_type, announcement_date,
                        url, source, is_important, matched_keywords
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                inserted += 1
    return inserted, updated


def count_important_by_date(date: str) -> int:
    normalized_date = _normalize_date(date)
    with get_connection() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM announcements WHERE announcement_date = ? AND is_important = 1",
                (normalized_date,),
            ).fetchone()["count"]
        )


def list_announcements(filters: dict[str, Any], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = []
    params: list[Any] = []
    joins = ""
    if filters.get("date"):
        where.append("announcement_date = ?")
        params.append(_normalize_date(filters["date"]))
    if filters.get("code"):
        where.append("code = ?")
        params.append(filters["code"])
    if filters.get("announcement_type"):
        where.append("announcement_type = ?")
        params.append(filters["announcement_type"])
    if filters.get("important") is not None:
        where.append("is_important = ?")
        params.append(1 if filters["important"] else 0)
    if filters.get("ai_worth_tracking") is not None:
        where.append("ai_worth_tracking = ?")
        params.append(1 if filters["ai_worth_tracking"] else 0)
    if filters.get("ai_screen_status"):
        where.append("ai_screen_status = ?")
        params.append(filters["ai_screen_status"])
    if filters.get("analysis_status"):
        where.append("analysis_status = ?")
        params.append(filters["analysis_status"])
    if filters.get("parse_status"):
        where.append("parse_status = ?")
        params.append(filters["parse_status"])
    if filters.get("sentiment"):
        joins = "LEFT JOIN analyses ON analyses.announcement_id = announcements.id"
        where.append("analyses.sentiment = ?")
        params.append(filters["sentiment"])
    if filters.get("keyword"):
        where.append("(title LIKE ? OR name LIKE ? OR code LIKE ?)")
        keyword = f"%{filters['keyword']}%"
        params.extend([keyword, keyword, keyword])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM announcements {joins} {where_sql}", params).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT announcements.*, substr(content, 1, 240) AS content_preview
            FROM announcements
            {joins}
            {where_sql}
            ORDER BY announcement_date DESC, announcements.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return [_deserialize_announcement(row_to_dict(row) or {}) for row in rows], int(total)


def get_announcement(announcement_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM announcements WHERE id = ?", (announcement_id,)).fetchone()
    data = row_to_dict(row)
    return _deserialize_announcement(data) if data else None


def update_parse_result(announcement_id: int, status: str, content: str | None, error_message: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE announcements SET
                parse_status = ?,
                content = COALESCE(?, content),
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, content, error_message, announcement_id),
        )


def mark_analysis_status(announcement_id: int, status: str, error_message: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE announcements SET
                analysis_status = ?,
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error_message, announcement_id),
        )


def mark_screen_status(announcement_id: int, status: str, error_message: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE announcements SET
                ai_screen_status = ?,
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error_message, announcement_id),
        )


def get_screen_candidates(limit: int, date: str | None = None) -> list[dict[str, Any]]:
    where_date = "AND announcement_date = ?" if date else ""
    params: list[Any] = []
    if date:
        params.append(_normalize_date(date))
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM announcements
            WHERE ai_screen_status IN ('pending', 'failed')
            {where_date}
            ORDER BY announcement_date DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_deserialize_announcement(row_to_dict(row) or {}) for row in rows]


def reset_screening(date: str | None = None) -> int:
    where = ""
    params: list[Any] = []
    if date:
        where = "WHERE announcement_date = ?"
        params.append(_normalize_date(date))
    with get_connection() as conn:
        cursor = conn.execute(
            f"""
            UPDATE announcements
            SET ai_screen_status = 'pending',
                ai_worth_tracking = NULL,
                ai_importance_score = NULL,
                ai_event_type = NULL,
                ai_screen_reason = NULL,
                updated_at = CURRENT_TIMESTAMP
            {where}
            """,
            params,
        )
        return int(cursor.rowcount)


def save_screen_result(announcement_id: int, result: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE announcements SET
                ai_screen_status = 'succeeded',
                ai_worth_tracking = ?,
                ai_importance_score = ?,
                ai_event_type = ?,
                ai_screen_reason = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                1 if result["worth_tracking"] else 0,
                result["importance_score"],
                result["event_type"],
                result["reason"],
                announcement_id,
            ),
        )


def get_analysis_candidates(limit: int, target_date: str | None = None) -> list[dict[str, Any]]:
    where_date = "AND announcement_date = ?" if target_date else ""
    params: list[Any] = []
    if target_date:
        params.append(_normalize_date(target_date))
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM announcements
            WHERE COALESCE(ai_worth_tracking, 0) = 1
              AND analysis_status IN ('pending', 'failed')
            {where_date}
            ORDER BY announcement_date DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_deserialize_announcement(row_to_dict(row) or {}) for row in rows]


def save_analysis(announcement_id: int, provider: str, model: str, analysis: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO analyses (
                announcement_id, provider, model, summary, sentiment, importance_score,
                risk_points, opportunities, watch_signals, action_suggestion, confidence,
                reasoning_short, not_investment_advice, raw_response
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(announcement_id) DO UPDATE SET
                provider = excluded.provider,
                model = excluded.model,
                summary = excluded.summary,
                sentiment = excluded.sentiment,
                importance_score = excluded.importance_score,
                risk_points = excluded.risk_points,
                opportunities = excluded.opportunities,
                watch_signals = excluded.watch_signals,
                action_suggestion = excluded.action_suggestion,
                confidence = excluded.confidence,
                reasoning_short = excluded.reasoning_short,
                not_investment_advice = excluded.not_investment_advice,
                raw_response = excluded.raw_response,
                created_at = CURRENT_TIMESTAMP
            """,
            (
                announcement_id,
                provider,
                model,
                analysis["summary"],
                analysis["sentiment"],
                analysis["importance_score"],
                json.dumps(analysis["risk_points"], ensure_ascii=False),
                json.dumps(analysis["opportunities"], ensure_ascii=False),
                json.dumps(analysis["watch_signals"], ensure_ascii=False),
                analysis.get("action_suggestion", ""),
                analysis["confidence"],
                analysis["reasoning_short"],
                analysis["not_investment_advice"],
                json.dumps(analysis, ensure_ascii=False),
            ),
        )
        conn.execute(
            "UPDATE announcements SET analysis_status = 'succeeded', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (announcement_id,),
        )


def get_analysis(announcement_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE announcement_id = ?", (announcement_id,)).fetchone()
    data = row_to_dict(row)
    if not data:
        return None
    for key in ("risk_points", "opportunities", "watch_signals"):
        data[key] = json.loads(data[key])
    data["action_suggestion"] = data.get("action_suggestion") or ""
    return data


def list_chat_messages(announcement_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT *
                FROM chat_messages
                WHERE announcement_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (announcement_id, limit),
        ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def save_chat_message(
    announcement_id: int,
    role: str,
    content: str,
    provider: str | None = None,
    model: str | None = None,
    content_length: int = 0,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages(announcement_id, role, content, provider, model, content_length)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (announcement_id, role, content, provider, model, content_length),
        )


def cleanup_old_announcements(days: int = 3) -> int:
    cutoff = (date.today() - timedelta(days=days - 1)).strftime("%Y%m%d")
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM announcements WHERE announcement_date < ?", (cutoff,))
        return int(cursor.rowcount)


def cleanup_untracked_announcements(target_date: str | None = None) -> int:
    where = "WHERE COALESCE(ai_worth_tracking, 0) != 1"
    params: list[Any] = []
    if target_date:
        where += " AND announcement_date = ?"
        params.append(_normalize_date(target_date))
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM announcements {where}", params)
        return int(cursor.rowcount)


def cleanup_analyzed_content() -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE announcements
            SET content = NULL,
                parse_status = 'pending',
                updated_at = CURRENT_TIMESTAMP
            WHERE analysis_status = 'succeeded'
              AND content IS NOT NULL
              AND content != ''
            """
        )
        return int(cursor.rowcount)


def cleanup_all_data() -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM announcements")
        return int(cursor.rowcount)


def database_summary() -> dict[str, Any]:
    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_announcements,
                SUM(CASE WHEN is_important = 1 THEN 1 ELSE 0 END) AS important_announcements,
                SUM(CASE WHEN ai_worth_tracking = 1 THEN 1 ELSE 0 END) AS ai_tracking_announcements,
                SUM(CASE WHEN analysis_status = 'succeeded' THEN 1 ELSE 0 END) AS analyzed_announcements,
                SUM(CASE WHEN parse_status = 'succeeded' THEN 1 ELSE 0 END) AS parsed_announcements,
                SUM(CASE WHEN content IS NOT NULL AND content != '' THEN 1 ELSE 0 END) AS content_announcements
            FROM announcements
            """
        ).fetchone()
        chat_total = conn.execute("SELECT COUNT(*) AS count FROM chat_messages").fetchone()
        return {
            "total_announcements": int(totals["total_announcements"] or 0),
            "important_announcements": int(totals["important_announcements"] or 0),
            "ai_tracking_announcements": int(totals["ai_tracking_announcements"] or 0),
            "analyzed_announcements": int(totals["analyzed_announcements"] or 0),
            "parsed_announcements": int(totals["parsed_announcements"] or 0),
            "content_announcements": int(totals["content_announcements"] or 0),
            "chat_messages": int(chat_total["count"] or 0),
            "dates": _count_items(conn, "announcement_date", "announcements", "announcement_date DESC", 30),
            "announcement_types": _count_items(conn, "announcement_type", "announcements", "count DESC", 30),
            "parse_statuses": _count_items(conn, "parse_status", "announcements", "count DESC", 10),
            "analysis_statuses": _count_items(conn, "analysis_status", "announcements", "count DESC", 10),
            "ai_screen_statuses": _count_items(conn, "ai_screen_status", "announcements", "count DESC", 10),
            "sentiments": _count_items(conn, "sentiment", "analyses", "count DESC", 10),
        }


def filter_options() -> dict[str, list[str]]:
    with get_connection() as conn:
        return {
            "dates": _distinct_values(conn, "announcement_date", "announcements", "announcement_date DESC"),
            "announcement_types": _distinct_values(conn, "announcement_type", "announcements", "announcement_type ASC"),
            "parse_statuses": _distinct_values(conn, "parse_status", "announcements", "parse_status ASC"),
            "analysis_statuses": _distinct_values(conn, "analysis_status", "announcements", "analysis_status ASC"),
            "ai_screen_statuses": _distinct_values(conn, "ai_screen_status", "announcements", "ai_screen_status ASC"),
            "sentiments": _distinct_values(conn, "sentiment", "analyses", "sentiment ASC"),
        }


def _deserialize_announcement(data: dict[str, Any]) -> dict[str, Any]:
    data["is_important"] = bool(data.get("is_important"))
    if data.get("ai_worth_tracking") is not None:
        data["ai_worth_tracking"] = bool(data.get("ai_worth_tracking"))
    data["matched_keywords"] = json.loads(data.get("matched_keywords") or "[]")
    return data


def _normalize_date(value: str) -> str:
    return value.replace("-", "")


def _count_items(conn: Any, column: str, table: str, order_by: str, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT {column} AS name, COUNT(*) AS count
        FROM {table}
        WHERE {column} IS NOT NULL AND {column} != ''
        GROUP BY {column}
        ORDER BY {order_by}
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{"name": row["name"], "count": int(row["count"])} for row in rows]


def _distinct_values(conn: Any, column: str, table: str, order_by: str) -> list[str]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT {column} AS value
        FROM {table}
        WHERE {column} IS NOT NULL AND {column} != ''
        ORDER BY {order_by}
        """
    ).fetchall()
    return [str(row["value"]) for row in rows]
