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


def build_market_sell_preview(market: str, volume: float) -> dict[str, str]:
    return {
        "market": market,
        "side": "ask",
        "ord_type": "market",
        "volume": f"{volume:.16f}".rstrip("0").rstrip("."),
    }


def main() -> None:
    try:
        load_env()

        position_state_path = get_position_state_path()
        position_state = read_json_file(position_state_path)

        print_header("WAVIS v4 시장가 매도 요청 미리보기")
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
            print("시장가 매도 요청 미리보기를 만들 대상이 없습니다.")
            sys.exit(1)

        market = str(position.get("market", "")).strip()
        side = str(position.get("side", "")).strip()
        order_state = str(position.get("order_state", "")).strip()
        executed_volume = to_float(position.get("executed_volume"))
        avg_entry_price = to_float(position.get("avg_entry_price"))
        paid_fee = to_float(position.get("paid_fee"))

        if not market:
            print_header("최종 결과")
            print("포지션 종목 정보가 없습니다.")
            sys.exit(1)

        if side != "bid" or executed_volume <= 0:
            print_header("최종 결과")
            print("현재 데이터는 매수 포지션 기준이 아닙니다.")
            print("시장가 매도 요청 미리보기를 중단합니다.")
            sys.exit(1)

        preview_payload = build_market_sell_preview(
            market=market,
            volume=executed_volume,
        )

        print_header("현재 포지션 요약")
        print(f"종목                  : {market}")
        print(f"매수/매도 방향         : {side}")
        print(f"주문 상태              : {order_state}")
        print(f"평균 진입가            : {avg_entry_price:,.8f}")
        print(f"체결 수량              : {executed_volume:,.8f}")
        print(f"누적 수수료            : {paid_fee:,.8f}")

        print_header("업비트 시장가 매도 요청 미리보기")
        print(json.dumps(preview_payload, ensure_ascii=False, indent=2))

        print_header("최종 결과")
        print("실제 매도 주문 전송 없이 시장가 매도 요청 형태만 미리 확인했습니다.")
        print("다음 단계에서 이 구조를 실제 매도 주문 파일로 연결할 수 있습니다.")

    except Exception as exc:
        print("\n[실패] 시장가 매도 미리보기 생성 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()