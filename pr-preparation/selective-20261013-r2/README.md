# 최신 공식 Carrot에 필요한 부분만 추가하기

공식 `ajouatom/openpilot`의 **실행 시점 최신 `carrot-wip`**을 새 개발 폴더에 받고, 필요한 런타임 변경만 선택해 덧붙입니다. 과거 검증 fork의 고정 소스로 갈아타는 방식은 아닙니다. 기존 설치, 운영 Params, 차량 연결, 재부팅 또는 자동 업데이트 설정은 변경하지 않습니다.

오버레이 자산은 검증 저장소의 고정 태그에서 받지만 Carrot 소스는 공식 최신 브랜치에서 받습니다. 적용 전 소스 지문·문맥·변경 후 지문을 검사하며, 미래 upstream과 맞지 않으면 적용을 보류합니다. 검사를 통과한 19개 런타임 파일만 대상이며 사용자 문서·테스트·현대 Bosch·다른 차량의 전용 파일은 덮어쓰지 않습니다. 공식 업데이트의 최적화·신호·타차 기반을 유지하고 선택한 좁은 변경만 추가합니다.

## 선택 범위

| 선택 | 기존 파일 변경 | 추가 파일 | 범위 |
|---|---:|---:|---|
| `radar` | 3 | 11 | RAV4 2022 ARS510 수신기·최신 decoder 9파일·MIT LICENSE·레이더 입력 오류 후 복구 연결 |
| `pcm` | 1 | 1 | 정확한 RAV4 2022 직접 제어의 PCM 모드 0 관측 속도 연결 |
| `longitudinal` | 3 | 0 | 정확한 RAV4 2022 직접 제어의 명령 범위·호스트 감속 전달·정지 명령 보완 |
| 기본값: 모두 | 7 | 12 | 총 19개 런타임 파일 |

`radar`는 모델과 기존 `RADAR_ACC`의 소프트웨어 수신 능력을 연결하며 새 객체는 실제 정상 CAN 레코드에서만 만듭니다. `pcm`은 새 RES/SET CAN 스팸을 보내지 않습니다. `longitudinal`은 기존 직접 제어 조건 안의 계산 경계 보완이며 새 제어 권한을 부여하지 않습니다. 실물 ECU/펌웨어, PCS/AEB, 회생제동, 실제 차량 응답과 장치 전체 빌드는 이 파일 준비만으로 검증되지 않습니다.

레이더 범위에는 공통 입력 처리 파일인 `radarcan.py` 1개가 포함됩니다. 입력 오류 후 수신기를 다시 만들 때 정확한 RAV4 2022 ARS510 수신기의 복구 상태를 연결합니다. 정수형 `ARS510_INPUT_RECOVERY_API=1`과 `recover_from_input_fault`를 명시한 수신기에서만 실행하고, 다른 차량은 기존 기본 생성 경로를 유지합니다. 이 복구 연결은 정상 레코드 없이 새 측정 객체나 제어 권한을 만들지 않습니다.

## 새 개발 폴더 준비

Linux 개발 환경과 Git, curl, 프로젝트에서 시험한 `3.12.3 <= Python < 3.13`을 준비합니다. 이번 패키지의 태그는 `selective-runtime-20261013-r2`입니다. 공개 스크립트는 태그가 채워진 `prepare_latest_carrot.sh`이며 `.sh.in`은 게시 시 `selective-runtime-20261013-r2`를 이 태그로 채우는 템플릿입니다.

검증 자산 경로는 다음과 같습니다.

```text
https://raw.githubusercontent.com/Mlnege/rav4-ars510-validation/selective-runtime-20261013-r2/pr-preparation/selective-20261013-r2
```

이 경로의 `pr-preparation/selective-20261013-r2`는 태그 안의 디렉터리입니다. 공식 Carrot branch를 이 검증 태그나 과거 fork commit으로 checkout하지 않습니다.

태그가 게시된 뒤 스크립트를 새 개발 준비 폴더에 받습니다. 아래 다운로드 명령은 게시 전에는 사용할 수 없습니다.

```bash
set -e
mkdir rav4-overlay-preparation-new
cd rav4-overlay-preparation-new
VALIDATION_TAG='selective-runtime-20261013-r2'
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
  "https://raw.githubusercontent.com/Mlnege/rav4-ars510-validation/${VALIDATION_TAG}/pr-preparation/selective-20261013-r2/prepare_latest_carrot.sh" \
  --output prepare_latest_carrot.sh
```

다운로드한 내용을 확인한 뒤 다음 명령을 실행합니다. 기본값은 세 부분 모두이며 지정한 대상은 존재하지 않아야 합니다.

```bash
bash prepare_latest_carrot.sh --destination "$PWD/rav4-review-new/carrotpilot"
```

레이더 수신만 준비하려면 다음과 같이 선택합니다.

