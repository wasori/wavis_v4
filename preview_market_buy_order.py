from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os
import sys

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)


def get_env_str(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    return value.strip() if isinstance(value, str) else default


def get_env_float(key: str, default: float) -> float:
    raw = get_env_str(key, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def get_signal_state_path() -> Path:
    state_dir = get_env_str("STATE_DIR", "state")
    return PROJECT_ROOT / state_dir / "signal_state.json"


def read_json_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def choose_target_market(signal_state: dict) -> tuple[str | None, dict | None]:
    entry_candidates = signal_state.get("entry_candidates", [])
    markets = signal_state.get("markets", [])

    if not entry_candidates:
        return None, None

    target_market = entry_candidates[0]

    for item in markets:
        if item.get("market") == target_market:
            return target_market, item

    return target_market, None


def build_market_buy_preview(market: str, order_krw: float) -> dict:
    return {
        "market": market,
        "side": "bid",
        "ord_type": "price",
        "price": str(int(order_krw)),
    }


def main() -> None:
    try:
        load_env()

        device_id = get_env_str("DEVICE_ID", "unknown-device")
        app_mode = get_env_str("APP_MODE", "test")
        test_order_krw = get_env_float("TEST_ORDER_KRW", 5000.0)

        signal_state_path = get_signal_state_path()
        signal_state = read_json_file(signal_state_path)

        print_header("WAVIS v4 시장가 매수 요청 미리보기")
        print(f"실행 시각            : {datetime.now().astimezone().isoformat(timespec='seconds')}")
        print(f"프로젝트 경로        : {PROJECT_ROOT}")
        print(f".env 존재 여부       : {ENV_PATH.exists()}")
        print(f"DEVICE_ID            : {device_id}")
        print(f"APP_MODE             : {app_mode}")
        print(f"signal_state 파일     : {signal_state_path}")
        print(f"signal_state 존재 여부: {signal_state_path.exists()}")
        print(f"테스트 주문 금액      : {test_order_krw:,.0f} KRW")

        if signal_state is None:
            print_header("최종 결과")
            print("signal_state.json 파일을 읽지 못했습니다.")
            print("먼저 check_signal.py 를 실행해라.")
            sys.exit(1)

        entry_candidates = signal_state.get("entry_candidates", [])
        print_header("현재 신호 상태")
        print(f"signal 생성 시각      : {signal_state.get('generated_at')}")
        print(f"대상 종목 수          : {len(signal_state.get('target_markets', []))}")
        print(f"진입 후보 수          : {signal_state.get('entry_candidate_count', 0)}")
        print(f"진입 후보 목록        : {', '.join(entry_candidates) if entry_candidates else '없음'}")

        target_market, market_detail = choose_target_market(signal_state)

        if target_market is None:
            print_header("최종 결과")
            print("현재 진입 후보가 없어 주문 미리보기를 만들지 않습니다.")
            sys.exit(1)

        preview_payload = build_market_buy_preview(
            market=target_market,
            order_krw=test_order_krw,
        )

        print_header("선택된 주문 후보")
        print(f"선택 종목            : {target_market}")

        if market_detail is not None:
            print(f"현재가               : {market_detail.get('current_close', 0):,.0f} KRW")
            print(f"추세 상태            : {market_detail.get('trend_status')}")
            print(f"눌림 상태            : {market_detail.get('pullback_status')}")
            print(f"15분봉 시각          : {market_detail.get('time_15m')}")
            print(f"1시간봉 시각         : {market_detail.get('time_60m')}")

        print_header("업비트 주문 요청 미리보기")
        print(json.dumps(preview_payload, ensure_ascii=False, indent=2))

        print_header("최종 결과")
        print("실제 주문 전송 없이 시장가 매수 요청 형태만 미리 확인했습니다.")
        print("다음 단계에서 이 미리보기 구조를 실제 주문 파일에 연결할 수 있습니다.")

    except Exception as exc:
        print("\n[실패] 주문 미리보기 생성 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()