import numpy as np

from app.viz_final import COLOR, _best_horizon, _blend, _knn_forecast, _stitched
from app.train_common import fomo_scores


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


def test_best_horizon_picks_max():
    comp = [
        {"horizon": 7, "xgb_holdout": 0.10},
        {"horizon": 14, "xgb_holdout": 0.23},
        {"horizon": 30, "xgb_holdout": 0.21},
    ]
    assert _best_horizon(comp, "xgb_holdout") == 14


def test_knn_forecast_panel_writes_png(tmp_path):
    candles = _make_candles()
    scores = fomo_scores(candles)
    out = tmp_path / "knn_forecast.png"
    _knn_forecast(candles, scores, "KRW-BTC", out)
    assert out.exists() and out.stat().st_size > 0


def test_blend_aligns_and_scores():
    scores = np.arange(0.0, 60.0)
    # XGB/LSTM 예측을 target 시점으로 정렬해 평균
    tix = [40, 41, 42]
    st, skill = _blend(tix, [10.0, 12.0, 14.0], tix, [20.0, 22.0, 24.0], scores, horizon=5)
    assert st["target_index"] == tix
    assert st["pred"] == [15.0, 17.0, 19.0]  # (x+l)/2
    assert isinstance(skill, float)


def test_stitched_panel_writes_png(tmp_path):
    scores = fomo_scores(_make_candles())
    ti = list(range(len(scores) - 30, len(scores)))
    stitched = {"target_index": ti, "pred": [float(scores[i]) for i in ti]}
    out = tmp_path / "ens_stitched.png"
    _stitched("앙상블 XGBoost+LSTM", COLOR["ENS"], scores, stitched, 14, 0.21,
              "holdout(1회 학습)", "KRW-BTC", out)
    assert out.exists() and out.stat().st_size > 0
