# -*- coding: utf-8 -*-
"""
공공데이터포털 "한국철도공사_화물열차운행 시간표"(정적 파일데이터, CSV) 파싱.

출처: data.go.kr, 파일ID 15042241 (2025-04-14 기준 스냅샷)
⚠️ 실시간 API가 아니라 특정 시점 스냅샷입니다. 실제 운행은 임시열차 편성,
   선로 사정 등으로 바뀔 수 있어 "확정 시각표"가 아닌 "참고 시각표"로
   취급해야 합니다.

컬럼: 열차종별, 열차번호, 상하, 순서, 역명, 도착시각, 출발시각,
      정차사유, 운행선, 운행요일
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

CSV_PATH = Path(__file__).parent / "freight_train_schedule.csv"

# Python date.weekday(): 0=월요일 ... 6=일요일
_WEEKDAY_CHARS = ["월", "화", "수", "목", "금", "토", "일"]


def _parse_service_days(text: str) -> set[str]:
    if text == "매일":
        return set(_WEEKDAY_CHARS)
    return set(text)


@dataclass
class TrainMatch:
    train_no: str
    departure_time: time
    arrival_time: time
    overnight: bool  # 도착시각이 다음날로 넘어가는지 (출발시각보다 이르면 다음날로 간주)
    service_days: set[str]
    line: str


_rows_cache: list[dict] | None = None


def _get_rows() -> list[dict]:
    global _rows_cache
    if _rows_cache is None:
        with open(CSV_PATH, encoding="cp949") as f:
            _rows_cache = list(csv.DictReader(f))
    return _rows_cache


_by_train_cache: dict[str, list[dict]] | None = None


def _get_by_train() -> dict[str, list[dict]]:
    global _by_train_cache
    if _by_train_cache is None:
        by_train: dict[str, list[dict]] = {}
        for r in _get_rows():
            by_train.setdefault(r["열차번호"], []).append(r)
        _by_train_cache = by_train
    return _by_train_cache


def find_direct_trains(origin_station: str, dest_station: str) -> list[TrainMatch]:
    """두 역을 이 순서(origin -> dest)로 모두 경유하는 열차 목록 (요일 필터 전)."""
    results = []
    for train_no, stops in _get_by_train().items():
        stops_sorted = sorted(stops, key=lambda x: int(x["순서"]))
        names = [s["역명"] for s in stops_sorted]
        if origin_station not in names or dest_station not in names:
            continue
        i1, i2 = names.index(origin_station), names.index(dest_station)
        if i1 >= i2:
            continue
        o, d = stops_sorted[i1], stops_sorted[i2]
        dep_t = datetime.strptime(o["출발시각"], "%H:%M:%S").time()
        arr_t = datetime.strptime(d["도착시각"], "%H:%M:%S").time()
        results.append(TrainMatch(
            train_no=train_no,
            departure_time=dep_t,
            arrival_time=arr_t,
            overnight=arr_t < dep_t,
            service_days=_parse_service_days(o["운행요일"]),
            line=o["운행선"],
        ))
    return results


def find_next_departure(
    origin_station: str, dest_station: str, after_dt: datetime, search_days: int = 7
) -> dict | None:
    """after_dt 이후 가장 빠르게 출발하는 실제 열차. 없으면 None.

    ⚠️ 환승(중간에 다른 열차로 갈아타는 경로)은 고려하지 않음 — 직행
    열차만 찾음. 실제로는 화물도 중계 운송(다른 열차로 환적)이 흔하지만
    이 근사에서는 단순화함.
    """
    candidates = find_direct_trains(origin_station, dest_station)
    if not candidates:
        return None

    best: TrainMatch | None = None
    best_departure_dt: datetime | None = None

    for day_offset in range(search_days):
        check_date = after_dt.date() + timedelta(days=day_offset)
        day_char = _WEEKDAY_CHARS[check_date.weekday()]
        for c in candidates:
            if day_char not in c.service_days:
                continue
            dep_dt = datetime.combine(check_date, c.departure_time)
            if dep_dt < after_dt:
                continue
            if best_departure_dt is None or dep_dt < best_departure_dt:
                best_departure_dt = dep_dt
                best = c
        if best is not None:
            break

    if best is None or best_departure_dt is None:
        return None

    arr_date = best_departure_dt.date() + timedelta(days=1 if best.overnight else 0)
    arrival_dt = datetime.combine(arr_date, best.arrival_time)

    return {
        "train_no": best.train_no,
        "departure_dt": best_departure_dt,
        "arrival_dt": arrival_dt,
        "duration_min": round((arrival_dt - best_departure_dt).total_seconds() / 60),
        "line": best.line,
    }
