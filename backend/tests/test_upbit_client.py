"""upbit_client 단위테스트.

네트워크 호출(fetch_day_candles)은 monkeypatch로 목킹하며,
실제 api.upbit.com을 호출하지 않는다. DB는 tmp_path로 격리한다.
async 함수는 asyncio.run()으로 실행해 별도 플러그인 설정 없이 통과한다.
"""

import asyncio

from app import upbit_client


# ---------------------------------------------------------------------------
# 헬퍼: 업비트 raw 응답(newest-first) 생성 + 목킹 fetch
# ---------------------------------------------------------------------------

def _make_raw(dates: list[str]) -> list[dict]:
    """dates(oldest-first 'YYYY-MM-DD') → 업비트 raw 캔들 newest-first."""
    raws = []
    for i, d in enumerate(dates):
        price = 100.0 + i
        raws.append({
            "candle_date_time_utc": f"{d}T00:00:00",
            "opening_price": price,
            "high_price": price + 2,
            "low_price": price - 2,
            "trade_price": price + 1,
            "candle_acc_trade_volume": 10.0 + i,
        })
    return list(reversed(raws))  # 업비트는 newest-first 반환


def _install_fake(monkeypatch, full_newest_first: list[dict]) -> None:
    """to= 페이지네이션을 흉내내는 가짜 fetch_day_candles 설치."""
    async def fake(market, count=200, to=None):
        if to is None:
            start = 0
        else:
            to_norm = to.replace(" ", "T")
            start = next(
                (i for i, c in enumerate(full_newest_first)
                 if c["candle_date_time_utc"] < to_norm),
                len(full_newest_first),
            )
        return full_newest_first[start:start + count]

    monkeypatch.setattr(upbit_client, "fetch_day_candles", fake)


def _dates(start_day: int, end_day: int) -> list[str]:
    return [f"2024-01-{d:02d}" for d in range(start_day, end_day + 1)]


# ---------------------------------------------------------------------------
# fetch_all_candles / 저장·로드
# ---------------------------------------------------------------------------

def test_fetch_all_candles_sorted_oldest_first(monkeypatch):
    _install_fake(monkeypatch, _make_raw(_dates(1, 5)))
    result = asyncio.run(upbit_client.fetch_all_candles("KRW-BTC"))
    dts = [c["candle_date_time_utc"] for c in result]
    assert dts == sorted(dts)  # oldest-first
    assert len(result) == 5


def test_save_and_load_roundtrip(tmp_path):
    db = tmp_path / "t.db"
    candles = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 3))]
    n = upbit_client.save_candles(candles, "KRW-BTC", db)
    assert n == 3
    loaded = upbit_client.load_candles("KRW-BTC", db)
    # load는 oldest-first 보장
    assert [c["date_utc"] for c in loaded] == sorted(c["date_utc"] for c in candles)


def test_load_empty_db_returns_empty(tmp_path):
    assert upbit_client.load_candles("KRW-BTC", tmp_path / "nope.db") == []


# ---------------------------------------------------------------------------
# update_candles (증분 갱신)
# ---------------------------------------------------------------------------

def test_update_candles_incremental(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    # 기존 DB: day1~day5
    seed = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 5))]
    upbit_client.save_candles(seed, "KRW-BTC", db)
    # API에는 day1~day8 존재 → day6,7,8 만 새로 받아야 함
    _install_fake(monkeypatch, _make_raw(_dates(1, 8)))

    added = asyncio.run(upbit_client.update_candles("KRW-BTC", db))
    assert added == 3
    loaded = upbit_client.load_candles("KRW-BTC", db)
    assert len(loaded) == 8
    assert loaded[-1]["date_utc"] == "2024-01-08T00:00:00"


