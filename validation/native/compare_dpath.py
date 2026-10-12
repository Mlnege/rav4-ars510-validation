"""가정 센서+실제 DPath와 고정 Honda형 lead 입력을 분리 비교한다."""
import json
from pathlib import Path
from closed_loop import NativeClosedLoopPlant, Scenario
from dpath_truth_bridge import DPathTruthBridge
import openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc as mpc_module


root = Path(__file__).parent / "dpath_comparison"
results = []
for limit in (-4.0, -3.5):
  mpc_module.ACCEL_MIN = limit
  for scenario in (Scenario("stopped", lead=True, initial_speed=25, lead_speed=0, cruise_speed=25, gap=110),
                   Scenario("braking", lead=True, initial_speed=25, lead_speed=25, cruise_speed=25, gap=80, lead_brake=6)):
    scenario.name += f"_actual_dpath_mpc_{abs(limit):.1f}"
    bridge = DPathTruthBridge()
    result = NativeClosedLoopPlant(scenario, radar_bridge=bridge).run(root)
    result["isolated_mpc_min_accel_parameter"] = limit
    result["lead_aLeadTau_final"] = float(bridge.state.leadOne.aLeadTau)
    results.append(result)
    print(json.dumps(result), flush=True)
(root/"summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
