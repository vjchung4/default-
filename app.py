import streamlit as st

st.set_page_config(
    page_title="Korail Relai | AI 복합운송 조율 플랫폼",
    page_icon="🚆",
    layout="wide",
)

st.markdown(
    """
    <style>
    .relai-hero {
        padding: 1.6rem 2rem;
        border-radius: 16px;
        background: linear-gradient(120deg, #003876 0%, #0059b3 60%, #00b0d6 100%);
        color: white;
        margin-bottom: 1.2rem;
    }
    .relai-hero h1 { margin-bottom: 0.2rem; }
    .relai-hero p { font-size: 1.05rem; opacity: 0.92; }
    .metric-card {
        background: #f7f9fc;
        border: 1px solid #e3e8ef;
        border-radius: 12px;
        padding: 1rem 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="relai-hero">
        <h1>🚆 Korail Relai (릴레이)</h1>
        <p>복합 수송 병목을 깨는 AI 기반 Door-to-Door 화물 조율 &amp; 공차 셰어링 플랫폼</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption("코레일 사내 물류 아이디어 해커톤 · 아이디어 B [영업/화주 혁신] · 프로토타입 데모")

col1, col2 = st.columns([1.15, 1])

with col1:
    st.subheader("1. 문제 정의")
    st.markdown(
        """
- **현장의 병목**: 철도 물류는 `화주 공장 → 육상 트럭 → 화물역(CY) → 철도 → 목적지 역 → 트럭 → 최종 목적지`의
  **5단계 환적** 과정을 거칩니다.
- **비효율**: 철도 도착 시간과 육상 트럭 기사의 대기 시간이 어긋나 CY(컨테이너 야드)에 화물이 병목처럼 쌓이고,
  돌아가는 트럭/화차는 **빈 상태(공차)** 로 운행되어 화주가 육상 전용 트럭으로 이탈합니다.
        """
    )

    st.subheader("2. AI 적용 방안")
    st.markdown(
        """
- **도착 ETA 지능형 예측**: 철도 지연 변수를 계산하여 목적지 화물역 도착 시간을 **분 단위**로 정밀 예측
- **화물차 ↔ 철도 이종(異種) 매칭 & 공차 예측**: 철도 도착 시점에 맞춰 인근 육상 화물차를 자동 배차하고,
  돌아갈 때 빈 화차/빈 트럭을 다른 화주의 물동량과 **실시간 묶음 매칭(Grouping)**
        """
    )

with col2:
    st.subheader("3. 산출물 - 앱 UI/UX")
    st.info("**[화주용]**\n\nAI가 계산한 '최적 복합 운송 견적 및 소요시간' 확인 + 쿠팡 택배처럼\n철도+트럭 이동 상황 100% 실시간 추적")
    st.success("**[트럭 기사용]**\n\n\"의왕역 15시 10분 도착 화물열차 3번 컨테이너 상차 대기 중.\n상차 후 대전 공장 이동 시 복귀 화물(공차 방지) 자동 연계 추천.\"")
    st.warning("**[관제센터]**\n\n전 노선 화차·트럭 실시간 위치, 공차율/대기시간 등 핵심 KPI를\nBefore/After로 비교하는 운영 대시보드")

st.divider()
st.subheader("데모 둘러보기")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("#### 📦 화주용 대시보드")
    st.caption("실시간 화물 추적, AI 견적·ETA 확인")
    st.page_link("pages/1_화주용_대시보드.py", label="화주용 대시보드 열기 →", icon="📦")
with c2:
    st.markdown("#### 🚚 트럭 기사용 앱")
    st.caption("배차 안내, 공차 방지 복귀화물 추천")
    st.page_link("pages/2_트럭기사용_앱.py", label="트럭 기사용 앱 열기 →", icon="🚚")
with c3:
    st.markdown("#### 🛰️ 관제센터")
    st.caption("전국 네트워크 현황, KPI Before/After")
    st.page_link("pages/3_관제센터.py", label="관제센터 열기 →", icon="🛰️")

st.divider()
st.caption("※ 본 프로토타입의 위치·시간·수치 데이터는 데모를 위한 가상의 목업(mock) 데이터입니다.")
