from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import sys

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


def get_ticker(market: str) -> dict[str, Any]:
    data = request_json(
        f"{BASE_URL}/v1/ticker",
        params={"markets": market},
    )

    if not isinstance(data, list) or not data:
        raise ValueError("현재가 응답 형식이 올바르지 않습니다.")

    return data[0]


def get_minutes_candles(market: str, unit: int = 15, count: int = 5) -> list[dict[str, Any]]:
    data = request_json(
        f"{BASE_URL}/v1/candles/minutes/{unit}",
        params={"market": market, "count": count},
    )

    if not isinstance(data, list) or not data:
        raise ValueError("캔들 응답 형식이 올바르지 않습니다.")

    return data


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_basic_info(market: str) -> None:
    print_header("WAVIS v4 업비트 공개 API 연결 확인")

    print(f"프로젝트 경로 : {PROJECT_ROOT}")
    print(f".env 존재 여부: {ENV_PATH.exists()}")
    print(f"DEVICE_ID      : {get_env_str('DEVICE_ID', 'unknown-device')}")
    print(f"APP_MODE       : {get_env_str('APP_MODE', 'test')}")
    print(f"조회 종목      : {market}")


def print_ticker_info(ticker: dict[str, Any]) -> None:
    trade_price = ticker.get("trade_price", 0)
    signed_change_rate = float(ticker.get("signed_change_rate", 0)) * 100
    acc_trade_price_24h = ticker.get("acc_trade_price_24h", 0)
    high_price = ticker.get("high_price", 0)
    low_price = ticker.get("low_price", 0)

    print_header("현재가 정보")
    print(f"현재가         : {trade_price:,.0f} KRW")
    print(f"등락률         : {signed_change_rate:.2f}%")
    print(f"당일 고가      : {high_price:,.0f} KRW")
    print(f"당일 저가      : {low_price:,.0f} KRW")
    print(f"24시간 거래대금: {acc_trade_price_24h:,.0f} KRW")


def print_candles_info(candles: list[dict[str, Any]]) -> None:
    print_header("최근 15분봉 5개")

    # 업비트 캔들은 최신봉부터 내려온다.
    # 보기 편하게 오래된 봉 -> 최신봉 순서로 뒤집어서 출력
    candles_sorted = list(reversed(candles))

    for index, candle in enumerate(candles_sorted, start=1):
        time_kst = candle.get("candle_date_time_kst", "-")
        opening_price = candle.get("opening_price", 0)
        high_price = candle.get("high_price", 0)
        low_price = candle.get("low_price", 0)
        trade_price = candle.get("trade_price", 0)
        candle_acc_trade_volume = candle.get("candle_acc_trade_volume", 0)

        print(
            f"[{index}] {time_kst} | "
            f"시가 {opening_price:,.0f} | "
            f"고가 {high_price:,.0f} | "
            f"저가 {low_price:,.0f} | "
            f"종가 {trade_price:,.0f} | "
            f"거래량 {candle_acc_trade_volume:.6f}"
        )


def main() -> None:
    try:
        load_env()

        market = "KRW-BTC"
        print_basic_info(market)

        ticker = get_ticker(market)
        candles = get_minutes_candles(market=market, unit=15, count=5)

        print_ticker_info(ticker)
        print_candles_info(candles)

        print_header("최종 결과")
        print("업비트 공개 API 연결 확인 완료")
        print("다음 단계에서 개인 API 키를 이용한 잔고 조회로 넘어갈 수 있습니다.")

    except requests.HTTPError as exc:
        print("\n[오류] 업비트 HTTP 요청 실패")
        print(str(exc))
        sys.exit(1)

    except requests.RequestException as exc:
        print("\n[오류] 네트워크 요청 실패")
        print(str(exc))
        sys.exit(1)

    except Exception as exc:
        print("\n[오류] 실행 중 예외 발생")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()