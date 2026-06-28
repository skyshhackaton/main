import numpy as np
import pytest

pytest.importorskip("torch")  # LSTM 실험은 torch 설치 시에만 실행

from app.knn_pattern import fomo_score_series  # noqa: E402
from app.lstm_fomo import build_sequences, run_lstm, train_lstm  # noqa: E402


def _make_candles(length: int = 430) -> list[dict]:
    candles = []
    for i in range(length):
        close = 100.0 + (i % 20) + (i % 7) * 0.3
        candles.append(
            {
                "date_utc": f"2024-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00-{i:04d}",
                "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
                "close": close, "volume": 100.0 + (i % 9),
            }
        )
    return candles


def test_build_sequences_alignment():
    scores = np.arange(20.0)
    X, y, ends = build_sequences(scores, window=5, horizon=3)
    assert X.shape[1] == 5
    assert len(X) == len(y) == len(ends)
    # 첫 시퀀스: e=4, 타깃 = scores[4+3]=7
    assert list(X[0]) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert y[0] == 7.0
    assert ends[0] == 4


def test_train_lstm_returns_metrics_and_is_deterministic():
    scores, _ = fomo_score_series(_make_candles())
    kw = dict(window=10, horizon=1, hidden=8, epochs=5, train_ratio=0.7)
    a = train_lstm(scores, **kw)
    b = train_lstm(scores, **kw)

    assert a["val_mae"] >= 0 and a["persist_mae"] >= 0
    assert a["train_samples"] + a["val_samples"] == len(build_sequences(scores, 10, 1)[0])
    assert a["skill"] is not None
    assert a["val_mae"] == b["val_mae"]  # seed 고정 → 재현


def test_train_lstm_rejects_bad_args():
    scores, _ = fomo_score_series(_make_candles())
    with pytest.raises(ValueError):
        train_lstm(scores, window=1)
    with pytest.raises(ValueError):
        train_lstm(scores, horizon=0)
    with pytest.raises(ValueError):
        train_lstm(scores, train_ratio=1.0)


def test_run_lstm_end_to_end(tmp_path):
    import csv
    cols = ["market", "date_utc", "date_kst", "open", "high", "low",
            "close", "volume", "trade_price", "source", "crawled_at"]
    csv_path = tmp_path / "hist.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in _make_candles():
            w.writerow({"market": "KRW-BTC", "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                        "open": c["open"], "high": c["high"], "low": c["low"],
                        "close": c["close"], "volume": c["volume"],
                        "trade_price": c["close"], "source": "t", "crawled_at": "now"})
    report = run_lstm(csv_path, market="KRW-BTC", window=10,
                      horizons=(1, 7), hidden=8, epochs=5)
    assert len(report["results"]) == 2
    assert "심리 상태값" in report["disclaimer"]
