from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


FORBIDDEN_INVESTMENT_WORDS = ("사세요", "파세요", "매수 기회", "매도 신호", "수익 보장")


def _make_candles(length: int = 430) -> list[dict]:
    candles = []
    for i in range(length):
        close = 100.0 + (i % 20)
        candles.append(
            {
                "date_utc": f"2025-01-{(i % 28) + 1:02d}T00:00:00-{i:03d}",
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100.0 + (i % 7),
            }
        )
    return candles


def test_historical_mirror_endpoint(monkeypatch):
    monkeypatch.setattr(main, "load_candles", lambda market: _make_candles())

    response = client.get("/api/historical-mirror?market=KRW-BTC&tolerance=100&days=30&max_periods=3")

    assert response.status_code == 200
    data = response.json()
    assert data["market"] == "KRW-BTC"
    assert len(data["similar_periods"]) == 3
    assert "미래 성과를 보장하지 않습니다" in data["disclaimer"]


def test_decision_pause_endpoint_uses_reflection_language():
    response = client.get("/api/decision-pause")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 3
    assert "투자 추천" in data["disclaimer"]

    combined_questions = " ".join(item["question"] for item in data["items"])
    assert "확인" in combined_questions or "점검" in combined_questions
    assert not any(word in combined_questions for word in FORBIDDEN_INVESTMENT_WORDS)


def test_mvp_overview_endpoint_returns_demo_flow(monkeypatch):
    monkeypatch.setattr(main, "load_candles", lambda market: _make_candles())

    response = client.get(
        "/api/mvp-overview?market=KRW-BTC&history_days=20&mirror_days=30&tolerance=100&max_periods=3"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["market"] == "KRW-BTC"
    assert 0 <= data["current"]["score"] <= 100
    assert len(data["history"]["items"]) == 20
    assert len(data["historical_mirror"]["similar_periods"]) == 3
    assert len(data["decision_pause"]["items"]) >= 3
    assert "투자 추천" in data["disclaimer"]
    assert "미래 성과를 보장하지 않습니다" in data["history_disclaimer"]


def test_mvp_overview_endpoint_rejects_invalid_args(monkeypatch):
    monkeypatch.setattr(main, "load_candles", lambda market: _make_candles())

    response = client.get("/api/mvp-overview?market=KRW-BTC&history_days=0")
    assert response.status_code == 400
    assert response.json()["detail"] == "history_days must be positive"

    response = client.get("/api/mvp-overview?market=KRW-BTC&mirror_days=0")
    assert response.status_code == 400
    assert response.json()["detail"] == "days must be positive"


def test_historical_mirror_endpoint_rejects_invalid_args(monkeypatch):
    monkeypatch.setattr(main, "load_candles", lambda market: _make_candles())

    response = client.get("/api/historical-mirror?market=KRW-BTC&tolerance=-1")

    assert response.status_code == 400
    assert response.json()["detail"] == "tolerance must be non-negative"


def test_missing_market_data_returns_404(monkeypatch):
    monkeypatch.setattr(main, "load_candles", lambda market: [])

    response = client.get("/api/historical-mirror?market=KRW-NONE")

    assert response.status_code == 404
    assert "캔들 데이터가 없습니다" in response.json()["detail"]