def test_update_candles_no_new_data(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    seed = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 5))]
    upbit_client.save_candles(seed, "KRW-BTC", db)
    _install_fake(monkeypatch, _make_raw(_dates(1, 5)))  # 동일 → 새 데이터 없음

    added = asyncio.run(upbit_client.update_candles("KRW-BTC", db))
    assert added == 0
    assert len(upbit_client.load_candles("KRW-BTC", db)) == 5


def test_update_candles_empty_db_falls_back_to_full(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    _install_fake(monkeypatch, _make_raw(_dates(1, 6)))
    added = asyncio.run(upbit_client.update_candles("KRW-BTC", db))
    assert added == 6
    assert len(upbit_client.load_candles("KRW-BTC", db)) == 6


# ---------------------------------------------------------------------------
# refresh_markets (멀티 마켓)
# ---------------------------------------------------------------------------

def test_refresh_markets_mixed_states(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    # BTC는 기존 day1~5 있음(→3 추가 예정), ETH는 비어있음(→full 6)
    seed = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 5))]
    upbit_client.save_candles(seed, "KRW-BTC", db)

    # 두 마켓 모두 동일한 가짜 데이터셋(day1~8 for BTC, day1~6 for ETH는 구분 불가하므로
    # 마켓 무관 동일 셋 사용: day1~8). ETH는 비어있어 full로 8개 들어감.
    _install_fake(monkeypatch, _make_raw(_dates(1, 8)))

    result = asyncio.run(upbit_client.refresh_markets(["KRW-BTC", "KRW-ETH"], db))
    assert result["KRW-BTC"] == 3   # 증분
    assert result["KRW-ETH"] == 8   # 전체
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# validate_candles (데이터 검증)
# ---------------------------------------------------------------------------

def _good_candle(date, o=100, h=102, l=98, c=101, v=10):
    return {"date_utc": f"{date}T00:00:00", "open": o, "high": h,
            "low": l, "close": c, "volume": v}


def test_validate_clean_data_ok():
    candles = [_good_candle(f"2024-01-{d:02d}") for d in range(1, 6)]
    report = upbit_client.validate_candles(candles)
    assert report["ok"] is True
    assert report["count"] == 5
    assert report["missing_dates"] == []
    assert report["duplicate_dates"] == []
    assert report["ohlc_errors"] == []
    assert report["value_errors"] == []


def test_validate_detects_missing_date():
    # 01-03 누락
    candles = [_good_candle("2024-01-01"), _good_candle("2024-01-02"),
               _good_candle("2024-01-04")]
    report = upbit_client.validate_candles(candles)
    assert report["ok"] is False
    assert "2024-01-03" in report["missing_dates"]


def test_validate_detects_duplicate():
    candles = [_good_candle("2024-01-01"), _good_candle("2024-01-01")]
    report = upbit_client.validate_candles(candles)
    assert "2024-01-01T00:00:00" in report["duplicate_dates"]
    assert report["ok"] is False


def test_validate_detects_ohlc_violation():
    candles = [_good_candle("2024-01-01", h=90, l=100)]  # high < low
    report = upbit_client.validate_candles(candles)
    assert report["ohlc_errors"]
    assert report["ohlc_errors"][0]["reason"] == "high < low"


def test_validate_detects_close_out_of_range():
    candles = [_good_candle("2024-01-01", h=102, l=98, c=200)]  # close > high
    report = upbit_client.validate_candles(candles)
    assert any(e["reason"] == "close out of [low, high]" for e in report["ohlc_errors"])


def test_validate_detects_value_errors():
    candles = [_good_candle("2024-01-01", v=-5),
               _good_candle("2024-01-02", o=-1, h=102, l=-5, c=1)]
    report = upbit_client.validate_candles(candles)
    reasons = {e["reason"] for e in report["value_errors"]}
    assert "negative volume" in reasons
    assert "non-positive price" in reasons


# ---------------------------------------------------------------------------
# 엣지케이스: 오늘 partial candle 갱신 / off-by-one / 마켓 격리 / 실패 격리
# ---------------------------------------------------------------------------

