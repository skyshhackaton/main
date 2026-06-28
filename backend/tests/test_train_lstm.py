import csv

import numpy as np
import pytest

pytest.importorskip("torch")  # LSTM 실험은 torch 설치 시에만 실행

from app.train_common import fomo_scores  # noqa: E402
from app.train_lstm import build_sequences, run_lstm, train_lstm, tune_lstm  # noqa: E402


def _make_candles(length: int = 460) -> list[dict]:
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


def _write_csv(path, candles, market="KRW-BTC"):
    cols = ["market", "date_utc", "date_kst", "open", "high", "low",
            "close", "volume", "trade_price", "source", "crawled_at"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in candles:
            w.writerow({"market": market, "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                        "open": c["open"], "high": c["high"], "low": c["low"],
                        "close": c["close"], "volume": c["volume"],
                        "trade_price": c["close"], "source": "t", "crawled_at": "now"})


def test_build_sequences_alignment():
    scores = np.arange(20.0)
    X, y, ends = build_sequences(scores, window=5, horizon=3)
    assert X.shape[1] == 5
    assert list(X[0]) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert y[0] == 7.0 and ends[0] == 4


def test_train_lstm_deterministic_and_input_dense():
    scores = fomo_scores(_make_candles())
    kw = dict(window=10, horizon=1, hidden=8, input_dense=4, epochs=5, train_ratio=0.7)
    a = train_lstm(scores, **kw)
    b = train_lstm(scores, **kw)
    assert a["val_mae"] >= 0 and a["persist_mae"] >= 0
    assert a["val_mae"] == b["val_mae"]  # seed 고정 → 재현
    assert a["n_params"] > 0


def test_train_lstm_rejects_bad_args():
    scores = fomo_scores(_make_candles())
    with pytest.raises(ValueError):
        train_lstm(scores, window=1)
    with pytest.raises(ValueError):
        train_lstm(scores, horizon=0)
    with pytest.raises(ValueError):
        train_lstm(scores, train_ratio=1.0)


def test_tune_lstm_selects_best():
    scores = fomo_scores(_make_candles())
    grid = {"hidden": [8], "input_dense": [0, 4], "dropout": [0.0], "lr": [0.01]}
    result = tune_lstm(scores, horizon=1, window=10, param_grid=grid, epochs=5)
    assert result["n_candidates"] == 2
    assert result["best"]["val_mae"] == min(r["val_mae"] for r in result["results"])


def test_run_lstm_end_to_end(tmp_path):
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())
    report = run_lstm(csv_path, market="KRW-BTC", window=10, horizons=(1, 7), epochs=5, tune=False)
    assert len(report["results"]) == 2
    assert "심리 상태값" in report["disclaimer"]
