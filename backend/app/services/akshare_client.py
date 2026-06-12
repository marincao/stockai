from __future__ import annotations

from dataclasses import dataclass

from .rules import classify_importance


@dataclass(frozen=True)
class RawAnnouncement:
    code: str
    name: str
    title: str
    announcement_type: str
    announcement_date: str
    url: str
    source: str
    is_important: bool
    matched_keywords: list[str]


def fetch_announcements_by_date(date: str) -> list[RawAnnouncement]:
    import akshare as ak

    df = ak.stock_notice_report(symbol="全部", date=date)
    items: list[RawAnnouncement] = []
    for row in df.to_dict(orient="records"):
        title = str(row.get("公告标题", "")).strip()
        announcement_type = str(row.get("公告类型", "")).strip() or "未分类"
        is_important, matched_keywords = classify_importance(title, announcement_type)
        items.append(
            RawAnnouncement(
                code=str(row.get("代码", "")).strip(),
                name=str(row.get("名称", "")).strip(),
                title=title,
                announcement_type=announcement_type,
                announcement_date=normalize_date(str(row.get("公告日期", "")).strip()),
                url=str(row.get("网址", "")).strip(),
                source="eastmoney",
                is_important=is_important,
                matched_keywords=matched_keywords,
            )
        )
    return [item for item in items if item.url and item.title]


def normalize_date(value: str) -> str:
    return value.replace("-", "")
