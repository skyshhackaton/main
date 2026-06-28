import pytest

pytest.importorskip("torch")

from app.train_common import load_candles_from_csv  # noqa: E402
from app.viz_models import compare_models, plot_model_comparison  # noqa: E402


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


def test_compare_models_and_plot(tmp_path):
    candles = _make_candles()
    grid = {"hidden": [8], "input_dense": [0], "dropout": [0.0], "lr": [0.01]}
    rows = compare_models(
        candles, horizons=(1, 7), train_ratio=0.7,
        lstm_window=10, lstm_grid=grid, lstm_epochs=5,
    )
    assert len(rows) == 2
    for r in rows:
        assert "knn_skill" in r and "xgb_skill" in r and "lstm_skill" in r

    out = tmp_path / "model_comparison.png"
    plot_model_comparison(rows, "KRW-BTC", out)
    assert out.exists() and out.stat().st_size > 0
