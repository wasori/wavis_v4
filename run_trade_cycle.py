from __future__ import annotations

from datetime import datetime
from typing import Any
import json
import sys

import pandas as pd
import requests
from dotenv import load_dotenv

from project_paths import (
    get_env_path,
    get_env_str,
    get_project_root,
    get_log_dir,
    get_state_dir,
    get_signal_state_path,
    get_position_state_path,
    get_trade_cycle_state_path,
)


ENV_PATH = get_env_path()
PROJECT_ROOT = get_project_root()
BASE_URL = "https://api.upbit.com"

load_dotenv(dotenv_path=ENV_PATH, override=False)


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_env_float(key: str, default: float) -> float:
    raw = get_env_str(key, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def get_trade_symbols() -> list[str]:
    raw = get_env_str("TRADE_SYMBOLS", "KRW-BTC")
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    return symbols if symbols else ["KRW-BTC"]


def read_json_file(file_path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json_file(file_path, payload: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def request_json(url: str, params: dict[str, Any] | None = None) -> Any:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def get_candles(market: str, unit: int, count: int) -> list[dict[str, Any]]:
    data = request_json(
        f"{BASE_URL}/v1/candles/minutes/{unit}",
        params={"market": market, "count": count},
    )

    if not isinstance(data, list) or not data:
        raise ValueError(f"{market} 캔들 데이터를 가져오지 못했습니다.")

    return data


def get_ticker(market: str) -> dict[str, Any]:
    data = request_json(
        f"{BASE_URL}/v1/ticker",
        params={"markets": market},
    )

    if not isinstance(data, list) or not data:
        raise ValueError(f"{market} 현재가 데이터를 가져오지 못했습니다.")

    return data[0]


def candles_to_df(candles: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    df = df.iloc[::-1].reset_index(drop=True)

    rename_map = {
        "candle_date_time_kst": "time_kst",
        "opening_price": "open",
        "high_price": "high",
        "low_price": "low",
        "trade_price": "close",
        "candle_acc_trade_volume": "volume",
    }
    df = df.rename(columns=rename_map)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def add_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def prepare_df(market: str, unit: int, count: int) -> pd.DataFrame:
    candles = get_candles(market=market, unit=unit, count=count)
    df = candles_to_df(candles)
    df["ema20"] = add_ema(df, 20)
    df["ema60"] = add_ema(df, 60)
    return df


def get_trend_status(df_60m: pd.DataFrame) -> tuple[str, str]:
    current = df_60m.iloc[-1]
    previous = df_60m.iloc[-2]

    close_price = float(current["close"])
    ema20 = float(current["ema20"])
    ema60 = float(current["ema60"])
    prev_ema60 = float(previous["ema60"])

    ema20_over_ema60 = ema20 > ema60
    ema60_rising = ema60 > prev_ema60
    close_near_or_above_ema20 = close_price >= ema20 * 0.997

    if ema20_over_ema60 and ema60_rising and close_near_or_above_ema20:
        return "상승 추세", "EMA20 > EMA60, EMA60 상승, 현재가가 EMA20 위 또는 근처"

    if ema20_over_ema60 and ema60_rising:
        return "약한 상승 추세", "EMA20 > EMA60, EMA60 상승"

    return "비상승", "상위 추세 조건 미충족"


def get_pullback_status(df_15m: pd.DataFrame) -> tuple[str, bool, dict[str, bool]]:
    current = df_15m.iloc[-1]
    previous = df_15m.iloc[-2]
    recent3 = df_15m.iloc[-3:]

    ema20_now = float(current["ema20"])
    current_close = float(current["close"])
    current_open = float(current["open"])
    previous_close = float(previous["close"])

    recent_low_touched = bool((recent3["low"] <= recent3["ema20"] * 1.002).any())
    recovered_above_ema20 = current_close > ema20_now and previous_close <= ema20_now * 1.003
    bullish_candle = current_close > current_open

    detail = {
        "recent_low_touched_ema20": recent_low_touched,
        "recovered_above_ema20": recovered_above_ema20,
        "bullish_candle": bullish_candle,
    }

    if recent_low_touched and recovered_above_ema20 and bullish_candle:
        return "눌림 후 회복", True, detail

    if recent_low_touched:
        return "눌림 발생", False, detail

    return "뚜렷한 눌림 없음", False, detail


def analyze_market(market: str) -> dict[str, Any]:
    df_60m = prepare_df(market=market, unit=60, count=120)
    df_15m = prepare_df(market=market, unit=15, count=120)

    trend_status, trend_reason = get_trend_status(df_60m)
    pullback_status, pullback_entry, detail = get_pullback_status(df_15m)
    entry = trend_status in ("상승 추세", "약한 상승 추세") and pullback_entry

    row_60 = df_60m.iloc[-1]
    row_15 = df_15m.iloc[-1]

    return {
        "market": market,
        "current_close": float(row_15["close"]),
        "trend_status": trend_status,
        "trend_reason": trend_reason,
        "pullback_status": pullback_status,
        "entry": entry,
        "detail": detail,
        "time_15m": str(row_15["time_kst"]),
        "time_60m": str(row_60["time_kst"]),
        "ema20_15m": float(row_15["ema20"]),
        "ema20_60m": float(row_60["ema20"]),
        "ema60_60m": float(row_60["ema60"]),
    }


def save_signal_state(now_str: str, results: list[dict[str, Any]]):
    signal_state_path = get_signal_state_path()

    entry_candidates = [item["market"] for item in results if item["entry"]]

    payload = {
        "service": "wavis_v4",
        "type": "signal_state",
        "generated_at": now_str,
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "app_mode": get_env_str("APP_MODE", "test"),
        "target_markets": [item["market"] for item in results],
        "entry_candidates": entry_candidates,
        "entry_candidate_count": len(entry_candidates),
        "markets": results,
    }

    write_json_file(signal_state_path, payload)
    return signal_state_path


def get_position_state() -> dict | None:
    return read_json_file(get_position_state_path())


def build_exit_trigger(position_state: dict, current_price: float) -> dict[str, Any]:
    position = position_state.get("position", {})

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
        "current_price": current_price,
        "take_profit_price": take_profit_price,
        "stop_loss_price": stop_loss_price,
        "tp_hit": tp_hit,
        "sl_hit": sl_hit,
        "exit_signal": exit_signal,
        "exit_reason": exit_reason,
        "exit_message": exit_message,
        "current_pnl_krw": current_pnl_krw,
        "current_pnl_pct": current_pnl_pct,
    }


def build_cycle_result(
    now_str: str,
    signal_results: list[dict[str, Any]],
    position_state: dict | None,
) -> dict[str, Any]:
    device_id = get_env_str("DEVICE_ID", "unknown-device")
    app_mode = get_env_str("APP_MODE", "test")
    entry_candidates = [item["market"] for item in signal_results if item["entry"]]

    result: dict[str, Any] = {
        "service": "wavis_v4",
        "type": "trade_cycle_state",
        "generated_at": now_str,
        "device_id": device_id,
        "app_mode": app_mode,
        "entry_candidates": entry_candidates,
        "entry_candidate_count": len(entry_candidates),
        "has_position": False,
        "next_action": "wait_entry",
        "message": "진입 후보를 대기 중입니다.",
        "signal_results": signal_results,
        "position_summary": None,
        "exit_check": None,
    }

    if not position_state or not bool(position_state.get("has_position", False)):
        if entry_candidates:
            result["next_action"] = "entry_candidate_found"
            result["message"] = f"진입 후보 발견: {entry_candidates[0]}"
        return result

    position = position_state.get("position", {}) or {}
    market = str(position.get("market", "")).strip()
    executed_volume = to_float(position.get("executed_volume"))
    avg_entry_price = to_float(position.get("avg_entry_price"))

    result["has_position"] = True
    result["position_summary"] = {
        "market": market,
        "side": position.get("side"),
        "order_state": position.get("order_state"),
        "avg_entry_price": avg_entry_price,
        "executed_volume": executed_volume,
        "paid_fee": to_float(position.get("paid_fee")),
        "order_uuid": position.get("order_uuid"),
    }

    if not market or executed_volume <= 0:
        result["next_action"] = "position_state_invalid"
        result["message"] = "포지션 상태가 비정상입니다."
        return result

    ticker = get_ticker(market)
    current_price = to_float(ticker.get("trade_price"))
    exit_check = build_exit_trigger(position_state, current_price)

    result["exit_check"] = exit_check

    if exit_check["exit_signal"]:
        result["next_action"] = "exit_signal_detected"
        result["message"] = f"{market} 청산 신호 감지: {exit_check['exit_reason']}"
    else:
        result["next_action"] = "hold_position"
        result["message"] = f"{market} 포지션 보유 유지"

    return result


def save_cycle_result(payload: dict[str, Any]) -> tuple:
    cycle_state_path = get_trade_cycle_state_path()
    cycle_history_path = get_log_dir() / "trade_cycle_history.log"

    write_json_file(cycle_state_path, payload)

    history_line = (
        f"{payload.get('generated_at')} | "
        f"device_id={payload.get('device_id')} | "
        f"app_mode={payload.get('app_mode')} | "
        f"has_position={payload.get('has_position')} | "
        f"entry_candidate_count={payload.get('entry_candidate_count')} | "
        f"next_action={payload.get('next_action')} | "
        f"message={payload.get('message')}"
    )

    with cycle_history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return cycle_state_path, cycle_history_path


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_signal_summary(results: list[dict[str, Any]]) -> None:
    print_header("신호 요약")
    if not results:
        print("분석 결과가 없습니다.")
        return

    for item in results:
        print(
            f"{item['market']:<10} | "
            f"현재가 {item['current_close']:>14,.0f} | "
            f"추세 {item['trend_status']:<10} | "
            f"눌림 {item['pullback_status']:<12} | "
            f"진입 {item['entry']}"
        )


def print_cycle_summary(cycle_result: dict[str, Any]) -> None:
    print_header("사이클 판단 결과")
    print(f"포지션 보유 여부        : {cycle_result['has_position']}")
    print(f"진입 후보 수            : {cycle_result['entry_candidate_count']}")
    print(
        f"진입 후보 목록          : "
        f"{', '.join(cycle_result['entry_candidates']) if cycle_result['entry_candidates'] else '없음'}"
    )
    print(f"다음 액션              : {cycle_result['next_action']}")
    print(f"설명                  : {cycle_result['message']}")

    if cycle_result.get("position_summary"):
        pos = cycle_result["position_summary"]
        print_header("현재 포지션 요약")
        print(f"종목                  : {pos.get('market')}")
        print(f"평균 진입가            : {pos.get('avg_entry_price', 0):,.8f}")
        print(f"체결 수량              : {pos.get('executed_volume', 0):,.8f}")
        print(f"수수료                : {pos.get('paid_fee', 0):,.8f}")

    if cycle_result.get("exit_check"):
        ex = cycle_result["exit_check"]
        print_header("청산 신호 점검")
        print(f"현재가                : {ex.get('current_price', 0):,.8f}")
        print(f"익절 목표가            : {ex.get('take_profit_price', 0):,.8f}")
        print(f"손절 기준가            : {ex.get('stop_loss_price', 0):,.8f}")
        print(f"익절 도달 여부          : {ex.get('tp_hit')}")
        print(f"손절 도달 여부          : {ex.get('sl_hit')}")
        print(f"청산 신호 여부          : {ex.get('exit_signal')}")
        print(f"청산 사유 코드          : {ex.get('exit_reason')}")
        print(f"현재 손익(KRW)         : {ex.get('current_pnl_krw', 0):,.8f}")
        print(f"현재 손익률(%)         : {ex.get('current_pnl_pct', 0):.4f}%")


def main() -> None:
    try:
        now_str = get_now_iso()
        markets = get_trade_symbols()

        get_log_dir()
        get_state_dir()

        print_header("WAVIS v4 트레이드 사이클 실행")
        print(f"실행 시각              : {now_str}")
        print(f"프로젝트 경로          : {PROJECT_ROOT}")
        print(f".env 존재 여부         : {ENV_PATH.exists()}")
        print(f"DEVICE_ID              : {get_env_str('DEVICE_ID', 'unknown-device')}")
        print(f"APP_MODE               : {get_env_str('APP_MODE', 'test')}")
        print(f"대상 종목              : {', '.join(markets)}")

        signal_results: list[dict[str, Any]] = []
        for market in markets:
            signal_results.append(analyze_market(market))

        signal_state_path = save_signal_state(now_str, signal_results)
        position_state = get_position_state()
        cycle_result = build_cycle_result(now_str, signal_results, position_state)
        cycle_state_path, cycle_history_path = save_cycle_result(cycle_result)

        print_signal_summary(signal_results)
        print_cycle_summary(cycle_result)

        print_header("저장 완료")
        print(f"신호 상태 파일          : {signal_state_path}")
        print(f"사이클 상태 파일        : {cycle_state_path}")
        print(f"사이클 이력 로그 파일   : {cycle_history_path}")

        print_header("최종 결과")
        print("트레이드 사이클 1회 실행이 완료되었습니다.")
        print("현재 상태에 맞는 다음 액션이 계산되었습니다.")

    except requests.HTTPError as exc:
        print("\n[실패] 업비트 요청 오류")
        print(str(exc))
        sys.exit(1)

    except requests.RequestException as exc:
        print("\n[실패] 네트워크 요청 오류")
        print(str(exc))
        sys.exit(1)

    except Exception as exc:
        print("\n[실패] 트레이드 사이클 실행 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()