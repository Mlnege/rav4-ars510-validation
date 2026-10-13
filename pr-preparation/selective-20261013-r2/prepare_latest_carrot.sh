#!/usr/bin/env bash
# 최신 공식 소스를 새 개발 폴더에 받고 선택한 런타임 변경만 검사·적용한다.
set -euo pipefail

# 게시 단계에서 selective-runtime-20261013-r2를 selective-runtime-20261013-r2로 채운다.
VALIDATION_TAG='selective-runtime-20261013-r2'
BASE_URL="https://raw.githubusercontent.com/Mlnege/rav4-ars510-validation/${VALIDATION_TAG}/pr-preparation/selective-20261013-r2"
UPSTREAM_URL='https://github.com/ajouatom/openpilot.git'
DESTINATION="${PWD}/carrot-latest-review/carrotpilot"
PYTHON_BIN='python3'
CHECK_ONLY=0
PARTS=(radar pcm longitudinal)

usage() {
  cat <<'HELP'
사용법: prepare_latest_carrot.sh [--destination 새개발폴더] [--python Python경로]
                                [--parts radar pcm longitudinal] [--check-only]

기본값은 세 부분 모두다. 공식 carrot-wip 최신 clone을 검사한 뒤 새 폴더에만 적용한다.
--check-only는 clone과 읽기 전용 검사까지만 한다. 기존 폴더는 덮어쓰지 않는다.
보고서와 다운로드 도구는 먼저 만든 clone 밖의 상위 폴더에 둔다.
전체 선택은 기존 7개·추가 12개, 총 19개 런타임 파일이다.
운영 설치·Params·실차 실행·자동 업데이트·재부팅은 수행하지 않는다.
HELP
}