def test_update_refreshes_last_day_partial_candle(monkeypatch, tmp_path):
    """DB의 마지막 날(=오늘) 캔들이 API에서 바뀌면 덮어써야 함(stale 방지)."""
    db = tmp_path / "t.db"
    # 기존 DB: day1~day5, day5는 오전 partial candle(종가 999)
    seed = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 5))]
    seed[-1]["close"] = 999.0  # 미완성 값
    upbit_client.save_candles(seed, "KRW-BTC", db)

    # API: day1~day5, day5 종가가 확정값으로 바뀜
    api = _make_raw(_dates(1, 5))
    for raw in api:
        if raw["candle_date_time_utc"] == "2024-01-05T00:00:00":
            raw["trade_price"] = 555.0  # 확정 종가
    _install_fake(monkeypatch, api)

    added = asyncio.run(upbit_client.update_candles("KRW-BTC", db))
    assert added == 0  # 신규 날짜는 없음
    loaded = upbit_client.load_candles("KRW-BTC", db)
    assert len(loaded) == 5  # 중복 없음
    # 오늘(day5) 캔들이 확정 종가로 갱신됨
    assert loaded[-1]["close"] == 555.0


def test_update_no_off_by_one_duplicate(monkeypatch, tmp_path):
    """증분 갱신 후 같은 날짜가 중복 저장되지 않아야 함."""
    db = tmp_path / "t.db"
    seed = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 5))]
    upbit_client.save_candles(seed, "KRW-BTC", db)
    _install_fake(monkeypatch, _make_raw(_dates(1, 8)))

    asyncio.run(upbit_client.update_candles("KRW-BTC", db))
    loaded = upbit_client.load_candles("KRW-BTC", db)
    dates = [c["date_utc"] for c in loaded]
    assert len(dates) == len(set(dates))  # 중복 없음
    assert dates == sorted(dates)          # oldest-first 유지


def test_markets_do_not_collide_on_same_date(tmp_path):
    """KRW-BTC와 KRW-ETH가 같은 날짜를 가져도 서로 덮어쓰지 않음."""
    db = tmp_path / "t.db"
    btc = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 3))]
    eth = [upbit_client._normalize(c) for c in _make_raw(_dates(1, 3))]
    for c in eth:
        c["close"] = c["close"] + 10000  # 구분되는 값
    upbit_client.save_candles(btc, "KRW-BTC", db)
    upbit_client.save_candles(eth, "KRW-ETH", db)

    btc_loaded = upbit_client.load_candles("KRW-BTC", db)
    eth_loaded = upbit_client.load_candles("KRW-ETH", db)
    assert len(btc_loaded) == 3 and len(eth_loaded) == 3
    assert btc_loaded[0]["close"] != eth_loaded[0]["close"]


def test_refresh_markets_isolates_failure(monkeypatch, tmp_path):
    """한 마켓이 실패해도 나머지 마켓은 정상 처리되어야 함."""
    db = tmp_path / "t.db"
    full = _make_raw(_dates(1, 5))

    async def flaky(market, count=200, to=None):
        if market == "KRW-ETH":
            raise RuntimeError("simulated network error")
        if to is None:
            start = 0
        else:
            to_norm = to.replace(" ", "T")
            start = next((i for i, c in enumerate(full)
                          if c["candle_date_time_utc"] < to_norm), len(full))
        return full[start:start + count]

    monkeypatch.setattr(upbit_client, "fetch_day_candles", flaky)

    result = asyncio.run(
        upbit_client.refresh_markets(["KRW-BTC", "KRW-ETH", "KRW-XRP"], db)
    )
    assert result["KRW-BTC"] == 5            # 성공 (full)
    assert result["KRW-XRP"] == 5            # 실패 마켓 뒤에도 정상 실행
    assert isinstance(result["KRW-ETH"], dict)
    assert result["KRW-ETH"]["error"] == "RuntimeError"
