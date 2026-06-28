"""KNN k 최적화 + XGBoost FOMO Score 학습 (오프라인 실험).

`data/upbit_candles_snapshot.csv`(data-handoff CSV 계약)를 입력으로 받아 두 가지를
수행한다.

1. KNN k 최적화
   - 피처는 knn-integration-contract의 4피처
     [fomo_score, change_rate_1d, volume_ratio_5_20, rsi_14].
   - Pipeline(StandardScaler -> KNeighborsRegressor)을 TimeSeriesSplit 교차검증으로
     평가해, 다음 시점 FOMO Score를 가장 잘 맞히는 k를 고른다.
   - 스케일러를 fold별로 학습해 룩어헤드/누수를 피한다.

2. XGBoost FOMO Score 학습
   - forecast_score의 피처(점수 lag + 시장 피처)와 동일 구성으로 horizon별
     (기본 1/3/7일) FOMO Score를 학습/평가한다.
   - TimeSeriesSplit CV 지표(MAE/RMSE/R2) + 워크포워드 MAE + 피처 중요도를 리포트.

**중요(compliance):** 학습/예측 대상은 가격·수익률이 아니라 시장 심리 상태값인
FOMO Score다. 결과는 모델 성능 참고치이며 투자 추천·수익 예측이 아니다.

MVP rule: 네트워크 호출 없음. 이미 공유된 CSV만 읽는다.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.forecast_score import (
    DEFAULT_HORIZONS,
    DEFAULT_LAGS,
    MODEL_NAME,
    RANDOM_STATE,
    _build_supervised,
    _new_model,
)
from app.knn_mirror import FEATURE_NAMES, build_feature_matrix

try:  # 튜닝 대상 추정기 (xgboost 우선, 없으면 sklearn 폴백)
    from xgboost import XGBRegressor

    _HAS_XGB = True
except ImportError:  # pragma: no cover
    from sklearn.ensemble import GradientBoostingRegressor as XGBRegressor  # type: ignore

    _HAS_XGB = False

_REPO_ROOT = Path(__file__).parent.parent.parent
# ML 학습은 깊은 히스토리(history)를 우선 사용하고, 없으면 공유 snapshot으로 폴백.
_HISTORY_CSV = _REPO_ROOT / "data" / "upbit_candles_history.csv"
_SNAPSHOT_CSV = _REPO_ROOT / "data" / "upbit_candles_snapshot.csv"
DEFAULT_CSV = _HISTORY_CSV if _HISTORY_CSV.exists() else _SNAPSHOT_CSV
DEFAULT_OUT = _REPO_ROOT / "report"
DEFAULT_MARKET = "KRW-BTC"
DEFAULT_K_VALUES = (3, 5, 7, 9, 11, 13, 15, 17, 19)
DEFAULT_N_SPLITS = 5
KNN_HORIZON = 1  # 다음 시점 FOMO 상태 예측 기준으로 k를 고른다

# XGBoost 하이퍼파라미터 격자 (시계열·표본 규모에 맞춘 보수적 범위).
XGB_PARAM_GRID = {
    "n_estimators": [200, 400],
    "max_depth": [2, 3, 4],
    "learning_rate": [0.05, 0.1],
    "subsample": [0.8, 1.0],
}

CSV_NUMERIC = ("open", "high", "low", "close", "volume")


# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------

def load_candles_from_csv(csv_path: Path, market: str = DEFAULT_MARKET) -> list[dict]:
    """data-handoff CSV에서 한 마켓 캔들을 공통 인터페이스로 로드(oldest-first)."""
    rows: list[dict] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            if raw["market"] != market:
                continue
            rows.append(
                {
                    "date_utc": raw["date_utc"],
                    **{key: float(raw[key]) for key in CSV_NUMERIC},
                }
            )
    if not rows:
        raise ValueError(f"'{market}' 행이 {csv_path}에 없습니다.")
    rows.sort(key=lambda c: c["date_utc"])
    return rows


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    """(MAE, RMSE)."""
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    return mae, rmse


def _cap_k_values(k_values: tuple[int, ...], n_samples: int, n_splits: int) -> list[int]:
    """TimeSeriesSplit 최소 train fold 크기보다 작은 k만 남긴다(이웃 부족 방지)."""
    first_train = max(1, n_samples // (n_splits + 1))
    capped = sorted({k for k in k_values if 1 <= k < first_train})
    if not capped:
        capped = [min(3, max(1, first_train - 1))]
    return capped


def _xgb_supervised(candles: list[dict], lags: int, horizon: int, days: int | None):
    """forecast_score와 동일한 피처(lag+시장)로 (X, y, feature_names) 구성."""
    days = days if days is not None else len(candles)
    fm = build_feature_matrix(candles, days=days)
    scores = [item["score"] for item in fm["series"]]
    X, y = _build_supervised(fm["matrix"], scores, lags, horizon)
    feature_names = [f"score_lag_{lags - 1 - j}" for j in range(lags)]
    feature_names += list(FEATURE_NAMES[1:])  # change_rate_1d, volume_ratio_5_20, rsi_14
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float), feature_names


# ---------------------------------------------------------------------------
# 1) KNN k 최적화
# ---------------------------------------------------------------------------

def optimize_knn_k(
    candles: list[dict],
    horizon: int = KNN_HORIZON,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    days: int | None = None,
    n_splits: int = DEFAULT_N_SPLITS,
) -> dict:
    """4피처 KNN으로 horizon 시점 FOMO Score를 예측, CV로 최적 k 선정."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")

    days = days if days is not None else len(candles)
    fm = build_feature_matrix(candles, days=days)
    scores = [item["score"] for item in fm["series"]]
    matrix = fm["matrix"]

    X = np.asarray(matrix[: len(scores) - horizon], dtype=float)
    y = np.asarray(scores[horizon:], dtype=float)
    n_samples = len(X)
    if n_samples <= n_splits + 1:
        raise ValueError("표본이 부족해 KNN 교차검증을 할 수 없습니다.")

    candidate_k = _cap_k_values(k_values, n_samples, n_splits)
    pipe = Pipeline(
        [("scaler", StandardScaler()), ("knn", KNeighborsRegressor())]
    )
    tscv = TimeSeriesSplit(n_splits=n_splits)
    grid = GridSearchCV(
        pipe,
        {"knn__n_neighbors": candidate_k},
        scoring={"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error"},
        refit="mae",
        cv=tscv,
    )
    grid.fit(X, y)

    cv = grid.cv_results_
    results = [
        {
            "k": int(k),
            "cv_mae": round(-float(mae), 4),
            "cv_rmse": round(-float(rmse), 4),
        }
        for k, mae, rmse in zip(
            cv["param_knn__n_neighbors"].data,
            cv["mean_test_mae"],
            cv["mean_test_rmse"],
        )
    ]
    results.sort(key=lambda r: r["k"])
    best_k = int(grid.best_params_["knn__n_neighbors"])

    return {
        "horizon": horizon,
        "feature_set": list(FEATURE_NAMES),
        "n_samples": n_samples,
        "n_splits": n_splits,
        "k_values": candidate_k,
        "results": results,
        "best_k": best_k,
        "best_cv_mae": round(-float(grid.best_score_), 4),
    }


