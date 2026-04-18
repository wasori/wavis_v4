from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any
import json
import os
import sys

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
BASE_URL = "https://api.upbit.com"


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


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def request_json(url: str, params: dict[str, Any] | None = None) -> Any:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def get_ticker(market: str) -> dict[str, Any]:
    data = request_json(
        f"{BASE_URL}/v1/ticker",
        params={"markets": market},
    )

    if not isinstance(data, list) or not data:
        raise ValueError("현재가 응답 형식이 올바르지 않습니다.")

    return data[0]


def build_exit_trigger(position_state: dict, current_price: float) -> dict:
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

    tp_hit = current_price >= take_profit_price
    sl_hit = current_price <= stop_loss_price

    entry_value = avg_entry_price * executed_volume
    current_value = current_price * executed_volume
    current_pnl_krw = current_value - entry_value - paid_fee

    current_pnl_pct = 0.0
    if avg_entry_price > 0:
        current_pnl_pct = ((current_price - avg_entry_price) / avg_entry_price) * 100

    exit_signal = tp_hit or sl_hit

    if tp_hit:
        exit_reason = "take_profit_hit"
        exit_message = "현재가가 익절 목표가 이상입니다."
    elif sl_hit:
        exit_reason = "stop_loss_hit"
        exit_message = "현재가가 손절 기준가 이하입니다."
    else:
        exit_reason = "hold"
        exit_message = "아직 익절/손절 조건에 도달하지 않았습니다."

    return {
        "market": market,
        "side": side,
        "order_state": order_state,
        "avg_entry_price": avg_entry_price,
        "executed_volume": executed_volume,
        "paid_fee": paid_fee,
        "current_price": current_price,
        "take_profit_pct": take_profit_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_price": take_profit_price,
        "stop_loss_price": stop_loss_price,
        "tp_hit": tp_hit,
        "sl_hit": sl_hit,
        "exit_signal": exit_signal,
        "exit_reason": exit_reason,
        "exit_message": exit_message,
        "entry_value": entry_value,
        "current_value": current_value,
        "current_pnl_krw": current_pnl_krw,
        "current_pnl_pct": current_pnl_pct,
    }


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    try:
        load_env()

        position_state_path = get_position_state_path()
        position_state = read_json_file(position_state_path)

        print_header("WAVIS v4 익절/손절 도달 점검")
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
            print("익절/손절 도달 여부를 점검할 대상이 없습니다.")
            sys.exit(1)

        market = str(position.get("market", "")).strip()
        side = str(position.get("side", "")).strip()
        executed_volume = to_float(position.get("executed_volume"))

        if not market:
            print_header("최종 결과")
            print("포지션 종목 정보가 없습니다.")
            sys.exit(1)

        if side != "bid" or executed_volume <= 0:
            print_header("최종 결과")
            print("현재 데이터는 매수 포지션 기준이 아닙니다.")
            print("익절/손절 도달 여부 점검을 중단합니다.")
            sys.exit(1)

        ticker = get_ticker(market)
        current_price = to_float(ticker.get("trade_price"))

        result = build_exit_trigger(position_state, current_price)

        print_header("포지션 요약")
        print(f"종목                  : {result['market']}")
        print(f"평균 진입가            : {result['avg_entry_price']:,.8f}")
        print(f"체결 수량              : {result['executed_volume']:,.8f}")
        print(f"누적 수수료            : {result['paid_fee']:,.8f}")
        print(f"현재가                : {result['current_price']:,.8f}")

        print_header("익절/손절 기준")
        print(f"익절 비율              : {result['take_profit_pct'] * 100:.3f}%")
        print(f"손절 비율              : {result['stop_loss_pct'] * 100:.3f}%")
        print(f"익절 목표가            : {result['take_profit_price']:,.8f}")
        print(f"손절 기준가            : {result['stop_loss_price']:,.8f}")

        print_header("현재 손익 상태")
        print(f"현재 평가 금액          : {result['current_value']:,.8f}")
        print(f"현재 예상 손익(KRW)     : {result['current_pnl_krw']:,.8f}")
        print(f"현재 손익률(%)         : {result['current_pnl_pct']:.4f}%")

        print_header("도달 여부 판단")
        print(f"익절 도달 여부          : {result['tp_hit']}")
        print(f"손절 도달 여부          : {result['sl_hit']}")
        print(f"청산 신호 여부          : {result['exit_signal']}")
        print(f"청산 사유 코드          : {result['exit_reason']}")
        print(f"설명                  : {result['exit_message']}")

        print_header("최종 결과")
        if result["exit_signal"]:
            print("현재 포지션은 청산 후보입니다.")
        else:
            print("현재 포지션은 아직 보유 유지 상태입니다.")

    except requests.HTTPError as exc:
        print("\n[실패] 현재가 조회 HTTP 오류")
        print(str(exc))
        sys.exit(1)

    except requests.RequestException as exc:
        print("\n[실패] 네트워크 요청 오류")
        print(str(exc))
        sys.exit(1)

    except Exception as exc:
        print("\n[실패] 익절/손절 도달 점검 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()