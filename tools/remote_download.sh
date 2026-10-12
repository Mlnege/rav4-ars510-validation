#!/usr/bin/env bash
# 차량 설치를 변경하지 않고 고정 버전의 검증 소스와 의존성을 별도 공간에 준비한다.
set -euo pipefail
PACKAGE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TARGET="${PWD}/rav4-validation-lab"
INSTALLED="/data/openpilot"
PYTHON_BIN="python3"
INSTALL_DEPS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --destination|--installed-openpilot|--python)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { printf '옵션 값이 필요합니다: %s\n' "$1" >&2; exit 2; }
      case "$1" in
        --destination) TARGET="$2";;
        --installed-openpilot) INSTALLED="$2";;
        --python) PYTHON_BIN="$2";;
      esac
      shift 2;;
    --install-deps) INSTALL_DEPS=1; shift;;
    *) printf '지원하지 않는 옵션: %s\n' "$1" >&2; exit 2;;
  esac
done
for PROGRAM in git "$PYTHON_BIN" sha256sum; do
  command -v "$PROGRAM" >/dev/null || { printf '필요한 실행 파일이 없습니다: %s\n' "$PROGRAM" >&2; exit 3; }
done
cd -- "$PACKAGE_ROOT"
sha256sum --check SHA256SUMS
"$PYTHON_BIN" - "$PACKAGE_ROOT" "$TARGET" "$INSTALLED" <<'PY'
import json, os, platform, sys
from pathlib import Path
package, target, installed = map(lambda x: Path(x).resolve(), sys.argv[1:])
version = sys.version_info
if not ((3,12,3) <= tuple(version[:3]) < (3,13,0)):
    raise SystemExit('Python 3.12.3 이상, 3.13 미만이 필요합니다. 운영 가상환경에 패키지를 설치하지 마세요.')
if platform.system() != 'Linux':
    raise SystemExit('이 원격 준비 명령은 Linux용입니다. Windows는 별도 적용 문서를 사용하세요.')
for protected in {installed, Path('/data/openpilot').resolve()}:
    if target == protected or target.is_relative_to(protected) or protected.is_relative_to(target):
        raise SystemExit('검증 공간은 기존 openpilot 설치와 완전히 다른 경로여야 합니다.')
if target == package or package.is_relative_to(target) or target.is_relative_to(package):
    raise SystemExit('검증 공간은 다운로드한 배포 저장소와 다른 경로여야 합니다.')
if target.exists() and not target.is_dir():
    raise SystemExit('대상 경로가 폴더가 아닙니다.')
if target.exists() and any(target.iterdir()):
    raise SystemExit('대상 폴더가 비어 있지 않습니다. 기존 파일을 덮어쓰지 않습니다.')
if not (package/'validation_manifest.json').is_file():
    raise SystemExit('검증 배포 manifest가 없습니다.')
manifest=json.loads((package/'validation_manifest.json').read_text())
if manifest.get('vehicle_deployment_allowed') is not False:
    raise SystemExit('실차 배포 허용 상태가 아닌 검증 manifest가 필요합니다.')
target.mkdir(parents=True,exist_ok=True)
print(json.dumps({'python':platform.python_version(),'architecture':platform.machine(),
                 'scope':'isolated_offline_source','native_architecture_validated':platform.machine() in ('x86_64','AMD64')},ensure_ascii=False))
PY
TARGET=$(cd -- "$TARGET" && pwd)
BASE_COMMIT=$("$PYTHON_BIN" - "$PACKAGE_ROOT/validation_manifest.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))['carrot_source_commit']
if len(value)!=40 or any(c not in '0123456789abcdef' for c in value): raise SystemExit('소스 커밋 형식 오류')
print(value)
PY
)
mkdir -p "$TARGET/work"
GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none --depth 1 --single-branch --branch carrot-wip --no-checkout https://github.com/ajouatom/openpilot.git "$TARGET/work/carrotpilot"
git -C "$TARGET/work/carrotpilot" fetch --depth 1 origin "$BASE_COMMIT"
GIT_LFS_SKIP_SMUDGE=1 git -C "$TARGET/work/carrotpilot" checkout --detach "$BASE_COMMIT"
for PATCH in "$PACKAGE_ROOT"/patches/*.patch; do
  git -C "$TARGET/work/carrotpilot" apply --check "$PATCH"
  git -C "$TARGET/work/carrotpilot" apply "$PATCH"
done
"$PYTHON_BIN" - "$PACKAGE_ROOT" "$TARGET" <<'PY'
import json,shutil,sys
from pathlib import Path
package,target=map(Path,sys.argv[1:])
manifest=json.loads((package/'validation_manifest.json').read_text())
import hashlib
for item in manifest['patched_source_files']:
    path=(target/'work/carrotpilot'/item['path'])
    digest=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    if digest != item['sha256_lf']: raise SystemExit('패치 적용 결과의 해시가 다릅니다: '+item['path'])
for source,destination in [('native','native_sim'),('signal','signal_validation'),('safety','safety_validation')]:
    src=package/'validation'/source
    if src.exists(): shutil.copytree(src,target/'work'/destination)
shutil.copyfile(package/'validation_manifest.json',target/'validation_manifest.json')
print('소스 버전과 모든 변경 파일의 무결성을 확인했습니다.')
PY
if [[ -d "$INSTALLED/.git" ]]; then
  CURRENT_COMMIT=$(git -C "$INSTALLED" rev-parse HEAD)
  if [[ "$CURRENT_COMMIT" != "$BASE_COMMIT" ]]; then
    printf '기존 설치 버전은 시험한 기준과 다릅니다. 기존 설치에는 패치를 적용하지 않았습니다.\n'
  fi
fi
if [[ "$INSTALL_DEPS" == 1 ]]; then
  "$PYTHON_BIN" -m venv "$TARGET/work/offline-venv"
  "$TARGET/work/offline-venv/bin/python" -m pip install -r "$PACKAGE_ROOT/requirements-offline.txt"
fi
"$PYTHON_BIN" "$PACKAGE_ROOT/tools/check_compatibility.py" --installed-openpilot "$INSTALLED" --prepared-source "$TARGET/work/carrotpilot"
printf '\n준비된 검증 소스: %s\n' "$TARGET/work/carrotpilot"
printf '원본 차량 설치·Params·Panda·PCS/AEB·제어 활성화는 변경하지 않았습니다.\n'
printf '이 명령은 파일 준비만 수행합니다. 장치용 native 빌드·실차 호환성은 별도 검증 대상입니다.\n'
