from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import sys
import time

from run_trade_cycle import (
    load_env,
    get_now_iso,
    get_env_str,
    get_trade_symbols,
    get_state_dir,
    get_log_dir,
    analyze_market,
    save_signal_state,
    get_position_state,
    build_cycle_result,
    save_cycle_result,
    print_header,
    print_signal_summary,
    print_cycle_summary,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def get_env_int(key: str, default: int) -> int:
    raw = get_env_str(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def write_json_file(file_path: Path, payload: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_loop_status(
    *,
    started_at: str,
    current_cycle: int,
    interval_seconds: int,
    max_cycles: int,
    last_cycle_at: str,
    last_next_action: str,
    last_message: str,
    is_running: bool,
) -> Path:
    state_dir = get_state_dir()
    status_path = state_dir / "trade_loop_status.json"

    payload = {
        "service": "wavis_v4",
        "type": "trade_loop_status",
        "updated_at": get_now_iso(),
        "started_at": started_at,
        "device_id": get_env_str("DEVICE_ID", "unknown-device"),
        "app_mode": get_env_str("APP_MODE", "test"),
        "current_cycle": current_cycle,
        "interval_seconds": interval_seconds,
        "max_cycles": max_cycles,
        "last_cycle_at": last_cycle_at,
        "last_next_action": last_next_action,
        "last_message": last_message,
        "is_running": is_running,
    }

    write_json_file(status_path, payload)
    return status_path


def append_loop_history(
    *,
    cycle_no: int,
    cycle_result: dict,
) -> Path:
    log_dir = get_log_dir()
    history_path = log_dir / "trade_loop_history.log"

    history_line = (
        f"{cycle_result.get('generated_at')} | "
        f"cycle={cycle_no} | "
        f"device_id={cycle_result.get('device_id')} | "
        f"app_mode={cycle_result.get('app_mode')} | "
        f"has_position={cycle_result.get('has_position')} | "
        f"entry_candidate_count={cycle_result.get('entry_candidate_count')} | "
        f"next_action={cycle_result.get('next_action')} | "
        f"message={cycle_result.get('message')}"
    )

    with history_path.open("a", encoding="utf-8") as f:
        f.write(history_line + "\n")

    return history_path


def run_one_cycle(cycle_no: int) -> dict:
    now_str = get_now_iso()
    markets = get_trade_symbols()

    print_header(f"WAVIS v4 트레이드 루프 - {cycle_no}회차")
    print(f"실행 시각              : {now_str}")
    print(f"프로젝트 경로          : {PROJECT_ROOT}")
    print(f"DEVICE_ID              : {get_env_str('DEVICE_ID', 'unknown-device')}")
    print(f"APP_MODE               : {get_env_str('APP_MODE', 'test')}")
    print(f"대상 종목              : {', '.join(markets)}")

    signal_results = [analyze_market(market) for market in markets]
    signal_state_path = save_signal_state(now_str, signal_results)

    position_state = get_position_state()
    cycle_result = build_cycle_result(now_str, signal_results, position_state)
    cycle_state_path, cycle_history_path = save_cycle_result(cycle_result)
    loop_history_path = append_loop_history(cycle_no=cycle_no, cycle_result=cycle_result)

    print_signal_summary(signal_results)
    print_cycle_summary(cycle_result)

    print_header("저장 완료")
    print(f"신호 상태 파일          : {signal_state_path}")
    print(f"사이클 상태 파일        : {cycle_state_path}")
    print(f"사이클 이력 로그 파일   : {cycle_history_path}")
    print(f"루프 이력 로그 파일     : {loop_history_path}")

    print_header("회차 종료")
    print(f"{cycle_no}회차 판단이 완료되었습니다.")

    return cycle_result


def main() -> None:
    try:
        load_env()

        interval_seconds = get_env_int("LOOP_INTERVAL_SECONDS", 30)
        max_cycles = get_env_int("LOOP_MAX_CYCLES", 0)  # 0이면 무한 반복
        app_mode = get_env_str("APP_MODE", "test")

        started_at = get_now_iso()

        print_header("WAVIS v4 트레이드 루프 시작")
        print(f"시작 시각              : {started_at}")
        print(f"프로젝트 경로          : {PROJECT_ROOT}")
        print(f"DEVICE_ID              : {get_env_str('DEVICE_ID', 'unknown-device')}")
        print(f"APP_MODE               : {app_mode}")
        print(f"반복 간격(초)          : {interval_seconds}")
        print(f"최대 반복 횟수         : {max_cycles} (0이면 수동 종료까지 계속)")

        cycle_no = 0

        while True:
            cycle_no += 1

            cycle_result = run_one_cycle(cycle_no)

            status_path = save_loop_status(
                started_at=started_at,
                current_cycle=cycle_no,
                interval_seconds=interval_seconds,
                max_cycles=max_cycles,
                last_cycle_at=cycle_result.get("generated_at", get_now_iso()),
                last_next_action=cycle_result.get("next_action", ""),
                last_message=cycle_result.get("message", ""),
                is_running=True,
            )

            print_header("루프 상태 저장 완료")
            print(f"루프 상태 파일         : {status_path}")

            if max_cycles > 0 and cycle_no >= max_cycles:
                print_header("최종 결과")
                print(f"설정된 최대 반복 횟수({max_cycles})에 도달하여 종료합니다.")
                break

            print_header("다음 회차 대기")
            print(f"{interval_seconds}초 후 다음 회차를 실행합니다.")
            time.sleep(interval_seconds)

        save_loop_status(
            started_at=started_at,
            current_cycle=cycle_no,
            interval_seconds=interval_seconds,
            max_cycles=max_cycles,
            last_cycle_at=get_now_iso(),
            last_next_action="stopped",
            last_message="루프가 정상 종료되었습니다.",
            is_running=False,
        )

    except KeyboardInterrupt:
        print("\n")
        print_header("수동 종료")
        print("사용자가 루프 실행을 중단했습니다.")

        try:
            save_loop_status(
                started_at=get_now_iso(),
                current_cycle=0,
                interval_seconds=get_env_int("LOOP_INTERVAL_SECONDS", 30),
                max_cycles=get_env_int("LOOP_MAX_CYCLES", 0),
                last_cycle_at=get_now_iso(),
                last_next_action="stopped_by_user",
                last_message="사용자가 수동 종료했습니다.",
                is_running=False,
            )
        except Exception:
            pass

        sys.exit(0)

    except Exception as exc:
        print("\n[실패] 트레이드 루프 실행 중 오류")
        print(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()