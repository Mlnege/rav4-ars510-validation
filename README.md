# RAV4 2022 레이더·종방향 제어 오프라인 검증

## 최신 공식 소스에 선택 파일 패치 — 코드 검토 후 r2

공식 `carrot-wip`을 실행 시점 최신으로 새 개발 폴더에 받은 뒤 필요한 레이더·PCM·종방향 변경만 선택합니다. 기존 실행 파일7개와 추가12개, 총19개가 대상입니다. 레이더 입력 오류 뒤 재구성해도 정상 레코드까지 오류를 유지하도록 보완했습니다. 다른 차량·Bosch·신호·성능·UI 기반과 운영 설치는 유지합니다.

[선택 패치·최신 소스 다운로드 안내](pr-preparation/selective-20261013-r2/README.md), [코드 검토5건과 수정 결과](pr-preparation/selective-20261013-r2/코드검토.md), [직접 검증 결과](pr-preparation/selective-20261013-r2/검증결과.md)를 확인하세요. 핵심 지문이나 문맥이 달라지면 강제 적용하지 않습니다. 후보 `94ecc00c`는 [최신 Carrot PR 비교](https://github.com/ajouatom/openpilot/compare/carrot-wip...Mlnege:codex/rav4-ars510-carrot-latest?expand=1)에 있으며 실제 PR는 제출하지 않았습니다.

최신 공식0611 clone의 선택19 적용을 직접 확인했습니다. 공개 고정 태그 다운로드부터 공식 최신 clone·검사·적용까지 직접 완료했으며 [원격 준비 근거](pr-preparation/selective-20261013-r2/원격준비_검증.json)에 기록했습니다. 실제 로그는 제어OFF이며 ECU/펌웨어·PCS/AEB·회생·Konik 전체 빌드·실차 제동은 미검증입니다. 이전18파일 배포와2ec/417 자료는 당시 스냅샷으로 보존했습니다.

## 최신 PR 준비 — 2026-10-13

사용자 요청에 따라 기존 반복 검증을 종료하고 최신 Carrot `2ec25da`와 ARS `fb5b29c`를 기준으로 PR 후보를 준비했습니다. 실제 PR은 아직 제출하지 않았습니다.

- [Carrot 후보 비교](https://github.com/ajouatom/openpilot/compare/carrot-wip...Mlnege:codex/rav4-ars510-carrot-compat?expand=1): `41773212b683181d9ce569c627ef7a97a74f0dc6`, 33파일.
- [ARS 후보 비교](https://github.com/ds-sebastian/ars510-radar/compare/main...Mlnege:codex/carrot-native-ars510-dispatch?expand=1): `a63279545adc72c5a4330f84391b9a19d932c6d7`, 4파일.
- [패치·검증·다운로드 안내](pr-preparation/20261013/README.md): 수정 소스37개, PR 설명, 소스 확인 명령, Wiki 수동 설명 패치.

최종 고정 pycapnp2.1.0에서 수신기·PCM·native 종방향 182개가 통과했습니다. 원격에서 새로 복제한 ARS 전체 시험은 271통과·설치 환경1개 생략입니다. 실제 로그는 정상 레코드2,399개·전달점367개와 원형 Float32 값 차이0을 확인했습니다. 다른 차량/Bosch/신호·야간/공유 필터/Panda 기반을 유지하며, 실제 ECU·PCS/AEB·회생·Konik 전체 빌드·물리 제동은 미검증입니다.

아래 내용은 종료한 기존 `r10.1`까지의 조사 스냅샷입니다. 최신 후보의 기준·변경 파일·적용 명령은 위 새 안내를 사용합니다.

## 이전 조사 스냅샷

한국형 RAV4 Hybrid 2022의 저장 CAN을 분석하고, ARS 객체를 기존 당근레이더 처리 코어로 전달하는 수신 어댑터와 재현 가능한 검증 도구입니다. **실차 자동 설치·제어 활성화용 배포가 아닙니다.**

기준 CarrotPilot은 `carrot-wip`의 `0e4ee1bdbef3ad7284b136fddf31592e3f8a785f`, ARS510 분석 기준은 `673eb8e609e303feff2c15dd250592c383962156`입니다. 변경 파일의 정확한 목록·해시는 `validation_manifest.json`에 있습니다.

검증 표현 정정: CANParser/CANPacker와 레이더 처리에서는 프로젝트의 원형 Python 처리 경로를 사용했습니다. 실제 C/Cython으로 빌드한 MPC, 별도로 빌드한 안전 검사 C와 구분합니다. 최초 태그의 일부 문서에 있던 'native CANParser' 표현은 부정확하며 CAN C++ 빌드·장치 처리 성능의 증거가 아닙니다. 이 표현 정정은 r7까지 반영됐고 이후 검증판에서도 유지합니다. 배포 파일은 LF 줄끝으로 생성하며 Git의 자동 줄끝 변환도 끕니다. Windows에서 clone한 파일을 Linux로 옮겨도 원바이트가 바뀌지 않아야 합니다.

제공한 실제 로그에서 ARS 객체 CRC와 거리·속도 디코딩, 기존 레이더 처리 코어 전달을 검증했습니다. 실물 ECU 제조사·모델·펌웨어는 확인되지 않았습니다. 공유 대화의 부품번호 후보와 저장소의 지원 펌웨어 문자열은 실제 ECU 조회 응답으로 취급하지 않았습니다.

추가 수정은 RAV4 직접 종방향 제어의 가속도 계산·송신 한계 일치, 기존 PCM 버튼 설정속도 입력 연동, 엄격하게 제한된 근거리 기존 측정 유지, C 제어 권한 검사 복원, 공식 OX03C10 카메라 형식 지원입니다. `radarUnavailable`을 강제로 끄거나 코너 객체·알 수 없는 신호를 만들지 않았습니다. 근거리 기능은 현재 RAV4의 `radarUnavailable=True`에서 켜지지 않습니다.

롱컨 활성 조건은 PC 모의주행의 `longActive=True`와 허용된 제어 권한 입력으로 검사했습니다. 센서·카메라 인식 결과와 차량의 지연·응답은 명시된 가정입니다. 실제 배터리 회수량, 실차 급제동 성능, 순정 PCS/AEB 유지, Konik 전체 빌드는 미검증입니다. ACC 보조 관측 누락·오래된 입력과 일부 정지거리 부족 조건에서는 모의 충돌이 남아 있습니다.


근본 원인 분석을 추가했다. 실제 비활성 로그의 초기 추론 지연·속도 기준 차이와 합성 지연의 권한 반응을 구분하고, 이력·공개조건 하나로 급감속 실패를 설명할 수 없다는 반례를 보존했다. r9까지 소스 63개와 패치 8개의 개수를 유지했고, r7에서는 오프라인 재생기의 오류 전파 수정으로 replay.py와 patch01의 지문을 갱신했다. r9까지 주행 제어 코드는 r4 이후 그대로였고, r10은 재현된 감속 요청 전달 손실을 수정했다. 새 분석 범위와 지문 변환은 `analysis/README_KO.md`, `published_analysis_manifest.json`에 있다.

## 파일을 별도 검증 공간에 준비하기

Linux, Git, SHA256 도구와 Python 3.12.3 이상·3.13 미만이 필요합니다. 기존 `/data/openpilot`에 쓰지 않습니다. 아래 명령은 고정 버전 clone, 패치 적용 검사, 변경 파일 해시 검사, CPU·Python·기존 소스 비교와 격리된 가상환경 다운로드만 실행합니다.

```sh
git clone --branch lab-20261013-r10.1 --depth 1 https://github.com/Mlnege/rav4-ars510-validation.git rav4-ars510-validation-r10-1
cd rav4-ars510-validation-r10-1
bash tools/remote_download.sh --destination /data/rav4-validation-lab-r10-1 --install-deps
```

`--python /경로/python3.12`로 실행 파일을 선택할 수 있습니다. 대상 폴더가 비어 있지 않으면 중단합니다. 기존 설치가 `/data/openpilot` 이외에 있으면 `--installed-openpilot /기존/설치`도 지정합니다. 기본 차량 설치 경로는 이 옵션과 관계없이 보호합니다.

출력의 '소스 일치'는 파일 준비 조건이며 실차 레이더·회생·PCS 호환성 판정이 아닙니다. ARM 장치의 native 계산 빌드는 별도 확인 대상입니다. 장치 재부팅·Params 변경·Panda 펌웨어 설치·ECU 비활성화·차량 CAN 송신은 하지 않습니다.

## 오프라인 실행

준비된 공간의 `work/carrotpilot`에서 수신 검사를 실행할 수 있습니다. 로그와 기록 당시 전체 cereal 스키마는 사용자가 별도 보관한 자료를 지정합니다. 원본 주행 로그·차량 식별자·좌표·계정 정보는 이 배포에 포함하지 않았습니다.

```sh
cd /data/rav4-validation-lab-r10-1/work/carrotpilot
../offline-venv/bin/python -m pytest -c tools/ars510_offline/pytest.ini opendbc_repo/opendbc/car/toyota/tests/test_ars510_offline.py tools/ars510_offline/test_legacy_regression.py
../offline-venv/bin/python -m tools.ars510_offline.replay /보관/rlog폴더 --schemas /보관/기록당시전체스키마 --output /별도/재생결과
```

회생 관련 수신 진단은 기존 Toyota DBC의 `FDRVREAL`과 `BRAKE_FORCE`만 읽습니다. 엔진·모터·크리프·회생이 섞인 값과 의미가 검증되지 않은 포화 값을 실제 회생량으로 바꾸지 않습니다. 자세한 결과는 `validation/safety/REGEN_FILTER_REVIEW_KO.md`, 활성 가정 에너지 계산은 `results/long_active_energy_budget.json`에 있습니다.

native MPC와 안전 C 검사의 재현은 `validation/native/VALIDATION_KO.md`, `validation/safety/README.md`를 참고합니다. 별도 Linux x86_64 Python3.12 환경·GCC가 필요하며, 실행 중인 solver 빌드를 덮어쓰지 않습니다. 전체 차량 설치 환경에 의존성을 추가하지 마세요.

## 자료와 범위

- `patches/`: 기능별 수정 9개, manifest 순서로 적용
- `reports/`: 실제 CAN 분석·Vision Only 원인·PCM 모드0·전방/코너/당근 구현 가능성
- `results/`: 실제 실행한 검사 결과와 가상 주행 CSV·그림
- `validation/`: 입출력을 격리한 실제 계산 코드 검증 도구
- `SHA256SUMS`: 배포 파일 무결성 확인

ARS510 원형 소스·DBC는 MIT 라이선스와 저작권 표시를 유지했습니다. CarrotPilot의 라이선스도 포함합니다. 실차 호환성이 확인될 때까지 검증용 배포 상태를 유지합니다.

추가 연결과 정정: `reports/연결검증_갱신_r6.md`에서 Mode0→ToyotaCAN/C 검사와 신호 재개 반례의 서로 다른 범위를 확인하세요. r6까지 유지한 계산 소스 63개와 패치 8개 중, r7에서는 오프라인 재생기의 오류 전파만 수정했습니다.

통합 신호 갱신: `reports/통합신호_검증갱신_r7.md`에서 가속 입력 시점·정지 기억의 복구·오래된 모델 출처와 최초 기대 오류를 확인하세요. 주행 제어 코드는 그대로이며, 오프라인 오류 전파 수정만 patch01에 추가했습니다. 실차 배포 허용은 여전히 False입니다.

r8에는 실제 CAN의 비활성 호스트·MPC 연결, 정확한 CAN 묶음과 시간 가정, 기록 Panda 모드 전환 및 수신/송신 통지 분류 검증을 추가했습니다. `reports/연결과_초기화_검증갱신_r8.md`에 완료 범위와 최초 실패·정정을 정리했습니다. 소스 63개·패치 8개·manifest는 r7과 바이트가 같습니다. 직접 롱컨 설정은 원본 CP 5개 중 True3/False2였으며, 실제 활성화는 모두 꺼져 있었습니다. 검사 수치가 실차 제어 성공이나 PCS·회생 보증을 뜻하지 않습니다.

r9에서는 정확한 CAN 묶음과 원본 CP·기록 Panda 정책을 같은 비활성 호스트/MPC/CAN 경로에 연결했습니다. 실제 발행 P는 미관측이고 새 헤더는 선언한 재생 시각 가정입니다. `reports/통합검증_갱신_r9.md`에서 송신 기대값을 정의한 3,191개와 미정 21,135개의 범위를 확인하세요. 코드 소스·패치·manifest는 r8.1과 그대로이며 새 장치 빌드나 실차 배포는 없습니다.


r10은 오류 해제 대기 중 감속 목표를 다시 크루즈 속도로 덮던 결함을 정확 RAV4 2022 직접 종방향에 한정해 수정했습니다. 기존 01~08 패치는 바이트 그대로이며 09를 추가했습니다. 소스64개·패치9개·실차배포False입니다. `reports/레이더_소실_감속요청_수정검증.md`에서 최초 실패, 60고유 계획/300반복틱, 수정 후 남은 양수CAN과 최초 파일경로 준비 실패를 확인하세요. 기본False의 새 MPC 인자를 실제 수정 Python/동결 native 사본으로 검증했으며 새 C 빌드나 실차 제동 검증으로 표현하지 않습니다.


r10.1은 공개 XML7개의 줄끝만 LF로 정규화한 형식 정정입니다. 코드64개·패치9개·검사 결과는 r10과 같습니다. r10태그는 보존하며 새 명령은 r10.1을 사용합니다.
