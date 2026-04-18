from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os
import socket
import sys

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_env_str(key: str, default: str) -> str:
    value = os.getenv(key, default)
    return value.strip() if isinstance(value, str) else default


def get_engine_lock_path() -> Path:
    lock_file_value = get_env_str("ENGINE_LOCK_FILE", "state/engine_lock.json")
    return PROJECT_ROOT / lock_file_value


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


def evaluate_live_order_guard() -> dict:
    device_id = get_env_str("DEVICE_ID", "unknown-device")
    app_mode = get_env_str("APP_MODE", "test").lower()
    machine_name = socket.gethostname()

    engine_lock_path = get_engine_lock_path()
    engine_lock = read_json_file(engine_lock_path)

    result = {
        "checked_at": get_now_iso(),
        "device_id": device_id,
        "app_mode": app_mode,
        "machine_name": machine_name,
        "engine_lock_path": str(engine_lock_path),
        "engine_lock_exists": engine_lock_path.exists(),
        "allow_live_order": False,
        "reason": "",
        "engine_lock": engine_lock,
    }

    if app_mode != "live":
        result["reason"] = "APP_MODE가 live가 아니므로 실거래 주문이 차단됩니다."
        return result

    if engine_lock is None:
        result["reason"] = "engine_lock.json 파일이 없어 실거래 주문이 차단됩니다."
        return result

    if not bool(engine_lock.get("lock_enabled", True)):
        result["reason"] = "engine lock이 비활성화되어 있어 현재는 실거래 주문을 허용하지 않습니다."
        return result

    active_live_device = engine_lock.get("active_live_device")
    if active_live_device is None:
        result["reason"] = "활성 실거래 장치가 지정되지 않아 실거래 주문이 차단됩니다."
        return result

    if active_live_device != device_id:
        result["reason"] = (
            f"현재 장치({device_id})가 활성 실거래 장치({active_live_device})가 아니므로 "
            "실거래 주문이 차단됩니다."
        )
        return result

    result["allow_live_order"] = True
    result["reason"] = "현재 장치는 live 모드이며 활성 실거래 장치로 등록되어 있습니다."
    return result


def main() -> None:
    try:
        load_env()
        result = evaluate_live_order_guard()

        print_header("WAVIS v4 실거래 주문 가드 검사")
        print(f"검사 시각                  : {result['checked_at']}")
        print(f"현재 장치 ID               : {result['device_id']}")
        print(f"현재 APP_MODE              : {result['app_mode']}")
        print(f"현재 머신 이름             : {result['machine_name']}")
        print(f"엔진 잠금 파일             : {result['engine_lock_path']}")
        print(f"엔진 잠금 파일 존재 여부   : {result['engine_lock_exists']}")
        print(f"실거래 주문 허용 여부      : {result['allow_live_order']}")
        print(f"판정                       : {result['reason']}")

        engine_lock = result["engine_lock"]
        if engine_lock is not None:
            print_header("engine_lock 핵심 정보")
            print(f"lock_enabled               : {engine_lock.get('lock_enabled')}")
            print(f"active_live_device         : {engine_lock.get('active_live_device')}")
            print(f"active_live_mode           : {engine_lock.get('active_live_mode')}")
            print(f"active_since               : {engine_lock.get('active_since')}")
            print(f"last_updated_at            : {engine_lock.get('last_updated_at')}")
            print(f"last_updated_by            : {engine_lock.get('last_updated_by')}")
            print(f"last_action                : {engine_lock.get('last_action')}")

    except Exception as exc:
        print("\n[실패] 실거래 주문 가드 검사 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()