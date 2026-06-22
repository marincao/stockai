from app.services.llm import MockProvider, normalize_analysis


def test_mock_provider_returns_required_shape() -> None:
    provider = MockProvider()
    result = provider.analyze(
        {
            "code": "000001",
            "name": "平安银行",
            "title": "关于回购股份的公告",
            "announcement_type": "重大事项",
            "announcement_date": "20260610",
            "is_important": True,
        },
        "公告正文",
    )
    normalized = normalize_analysis(result)
    assert normalized["output_format"] == "free"
    assert normalized["free_output"]
