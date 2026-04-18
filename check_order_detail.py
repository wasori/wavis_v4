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


def get_state_dir() -> Path:
    state_dir = PROJECT_ROOT / get_env_str("STATE_DIR", "state")
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_log_dir() -> Path:
    log_dir = PROJECT_ROOT / get_env_str("LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_latest_order_response_path() -> Path:
    return get_state_dir() / "latest_order_response.json"


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
        result["reason"] = "APP_MODE가 live가 아니므로 주문 조회가 차단됩니다."
        return result

    if engine_lock is None:
        result["reason"] = "engine_lock.json 파일이 없어 주문 조회가 차단됩니다."
        return result

    if not bool(engine_lock.get("lock_enabled", True)):
        result["reason"] = "engine lock이 비활성화되어 있어 주문 조회가 차단됩니다."
        return result

    active_live_device = engine_lock.get("active_live_device")
    if active_live_device is None:
        result["reason"] = "활성 실거래 장치가 지정되지 않아 주문 조회가 차단됩니다."
        return result

    if active_live_device != device_id:
        result["reason"] = (
            f"현재 장치({device_id})가 활성 실거래 장치({active_live_device})가 아니므로 "
            "주문 조회가 차단됩니다."
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
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def resolve_order_uuid() -> str:
    env_order_uuid = get_env_str("ORDER_UUID", "")
    if env_order_uuid:
        return env_order_uuid

    latest_order_path = get_latest_order_response_path()
    latest_order_data = read_json_file(latest_order_path)

    if latest_order_data is None:
        return ""

    response_data = latest_order_data.get("response", {})
    return str(response_data.get("uuid", "")).strip()


def request_order_detail(order_uuid: str) -> dict[str, Any]:
    params = {"uuid": order_uuid}
    headers = make_auth_headers(query_params=params)

    response = requests.get(
        f"{BASE_URL}/v1/order",
        params=params,
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("주문 상세 조회 응답 형식이 올바르지 않습니다.")

    return data


def save_order_detail(order_uuid: str, response_data: dict[str, Any]) -> tuple[Path, Path]:
    state_dir = get_state_dir()
    log_dir = get_log_dir()

    now_str = datetime.now().astimezone().isoformat(timespec="seconds")

    latest_detail_path = state_dir / "latest_order_detail.json"
    history_path = log_dir / "order_detail_history.log"

    state_payload = {
        "service": "wavis_v4",
        "type": "latest_order_detail",
        "saved_at": now_str,
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "app_mode": get_env_str("APP_MODE", "test"),
        "order_uuid": order_uuid,
        "response": response_data,
    }

    latest_detail_path.write_text(
        json.dumps(state_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    history_line = (
        f"{now_str} | "
        f"uuid={response_data.get('uuid', '-')} | "
        f"market={response_data.get('market', '-')} | "
        f"side={response_data.get('side', '-')} | "
        f"ord_type={response_data.get('ord_type', '-')} | "
        f"state={response_data.get('state', '-')} | "
        f"price={response_data.get('price', '-')} | "
        f"avg_price={response_data.get('avg_price', '-')} | "
        f"executed_volume={response_data.get('executed_volume', '-')}"
    )

    with history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return latest_detail_path, history_path


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


def print_order_detail(data: dict[str, Any]) -> None:
    print_header("주문 상세 정보")
    print(f"uuid             : {data.get('uuid')}")
    print(f"identifier       : {data.get('identifier')}")
    print(f"market           : {data.get('market')}")
    print(f"side             : {data.get('side')}")
    print(f"ord_type         : {data.get('ord_type')}")
    print(f"state            : {data.get('state')}")
    print(f"created_at       : {data.get('created_at')}")
    print(f"price            : {data.get('price')}")
    print(f"avg_price        : {data.get('avg_price')}")
    print(f"volume           : {data.get('volume')}")
    print(f"remaining_volume : {data.get('remaining_volume')}")
    print(f"executed_volume  : {data.get('executed_volume')}")
    print(f"locked           : {data.get('locked')}")
    print(f"paid_fee         : {data.get('paid_fee')}")
    print(f"trades_count     : {data.get('trades_count')}")


def main() -> None:
    try:
        load_env()

        order_uuid = resolve_order_uuid()

        print_header("WAVIS v4 주문 상세 조회")
        print(f"실행 시각            : {datetime.now().astimezone().isoformat(timespec='seconds')}")
        print(f"프로젝트 경로        : {PROJECT_ROOT}")
        print(f".env 존재 여부       : {ENV_PATH.exists()}")
        print(f"DEVICE_ID            : {get_env_str('DEVICE_ID', 'unknown-device')}")
        print(f"APP_MODE             : {get_env_str('APP_MODE', 'test')}")
        print(f"조회 주문 UUID       : {order_uuid or '없음'}")
        print(f"latest_order_response : {get_latest_order_response_path()}")

        guard_result = evaluate_live_order_guard()
        print_guard_result(guard_result)

        if not guard_result["allow_live_order"]:
            print_header("최종 결과")
            print("주문 상세 조회가 차단되었습니다.")
            print("현재 장치는 실거래 허용 조건을 만족하지 않습니다.")
            sys.exit(1)

        if not order_uuid:
            print_header("최종 결과")
            print("조회할 주문 UUID가 없습니다.")
            print(".env 의 ORDER_UUID 를 넣거나 실제 주문 후 다시 실행해라.")
            sys.exit(1)

        response_data = request_order_detail(order_uuid)
        print_order_detail(response_data)

        latest_detail_path, history_path = save_order_detail(order_uuid, response_data)

        print_header("조회 결과 저장 완료")
        print(f"최신 주문 상세 파일  : {latest_detail_path}")
        print(f"주문 상세 이력 로그  : {history_path}")

        print_header("최종 결과")
        print("주문 UUID 기준 상세 조회가 완료되었습니다.")

    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        body_text = response.text if response is not None else ""
        print("\n[실패] 주문 상세 조회 HTTP 오류")
        print(f"status_code: {status_code}")
        print(body_text)
        sys.exit(1)

    except requests.RequestException as exc:
        print("\n[실패] 네트워크 요청 오류")
        print(str(exc))
        sys.exit(1)

    except Exception as exc:
        print("\n[실패] 주문 상세 조회 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()