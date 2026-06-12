from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    keyword: str
    event_type: str
    score: int
    reason: str


HIGH_PRIORITY_RULES = [
    Rule("退市", "退市风险", 95, "可能影响上市地位或交易风险"),
    Rule("被立案", "监管立案", 92, "监管调查通常需要优先关注"),
    Rule("立案调查", "监管立案", 92, "监管调查通常需要优先关注"),
    Rule("行政处罚", "监管处罚", 90, "处罚可能影响公司治理和市场预期"),
    Rule("重大资产重组", "资产重组", 90, "重大重组可能改变公司资产和盈利结构"),
    Rule("控制权变更", "控制权变更", 90, "控制权变化可能影响公司战略和治理"),
    Rule("要约收购", "收购并购", 88, "要约收购可能影响股权结构"),
    Rule("风险提示", "风险提示", 88, "公司主动提示风险，需要优先核查"),
    Rule("重大诉讼", "诉讼仲裁", 86, "重大诉讼可能影响利润、现金流或治理"),
    Rule("重大仲裁", "诉讼仲裁", 86, "重大仲裁可能影响利润、现金流或治理"),
    Rule("债务逾期", "债务风险", 86, "债务逾期可能反映流动性压力"),
    Rule("无法表示意见", "审计风险", 88, "审计意见异常是重大财务风险信号"),
    Rule("保留意见", "审计风险", 82, "审计意见异常需要进一步核查"),
]

MEDIUM_PRIORITY_RULES = [
    Rule("业绩预告", "业绩预告", 78, "业绩预告可能影响盈利预期"),
    Rule("业绩快报", "业绩快报", 74, "业绩快报反映最新经营结果"),
    Rule("年度报告", "定期报告", 70, "定期报告包含完整财务与经营信息"),
    Rule("季度报告", "定期报告", 66, "季度报告可用于观察经营趋势"),
    Rule("半年度报告", "定期报告", 68, "半年度报告可用于观察经营趋势"),
    Rule("重大合同", "重大合同", 76, "重大合同可能影响未来收入"),
    Rule("中标", "中标/订单", 72, "中标可能带来后续收入确认"),
    Rule("回购", "回购", 72, "回购可能反映公司资本安排或信心"),
    Rule("增持", "增持", 70, "重要股东增持可能影响市场预期"),
    Rule("减持", "减持", 76, "重要股东减持可能影响供给和预期"),
    Rule("定增", "再融资", 70, "再融资会影响资金结构和股本"),
    Rule("增发", "再融资", 70, "再融资会影响资金结构和股本"),
    Rule("担保", "担保", 68, "担保可能带来或有负债风险"),
    Rule("质押", "股权质押", 68, "股权质押可能反映股东资金压力"),
    Rule("问询函", "监管问询", 72, "监管问询通常指向披露或经营疑点"),
    Rule("利润分配", "分红", 58, "分红方案可作为资金回报信息"),
    Rule("分红", "分红", 58, "分红方案可作为资金回报信息"),
    Rule("股权激励", "股权激励", 58, "股权激励可能影响费用和团队约束"),
]

ROUTINE_KEYWORDS = [
    "召开股东会",
    "召开股东大会",
    "临时股东会",
    "董事会决议",
    "监事会决议",
    "独立董事",
    "公司章程",
    "办公地址",
    "联系方式",
    "投资者关系活动记录",
    "提示性公告",
    "更正公告",
]

IMPORTANT_TYPES = {
    "重大事项": 72,
    "财务报告": 68,
    "融资公告": 68,
    "风险提示": 86,
    "资产重组": 88,
    "持股变动": 70,
}

IMPORTANT_KEYWORDS = [rule.keyword for rule in [*HIGH_PRIORITY_RULES, *MEDIUM_PRIORITY_RULES]]


def classify_importance(title: str, announcement_type: str) -> tuple[bool, list[str]]:
    result = _score_title(title, announcement_type)
    return bool(result["worth_tracking"]), list(result["matched_keywords"])


def screen_by_title(title: str, announcement_type: str, matched_keywords: list[str] | None = None) -> dict[str, object]:
    result = _score_title(title, announcement_type)
    combined_keywords = list(dict.fromkeys([*(matched_keywords or []), *result["matched_keywords"]]))
    score = int(result["importance_score"])
    worth_tracking = bool(result["worth_tracking"])
    reason_parts = list(result["reason_parts"])

    if combined_keywords:
        reason_parts.insert(0, f"命中关键词：{', '.join(combined_keywords[:6])}")
    if not worth_tracking:
        reason_parts = ["未命中重大风险、业绩、重组、增减持、回购、重大合同等重点事件。"]

    return {
        "worth_tracking": worth_tracking,
        "importance_score": score,
        "event_type": result["event_type"],
        "reason": "；".join(reason_parts),
    }


def _score_title(title: str, announcement_type: str) -> dict[str, object]:
    haystack = f"{announcement_type} {title}"
    matched_keywords: list[str] = []
    reason_parts: list[str] = []
    event_type = announcement_type or "其他"
    score = 20

    for rule in HIGH_PRIORITY_RULES:
        if rule.keyword in haystack:
            matched_keywords.append(rule.keyword)
            reason_parts.append(rule.reason)
            event_type = rule.event_type
            score = max(score, rule.score)

    for rule in MEDIUM_PRIORITY_RULES:
        if rule.keyword in haystack:
            matched_keywords.append(rule.keyword)
            reason_parts.append(rule.reason)
            if score < rule.score:
                event_type = rule.event_type
            score = max(score, rule.score)

    type_score = IMPORTANT_TYPES.get(announcement_type)
    if type_score:
        matched_keywords.append(f"type:{announcement_type}")
        reason_parts.append(f"公告类型属于重点类型：{announcement_type}")
        score = max(score, type_score)

    routine_hits = [keyword for keyword in ROUTINE_KEYWORDS if keyword in haystack]
    if routine_hits and score < 75:
        score = min(score, 35)
        reason_parts.append(f"偏例行公告：{', '.join(routine_hits[:3])}")

    matched_keywords = list(dict.fromkeys(matched_keywords))
    worth_tracking = score >= 60
    return {
        "worth_tracking": worth_tracking,
        "importance_score": score,
        "event_type": event_type or "其他",
        "matched_keywords": matched_keywords,
        "reason_parts": reason_parts,
    }
