#!/usr/bin/env bash
# 격리된 Linux x86_64 검증 공간에서만 native 계산·단위 검사를 실행한다.
set -euo pipefail
[[ $# -eq 1 ]] || { printf '사용법: bash tools/run_native_validation.sh /별도/검증공간\n' >&2; exit 2; }
LAB=$(cd -- "$1" && pwd)
PY="$LAB/work/offline-venv/bin/python"
[[ -x "$PY" ]] || { printf '검증 전용 가상환경이 없습니다.\n' >&2; exit 3; }
"$PY" - "$LAB" <<'PY'
from pathlib import Path
import json,platform,sys
lab=Path(sys.argv[1]).resolve()
protected=Path('/data/openpilot').resolve()
if lab==protected or lab.is_relative_to(protected) or protected.is_relative_to(lab):
    raise SystemExit('운영 설치 경로에서는 실행하지 않습니다.')
if platform.system()!='Linux' or platform.machine()!='x86_64':
    raise SystemExit('이 native 재현은 Linux x86_64에서만 검증했습니다. 장치 전체 빌드는 별도 대상입니다.')
if not ((3,12,3)<=tuple(sys.version_info[:3])<(3,13,0)):
    raise SystemExit('검증한 Python 범위와 다릅니다.')
if json.loads((lab/'validation_manifest.json').read_text())['vehicle_deployment_allowed'] is not False:
    raise SystemExit('검증용 배포 상태가 아닙니다.')
PY
for PROGRAM in gcc make; do
  command -v "$PROGRAM" >/dev/null || { printf '필요한 빌드 도구가 없습니다: %s\n' "$PROGRAM" >&2; exit 3; }
done
PACKAGE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$PY" "$PACKAGE_ROOT/tools/check_compatibility.py" --manifest "$PACKAGE_ROOT/validation_manifest.json" --prepared-source "$LAB/work/carrotpilot"
export CARROT_VALIDATION_BUILD="$LAB/work/native_sim/build_first"
[[ ! -e "$CARROT_VALIDATION_BUILD" ]] || { printf '기존 solver는 덮어쓰지 않습니다. 새 검증 공간을 사용하세요.\n' >&2; exit 4; }
"$PY" -m pip install -r "$PACKAGE_ROOT/requirements-native.txt"
cd -- "$LAB"
"$PY" work/native_sim/build_mpc.py
"$PY" -m pytest -s -c work/carrotpilot/tools/ars510_offline/pytest.ini work/carrotpilot/tools/ars510_validation/native work/carrotpilot/tools/ars510_validation/signal/test_camera_profiles.py work/carrotpilot/tools/ars510_validation/signal/test_native_signal.py -q
printf '완료: 실제 native MPC·카메라 계약의 PC 오프라인 검사입니다. 실제 CAN 송신과 차량 활성화는 없습니다.\n'
