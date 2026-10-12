"""운영 소스를 유지하고 RAV4 감속 요청 전달 후보를 별도 파일로 만든다."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work/carrotpilot"
OUT = Path(__file__).resolve().parent / "candidate_sources"

edits = [
  ("openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py", [
    ("             cutout_relief_enabled=False):", "             cutout_relief_enabled=False,\n             force_slow_decel=False):"),
    ("      v_cruise, stop_x, mode = carrot.v_cruise, carrot.stop_dist, carrot.mode\n",
     "      v_cruise, stop_x, mode = carrot.v_cruise, carrot.stop_dist, carrot.mode\n\n"
     "    if force_slow_decel:\n"
     "      # 호스트 감속 요청은 당근 목표 속도를 읽은 뒤에도 유지한다.\n"
     "      v_cruise = 0.0\n"),
  ]),
  ("openpilot/selfdrive/controls/lib/longitudinal_planner.py", [
    ("      measured_a_ego=sm['carState'].aEgo,\n",
     "      measured_a_ego=sm['carState'].aEgo,\n"
     "      # 검증 범위는 정확한 RAV4 2022의 직접 종방향 제어로 제한한다.\n"
     "      force_slow_decel=force_slow_decel and self.actuator_accel_limits is not None,\n"),
  ]),
]

if OUT.exists():
  raise RuntimeError("기존 후보 파일은 덮어쓰지 않습니다")
OUT.mkdir()
rows = []
for relative, replacements in edits:
  original = SOURCE / relative
  text = original.read_text(encoding="utf-8")
  for before, after in replacements:
    if text.count(before) != 1:
      raise RuntimeError(f"치환 범위를 확인할 수 없습니다: {relative}")
    text = text.replace(before, after)
  target = OUT / Path(relative).name
  target.write_text(text, encoding="utf-8", newline="\n")
  compile(text, str(target), "exec")
  rows.append({"path": relative, "original_sha256_raw": hashlib.sha256(original.read_bytes()).hexdigest(),
               "candidate_sha256_raw": hashlib.sha256(target.read_bytes()).hexdigest()})
(OUT / "manifest.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
print(json.dumps(rows))
