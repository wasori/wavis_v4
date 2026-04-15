from pathlib import Path
from datetime import datetime
import json
import os
import socket

from dotenv import load_dotenv
from fastapi import FastAPI


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=False)


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_env_str(key: str, default: str) -> str:
    value = os.getenv(key, default)
    return value.strip() if isinstance(value, str) else default


def get_env_int(key: str, default: int) -> int:
    value = os.getenv(key, str(default)).strip()
    try:
        return int(value)
    except ValueError:
        return default


def load_settings() -> dict:
    return {
        "app_mode": get_env_str("APP_MODE", "test"),
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "host": get_env_str("HOST", "0.0.0.0"),
        "port": get_env_int("PORT", 8787),
        "log_dir": get_env_str("LOG_DIR", "logs"),
        "state_dir": get_env_str("STATE_DIR", "state"),
        "engine_lock_file": get_env_str("ENGINE_LOCK_FILE", "state/engine_lock.json"),
    }


SETTINGS = load_settings()
APP_STARTED_AT = get_now_iso()


def ensure_runtime_dirs() -> None:
    log_dir = PROJECT_ROOT / SETTINGS["log_dir"]
    state_dir = PROJECT_ROOT / SETTINGS["state_dir"]

    log_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)


def is_live_mode() -> bool:
    return SETTINGS["app_mode"].lower() == "live"


def get_signal_state_path() -> Path:
    return PROJECT_ROOT / SETTINGS["state_dir"] / "signal_state.json"


def get_engine_lock_path() -> Path:
    return PROJECT_ROOT / SETTINGS["engine_lock_file"]


def read_json_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


app = FastAPI(
    title="WAVIS v4",
    version="0.1.0",
    description="업비트 실전 자동매매 프로젝트 기본 서버 뼈대",
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_runtime_dirs()

    print("=" * 60)
    print("WAVIS v4 서버 시작")
    print(f"시작 시각         : {APP_STARTED_AT}")
    print(f"머신 이름         : {socket.gethostname()}")
    print(f"DEVICE_ID         : {SETTINGS['device_id']}")
    print(f"APP_MODE          : {SETTINGS['app_mode']}")
    print(f"실거래 가능 여부  : {is_live_mode()}")
    print(f"LOG_DIR           : {SETTINGS['log_dir']}")
    print(f"STATE_DIR         : {SETTINGS['state_dir']}")
    print(f"ENGINE_LOCK_FILE  : {SETTINGS['engine_lock_file']}")
    print("=" * 60)


@app.get("/")
def root() -> dict:
    return {
        "message": "WAVIS v4 server is running",
        "docs": "/docs",
        "health": "/health",
        "status": "/status",
    }


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "wavis_v4",
        "time": get_now_iso(),
    }


@app.get("/status")
def status() -> dict:
    signal_state_path = get_signal_state_path()
    engine_lock_path = get_engine_lock_path()

    signal_state = read_json_file(signal_state_path)
    engine_lock = read_json_file(engine_lock_path)

    return {
        "service": "wavis_v4",
        "version": "0.1.0",
        "started_at": APP_STARTED_AT,
        "current_time": get_now_iso(),
        "machine_name": socket.gethostname(),
        "device_id": SETTINGS["device_id"],
        "app_mode": SETTINGS["app_mode"],
        "live_trading_enabled": is_live_mode(),
        "paths": {
            "project_root": str(PROJECT_ROOT),
            "env_file_exists": ENV_PATH.exists(),
            "log_dir": str(PROJECT_ROOT / SETTINGS["log_dir"]),
            "state_dir": str(PROJECT_ROOT / SETTINGS["state_dir"]),
            "engine_lock_file": str(engine_lock_path),
            "engine_lock_exists": engine_lock_path.exists(),
            "signal_state_file": str(signal_state_path),
            "signal_state_exists": signal_state_path.exists(),
        },
        "signal_state": signal_state,
        "engine_lock": engine_lock,
    }