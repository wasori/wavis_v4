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


def get_state_dir() -> Path:
    state_dir_name = get_env_str("STATE_DIR", "state")
    state_dir = PROJECT_ROOT / state_dir_name
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_engine_lock_path() -> Path:
    lock_file_value = get_env_str("ENGINE_LOCK_FILE", "state/engine_lock.json")
    return PROJECT_ROOT / lock_file_value


def read_existing_lock(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_engine_lock_payload(existing: dict | None) -> dict:
    now_str = get_now_iso()
    device_id = get_env_str("DEVICE_ID", "unknown-device")
    app_mode = get_env_str("APP_MODE", "test").lower()
    machine_name = socket.gethostname()

    existing = existing or {}

    lock_enabled = bool(existing.get("lock_enabled", True))
    active_live_device = existing.get("active_live_device")
    active_live_mode = existing.get("active_live_mode")
    active_since = existing.get("active_since")

    live_order_allowed_for_current_device = (
        lock_enabled
        and app_mode == "live"
        and active_live_device == device_id
    )

    if app_mode == "test":
        message = "현재 장치는 test 모드입니다. 실거래 주문은 허용되지 않습니다."
    elif active_live_device is None:
        message = "live 모드이지만 아직 활성 실거래 장치가 지정되지 않았습니다."
    elif active_live_device == device_id:
        message = "현재 장치가 활성 실거래 장치입니다."
    else:
        message = f"현재 장치는 활성 실거래 장치가 아닙니다. active_live_device={active_live_device}"

    return {
        "service": "wavis_v4",
        "type": "engine_lock",
        "lock_enabled": lock_enabled,
        "active_live_device": active_live_device,
        "active_live_mode": active_live_mode,
        "active_since": active_since,
        "last_updated_at": now_str,
        "last_updated_by": device_id,
        "last_action": "refresh_engine_lock_file",
        "current_snapshot": {
            "device_id": device_id,
            "app_mode": app_mode,
            "machine_name": machine_name,
            "env_file_exists": ENV_PATH.exists(),
        },
        "live_order_allowed_for_current_device": live_order_allowed_for_current_device,
        "message": message,
    }


def save_engine_lock(file_path: Path, payload: dict) -> None:
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
        get_state_dir()

        engine_lock_path = get_engine_lock_path()
        existing = read_existing_lock(engine_lock_path)
        payload = build_engine_lock_payload(existing)
        save_engine_lock(engine_lock_path, payload)

        print_header("WAVIS v4 엔진 잠금 파일 초기화")
        print(f"프로젝트 경로                  : {PROJECT_ROOT}")
        print(f".env 존재 여부                 : {ENV_PATH.exists()}")
        print(f"현재 장치 ID                   : {payload['current_snapshot']['device_id']}")
        print(f"현재 APP_MODE                  : {payload['current_snapshot']['app_mode']}")
        print(f"현재 머신 이름                 : {payload['current_snapshot']['machine_name']}")
        print(f"잠금 사용 여부                 : {payload['lock_enabled']}")
        print(f"활성 실거래 장치               : {payload['active_live_device']}")
        print(f"현재 장치 실거래 허용 여부     : {payload['live_order_allowed_for_current_device']}")
        print(f"설명                           : {payload['message']}")

        print_header("저장 완료")
        print(f"엔진 잠금 파일                 : {engine_lock_path}")

    except Exception as exc:
        print("\n[실패] 엔진 잠금 파일 처리 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()