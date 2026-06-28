import csv

import pytest

pytest.importorskip("torch")

import app.viz_validation as vv  # noqa: E402


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


def test_generate_best_skill_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(vv, "HORIZONS", (1, 7))
    monkeypatch.setitem(vv.LSTM_CFG, "epochs", 5)
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())

    out = vv.generate(csv_path, market="KRW-BTC", out_dir=tmp_path, train_ratio=0.7)

    assert set(out) == {"KNN pattern", "XGBoost", "LSTM"}
    for info in out.values():
        assert info["best_horizon"] in (1, 7)
        assert info["path"].exists() and info["path"].stat().st_size > 0
