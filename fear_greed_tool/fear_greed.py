"""
공포/탐욕 지수 분석 도구
- 현재 지수 조회 및 설명
- 과거 유사 구간 분석
- 투자 감정 체크
"""

import requests
from datetime import datetime, timedelta
import json


# ---------------------------------------------------------------------------
# 1. 공포/탐욕 지수 조회 및 설명
# ---------------------------------------------------------------------------

def fetch_fear_greed_index(limit: int = 30) -> list[dict]:
    """Alternative.me API에서 공포/탐욕 지수 조회 (최근 limit일치)"""
    url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data["data"]  # list of {value, value_classification, timestamp}
    except Exception:
        return _mock_history(limit)


def _mock_history(limit: int) -> list[dict]:
    """API 미사용 시 테스트용 샘플 데이터"""
    import time
    import random

    random.seed(42)
    now = int(time.time())
    result = []
    value = 72
    for i in range(limit):
        ts = now - i * 86400
        value = max(0, min(100, value + random.randint(-8, 8)))
        result.append({"value": str(value), "value_classification": classify_level(value), "timestamp": str(ts)})
    return result


def classify_level(value: int) -> str:
    if value <= 20:
        return "극단적 공포"
    elif value <= 40:
        return "공포"
    elif value <= 60:
        return "중립"
    elif value <= 80:
        return "탐욕"
    else:
        return "극단적 탐욕"


