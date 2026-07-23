from fastapi.testclient import TestClient

from backend.app.db import init_db
from backend.app.main import app


def test_research_report_list_and_detail(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKAI_DB_PATH", str(tmp_path / "stockai.db"))
    init_db()
    client = TestClient(app)

    upload = client.post(
        "/api/research-reports",
        json={
            "report_name": "sample-report.pdf",
            "translated_text": "第一段\n\n第二段",
            "source": "visionalpha",
        },
    )
    assert upload.status_code == 200
    report_id = upload.json()["id"]

    listing = client.get("/api/research-reports")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["report_name"] == "sample-report.pdf"
    assert listing.json()["items"][0]["analysis_status"] == "pending"
    assert "translated_text" not in listing.json()["items"][0]

    detail = client.get(f"/api/research-reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["translated_text"] == "第一段\n\n第二段"

    missing = client.get("/api/research-reports/999")
    assert missing.status_code == 404

    deleted = client.delete(f"/api/research-reports/{report_id}")
    assert deleted.status_code == 200
    assert deleted.json()["affected"] == 1
    assert client.get("/api/research-reports").json()["total"] == 0
