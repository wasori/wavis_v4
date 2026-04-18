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


def get_state_dir() -> Path:
    state_dir = PROJECT_ROOT / get_env_str("STATE_DIR", "state")
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_position_state_path() -> Path:
    return get_state_dir() / "position_state.json"


def read_json_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    try:
        load_env()

        position_state_path = get_position_state_path()
        position_state = read_json_file(position_state_path)

        print_header("WAVIS v4 포지션 복구 점검")
        print(f"실행 시각              : {datetime.now().astimezone().isoformat(timespec='seconds')}")
        print(f"프로젝트 경로          : {PROJECT_ROOT}")
        print(f".env 존재 여부         : {ENV_PATH.exists()}")
        print(f"DEVICE_ID              : {get_env_str('DEVICE_ID', 'unknown-device')}")
        print(f"APP_MODE               : {get_env_str('APP_MODE', 'test')}")
        print(f"포지션 상태 파일        : {position_state_path}")
        print(f"포지션 상태 파일 존재   : {position_state_path.exists()}")

        if position_state is None:
            print_header("최종 결과")
            print("position_state.json 파일이 없습니다.")
            print("아직 복구할 포지션 상태가 없습니다.")
            sys.exit(1)

        has_position = bool(position_state.get("has_position", False))
        position = position_state.get("position", {})

        market = position.get("market")
        side = position.get("side")
        order_state = position.get("order_state")
        order_uuid = position.get("order_uuid")
        avg_entry_price = to_float(position.get("avg_entry_price"))
        executed_volume = to_float(position.get("executed_volume"))
        remaining_volume = to_float(position.get("remaining_volume"))
        paid_fee = to_float(position.get("paid_fee"))
        position_value_krw = to_float(position.get("position_value_krw"))

        print_header("포지션 상태 요약")
        print(f"포지션 보유 여부        : {has_position}")
        print(f"종목                  : {market}")
        print(f"매수/매도 방향         : {side}")
        print(f"주문 상태              : {order_state}")
        print(f"주문 UUID             : {order_uuid}")
        print(f"평균 진입가            : {avg_entry_price:,.8f}")
        print(f"체결 수량              : {executed_volume:,.8f}")
        print(f"미체결 수량            : {remaining_volume:,.8f}")
        print(f"수수료                : {paid_fee:,.8f}")
        print(f"포지션 평가 기준 금액   : {position_value_krw:,.8f}")

        print_header("복구 판단")
        if has_position and side == "bid" and executed_volume > 0:
            print("현재 포지션 복구 가능")
            print("프로그램 재시작 시 이 값을 기준으로 포지션 관리 로직을 이어갈 수 있습니다.")
        else:
            print("현재 복구할 활성 포지션이 없습니다.")
            print("다음 진입 전 대기 상태로 보면 됩니다.")

        print_header("최종 결과")
        print("포지션 복구 점검이 완료되었습니다.")

    except Exception as exc:
        print("\n[실패] 포지션 복구 점검 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()