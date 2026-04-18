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


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_env_str(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    return value.strip() if isinstance(value, str) else default


def get_state_dir() -> Path:
    state_dir = PROJECT_ROOT / get_env_str("STATE_DIR", "state")
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_log_dir() -> Path:
    log_dir = PROJECT_ROOT / get_env_str("LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_position_state_path() -> Path:
    return get_state_dir() / "position_state.json"


def get_last_closed_position_path() -> Path:
    return get_state_dir() / "last_closed_position.json"


def get_latest_sell_order_response_path() -> Path:
    return get_state_dir() / "latest_sell_order_response.json"


def read_json_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json_file(file_path: Path, payload: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_cleared_position_state(
    previous_position_state: dict,
    latest_sell_order_state: dict | None,
) -> tuple[dict, dict]:
    now_str = get_now_iso()
    device_id = get_env_str("DEVICE_ID", "unknown-device")
    app_mode = get_env_str("APP_MODE", "test")

    previous_position = previous_position_state.get("position", {}) or {}
    sell_response = (latest_sell_order_state or {}).get("response", {}) or {}

    close_context = {
        "cleared_at": now_str,
        "cleared_by_device_id": device_id,
        "cleared_in_app_mode": app_mode,
        "source_sell_order_uuid": sell_response.get("uuid"),
        "source_sell_order_identifier": sell_response.get("identifier"),
        "source_sell_order_market": sell_response.get("market"),
        "source_sell_order_state": sell_response.get("state"),
        "source_sell_saved_at": (latest_sell_order_state or {}).get("saved_at"),
    }

    cleared_position_state = {
        "service": "wavis_v4",
        "type": "position_state",
        "saved_at": now_str,
        "device_id": device_id,
        "app_mode": app_mode,
        "has_position": False,
        "position": None,
        "last_close_context": close_context,
    }

    closed_position_backup = {
        "service": "wavis_v4",
        "type": "last_closed_position",
        "saved_at": now_str,
        "device_id": device_id,
        "app_mode": app_mode,
        "closed_position": previous_position,
        "close_context": close_context,
    }

    return cleared_position_state, closed_position_backup


def append_position_history_log(
    previous_position_state: dict,
    latest_sell_order_state: dict | None,
) -> Path:
    log_dir = get_log_dir()
    history_path = log_dir / "position_history.log"

    now_str = get_now_iso()
    previous_position = previous_position_state.get("position", {}) or {}
    sell_response = (latest_sell_order_state or {}).get("response", {}) or {}

    market = previous_position.get("market")
    avg_entry_price = to_float(previous_position.get("avg_entry_price"))
    executed_volume = to_float(previous_position.get("executed_volume"))
    paid_fee = to_float(previous_position.get("paid_fee"))

    sell_uuid = sell_response.get("uuid", "-")
    sell_state = sell_response.get("state", "-")

    history_line = (
        f"{now_str} | "
        f"action=clear_position_state | "
        f"market={market} | "
        f"avg_entry_price={avg_entry_price} | "
        f"executed_volume={executed_volume} | "
        f"paid_fee={paid_fee} | "
        f"sell_uuid={sell_uuid} | "
        f"sell_state={sell_state}"
    )

    with history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return history_path


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    try:
        load_env()

        position_state_path = get_position_state_path()
        last_closed_position_path = get_last_closed_position_path()
        latest_sell_order_response_path = get_latest_sell_order_response_path()

        position_state = read_json_file(position_state_path)
        latest_sell_order_state = read_json_file(latest_sell_order_response_path)

        print_header("WAVIS v4 포지션 상태 비우기")
        print(f"실행 시각                : {get_now_iso()}")
        print(f"프로젝트 경로            : {PROJECT_ROOT}")
        print(f".env 존재 여부           : {ENV_PATH.exists()}")
        print(f"DEVICE_ID                : {get_env_str('DEVICE_ID', 'unknown-device')}")
        print(f"APP_MODE                 : {get_env_str('APP_MODE', 'test')}")
        print(f"포지션 상태 파일          : {position_state_path}")
        print(f"포지션 상태 파일 존재     : {position_state_path.exists()}")
        print(f"최근 매도 응답 파일       : {latest_sell_order_response_path}")
        print(f"최근 매도 응답 파일 존재  : {latest_sell_order_response_path.exists()}")

        if position_state is None:
            print_header("최종 결과")
            print("position_state.json 파일이 없습니다.")
            print("비울 포지션 상태가 없습니다.")
            sys.exit(1)

        has_position = bool(position_state.get("has_position", False))
        previous_position = position_state.get("position")

        if not has_position or not previous_position:
            print_header("최종 결과")
            print("현재 활성 포지션이 없습니다.")
            print("이미 비워진 상태로 보입니다.")
            sys.exit(1)

        print_header("현재 포지션 요약")
        print(f"종목                    : {previous_position.get('market')}")
        print(f"매수/매도 방향           : {previous_position.get('side')}")
        print(f"주문 상태                : {previous_position.get('order_state')}")
        print(f"평균 진입가              : {to_float(previous_position.get('avg_entry_price')):,.8f}")
        print(f"체결 수량                : {to_float(previous_position.get('executed_volume')):,.8f}")
        print(f"누적 수수료              : {to_float(previous_position.get('paid_fee')):,.8f}")

        cleared_position_state, closed_position_backup = build_cleared_position_state(
            previous_position_state=position_state,
            latest_sell_order_state=latest_sell_order_state,
        )

        write_json_file(position_state_path, cleared_position_state)
        write_json_file(last_closed_position_path, closed_position_backup)
        history_path = append_position_history_log(
            previous_position_state=position_state,
            latest_sell_order_state=latest_sell_order_state,
        )

        print_header("저장 완료")
        print(f"비워진 포지션 상태 파일    : {position_state_path}")
        print(f"마지막 청산 백업 파일      : {last_closed_position_path}")
        print(f"포지션 이력 로그 파일      : {history_path}")

        print_header("최종 결과")
        print("포지션 상태를 비웠습니다.")
        print("다음 진입을 받을 수 있는 대기 상태로 전환되었습니다.")

    except Exception as exc:
        print("\n[실패] 포지션 상태 비우기 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()