# BTC(KRW-BTC) FOMO Score 예측 그래프 — MVP 권장 안내

이 폴더에는 `viz_final`로 생성한 KRW-BTC FOMO Score 예측 그래프 7장 세트가 있다.
**검증 비율은 val 20%** (train_ratio = 0.8) 기준이다.

```
python -m app.viz_final --market KRW-BTC --train-ratio 0.8
```

> 다른 코인(ETH·XRP) 세트는 [`other_coins/`](other_coins/) 폴더 참고.

## ✅ MVP 권장: 3종만 사용

7장 중 **MVP에는 아래 3종 그래프와 그 데이터만 사용하는 것을 권장**한다.

| 그래프 | 의미 |
|---|---|
| `knn_forecast.png` | 과거 패턴 기반(KNN) 향후 시나리오 밴드 |
| `xgb_stitched_holdout.png` | XGBoost holdout(1회 학습) 예측 vs 실제 |
| `xgb_stitched_expanding.png` | XGBoost expanding(운영) 예측 vs 실제 |

**권장 이유**
- KNN·XGBoost는 경량 의존성(sklearn / xgboost)으로 동작해 **torch 없이 재현 가능**하고
  CI·발표 환경에서 안정적이다 (프로젝트 MVP 규율: 네트워크 호출 없음, 가벼운 폴백).
- 나머지 4종(`lstm_*`, `ensemble_*`)은 **torch 의존 + 학습 비용이 크고 실행 간 변동성**이
  있어 MVP 범위에서는 제외한다. 비교·후속 실험용 참고 자료로만 남긴다.

### 권장 3종 중 XGBoost skill (val 20%, horizon 14d)

skill = 1 − model_MAE / persistence_MAE (0보다 크면 "현재값 유지" 대비 우위).

| 코인 | xgb_holdout@14 | xgb_expanding@14 |
|---|---:|---:|
| **KRW-BTC** | **+0.240** | **+0.241** |
| KRW-ETH | +0.172 | +0.187 |
| KRW-XRP | +0.118 | +0.140 |

> KNN(`knn_forecast`)은 미래 시나리오 밴드 제시용이라 단일 skill 수치 대신 분포(p10~p90)로 본다.
> ETH·XRP 상세는 [`other_coins/README.md`](other_coins/README.md) 참고.

---

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다.
> 모델 성능 참고치일 뿐 **투자 추천·투자 자문·수익 보장이 아닙니다.**
