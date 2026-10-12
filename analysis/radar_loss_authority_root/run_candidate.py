"""격리된 두 Python 후보 파일만 로드하고 기존 native 바이너리로 검사한다."""
import hashlib
import importlib
import json
from pathlib import Path

import run

ROOT = Path(__file__).resolve().parent
folder = ROOT / "candidate"
if folder.exists():
  raise RuntimeError("기존 후보 실행 결과는 덮어쓰지 않습니다")
folder.mkdir()
overlays = []
for module_name, filename in (
  ("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc", "long_mpc.py"),
  ("openpilot.selfdrive.controls.lib.longitudinal_planner", "longitudinal_planner.py"),
):
  module = importlib.import_module(module_name)
  path = ROOT / "candidate_sources" / filename
  content = path.read_text(encoding="utf-8")
  # 원형 네이티브 경로를 유지하며 별도 후보의 전체 Python 본문을 로드한다.
  exec(compile(content, str(path), "exec"), module.__dict__)
  overlays.append({"module": module_name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
run.WORK = folder
try:
  run.main()
except SystemExit as result:
  if result.code:
    raise

result_folder = folder / "run01"
report = json.loads((result_folder / "results.json").read_text(encoding="utf-8"))
observations = []
for case in report["cases"]:
  rows = json.loads((result_folder / (case["kind"] + "_rows.json")).read_text(encoding="utf-8"))
  slow = [row for row in rows if row["controls_force_decel"] and row["longActive"]]
  first_negative = next((index * .01 for index, row in enumerate(rows) if row["accel"] < -1e-6), None)
  observations.append({"kind": case["kind"], "force_decel_active_ticks": len(slow),
                       "positive_control_ticks_during_force_decel": sum(row["accel"] > 1e-6 for row in slow),
                       "negative_control_ticks_during_force_decel": sum(row["accel"] < -1e-6 for row in slow),
                       "first_negative_control_s": first_negative,
                       "first_not_longActive_s": case["first_not_longActive_s"],
                       "negative_accel_can": case["negative_accel_can"],
                       "positive_accel_can": case["positive_accel_can"],
                       "deceleration_missing": bool(slow) and not any(row["accel"] < -1e-6 for row in slow)})
diagnostic = {"python_candidate_overlays": overlays, "source_on_disk_modified": False,
              "new_native_build": False, "actual_vehicle_tx": False,
              "cases": observations,
              "deceleration_missing_cases": sum(row["deceleration_missing"] for row in observations)}
(folder / "candidate_observation.json").write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(diagnostic, ensure_ascii=False))
raise SystemExit(1 if diagnostic["deceleration_missing_cases"] else 0)
