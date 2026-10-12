"""실제 MPC의 최저 가속도 매개변수만 격리 프로세스에서 비교해 원인을 분리한다."""
import json
from pathlib import Path
from closed_loop import NativeClosedLoopPlant, Scenario
import openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc as mpc_module


root = Path(__file__).parent / "brake_limit_comparison"
results = []
for limit in (-4.0, -3.5):
  # 제어 함수·solver를 대체하지 않는다. 실제 API에 입력하는 제동 한계 매개변수 비교다.
  mpc_module.ACCEL_MIN = limit
  for base in (Scenario("stopped_front", lead=True, initial_speed=25, lead_speed=0, cruise_speed=25, gap=110),
               Scenario("front_brake", lead=True, initial_speed=25, lead_speed=25, cruise_speed=25, gap=80, lead_brake=6)):
    base.name += f"_mpc_{abs(limit):.1f}"
    result = NativeClosedLoopPlant(base).run(root)
    result["isolated_mpc_min_accel_parameter"] = limit
    results.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
(root / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
