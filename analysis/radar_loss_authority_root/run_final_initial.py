"""수정된 실제 Python 파일과 새 동결 런타임에서 오류 전이를 확인한다."""
import hashlib
import importlib
import json
from pathlib import Path

import run

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
BUILD = ROOT / "work/native_sim/build_force_decel_frozen"
package = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib")
package.__path__.insert(0, str(BUILD))
mpc = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc")
planner = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_planner")
native = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.c_generated_code.acados_ocp_solver_pyx")
assert Path(mpc.__file__).resolve() == (BUILD / "long_mpc.py").resolve()
assert Path(planner.__file__).resolve() == (run.SOURCE / "openpilot/selfdrive/controls/lib/longitudinal_planner.py").resolve()
assert Path(native.__file__).resolve().parent == (BUILD / "c_generated_code").resolve()
protected = [BUILD / "long_mpc.py", *sorted((BUILD / "c_generated_code").glob("*.so*"))]
before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
run.WORK = WORK / "final"
try:
  run.main()
except SystemExit as result:
  if result.code:
    raise
after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
report = json.loads((run.WORK / "run01/results.json").read_text(encoding="utf-8"))
behavior = []
for case in report["cases"]:
  if case["first_softDisabling_s"] is None:
    continue
  rows = json.loads((run.WORK / "run01" / (case["kind"] + "_rows.json")).read_text(encoding="utf-8"))
  braking = any(row["accel"] < -1e-6 for row in rows if row["controls_force_decel"] and row["longActive"])
  expected_off = 3.45 if case["kind"] == "producer_stopped" else 3.0
  behavior.append({"kind": case["kind"], "deceleration_observed": braking,
                   "disable_timing_preserved": abs(case["first_not_longActive_s"] - expected_off) < 1e-9})
result = {"loaded_python_file": "work/native_sim/build_force_decel_frozen/long_mpc.py",
          "loaded_planner_file": "work/carrotpilot/openpilot/selfdrive/controls/lib/longitudinal_planner.py",
          "loaded_cython_file": native.__file__.split("build_force_decel_frozen/")[-1],
          "runtime_hashes_before": before, "runtime_hashes_after": after,
          "runtime_files_unchanged": before == after, "new_native_build": False,
          "force_decel_behavior_checks": behavior,
          "actual_vehicle_tx": False,
          "scope_ko": "실제 수정 Python·기존 native 바이너리 사본의 메모리 호스트 검사. 가상 시간과 고정 ego 입력이며 실차 안전성은 미검증."}
(run.WORK / "runtime_and_behavior.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"runtime_unchanged": before == after, "behavior": behavior}, ensure_ascii=False))
raise SystemExit(0 if before == after and all(row["deceleration_observed"] and row["disable_timing_preserved"] for row in behavior) else 1)
