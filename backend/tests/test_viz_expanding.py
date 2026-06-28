import csv

from app.viz_expanding import generate, plot_skill_comparison


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


_COMPARISON = [
    {"horizon": 1, "knn_holdout": 0.03, "knn_expanding": 0.04,
     "xgb_holdout": 0.02, "xgb_expanding": 0.01},
    {"horizon": 7, "knn_holdout": 0.06, "knn_expanding": 0.07,
     "xgb_holdout": 0.14, "xgb_expanding": 0.13},
]


def test_plot_skill_comparison_writes_file(tmp_path):
    out = tmp_path / "skill.png"
    plot_skill_comparison(_COMPARISON, "KRW-BTC", out)
    assert out.exists() and out.stat().st_size > 0


def test_generate_expanding_without_lstm(tmp_path):
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())
    paths = generate(csv_path, market="KRW-BTC", out_dir=tmp_path,
                     comparison=_COMPARISON, include_lstm=False)
    assert paths["skill"].exists()
    assert paths["XGBoost"].exists() and paths["XGBoost"].stat().st_size > 0
    assert paths["KNN pattern"].exists()
    assert "LSTM" not in paths
