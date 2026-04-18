from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime
import base64
import hashlib
import hmac
import json
import os
import socket
import sys
import uuid

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


def get_engine_lock_path() -> Path:
    lock_file_value = get_env_str("ENGINE_LOCK_FILE", "state/engine_lock.json")
    return PROJECT_ROOT / lock_file_value


def read_json_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def evaluate_live_order_guard() -> dict[str, Any]:
    device_id = get_env_str("DEVICE_ID", "unknown-device")
    app_mode = get_env_str("APP_MODE", "test").lower()
    machine_name = socket.gethostname()

    engine_lock_path = get_engine_lock_path()
    engine_lock = read_json_file(engine_lock_path)

    result = {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "device_id": device_id,
        "app_mode": app_mode,
        "machine_name": machine_name,
        "engine_lock_path": str(engine_lock_path),
        "engine_lock_exists": engine_lock_path.exists(),
        "allow_live_order": False,
        "reason": "",
        "engine_lock": engine_lock,
    }

    if app_mode != "live":
        result["reason"] = "APP_MODE가 live가 아니므로 주문 가능 정보 조회가 차단됩니다."
        return result

    if engine_lock is None:
        result["reason"] = "engine_lock.json 파일이 없어 주문 가능 정보 조회가 차단됩니다."
        return result

    if not bool(engine_lock.get("lock_enabled", True)):
        result["reason"] = "engine lock이 비활성화되어 있어 주문 가능 정보 조회가 차단됩니다."
        return result

    active_live_device = engine_lock.get("active_live_device")
    if active_live_device is None:
        result["reason"] = "활성 실거래 장치가 지정되지 않아 주문 가능 정보 조회가 차단됩니다."
        return result

    if active_live_device != device_id:
        result["reason"] = (
            f"현재 장치({device_id})가 활성 실거래 장치({active_live_device})가 아니므로 "
            "주문 가능 정보 조회가 차단됩니다."
        )
        return result

    result["allow_live_order"] = True
    result["reason"] = "현재 장치는 live 모드이며 활성 실거래 장치로 등록되어 있습니다."
    return result