die() {
  printf '준비 중단: %s\n' "$1" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage; exit 0;;
    --destination|--python)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || die '옵션 값이 필요합니다.'
      if [[ "$1" == --destination ]]; then DESTINATION="$2"; else PYTHON_BIN="$2"; fi
      shift 2;;
    --parts)
      shift
      PARTS=()
      while [[ $# -gt 0 && "$1" != --* ]]; do
        case "$1" in radar|pcm|longitudinal) ;; *) die '선택할 부분은 radar, pcm, longitudinal뿐입니다.';; esac
        for existing in "${PARTS[@]}"; do [[ "$existing" != "$1" ]] || die '같은 부분을 두 번 지정할 수 없습니다.'; done
        PARTS+=("$1")
        shift
      done
      [[ ${#PARTS[@]} -gt 0 ]] || die '--parts에는 하나 이상 필요합니다.';;
    --check-only) CHECK_ONLY=1; shift;;
    *) die '지원하지 않는 옵션입니다.';;
  esac
done

[[ "$VALIDATION_TAG" != *'@'* && "$VALIDATION_TAG" =~ ^[A-Za-z0-9._-]+$ ]] || die '태그가 치환된 정식 스크립트를 사용하세요.'
for program in git curl "$PYTHON_BIN"; do
  command -v "$program" >/dev/null || die 'git, curl, 지정한 Python이 필요합니다.'
done

# 시크릿·운영 설정을 읽지 않고 경로와 개발용 Python 범위만 확인한다.
"$PYTHON_BIN" - "$DESTINATION" <<'PY'
import os
from pathlib import Path
import platform
import sys

if not ((3, 12, 3) <= tuple(sys.version_info[:3]) < (3, 13, 0)):
    raise SystemExit('Python 3.12.3 이상, 3.13 미만이 필요합니다.')
if platform.system() != 'Linux':
    raise SystemExit('Linux 개발 환경에서 실행하세요.')
raw = Path(sys.argv[1]).expanduser().absolute()
if os.path.lexists(raw):
    raise SystemExit('대상 경로가 이미 있습니다. 새 개발 폴더를 지정하세요.')
target = raw.resolve()
if target.is_relative_to(Path('/data').resolve()) or target.parent == Path('/'):
    raise SystemExit('운영 /data 경로 또는 루트 바로 아래에는 준비하지 않습니다.')
for name in ('overlay-tools', 'check_report.json', 'reviewreport.json'):
    if os.path.lexists(target.parent / name):
        raise SystemExit('상위 폴더에 이전 도구/보고서가 있습니다. 새 준비 폴더를 사용하세요.')
PY

DESTINATION=$("$PYTHON_BIN" - "$DESTINATION" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)
RUN_ROOT=$(dirname -- "$DESTINATION")
TOOLS_DIR="$RUN_ROOT/overlay-tools"
CHECK_REPORT="$RUN_ROOT/check_report.json"
REVIEW_REPORT="$RUN_ROOT/reviewreport.json"
mkdir -p -- "$RUN_ROOT"
# v2 CLI는 보고서 부모가 미리 존재해야 하며 저장 중 부모를 만들지 않는다.
mkdir -- "$TOOLS_DIR"
mkdir -p -- "$TOOLS_DIR/assets/patches"

download() {
  curl --fail --show-error --silent --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
    "$BASE_URL/$1" --output "$TOOLS_DIR/$1"
}
download 'apply_runtime_overlay.py'
download 'assets/runtime_manifest.json'
download 'assets/patches/radar.patch'
download 'assets/patches/pcm.patch'
download 'assets/patches/longitudinal.patch'

printf '공식 carrot-wip 최신 소스를 새 개발 폴더에 받습니다.\n'
[[ ! -e "$DESTINATION" && ! -L "$DESTINATION" ]] || die '대상 경로가 생겼습니다. 기존 폴더에 clone하지 않습니다.'
GIT_TERMINAL_PROMPT=0 GIT_LFS_SKIP_SMUDGE=1 git -c core.autocrlf=false clone \
  --config core.autocrlf=false --filter=blob:none --single-branch --branch carrot-wip \
  "$UPSTREAM_URL" "$DESTINATION"

verify_latest_head() {
  local local_head remote_head
  local_head=$(git -C "$DESTINATION" rev-parse HEAD)
  remote_head=$(GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code "$UPSTREAM_URL" refs/heads/carrot-wip)
  remote_head=${remote_head%%$'\t'*}
  [[ "$remote_head" =~ ^[0-9a-f]{40}$ ]] || die '공식 브랜치 지문을 확인하지 못했습니다.'
  [[ "$local_head" == "$remote_head" ]] || die '준비 중 upstream이 바뀌었습니다. 새 폴더에서 다시 준비하세요.'
  printf '공식 최신 HEAD 일치: %s\n' "$local_head"
}

verify_latest_head
"$PYTHON_BIN" "$TOOLS_DIR/apply_runtime_overlay.py" "$DESTINATION" \
  --parts "${PARTS[@]}" --assets "$TOOLS_DIR/assets" --check --report "$CHECK_REPORT"
if [[ "$CHECK_ONLY" == 1 ]]; then
  printf '읽기 전용 검사 완료. 최신 소스에는 오버레이를 적용하지 않았습니다.\n'
  printf '검사 보고서: %s\n' "$CHECK_REPORT"
  exit 0
fi

# 원형 지문/문맥이 맞을 때만 CLI가 새 clone에 명시적으로 적용한다.
verify_latest_head
"$PYTHON_BIN" "$TOOLS_DIR/apply_runtime_overlay.py" "$DESTINATION" \
  --parts "${PARTS[@]}" --assets "$TOOLS_DIR/assets" --apply --report "$REVIEW_REPORT"
printf '선택한 런타임 파일의 적용과 지문 확인을 완료했습니다.\n'
printf '개발 소스: %s\n검토 보고서: %s\n' "$DESTINATION" "$REVIEW_REPORT"
printf '운영 설치와 실차는 변경하지 않았습니다. 전체 빌드·장치 호환성·차량 안전은 별도 검증 대상입니다.\n'
