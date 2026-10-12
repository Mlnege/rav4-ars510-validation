"""동결된 실제 신호·MPC·LongControl의 비활성 후 정지 기억 전이를 기록한다.

이 검사는 합성 서비스 입력을 쓰는 부분 계획 검사다. 헤더 보강안을 구현하거나
전체 호스트 권한, 이미지 인식, Toyota CAN 송신 및 실차 운동을 검증하지 않는다.
"""
import argparse
import csv
import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
REPO = WORK / "carrotpilot"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(WORK / "native_sim"))
from offline_io import BUILD_ROOT
from tools.ars510_validation.signal.native_signal import (
  NativeSignalHarness,
  ReplayClock,
  input_clock,
)

SOURCE_FILES = (
  "tools/ars510_validation/signal/native_signal.py",
  "tools/ars510_validation/signal/core.py",
  "openpilot/selfdrive/carrot/signal_mode.py",
  "openpilot/selfdrive/carrot/signal_assist.py",
  "openpilot/selfdrive/carrot/signal_assist_runtime.py",
  "openpilot/selfdrive/carrot/signal_start_guard.py",
  "openpilot/selfdrive/carrot/signal_stop_prepare.py",
  "openpilot/selfdrive/carrot/signal_stop_prepare_runtime.py",
  "openpilot/selfdrive/carrot/carrot_functions.py",
  "openpilot/selfdrive/controls/lib/longitudinal_planner.py",
  "openpilot/selfdrive/controls/lib/longcontrol.py",
  "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py",
)


