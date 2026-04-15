from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
BASE_URL = "https://api.upbit.com"


def load_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)


def get_env_str(key: str, default: str) -> str:
    value = os.getenv(key, default)
    return value.strip() if isinstance(value, str) else default


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
        raise ValueError("캔들 데이터를 가져오지 못했습니다.")

    return data


def candles_to_df(candles: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(candles)

    # 업비트 캔들은 최신봉 -> 과거봉 순서이므로 뒤집어준다.
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


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_last_row_info(df_60m: pd.DataFrame, df_15m: pd.DataFrame) -> None:
    row_60 = df_60m.iloc[-1]
    row_15 = df_15m.iloc[-1]

    print_header("기본 정보")
    print(f"DEVICE_ID        : {get_env_str('DEVICE_ID', 'unknown-device')}")
    print(f"APP_MODE         : {get_env_str('APP_MODE', 'test')}")
    print(f"종목             : KRW-BTC")
    print(f"현재가           : {row_15['close']:,.0f} KRW")
    print(f"15분봉 시각      : {row_15['time_kst']}")
    print(f"1시간봉 시각     : {row_60['time_kst']}")


def print_trend_info(df_60m: pd.DataFrame, trend_status: str, trend_reason: str) -> None:
    row = df_60m.iloc[-1]

    print_header("1시간봉 추세 판단")
    print(f"상태             : {trend_status}")
    print(f"사유             : {trend_reason}")
    print(f"종가             : {row['close']:,.0f}")
    print(f"EMA20            : {row['ema20']:,.0f}")
    print(f"EMA60            : {row['ema60']:,.0f}")


def print_pullback_info(
    df_15m: pd.DataFrame,
    pullback_status: str,
    entry_signal: bool,
    detail: dict[str, bool],
) -> None:
    row = df_15m.iloc[-1]

    print_header("15분봉 눌림/회복 판단")
    print(f"상태             : {pullback_status}")
    print(f"진입 신호        : {entry_signal}")
    print(f"종가             : {row['close']:,.0f}")
    print(f"EMA20            : {row['ema20']:,.0f}")
    print(f"최근 저가 EMA20 근접 : {detail['recent_low_touched_ema20']}")
    print(f"EMA20 상향 회복      : {detail['recovered_above_ema20']}")
    print(f"현재봉 양봉 여부     : {detail['bullish_candle']}")


def main() -> None:
    try:
        load_env()

        market = "KRW-BTC"
        df_60m = prepare_df(market=market, unit=60, count=120)
        df_15m = prepare_df(market=market, unit=15, count=120)

        trend_status, trend_reason = get_trend_status(df_60m)
        pullback_status, pullback_entry, detail = get_pullback_status(df_15m)

        final_entry = trend_status in ("상승 추세", "약한 상승 추세") and pullback_entry

        print_header("WAVIS v4 전략 진입 판단 점검")
        print_last_row_info(df_60m, df_15m)
        print_trend_info(df_60m, trend_status, trend_reason)
        print_pullback_info(df_15m, pullback_status, final_entry, detail)

        print_header("최종 결과")
        print(f"최종 진입 가능 여부 : {final_entry}")
        if final_entry:
            print("판정 : 상위 추세가 살아 있고, 15분봉 눌림 회복 신호가 확인되었습니다.")
        else:
            print("판정 : 아직 진입 조건이 완성되지 않았습니다.")

    except requests.HTTPError as exc:
        print("\n[실패] 업비트 요청 오류")
        print(str(exc))
        sys.exit(1)

    except requests.RequestException as exc:
        print("\n[실패] 네트워크 요청 오류")
        print(str(exc))
        sys.exit(1)

    except Exception as exc:
        print("\n[실패] 실행 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()