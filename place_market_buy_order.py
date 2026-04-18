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


def get_env_float(key: str, default: float) -> float:
    raw = get_env_str(key, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def get_engine_lock_path() -> Path:
    lock_file_value = get_env_str("ENGINE_LOCK_FILE", "state/engine_lock.json")
    return PROJECT_ROOT / lock_file_value


def get_signal_state_path() -> Path:
    state_dir = get_env_str("STATE_DIR", "state")
    return PROJECT_ROOT / state_dir / "signal_state.json"


def get_state_dir() -> Path:
    state_dir = PROJECT_ROOT / get_env_str("STATE_DIR", "state")
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_log_dir() -> Path:
    log_dir = PROJECT_ROOT / get_env_str("LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


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
        result["reason"] = "APP_MODE가 live가 아니므로 실제 주문 실행이 차단됩니다."
        return result

    if engine_lock is None:
        result["reason"] = "engine_lock.json 파일이 없어 실제 주문 실행이 차단됩니다."
        return result

    if not bool(engine_lock.get("lock_enabled", True)):
        result["reason"] = "engine lock이 비활성화되어 있어 실제 주문 실행이 차단됩니다."
        return result

    active_live_device = engine_lock.get("active_live_device")
    if active_live_device is None:
        result["reason"] = "활성 실거래 장치가 지정되지 않아 실제 주문 실행이 차단됩니다."
        return result

    if active_live_device != device_id:
        result["reason"] = (
            f"현재 장치({device_id})가 활성 실거래 장치({active_live_device})가 아니므로 "
            "실제 주문 실행이 차단됩니다."
        )
        return result

    result["allow_live_order"] = True
    result["reason"] = "현재 장치는 live 모드이며 활성 실거래 장치로 등록되어 있습니다."
    return result


def choose_target_market(signal_state: dict) -> tuple[str | None, dict | None]:
    entry_candidates = signal_state.get("entry_candidates", [])
    markets = signal_state.get("markets", [])

    if not entry_candidates:
        return None, None

    target_market = entry_candidates[0]

    for item in markets:
        if item.get("market") == target_market:
            return target_market, item

    return target_market, None


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
    body_params: dict[str, Any] | None = None,
) -> str:
    header = {
        "alg": "HS512",
        "typ": "JWT",
    }

    payload: dict[str, Any] = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
    }

    if body_params:
        query_string = build_query_string(body_params)
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


def make_auth_headers(body_params: dict[str, Any] | None = None) -> dict[str, str]:
    access_key = get_env_str("UPBIT_ACCESS_KEY")
    secret_key = get_env_str("UPBIT_SECRET_KEY")

    if not access_key or not secret_key:
        print("[중지] .env 파일에 업비트 API 키가 비어 있습니다.")
        print("UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY 값을 먼저 입력해라.")
        sys.exit(1)

    token = make_jwt_token(
        access_key=access_key,
        secret_key=secret_key,
        body_params=body_params,
    )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def build_market_buy_payload(market: str, order_krw: float) -> dict[str, str]:
    identifier = (
        f"wavis-live-{get_env_str('DEVICE_ID', 'unknown')}-"
        f"{datetime.now().astimezone().strftime('%Y%m%d%H%M%S')}-"
        f"{uuid.uuid4().hex[:8]}"
    )

    return {
        "market": market,
        "side": "bid",
        "ord_type": "price",
        "price": str(int(order_krw)),
        "identifier": identifier,
    }


