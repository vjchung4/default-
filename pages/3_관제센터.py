import plotly.graph_objects as go
import streamlit as st

from utils.data import STATIONS, generate_network_snapshot, kpi_before_after

st.set_page_config(page_title="관제센터 | Korail Relai", page_icon="🛰️", layout="wide")

st.title("🛰️ Korail Relai 관제센터")
st.caption("전국 화물역 네트워크의 트럭·화차 실시간 현황과, 도입 전/후 핵심 KPI를 한눈에 확인합니다.")

if "network_snapshot" not in st.session_state:
    st.session_state.network_snapshot = generate_network_snapshot()

trucks_df, trains_df = st.session_state.network_snapshot

top1, top2, top3, top4 = st.columns(4)
empty_ratio = round((trucks_df["type"] == "공차").mean() * 100, 1)
top1.metric("현재 운행 트럭", f"{len(trucks_df)}대")
top2.metric("공차 비율", f"{empty_ratio}%", delta=f"-{round(34.2-empty_ratio,1)}%p vs 기존", delta_color="inverse")
top3.metric("운행중 화차", f"{len(trains_df)}편성")
top4.metric("AI 매칭 성사 건수 (오늘)", "182건", delta="+37건")

if st.button("🤖 AI 매칭 재실행 (실시간 스냅샷 새로고침)"):
    st.session_state.network_snapshot = generate_network_snapshot()
    st.rerun()

st.divider()

left, right = st.columns([1.4, 1])

with left:
    st.subheader("전국 네트워크 실시간 현황")
    fig = go.Figure()

    # 화물역
    st_lats = [v[0] for v in STATIONS.values()]
    st_lons = [v[1] for v in STATIONS.values()]
    fig.add_trace(go.Scattermapbox(
        lat=st_lats, lon=st_lons, mode="markers+text",
        marker=dict(size=13, color="#00376b", symbol="circle"),
        text=list(STATIONS.keys()), textposition="top center", name="화물역",
    ))

    # 화차
    fig.add_trace(go.Scattermapbox(
        lat=trains_df["lat"], lon=trains_df["lon"], mode="markers",
        marker=dict(size=11, color="#ffb300", symbol="circle"),
        text=trains_df["id"] + " (" + trains_df["출발역"] + "→" + trains_df["도착역"] + ")",
        name="운행중 화차",
    ))

    # 트럭 (적재 / 공차)
    loaded = trucks_df[trucks_df["type"] == "적재"]
    empty = trucks_df[trucks_df["type"] == "공차"]
    fig.add_trace(go.Scattermapbox(
        lat=loaded["lat"], lon=loaded["lon"], mode="markers",
        marker=dict(size=9, color="#0059b3"), text=loaded["id"], name="적재 트럭",
    ))
    fig.add_trace(go.Scattermapbox(
        lat=empty["lat"], lon=empty["lon"], mode="markers",
        marker=dict(size=9, color="#d9534f"), text=empty["id"], name="공차 (매칭 대상)",
    ))

    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=36.4, lon=127.8), zoom=5.4),
        margin=dict(l=0, r=0, t=0, b=0), height=520,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("도입 전/후 핵심 지표")
    kpis = kpi_before_after()
    for name, vals in kpis.items():
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=["기존"], y=[vals["기존"]], marker_color="#aab2bd", name="기존", showlegend=False))
        fig2.add_trace(go.Bar(x=["Relai 적용"], y=[vals["Relai적용"]], marker_color="#0059b3", name="Relai", showlegend=False))
        improve = round((1 - vals["Relai적용"] / vals["기존"]) * 100, 1)
        fig2.update_layout(
            title=dict(text=f"{name}  (▼{improve}%)", font=dict(size=13)),
            height=180, margin=dict(l=10, r=10, t=35, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.subheader("🚛 매칭 대기 중인 공차 목록")
st.dataframe(
    empty.rename(columns={"id": "트럭ID", "인근화물역": "인근 화물역", "type": "상태"}),
    use_container_width=True,
    hide_index=True,
)
