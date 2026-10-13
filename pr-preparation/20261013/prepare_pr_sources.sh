#!/usr/bin/env bash
# 새 작업 폴더에 검토용 소스만 준비한다. 설치·설정·제어 활성화는 하지 않는다.
set -euo pipefail
command -v git >/dev/null
command -v curl >/dev/null
command -v python3 >/dev/null
python3 -c 'import sys;sys.exit(None if (3,12,3) <= sys.version_info < (3,13) else "Python 3.12.3 이상, 3.13 미만이 필요합니다.")'
target="${1:-$PWD/rav4-pr-20261013}"
target="$(python3 -c 'from pathlib import Path;import sys;print(Path(sys.argv[1]).resolve())' "$target")"
case "$target" in
  /data/openpilot|/data/openpilot/*|/data/opendbc|/data/opendbc/*)
    printf '%s\n' '운영 소스 경로에는 준비할 수 없습니다.' >&2; exit 2 ;;
esac
if [ -e "$target" ]; then
  printf '%s\n' '대상 폴더가 이미 있습니다. 새로운 폴더를 지정해 주세요.' >&2; exit 2
fi
mkdir -p "$target"
base='https://raw.githubusercontent.com/Mlnege/rav4-ars510-validation/pr-ready-20261013/pr-preparation/20261013'
curl -fL "$base/source_manifest.json" -o "$target/source_manifest.json"
curl -fL "$base/verify_pr_sources.py" -o "$target/verify_pr_sources.py"
git -c core.autocrlf=false clone --filter=blob:none --single-branch --branch codex/rav4-ars510-carrot-compat https://github.com/Mlnege/openpilot.git "$target/carrot"
git -C "$target/carrot" checkout --detach 41773212b683181d9ce569c627ef7a97a74f0dc6
git -c core.autocrlf=false clone --filter=blob:none --single-branch --branch codex/carrot-native-ars510-dispatch https://github.com/Mlnege/ars510-radar.git "$target/ars510"
git -C "$target/ars510" checkout --detach a63279545adc72c5a4330f84391b9a19d932c6d7
python3 "$target/verify_pr_sources.py" "$target/carrot" "$target/ars510" "$target/source_manifest.json"
printf '%s\n' '검토용 파일 준비 완료. 실차 설치·종방향 활성화는 실행하지 않았습니다.'