# ---------------------------------------------------------------------------
# 2) XGBoost FOMO Score 학습
# ---------------------------------------------------------------------------

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
            mae, rmse = _metrics(y[test_idx], pred)
            fold_mae.append(mae)
            fold_rmse.append(rmse)

        # 전체 데이터로 최종 학습 후 피처 중요도 추출.
        final = _new_model()
        final.fit(X, y)
        importances = getattr(final, "feature_importances_", None)
        importance_map = (
            {name: round(float(val), 4) for name, val in zip(feature_names, importances)}
            if importances is not None
            else None
        )

        # 단순 baseline(직전 점수 유지) 대비 개선폭을 함께 본다.
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
    """horizon별 XGBoost 하이퍼파라미터를 TimeSeriesSplit CV로 튜닝해 최고 설정 선정.

    history 데이터(표본 ~1800)에서 '가장 좋은 성능'을 내는 설정을 찾는다. CV 점수는
    look-ahead 없이 시간 순서를 보존(TimeSeriesSplit)하며, persistence baseline과
    함께 보고한다.
    """
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

        estimator = XGBRegressor(random_state=RANDOM_STATE)
        search = GridSearchCV(
            estimator,
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
        cv = search.cv_results_
        bi = search.best_index_
        baseline_mae = float(np.mean(np.abs(y - X[:, lags - 1])))

        per_horizon[str(horizon)] = {
            "n_samples": n_samples,
            "best_params": search.best_params_,
            "cv_mae": round(-float(search.best_score_), 4),
            "cv_rmse": round(-float(cv["mean_test_rmse"][bi]), 4),
            "baseline_persist_mae": round(baseline_mae, 4),
            "skill_vs_persist": round(1.0 - (-float(search.best_score_)) / baseline_mae, 4)
            if baseline_mae > 0 else None,
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


# ---------------------------------------------------------------------------
# 통합 실행 + 리포트
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. "
    "모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
)


def run_training(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lags: int = DEFAULT_LAGS,
    n_splits: int = DEFAULT_N_SPLITS,
    tune_xgb: bool = False,
) -> dict:
    """CSV 로드 → KNN k 최적화 + XGBoost 학습을 실행하고 리포트 dict 반환.

    tune_xgb=True면 XGBoost 하이퍼파라미터 격자 탐색까지 수행해 최고 성능 설정을 찾는다.
    """
    candles = load_candles_from_csv(csv_path, market)
    fm = build_feature_matrix(candles, days=len(candles))

    report = {
        "market": market,
        "csv_path": str(csv_path),
        "n_candles": len(candles),
        "n_scored": len(fm["series"]),
        "knn_k_optimization": optimize_knn_k(
            candles, horizon=KNN_HORIZON, k_values=k_values, n_splits=n_splits
        ),
        "xgboost_fomo_forecast": train_xgb_fomo(
            candles, horizons=horizons, lags=lags, n_splits=n_splits
        ),
        "disclaimer": DISCLAIMER,
    }
    if tune_xgb:
        report["xgboost_tuned"] = tune_xgb_fomo(
            candles, horizons=horizons, lags=lags, n_splits=n_splits
        )
    return report


def format_report_md(report: dict) -> str:
    knn = report["knn_k_optimization"]
    xgb = report["xgboost_fomo_forecast"]
    lines = [
        "# KNN k 최적화 & XGBoost FOMO 학습 리포트",
        "",
        f"- market: `{report['market']}`",
        f"- candles: {report['n_candles']} (scored: {report['n_scored']})",
        f"- 입력: `{report['csv_path']}`",
        "",
        f"## 1. KNN k 최적화 (horizon={knn['horizon']}d, FOMO Score 예측)",
        f"피처: {', '.join(knn['feature_set'])} · StandardScaler · TimeSeriesSplit({knn['n_splits']})",
        f"표본: {knn['n_samples']} · **최적 k = {knn['best_k']}** (CV MAE={knn['best_cv_mae']})",
        "",
        "| k | CV MAE | CV RMSE |",
        "|---:|---:|---:|",
    ]
    for row in knn["results"]:
        mark = " (best)" if row["k"] == knn["best_k"] else ""
        lines.append(f"| {row['k']}{mark} | {row['cv_mae']} | {row['cv_rmse']} |")

    lines += [
        "",
        f"## 2. XGBoost FOMO 학습 ({xgb['model']})",
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
            f"## 3. XGBoost 하이퍼파라미터 튜닝 ({tuned['model']}, {tuned['n_candidates']} combos)",
            f"lags={tuned['lags']} · TimeSeriesSplit({tuned['n_splits']}) · grid CV로 horizon별 최고 설정",
            "",
            "| horizon | CV MAE | CV RMSE | baseline MAE | skill | best params |",
            "|---:|---:|---:|---:|---:|---|",
        ]
        for horizon, info in tuned["horizons"].items():
            if "error" in info:
                lines.append(f"| {horizon}d | - | - | - | - | (표본부족) |")
                continue
            bp = info["best_params"]
            bp_str = ", ".join(f"{k}={v}" for k, v in sorted(bp.items()))
            skill = "-" if info["skill_vs_persist"] is None else f"{info['skill_vs_persist']:+.3f}"
            lines.append(
                f"| {horizon}d | {info['cv_mae']} | {info['cv_rmse']} | "
                f"{info['baseline_persist_mae']} | {skill} | {bp_str} |"
            )

    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="KNN k 최적화 + XGBoost FOMO Score 학습 (CSV 입력, 오프라인)"
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help=f"입력 CSV (기본: {DEFAULT_CSV})")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="마켓 코드 (기본: KRW-BTC)")
    parser.add_argument("--n-splits", type=int, default=DEFAULT_N_SPLITS, help="TimeSeriesSplit fold 수")
    parser.add_argument("--no-tune", action="store_true", help="XGBoost 하이퍼파라미터 튜닝 생략")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"리포트 출력 디렉터리 (기본: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    report = run_training(
        csv_path=Path(args.csv), market=args.market, n_splits=args.n_splits,
        tune_xgb=not args.no_tune,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "knn_xgb_training_report.json"
    md_path = out_dir / "knn_xgb_training_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = format_report_md(report)
    md_path.write_text(md + "\n", encoding="utf-8")

    print(md)
    print(f"\n저장: {json_path}\n      {md_path}")


if __name__ == "__main__":
    main()
