"""완전·누락·idle·오래된 ACC 합성 관측과 근거리 opt-in을 실제 경로로 비교한다."""
import json
from pathlib import Path

from closed_loop import NativeClosedLoopPlant, Scenario
from witness_bridge import AccWitnessRadarBridge


root = Path(__file__).parent / "witness_sensitivity"
root.mkdir(exist_ok=True)
results = []
cases = [("stopped", "missing", False), ("stopped", "missing", True), ("stopped", "full", False),
         ("stopped", "full", True), ("braking", "full", False), ("braking", "missing", False),
         ("braking", "idle", False), ("braking", "stale", False)]
for case, witness, near in cases:
  scenario = (Scenario(f"stopped_{witness}_near_{near}", duration=20, lead=True, initial_speed=25,
                       lead_speed=0, cruise_speed=25, gap=110) if case == "stopped" else
              Scenario(f"braking_{witness}_near_{near}", duration=20, lead=True, initial_speed=20,
                       lead_speed=20, cruise_speed=20, gap=60, event_time=7, lead_brake=5))
  plant = NativeClosedLoopPlant(scenario)
  plant.radar_bridge = AccWitnessRadarBridge(plant.CP, witness_mode=witness, retain_near=near)
  result = plant.run(root)
  result["ars"] = plant.radar_bridge.summary()
  result["post_contact_trajectory_valid"] = not result["geometric_overlap"]
  results.append(result)
  print(json.dumps({key: result[key] for key in ("name", "minimum_gap", "geometric_overlap", "final_speed",
                                              "first_geometric_overlap_s", "native_status", "acc_control_decode_errors")}), flush=True)
(root / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
