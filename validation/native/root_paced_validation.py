"""실제 제어 계산을 시간에 맞춰 실행하고 입력·차량 응답 조건별 결과를 보존한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from closed_loop import NativeClosedLoopPlant, Scenario, WALL_CLOCK
from dpath_truth_bridge import DPathTruthBridge
from radar_bridge import ArsRadarBridge
from offline_io import BUILD_ROOT, REPO_ROOT


def source_hashes():
    paths = ["openpilot/selfdrive/controls/lib/longitudinal_planner.py",
             "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py",
             "openpilot/selfdrive/carrot/radar_motion/controller.py",
             "openpilot/selfdrive/carrot/radar/radard_dpath.py"]
    return {p: hashlib.sha256((REPO_ROOT / p).read_bytes()).hexdigest() for p in paths}


def scenario(index):
    kind = index % 6
    delay = [.0, .1, .2, .3][(index // 6) % 4]
    tau = [.05, .15, .3, .4][(index // 24) % 4]
    speed = [10., 15., 20., 25.][(index // 3) % 4]
    values = dict(name=f"case_{index:03d}", duration=30., initial_speed=speed,
                  cruise_speed=speed, actuator_delay=delay, actuator_tau=tau,
                  sensor_delay=[0., .05, .15][(index // 4) % 3], personality=index % 3)
    if kind == 0:
        values.update(initial_speed=0., cruise_speed=speed)
    elif kind in (1, 2):
        values.update(navigation_cap=30. if speed < 20 else 50.,
                      navigation_source="vturn" if kind == 1 else "route")
    elif kind in (3, 4):
        values.update(lead=True, lead_speed=speed, gap=40. + (index % 5)*20.,
                      lead_brake=3. + (index % 4), event_time=5.)
    else:
        values.update(lead=True, lead_speed=0., gap=45. + (index % 5)*20.)
    return Scenario(**values), kind


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5580.)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = WALL_CLOCK()
    meta = {"started_utc": datetime.now(timezone.utc).isoformat(),
            "planned_wall_seconds": args.seconds, "source_hashes_at_import": source_hashes(),
            "solver_build": BUILD_ROOT.name, "physical_can_transmission": False,
            "hardware_response": "assumed_delay_and_first_order_response",
            "perception_input": "synthetic_future_model_and_known_radar_fields",
            "whole_runtime_watchdog_validated": False}
    (args.out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    results, violations = [], []
    index, total_steps, late_steps = 0, 0, 0
    lateness, step_work = [], []
    while WALL_CLOCK() - start < args.seconds:
        case, kind = scenario(index)
        plant = NativeClosedLoopPlant(case)
        # 불완전한 순정 ACC 입력을 실제 ECU 데이터로 표현하지 않는다.
        if kind == 4:
            plant.radar_bridge = ArsRadarBridge(plant.CP, sensor_delay_s=case.sensor_delay,
                dropout_interval=(12., 12.6) if index % 2 else None,
                corruption_interval=(18., 18.3) if index % 3 == 0 else None)
        elif case.lead:
            plant.radar_bridge = DPathTruthBridge()
        case_start = WALL_CLOCK()
        while plant.step_index * plant.dt < case.duration:
            target = case_start + plant.step_index * plant.dt
            remaining = target - WALL_CLOCK()
            if remaining > 0:
                time.sleep(remaining)
            tardy = max(0., WALL_CLOCK()-target)
            lateness.append(tardy*1000.)
            late_steps += int(tardy > plant.dt)
            before = WALL_CLOCK()
            plant.step()
            step_work.append((WALL_CLOCK()-before)*1000.)
            total_steps += 1
        result = plant.run(args.out)
        result["case_wall_seconds"] = WALL_CLOCK()-case_start
        result["radar_input"] = "synthetic_ARS_without_ACC_witness" if kind == 4 else (
            "ideal_synthetic_point_actual_DPath" if case.lead else "no_front_target")
        if kind == 4:
            result["radar_bridge"] = plant.radar_bridge.summary()
        if kind == 5:
            lower_bound = case.initial_speed**2/(2*3.5)+case.initial_speed*case.actuator_delay
            result["stationary_ideal_stop_lower_bound_m"] = lower_bound
            result["gap_below_ideal_bound"] = case.gap < lower_bound
        bad = []
        if not result["finite"]: bad.append("nonfinite")
        if result["acc_control_decode_errors"]: bad.append("CAN_decode")
        if any(int(k) != 0 and v for k, v in result["native_status"].items()): bad.append("solver")
        if any(row[4] < -3.501 or row[4] > 2.001 for row in plant.rows): bad.append("command_limit")
        if bad: violations.append({"case": index, "violations": bad})
        results.append(result)
        elapsed = WALL_CLOCK()-start
        progress = {"started_utc": meta["started_utc"], "wall_seconds": elapsed,
                    "completed_cases": len(results), "steps": total_steps,
                    "invariant_violations": violations,
                    "overlap_cases": sum(r["geometric_overlap"] for r in results),
                    "step_lateness_p99_ms": float(np.percentile(lateness,99)),
                    "step_work_p99_ms": float(np.percentile(step_work,99)),
                    "late_over_10ms_steps": late_steps}
        (args.out/"progress.json").write_text(json.dumps(progress,indent=2),encoding="utf-8")
        (args.out/"summary.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
        print(json.dumps(progress), flush=True)
        index += 1
    final = progress | {"finished_utc": datetime.now(timezone.utc).isoformat(),
                        "completed": True, "simulation_seconds": total_steps*.01,
                        "source_hashes_at_end": source_hashes(),
                        "source_files_changed_during_run": source_hashes()!=meta["source_hashes_at_import"]}
    (args.out/"final.json").write_text(json.dumps(final,indent=2),encoding="utf-8")


if __name__ == "__main__":
    main()
