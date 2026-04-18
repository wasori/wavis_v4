# WAVIS v4 2차 정리 계획

## 1. 목적
이 문서는 WAVIS v4 프로젝트의 2차 정리 방향을 확정하기 위한 문서다.

현재 프로젝트는 안전한 검증을 위해 파일을 잘게 나눠서 개발했다.
이제부터는 실제 운영을 고려해서 파일 역할을 정리해야 한다.

중요 원칙:
- 지금 당장 무리하게 다 옮기지 않는다
- 먼저 분류 기준을 확정한다
- 실제 이동은 단계별로 천천히 한다
- 실행 중인 핵심 파일은 마지막에 건드린다

---

## 2. 현재 정리 기준

### A. 핵심 운영 파일
최종 운영 구조에 남길 가능성이 높은 파일

- `main.py`
- `run_trade_cycle.py`
- `run_trade_loop.py`

설명:
- 서버 실행
- 1회 트레이드 판단
- 반복 루프 실행

이 파일들은 당분간 루트에 유지한다.

---

### B. 상태 생성 / 상태 관리 파일
현재는 독립 파일이지만, 나중에 engine 내부로 흡수될 가능성이 큰 파일

- `check_signal.py`
- `build_position_state.py`
- `clear_position_state.py`

설명:
- 신호 상태 생성
- 포지션 상태 생성
- 포지션 상태 초기화

정리 방향:
- 나중에 `engine/state_manager.py` 또는 `engine/signal_engine.py` 로 흡수 후보

---

### C. 장치 잠금 / 실거래 권한 관리 파일
운영 보조 도구로 남을 가능성이 높은 파일

- `init_engine_lock.py`
- `activate_live_device.py`
- `release_live_device.py`
- `check_live_order_guard.py`
- `check_live_readiness.py`

설명:
- active device 지정
- live 전환 준비 점검
- 실거래 차단/허용 검사

정리 방향:
- `scripts/` 폴더 이동 후보

---

### D. 공개 API / 검증용 파일
검증용 도구 성격이 강한 파일

- `check_upbit_public.py`
- `check_upbit_private.py`
- `check_order_chance.py`
- `check_order_preflight.py`

설명:
- 공개 API 확인
- 개인 API 확인
- 주문 가능 정보 확인
- 주문 직전 검사

정리 방향:
- `scripts/verify/` 폴더 이동 후보

---

### E. 주문 미리보기 / 테스트용 파일
실전 직전 검증용 파일

- `preview_market_buy_order.py`
- `test_market_buy_order.py`
- `preview_market_sell_order.py`

설명:
- 요청 형태 미리보기
- 테스트 주문 검증
- 매도 요청 미리보기

정리 방향:
- `scripts/preview/` 또는 `scripts/verify/` 이동 후보

---

### F. 실제 주문 파일
실제 live 연결 핵심 파일

- `place_market_buy_order.py`
- `place_market_sell_order.py`
- `check_order_detail.py`

설명:
- 실제 매수
- 실제 매도
- 주문 상세 조회

정리 방향:
- 당장은 루트 유지
- 나중에 `engine/order_manager.py` 또는 `orders/` 폴더로 이동 후보

---

### G. 포지션/청산 판단 파일
포지션 유지 및 청산 관련 판단 파일

- `check_position_recovery.py`
- `check_exit_plan.py`
- `check_exit_trigger.py`

설명:
- 포지션 복구
- 익절/손절 계획 계산
- 현재가 기준 청산 후보 판정

정리 방향:
- 나중에 `engine/exit_manager.py` 로 흡수 후보

---

### H. 문서 파일
설명용 / 운영용 문서 파일

- `PROJECT_MAP.md`
- `LIVE_SWITCH_CHECKLIST.md`
- `REORG_PLAN.md`

설명:
- 현재 구조 설명
- 집 PC live 전환 절차
- 2차 정리 방향

정리 방향:
- 나중에 `docs/` 폴더 이동 후보

---

## 3. 이번 2차 정리에서 바로 하지 않을 것

이번 단계에서는 아래 작업은 하지 않는다.

- 핵심 실행 파일 대규모 이동
- import 경로 대량 수정
- engine 폴더 한 번에 완성
- scripts/verify/preview를 한 번에 모두 생성
- 실거래 파일 구조 강제 합치기

이유:
- 지금은 동작 중인 구조를 깨지 않는 것이 더 중요하다

---

## 4. 2차 정리 실제 순서

### 1단계
문서 정리
- `REORG_PLAN.md` 작성
- 정리 기준 확정

### 2단계
문서 폴더 정리
- `docs/` 폴더 생성
- `.md` 문서 파일 이동

### 3단계
운영 보조 도구 분리
- `scripts/` 폴더 생성
- engine lock / readiness 관련 파일 이동

### 4단계
검증 도구 분리
- `scripts/verify/` 또는 `scripts/tools/` 구조 생성
- check_* 계열 검증 파일 이동

### 5단계
미리보기 도구 분리
- `scripts/preview/` 폴더 생성
- preview_* 파일 이동

### 6단계
핵심 엔진 흡수
- signal / position / exit 관련 로직을 `engine/` 으로 흡수
- 마지막에 루트 파일 정리

---

## 5. 권장 최종 구조 초안

```text
wavis_v4/
├─ main.py
├─ run_trade_cycle.py
├─ run_trade_loop.py
├─ requirements.txt
├─ .env
├─ .env.example
├─ .gitignore
├─ docs/
│  ├─ PROJECT_MAP.md
│  ├─ LIVE_SWITCH_CHECKLIST.md
│  └─ REORG_PLAN.md
├─ scripts/
│  ├─ activate_live_device.py
│  ├─ release_live_device.py
│  ├─ init_engine_lock.py
│  ├─ check_live_order_guard.py
│  ├─ check_live_readiness.py
│  ├─ verify/
│  │  ├─ check_upbit_public.py
│  │  ├─ check_upbit_private.py
│  │  ├─ check_order_chance.py
│  │  ├─ check_order_preflight.py
│  │  ├─ check_order_detail.py
│  │  ├─ check_position_recovery.py
│  │  ├─ check_exit_plan.py
│  │  └─ check_exit_trigger.py
│  └─ preview/
│     ├─ preview_market_buy_order.py
│     └─ preview_market_sell_order.py
├─ engine/
│  ├─ signal_engine.py
│  ├─ state_manager.py
│  ├─ order_manager.py
│  └─ exit_manager.py
├─ state/
└─ logs/