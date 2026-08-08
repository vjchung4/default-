# -*- coding: utf-8 -*-
"""
트럭/퀵서비스 소요시간 및 요금 계산.

- 소요시간: 카카오맵 API 실제 데이터 (근사 아님)
- 요금: 국토부 화물 표준운임 가이드라인 취지를 참고한 거리+중량 근사식
        (특정 사설 업체 요금표가 아닌, 공적 참고 기준을 쓰는 이유는
         "왜 이 값이냐"는 질문에 근거를 댈 수 있어야 하기 때문)

⚠️ 요금 계수(TRUCK_TIERS 등)는 예시치입니다. 제출 전 국토부 화물
   표준운임 공고 자료 또는 실제 차종별 요금표로 계수를 보정해야 합니다.
"""

from dataclasses import dataclass

import requests

KAKAO_REST_API_KEY = ""  # TODO: Streamlit secrets 등으로 주입

# 근사 요금 계수 (예시치, TODO: 보정 필요)
# ⚠️ 이전 버전은 화물량과 무관하게 소형 트럭 단가(톤당 15,000원)를
#    무한정 곱해서, 화물이 많아질수록 트럭 요금이 비현실적으로 커지는
#    문제가 있었습니다(실제로는 화물이 늘면 5톤·11톤·25톤 등 더 큰
#    차량으로 바뀌고, 큰 차량일수록 톤당 단가는 오히려 낮아지는 규모의
#    경제가 있음). 차량 톤급별 단계 요금으로 교체합니다.
#
# 각 구간은 "이 톤수까지 실을 수 있는 가장 작은 차량" 기준입니다.
# TODO: 실제 화물 운송사 차종별 요금표로 계수 보정 필요.
@dataclass(frozen=True)
class TruckTier:
    max_ton: float
    label: str
    base_won: int
    per_km_won: int
    per_ton_won: int


TRUCK_TIERS: list[TruckTier] = [
    TruckTier(1.0, "1톤", 50_000, 700, 15_000),
    TruckTier(2.5, "2.5톤", 70_000, 750, 12_000),
    TruckTier(5.0, "5톤", 90_000, 800, 9_000),
    TruckTier(11.0, "11톤", 130_000, 900, 6_000),
    TruckTier(25.0, "25톤", 180_000, 1_000, 4_000),
]

# 톤수가 25톤(최대 차급)을 넘으면 이 계수로 계속 계산 — 초과분은 근사치
_MAX_TIER = TRUCK_TIERS[-1]

QUICK_FARE_BASE_WON = 15_000
QUICK_FARE_PER_KM_WON = 1_200  # 퀵은 근거리 급행이라 km당 단가가 더 높음
QUICK_MAX_WEIGHT_KG = 30  # 퀵서비스는 대개 소형화물 한정

# 첫마일/막판마일(출발지↔화물역, 화물역↔도착지) 근거리 운송 — 장거리 트럭과
# 달리 기본료만 낮음(단거리 배차이므로). km당/톤당 단가는 estimate_drayage_fare
# 안에서 estimate_truck_fare와 동일하게 화물량에 맞는 차급을 선택해 적용
# (규모의 경제 반영). ⚠️ 추정치.
DRAYAGE_BASE_WON = 20_000


def get_road_distance_duration(
    origin_lng: float,
    origin_lat: float,
    dest_lng: float,
    dest_lat: float,
) -> dict:
    """카카오 모빌리티 API로 실제 도로 거리(m)/시간(초)/경로 좌표 조회.

    'path'는 지도에 실제 도로를 따라 그리기 위한 [(lat, lng), ...] 목록.
    API 응답의 sections[].roads[].vertexes는 [lng, lat, lng, lat, ...]
    형태로 평탄화돼 있어, 2개씩 끊어서 (lat, lng) 튜플로 변환한다.
    """
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {
        "origin": f"{origin_lng},{origin_lat}",
        "destination": f"{dest_lng},{dest_lat}",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    route = data["routes"][0]
    summary = route["summary"]

    path: list[tuple[float, float]] = []
    for section in route.get("sections", []):
        for road in section.get("roads", []):
            vertexes = road.get("vertexes", [])
            for i in range(0, len(vertexes) - 1, 2):
                lng, lat = vertexes[i], vertexes[i + 1]
                path.append((lat, lng))
    if not path:
        # 폴백: 도로 구간 정보가 없으면 최소한 시작/끝 직선이라도 제공
        path = [(origin_lat, origin_lng), (dest_lat, dest_lng)]

    return {
        "distance_km": summary["distance"] / 1000,
        "duration_min": summary["duration"] / 60,
        "path": path,
    }


def select_truck_tier(weight_ton: float) -> TruckTier:
    """화물을 실을 수 있는 가장 작은 차급을 선택."""
    for tier in TRUCK_TIERS:
        if weight_ton <= tier.max_ton:
            return tier
    return _MAX_TIER  # 25톤 초과 — 최대 차급 계수로 근사


def estimate_truck_fare(distance_km: float, weight_ton: float) -> int:
    """거리+중량 기반 근사 요금 (원), 차급별 단계 요금 적용. ⚠️ 추정치."""
    tier = select_truck_tier(weight_ton)
    fare = tier.base_won + distance_km * tier.per_km_won + weight_ton * tier.per_ton_won
    return round(fare, -3)  # 천원 단위 반올림


def estimate_quick_fare(distance_km: float, weight_kg: float) -> int | None:
    """근거리 급행 근사 요금 (원). 중량 초과 시 None(이용 불가)."""
    if weight_kg > QUICK_MAX_WEIGHT_KG:
        return None
    fare = QUICK_FARE_BASE_WON + distance_km * QUICK_FARE_PER_KM_WON
    return round(fare, -3)


def estimate_drayage_fare(distance_km: float, weight_ton: float) -> int:
    """첫마일/막판마일 근거리 운송 근사 요금 (원). ⚠️ 추정치.

    ⚠️ 이전 버전은 화물량과 무관하게 소형 트럭 톤당 단가를 그대로 곱해서,
    무거운 화물일수록 드레이지(양단 2회) 비용이 철도 구간 자체보다도
    커지는 역전 현상이 있었습니다. estimate_truck_fare와 동일하게
    차급별 단계 요금(규모의 경제)을 적용하되, 단거리 배차라는 특성을
    반영해 기본료만 낮은 DRAYAGE_BASE_WON을 씁니다.
    """
    tier = select_truck_tier(weight_ton)
    fare = DRAYAGE_BASE_WON + distance_km * tier.per_km_won + weight_ton * tier.per_ton_won
    return round(fare, -3)
