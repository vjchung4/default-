"""Korail Relai 데모용 목업 데이터 생성 모듈."""

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

# 주요 화물역 (실제 코레일 화물역 명칭 기반 위경도 근사치)
STATIONS = {
    "의왕(ICD)": (37.3448, 126.9682),
    "오봉": (37.4390, 126.8862),
    "대전조차장": (36.3504, 127.3845),
    "부산진": (35.1370, 129.0403),
    "양산": (35.3350, 129.0378),
    "동해": (37.5075, 129.1144),
    "울산항": (35.5040, 129.3870),
    "광양항": (34.9060, 127.7420),
}

CARGO_TYPES = ["컨테이너 20FT", "컨테이너 40FT", "냉동 컨테이너", "일반 화물"]

SHIPPER_NAMES = ["대한전자(주)", "한빛물류", "동서식품", "삼진화학", "케이스틸", "네오패키징"]

DRIVER_NAMES = ["김도현", "이수민", "박정우", "최은서", "장민호"]

STAGE_LABELS = [
    "화주 공장 출발",
    "육상 트럭 이동중",
    "화물역(CY) 도착",
    "철도 상차 대기",
    "철도 운송중",
    "목적지 화물역 도착",
    "육상 트럭 배송중",
    "최종 목적지 도착",
]


def _rand_point_near(lat, lon, spread=0.05):
    return lat + random.uniform(-spread, spread), lon + random.uniform(-spread, spread)


def generate_shipments(n=6):
    rows = []
    station_names = list(STATIONS.keys())
    for i in range(n):
        origin_station = random.choice(station_names)
        dest_station = random.choice([s for s in station_names if s != origin_station])
        stage_idx = random.randint(1, len(STAGE_LABELS) - 2)
        base_time = datetime.now() - timedelta(hours=random.randint(1, 10))
        eta = datetime.now() + timedelta(minutes=random.randint(20, 260))
        delay_risk = round(random.uniform(2, 38), 1)

        rows.append(
            {
                "화물ID": f"KRL-{2026000 + i}",
                "화주": random.choice(SHIPPER_NAMES),
                "화물종류": random.choice(CARGO_TYPES),
                "출발지": f"{origin_station} 인근 공장",
                "출발화물역": origin_station,
                "도착화물역": dest_station,
                "최종목적지": f"{dest_station} 인근 물류센터",
                "현재단계": stage_idx,
                "단계명": STAGE_LABELS[stage_idx],
                "접수시각": base_time,
                "AI예측ETA": eta,
                "지연위험도(%)": delay_risk,
                "AI절감비용(원)": random.randint(35000, 180000),
                "AI절감시간(분)": random.randint(25, 140),
            }
        )
    return pd.DataFrame(rows)


def generate_return_cargo_options(current_station, n=4):
    """트럭 기사가 화물 하차 후 복귀 시 매칭 가능한 화물 목록."""
    station_names = [s for s in STATIONS.keys() if s != current_station]
    rows = []
    for i in range(n):
        dest = random.choice(station_names)
        distance = round(random.uniform(3, 45), 1)
        match_score = round(random.uniform(62, 99), 1)
        rows.append(
            {
                "매칭ID": f"MTC-{random.randint(1000, 9999)}",
                "화주": random.choice(SHIPPER_NAMES),
                "화물종류": random.choice(CARGO_TYPES),
                "픽업위치": f"{current_station} 인근 {random.randint(1,9)}번 화물장",
                "픽업까지거리(km)": distance,
                "목적지": dest,
                "AI매칭점수": match_score,
                "예상추가수익(원)": random.randint(45000, 130000),
                "공차방지여부": "✅ 공차 방지" if match_score > 75 else "△ 검토 필요",
            }
        )
    df = pd.DataFrame(rows).sort_values("AI매칭점수", ascending=False).reset_index(drop=True)
    return df


def generate_driver_today(driver_name):
    origin = random.choice(list(STATIONS.keys()))
    arrival = datetime.now() + timedelta(minutes=random.randint(15, 90))
    return {
        "기사명": driver_name,
        "배차역": origin,
        "도착열차": f"{random.randint(1,9)}0{random.randint(1,9)}열차",
        "도착시각": arrival,
        "컨테이너번호": f"{random.randint(1,6)}번 컨테이너",
        "상차예정시각": arrival + timedelta(minutes=10),
    }


def generate_network_snapshot(n_trucks=14, n_trains=6):
    """관제센터용 실시간 네트워크 스냅샷 (트럭/화차 위치)."""
    trucks = []
    for i in range(n_trucks):
        st = random.choice(list(STATIONS.keys()))
        lat, lon = STATIONS[st]
        plat, plon = _rand_point_near(lat, lon, spread=0.08)
        trucks.append(
            {
                "id": f"TRK-{i:03d}",
                "type": "공차" if random.random() < 0.28 else "적재",
                "lat": plat,
                "lon": plon,
                "인근화물역": st,
            }
        )

    trains = []
    station_names = list(STATIONS.keys())
    for i in range(n_trains):
        a, b = random.sample(station_names, 2)
        lat_a, lon_a = STATIONS[a]
        lat_b, lon_b = STATIONS[b]
        t = random.random()
        trains.append(
            {
                "id": f"화차-{i:02d}",
                "출발역": a,
                "도착역": b,
                "lat": lat_a + (lat_b - lat_a) * t,
                "lon": lon_a + (lon_b - lon_a) * t,
                "진행률(%)": round(t * 100, 1),
            }
        )

    return pd.DataFrame(trucks), pd.DataFrame(trains)


def kpi_before_after():
    return {
        "공차운행률": {"기존": 34.2, "Relai적용": 11.8},
        "CY평균대기시간(분)": {"기존": 96, "Relai적용": 27},
        "화주평균비용(만원/건)": {"기존": 42.5, "Relai적용": 33.1},
        "평균리드타임(시간)": {"기존": 18.4, "Relai적용": 13.9},
    }
