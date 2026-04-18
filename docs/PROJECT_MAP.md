# WAVIS v4 프로젝트 맵

## 1. 현재 프로젝트 목적
이 프로젝트는 업비트 자동매매 시스템의 v4 버전이다.

목표:
- 노트북과 집 PC에서 같은 코드를 이어서 개발
- 노트북은 test 모드 중심
- 집 PC는 최종 live 모드 실행 장치
- active device / engine lock 구조로 중복 실거래 방지
- 실전 전환 전 모든 단계를 작은 파일로 검증

---

## 2. 핵심 상시 실행 파일
이 파일들은 최종 운영 구조에 남을 가능성이 높다.

### main.py
- FastAPI 서버 실행 파일
- `/health`, `/status` 제공
- 상태 파일을 읽어서 현재 엔진 상태를 보여줌

### run_trade_cycle.py
- 트레이드 판단 1회 실행
- 신호 계산
- 포지션 상태 확인
- 다음 액션 계산

### run_trade_loop.py
- 트레이드 사이클 반복 실행
- test 모드 자동 순환 엔진 역할

---

## 3. 상태 파일 생성 / 관리 파일
이 파일들은 state 구조를 만드는 데 중요하다.

### check_signal.py
- 공개 API로 종목 신호 계산
- signal_state.json 생성

### build_position_state.py
- 주문 상세 결과를 포지션 상태로 변환
- position_state.json 생성

### clear_position_state.py
- 청산 후 position_state.json 비우기
- last_closed_position.json 백업 생성

---

## 4. 장치 잠금 / 실거래 권한 관리 파일
이 파일들은 중복 자동매매 방지에 필요하다.

### init_engine_lock.py
- engine_lock.json 초기화

### activate_live_device.py
- 현재 장치를 활성 실거래 장치로 지정
- 집 PC live 모드에서 사용 예정

### release_live_device.py
- 활성 실거래 장치 해제

### check_live_order_guard.py
- 현재 장치가 실거래 가능한 상태인지 검사

### check_live_readiness.py
- 실거래 시작 직전 준비 상태 종합 점검

---

## 5. 공개 API / 인증 / 주문 검증 파일
이 파일들은 실전 전환 전에 단계별 검증용으로 사용한다.

### check_upbit_public.py
- 공개 API 연결 확인
- 현재가 / 캔들 조회

### check_upbit_private.py
- 개인 API 잔고 조회
- 현재는 live guard 통과 시에만 허용

### check_order_chance.py
- 주문 가능 정보 조회

### check_order_preflight.py
- 최소 주문금액 / 잔고 / 주문 가능 여부 점검

### preview_market_buy_order.py
- 시장가 매수 요청 형태 미리보기

### test_market_buy_order.py
- 업비트 테스트 주문 API 기반 매수 검증

### place_market_buy_order.py
- 실제 시장가 매수 주문

### check_order_detail.py
- 주문 UUID 기준 상세 조회

### preview_market_sell_order.py
- 시장가 매도 요청 형태 미리보기

### place_market_sell_order.py
- 실제 시장가 매도 주문

---

## 6. 포지션 관리 / 청산 판단 파일
이 파일들은 포지션 보유 시 판단에 필요하다.

### check_position_recovery.py
- 재시작 시 포지션 복구 가능 여부 점검

### check_exit_plan.py
- 현재 포지션 기준 익절가 / 손절가 계산

### check_exit_trigger.py
- 현재가 기준 익절/손절 도달 여부 점검

---

## 7. 상태 파일 목록
현재 프로젝트에서 중요한 state 파일들

### signal_state.json
- 최신 진입 신호 상태

### trade_cycle_state.json
- 1회 사이클 판단 결과

### trade_loop_status.json
- 루프 실행 상태

### engine_lock.json
- 실거래 활성 장치 정보
- 중복 실행 방지 핵심

### position_state.json
- 현재 포지션 상태
- 실제 체결 후 생성

### last_closed_position.json
- 마지막 청산 포지션 백업

### latest_order_response.json
- 최근 매수 주문 응답

### latest_order_detail.json
- 최근 주문 상세 응답

### latest_sell_order_response.json
- 최근 매도 주문 응답

### live_readiness.json
- 실거래 전환 준비 점검 결과

---

## 8. 로그 파일 목록
### signal_history.log
- 신호 요약 누적

### trade_cycle_history.log
- 트레이드 사이클 판단 이력

### trade_loop_history.log
- 루프 반복 이력

### position_history.log
- 포지션 상태 변경 이력

### order_history.log
- 매수 주문 이력

### order_detail_history.log
- 주문 상세 조회 이력

### sell_order_history.log
- 매도 주문 이력

### live_readiness_history.log
- 실거래 준비 점검 이력

---

## 9. 현재 운영 해석
### 노트북
- APP_MODE=test
- 실거래 차단 상태
- 공개 API 개발 가능
- 엔진 판단 / 루프 / 상태 파일 개발 가능

### 집 PC
- 최종적으로 APP_MODE=live 예정
- 업비트 키 설정
- active_live_device 지정
- 실제 주문 가능 장치

---

## 10. 다음 정리 방향
나중에 2차 정리에서 아래처럼 묶을 수 있다.

### 유지 후보
- main.py
- run_trade_cycle.py
- run_trade_loop.py

### scripts 폴더로 이동 후보
- init_engine_lock.py
- activate_live_device.py
- release_live_device.py
- check_live_readiness.py

### verify 또는 tools 폴더로 이동 후보
- check_upbit_public.py
- check_upbit_private.py
- check_order_chance.py
- check_order_preflight.py
- preview_market_buy_order.py
- preview_market_sell_order.py
- check_order_detail.py
- check_position_recovery.py
- check_exit_plan.py
- check_exit_trigger.py

### order 또는 engine 내부로 흡수 후보
- place_market_buy_order.py
- place_market_sell_order.py
- build_position_state.py
- clear_position_state.py

---

## 11. 현재 결론
지금 파일 수가 많아 보이는 것은 정상이다.

이 파일들은:
- 대부분 의미 있는 검증 도구이고
- 지금은 안전하게 개발하기 위해 분리되어 있으며
- 나중에 정리 단계에서 합치거나 이동할 수 있다.

즉,
현재 구조는 "최종 폴더 구조"가 아니라
"안전하게 실전 시스템을 검증하면서 만드는 중간 구조"로 보면 된다.