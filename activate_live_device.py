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


def save_json_file(file_path: Path, payload: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    try:
        load_env()

        now_str = get_now_iso()
        device_id = get_env_str("DEVICE_ID", "unknown-device")
        app_mode = get_env_str("APP_MODE", "test").lower()
        machine_name = socket.gethostname()

        engine_lock_path = get_engine_lock_path()
        engine_lock = read_json_file(engine_lock_path) or {
            "service": "wavis_v4",
            "type": "engine_lock",
            "lock_enabled": True,
            "active_live_device": None,
            "active_live_mode": None,
            "active_since": None,
        }

        print_header("WAVIS v4 활성 실거래 장치 지정")

        print(f"현재 장치 ID               : {device_id}")
        print(f"현재 APP_MODE              : {app_mode}")
        print(f"현재 머신 이름             : {machine_name}")
        print(f"엔진 잠금 파일             : {engine_lock_path}")

        if app_mode != "live":
            engine_lock["last_updated_at"] = now_str
            engine_lock["last_updated_by"] = device_id
            engine_lock["last_action"] = "activate_live_device_denied"
            engine_lock["current_snapshot"] = {
                "device_id": device_id,
                "app_mode": app_mode,
                "machine_name": machine_name,
                "env_file_exists": ENV_PATH.exists(),
            }
            engine_lock["live_order_allowed_for_current_device"] = False
            engine_lock["message"] = (
                "현재 장치는 live 모드가 아닙니다. "
                "APP_MODE=live 인 장치에서만 활성 실거래 장치 지정이 가능합니다."
            )

            save_json_file(engine_lock_path, engine_lock)

            print("\n실행 결과")
            print("현재 장치는 live 모드가 아니므로 활성 실거래 장치로 지정되지 않았습니다.")
            print("집 PC에서 APP_MODE=live 로 설정한 뒤 다시 실행해라.")
            return

        engine_lock["service"] = "wavis_v4"
        engine_lock["type"] = "engine_lock"
        engine_lock["lock_enabled"] = True
        engine_lock["active_live_device"] = device_id
        engine_lock["active_live_mode"] = "live"
        engine_lock["active_since"] = now_str
        engine_lock["last_updated_at"] = now_str
        engine_lock["last_updated_by"] = device_id
        engine_lock["last_action"] = "activate_live_device"
        engine_lock["current_snapshot"] = {
            "device_id": device_id,
            "app_mode": app_mode,
            "machine_name": machine_name,
            "env_file_exists": ENV_PATH.exists(),
        }
        engine_lock["live_order_allowed_for_current_device"] = True
        engine_lock["message"] = "현재 장치가 활성 실거래 장치로 지정되었습니다."

        save_json_file(engine_lock_path, engine_lock)

        print("\n실행 결과")
        print(f"active_live_device          : {engine_lock['active_live_device']}")
        print(f"active_live_mode            : {engine_lock['active_live_mode']}")
        print(f"active_since                : {engine_lock['active_since']}")
        print(f"현재 장치 실거래 허용 여부 : {engine_lock['live_order_allowed_for_current_device']}")
        print("현재 장치가 실거래 전용 장치로 지정되었습니다.")

    except Exception as exc:
        print("\n[실패] 활성 실거래 장치 지정 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()