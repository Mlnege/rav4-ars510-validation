"""새 오류 계약 시험 중 대표 네 조건을 독립 재현한다."""
import json
from pathlib import Path

import run

selected = {"healthy_empty", "can_error", "temporary", "producer_stopped"}
run.CASES = [case for case in run.CASES if case[0] in selected]
try:
  run.main()
except SystemExit as result:
  if result.code:
    raise

folder = Path(__file__).resolve().parent / "run01"
report = json.loads((folder / "results.json").read_text(encoding="utf-8"))
observations = []
for case in report["cases"]:
  if case["kind"] not in ("temporary", "producer_stopped"):
    continue
  rows = json.loads((folder / (case["kind"] + "_rows.json")).read_text(encoding="utf-8"))
  slow = [row for row in rows if row["controls_force_decel"] and row["longActive"]]
  observations.append({"kind": case["kind"], "force_decel_active_ticks": len(slow),
                       "positive_control_ticks": sum(row["accel"] > 1e-6 for row in slow),
                       "negative_control_ticks": sum(row["accel"] < -1e-6 for row in slow),
                       "deceleration_observed": any(row["accel"] < -1e-6 for row in slow),
                       "interpretation_ko": "고정 ego 합성 입력에서 감속 요청이 실제 제어 부호로 전달되는지 검사. 물리 제동 거리는 미검증."})
diagnostic = {"cases": observations, "deceleration_missing_cases": sum(not row["deceleration_observed"] for row in observations)}
(folder / "force_decel_observation.json").write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(diagnostic, ensure_ascii=False))
raise SystemExit(1 if diagnostic["deceleration_missing_cases"] else 0)
