from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime
import json
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


def get_trade_symbols() -> list[str]:
    raw = get_env_str("TRADE_SYMBOLS", "KRW-BTC")
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    return symbols if symbols else ["KRW-BTC"]


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


def make_line(title: str = "") -> str:
    if title:
        return "\n" + "=" * 60 + f"\n{title}\n" + "=" * 60
    return "\n" + "=" * 60


def build_report(
    market: str,
    df_60m: pd.DataFrame,
    df_15m: pd.DataFrame,
    trend_status: str,
    trend_reason: str,
    pullback_status: str,
    final_entry: bool,
    detail: dict[str, bool],
    now_str: str,
) -> tuple[str, str]:
    row_60 = df_60m.iloc[-1]
    row_15 = df_15m.iloc[-1]

    lines: list[str] = []

    lines.append(make_line(f"WAVIS v4 전략 진입 판단 점검 - {market}"))
    lines.append(make_line("기본 정보"))
    lines.append(f"실행 시각        : {now_str}")
    lines.append(f"DEVICE_ID        : {get_env_str('DEVICE_ID', 'unknown-device')}")
    lines.append(f"APP_MODE         : {get_env_str('APP_MODE', 'test')}")
    lines.append(f"종목             : {market}")
    lines.append(f"현재가           : {row_15['close']:,.0f} KRW")
    lines.append(f"15분봉 시각      : {row_15['time_kst']}")
    lines.append(f"1시간봉 시각     : {row_60['time_kst']}")

    lines.append(make_line("1시간봉 추세 판단"))
    lines.append(f"상태             : {trend_status}")
    lines.append(f"사유             : {trend_reason}")
    lines.append(f"종가             : {row_60['close']:,.0f}")
    lines.append(f"EMA20            : {row_60['ema20']:,.0f}")
    lines.append(f"EMA60            : {row_60['ema60']:,.0f}")

    lines.append(make_line("15분봉 눌림/회복 판단"))
    lines.append(f"상태             : {pullback_status}")
    lines.append(f"진입 신호        : {final_entry}")
    lines.append(f"종가             : {row_15['close']:,.0f}")
    lines.append(f"EMA20            : {row_15['ema20']:,.0f}")
    lines.append(f"최근 저가 EMA20 근접 : {detail['recent_low_touched_ema20']}")
    lines.append(f"EMA20 상향 회복      : {detail['recovered_above_ema20']}")
    lines.append(f"현재봉 양봉 여부     : {detail['bullish_candle']}")

    lines.append(make_line("최종 결과"))
    lines.append(f"최종 진입 가능 여부 : {final_entry}")
    if final_entry:
        lines.append("판정 : 상위 추세가 살아 있고, 15분봉 눌림 회복 신호가 확인되었습니다.")
    else:
        lines.append("판정 : 아직 진입 조건이 완성되지 않았습니다.")

    report_text = "\n".join(lines).strip() + "\n"

    summary_line = (
        f"{now_str} | "
        f"market={market} | "
        f"close={row_15['close']:,.0f} | "
        f"trend={trend_status} | "
        f"pullback={pullback_status} | "
        f"entry={final_entry}"
    )

    return report_text, summary_line


def ensure_log_dir() -> Path:
    log_dir_name = get_env_str("LOG_DIR", "logs")
    log_dir = PROJECT_ROOT / log_dir_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def ensure_state_dir() -> Path:
    state_dir_name = get_env_str("STATE_DIR", "state")
    state_dir = PROJECT_ROOT / state_dir_name
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def market_to_filename(market: str) -> str:
    return market.replace("-", "_")


def save_market_logs(log_dir: Path, market: str, report_text: str, summary_line: str) -> tuple[Path, Path]:
    safe_name = market_to_filename(market)
    latest_path = log_dir / f"signal_latest_{safe_name}.txt"
    history_path = log_dir / "signal_history.log"

    latest_path.write_text(report_text, encoding="utf-8")

    with history_path.open("a", encoding="utf-8") as f:
        f.write(summary_line + "\n")

    return latest_path, history_path


def save_summary_report(log_dir: Path, content: str) -> Path:
    summary_path = log_dir / "signal_summary.txt"
    summary_path.write_text(content, encoding="utf-8")
    return summary_path


