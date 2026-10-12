"""소스 준비 조건을 검사한다. ECU 식별이나 실차 안전성의 판정기는 아니다."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def revision(path):
    if not (path / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def inspect(manifest, prepared, installed):
    prepared, installed = prepared.resolve(), installed.resolve()
    isolated = all(prepared != p and not prepared.is_relative_to(p) and not p.is_relative_to(prepared)
                   for p in {installed, Path('/data/openpilot').resolve()})
    python_allowed = (3,12,3) <= tuple(sys.version_info[:3]) < (3,13,0)
    mismatches = []
    for item in manifest["patched_source_files"]:
        path = prepared / item["path"]
        if not path.is_file():
            mismatches.append(item["path"])
            continue
        digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if digest != item["sha256_lf"]:
            mismatches.append(item["path"])
    current = revision(installed)
    prepared_revision = revision(prepared)
    return {"검사범위": "격리된 오프라인 소스 준비",
            "Python": platform.python_version(), "운영체제": platform.system(),
            "CPU구조": platform.machine(),
            "격리경로확인": isolated, "Python준비조건일치": python_allowed,
            "Linux준비조건일치": platform.system() == 'Linux',
            "검증용배포상태확인": manifest.get("vehicle_deployment_allowed") is False,
            "기준소스일치": prepared_revision == manifest["carrot_source_commit"],
            "변경파일해시일치": not mismatches, "불일치파일": mismatches,
            "기존설치확인가능": current is not None,
            "기존설치기준소스일치": current == manifest["carrot_source_commit"] if current else None,
            "장치용전체빌드검증": False, "레이더ECU식별": "미확인",
            "회생제동검증": "미확인", "실차배포허용": False,
            "순정PCS_AEB실차검증": "미확인", "설치된Panda펌웨어검증": "미확인",
            "원격제어명령송신": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1]/"validation_manifest.json")
    parser.add_argument("--installed-openpilot", type=Path, default=Path("/data/openpilot"))
    parser.add_argument("--prepared-source", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = inspect(manifest, args.prepared_source, args.installed_openpilot)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(result[key] for key in ("기준소스일치", "변경파일해시일치", "격리경로확인",
                                      "Python준비조건일치", "Linux준비조건일치", "검증용배포상태확인")):
        raise SystemExit(4)


if __name__ == "__main__":
    main()
