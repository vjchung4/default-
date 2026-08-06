# -*- coding: utf-8 -*-
"""
gemini_assist.py의 폐쇄망(오프라인) 대체 모듈.

같은 6개 함수를 동일한 시그니처로 구현했다 — 팀원 쪽에서 바꿀 부분은
import 문 한 줄뿐이다.

    from gemini_assist import parse_free_text_order, ...
    ->
    from offline_assist import parse_free_text_order, ...

Gemini(외부 API) 대신 정규식/키워드 매칭 + 결정론적 규칙으로 처리하므로
인터넷 연결이 전혀 필요 없다 (사내 인트라넷/폐쇄망에서도 100% 동작).
숫자는 항상 호출부(계산 코드)가 넘겨준 값을 그대로 문장에 꽂아 넣을 뿐,
새로 만들어내지 않는다 — gemini_assist.py가 지켜온 "계산은 코드,
설명은 AI" 원칙을 그대로 따른다.

한계: 자연어 파싱 커버리지가 LLM보다 좁다. 여기 정의된 패턴/키워드
바깥의 표현(예: 아주 특이한 어순, 신조어)은 못 알아챈다. 해커톤
데모에서 다루는 대표적인 문장 패턴은 커버하지만, 실서비스라면
사내망에 배포 가능한 온프레미스 소형 한국어 모델(sLLM)로 이 모듈을
다시 교체하는 편이 낫다.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


# ---------- parse_free_text_order ----------

# 화물 결절점 + 주요 도시명 (rail_freight_nodes.py의 화물역 목록 기준으로
# 보강했다. 실제 서비스라면 이 목록을 화물역/거점 마스터 데이터와 동기화)
KNOWN_PLACES = [
    "오봉", "의왕", "부산항", "부산진", "천안", "순천", "포항",
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "수원", "성남", "고양", "용인", "창원", "전주", "제주", "청주",
    "여수", "김해", "화성", "평택", "구미",
]

_ORIGIN_PATTERNS = [r"([가-힣]+)\s*(?:에서|출발해서|출발|부터)"]
_DEST_PATTERNS = [r"([가-힣]+)\s*(?:으로|로|까지|도착)"]

_CARGO_TYPE_KEYWORDS = [
    "일반화물", "냉동", "냉장", "신선식품", "위험물", "화학물질", "가스",
    "파손주의", "고가품", "정밀", "전자부품", "농산물", "과일", "채소",
    "수산물", "화훼",
]


def _extract_place(text: str, patterns: list[str], exclude: str | None = None) -> str | None:
    """알려진 지명이 포함된 매치를 우선한다 — "3시까지"의 "시"처럼 지명이
    아닌 글자가 먼저 걸리는 오탐(false positive)을 피하기 위해, 문장 내
    모든 후보를 훑어보고 KNOWN_PLACES에 걸리는 것부터 채택한다.
    """
    fallback = None
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            candidate = m.group(1)
            if candidate == exclude:
                continue
            for place in KNOWN_PLACES:
                if place in candidate:
                    return place
            if fallback is None:
                fallback = candidate
    return fallback


def _extract_weight_kg(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|킬로그램|킬로)", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(t|톤|ton)", text, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 1000
    return None


def _extract_long_side_cm(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(cm|센치|센티미터)", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m|미터)(?!\w)", text, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 100
    return None


_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _extract_date(text: str, now: datetime) -> str | None:
    today = now.date()
    if "모레" in text:
        return (today + timedelta(days=2)).isoformat()
    if "내일" in text:
        return (today + timedelta(days=1)).isoformat()
    if "오늘" in text or "최대한 빨리" in text or "지금 바로" in text or "지금바로" in text:
        return today.isoformat()

    m = re.search(r"다음\s*주\s*([월화수목금토일])요일", text)
    if m:
        target = _WEEKDAYS.index(m.group(1))
        days_ahead = (target - today.weekday()) % 7 + 7
        return (today + timedelta(days=days_ahead)).isoformat()

    m = re.search(r"([월화수목금토일])요일", text)
    if m:
        target = _WEEKDAYS.index(m.group(1))
        days_ahead = (target - today.weekday()) % 7 or 7
        return (today + timedelta(days=days_ahead)).isoformat()

    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year if (month, day) >= (today.month, today.day) else today.year + 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _extract_time(text: str, now: datetime) -> str | None:
    if "최대한 빨리" in text or "지금 바로" in text or "지금바로" in text:
        return now.strftime("%H:%M")

    m = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시\s*(\d{1,2})?\s*분?", text)
    if m:
        ampm, hour, minute = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if ampm == "오후" and hour < 12:
            hour += 12
        if ampm == "오전" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def parse_free_text_order(text: str) -> dict:
    """자연어 입력 -> 구조화된 필드(JSON). gemini_assist.parse_free_text_order와 동일한 반환 스키마."""
    now = now_kst()

    origin = _extract_place(text, _ORIGIN_PATTERNS)
    destination = _extract_place(text, _DEST_PATTERNS, exclude=origin)

    weight_kg = _extract_weight_kg(text)
    long_side_cm = _extract_long_side_cm(text)
    desired_date = _extract_date(text, now)
    desired_time = _extract_time(text, now)

    cargo_type = next((kw for kw in _CARGO_TYPE_KEYWORDS if kw in text), None)

    missing_fields = []
    if not origin:
        missing_fields.append("origin")
    if not destination:
        missing_fields.append("destination")
    if weight_kg is None:
        missing_fields.append("weight_kg")

    clarification_message = None
    if missing_fields:
        label = {"origin": "출발지", "destination": "도착지", "weight_kg": "화물 중량"}
        names = ", ".join(label[f] for f in missing_fields)
        clarification_message = f"{names} 정보를 확인하지 못했어요. 조금 더 자세히 알려주시겠어요?"

    unset_optional_fields = [
        name
        for name, value in [
            ("cargo_type", cargo_type),
            ("long_side_cm", long_side_cm),
            ("desired_date", desired_date),
            ("desired_time", desired_time),
        ]
        if value is None
    ]

    return {
        "origin": origin,
        "destination": destination,
        "cargo_type": cargo_type,
        "weight_kg": weight_kg,
        "long_side_cm": long_side_cm,
        "desired_date": desired_date,
        "desired_time": desired_time,
        "missing_fields": missing_fields,
        "clarification_message": clarification_message,
        "unset_optional_fields": unset_optional_fields,
    }


# ---------- classify_cargo_category ----------

CARGO_CATEGORIES = ["일반화물", "냉장·냉동", "위험물", "파손주의·고가품", "농산물·생물"]

# cargo.py의 _KEYWORD_MAP과 동일한 키워드 체계 (동일 분류 기준 유지)
_CATEGORY_KEYWORD_MAP = {
    "위험물": ["위험물", "화학물질", "가스", "인화성", "폭발물", "배터리", "리튬", "황산", "질산", "염산", "부식성"],
    "냉장·냉동": ["냉동", "냉장", "신선식품", "아이스"],
    "농산물·생물": ["농산물", "과일", "채소", "생물", "수산물", "화훼"],
    "파손주의·고가품": ["파손", "유리", "고가", "정밀", "전자부품", "귀중품"],
}


def classify_cargo_category(cargo_type_text: str) -> str:
    for category, keywords in _CATEGORY_KEYWORD_MAP.items():
        if any(kw in cargo_type_text for kw in keywords):
            return category
    return "일반화물"


# ---------- explain_comparison ----------


def explain_comparison(comparison_rows: list[dict], consolidation_note: str) -> str:
    numeric_fare_rows = [r for r in comparison_rows if isinstance(r.get("요금(원)"), (int, float))]

    if not numeric_fare_rows:
        return f"이용 가능한 수단의 요금 정보를 확인하지 못했습니다. {consolidation_note}"

    cheapest = min(numeric_fare_rows, key=lambda r: r["요금(원)"])
    fastest = min(comparison_rows, key=lambda r: r["소요시간(분)"])

    sentences = [
        f"가장 저렴한 수단은 {cheapest['수단']}(으)로 {cheapest['요금(원)']:,}원이 예상됩니다.",
    ]
    if fastest["수단"] == cheapest["수단"]:
        sentences.append(f"소요시간도 {fastest['소요시간(분)']}분으로 가장 빠릅니다.")
    else:
        sentences.append(f"가장 빠른 수단은 {fastest['수단']}(으)로 {fastest['소요시간(분)']}분이 소요됩니다.")

    if consolidation_note:
        sentences.append(consolidation_note)

    return " ".join(sentences)


# ---------- explain_carbon_savings ----------


def explain_carbon_savings(gwp_savings_kg: float, mileage: int, tree_equivalent: float) -> str:
    return (
        f"트럭 전용 운송 대비 {gwp_savings_kg:.1f} kgCO2eq를 절감해, "
        f"나무 {tree_equivalent:.1f}그루가 1년간 흡수하는 양과 비슷한 효과예요. "
        f"이번 운송으로 탄소 마일리지 {mileage:,}P가 적립될 예정입니다."
    )


# ---------- assess_delay_risk ----------

_BUSY_WEEKDAYS = {"Friday", "Saturday", "Sunday"}


def assess_delay_risk(signals: dict) -> dict:
    reasons = []
    risk_score = 0

    if not signals.get("시각표출처"):
        risk_score += 2
        reasons.append("시각표 매칭 정보가 없어 예상 소요시간의 신뢰도가 낮음")

    if signals.get("결합배송여부"):
        risk_score += 1
        reasons.append("여러 화주와 결합배송 중이라 상하차 순서 조율에 따른 지연 여지가 있음")

    if signals.get("출발요일") in _BUSY_WEEKDAYS:
        risk_score += 1
        reasons.append("주말 전후로 물동량이 몰리는 시기")

    if risk_score >= 3:
        level = "높음"
    elif risk_score >= 2:
        level = "보통"
    else:
        level = "낮음"

    reason = ", ".join(reasons) + "." if reasons else "특이 위험 신호가 확인되지 않아 정상 운행이 예상됩니다."
    return {"level": level, "reason": reason}


# ---------- explain_match ----------


def explain_match(score: float, factors: dict) -> str:
    weight = factors.get("중량톤")
    min_ton = factors.get("결합최소기준톤")
    grouped = factors.get("결합배송여부")

    parts = []
    if weight is not None and min_ton:
        ratio_pct = weight / min_ton * 100
        parts.append(f"중량 {weight}톤(결합 기준 {min_ton}톤 대비 {ratio_pct:.0f}%)")
    if grouped:
        parts.append("이미 다른 화주와 결합배송 중이라는 점")

    basis = ", ".join(parts) if parts else "제공된 신호"
    return f"{basis}을 근거로 결합적합도 {score}점이 산정됐습니다."