def digest(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
  values = {name: digest(REPO / name) for name in SOURCE_FILES}
  values["offline_io.py"] = digest(WORK / "native_sim/offline_io.py")
  values["probe.py"] = digest(Path(__file__))
  return values


def native_hashes():
  return {str(path.relative_to(BUILD_ROOT)): digest(path) for path in sorted(BUILD_ROOT.rglob("*.so"))}


def run_case(directory, kind, off_seconds, resume_color, *, model_stop=False):
  """입력·기록만 감싸며 원형 계산의 인수와 반환값을 유지한다."""
  clock = ReplayClock(100.)
  rows, controls = [], []
  phase = "baseline"
  with input_clock(clock):
    h = NativeSignalHarness(directory, clock=clock, speed=0., camera_profile="ox03c10")
    touch = h.sm.touch
    update = h.control.update

    def input_touch(now):
      # 실제 Cap'n Proto 메시지와 수신 메타데이터에 명시적인 합성 상태를 넣는다.
      h.sm.valid["modelV2"] = not (phase == "off" and kind == "invalid_model_only")
      touch(now)
      if phase == "off" and kind == "cc_only_off":
        h.sm["carControl"].longActive = False
        h.sm["controlsState"].longControlState = "off"

    def record_control(*args, **kwargs):
      before = str(h.control.long_control_state)
      result = update(*args, **kwargs)
      controls.append({"plan_time": clock.now, "sample": len(controls) % 5,
                       "phase": phase, "active": bool(args[0]), "should_stop": bool(args[2].shouldStop),
                       "requested_accel": float(args[2].aTarget), "output_accel": float(result[0]),
                       "state_before": before, "state_after": str(h.control.long_control_state),
                       "pid_i": float(h.control.pid.i)})
      return result

    h.sm.touch = input_touch
    h.control.update = record_control

    def step(now, color, enabled=True, stopping=False):
      previous = len(controls)
      result = h.step(now, signal_mode=2, speed=0., color=color, enabled=enabled,
                      session="same_synthetic_housing", model_stop_distance=.1 if stopping else None)
      observation, context = h.start_runtime.read(h.sm, now)
      guard = h.start_runtime.guard
      result.update({"phase": phase, "sd_enabled": bool(h.sm["selfdriveState"].enabled),
                     "cc_enabled": bool(h.sm["carControl"].enabled),
                     "cc_long_active": bool(h.sm["carControl"].longActive),
                     "runtime_enabled": bool(context["enabled"]), "runtime_valid": bool(context["valid"]),
                     "runtime_drive": bool(context["drive"]), "observation_present": observation is not None,
                     "guard_hold": bool(guard.hold), "guard_session": guard.session,
                     "guard_pending": guard.pending, "guard_count": guard.count,
                     "guard_since": guard.since,
                     "guard_timestamp": guard.timestamp if math.isfinite(guard.timestamp) else None,
                     "guard_timestamp_valid": math.isfinite(guard.timestamp),
                     "guard_box": guard.box, "model_should_stop": bool(h.sm["modelV2"].action.shouldStop),
                     "model_valid": bool(h.sm.valid["modelV2"]),
                     "model_header_ns": int(h.sm.logMonoTime["modelV2"]),
                     "model_receive_time": h.sm.recv_time["modelV2"],
                     "long_control_state": str(h.control.long_control_state),
                     "control_min": min(sample["output_accel"] for sample in controls[previous:]),
                     "control_max": max(sample["output_accel"] for sample in controls[previous:])})
      rows.append(result)
      return result

    for index in range(100):
      step(round(100. + index * .05, 9), "red")
    baseline = rows[-1].copy()
    if not (baseline["runtime_enabled"] and baseline["runtime_valid"] and baseline["start_hold"]
            and baseline["should_stop"]):
      raise AssertionError("정상 mode2 입력에서 빨강 정지 유지 기준 상태가 성립하지 않았습니다")
    phase = "off"
    off_steps = round(off_seconds / .05)
    for index in range(off_steps):
      step(round(105. + index * .05, 9), "red", enabled=kind != "sd_cc_off")
    phase = "resume"
    resumed = round(105. + off_seconds, 9)
    for index in range(40):
      step(round(resumed + index * .05, 9), resume_color, stopping=model_stop)
    resume = [row for row in rows if row["phase"] == "resume"]
    off = [row for row in rows if row["phase"] == "off"]
    result = {
      "kind": kind, "off_seconds": off_seconds, "off_plan_ticks": off_steps,
      "resume_color": resume_color, "resume_model_stop": model_stop,
      "baseline": baseline, "first_off": off[0], "first_resume": resume[0], "last_resume": resume[-1],
      "first_resume_hold_s": next((row["time"] - resumed for row in resume if row["start_hold"]), None),
      "first_resume_release_s": next((row["time"] - resumed for row in resume if row["start_released"]), None),
      "first_positive_target_s": next((row["time"] - resumed for row in resume if row["a_target"] > 0), None),
      "first_positive_control_s": next((row["time"] - resumed for row in resume if row["control_max"] > 0), None),
      "resume_no_hold_rows": sum(not row["start_hold"] for row in resume),
      "resume_positive_target_rows": sum(row["a_target"] > 0 for row in resume),
      "resume_positive_control_rows": sum(row["control_max"] > 0 for row in resume),
      "off_all_hold": all(row["start_hold"] for row in off),
      "resume_all_hold": all(row["start_hold"] for row in resume),
      "solver_nonzero": sum(row["solver_status"] != 0 for row in rows),
      "carparams_unchanged": h.unchanged_cp(), "steps": len(rows), "control_calls": len(controls),
      "native_solver": type(h.planner.mpc.solver).__module__,
    }
  directory.mkdir(parents=True, exist_ok=True)
  for name, values in (("plans.csv", rows), ("controls.csv", controls)):
    with (directory / name).open("w", encoding="utf-8", newline="") as stream:
      writer = csv.DictWriter(stream, fieldnames=list(values[0]))
      writer.writeheader()
      writer.writerows(values)
  (directory / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
  return result


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output", type=Path, required=True)
  args = parser.parse_args()
  args.output.mkdir(parents=True, exist_ok=True)
  if not BUILD_ROOT.name.startswith("build_snapshot_"):
    raise RuntimeError("읽기 전용 native 스냅샷 경로를 지정해야 합니다")
  source_before, native_before = source_hashes(), native_hashes()
  if not native_before:
    raise RuntimeError("실제 native binary의 해시를 확인할 수 없습니다")
  started_utc, started = datetime.now(UTC).isoformat(), time.perf_counter()
  cases = []
  for kind in ("cc_only_off", "sd_cc_off", "invalid_model_only"):
    for seconds in (.05, .5):
      for color in ("red", "unknown", "green"):
        name = f"{kind}_{seconds:g}_{color}"
        cases.append(run_case(args.output / name, kind, seconds, color))
  for color in ("red", "unknown", "green"):
    cases.append(run_case(args.output / ("continuous_" + color), "continuous", .05, color))
  for kind in ("cc_only_off", "sd_cc_off"):
    cases.append(run_case(args.output / (kind + "_green_model_stop"), kind, .05, "green", model_stop=True))
  failures = []
  for case in cases:
    if case["solver_nonzero"] or not case["carparams_unchanged"]:
      failures.append(case["kind"] + ": 계산/차량 설정 불변식")
    if case["kind"] == "invalid_model_only" and not case["off_all_hold"]:
      failures.append("자료만 무효인 구간의 기존 정지 기억 불변식")
    if case["kind"] == "continuous" and case["resume_color"] in ("red", "unknown") and not case["resume_all_hold"]:
      failures.append("연속 활성 빨강/미확인 구간의 기존 정지 기억 불변식")
    if case["resume_model_stop"] and case["resume_positive_control_rows"]:
      failures.append("모델 정지 의도가 있는 재개의 양수 제어")
  report = {
    "started_utc": started_utc, "finished_utc": datetime.now(UTC).isoformat(),
    "wall_seconds": time.perf_counter() - started, "cases": cases, "failures": failures,
    "source_hashes": source_before, "source_unchanged": source_before == source_hashes(),
    "native_build": BUILD_ROOT.name, "native_hashes": native_before, "native_unchanged": native_before == native_hashes(),
    "time_contract": "합성 단조 시각 50ms 계획/계획당 가상 10ms 간격 제어 5회; 실제 벽시계 주기나 지연 시험 아님",
    "synthetic_metadata_refreshed_each_tick": True, "model_stop_and_departure_intent_explicit": True,
    "native_mpc_backend": "원형 C/Cython/acados snapshot", "longcontrol_backend": "원형 Python LongControl",
    "toyota_can_backend": "이 검사에서 미실행; Python CAN 생성/디코딩 및 실물 송신 모두 없음",
    "full_host_permission_chain_executed": False, "proposed_header_guard_implemented": False,
    "new_radar_objects_created": False, "camera_recognition_verified": False, "physical_safety_proven": False,
    "real_can_sent": False, "carinterface_init_called": False, "operating_params_writes": 0,
  }
  (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
  print(json.dumps({"cases": len(cases), "failures": failures, "source_unchanged": report["source_unchanged"],
                    "native_unchanged": report["native_unchanged"], "wall_seconds": report["wall_seconds"]}, ensure_ascii=False))
  return int(bool(failures) or not report["source_unchanged"] or not report["native_unchanged"])


if __name__ == "__main__":
  raise SystemExit(main())
