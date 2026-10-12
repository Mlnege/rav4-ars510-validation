import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work" / "carrotpilot"
OUT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
  return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
  manifest = json.loads((ROOT / "work/release_repo/validation_manifest.json").read_text(encoding="utf-8"))
  source_checks = []
  for entry in manifest["patched_source_files"]:
    content = (SOURCE / entry["path"]).read_bytes().replace(b"\r\n", b"\n")
    actual = hashlib.sha256(content).hexdigest()
    source_checks.append({"path": entry["path"], "sha256_lf": actual, "matches_r9": actual == entry["sha256_lf"]})
  windows = {
    "openpilot/selfdrive/carrot/radar/radarcan.py": [(41, 53), (87, 101)],
    "openpilot/selfdrive/carrot/radar/radard_dpath.py": [(90, 120), (145, 151), (164, 171)],
    "openpilot/selfdrive/selfdrived/selfdrived.py": [(424, 468)],
    "openpilot/selfdrive/selfdrived/events.py": [(920, 927), (940, 948), (1010, 1022)],
    "openpilot/selfdrive/selfdrived/state.py": [(1, 150)],
    "openpilot/selfdrive/controls/controlsd.py": [(155, 168), (430, 439)],
    "openpilot/selfdrive/controls/lib/longitudinal_planner.py": [(159, 169), (222, 231)],
  }
  excerpts = {}
  for relative, spans in windows.items():
    path = SOURCE / relative
    lines = path.read_text(encoding="utf-8").splitlines()
    excerpts[relative] = {
      "sha256_raw": digest(path),
      "ranges": [{"first_line": first, "last_line": min(last, len(lines)),
                  "text": "\n".join(lines[first - 1:last])} for first, last in spans],
    }
  result = {
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "kind": "source_read_and_fingerprint_only",
    "new_dynamic_tests": 0,
    "vehicle_or_socket_execution": False,
    "r9_source_files": len(source_checks),
    "source_mismatches": [entry["path"] for entry in source_checks if not entry["matches_r9"]],
    "source_checks": source_checks,
    "excerpts": excerpts,
    "review_notes_ko": [
      "정상 빈 트랙과 오류 표시는 서로 다른 입력 계약이다.",
      "radarcan은 오류가 있으면 liveTracks Event.valid=False로 발행한다.",
      "DPath는 liveTracks의 valid 및 수신 건강 판정을 포함한 SubMaster.all_checks를 radarState.valid로 전달한다.",
      "SelfdriveD는 invalid radarState의 오류 종류를 분기하며 CP.radarUnavailable로 이를 무시하지 않는다.",
      "canError는 즉시 해제, radarFault/temporaryUnavailable/commIssue는 명목 3초 soft-disable 경로다.",
      "softDisabling의 제어 활성 상태와 Controls.forceDecel의 감속 요청을 함께 봐야 한다.",
      "LongitudinalPlanner는 forceDecel이면 내부 크루즈 목표를 0으로 설정한다. 물리 급제동 보장은 아니다.",
      "원형 정상 producer에서 오류True/validTrue는 계약 불일치다. 별도 합성 시험을 실차 결함으로 해석하지 않는다.",
    ],
  }
  (OUT / "source_contract_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps({"kind": result["kind"], "source_files": len(source_checks), "mismatches": result["source_mismatches"]}, ensure_ascii=False))
  if result["source_mismatches"]:
    raise SystemExit(1)


if __name__ == "__main__":
  main()
