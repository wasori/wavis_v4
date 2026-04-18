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


def get_engine_lock_path() -> Path:
    return PROJECT_ROOT / get_env_str("ENGINE_LOCK_FILE", "state/engine_lock.json")


def get_signal_state_path() -> Path:
    return get_state_dir() / "signal_state.json"


def get_loop_status_path() -> Path:
    return get_state_dir() / "trade_loop_status.json"


def read_json_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def mask_secret(value: str) -> str:
    if not value:
        return "없음"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def build_checks() -> dict:
    device_id = get_env_str("DEVICE_ID", "unknown-device")
    app_mode = get_env_str("APP_MODE", "test").lower()

    access_key = get_env_str("UPBIT_ACCESS_KEY", "")
    secret_key = get_env_str("UPBIT_SECRET_KEY", "")

    confirm_live_buy = get_env_str("CONFIRM_LIVE_ORDER", "")
    confirm_live_sell = get_env_str("CONFIRM_LIVE_SELL_ORDER", "")

    engine_lock_path = get_engine_lock_path()
    signal_state_path = get_signal_state_path()
    loop_status_path = get_loop_status_path()

    engine_lock = read_json_file(engine_lock_path)
    signal_state = read_json_file(signal_state_path)
    loop_status = read_json_file(loop_status_path)

    active_live_device = None
    lock_enabled = None

    if engine_lock is not None:
        active_live_device = engine_lock.get("active_live_device")
        lock_enabled = engine_lock.get("lock_enabled")

    checks = [
        {
            "name": "env_file_exists",
            "ok": ENV_PATH.exists(),
            "detail": ".env 파일 존재 여부",
        },
        {
            "name": "device_id_set",
            "ok": device_id not in ("", "unknown-device"),
            "detail": f"DEVICE_ID={device_id}",
        },
        {
            "name": "app_mode_live",
            "ok": app_mode == "live",
            "detail": f"APP_MODE={app_mode}",
        },
        {
            "name": "upbit_access_key_set",
            "ok": bool(access_key),
            "detail": f"UPBIT_ACCESS_KEY={mask_secret(access_key)}",
        },
        {
            "name": "upbit_secret_key_set",
            "ok": bool(secret_key),
            "detail": f"UPBIT_SECRET_KEY={mask_secret(secret_key)}",
        },
        {
            "name": "engine_lock_exists",
            "ok": engine_lock_path.exists(),
            "detail": str(engine_lock_path),
        },
        {
            "name": "engine_lock_enabled",
            "ok": engine_lock is not None and bool(lock_enabled) is True,
            "detail": f"lock_enabled={lock_enabled}",
        },
        {
            "name": "active_live_device_matches",
            "ok": engine_lock is not None and active_live_device == device_id,
            "detail": f"active_live_device={active_live_device}",
        },
        {
            "name": "signal_state_exists",
            "ok": signal_state_path.exists(),
            "detail": str(signal_state_path),
        },
        {
            "name": "loop_status_exists",
            "ok": loop_status_path.exists(),
            "detail": str(loop_status_path),
        },
        {
            "name": "confirm_live_buy_enabled",
            "ok": confirm_live_buy == "YES",
            "detail": f"CONFIRM_LIVE_ORDER={confirm_live_buy or '미설정'}",
        },
        {
            "name": "confirm_live_sell_enabled",
            "ok": confirm_live_sell == "YES",
            "detail": f"CONFIRM_LIVE_SELL_ORDER={confirm_live_sell or '미설정'}",
        },
    ]

    required_names = {
        "env_file_exists",
        "device_id_set",
        "app_mode_live",
        "upbit_access_key_set",
        "upbit_secret_key_set",
        "engine_lock_exists",
        "engine_lock_enabled",
        "active_live_device_matches",
        "signal_state_exists",
        "confirm_live_buy_enabled",
        "confirm_live_sell_enabled",
    }

    failed_required = [
        item["name"]
        for item in checks
        if item["name"] in required_names and not item["ok"]
    ]

    ready_for_live = len(failed_required) == 0

    message = (
        "실거래 시작 가능 상태입니다."
        if ready_for_live
        else "아직 실거래 시작 전 준비가 덜 되었습니다."
    )

    return {
        "generated_at": get_now_iso(),
        "device_id": device_id,
        "app_mode": app_mode,
        "ready_for_live": ready_for_live,
        "message": message,
        "checks": checks,
        "failed_required": failed_required,
        "engine_lock_summary": {
            "exists": engine_lock_path.exists(),
            "lock_enabled": lock_enabled,
            "active_live_device": active_live_device,
        },
        "signal_state_summary": {
            "exists": signal_state_path.exists(),
            "entry_candidate_count": (
                signal_state.get("entry_candidate_count", 0) if signal_state else 0
            ),
            "entry_candidates": (
                signal_state.get("entry_candidates", []) if signal_state else []
            ),
        },
        "loop_status_summary": {
            "exists": loop_status_path.exists(),
            "is_running": (loop_status.get("is_running") if loop_status else None),
            "current_cycle": (loop_status.get("current_cycle") if loop_status else None),
            "last_next_action": (
                loop_status.get("last_next_action") if loop_status else None
            ),
        },
    }


def save_live_readiness(payload: dict) -> tuple[Path, Path]:
    state_dir = get_state_dir()
    log_dir = get_log_dir()

    state_path = state_dir / "live_readiness.json"
    history_path = log_dir / "live_readiness_history.log"

    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    history_line = (
        f"{payload.get('generated_at')} | "
        f"device_id={payload.get('device_id')} | "
        f"app_mode={payload.get('app_mode')} | "
        f"ready_for_live={payload.get('ready_for_live')} | "
        f"failed_required={','.join(payload.get('failed_required', [])) or '없음'} | "
        f"message={payload.get('message')}"
    )

    with history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return state_path, history_path


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    try:
        load_env()

        payload = build_checks()
        state_path, history_path = save_live_readiness(payload)

        print_header("WAVIS v4 실거래 전환 준비 점검")
        print(f"실행 시각              : {payload['generated_at']}")
        print(f"프로젝트 경로          : {PROJECT_ROOT}")
        print(f".env 존재 여부         : {ENV_PATH.exists()}")
        print(f"DEVICE_ID              : {payload['device_id']}")
        print(f"APP_MODE               : {payload['app_mode']}")
        print(f"실거래 시작 가능 여부   : {payload['ready_for_live']}")
        print(f"설명                  : {payload['message']}")

        print_header("필수 점검 항목")
        for item in payload["checks"]:
            status = "OK" if item["ok"] else "FAIL"
            print(f"[{status:<4}] {item['name']:<28} | {item['detail']}")

        print_header("요약")
        failed_required = payload.get("failed_required", [])
        if failed_required:
            print("실패한 필수 항목:")
            for name in failed_required:
                print(f"- {name}")
        else:
            print("모든 필수 항목 통과")

        print_header("저장 완료")
        print(f"실거래 준비 상태 파일    : {state_path}")
        print(f"실거래 준비 이력 로그    : {history_path}")

        print_header("최종 결과")
        if payload["ready_for_live"]:
            print("이 장치는 실거래 시작 가능한 상태입니다.")
        else:
            print("이 장치는 아직 실거래 시작 상태가 아닙니다.")

    except Exception as exc:
        print("\n[실패] 실거래 전환 준비 점검 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()