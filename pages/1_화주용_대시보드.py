from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from utils.data import STAGE_LABELS, STATIONS, generate_shipments

st.set_page_config(page_title="화주용 대시보드 | Korail Relai", page_icon="📦", layout="wide")

if "shipments_df" not in st.session_state:
    st.session_state.shipments_df = generate_shipments(6)

df = st.session_state.shipments_df

st.title("📦 화주용 대시보드")
st.caption("AI가 계산한 최적 복합 운송 견적과, 쿠팡 택배처럼 100% 실시간 이동 상황을 확인하세요.")

with st.sidebar:
    st.header("내 화물 목록")
    selected_id = st.radio(
        "조회할 화물을 선택하세요",
        options=df["화물ID"],
        format_func=lambda x: f"{x} · {df.loc[df['화물ID']==x, '화주'].values[0]}",
    )
    if st.button("🔄 새 화물 배차 (데모 새로고침)"):
        st.session_state.shipments_df = generate_shipments(6)
        st.rerun()

row = df[df["화물ID"] == selected_id].iloc[0]

# ---- 상단 요약 카드 ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("화물 ID", row["화물ID"])
c2.metric("AI 예측 도착(ETA)", row["AI예측ETA"].strftime("%H:%M"), help="목적지 화물역 기준")
remaining = int((row["AI예측ETA"] - datetime.now()).total_seconds() // 60)
c3.metric("남은 예상 시간", f"{max(remaining,0)}분")
c4.metric("지연 위험도", f"{row['지연위험도(%)']}%", delta=None)

st.divider()

left, right = st.columns([1.3, 1])

with left:
    st.subheader("🚦 실시간 이동 현황")
    stage_idx = int(row["현재단계"])
    progress = (stage_idx + 1) / len(STAGE_LABELS)
    st.progress(progress, text=f"현재 단계: {row['단계명']} ({stage_idx+1}/{len(STAGE_LABELS)})")

    step_cols = st.columns(len(STAGE_LABELS))
    for i, (col, label) in enumerate(zip(step_cols, STAGE_LABELS)):
        with col:
            if i < stage_idx:
                col.markdown(f"<div style='text-align:center;color:#0059b3;'>✅<br><span style='font-size:0.68rem'>{label}</span></div>", unsafe_allow_html=True)
            elif i == stage_idx:
                col.markdown(f"<div style='text-align:center;color:#d9534f;font-weight:700;'>🔴<br><span style='font-size:0.68rem'>{label}</span></div>", unsafe_allow_html=True)
            else:
                col.markdown(f"<div style='text-align:center;color:#aab2bd;'>⚪<br><span style='font-size:0.68rem'>{label}</span></div>", unsafe_allow_html=True)

    st.markdown(" ")
    st.markdown(f"**출발지**: {row['출발지']} → **출발 화물역**: {row['출발화물역']} → **도착 화물역**: {row['도착화물역']} → **최종 목적지**: {row['최종목적지']}")

    # 지도
    o_lat, o_lon = STATIONS[row["출발화물역"]]
    d_lat, d_lon = STATIONS[row["도착화물역"]]
    t = min(max((stage_idx - 1) / 5, 0), 1)
    cur_lat = o_lat + (d_lat - o_lat) * t
    cur_lon = o_lon + (d_lon - o_lon) * t

    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(
        lat=[o_lat, d_lat], lon=[o_lon, d_lon],
        mode="lines", line=dict(width=3, color="#aab2bd"), name="경로",
    ))
    fig.add_trace(go.Scattermapbox(
        lat=[o_lat], lon=[o_lon], mode="markers+text",
        marker=dict(size=14, color="#0059b3"), text=[row["출발화물역"]], textposition="top center",
        name="출발 화물역",
    ))
    fig.add_trace(go.Scattermapbox(
        lat=[d_lat], lon=[d_lon], mode="markers+text",
        marker=dict(size=14, color="#00838f"), text=[row["도착화물역"]], textposition="top center",
        name="도착 화물역",
    ))
    fig.add_trace(go.Scattermapbox(
        lat=[cur_lat], lon=[cur_lon], mode="markers+text",
        marker=dict(size=20, color="#d9534f", symbol="circle"), text=["현재 위치"], textposition="bottom center",
        name="현재 위치",
    ))
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=(o_lat+d_lat)/2, lon=(o_lon+d_lon)/2), zoom=5.4),
        margin=dict(l=0, r=0, t=0, b=0), height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("💡 AI 최적 복합 운송 견적")
    baseline_cost = row["AI절감비용(원)"] + 250000
    baseline_time = row["AI절감시간(분)"] + 480
    relai_cost = 250000
    relai_time = 480

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name="기존 육상 트럭 전용", x=["비용(원)"], y=[baseline_cost], marker_color="#aab2bd"))
    fig2.add_trace(go.Bar(name="Korail Relai 복합운송", x=["비용(원)"], y=[relai_cost], marker_color="#0059b3"))
    fig2.update_layout(barmode="group", height=260, margin=dict(l=0, r=0, t=20, b=0),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig2, use_container_width=True)

    m1, m2 = st.columns(2)
    m1.metric("💰 절감 비용", f"{row['AI절감비용(원)']:,}원", delta=f"-{row['AI절감비용(원)']:,}원")
    m2.metric("⏱️ 절감 시간", f"{row['AI절감시간(분)']}분", delta=f"-{row['AI절감시간(분)']}분")

    st.markdown("##### 지연 위험 변수 (AI 예측 근거)")
    st.markdown(
        f"""
- 선로 혼잡도: {"높음" if row['지연위험도(%)']>25 else "보통"}
- 기상 영향: {"주의" if row['지연위험도(%)']>30 else "양호"}
- CY 하역 대기: 평균 {int(row['지연위험도(%)']*1.3)}분
        """
    )

st.divider()
st.subheader("📋 전체 화물 목록")
st.dataframe(
    df[["화물ID", "화주", "화물종류", "출발화물역", "도착화물역", "단계명", "AI예측ETA", "지연위험도(%)"]]
    .rename(columns={"AI예측ETA": "AI 예측 도착"}),
    use_container_width=True,
    hide_index=True,
)
