# 🚆 Korail Relai (릴레이)

복합 수송 병목을 깨는 AI 기반 Door-to-Door 화물 조율 & 공차 셰어링 앱

코레일 사내 물류 아이디어 해커톤 프로토타입 (Streamlit)

## 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 화면 구성

- `app.py` — 소개 / 문제 정의 / 솔루션 개요
- `pages/1_화주용_대시보드.py` — AI 견적, 실시간 Door-to-Door 추적
- `pages/2_트럭기사용_앱.py` — 열차 도착 배차 안내, 공차 방지 복귀 화물 매칭
- `pages/3_관제센터.py` — 전국 네트워크 실시간 현황, KPI Before/After

※ 모든 위치·시간·수치 데이터는 데모를 위한 가상의 목업(mock) 데이터입니다.
