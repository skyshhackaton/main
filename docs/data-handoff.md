# Data Handoff

## Source Branch

크롤링 기준 작업은 PR #7 기준입니다.

- Base: `feature/historical-mirror-polish`
- Head: `feature/upbit-crawler-pipeline-clean`
- 범위: Upbit 공개 일봉 캔들 수집, 검증, CSV/JSON export

기존 PR #5에는 backtest/Historical Mirror 변경이 섞여 있으므로, 크롤링 작업 기준으로는 PR #7만 봅니다.

## Local Commands

```powershell
cd backend
python -m app.upbit_client --markets KRW-BTC KRW-ETH KRW-XRP
python -m app.data_export --out ../data
```

생성 파일:

```text
data/upbit_candles_snapshot.csv
data/crawl_report.json
```

SQLite DB 파일은 충돌 우려가 있으므로 커밋하지 않습니다. 팀 공유는 DB가 아니라 CSV/JSON 파일로 합니다.

## CSV Contract

`upbit_candles_snapshot.csv`는 ML/KNN 및 통계 담당자가 바로 읽는 공유 스냅샷입니다.

필수 컬럼:

| 컬럼 | 설명 |
|---|---|
| `market` | 업비트 마켓 코드 |
| `date_utc` | UTC 기준 일봉 시각 |
| `date_kst` | KST 기준 일봉 시각 |
| `open` | 시가 |
| `high` | 고가 |
| `low` | 저가 |
| `close` | 종가 |
| `volume` | 거래량 |
| `trade_price` | Upbit 원본 종가 필드, `close`와 동일 |
| `source` | 데이터 출처 |
| `crawled_at` | export 생성 시각 |

Historical Mirror, KNN Mirror, backtest 입력으로 쓸 때는 기존 공통 캔들 인터페이스에 맞춰
`date_utc`, `open`, `high`, `low`, `close`, `volume`만 사용하면 됩니다.

## Latest Shared Snapshot

공유된 스냅샷 기준:

| market | rows | first_date_utc | last_date_utc | validation |
|---|---:|---|---|---|
| KRW-BTC | 2200 | 2020-06-20T00:00:00 | 2026-06-28T00:00:00 | OK |
| KRW-ETH | 2200 | 2020-06-20T00:00:00 | 2026-06-28T00:00:00 | OK |
| KRW-XRP | 2200 | 2020-06-20T00:00:00 | 2026-06-28T00:00:00 | OK |

QA 리포트 기준:

- `run_id`: `20260628_0434`
- `missing_dates`: 0
- `duplicate_dates`: 0
- `ohlc_errors`: 0
- `value_errors`: 0

## Consumer Notes

- 통계 담당은 KRW-BTC를 기본으로 Historical Mirror를 산출하고, 멀티마켓 확장 검토 시 KRW-ETH/KRW-XRP를 비교군으로 사용합니다.
- KNN/ML 담당은 `docs/knn-integration-contract.md`의 피처 계약을 기준으로 CSV에서 피처를 구성합니다.
- QA 담당은 `crawl_report.json`을 기준으로 데이터 결측/중복/OHLC 오류를 확인합니다.
- 발표 자료에는 DB 파일이 아니라 CSV/JSON export 흐름을 데이터 공유 방식으로 설명합니다.
