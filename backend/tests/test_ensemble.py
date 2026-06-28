import csv

import pytest

pytest.importorskip("torch")  # 앙상블에 LSTM 포함

from app.ensemble import MODELS, ensemble_at, plot_ensemble, run_ensemble  # noqa: E402
from app.train_common import fomo_scores  # noqa: E402


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


def test_models_are_xgb_and_lstm_only():
    assert set(MODELS) == {"XGB", "LSTM"}  # KNN 제외


def test_ensemble_at_blends_two_models(monkeypatch):
    import app.ensemble as ens
    monkeypatch.setitem(ens.LSTM_CFG, "epochs", 5)
    scores = fomo_scores(_make_candles())
    res = ensemble_at(_make_candles(), scores, horizon=3, mode="holdout")
    assert res is not None
    assert set(res["individual"]) == {"XGB", "LSTM"}
    assert res["n_aligned"] >= 5
    assert res["equal"] is not None and res["weighted"] is not None
    assert abs(sum(res["weights"].values()) - 1.0) < 1e-6


def test_run_ensemble_and_plot(tmp_path, monkeypatch):
    import app.ensemble as ens
    monkeypatch.setitem(ens.LSTM_CFG, "epochs", 5)
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())
    report = run_ensemble(csv_path, market="KRW-BTC", horizons=(1, 7), mode="holdout")
    assert len(report["results"]) >= 1
    out = tmp_path / "ens.png"
    plot_ensemble(report, out)
    assert out.exists() and out.stat().st_size > 0
