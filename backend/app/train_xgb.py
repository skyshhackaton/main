"""XGBoost FOMO Score 학습 + 하이퍼파라미터 튜닝 (오프라인 실험).

forecast_score의 피처(점수 lag + 시장 피처)로 horizon별 FOMO Score를 학습한다.
- train_xgb_fomo: 고정 파라미터 TimeSeriesSplit CV.
- tune_xgb_fomo: 하이퍼파라미터 격자를 TimeSeriesSplit CV로 탐색해 최고 설정 선정.
- evaluate_xgb_holdout: train/val 단일 분리 평가(모델 간 비교용, persistence 대비 skill).

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

from app.forecast_score import (
    DEFAULT_HORIZONS,
    DEFAULT_LAGS,
    MODEL_NAME,
    RANDOM_STATE,
    _build_supervised,
    _features_at,
    _new_model,
)
from app.knn_mirror import FEATURE_NAMES, build_feature_matrix
from app.train_common import (
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_N_SPLITS,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    DISCLAIMER,
    load_candles_from_csv,
    metrics,
)

try:  # 튜닝 대상 추정기 (xgboost 우선, 없으면 sklearn 폴백)
    from xgboost import XGBRegressor

    _HAS_XGB = True
except ImportError:  # pragma: no cover
    from sklearn.ensemble import GradientBoostingRegressor as XGBRegressor  # type: ignore

    _HAS_XGB = False

# XGBoost 하이퍼파라미터 격자 (시계열·표본 규모에 맞춘 보수적 범위).
XGB_PARAM_GRID = {
    "n_estimators": [200, 400],
    "max_depth": [2, 3, 4],
    "learning_rate": [0.05, 0.1],
    "subsample": [0.8, 1.0],
}


def _xgb_supervised(candles: list[dict], lags: int, horizon: int, days: int | None):
    """forecast_score와 동일한 피처(lag+시장)로 (X, y, feature_names) 구성."""
    days = days if days is not None else len(candles)
    fm = build_feature_matrix(candles, days=days)
    scores = [item["score"] for item in fm["series"]]
    X, y = _build_supervised(fm["matrix"], scores, lags, horizon)
    feature_names = [f"score_lag_{lags - 1 - j}" for j in range(lags)]
    feature_names += list(FEATURE_NAMES[1:])  # change_rate_1d, volume_ratio_5_20, rsi_14
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float), feature_names


def train_xgb_fomo(
    candles: list[dict],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lags: int = DEFAULT_LAGS,
    days: int | None = None,
    n_splits: int = DEFAULT_N_SPLITS,
) -> dict:
    """horizon별 FOMO Score 예측 모델 학습 + CV 평가 + 피처 중요도."""
    if lags < 1:
        raise ValueError("lags must be positive")
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must be positive integers")

    per_horizon: dict[str, dict] = {}
    for horizon in sorted(set(horizons)):
        X, y, feature_names = _xgb_supervised(candles, lags, horizon, days)
        n_samples = len(X)
        if n_samples <= n_splits + 1:
            per_horizon[str(horizon)] = {"n_samples": n_samples, "error": "insufficient_samples"}
            continue

        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_mae, fold_rmse = [], []
        for train_idx, test_idx in tscv.split(X):
            model = _new_model()
            model.fit(X[train_idx], y[train_idx])
            pred = np.clip(model.predict(X[test_idx]), 0.0, 100.0)
            mae, rmse = metrics(y[test_idx], pred)
            fold_mae.append(mae)
            fold_rmse.append(rmse)

        final = _new_model()
        final.fit(X, y)
        importances = getattr(final, "feature_importances_", None)
        importance_map = (
            {name: round(float(v), 4) for name, v in zip(feature_names, importances)}
            if importances is not None
            else None
        )
        baseline_mae = float(np.mean(np.abs(y - X[:, lags - 1])))
        per_horizon[str(horizon)] = {
            "n_samples": n_samples,
            "cv_mae": round(float(np.mean(fold_mae)), 4),
            "cv_rmse": round(float(np.mean(fold_rmse)), 4),
            "cv_mae_std": round(float(np.std(fold_mae)), 4),
            "baseline_persist_mae": round(baseline_mae, 4),
            "feature_importances": importance_map,
        }

    return {
        "model": MODEL_NAME,
        "lags": lags,
        "n_splits": n_splits,
        "feature_names": feature_names,
        "horizons": per_horizon,
    }


def tune_xgb_fomo(
    candles: list[dict],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lags: int = DEFAULT_LAGS,
    param_grid: dict | None = None,
    days: int | None = None,
    n_splits: int = DEFAULT_N_SPLITS,
) -> dict:
    """horizon별 XGBoost 하이퍼파라미터를 TimeSeriesSplit CV로 튜닝해 최고 설정 선정."""
    if lags < 1:
        raise ValueError("lags must be positive")
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must be positive integers")
    grid = param_grid or XGB_PARAM_GRID

    per_horizon: dict[str, dict] = {}
    for horizon in sorted(set(horizons)):
        X, y, feature_names = _xgb_supervised(candles, lags, horizon, days)
        n_samples = len(X)
        if n_samples <= n_splits + 1:
            per_horizon[str(horizon)] = {"n_samples": n_samples, "error": "insufficient_samples"}
            continue

        search = GridSearchCV(
            XGBRegressor(random_state=RANDOM_STATE),
            grid,
            scoring={"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error"},
            refit="mae",
            cv=TimeSeriesSplit(n_splits=n_splits),
            n_jobs=1,
        )
        search.fit(X, y)
        best = search.best_estimator_
        importances = getattr(best, "feature_importances_", None)
        importance_map = (
            {name: round(float(v), 4) for name, v in zip(feature_names, importances)}
            if importances is not None
            else None
        )
        bi = search.best_index_
        baseline_mae = float(np.mean(np.abs(y - X[:, lags - 1])))
        cv_mae = -float(search.best_score_)
        per_horizon[str(horizon)] = {
            "n_samples": n_samples,
            "best_params": search.best_params_,
            "cv_mae": round(cv_mae, 4),
            "cv_rmse": round(-float(search.cv_results_["mean_test_rmse"][bi]), 4),
            "baseline_persist_mae": round(baseline_mae, 4),
            "skill_vs_persist": round(1.0 - cv_mae / baseline_mae, 4) if baseline_mae > 0 else None,
            "feature_importances": importance_map,
        }

    return {
        "model": ("XGBRegressor" if _HAS_XGB else "GradientBoostingRegressor") + " (grid-tuned)",
        "lags": lags,
        "n_splits": n_splits,
        "param_grid": grid,
        "n_candidates": int(np.prod([len(v) for v in grid.values()])),
        "feature_names": feature_names,
        "horizons": per_horizon,
    }


def evaluate_xgb_holdout(
    candles: list[dict],
    horizon: int,
    lags: int = DEFAULT_LAGS,
    params: dict | None = None,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    days: int | None = None,
    collect: bool = False,
) -> dict:
    """단일 train/val 분리 평가 (모델 간 비교용). persistence 대비 skill 반환."""
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be in (0, 1)")
    X, y, _ = _xgb_supervised(candles, lags, horizon, days)
    n = len(X)
    split = int(n * train_ratio)
    if split < 5 or n - split < 1:
        return {"horizon": horizon, "val_mae": None, "persist_mae": None, "skill": None,
                "val_samples": max(0, n - split)}

    model = _new_model() if params is None else XGBRegressor(random_state=RANDOM_STATE, **params)
    model.fit(X[:split], y[:split])
    pred = np.clip(model.predict(X[split:]), 0.0, 100.0)
    val_mae, _ = metrics(y[split:], pred)
    persist_mae = float(np.mean(np.abs(X[split:, lags - 1] - y[split:])))
    skill = 1.0 - val_mae / persist_mae if persist_mae > 0 else None
    out = {
        "horizon": horizon,
        "val_samples": n - split,
        "val_mae": round(val_mae, 4),
        "persist_mae": round(persist_mae, 4),
        "skill": round(skill, 4) if skill is not None else None,
    }
    if collect:
        out["pred"] = [float(v) for v in pred]
        out["actual"] = [float(v) for v in y[split:]]
    return out


def forecast_xgb(
    candles: list[dict],
    horizons: tuple[int, ...] = (1, 3, 7, 14, 30),
    lags: int = DEFAULT_LAGS,
    params: dict | None = None,
    days: int | None = None,
) -> dict:
    """현재 시점에서 horizon별 FOMO Score 예측 (전체 데이터로 학습 후 최신 피처 예측)."""
    days = days if days is not None else len(candles)
    fm = build_feature_matrix(candles, days=days)
    scores = [item["score"] for item in fm["series"]]
    latest = np.asarray([_features_at(fm["matrix"], scores, len(scores) - 1, lags)], dtype=float)

    points = []
    for h in sorted(set(horizons)):
        X, y, _ = _xgb_supervised(candles, lags, h, days)
        model = _new_model() if params is None else XGBRegressor(random_state=RANDOM_STATE, **params)
        model.fit(X, y)
        pred = float(np.clip(model.predict(latest)[0], 0.0, 100.0))
        points.append({"horizon": h, "predicted_score": round(pred, 2)})
    return {"current_score": round(float(scores[-1]), 2), "horizons": points}


def run_xgb(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lags: int = DEFAULT_LAGS,
    n_splits: int = DEFAULT_N_SPLITS,
    tune: bool = True,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    fm = build_feature_matrix(candles, days=len(candles))
    report = {
        "market": market,
        "csv_path": str(csv_path),
        "n_candles": len(candles),
        "n_scored": len(fm["series"]),
        "xgboost_fomo_forecast": train_xgb_fomo(candles, horizons=horizons, lags=lags, n_splits=n_splits),
        "disclaimer": DISCLAIMER,
    }
    if tune:
        report["xgboost_tuned"] = tune_xgb_fomo(candles, horizons=horizons, lags=lags, n_splits=n_splits)
    return report


def format_report_md(report: dict) -> str:
    xgb = report["xgboost_fomo_forecast"]
    lines = [
        "# XGBoost FOMO 학습 리포트",
        "",
        f"- market: `{report['market']}`  ·  candles: {report['n_candles']} (scored: {report['n_scored']})",
        f"- 입력: `{report['csv_path']}`",
        "",
        f"## 1. 고정 파라미터 학습 ({xgb['model']})",
        f"lags={xgb['lags']} · TimeSeriesSplit({xgb['n_splits']})",
        "",
        "| horizon | samples | CV MAE | CV RMSE | baseline(유지) MAE |",
        "|---:|---:|---:|---:|---:|",
    ]
    for horizon, info in xgb["horizons"].items():
        if "error" in info:
            lines.append(f"| {horizon}d | {info['n_samples']} | - | - | (표본부족) |")
            continue
        lines.append(
            f"| {horizon}d | {info['n_samples']} | {info['cv_mae']} | "
            f"{info['cv_rmse']} | {info['baseline_persist_mae']} |"
        )

    tuned = report.get("xgboost_tuned")
    if tuned:
        lines += [
            "",
            f"## 2. 하이퍼파라미터 튜닝 ({tuned['model']}, {tuned['n_candidates']} combos)",
            f"lags={tuned['lags']} · TimeSeriesSplit({tuned['n_splits']}) · grid CV로 horizon별 최고 설정",
            "",
            "| horizon | CV MAE | CV RMSE | baseline MAE | skill | best params |",
            "|---:|---:|---:|---:|---:|---|",
        ]
        for horizon, info in tuned["horizons"].items():
            if "error" in info:
                lines.append(f"| {horizon}d | - | - | - | - | (표본부족) |")
                continue
            bp = ", ".join(f"{k}={v}" for k, v in sorted(info["best_params"].items()))
            skill = "-" if info["skill_vs_persist"] is None else f"{info['skill_vs_persist']:+.3f}"
            lines.append(
                f"| {horizon}d | {info['cv_mae']} | {info['cv_rmse']} | "
                f"{info['baseline_persist_mae']} | {skill} | {bp} |"
            )

    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="XGBoost FOMO Score 학습 + 튜닝 (CSV, 오프라인)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help=f"입력 CSV (기본: {DEFAULT_CSV})")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="마켓 코드 (기본: KRW-BTC)")
    parser.add_argument("--n-splits", type=int, default=DEFAULT_N_SPLITS, help="TimeSeriesSplit fold 수")
    parser.add_argument("--no-tune", action="store_true", help="하이퍼파라미터 튜닝 생략")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"출력 디렉터리 (기본: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    report = run_xgb(
        csv_path=Path(args.csv), market=args.market, n_splits=args.n_splits, tune=not args.no_tune
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "xgb_training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = format_report_md(report)
    (out_dir / "xgb_training_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\n저장: {out_dir / 'xgb_training_report.json'}\n      {out_dir / 'xgb_training_report.md'}")


if __name__ == "__main__":
    main()
