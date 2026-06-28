# KNN k 최적화 & XGBoost FOMO 학습 리포트

- market: `KRW-BTC`
- candles: 565 (scored: 200)
- 입력: `C:\Users\juwon\Desktop\skysh-2026-hackaton\data\upbit_candles_snapshot.csv`

## 1. KNN k 최적화 (horizon=1d, FOMO Score 예측)
피처: fomo_score, change_rate_1d, volume_ratio_5_20, rsi_14 · StandardScaler · TimeSeriesSplit(5)
표본: 199 · **최적 k = 19** (CV MAE=4.4147)

| k | CV MAE | CV RMSE |
|---:|---:|---:|
| 3 | 5.2186 | 6.3431 |
| 5 | 4.9122 | 6.0046 |
| 7 | 4.6281 | 5.769 |
| 9 | 4.5137 | 5.5862 |
| 11 | 4.4378 | 5.4944 |
| 13 | 4.4282 | 5.4697 |
| 15 | 4.4842 | 5.5425 |
| 17 | 4.4244 | 5.5713 |
| 19 (best) | 4.4147 | 5.6565 |

## 2. XGBoost FOMO 학습 (XGBRegressor (per-horizon direct forecast))
lags=5 · TimeSeriesSplit(5)

| horizon | samples | CV MAE | CV RMSE | baseline(유지) MAE |
|---:|---:|---:|---:|---:|
| 1d | 195 | 4.545 | 5.6886 | 3.6388 |
| 3d | 193 | 7.2114 | 8.7438 | 6.8213 |
| 7d | 189 | 9.4744 | 11.7235 | 9.0522 |

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. 모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