def request_live_order(payload: dict[str, str]) -> dict[str, Any]:
    headers = make_auth_headers(body_params=payload)

    response = requests.post(
        f"{BASE_URL}/v1/orders",
        headers=headers,
        json=payload,
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("실제 주문 응답 형식이 올바르지 않습니다.")

    return data


def ensure_manual_confirmation() -> None:
    confirm_value = get_env_str("CONFIRM_LIVE_ORDER", "")

    if confirm_value != "YES":
        print("[중지] 실제 주문 보호값이 없습니다.")
        print(".env 에 CONFIRM_LIVE_ORDER=YES 를 넣은 뒤 다시 실행해라.")
        sys.exit(1)


def save_order_state(
    target_market: str,
    order_krw: float,
    payload: dict[str, str],
    response_data: dict[str, Any],
) -> tuple[Path, Path]:
    state_dir = get_state_dir()
    log_dir = get_log_dir()

    now_str = datetime.now().astimezone().isoformat(timespec="seconds")

    latest_order_path = state_dir / "latest_order_response.json"
    order_history_path = log_dir / "order_history.log"

    state_payload = {
        "service": "wavis_v4",
        "type": "latest_order_response",
        "saved_at": now_str,
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "app_mode": get_env_str("APP_MODE", "test"),
        "market": target_market,
        "order_krw": order_krw,
        "request_payload": payload,
        "response": response_data,
    }

    latest_order_path.write_text(
        json.dumps(state_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    order_uuid = response_data.get("uuid", "-")
    order_side = response_data.get("side", "-")
    order_state = response_data.get("state", "-")
    order_identifier = response_data.get("identifier", "-")

    history_line = (
        f"{now_str} | "
        f"market={target_market} | "
        f"order_krw={int(order_krw)} | "
        f"uuid={order_uuid} | "
        f"side={order_side} | "
        f"state={order_state} | "
        f"identifier={order_identifier}"
    )

    with order_history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return latest_order_path, order_history_path


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_guard_result(guard_result: dict[str, Any]) -> None:
    print_header("실거래 가드 검사 결과")
    print(f"현재 장치 ID   : {guard_result['device_id']}")
    print(f"현재 APP_MODE  : {guard_result['app_mode']}")
    print(f"머신 이름      : {guard_result['machine_name']}")
    print(f"잠금 파일 존재 : {guard_result['engine_lock_exists']}")
    print(f"실행 허용 여부 : {guard_result['allow_live_order']}")
    print(f"판정          : {guard_result['reason']}")


def main() -> None:
    try:
        load_env()

        device_id = get_env_str("DEVICE_ID", "unknown-device")
        app_mode = get_env_str("APP_MODE", "test")
        order_krw = get_env_float("TEST_ORDER_KRW", 5000.0)

        signal_state_path = get_signal_state_path()
        signal_state = read_json_file(signal_state_path)

        print_header("WAVIS v4 실제 시장가 매수")
        print(f"실행 시각            : {datetime.now().astimezone().isoformat(timespec='seconds')}")
        print(f"프로젝트 경로        : {PROJECT_ROOT}")
        print(f".env 존재 여부       : {ENV_PATH.exists()}")
        print(f"DEVICE_ID            : {device_id}")
        print(f"APP_MODE             : {app_mode}")
        print(f"signal_state 파일     : {signal_state_path}")
        print(f"signal_state 존재 여부: {signal_state_path.exists()}")
        print(f"주문 금액            : {order_krw:,.0f} KRW")

        guard_result = evaluate_live_order_guard()
        print_guard_result(guard_result)

        if not guard_result["allow_live_order"]:
            print_header("최종 결과")
            print("실제 주문 실행이 차단되었습니다.")
            print("현재 장치는 실거래 허용 조건을 만족하지 않습니다.")
            sys.exit(1)

        ensure_manual_confirmation()

        if signal_state is None:
            print_header("최종 결과")
            print("signal_state.json 파일을 읽지 못했습니다.")
            print("먼저 check_signal.py 를 실행해라.")
            sys.exit(1)

        target_market, market_detail = choose_target_market(signal_state)

        print_header("현재 신호 상태")
        print(f"signal 생성 시각      : {signal_state.get('generated_at')}")
        print(f"진입 후보 목록        : {', '.join(signal_state.get('entry_candidates', [])) or '없음'}")

        if target_market is None:
            print_header("최종 결과")
            print("현재 진입 후보가 없어 실제 주문을 만들지 않습니다.")
            sys.exit(1)

        payload = build_market_buy_payload(
            market=target_market,
            order_krw=order_krw,
        )

        print_header("선택된 주문 후보")
        print(f"선택 종목            : {target_market}")
        if market_detail is not None:
            print(f"현재가               : {market_detail.get('current_close', 0):,.0f} KRW")
            print(f"추세 상태            : {market_detail.get('trend_status')}")
            print(f"눌림 상태            : {market_detail.get('pullback_status')}")
            print(f"15분봉 시각          : {market_detail.get('time_15m')}")
            print(f"1시간봉 시각         : {market_detail.get('time_60m')}")

        print_header("업비트 실제 주문 요청")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

        response_data = request_live_order(payload)

        print_header("업비트 실제 주문 응답")
        print(json.dumps(response_data, ensure_ascii=False, indent=2))

        latest_order_path, order_history_path = save_order_state(
            target_market=target_market,
            order_krw=order_krw,
            payload=payload,
            response_data=response_data,
        )

        print_header("주문 결과 저장 완료")
        print(f"최신 주문 상태 파일  : {latest_order_path}")
        print(f"주문 이력 로그 파일  : {order_history_path}")

        print_header("최종 결과")
        print("실제 시장가 매수 주문 요청이 완료되었습니다.")
        print("주문 응답이 state와 log에 저장되었습니다.")

    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        body_text = response.text if response is not None else ""
        print("\n[실패] 실제 주문 HTTP 오류")
        print(f"status_code: {status_code}")
        print(body_text)
        sys.exit(1)

    except requests.RequestException as exc:
        print("\n[실패] 네트워크 요청 오류")
        print(str(exc))
        sys.exit(1)

    except Exception as exc:
        print("\n[실패] 실제 주문 실행 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()