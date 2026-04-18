from __future__ import annotations

from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"


def get_project_root() -> Path:
    return PROJECT_ROOT


def get_env_path() -> Path:
    return ENV_PATH


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


def get_position_state_path() -> Path:
    return get_state_dir() / "position_state.json"


def get_trade_cycle_state_path() -> Path:
    return get_state_dir() / "trade_cycle_state.json"


def get_trade_loop_status_path() -> Path:
    return get_state_dir() / "trade_loop_status.json"


def get_live_readiness_path() -> Path:
    return get_state_dir() / "live_readiness.json"


def get_latest_order_response_path() -> Path:
    return get_state_dir() / "latest_order_response.json"


def get_latest_order_detail_path() -> Path:
    return get_state_dir() / "latest_order_detail.json"


def get_latest_sell_order_response_path() -> Path:
    return get_state_dir() / "latest_sell_order_response.json"


def get_last_closed_position_path() -> Path:
    return get_state_dir() / "last_closed_position.json"