def build_query_string(params: dict[str, Any]) -> str:
    parts: list[str] = []

    for key, value in params.items():
        if isinstance(value, list):
            for item in value:
                parts.append(f"{key}={item}")
        else:
            parts.append(f"{key}={value}")

    return "&".join(parts)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def make_jwt_token(
    access_key: str,
    secret_key: str,
    query_params: dict[str, Any] | None = None,
) -> str:
    header = {
        "alg": "HS512",
        "typ": "JWT",
    }

    payload: dict[str, Any] = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
    }

    if query_params:
        query_string = build_query_string(query_params)
        query_hash = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
        payload["query_hash"] = query_hash
        payload["query_hash_alg"] = "SHA512"

    header_b64 = b64url_encode(
        json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    payload_b64 = b64url_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha512,
    ).digest()
    signature_b64 = b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def make_auth_headers(query_params: dict[str, Any] | None = None) -> dict[str, str]:
    access_key = get_env_str("UPBIT_ACCESS_KEY")
    secret_key = get_env_str("UPBIT_SECRET_KEY")

    if not access_key or not secret_key:
        print("[중지] .env 파일에 업비트 API 키가 비어 있습니다.")
        print("UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY 값을 먼저 입력해라.")
        sys.exit(1)

    token = make_jwt_token(
        access_key=access_key,
        secret_key=secret_key,
        query_params=query_params,
    )

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def request_order_chance(market: str) -> dict[str, Any]:
    params = {"market": market}
    headers = make_auth_headers(query_params=params)

    response = requests.get(
        f"{BASE_URL}/v1/orders/chance",
        params=params,
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("주문 가능 정보 응답 형식이 올바르지 않습니다.")

    return data


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_basic_info(market: str) -> None:
    print_header("WAVIS v4 주문 가능 정보 조회")
    print(f"실행 시각      : {datetime.now().astimezone().isoformat(timespec='seconds')}")
    print(f"프로젝트 경로  : {PROJECT_ROOT}")
    print(f".env 존재 여부 : {ENV_PATH.exists()}")
    print(f"DEVICE_ID      : {get_env_str('DEVICE_ID', 'unknown-device')}")
    print(f"APP_MODE       : {get_env_str('APP_MODE', 'test')}")
    print(f"조회 종목      : {market}")


def print_guard_result(guard_result: dict[str, Any]) -> None:
    print_header("실거래 가드 검사 결과")
    print(f"현재 장치 ID   : {guard_result['device_id']}")
    print(f"현재 APP_MODE  : {guard_result['app_mode']}")
    print(f"머신 이름      : {guard_result['machine_name']}")
    print(f"잠금 파일 존재 : {guard_result['engine_lock_exists']}")
    print(f"실행 허용 여부 : {guard_result['allow_live_order']}")
    print(f"판정          : {guard_result['reason']}")


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def print_order_chance(data: dict[str, Any]) -> None:
    market_info = data.get("market", {})
    bid_account = data.get("bid_account", {})
    ask_account = data.get("ask_account", {})

    print_header("수수료 / 주문 조건")
    print(f"매수 수수료      : {to_float(data.get('bid_fee')):.6f}")
    print(f"매도 수수료      : {to_float(data.get('ask_fee')):.6f}")
    print(f"메이커 매수 수수료: {to_float(data.get('maker_bid_fee')):.6f}")
    print(f"메이커 매도 수수료: {to_float(data.get('maker_ask_fee')):.6f}")
    print(f"지원 매수 타입   : {', '.join(market_info.get('bid_types', []))}")
    print(f"지원 매도 타입   : {', '.join(market_info.get('ask_types', []))}")
    print(f"지원 주문 방향   : {', '.join(market_info.get('order_sides', []))}")
    print(f"마켓 상태        : {market_info.get('state')}")

    bid_info = market_info.get("bid", {})
    ask_info = market_info.get("ask", {})

    print_header("주문 금액 조건")
    print(f"매수 통화        : {bid_info.get('currency')}")
    print(f"매수 최소 금액   : {to_float(bid_info.get('min_total')):,.0f}")
    print(f"매도 통화        : {ask_info.get('currency')}")
    print(f"매도 최소 금액   : {to_float(ask_info.get('min_total')):,.0f}")
    print(f"최대 주문 금액   : {to_float(market_info.get('max_total')):,.0f}")

    print_header("계정 잔고 상태")
    print(f"매수 계정 통화   : {bid_account.get('currency')}")
    print(f"매수 가능 잔고   : {to_float(bid_account.get('balance')):,.8f}")
    print(f"매수 잠금 잔고   : {to_float(bid_account.get('locked')):,.8f}")
    print(f"매도 계정 통화   : {ask_account.get('currency')}")
    print(f"매도 가능 잔고   : {to_float(ask_account.get('balance')):,.8f}")
    print(f"매도 잠금 잔고   : {to_float(ask_account.get('locked')):,.8f}")


def main() -> None:
    try:
        load_env()

        market = "KRW-BTC"
        print_basic_info(market)

        guard_result = evaluate_live_order_guard()
        print_guard_result(guard_result)

        if not guard_result["allow_live_order"]:
            print_header("최종 결과")
            print("주문 가능 정보 조회가 차단되었습니다.")
            print("현재 장치는 실거래 허용 조건을 만족하지 않습니다.")
            sys.exit(1)

        data = request_order_chance(market)
        print_order_chance(data)

        print_header("최종 결과")
        print("주문 가능 정보 조회 완료")
        print("현재 장치는 실거래 허용 조건을 만족합니다.")

    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        body_text = response.text if response is not None else ""
        print("\n[실패] 주문 가능 정보 조회 HTTP 오류")
        print(f"status_code: {status_code}")
        print(body_text)
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