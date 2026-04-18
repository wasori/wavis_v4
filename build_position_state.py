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


def get_log_dir() -> Path:
    log_dir = PROJECT_ROOT / get_env_str("LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_latest_order_detail_path() -> Path:
    return get_state_dir() / "latest_order_detail.json"


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


def build_position_payload(order_detail_state: dict) -> dict:
    response = order_detail_state.get("response", {})

    now_str = datetime.now().astimezone().isoformat(timespec="seconds")

    market = response.get("market")
    side = response.get("side")
    state = response.get("state")
    order_uuid = response.get("uuid")
    identifier = response.get("identifier")
    created_at = response.get("created_at")

    avg_price = to_float(response.get("avg_price"))
    executed_volume = to_float(response.get("executed_volume"))
    remaining_volume = to_float(response.get("remaining_volume"))
    paid_fee = to_float(response.get("paid_fee"))
    locked = to_float(response.get("locked"))
    trades_count = response.get("trades_count")

    has_position = side == "bid" and executed_volume > 0
    position_value_krw = avg_price * executed_volume

    payload = {
        "service": "wavis_v4",
        "type": "position_state",
        "saved_at": now_str,
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "app_mode": get_env_str("APP_MODE", "test"),
        "source_order_detail_saved_at": order_detail_state.get("saved_at"),
        "has_position": has_position,
        "position": {
            "market": market,
            "side": side,
            "order_state": state,
            "order_uuid": order_uuid,
            "identifier": identifier,
            "created_at": created_at,
            "avg_entry_price": avg_price,
            "executed_volume": executed_volume,
            "remaining_volume": remaining_volume,
            "paid_fee": paid_fee,
            "locked": locked,
            "trades_count": trades_count,
            "position_value_krw": position_value_krw,
        },
    }

    return payload


def save_position_state(payload: dict) -> tuple[Path, Path]:
    state_dir = get_state_dir()
    log_dir = get_log_dir()

    position_state_path = state_dir / "position_state.json"
    position_history_path = log_dir / "position_history.log"

    position_state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    position = payload.get("position", {})
    history_line = (
        f"{payload.get('saved_at')} | "
        f"market={position.get('market')} | "
        f"side={position.get('side')} | "
        f"order_state={position.get('order_state')} | "
        f"avg_entry_price={position.get('avg_entry_price')} | "
        f"executed_volume={position.get('executed_volume')} | "
        f"paid_fee={position.get('paid_fee')} | "
        f"has_position={payload.get('has_position')}"
    )

    with position_history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return position_state_path, position_history_path


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    try:
        load_env()

        latest_order_detail_path = get_latest_order_detail_path()
        order_detail_state = read_json_file(latest_order_detail_path)

        print_header("WAVIS v4 포지션 상태 생성")
        print(f"실행 시각              : {datetime.now().astimezone().isoformat(timespec='seconds')}")
        print(f"프로젝트 경로          : {PROJECT_ROOT}")
        print(f".env 존재 여부         : {ENV_PATH.exists()}")
        print(f"DEVICE_ID              : {get_env_str('DEVICE_ID', 'unknown-device')}")
        print(f"APP_MODE               : {get_env_str('APP_MODE', 'test')}")
        print(f"입력 주문 상세 파일     : {latest_order_detail_path}")
        print(f"입력 파일 존재 여부     : {latest_order_detail_path.exists()}")

        if order_detail_state is None:
            print_header("최종 결과")
            print("latest_order_detail.json 파일이 없습니다.")
            print("먼저 실제 주문 후 check_order_detail.py 를 실행해라.")
            sys.exit(1)

        payload = build_position_payload(order_detail_state)

        print_header("포지션 요약")
        position = payload["position"]
        print(f"종목                  : {position.get('market')}")
        print(f"매수/매도 방향         : {position.get('side')}")
        print(f"주문 상태              : {position.get('order_state')}")
        print(f"주문 UUID             : {position.get('order_uuid')}")
        print(f"평균 진입가            : {position.get('avg_entry_price'):,.8f}")
        print(f"체결 수량              : {position.get('executed_volume'):,.8f}")
        print(f"미체결 수량            : {position.get('remaining_volume'):,.8f}")
        print(f"수수료                : {position.get('paid_fee'):,.8f}")
        print(f"포지션 평가 기준 금액   : {position.get('position_value_krw'):,.8f}")
        print(f"현재 포지션 보유 여부   : {payload.get('has_position')}")

        position_state_path, position_history_path = save_position_state(payload)

        print_header("포지션 상태 저장 완료")
        print(f"포지션 상태 파일        : {position_state_path}")
        print(f"포지션 이력 로그 파일   : {position_history_path}")

        print_header("최종 결과")
        print("주문 상세 결과를 기반으로 포지션 상태 저장이 완료되었습니다.")

    except Exception as exc:
        print("\n[실패] 포지션 상태 생성 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()