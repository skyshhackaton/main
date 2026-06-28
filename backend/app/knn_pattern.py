"""KNN FOMO 패턴 매칭 (analog forecasting).

KNN Mirror가 '한 시점의 4피처'로 유사 과거를 찾는다면, 이 모듈은 '최근 W일 FOMO
*궤적(패턴)*'으로 가장 닮은 과거 구간 k개를 찾고, 그 패턴 *이후* 실제 흐름을 현재
점수에 레벨 정렬해 **앞으로 가능한 FOMO 후보 시나리오 k개**로 제시한다.

성격(중요, compliance):
- 단일 값을 단정 예측하는 것이 아니라, "과거 비슷한 패턴 이후엔 이렇게 흘러갔다"는
  **사례(analog) 분포**를 보여주는 보조 렌즈다.
- 대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이며 투자 추천/수익 예측이 아니다.

Look-ahead 규율:
- 시점 t의 쿼리 윈도우는 scores[t-W+1 : t+1]만 사용한다.
- 후보 과거 패턴은 미래(t+H)까지 실현된 것만 쓴다(`e + H <= t`). 따라서 백테스트에서도
  각 원점은 자기 과거만 참조한다.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from app.fomo_score import classify_grade, clamp
from app.fomo_score import score_series

DEFAULT_WINDOW = 20
DEFAULT_HORIZON = 7
DEFAULT_K = 5
DEFAULT_METRIC = "znorm"
METRICS = ("raw", "znorm")

# 비교 스윕 기본 격자
SWEEP_WINDOWS = (10, 20, 30)
SWEEP_HORIZONS = (7, 14, 30)
SWEEP_K = (5, 10)
DEFAULT_TEST_SIZE = 300

_REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_CSV = _REPO_ROOT / "data" / "upbit_candles_history.csv"
DEFAULT_OUT = _REPO_ROOT / "report"
DEFAULT_MARKET = "KRW-BTC"
CSV_NUMERIC = ("open", "high", "low", "close", "volume")


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------

def load_candles_from_csv(csv_path: Path, market: str = DEFAULT_MARKET) -> list[dict]:
    rows: list[dict] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            if raw["market"] != market:
                continue
            rows.append({"date_utc": raw["date_utc"], **{k: float(raw[k]) for k in CSV_NUMERIC}})
    if not rows:
        raise ValueError(f"'{market}' 행이 {csv_path}에 없습니다.")
    rows.sort(key=lambda c: c["date_utc"])
    return rows


def fomo_score_series(candles: list[dict], days: int | None = None) -> tuple[np.ndarray, list[str]]:
    """전체 구간 FOMO Score 시계열과 날짜 반환 (oldest-first)."""
    days = days if days is not None else len(candles)
    series = score_series(candles, days=days)
    if not series:
        raise ValueError("not enough candles to build score series")
    scores = np.asarray([s["score"] for s in series], dtype=float)
    dates = [s["date"] for s in series]
    return scores, dates


# ---------------------------------------------------------------------------
# 윈도우 / 거리
# ---------------------------------------------------------------------------

def _window_matrix(scores: np.ndarray, window: int) -> np.ndarray:
    """행 r = 끝점 e=(r+window-1)인 길이 window 윈도우. shape (N-window+1, window)."""
    n = len(scores)
    if window < 2 or window > n:
        raise ValueError("window out of range")
    idx = np.arange(window)[None, :] + np.arange(0, n - window + 1)[:, None]
    return scores[idx]


def _znorm_rows(mat: np.ndarray) -> np.ndarray:
    mu = mat.mean(axis=1, keepdims=True)
    sd = mat.std(axis=1, keepdims=True)
    sd = np.where(sd > 0, sd, 1.0)
    return (mat - mu) / sd


def _prep_matrix(scores: np.ndarray, window: int, metric: str) -> np.ndarray:
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    mat = _window_matrix(scores, window)
    return _znorm_rows(mat) if metric == "znorm" else mat


# ---------------------------------------------------------------------------
# 현재 시점 후보 시나리오
# ---------------------------------------------------------------------------

def build_fomo_pattern_forecast(
    candles: list[dict],
    window: int = DEFAULT_WINDOW,
    horizon: int = DEFAULT_HORIZON,
    k: int = DEFAULT_K,
    metric: str = DEFAULT_METRIC,
    days: int | None = None,
) -> dict:
    """현재 W일 패턴과 가장 닮은 과거 k개를 찾아 앞으로의 FOMO 후보 시나리오 생성."""
    if window < 2:
        raise ValueError("window must be >= 2")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if k < 1:
        raise ValueError("k must be >= 1")

    scores, dates = fomo_score_series(candles, days=days)
    n = len(scores)
    mat = _prep_matrix(scores, window, metric)

    query_end = n - 1
    max_e = query_end - horizon  # 미래가 실현된 후보만
    max_r = max_e - (window - 1)
    if max_r < 0:
        raise ValueError("표본이 부족해 패턴 매칭을 할 수 없습니다.")

    q = mat[query_end - (window - 1)]
    cand = mat[: max_r + 1]
    dists = np.sqrt(((cand - q) ** 2).sum(axis=1))
    k_eff = min(k, len(cand))
    order = np.argsort(dists)[:k_eff]

    current = float(scores[query_end])
    candidates = []
    anchored_paths = []
    for r in order:
        e = int(r) + (window - 1)
        future = scores[e + 1 : e + 1 + horizon]
        anchor = float(scores[e])
        anchored = [clamp(current + (float(f) - anchor)) for f in future]
        anchored_paths.append(anchored)
        candidates.append(
            {
                "match_end_date": dates[e],
                "distance": round(float(dists[r]), 4),
                "match_end_score": round(anchor, 2),
                "future_scores": [round(float(f), 2) for f in future],
                "anchored_future": [round(v, 2) for v in anchored],
                "anchored_end_grade": classify_grade(anchored[-1])[0],
            }
        )

    band = _band(np.asarray(anchored_paths), horizon)
    grade_now = classify_grade(current)[0]
    return {
        "current_date": dates[-1],
        "current_score": round(current, 2),
        "current_grade": grade_now,
        "window": window,
        "horizon": horizon,
        "k": k_eff,
        "metric": metric,
        "candidates": candidates,
        "band": band,
        "summary": _forecast_summary(current, band, k_eff, window, horizon),
    }


def _band(paths: np.ndarray, horizon: int) -> dict:
    """후보 경로들의 step별 평균/분위수 밴드."""
    steps = list(range(1, horizon + 1))
    if paths.size == 0:
        empty = [None] * horizon
        return {"steps": steps, "mean": empty, "p10": empty, "p50": empty, "p90": empty}
    return {
        "steps": steps,
        "mean": [round(float(v), 2) for v in paths.mean(axis=0)],
        "p10": [round(float(v), 2) for v in np.percentile(paths, 10, axis=0)],
        "p50": [round(float(v), 2) for v in np.percentile(paths, 50, axis=0)],
        "p90": [round(float(v), 2) for v in np.percentile(paths, 90, axis=0)],
    }


def _forecast_summary(current: float, band: dict, k: int, window: int, horizon: int) -> str:
    end_mean = band["mean"][-1]
    if end_mean is None:
        return "유사 패턴을 찾지 못했습니다."
    diff = end_mean - current
    direction = "상승" if diff > 1 else "하락" if diff < -1 else "횡보"
    return (
        f"최근 {window}일 FOMO 패턴과 가장 닮은 과거 {k}개 사례 기준, {horizon}일 후 심리는 "
        f"평균적으로 '{direction}' 경향(현재 {round(current, 2)} → 평균 {end_mean}, "
        f"범위 {band['p10'][-1]}~{band['p90'][-1]})이었습니다. 과거 사례 분포이며 미래를 보장하지 않습니다."
    )


# ---------------------------------------------------------------------------
# 백테스트 / 파라미터 비교
# ---------------------------------------------------------------------------

def backtest_config(
    scores: np.ndarray,
    window: int,
    horizon: int,
    k: int,
    metric: str,
    test_size: int = DEFAULT_TEST_SIZE,
) -> dict:
    """analog 평균경로 vs persistence(현재값 유지) baseline의 H-step MAE 비교.

    각 원점 t는 e+H<=t 인 과거 패턴만 참조 → look-ahead 없음.
    """
    n = len(scores)
    mat = _prep_matrix(scores, window, metric)

    # 유효 원점: 후보가 k개 이상이고 t+H<=n-1
    first_t = (window - 1) + horizon + (k - 1)
    last_t = n - 1 - horizon
    if last_t < first_t:
        return {"window": window, "horizon": horizon, "k": k, "metric": metric,
                "origins": 0, "analog_mae": None, "persist_mae": None, "skill": None}

    origins = list(range(first_t, last_t + 1))
    if len(origins) > test_size:
        origins = origins[-test_size:]

    analog_abs, persist_abs = [], []
    for t in origins:
        q = mat[t - (window - 1)]
        max_r = (t - horizon) - (window - 1)
        cand = mat[: max_r + 1]
        dists = np.sqrt(((cand - q) ** 2).sum(axis=1))
        order = np.argsort(dists)[:k]
        current = float(scores[t])

        paths = []
        for r in order:
            e = int(r) + (window - 1)
            future = scores[e + 1 : e + 1 + horizon]
            anchor = float(scores[e])
            paths.append([clamp(current + (float(f) - anchor)) for f in future])
        pred = np.asarray(paths).mean(axis=0)
        actual = scores[t + 1 : t + 1 + horizon]
        analog_abs.append(np.abs(pred - actual))
        persist_abs.append(np.abs(current - actual))  # flat baseline

    analog_mae = float(np.mean(np.concatenate(analog_abs)))
    persist_mae = float(np.mean(np.concatenate(persist_abs)))
    skill = 1.0 - analog_mae / persist_mae if persist_mae > 0 else None
    return {
        "window": window,
        "horizon": horizon,
        "k": k,
        "metric": metric,
        "origins": len(origins),
        "analog_mae": round(analog_mae, 4),
        "persist_mae": round(persist_mae, 4),
        "skill": round(skill, 4) if skill is not None else None,
    }


def compare_configs(
    candles: list[dict],
    windows: tuple[int, ...] = SWEEP_WINDOWS,
    horizons: tuple[int, ...] = SWEEP_HORIZONS,
    ks: tuple[int, ...] = SWEEP_K,
    metrics: tuple[str, ...] = METRICS,
    test_size: int = DEFAULT_TEST_SIZE,
    days: int | None = None,
) -> list[dict]:
    """파라미터 격자 백테스트. skill 내림차순 정렬해 반환."""
    scores, _ = fomo_score_series(candles, days=days)
    results = []
    for w in windows:
        for h in horizons:
            for k in ks:
                for m in metrics:
                    results.append(backtest_config(scores, w, h, k, m, test_size))
    results.sort(key=lambda r: (r["skill"] is not None, r["skill"] or -1), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Holdout 검증 (train / validation 완전 분리)
# ---------------------------------------------------------------------------

DEFAULT_TRAIN_RATIO = 0.7


def validate_holdout(
    scores: np.ndarray,
    window: int,
    horizon: int,
    k: int,
    metric: str,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    collect: bool = False,
) -> dict:
    """train/validation 분리 검증.

    analog 후보 풀은 train 구간에서만 구성한다(`e + horizon <= cutoff-1`).
    따라서 검증 구간 데이터는 후보 매칭에 절대 쓰이지 않는다(누수/과적합 차단).
    검증 구간의 각 시점 t는 train 패턴만으로 예측하고 실제 미래와 비교한다.
    """
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be in (0, 1)")

    n = len(scores)
    cutoff = int(n * train_ratio)
    mat = _prep_matrix(scores, window, metric)

    # train 풀: 윈도우와 미래가 모두 train 구간(<= cutoff-1) 안에 있는 패턴.
    pool_max_e = (cutoff - 1) - horizon
    pool_max_r = pool_max_e - (window - 1)
    # 검증 원점: cutoff 이후, 미래가 실현되는 t.
    first_t = max(cutoff, window - 1)
    last_t = n - 1 - horizon
    if pool_max_r < k - 1 or last_t < first_t:
        result = {
            "window": window, "horizon": horizon, "k": k, "metric": metric,
            "train_ratio": train_ratio, "cutoff_index": cutoff,
            "train_pool": max(0, pool_max_r + 1), "val_origins": 0,
            "analog_mae": None, "persist_mae": None, "skill": None,
        }
        if collect:
            result.update({"per_step": None, "samples": [], "scatter": None})
        return result

    pool = mat[: pool_max_r + 1]  # train-only 후보 (고정)
    analog_abs, persist_abs = [], []
    pred_h, actual_h, target_index, samples = [], [], [], []

    origins = list(range(first_t, last_t + 1))
    sample_at = set(np.linspace(0, len(origins) - 1, min(8, len(origins))).astype(int).tolist())

    for oi, t in enumerate(origins):
        q = mat[t - (window - 1)]
        dists = np.sqrt(((pool - q) ** 2).sum(axis=1))
        order = np.argsort(dists)[:k]
        current = float(scores[t])

        paths = []
        for r in order:
            e = int(r) + (window - 1)
            future = scores[e + 1 : e + 1 + horizon]
            anchor = float(scores[e])
            paths.append([clamp(current + (float(f) - anchor)) for f in future])
        pred = np.asarray(paths).mean(axis=0)
        actual = scores[t + 1 : t + 1 + horizon]
        analog_abs.append(np.abs(pred - actual))
        persist_abs.append(np.abs(current - actual))
        pred_h.append(float(pred[-1]))
        actual_h.append(float(actual[-1]))
        target_index.append(t + horizon)
        if collect and oi in sample_at:
            samples.append({"origin_index": t, "pred": [float(v) for v in pred],
                            "actual": [float(v) for v in actual]})

    analog_stack = np.vstack(analog_abs)
    persist_stack = np.vstack(persist_abs)
    analog_mae = float(analog_stack.mean())
    persist_mae = float(persist_stack.mean())
    skill = 1.0 - analog_mae / persist_mae if persist_mae > 0 else None

    result = {
        "window": window, "horizon": horizon, "k": k, "metric": metric,
        "train_ratio": train_ratio, "cutoff_index": cutoff,
        "train_pool": int(pool_max_r + 1), "val_origins": len(origins),
        "analog_mae": round(analog_mae, 4), "persist_mae": round(persist_mae, 4),
        "skill": round(skill, 4) if skill is not None else None,
    }
    if collect:
        result["per_step"] = {
            "steps": list(range(1, horizon + 1)),
            "analog_mae": [round(float(v), 4) for v in analog_stack.mean(axis=0)],
            "persist_mae": [round(float(v), 4) for v in persist_stack.mean(axis=0)],
        }
        result["samples"] = samples
        result["scatter"] = {"pred_h": pred_h, "actual_h": actual_h}
        result["stitched"] = {"target_index": target_index, "pred": pred_h, "actual": actual_h}
    return result


def compare_holdout(
    candles: list[dict],
    windows: tuple[int, ...] = SWEEP_WINDOWS,
    horizons: tuple[int, ...] = SWEEP_HORIZONS,
    ks: tuple[int, ...] = SWEEP_K,
    metrics: tuple[str, ...] = METRICS,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    days: int | None = None,
) -> list[dict]:
    """holdout 검증 격자. validation skill 내림차순 정렬."""
    scores, _ = fomo_score_series(candles, days=days)
    results = []
    for w in windows:
        for h in horizons:
            for k in ks:
                for m in metrics:
                    results.append(validate_holdout(scores, w, h, k, m, train_ratio))
    results.sort(key=lambda r: (r["skill"] is not None, r["skill"] or -1), reverse=True)
    return results


# ---------------------------------------------------------------------------
# 통합 실행 + 리포트
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "패턴 매칭 결과는 과거 유사 사례의 분포이며 가격·수익률 예측이 아닙니다. "
    "시장 심리 상태(FOMO Score) 관찰용 보조 참고일 뿐 투자 추천을 제공하지 않습니다."
)


def run_pattern_analysis(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    test_size: int = DEFAULT_TEST_SIZE,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores, _ = fomo_score_series(candles)
    comparison = compare_configs(candles, test_size=test_size)
    holdout = compare_holdout(candles, train_ratio=train_ratio)

    # 추천 설정: walk-forward 전체에서 baseline 대비 skill이 가장 높은 조합.
    # (단기 H=7은 거의 랜덤워크라 skill이 낮고, 중기 H=14/30에서 패턴 매칭의 가치가 큼)
    scored = [c for c in comparison if c["skill"] is not None]
    best = (scored or [None])[0]  # comparison은 이미 skill 내림차순 정렬됨
    holdout_best = next((c for c in holdout if c["skill"] is not None), None)
    forecast = None
    if best:
        forecast = build_fomo_pattern_forecast(
            candles, window=best["window"], horizon=best["horizon"],
            k=best["k"], metric=best["metric"],
        )

    return {
        "market": market,
        "csv_path": str(csv_path),
        "n_candles": len(candles),
        "n_scored": len(scores),
        "test_size": test_size,
        "train_ratio": train_ratio,
        "recommended_config": best,
        "holdout_best": holdout_best,
        "comparison": comparison,
        "holdout_comparison": holdout,
        "current_forecast": forecast,
        "disclaimer": DISCLAIMER,
    }


def format_report_md(report: dict) -> str:
    lines = [
        "# KNN FOMO 패턴 매칭 리포트",
        "",
        f"- market: `{report['market']}`  ·  candles: {report['n_candles']} (scored: {report['n_scored']})",
        f"- 입력: `{report['csv_path']}`  ·  backtest 원점: 최근 {report['test_size']}개",
        "",
        "## 1. 파라미터 비교 (analog 평균경로 vs persistence baseline)",
        "skill = 1 − analog_MAE / persist_MAE  (>0 이면 baseline보다 나음)",
        "",
        "| window | horizon | k | metric | origins | analog MAE | persist MAE | skill |",
        "|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for c in report["comparison"]:
        skill = "-" if c["skill"] is None else f"{c['skill']:+.3f}"
        a = "-" if c["analog_mae"] is None else c["analog_mae"]
        p = "-" if c["persist_mae"] is None else c["persist_mae"]
        lines.append(
            f"| {c['window']} | {c['horizon']} | {c['k']} | {c['metric']} | "
            f"{c['origins']} | {a} | {p} | {skill} |"
        )

    # Holdout 검증 (train/validation 완전 분리)
    holdout = report.get("holdout_comparison")
    if holdout:
        tr = int(report.get("train_ratio", DEFAULT_TRAIN_RATIO) * 100)
        lines += [
            "",
            f"## 2. Holdout 검증 (train {tr}% / validation {100 - tr}%, analog 풀=train 전용)",
            "walk-forward와 달리 검증 구간은 후보 매칭에 전혀 쓰이지 않음 → 일반화 성능.",
            "",
            "| window | horizon | k | metric | val_origins | analog MAE | persist MAE | skill |",
            "|---:|---:|---:|---|---:|---:|---:|---:|",
        ]
        for c in holdout:
            skill = "-" if c["skill"] is None else f"{c['skill']:+.3f}"
            a = "-" if c["analog_mae"] is None else c["analog_mae"]
            p = "-" if c["persist_mae"] is None else c["persist_mae"]
            lines.append(
                f"| {c['window']} | {c['horizon']} | {c['k']} | {c['metric']} | "
                f"{c['val_origins']} | {a} | {p} | {skill} |"
            )

    rec = report["recommended_config"]
    fc = report["current_forecast"]
    lines += ["", "## 3. 추천 설정 & 현재 후보 시나리오"]
    if rec and fc:
        lines += [
            f"추천: window={rec['window']}, horizon={rec['horizon']}, k={rec['k']}, "
            f"metric={rec['metric']} (skill={rec['skill']:+.3f})",
            "",
            f"현재 {fc['current_date']} FOMO={fc['current_score']} ({fc['current_grade']})",
            f"→ {fc['horizon']}일 후 밴드: 평균 {fc['band']['mean'][-1]} "
            f"(p10 {fc['band']['p10'][-1]} ~ p90 {fc['band']['p90'][-1]})",
            "",
            "닮은 과거 패턴:",
            "",
            "| match_end_date | distance | 패턴끝 점수 | H일후 평균(anchored) |",
            "|---|---:|---:|---:|",
        ]
        for cand in fc["candidates"]:
            lines.append(
                f"| {cand['match_end_date'][:10]} | {cand['distance']} | "
                f"{cand['match_end_score']} | {cand['anchored_future'][-1]} |"
            )
        lines += ["", f"> {fc['summary']}"]
    else:
        lines.append("표본 부족으로 추천 설정을 산출하지 못했습니다.")

    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="KNN FOMO 패턴 매칭 분석 (CSV, 오프라인)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help=f"입력 CSV (기본: {DEFAULT_CSV})")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="마켓 코드 (기본: KRW-BTC)")
    parser.add_argument("--test-size", type=int, default=DEFAULT_TEST_SIZE, help="backtest 원점 수")
    parser.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO, help="holdout train 비율")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"출력 디렉터리 (기본: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    report = run_pattern_analysis(Path(args.csv), args.market, args.test_size, args.train_ratio)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "knn_pattern_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = format_report_md(report)
    (out_dir / "knn_pattern_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\n저장: {out_dir / 'knn_pattern_report.json'}\n      {out_dir / 'knn_pattern_report.md'}")


if __name__ == "__main__":
    main()
