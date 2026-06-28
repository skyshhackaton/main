"""KNN k 최적화 (오프라인 실험).

knn-integration-contract의 4피처 [fomo_score, change_rate_1d, volume_ratio_5_20,
rsi_14]로 Pipeline(StandardScaler -> KNeighborsRegressor)을 구성하고, TimeSeriesSplit
교차검증으로 다음 시점 FOMO Score를 가장 잘 맞히는 k를 고른다. 스케일러는 fold별로
학습해 룩어헤드/누수를 피한다.

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
XGBoost는 train_xgb.py, LSTM은 train_lstm.py로 분리되어 있다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.knn_mirror import FEATURE_NAMES, build_feature_matrix
from app.train_common import (
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_N_SPLITS,
    DEFAULT_OUT,
    DISCLAIMER,
    load_candles_from_csv,
)

DEFAULT_K_VALUES = (3, 5, 7, 9, 11, 13, 15, 17, 19)
KNN_HORIZON = 1  # 다음 시점 FOMO 상태 예측 기준으로 k를 고른다


def _cap_k_values(k_values: tuple[int, ...], n_samples: int, n_splits: int) -> list[int]:
    """TimeSeriesSplit 최소 train fold 크기보다 작은 k만 남긴다(이웃 부족 방지)."""
    first_train = max(1, n_samples // (n_splits + 1))
    capped = sorted({k for k in k_values if 1 <= k < first_train})
    if not capped:
        capped = [min(3, max(1, first_train - 1))]
    return capped


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
    pipe = Pipeline([("scaler", StandardScaler()), ("knn", KNeighborsRegressor())])
    grid = GridSearchCV(
        pipe,
        {"knn__n_neighbors": candidate_k},
        scoring={"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error"},
        refit="mae",
        cv=TimeSeriesSplit(n_splits=n_splits),
    )
    grid.fit(X, y)

    cv = grid.cv_results_
    results = [
        {"k": int(k), "cv_mae": round(-float(mae), 4), "cv_rmse": round(-float(rmse), 4)}
        for k, mae, rmse in zip(
            cv["param_knn__n_neighbors"].data, cv["mean_test_mae"], cv["mean_test_rmse"]
        )
    ]
    results.sort(key=lambda r: r["k"])
    return {
        "horizon": horizon,
        "feature_set": list(FEATURE_NAMES),
        "n_samples": n_samples,
        "n_splits": n_splits,
        "k_values": candidate_k,
        "results": results,
        "best_k": int(grid.best_params_["knn__n_neighbors"]),
        "best_cv_mae": round(-float(grid.best_score_), 4),
    }


def run_knn(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    n_splits: int = DEFAULT_N_SPLITS,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    fm = build_feature_matrix(candles, days=len(candles))
    return {
        "market": market,
        "csv_path": str(csv_path),
        "n_candles": len(candles),
        "n_scored": len(fm["series"]),
        "knn_k_optimization": optimize_knn_k(
            candles, horizon=KNN_HORIZON, k_values=k_values, n_splits=n_splits
        ),
        "disclaimer": DISCLAIMER,
    }


def format_report_md(report: dict) -> str:
    knn = report["knn_k_optimization"]
    lines = [
        "# KNN k 최적화 리포트",
        "",
        f"- market: `{report['market']}`  ·  candles: {report['n_candles']} (scored: {report['n_scored']})",
        f"- 입력: `{report['csv_path']}`",
        "",
        f"## KNN k 최적화 (horizon={knn['horizon']}d, FOMO Score 예측)",
        f"피처: {', '.join(knn['feature_set'])} · StandardScaler · TimeSeriesSplit({knn['n_splits']})",
        f"표본: {knn['n_samples']} · **최적 k = {knn['best_k']}** (CV MAE={knn['best_cv_mae']})",
        "",
        "| k | CV MAE | CV RMSE |",
        "|---:|---:|---:|",
    ]
    for row in knn["results"]:
        mark = " (best)" if row["k"] == knn["best_k"] else ""
        lines.append(f"| {row['k']}{mark} | {row['cv_mae']} | {row['cv_rmse']} |")
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="KNN k 최적화 (CSV 입력, 오프라인)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help=f"입력 CSV (기본: {DEFAULT_CSV})")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="마켓 코드 (기본: KRW-BTC)")
    parser.add_argument("--n-splits", type=int, default=DEFAULT_N_SPLITS, help="TimeSeriesSplit fold 수")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"출력 디렉터리 (기본: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    report = run_knn(csv_path=Path(args.csv), market=args.market, n_splits=args.n_splits)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "knn_k_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = format_report_md(report)
    (out_dir / "knn_k_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\n저장: {out_dir / 'knn_k_report.json'}\n      {out_dir / 'knn_k_report.md'}")


if __name__ == "__main__":
    main()