```bash
bash prepare_latest_carrot.sh --destination "$PWD/rav4-radar-review-new/carrotpilot" --parts radar
```

PCM과 직접 종방향 계산만 준비하는 예시입니다.

```bash
bash prepare_latest_carrot.sh --destination "$PWD/rav4-control-review-new/carrotpilot" --parts pcm longitudinal
```

적용 없이 공식 최신 clone과 검사 보고서만 만들 수도 있습니다.

```bash
bash prepare_latest_carrot.sh --destination "$PWD/rav4-check-new/carrotpilot" --parts radar --check-only
```

Python 경로가 다르면 `--python /개발가상환경/bin/python`을 지정합니다. 운영 가상환경이나 기존 차량 설치 폴더에 도구를 넣지 않습니다.

## 실행 순서와 보고서

1. Python 버전·Linux·새 경로를 확인합니다. 기존 대상·도구·보고서가 있으면 덮어쓰지 않고 중단합니다. 보고서 부모가 될 clone 밖 상위 폴더를 먼저 만듭니다.
2. 고정 검증 태그의 CLI, manifest와 세 patch를 대상 clone 밖 `overlay-tools/`에 받습니다.
3. 공식 `carrot-wip`을 `core.autocrlf=false`, blob filter, single-branch로 clone하고 현재 HEAD가 공식 `ls-remote` 결과와 같은지 확인합니다. 비교용 이전 Git 객체의 이력이 필요하므로 얕은 clone으로 바꾸지 않습니다.
4. 선택한 부분을 CLI의 `--check`로 검사하고 clone 밖 `check_report.json`에 결과를 남깁니다.
5. 검사가 통과한 경우 최신 HEAD를 다시 확인한 뒤 `--apply`를 명시해 새 clone에만 적용하고 `reviewreport.json`을 남깁니다. `--check-only`는 4단계에서 끝납니다.

예시의 폴더 배치는 다음과 같습니다.

```text
rav4-review-new/
  carrotpilot/       공식 최신 소스 + 선택한 런타임 오버레이
  overlay-tools/    검증 태그의 CLI·manifest·patch
  check_report.json 읽기 전용 검사 결과
  reviewreport.json 적용 후 지문 결과
```

보고서는 소스 지문과 적용 범위 확인이며 `vehicle_deployment_allowed=False`인 개발 준비 결과입니다. 전체 빌드, 실시간 성능 또는 실차 제어를 통과했다는 보고서가 아닙니다. 모델/LFS 파일과 native 빌드는 프로젝트 공식 절차로 별도 준비합니다.

v2 CLI를 직접 호출할 때도 보고서 부모 디렉터리가 미리 존재해야 합니다. 보고서는 저장소 밖의 새 파일이어야 하며 운영 `/data` 경로와 심볼릭 경로를 거절합니다. 지원하는 Linux와 Windows에서는 검증한 디렉터리 핸들에 연결해 저장합니다. 없는 새 파일이 Git ignore 대상이면 적용 전에 거절하고, artifact 목록은 세 patch 경로로 제한합니다. 독립 Linux 재검사에서는 임의 더미 파일 읽기 0회, ignored 새 파일 사전 거절, 보고서 부모의 repo향 경로 전환 거절을 확인했습니다. 모든 시점의 파일 시스템 동시 변경을 원자적으로 막는다는 보증은 아닙니다.

적용 전 검사에서 충돌하면 패치를 적용하지 않습니다. 실제 적용 후 사후 검사나 보고서 저장이 실패하면 도구가 “패치 적용은 완료됐지만 … 실패”를 표시합니다. 그 개발 clone을 확인해야 하며 자동 원복하거나 성공 보고서를 만들지 않습니다.

## 공식 업데이트 이후

기존 clone에 자동으로 다시 덧붙이지 않습니다. 다음 업데이트마다 다른 새 준비 폴더를 지정해 최신 공식 소스를 받고 필요한 부분만 선택합니다. 원형 지문·패치 문맥·외부 ARS hook·decoder 소유권이 충돌하면 최신 clone을 그대로 두고 오버레이를 쓰지 않습니다. 강제 적용, 자동 3-way 병합, 기존 hook 삭제, 외부 decoder 덮기 또는 설치기 자동 복구는 하지 않습니다.

실패한 경로를 억지로 통과시키려고 manifest/patch 지문을 바꾸지 않습니다. 새로운 upstream을 검토한 호환 자산이 준비될 때까지 적용을 보류합니다. 기존 폴더 삭제나 운영 설치 교체는 이 스크립트의 작업 범위가 아닙니다.

이 문서와 스크립트의 로컬 작성 단계에서는 원격 태그 다운로드·실제 fresh-clone 전체 재현을 수행했다고 주장하지 않습니다. 최종 태그 생성과 실제 end-to-end 검사는 별도 실행 결과로 확인해야 합니다.
