"""
버려지는 틈새 선로 시간을 AI로 끌어모으는 가변 화물 슬롯 및 수송 최적화 앱 (데모)

주의: 모든 열차 스케줄/화물 데이터는 시연을 위한 시뮬레이션 데이터입니다.
실제 코레일 운행 데이터가 아닙니다.
"""

import datetime as dt

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Ghost Slot AI", page_icon="🚆", layout="wide")

SEGMENTS = ["의왕", "천안", "대전", "김천구미", "동대구", "밀양", "부산"]
CARGO_TYPES = {
    "컨테이너": {"weight": 1.0, "color": "#2563eb"},
    "시멘트": {"weight": 0.6, "color": "#78716c"},
    "유류": {"weight": 0.9, "color": "#dc2626"},
    "잡화": {"weight": 0.5, "color": "#16a34a"},
}
PASSENGER_TYPES = ["KTX", "무궁화", "새마을"]
DAY_START = dt.datetime.combine(dt.date.today(), dt.time(5, 0))
DAY_END = dt.datetime.combine(dt.date.today(), dt.time(23, 0))
MIN_HEADWAY_MIN = 8  # 여객열차 앞뒤로 확보해야 하는 안전 여유 시간(분)


def gen_passenger_schedule(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    n_trains = 26
    for i in range(n_trains):
        ttype = rng.choice(PASSENGER_TYPES, p=[0.5, 0.3, 0.2])
        start_offset = rng.uniform(0, (DAY_END - DAY_START).total_seconds())
        start = DAY_START + dt.timedelta(seconds=start_offset)
        seg_start = rng.integers(0, len(SEGMENTS) - 2)
        seg_span = rng.integers(2, len(SEGMENTS) - seg_start)
        cur = start
        for s in range(seg_start, seg_start + seg_span):
            dur = rng.integers(4, 9) if ttype == "KTX" else rng.integers(6, 12)
            finish = cur + dt.timedelta(minutes=int(dur))
            rows.append(
                {
                    "train_id": f"{ttype}-{100 + i}",
                    "type": ttype,
                    "segment": SEGMENTS[s],
                    "start": cur,
                    "finish": finish,
                }
            )
            cur = finish + dt.timedelta(minutes=int(rng.integers(2, 6)))
    df = pd.DataFrame(rows)
    return df.sort_values(["segment", "start"]).reset_index(drop=True)


def gen_freight_queue(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1000)
    rows = []
    n_freight = 14
    for i in range(n_freight):
        cargo = rng.choice(list(CARGO_TYPES.keys()))
        seg_start_idx = rng.integers(0, len(SEGMENTS) - 2)
        seg_end_idx = rng.integers(seg_start_idx + 1, len(SEGMENTS))
        wait_since = DAY_START + dt.timedelta(minutes=int(rng.integers(0, 500)))
        rows.append(
            {
                "freight_id": f"화물-{300 + i}",
                "cargo": cargo,
                "origin": SEGMENTS[seg_start_idx],
                "destination": SEGMENTS[seg_end_idx],
                "waiting_since": wait_since,
                "required_span": seg_end_idx - seg_start_idx,
            }
        )
    return pd.DataFrame(rows)


def find_ghost_slots(schedule: pd.DataFrame, min_slot_min: int) -> pd.DataFrame:
    slots = []
    for seg in SEGMENTS:
        seg_df = schedule[schedule["segment"] == seg].sort_values("start")
        cursor = DAY_START
        for _, row in seg_df.iterrows():
            blocked_start = row["start"] - dt.timedelta(minutes=MIN_HEADWAY_MIN)
            blocked_finish = row["finish"] + dt.timedelta(minutes=MIN_HEADWAY_MIN)
            if blocked_start > cursor:
                gap_min = (blocked_start - cursor).total_seconds() / 60
                if gap_min >= min_slot_min:
                    slots.append(
                        {
                            "segment": seg,
                            "slot_start": cursor,
                            "slot_end": blocked_start,
                            "gap_min": round(gap_min, 1),
                        }
                    )
            cursor = max(cursor, blocked_finish)
        if DAY_END > cursor:
            gap_min = (DAY_END - cursor).total_seconds() / 60
            if gap_min >= min_slot_min:
                slots.append(
                    {
                        "segment": seg,
                        "slot_start": cursor,
                        "slot_end": DAY_END,
                        "gap_min": round(gap_min, 1),
                    }
                )
    return pd.DataFrame(slots).sort_values("slot_start").reset_index(drop=True)


def score_match(freight_row, slot_row, cargo_weight_pref: float, wait_weight_pref: float) -> float:
    cargo_score = CARGO_TYPES[freight_row["cargo"]]["weight"]
    waited_min = (slot_row["slot_start"] - freight_row["waiting_since"]).total_seconds() / 60
    waited_min = max(waited_min, 0)
    wait_score = min(waited_min / 300, 1.0)
    fit_score = min(slot_row["gap_min"] / 45, 1.0)
    return cargo_weight_pref * cargo_score + wait_weight_pref * wait_score + (1 - cargo_weight_pref - wait_weight_pref) * fit_score


def build_recommendations(slots: pd.DataFrame, freight: pd.DataFrame, cargo_w: float, wait_w: float, exclude_ids: set) -> pd.DataFrame:
    candidates = freight[~freight["freight_id"].isin(exclude_ids)].copy()
    recs = []
    used_freight = set()
    for _, slot in slots.iterrows():
        seg_idx = SEGMENTS.index(slot["segment"])
        best = None
        best_score = -1
        for _, f in candidates.iterrows():
            if f["freight_id"] in used_freight:
                continue
            o_idx = SEGMENTS.index(f["origin"])
            if o_idx != seg_idx:
                continue
            if f["waiting_since"] > slot["slot_start"]:
                continue
            score = score_match(f, slot, cargo_w, wait_w)
            if score > best_score:
                best_score = score
                best = f
        if best is not None:
            wait_before_min = (slot["slot_start"] - best["waiting_since"]).total_seconds() / 60
            est_saved_min = max(10, min(wait_before_min * 0.5, 60))
            recs.append(
                {
                    "slot_start": slot["slot_start"],
                    "slot_end": slot["slot_end"],
                    "segment": slot["segment"],
                    "gap_min": slot["gap_min"],
                    "freight_id": best["freight_id"],
                    "cargo": best["cargo"],
                    "destination": best["destination"],
                    "score": round(best_score, 2),
                    "est_saved_min": int(est_saved_min),
                }
            )
            used_freight.add(best["freight_id"])
    return pd.DataFrame(recs)


def init_state():
    if "seed" not in st.session_state:
        st.session_state.seed = 42
    if "approval_log" not in st.session_state:
        st.session_state.approval_log = []
    if "approved_freight_ids" not in st.session_state:
        st.session_state.approved_freight_ids = set()


init_state()

st.title("🚆 Ghost Slot AI — 가변 화물 슬롯 최적화")
st.caption("여객열차가 지나간 뒤 비는 '유휴 선로 시간'을 실시간으로 포착해 화물열차에 매칭하는 관제사용 데모 앱입니다. (전 데이터는 시뮬레이션)")

with st.sidebar:
    st.header("⚙️ 시뮬레이션 설정")
    if st.button("🔄 오늘 스케줄 재시뮬레이션"):
        st.session_state.seed = np.random.randint(0, 100000)
        st.session_state.approval_log = []
        st.session_state.approved_freight_ids = set()

    min_slot_min = st.slider("최소 유휴 슬롯 길이 (분)", 10, 40, 18)
    st.markdown("**AI 추천 가중치**")
    cargo_w = st.slider("화물 종류(수익성) 가중치", 0.0, 0.8, 0.4)
    wait_w = st.slider("대기 시간(공정성) 가중치", 0.0, 0.8, 0.35)
    if cargo_w + wait_w > 0.95:
        cargo_w, wait_w = 0.4, 0.35
        st.caption("가중치 합이 너무 커서 기본값으로 보정했습니다.")

passenger_df = gen_passenger_schedule(st.session_state.seed)
freight_df = gen_freight_queue(st.session_state.seed)
ghost_slots = find_ghost_slots(passenger_df, min_slot_min)
recommendations = build_recommendations(ghost_slots, freight_df, cargo_w, wait_w, st.session_state.approved_freight_ids)

tab1, tab2, tab3 = st.tabs(["📊 관제 대시보드", "🤖 AI 추천 & 원클릭 승인", "📲 현장 알림 로그"])

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("오늘 탐지된 유휴 슬롯", f"{len(ghost_slots)}건")
    col2.metric("대기 중인 화물열차", f"{len(freight_df) - len(st.session_state.approved_freight_ids)}편성")
    col3.metric("AI 매칭 가능 추천", f"{len(recommendations)}건")
    total_saved = int(recommendations["est_saved_min"].sum()) if not recommendations.empty else 0
    col4.metric("예상 총 단축 시간", f"{total_saved}분")

    st.subheader("여객열차 스케줄 & 유휴 선로 슬롯")
    fig = px.timeline(
        passenger_df,
        x_start="start",
        x_end="finish",
        y="segment",
        color="type",
        category_orders={"segment": SEGMENTS},
    )
    for _, slot in ghost_slots.iterrows():
        fig.add_shape(
            type="rect",
            x0=slot["slot_start"],
            x1=slot["slot_end"],
            y0=SEGMENTS.index(slot["segment"]) - 0.4,
            y1=SEGMENTS.index(slot["segment"]) + 0.4,
            fillcolor="rgba(34,197,94,0.25)",
            line=dict(color="rgba(34,197,94,0.8)", dash="dot"),
            layer="below",
        )
    fig.update_yaxes(categoryorder="array", categoryarray=SEGMENTS)
    fig.update_layout(height=450, legend_title_text="열차 종류")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("초록 점선 영역 = AI가 탐지한 유휴 선로 슬롯 (Ghost Slot)")

    st.subheader("화물열차 대기열")
    show_freight = freight_df[~freight_df["freight_id"].isin(st.session_state.approved_freight_ids)]
    st.dataframe(show_freight, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("AI 추천 슬롯 목록")
    if recommendations.empty:
        st.info("현재 조건에서 매칭 가능한 추천이 없습니다. 사이드바에서 최소 슬롯 길이를 줄여보세요.")
    for i, rec in recommendations.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(
                    f"**{rec['slot_start']:%H:%M} ~ {rec['slot_end']:%H:%M}** · "
                    f"`{rec['segment']}` 구간 · 유휴 {rec['gap_min']}분"
                )
                st.markdown(
                    f"추천 편성: **{rec['freight_id']}** ({rec['cargo']} → {rec['destination']}) · "
                    f"AI 점수 {rec['score']} · 예상 단축 **{rec['est_saved_min']}분**"
                )
            with c2:
                if st.button("✅ 원클릭 승인", key=f"approve_{rec['freight_id']}_{i}"):
                    st.session_state.approved_freight_ids.add(rec["freight_id"])
                    st.session_state.approval_log.append(
                        {
                            "approved_at": dt.datetime.now().strftime("%H:%M:%S"),
                            "message": (
                                f"[기관사 앱 Push] {rec['segment']} 구간, {rec['slot_start']:%H:%M} 조기 출발 승인. "
                                f"{rec['freight_id']} ({rec['cargo']}) → {rec['destination']}. "
                                f"예상 도착 {rec['est_saved_min']}분 단축."
                            ),
                        }
                    )
                    st.rerun()

with tab3:
    st.subheader("현장(기관사/화물역) 알림 로그")
    if not st.session_state.approval_log:
        st.info("아직 승인된 슬롯이 없습니다. 'AI 추천 & 원클릭 승인' 탭에서 승인해보세요.")
    else:
        for log in reversed(st.session_state.approval_log):
            st.success(f"`{log['approved_at']}` {log['message']}")