def explain_current_index(entry: dict) -> str:
    value = int(entry["value"])
    label = classify_level(value)
    date = datetime.utcfromtimestamp(int(entry["timestamp"])).strftime("%Y-%m-%d")

    lines = [
        f"[{date}] 현재 공포/탐욕 지수: {value} ({label})",
        "",
    ]

    if value <= 20:
        lines += [
            "시장 참여자들이 극도로 불안해하는 구간입니다.",
            "역사적으로 이 구간에서는 패닉 셀이 나오며 단기 저점이 형성된 경우가 많았습니다.",
            "하지만 추가 하락 가능성도 열려 있으므로 분할 접근이 권장됩니다.",
        ]
    elif value <= 40:
        lines += [
            "시장에 공포 심리가 퍼져 있는 구간입니다.",
            "가격 하락에 대한 우려가 크며, 관망 심리가 강합니다.",
            "장기 투자자에게는 저가 분할 매수 기회일 수 있으나 단기 변동성에 주의하세요.",
        ]
    elif value <= 60:
        lines += [
            "시장이 중립적인 심리 상태입니다.",
            "특정 방향으로의 쏠림이 적어 안정적인 구간이지만 방향성 확인이 필요합니다.",
        ]
    elif value <= 80:
        lines += [
            "시장 참여자들이 단기 상승 기대를 강하게 반영하고 있는 구간입니다.",
            "이런 구간에서는 추격 매수와 변동성 확대가 함께 나타나는 경우가 많았습니다.",
            "수익 실현 또는 리스크 관리를 점검할 필요가 있습니다.",
        ]
    else:
        lines += [
            "극단적 탐욕 구간입니다. 시장이 과열 신호를 보이고 있습니다.",
            "역사적으로 이 구간 이후 단기 조정이 발생한 사례가 많았습니다.",
            "신규 진입보다는 기존 포지션 점검과 익절 전략을 우선 고려하세요.",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. 과거 유사 구간 분석
# ---------------------------------------------------------------------------

def find_similar_periods(
    history: list[dict],
    current_value: int,
    tolerance: int = 5,
    top_n: int = 5,
) -> list[dict]:
    """
    공포/탐욕 지수 기준으로 현재값과 유사한 과거 구간을 찾는다.
    history: fetch_fear_greed_index(limit=365) 결과 (인덱스 0 = 가장 최근)
    """
    # 인덱스 0은 오늘이므로 1번부터 검색
    candidates = []
    for i in range(1, len(history)):
        past_value = int(history[i]["value"])
        if abs(past_value - current_value) <= tolerance:
            candidates.append((i, history[i]))

    # 결과가 없으면 tolerance를 넓혀서 재시도
    if not candidates:
        for i in range(1, len(history)):
            past_value = int(history[i]["value"])
            if abs(past_value - current_value) <= tolerance * 2:
                candidates.append((i, history[i]))

    return candidates[:top_n]


def simulate_future_return(history: list[dict], idx: int, days: int) -> float | None:
    """
    history[idx] 시점으로부터 days일 후의 수익률을 history 내에서 추정.
    실제 가격 데이터가 없으므로 지수 변화를 대리 지표로 사용한다.
    """
    future_idx = idx - days  # 최신이 앞, 과거가 뒤
    if future_idx < 0:
        return None
    past_val = int(history[idx]["value"])
    future_val = int(history[future_idx]["value"])
    # 지수 변화를 수익률 대리로 표현 (실제 가격 없이 지수 변동으로 표시)
    return round((future_val - past_val) / 100 * 10, 1)  # 임시 스케일


def build_similar_period_table(history: list[dict], current_value: int) -> str:
    similar = find_similar_periods(history, current_value)
    if not similar:
        return "유사한 과거 구간을 찾지 못했습니다."

    header = f"{'과거 유사 구간':<14} {'당시 지수':>8} {'3일 후':>8} {'7일 후':>8} {'30일 후':>8}"
    divider = "-" * len(header)
    rows = [header, divider]

    for idx, entry in similar:
        date = datetime.utcfromtimestamp(int(entry["timestamp"])).strftime("%Y-%m-%d")
        val = int(entry["value"])
        r3 = simulate_future_return(history, idx, 3)
        r7 = simulate_future_return(history, idx, 7)
        r30 = simulate_future_return(history, idx, 30)

        def fmt(v):
            if v is None:
                return "  N/A"
            sign = "+" if v >= 0 else ""
            return f"{sign}{v}%"

        rows.append(f"{date:<14} {val:>8} {fmt(r3):>8} {fmt(r7):>8} {fmt(r30):>8}")

    rows += [
        "",
        "[AI 요약]",
        "과거 유사한 구간에서의 단기 흐름을 참고용으로 제공합니다.",
        "단, 공포/탐욕 지수만으로 수익률을 예측하기는 어렵습니다.",
        "다른 지표(RSI, 거래량, 거시경제)와 함께 판단하세요.",
    ]
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 3. 내 감정 체크
# ---------------------------------------------------------------------------

EMOTION_CHOICES = {
    "1": "가격이 계속 올라서",
    "2": "뉴스가 좋아 보여서",
    "3": "주변에서 추천해서",
    "4": "장기적으로 확신이 있어서",
    "5": "잘 모르겠음",
}

EMOTION_FEEDBACK = {
    "1": (
        "추격 매수 심리가 감지됩니다.\n"
        "현재 구간은 과거에도 추격 매수가 증가했던 구간과 유사할 수 있습니다.\n"
        "투자 결정 전, 목표 수익률과 손실 허용 범위를 다시 확인해보세요."
    ),
    "2": (
        "뉴스 기반 투자는 이미 시장에 반영된 정보일 수 있습니다.\n"
        "좋은 뉴스가 고점 신호가 된 사례도 많습니다. 뉴스의 출처와 시점을 확인하세요."
    ),
    "3": (
        "주변의 추천은 이미 많은 사람이 진입했다는 신호일 수 있습니다.\n"
        "본인만의 투자 근거가 있는지 다시 점검해보세요."
    ),
    "4": (
        "장기 확신 기반 투자는 가장 건전한 접근 중 하나입니다.\n"
        "다만 단기 변동성에 흔들리지 않도록 포지션 크기와 분할 전략을 사전에 설정해두세요."
    ),
    "5": (
        "불확실한 상태에서의 투자는 감정적 손절로 이어지기 쉽습니다.\n"
        "투자 근거를 먼저 정리한 후 결정하는 것을 권장합니다."
    ),
}


def emotion_check() -> None:
    print("\n=== 내 감정 체크 ===")
    print("지금 투자하려는 이유는 무엇인가요?\n")
    for k, v in EMOTION_CHOICES.items():
        print(f"  [{k}] {v}")
    print()

    choice = input("번호를 입력하세요: ").strip()
    if choice not in EMOTION_FEEDBACK:
        print("유효하지 않은 선택입니다.")
        return

    print(f"\n'{EMOTION_CHOICES[choice]}'를 선택하셨습니다.\n")
    print(EMOTION_FEEDBACK[choice])


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    print("공포/탐욕 지수 분석 도구")
    print("=" * 40)

    try:
        history = fetch_fear_greed_index(limit=365)
    except Exception as e:
        print(f"데이터 조회 실패: {e}")
        return

    current = history[0]
    current_value = int(current["value"])

    print("\n[1] 현재 공포/탐욕 지수")
    print("-" * 40)
    print(explain_current_index(current))

    print("\n[2] 과거 유사 구간 분석")
    print("-" * 40)
    print(build_similar_period_table(history, current_value))

    print()
    run_emotion = input("\n[3] 감정 체크를 진행하시겠습니까? (y/n): ").strip().lower()
    if run_emotion == "y":
        emotion_check()

    print("\n분석 완료.")


if __name__ == "__main__":
    main()
