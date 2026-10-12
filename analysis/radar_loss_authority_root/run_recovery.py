"""레이더 오류 회복과 정상 PCM 재활성을 가상 시간에서 검사한다."""
import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys

import run
from whole_chain import Chain
from whole_io import Clock, clock_inputs

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
BUILD = ROOT / "work/native_sim/build_force_decel_frozen"
package = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib")
package.__path__.insert(0, str(BUILD))
mpc = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc")
planner_name = "openpilot.selfdrive.controls.lib.longitudinal_planner"
spec = importlib.util.spec_from_file_location(planner_name, run.SOURCE / "openpilot/selfdrive/controls/lib/longitudinal_planner.py")
planner = importlib.util.module_from_spec(spec)
sys.modules[planner_name] = planner
spec.loader.exec_module(planner)
assert Path(mpc.__file__).resolve() == (BUILD / "long_mpc.py").resolve()
protected = [BUILD / "long_mpc.py", Path(planner.__file__), *sorted((BUILD / "c_generated_code").glob("*.so*")),
             run.LAB / "work/safety_validation/libsafety_download_native.so"]
before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
folder = WORK / "recovery"
if folder.exists():
  raise RuntimeError("기존 회복 결과는 덮어쓰지 않습니다")
folder.mkdir()
results = []
with run.quiet_c_stdout(), run.hide_stderr(), contextlib.redirect_stdout(io.StringIO()):
  for kind, fault_ticks in (("recover_before_disable", 100), ("recover_after_disable_pcm_restart", 320)):
    clock = Clock()
    with clock_inputs(clock):
      chain = Chain(clock)
      warm = chain.warm().copy()
      begin = len(chain.rows)
      start = clock.now + .01
      total = fault_ticks + 180
      for index in range(total):
        clock.now = start + index * .01
        fault = index < fault_ticks
        # 오래 지속된 오류 뒤에는 정상 PCM off/on 수신 전까지 재활성하지 않는다.
        engaged = not (kind == "recover_after_disable_pcm_restart" and fault_ticks + 100 <= index < fault_ticks + 120)
        chain.step(engaged=engaged, radar_valid=not fault,
                   radar_error="radarUnavailableTemporary" if fault else None)
      rows = chain.rows[begin:]
      recovery = rows[fault_ticks:]
      checks = {
        "normal_initial_enable": warm["enabled"] and warm["longActive"],
        "cp_unavailable_preserved": bool(chain.cp.radarUnavailable),
        "deceleration_during_fault": any(row["accel"] < -.1 for row in rows[:fault_ticks] if row["longActive"]),
        "no_permission_shortcut": chain.permission.shortcut_controls_true_calls == 0,
        "native_solution_success": all(row["native_solver_status"] == 0 for row in rows),
        "no_physical_init_or_tx": not chain.physical.actual_init_executed,
      }
      if fault_ticks < 300:
        checks["healthy_recovers_without_disabling"] = all(row["longActive"] for row in rows)
        checks["force_decel_clears"] = not recovery[-1]["controls_force_decel"]
        checks["normal_cruise_plan_returns"] = recovery[-1]["plan_aTarget"] > 0.0
      else:
        checks["healthy_alone_does_not_reengage"] = all(not row["longActive"] for row in recovery[:120])
        checks["normal_pcm_off_on_reengages"] = recovery[-1]["longActive"]
        checks["force_decel_clears"] = not recovery[-1]["controls_force_decel"]
      results.append({"kind": kind, "ticks": len(rows), "checks": checks,
                      "failures": [key for key, value in checks.items() if not value],
                      "cp_unavailable": bool(chain.cp.radarUnavailable),
                      "first_disabled_s": next((i * .01 for i, row in enumerate(rows) if not row["longActive"]), None),
                      "final_longActive": recovery[-1]["longActive"],
                      "final_plan_aTarget": recovery[-1]["plan_aTarget"]})
      (folder / (kind + "_rows.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
result = {"cases": results, "source_and_native_before": before, "source_and_native_after": after,
          "files_unchanged": before == after, "actual_vehicle_tx": False,
          "virtual_time": True, "fixed_ego_mps": 15.0, "native_rebuilt": False,
          "scope_ko": "건강 합성 빈 lead·고정 ego의 오류 회복/정상 PCM 상태 전이. 실제 차량 정지·재출발·PCS/회생은 미검증."}
(folder / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"cases": results, "files_unchanged": before == after}, ensure_ascii=False))
raise SystemExit(1 if before != after or any(case["failures"] for case in results) else 0)
