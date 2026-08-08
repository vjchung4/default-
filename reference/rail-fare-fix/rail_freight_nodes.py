# -*- coding: utf-8 -*-
"""
철도 화물 결절점(화물역) 좌표 및 근사 상수.

전철화 여부(electrified)는 나무위키 "철도 노선 정보/대한민국" 문서의
노선별 전철화 표를 참고했습니다. 위키 문서라 신뢰도는 국가철도공단
공식 자료보다 낮으므로, 제출 전 교차 검증을 권장합니다.

⚠️ 2026-07-29 수정: 아래 화물역 목록은 실제 화물열차 시각표 데이터
   (data.go.kr "한국철도공사_화물열차운행 시간표", rail_schedule.py 참고)의
   정차사유(시발/종착/화물취급) 빈도를 기준으로 재선정했습니다.
   기존에 있던 "대구역(화물)"은 실제 데이터상 화물열차가 통과만 하고
   상하차 취급이 없어 삭제했고, "여수국가산단역"도 실제 데이터에 없어
   더 활발한 실제 터미널인 "순천"으로 교체했습니다. "부산신항역"은
   실제 역명이 "부산항"이라 schedule_station 필드로 매핑해뒀습니다.

TODO(제출 전 확인 필요):
   - RAIL_TON_KM_RATE: 실제 화물역 간 계약운임 사례나 국토부 자료로 보정
   - AVG_FREIGHT_SPEED_KMH: 화물열차 실제 시각표 매칭 실패 시 폴백용 근사치
   - electrified 값: 국가철도공단/코레일 공식 자료로 교차 검증
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FreightNode:
    name: str  # 화면 표시용 이름
    lat: float
    lng: float
    region: str
    electrified: bool  # 접속 지선 기준 전철화 여부 (나무위키 참고, 교차검증 필요)
    schedule_station: str  # rail_schedule.py CSV의 실제 역명 (조회 키)


# 화물열차 시각표 실데이터에서 시발/종착/화물취급 빈도가 높은 실제 터미널만
# 선정 (근거: rail_schedule.py가 참조하는 CSV 분석 결과)
FREIGHT_NODES: list[FreightNode] = [
    FreightNode("오봉역", 37.4256, 126.9008, "수도권", electrified=True, schedule_station="오봉"),
    FreightNode("의왕역", 37.3308, 126.9683, "수도권", electrified=True, schedule_station="의왕"),
    FreightNode("부산항역(신항)", 35.0762, 128.8095, "부산·경남", electrified=True, schedule_station="부산항"),
    FreightNode("부산진역", 35.1298, 129.0403, "부산·경남", electrified=True, schedule_station="부산진"),
    FreightNode("천안역", 36.8095, 127.1444, "충청", electrified=True, schedule_station="천안"),
    FreightNode("순천역", 34.9506, 127.4875, "전남", electrified=True, schedule_station="순천"),
    FreightNode("포항역", 36.0653, 129.3690, "경북", electrified=True, schedule_station="포항"),
]

# 화물역 간 컨테이너(20피트, 최대 약 20톤) 적재 기준 — 단독 발송 판정용
CONTAINER_MAX_TON = 20.0

# LCL(소량 컨테이너 화물) 개념의 최소 결합 기준 — 여러 화주를 합쳐
# 철도가 경제적으로 유리해지는 최소 물량. 컨테이너를 완전히 채울 필요는
# 없고, 포워더가 여러 화주 화물을 나눠 싣는 공유 적재가 실무에서 일반적.
# ⚠️ 추정치 — 실제로는 화물 부피(CBM), 화물 종류(혼적 가능 여부),
# 코레일/포워더와의 최소 물량 계약 조건 등으로 결정되므로 국토부/
# 물류업계 자료로 보정 필요.
MIN_CONSOLIDATION_TON = 5.0

# 철도(팔레트 단위) 취급 최소 중량 — 이보다 가벼우면 소포/택배 영역이라
# 철도 화물 통합 자체를 검토하지 않고 퀵/KTX특송으로 안내.
# ⚠️ 추정치 — 실제 포워더의 최소 접수 중량 기준으로 보정 필요.
MIN_SHIPMENT_TON_FOR_RAIL = 0.5  # 500kg

# 철도 화물 최저운임 적용 기준 톤수 — 실제 화물 운임은 대부분
# "최저 O톤 기준으로 청구" 관행이 있어, 이보다 가벼운 화물도
# 이 톤수만큼 요금이 부과됨. ⚠️ 추정치, 코레일/포워더 실제 최저운임
# 기준으로 보정 필요.
MIN_BILLING_TON = 1.0

# 철도 화물역 상하차 취급수수료 (편도 1회, 원) — ⚠️ 추정치.
# 출발역 상차 + 도착역 하차 총 2회 부과됨(코드에서 ×2 처리).
RAIL_HANDLING_FEE_WON = 30_000

# 화물열차 평균 표정속도 근사치 (km/h) — ⚠️ 추정치, 공식 자료로 보정 필요
AVG_FREIGHT_SPEED_KMH = 45.0

# 톤·km 당 근사 운임 (원) — ⚠️ 추정치. 코레일에 실제 운임 데이터를
# 요청했으나 "정상운임(공시운임)을 참고하라"는 답변을 받아, 공식 임률표를
# 아직 확보하지 못한 상태에서 역산한 잠정값입니다.
#
# 역산 근거: 한국교통연구원(KOTI) "도로와 철도화물수송 경쟁력 분석을 통한
# 전환교통 대응방안" 연구에 따르면 철도는 대략 300km 이상 구간부터 도로
# 대비 비용 우위를 갖는다는 정성적 결과가 있습니다. 이 손익분기점(300km)에서
# road_cost.py의 트럭 요금(국토부 표준운임 참고, 20ft 컨테이너 실중량
# 약 18톤 기준 25톤급 티어)과 이 파일의 estimate_rail_leg() 운임이
# 같아지도록 RAIL_TON_KM_RATE_WON을 역산하면 약 91원/톤·km이 나옵니다.
# (이전 값 55원은 손익분기점 자체가 성립하지 않을 만큼 낮아, 모든 거리에서
# 철도가 비현실적으로 압도적으로 저렴하게 계산되는 문제가 있었습니다.)
#
# 여전히 실제 공시운임표는 아니므로, 확보되는 대로 이 값을 교체해야 합니다.
RAIL_TON_KM_RATE_WON = 91  # 원/톤·km, TODO: 코레일 공시 정상운임표로 보정

# 화물역 입출고(상하차, 마지막 트럭 연계) 고정 소요시간 (분)
TERMINAL_HANDLING_MIN = 60
