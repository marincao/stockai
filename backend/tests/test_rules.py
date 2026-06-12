from app.services.akshare_client import normalize_date
from app.services.rules import classify_importance, screen_by_title


def test_keywords_mark_important() -> None:
    important, keywords = classify_importance("关于签订重大合同的公告", "重大事项")
    assert important is True
    assert "重大合同" in keywords
    assert "type:重大事项" in keywords


def test_plain_notice_is_not_important() -> None:
    important, keywords = classify_importance("关于召开投资者交流会的公告", "其他")
    assert important is False
    assert keywords == []


def test_high_risk_notice_gets_high_score() -> None:
    result = screen_by_title("关于公司股票可能被终止上市暨退市风险提示公告", "风险提示")
    assert result["worth_tracking"] is True
    assert result["importance_score"] >= 88
    assert result["event_type"] == "退市风险"


def test_routine_notice_is_downgraded() -> None:
    result = screen_by_title("关于召开2026年第一次临时股东会的通知", "其他")
    assert result["worth_tracking"] is False
    assert result["importance_score"] <= 35


def test_akshare_date_is_normalized() -> None:
    assert normalize_date("2026-06-09") == "20260609"
    assert normalize_date("20260609") == "20260609"
