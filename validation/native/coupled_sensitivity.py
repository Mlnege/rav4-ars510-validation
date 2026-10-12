"""센서·응답 가정을 명시한 실제 ARS/native 경로의 급제동 감도를 기록한다."""
import json
import argparse
from pathlib import Path

from closed_loop import NativeClosedLoopPlant, Scenario
from radar_bridge import ArsRadarBridge
from dpath_truth_bridge import DPathTruthBridge


parser = argparse.ArgumentParser()
parser.add_argument("--bridge", choices=("ars", "truth"), default="ars")
args = parser.parse_args()
root = Path(__file__).parent / "coupled_sensitivity"
if args.bridge == "truth":
  root /= "truth"
root.mkdir(parents=True, exist_ok=True)
results = []
for cruise in (20, 25):
  for gap in (60, 80):
    scenario = Scenario(f"ars_brake_cruise_{cruise}_gap_{gap}", duration=20, lead=True,
                        initial_speed=20, lead_speed=20, cruise_speed=cruise, gap=gap,
                        event_time=7, lead_brake=5)
    plant = NativeClosedLoopPlant(scenario)
    plant.radar_bridge = ArsRadarBridge(plant.CP) if args.bridge == "ars" else DPathTruthBridge()
    result = plant.run(root)
    result["simulation_sensor"] = args.bridge
    if args.bridge == "ars":
      result["ars"] = plant.radar_bridge.summary()
    result["post_contact_trajectory_valid"] = not result["geometric_overlap"]
    results.append(result)
    print(json.dumps(result), flush=True)
(root / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