def build_state_payload(now_str: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    entry_candidates = [item["market"] for item in results if item["entry"]]

    return {
        "service": "wavis_v4",
        "type": "signal_state",
        "generated_at": now_str,
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "app_mode": get_env_str("APP_MODE", "test"),
        "target_markets": [item["market"] for item in results],
        "entry_candidates": entry_candidates,
        "entry_candidate_count": len(entry_candidates),
        "markets": [
            {
                "market": item["market"],
                "current_close": item["current_close"],
                "trend_status": item["trend_status"],
                "trend_reason": item["trend_reason"],
                "pullback_status": item["pullback_status"],
                "entry": item["entry"],
                "detail": item["detail"],
                "time_15m": item["time_15m"],
                "time_60m": item["time_60m"],
                "ema20_15m": item["ema20_15m"],
                "ema20_60m": item["ema20_60m"],
                "ema60_60m": item["ema60_60m"],
            }
            for item in results
        ],
    }


def save_state_json(state_dir: Path, payload: dict[str, Any]) -> Path:
    state_path = state_dir / "signal_state.json"
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state_path


def analyze_market(market: str, now_str: str) -> dict[str, Any]:
    df_60m = prepare_df(market=market, unit=60, count=120)
    df_15m = prepare_df(market=market, unit=15, count=120)

    trend_status, trend_reason = get_trend_status(df_60m)
    pullback_status, pullback_entry, detail = get_pullback_status(df_15m)
    final_entry = trend_status in ("상승 추세", "약한 상승 추세") and pullback_entry

    report_text, summary_line = build_report(
        market=market,
        df_60m=df_60m,
        df_15m=df_15m,
        trend_status=trend_status,
        trend_reason=trend_reason,
        pullback_status=pullback_status,
        final_entry=final_entry,
        detail=detail,
        now_str=now_str,
    )

    row_60 = df_60m.iloc[-1]
    row_15 = df_15m.iloc[-1]

    return {
        "market": market,
        "current_close": float(row_15["close"]),
        "trend_status": trend_status,
        "trend_reason": trend_reason,
        "pullback_status": pullback_status,
        "entry": final_entry,
        "detail": detail,
        "time_15m": str(row_15["time_kst"]),
        "time_60m": str(row_60["time_kst"]),
        "ema20_15m": float(row_15["ema20"]),
        "ema20_60m": float(row_60["ema20"]),
        "ema60_60m": float(row_60["ema60"]),
        "report_text": report_text,
        "summary_line": summary_line,
    }


def build_total_summary(results: list[dict[str, Any]], now_str: str) -> str:
    lines: list[str] = []

    lines.append(make_line("WAVIS v4 다중 종목 요약"))
    lines.append(f"실행 시각        : {now_str}")
    lines.append(f"DEVICE_ID        : {get_env_str('DEVICE_ID', 'unknown-device')}")
    lines.append(f"APP_MODE         : {get_env_str('APP_MODE', 'test')}")
    lines.append(f"대상 종목 수     : {len(results)}")

    lines.append(make_line("종목별 요약"))
    for item in results:
        lines.append(
            f"{item['market']:<10} | "
            f"현재가 {item['current_close']:>14,.0f} | "
            f"추세 {item['trend_status']:<10} | "
            f"눌림 {item['pullback_status']:<12} | "
            f"진입 {item['entry']}"
        )

    entry_markets = [item["market"] for item in results if item["entry"]]
    lines.append(make_line("최종 후보"))
    if entry_markets:
        lines.append("진입 가능 후보 : " + ", ".join(entry_markets))
    else:
        lines.append("진입 가능 후보 : 없음")

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    try:
        load_env()

        markets = get_trade_symbols()
        now_str = datetime.now().astimezone().isoformat(timespec="seconds")
        log_dir = ensure_log_dir()
        state_dir = ensure_state_dir()

        results: list[dict[str, Any]] = []

        for market in markets:
            result = analyze_market(market=market, now_str=now_str)
            results.append(result)

            print(result["report_text"], end="")

            latest_path, history_path = save_market_logs(
                log_dir=log_dir,
                market=market,
                report_text=result["report_text"],
                summary_line=result["summary_line"],
            )

            print(make_line("로그 저장 완료"))
            print(f"종목             : {market}")
            print(f"최신 로그 파일   : {latest_path}")
            print(f"누적 로그 파일   : {history_path}")

        total_summary = build_total_summary(results, now_str)
        summary_path = save_summary_report(log_dir, total_summary)

        print(total_summary, end="")
        print(make_line("요약 파일 저장 완료"))
        print(f"요약 로그 파일   : {summary_path}")

        state_payload = build_state_payload(now_str, results)
        state_path = save_state_json(state_dir, state_payload)

        print(make_line("상태 파일 저장 완료"))
        print(f"상태 파일        : {state_path}")

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