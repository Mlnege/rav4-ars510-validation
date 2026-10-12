"""수정 전후 원형 Python 소스와 동일한 native 수식을 별도 프로세스로 비교한다.

가상 센서·차량 응답은 폐루프 시험 입력이다. 실행 중인 solver 파일은 변경하지
않으며, 원형 snapshot과 수정 snapshot을 각각 고정 경로로 선택한다.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
UPDATED_BUILD = HERE / "build_snapshot_b0a5c630260ad76b"
BASELINE_BUILD = HERE / "baseline_build"


def worker(args):
  from offline_io import prepare
  prepare(solver_overlay=True)
  if args.variant == "baseline":
    import openpilot.selfdrive.controls.lib as controls_package
    controls_package.__path__.insert(0, str(BASELINE_BUILD))
  from closed_loop import NativeClosedLoopPlant, Scenario
  from dpath_truth_bridge import DPathTruthBridge
  import openpilot.selfdrive.controls.lib.longitudinal_planner as planner_module
  import openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc as mpc_module
  from opendbc.car import gen_empty_fingerprint
  from opendbc.car.toyota.interface import CarInterface
  from opendbc.car.toyota.values import CAR

  scenario = Scenario(args.case + "_" + args.bridge + "_" + args.variant, duration=30,
                      lead=True, initial_speed=25, lead_speed=0 if args.case == "stopped" else 25,
                      cruise_speed=25, gap=110 if args.case == "stopped" else 80,
                      lead_brake=0 if args.case == "stopped" else 6)
  if args.vehicle != "TOYOTA_RAV4_TSS2_2022":
    scenario.name += "_" + args.vehicle
  CP = CarInterface.get_params(CAR(args.vehicle), gen_empty_fingerprint(), [], True, False, False)
  plant = NativeClosedLoopPlant(scenario, CP=CP)
  if args.bridge == "truth":
    plant.radar_bridge = DPathTruthBridge()
  else:
    from radar_bridge import ArsRadarBridge
    plant.radar_bridge = ArsRadarBridge(plant.CP)
  result = plant.run(args.out)
  result["comparison_variant"] = args.variant
  result["car_fingerprint"] = plant.CP.carFingerprint
  result["simulation_sensor"] = args.bridge
  result["python_source_files"] = {
    name: {"path": str(Path(module.__file__).resolve()),
           "sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
    for name, module in (("planner", planner_module), ("mpc", mpc_module))
  }
  result["native_build_root"] = os.environ["CARROT_VALIDATION_BUILD"]
  result["actuator_accel_limits"] = getattr(plant.planner, "actuator_accel_limits", None)
  result["mpc_minimum_accel"] = getattr(plant.planner.mpc, "minimum_accel", mpc_module.ACCEL_MIN)
  result["final_mpc_min_parameters"] = plant.planner.mpc.params[:, 0].tolist()
  result["lead_aLeadTau_final"] = float(plant.sm["radarState"].leadOne.aLeadTau)
  result["post_contact_trajectory_valid"] = not result["geometric_overlap"]
  if hasattr(plant.radar_bridge, "metrics"):
    result["ars_metrics"] = dict(plant.radar_bridge.metrics)
  args.out.mkdir(parents=True, exist_ok=True)
  (args.out / (scenario.name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
  print(json.dumps(result), flush=True)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--worker", action="store_true")
  parser.add_argument("--variant", choices=("baseline", "updated"))
  parser.add_argument("--bridge", choices=("truth", "ars"))
  parser.add_argument("--case", choices=("stopped", "braking"))
  parser.add_argument("--vehicle", default="TOYOTA_RAV4_TSS2_2022")
  parser.add_argument("--default-regression", action="store_true")
  parser.add_argument("--out", type=Path, default=HERE / "paired_results")
  args = parser.parse_args()
  if args.worker:
    worker(args)
    return
  results = []
  if args.default_regression:
    import numpy as np
    for vehicle in ("TOYOTA_RAV4_TSS2_2023", "TOYOTA_CHR_TSS2"):
      rows = []
      for variant in ("baseline", "updated"):
        env = os.environ.copy()
        env["CARROT_VALIDATION_BUILD"] = str(BASELINE_BUILD if variant == "baseline" else UPDATED_BUILD)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        subprocess.run([sys.executable, str(Path(__file__)), "--worker", "--variant", variant,
                        "--bridge", "truth", "--case", "braking", "--vehicle", vehicle,
                        "--out", str(args.out)], env=env, check=True)
        name = "braking_truth_" + variant + "_" + vehicle
        results.append(json.loads((args.out / (name + ".json")).read_text()))
        rows.append(np.loadtxt(args.out / (name + ".csv"), delimiter=",", skiprows=1))
      np.testing.assert_array_equal(*rows)
      print(json.dumps({"vehicle": vehicle, "complete_dynamic_rows_identical": True,
                        "rows": len(rows[0]), "columns": rows[0].shape[1]}), flush=True)
    (args.out / "default_regression.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return
  for variant in ("baseline", "updated"):
    for bridge in ("truth", "ars"):
      for case in ("stopped", "braking"):
        env = os.environ.copy()
        env["CARROT_VALIDATION_BUILD"] = str(BASELINE_BUILD if variant == "baseline" else UPDATED_BUILD)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        subprocess.run([sys.executable, str(Path(__file__)), "--worker", "--variant", variant,
                        "--bridge", bridge, "--case", case, "--out", str(args.out)], env=env, check=True)
        results.append(json.loads((args.out / (case + "_" + bridge + "_" + variant + ".json")).read_text()))
  (args.out / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
  main()
