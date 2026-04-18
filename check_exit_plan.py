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


def build_exit_plan(position_state: dict) -> dict:
    position = position_state.get("position", {})

    market = position.get("market")
    side = position.get("side")
    order_state = position.get("order_state")
    avg_entry_price = to_float(position.get("avg_entry_price"))
    executed_volume = to_float(position.get("executed_volume"))
    paid_fee = to_float(position.get("paid_fee"))

    take_profit_pct = get_env_float("TAKE_PROFIT_PCT", 0.01)
    stop_loss_pct = get_env_float("STOP_LOSS_PCT", 0.008)

    take_profit_price = avg_entry_price * (1 + take_profit_pct)
    stop_loss_price = avg_entry_price * (1 - stop_loss_pct)

    estimated_take_profit_value = take_profit_price * executed_volume
    estimated_stop_loss_value = stop_loss_price * executed_volume
    entry_value = avg_entry_price * executed_volume

    estimated_take_profit_pnl = estimated_take_profit_value - entry_value - paid_fee
    estimated_stop_loss_pnl = estimated_stop_loss_value - entry_value - paid_fee

    return {
        "market": market,
        "side": side,
        "order_state": order_state,
        "avg_entry_price": avg_entry_price,
        "executed_volume": executed_volume,
        "paid_fee": paid_fee,
        "take_profit_pct": take_profit_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_price": take_profit_price,
        "stop_loss_price": stop_loss_price,
        "entry_value": entry_value,
        "estimated_take_profit_value": estimated_take_profit_value,
        "estimated_stop_loss_value": estimated_stop_loss_value,
        "estimated_take_profit_pnl": estimated_take_profit_pnl,
        "estimated_stop_loss_pnl": estimated_stop_loss_pnl,
    }


def main() -> None:
    try:
        load_env()

        position_state_path = get_position_state_path()
        position_state = read_json_file(position_state_path)

        print_header("WAVIS v4 익절/손절 계획 점검")
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
            print("먼저 실제 주문 후 build_position_state.py 를 실행해라.")
            sys.exit(1)

        has_position = bool(position_state.get("has_position", False))
        position = position_state.get("position", {})

        if not has_position:
            print_header("최종 결과")
            print("현재 활성 포지션이 없습니다.")
            print("익절/손절 계획을 계산할 대상이 없습니다.")
            sys.exit(1)

        if position.get("side") != "bid" or to_float(position.get("executed_volume")) <= 0:
            print_header("최종 결과")
            print("현재 데이터는 매수 포지션 기준이 아닙니다.")
            print("익절/손절 계획 계산을 중단합니다.")
            sys.exit(1)

        plan = build_exit_plan(position_state)

        print_header("포지션 요약")
        print(f"종목                  : {plan['market']}")
        print(f"매수/매도 방향         : {plan['side']}")
        print(f"주문 상태              : {plan['order_state']}")
        print(f"평균 진입가            : {plan['avg_entry_price']:,.8f}")
        print(f"체결 수량              : {plan['executed_volume']:,.8f}")
        print(f"진입 금액 기준         : {plan['entry_value']:,.8f}")
        print(f"누적 수수료            : {plan['paid_fee']:,.8f}")

        print_header("익절/손절 기준")
        print(f"익절 비율              : {plan['take_profit_pct'] * 100:.3f}%")
        print(f"손절 비율              : {plan['stop_loss_pct'] * 100:.3f}%")
        print(f"익절 목표가            : {plan['take_profit_price']:,.8f}")
        print(f"손절 기준가            : {plan['stop_loss_price']:,.8f}")

        print_header("예상 손익")
        print(f"익절 시 평가 금액       : {plan['estimated_take_profit_value']:,.8f}")
        print(f"손절 시 평가 금액       : {plan['estimated_stop_loss_value']:,.8f}")
        print(f"익절 시 예상 손익       : {plan['estimated_take_profit_pnl']:,.8f}")
        print(f"손절 시 예상 손익       : {plan['estimated_stop_loss_pnl']:,.8f}")

        print_header("최종 결과")
        print("현재 포지션 기준 익절/손절 계획 계산이 완료되었습니다.")

    except Exception as exc:
        print("\n[실패] 익절/손절 계획 계산 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()