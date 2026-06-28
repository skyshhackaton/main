# KNN k 최적화 리포트

- market: `KRW-BTC`  ·  candles: 2200 (scored: 1835)
- 입력: `C:\Users\juwon\Desktop\skysh-2026-hackaton\data\upbit_candles_history.csv`

## KNN k 최적화 (horizon=1d, FOMO Score 예측)
피처: fomo_score, change_rate_1d, volume_ratio_5_20, rsi_14 · StandardScaler · TimeSeriesSplit(5)
표본: 1834 · **최적 k = 11** (CV MAE=4.424)

| k | CV MAE | CV RMSE |
|---:|---:|---:|
| 3 | 4.7037 | 5.9353 |
| 5 | 4.512 | 5.7095 |
| 7 | 4.4591 | 5.6078 |
| 9 | 4.4281 | 5.5738 |
| 11 (best) | 4.424 | 5.5751 |
| 13 | 4.4272 | 5.5788 |
| 15 | 4.4587 | 5.6036 |
| 17 | 4.4696 | 5.6157 |
| 19 | 4.5028 | 5.6529 |

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. 모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
