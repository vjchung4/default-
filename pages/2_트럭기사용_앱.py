from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from utils.data import DRIVER_NAMES, STATIONS, generate_driver_today, generate_return_cargo_options

st.set_page_config(page_title="트럭 기사용 앱 | Korail Relai", page_icon="🚚", layout="centered")

st.title("🚚 트럭 기사용 Relai 앱")
st.caption("배차 안내부터 복귀 화물(공차 방지) 자동 연계 추천까지, 모바일 앱처럼 확인해 보세요.")

driver = st.selectbox("기사님 성함", DRIVER_NAMES)

if "driver_task" not in st.session_state or st.session_state.get("driver_task_name") != driver:
    st.session_state.driver_task = generate_driver_today(driver)
    st.session_state.driver_task_name = driver
    st.session_state.picked_up = False
    st.session_state.accepted_match = None

task = st.session_state.driver_task

st.divider()

# ---- 폰 프레임 느낌의 카드 ----
st.markdown(
    """
    <div style="max-width:420px;margin:auto;border:1px solid #dfe3e8;border-radius:20px;
                padding:1.2rem 1.4rem;background:#ffffff;box-shadow:0 2px 10px rgba(0,0,0,0.06);">
    """,
    unsafe_allow_html=True,
)

st.markdown(f"#### 📍 {task['기사명']} 기사님, 오늘의 배차")

remaining_min = int((task["도착시각"] - datetime.now()).total_seconds() // 60)
st.info(
    f"**{task['배차역']} {task['도착시각'].strftime('%H시 %M분')} 도착 화물열차 {task['도착열차']}**\n\n"
    f"**{task['컨테이너번호']} 상차 대기 중** (상차 예정 {task['상차예정시각'].strftime('%H:%M')})"
)
st.metric("열차 도착까지", f"{max(remaining_min,0)}분 남음")

if not st.session_state.picked_up:
    if st.button("✅ 상차 완료 처리", use_container_width=True, type="primary"):
        st.session_state.picked_up = True
        st.rerun()
else:
    st.success("상차 완료! 다음 이동지(대전 공장)로 출발합니다. 아래 복귀 화물 추천을 확인하세요. 👇")

st.markdown("</div>", unsafe_allow_html=True)

st.divider()

if st.session_state.picked_up:
    st.subheader("🔁 복귀 화물 자동 연계 추천 (공차 방지)")
    st.caption(f"'{task['배차역']}' 인근에서 상차 후 복귀 방향과 일치하는 화물을 AI가 실시간으로 묶음 매칭했습니다.")

    if "return_options" not in st.session_state:
        st.session_state.return_options = generate_return_cargo_options(task["배차역"], n=4)
    options = st.session_state.return_options

    for i, r in options.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{r['화주']}** · {r['화물종류']}")
                st.caption(f"📍 픽업: {r['픽업위치']} ({r['픽업까지거리(km)']}km) → 🎯 목적지: {r['목적지']}")
                st.caption(f"예상 추가 수익: **{r['예상추가수익(원)']:,}원** · {r['공차방지여부']}")
            with c2:
                st.metric("AI 매칭점수", f"{r['AI매칭점수']}")
                if st.session_state.accepted_match is None:
                    if st.button("수락", key=f"accept_{r['매칭ID']}", use_container_width=True):
                        st.session_state.accepted_match = r["매칭ID"]
                        st.rerun()
                elif st.session_state.accepted_match == r["매칭ID"]:
                    st.success("수락됨 ✅")

    if st.session_state.accepted_match:
        matched = options[options["매칭ID"] == st.session_state.accepted_match].iloc[0]
        st.success(
            f"🎉 복귀 화물이 확정되었습니다! **{matched['화주']}** 화물을 **{matched['목적지']}** 방향으로 운송하며 "
            f"공차 운행을 방지했습니다. (추가 수익 {matched['예상추가수익(원)']:,}원)"
        )

    # 지도 시각화
    st_lat, st_lon = STATIONS[task["배차역"]]
    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(
        lat=[st_lat], lon=[st_lon], mode="markers+text",
        marker=dict(size=16, color="#0059b3"), text=[f"{task['배차역']} (현재 위치)"], textposition="top center",
        name="현재 위치",
    ))
    dest_stations = options["목적지"].unique()
    for dest in dest_stations:
        d_lat, d_lon = STATIONS[dest]
        color = "#d9534f" if st.session_state.accepted_match and \
            options.loc[options["목적지"] == dest, "매칭ID"].isin([st.session_state.accepted_match]).any() else "#aab2bd"
        fig.add_trace(go.Scattermapbox(
            lat=[st_lat, d_lat], lon=[st_lon, d_lon], mode="lines+markers+text",
            line=dict(width=2, color=color), marker=dict(size=10, color=color),
            text=["", dest], textposition="top center", showlegend=False,
        ))
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=st_lat, lon=st_lon), zoom=5.2),
        margin=dict(l=0, r=0, t=0, b=0), height=360,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("상차 완료 처리를 하면 AI가 복귀 화물을 자동으로 추천해 드립니다.")
