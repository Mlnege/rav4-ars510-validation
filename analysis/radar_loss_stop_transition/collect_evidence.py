"""동결된 모의 결과를 읽어 변곡점과 현재 파일 지문만 모은다. 계산 알고리즘은 실행하지 않는다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
SCOPE = Path(__file__).resolve().parent

SOURCE_RANGES = {
  "work/carrotpilot/opendbc_repo/opendbc/car/toyota/carcontroller.py": [(81, 81), (176, 193), (201, 211), (233, 263)],
  "work/carrotpilot/opendbc_repo/opendbc/car/toyota/carstate.py": [(93, 97), (166, 171)],
  "work/carrotpilot/opendbc_repo/opendbc/car/toyota/interface.py": [(133, 147)],
  "work/carrotpilot/opendbc_repo/opendbc/car/toyota/values.py": [(264, 270)],
  "work/carrotpilot/openpilot/selfdrive/controls/lib/longcontrol.py": [(25, 63), (153, 175)],
  "work/carrotpilot/openpilot/selfdrive/carrot/carrot_functions.py": [(508, 508), (572, 647)],
  "work/carrotpilot/openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py": [(384, 406), (426, 426), (488, 491)],
  "work/carrotpilot/openpilot/selfdrive/controls/lib/longitudinal_planner.py": [(357, 369), (393, 420), (486, 499)],
  "work/carrotpilot/openpilot/selfdrive/controls/lib/drive_helpers.py": [(109, 125)],
  "work/carrotpilot/openpilot/selfdrive/carrot/radar/radard_dpath.py": [(103, 107)],
  "work/carrotpilot/openpilot/selfdrive/carrot/radar_motion/controller.py": [(548, 614)],
  "work/carrotpilot/openpilot/selfdrive/carrot/radar_motion/primary.py": [(790, 802)],
  "work/carrotpilot/openpilot/selfdrive/controls/controlsd.py": [(156, 184)],
  "work/carrotpilot/openpilot/selfdrive/selfdrived/selfdrived.py": [(426, 446)],
  "work/carrotpilot/openpilot/selfdrive/selfdrived/events.py": [(940, 949), (1010, 1019)],
  "work/carrotpilot/openpilot/selfdrive/selfdrived/state.py": [(7, 10), (39, 63), (74, 85), (107, 112)],
  "work/carrotpilot/openpilot/selfdrive/carrot/signal_start_guard.py": [(144, 165)],
  "work/native_sim/closed_loop.py": [(137, 149), (231, 246)],
  "work/native_sim/inspect_stop.py": [(43, 53)],
}

RESULT_FILES = [
  "work/native_sim/stop_inspection/summary.json",
  "work/native_sim/stop_inspection/observation.csv",
  "work/native_sim/stop_inspection/ars_near_stop.csv",
  "work/native_sim/witness_sensitivity/summary.json",
  "work/native_sim/witness_sensitivity/stopped_full_near_False.csv",
  "work/native_sim/witness_sensitivity/stopped_full_near_True.csv",
  "work/signal_validation/native_signal_can/summary.json",
  "work/signal_validation/native_signal_can/stopped_red_green_go_can_control.csv",
  "work/signal_validation/native_signal_can_fixed/summary.json",
  "work/signal_validation/native_signal_can_fixed/stopped_red_green_go_can_control.csv",
  "work/signal_host_can_integration/frozen_results.json",
  "work/signal_host_can_integration/RESULTS_KO.md",
  "work/paired_host_policy_integration/final_observation/frozen_results.json",
]


def load_json(relative):
  return json.loads((WORKSPACE / relative).read_text(encoding="utf-8"))


def csv_rows(relative):
  with (WORKSPACE / relative).open(encoding="utf-8", newline="") as stream:
    reader = csv.DictReader(stream)
    return reader.fieldnames, list(reader)


def selected_rows(relative, time_field, targets, *, normalize_start=False):
  fields, rows = csv_rows(relative)
  origin = float(rows[0][time_field]) if normalize_start else 0.0
  picked = []
  for target in targets:
    row = dict(min(rows, key=lambda value: abs(float(value[time_field]) - origin - target)))
    row[time_field] = round(float(row[time_field]) - origin, 9)
    picked.append(row)
  return {"path": relative, "csv_columns": fields, "row_count": len(rows),
          "time_origin": "합성 시험 첫 행을 0초로 표시" if normalize_start else "원래 합성 경과초",
          "rows": picked}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, default=SCOPE / "frozen_read03")
  args = parser.parse_args()
  destination = args.output_dir.resolve()
  if destination == SCOPE or SCOPE not in destination.parents:
    raise ValueError("출력은 허용된 정지·재출발 조사 폴더의 새 하위 폴더여야 한다.")
  destination.mkdir(parents=True, exist_ok=False)

  before = {}
  ranges = {}
  for relative in [*SOURCE_RANGES, *RESULT_FILES]:
    data = (WORKSPACE / relative).read_bytes()
    before[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if relative in SOURCE_RANGES:
      lines = data.decode("utf-8").splitlines()
      ranges[relative] = [{"line": number, "text": lines[number - 1]}
                          for low, high in SOURCE_RANGES[relative]
                          for number in range(low, high + 1)]

  near = load_json(RESULT_FILES[0])
  near_keys = ["name", "duration", "initial_speed", "cruise_speed", "gap", "lead_speed", "model_intent",
               "actuator_delay", "actuator_tau", "sensor_delay", "steps", "model_steps", "native_status",
               "first_geometric_overlap_s", "first_unsafe_clearance_s", "acc_control_messages",
               "acc_control_decode_errors", "native_solver"]
  near_summary = {key: near[key] for key in near_keys}
  near_summary["ars"] = {"stock_ACC_target_simulated": near["ars"]["stock_ACC_target_simulated"],
                         "records": near["ars"]["adapter"]["records"],
                         "crc_failures": near["ars"]["adapter"]["crc_failures"]}
  near_summary["post_contact_numbers_used_as_valid_motion"] = False

  witness = []
  for case in load_json("work/native_sim/witness_sensitivity/summary.json"):
    if case["name"].startswith("stopped_"):
      witness.append({key: case.get(key) for key in ["name", "first_geometric_overlap_s", "first_unsafe_clearance_s",
                                                     "post_contact_trajectory_valid"]} | {
        "minimum_gap_before_or_without_contact": case["minimum_gap"] if case["post_contact_trajectory_valid"] else None,
        "final_speed_without_contact": case["final_speed"] if case["post_contact_trajectory_valid"] else None,
        "witness_mode": case["ars"]["witness_mode"], "retain_near": case["ars"]["retain_near"],
        "check_byte": case["ars"]["check_byte"], "vehicle_tx": case["ars"]["real_vehicle_tx_count"]})

  signal = {}
  for folder in ["native_signal_can", "native_signal_can_fixed"]:
    summary = load_json(f"work/signal_validation/{folder}/summary.json")
    signal[folder] = {"stopped_red_green_go": next(row for row in summary["cases"] if row["case"] == "stopped_red_green_go"),
                      "execution_source_hashes_if_recorded": summary.get("source_hashes"),
                      "real_can_sent": summary["real_can_sent"],
                      "panda_permission_verified": summary["panda_permission_verified"]}

  host = load_json("work/signal_host_can_integration/frozen_results.json")
  host_cases = []
  for case in host["cases"]:
    if case["kind"] == "gas" and case["order"] == "before":
      # 103.50은 이 합성 시험의 명시한 기준 사건이다. 실물 로그의 절대 시각을 읽지 않는다.
      row = {key: case[key] for key in ["kind", "phase_ms", "order", "positive_allowed_can_count"]}
      for key in ["first_hold_removed", "first_hold_restored_after_gas", "first_positive_control"]:
        value = case.get(key)
        row[key + "_relative_to_fixture_event_s"] = None if value is None else round(value - 103.5, 9)
      host_cases.append(row)

  paired = load_json("work/paired_host_policy_integration/final_observation/frozen_results.json")
  paired_count_keys = ["host_ticks", "host_enabled", "host_active", "longActive", "c_controls_true_ticks", "c_long_true_ticks",
                       "nonzero_accel_requests", "native_mpc_models", "radar_lead_consumed_models", "points", "records"]
  output = {"scope_ko": "기존 동결 파일 읽기와 현재 지문 관찰. 새 모의 실행, 새 회귀 검사 또는 실차 검증이 아니다.",
            "near_summary": near_summary, "near_observation": selected_rows(RESULT_FILES[1], "time_s", [7.85, 8.5, 8.6, 8.7, 9.05]),
            "near_control": selected_rows(RESULT_FILES[2], "t_s", [8.0, 8.5, 8.6, 8.7, 9.0, 9.05, 9.15, 9.8, 10.3]),
            "witness_summary": witness, "signal_summary": signal,
            "signal_before": selected_rows(RESULT_FILES[7], "time", [2.13, 2.15, 2.16, 2.28, 2.31], normalize_start=True),
            "signal_fixed": selected_rows(RESULT_FILES[9], "time", [2.13, 2.15, 2.16, 2.28, 2.31], normalize_start=True),
            "host_natural_gas_cases": host_cases,
            "paired_recorded_off_counts": {key: paired["counts"][key] for key in paired_count_keys},
            "current_source_equals_original_near_execution_proven": False,
            "new_native_simulation_executed": False, "physical_can_sent": False}
  for relative, item in before.items():
    item["unchanged_during_read"] = hashlib.sha256((WORKSPACE / relative).read_bytes()).hexdigest() == item["sha256"]
  for name, content in [("evidence.json", output), ("fingerprints.json", before), ("current_source_excerpt.json", ranges)]:
    (destination / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps({"준비": "완료", "기존 파일 불변": all(item["unchanged_during_read"] for item in before.values()),
                    "읽은 파일 수": len(before), "새 모의 실행": False}, ensure_ascii=False))


if __name__ == "__main__":
  main()
