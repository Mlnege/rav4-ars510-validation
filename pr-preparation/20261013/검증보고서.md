# RAV4 2022 ARS510·PCM 호환 변경의 검증 범위

이 변경은 정확한 `TOYOTA_RAV4_TSS2_2022`의 ARS510 객체 CAN을 Carrot 수신기와 실제 MyTrack 처리에 연결하고, 별도 조건의 PCM 모드 0 속도 동기화와 직접 종방향 계산 경계를 보완한다. 정상 레코드 2,399개·디코딩 점 367개를 원본 배치로 처리했으며 원형 fused와 레코드·슬롯별 거리/속도 값이 Float32 기준으로 일치했다. 원본 로그의 제어는 모두 OFF였으므로 이 결과는 실차 종방향 활성화·제동 성능·PCS/AEB 보존의 증거가 아니다.

기준 소스는 [Carrot 2ec25da](https://github.com/ajouatom/openpilot/tree/2ec25da3c10e369eaf4ad0313fde3280e5a8b06e), [ARS510 fb5b29](https://github.com/ds-sebastian/ars510-radar/tree/fb5b29c2b5999f34afeb6f7ac494a73949d66c67)이다. ARS510 Python 9파일과 MIT LICENSE를 원문 그대로 포함하며 프로파일 계수·신호 정의를 튜닝하지 않았다. [한국어 사용자 안내](user/ko/radar.md#rav4-ars510)와 [영문 사용자 안내](user/en/radar.md#rav4-ars510)는 적용 범위를 요약한다.

## 지원 선언과 수신 연결

지원 조건은 `brand=toyota`, 정확한 RAV4 TSS2 2022 식별자, 기존 `ToyotaFlags.RADAR_ACC`다. 모델과 이미 검증한 수신 프로토콜의 소프트웨어 능력 선언이며 실제 ECU 부품·펌웨어를 새로 식별한 결과가 아니다. FW가 비어 있어도 parser를 선택할 수 있지만 새 객체는 실제 CRC 정상 레코드에서만 생성한다.

| 파일/구성 | 변경 |
|---|---|
| `opendbc_repo/opendbc/car/toyota/ars510/` | 최신 원문 decoder 9파일·MIT LICENSE. 숫자·신호·필터 원문 보존. |
| `ars510_carrot.py` | 독립 수신 전용 `Ars510RadarInterface`, API 1. 원형 fused metadata와 실제 Base/MyTrack 연결, CRC/순서/시간/객체 ID 경계 처리. |
| Toyota `interface.py` | 지원 조건에서 `radarUnavailable=False`, `radarTimeStep=0.06`, `radarDelay=0.0` 선언. 기존 종방향 선택·안전 설정·ECU 초기화 결정을 유지. |
| Toyota `radar_interface.py` | 지원 CP만 새 수신기로 dispatch. API 1·fused·지원 predicate를 명시하며 다른 Toyota는 기존 parser 사용. |

`radarDelay=0.0`은 이 수신 연결의 거리 시각 보정 설정이다. 물리 레이더 지연이 0이라는 측정 결과, 종방향 actuator 지연 0 또는 하이브리드 회생제동 확인을 뜻하지 않는다. 기존 하이브리드 flag는 FW의 hybrid ECU 확인에 따라 정하며 이 변경에서 강제하지 않는다.

추가 설정 키는 없다. Toyota의 기존 effective 모드는 CP.radarUnavailable=True이면 -2, False이면 1이다. 새 지원 선언 뒤에는 fused 전방 객체를 기존 레이더·비전 매칭 경로로 전달한다. 현대의 모드 2/SCC·코너 객체 기능으로 임의 확대하지 않는다. 객체 출처는 `frontRadar`, 확인되지 않은 native 상태는 `trackState=0`으로 전달한다. 특별한 정지차 규칙의 상태 조건을 만족시키려고 다른 제조사의 상태 번호를 넣지 않는다.

ARS upstream 설치기는 `ars510_radar_interface.py`를 복사하고 Toyota dispatcher에 hook을 추가한다. Carrot 전용 코드를 같은 파일에 넣으면 재설치로 덮어쓰거나 hook이 실제 MyTrack 연결 경로를 우회할 수 있어서 별도 `ars510_carrot.py`로 분리했다. [ARS 상호운용 후보 a632795](https://github.com/Mlnege/ars510-radar/commit/a63279545adc72c5a4330f84391b9a19d932c6d7)는 fused·정수 API 1·명시한 지원 predicate가 모두 맞을 때 기존 Carrot dispatcher를 존중한다.

해당 ARS 후보의 설치기는 명시한 native 계약을 소스에서 읽어 당근 소유의 `ars510/` 패키지와 LICENSE를 보존한다. Python 파일 목록·내용이 맞을 때만 외부 hook을 설치하고, 버전이 다르거나 계약이 불명확하면 파일을 바꾸기 전에 중단한다. 제거할 때도 당근 디코더를 삭제하지 않는다. 별도 복사본의 전체 ARS 시험은 271개 통과·설치 환경 미지정 1개 생략이었으며 실제 Carrot factory 연결은 별도 합성 입력으로 확인했다. 이 후보가 반영되지 않은 외부 설치기의 병용과 실제 장치 설치·제거는 검증하지 않았다.

## CAN·시간·동역학 계약

| bus/주소 | 원형 해석과 입력 길이 |
|---|---|
| bus 1 `0x80` | 8바이트 분할 프레임 106개를 742바이트 객체 레코드로 조립. 시작·연속 순서와 CRC 확인. |
| bus 0 `0xB4` | 8바이트 Toyota 속도. 기존 Toyota 체크섬 확인 후 원형 vRel의 자차 기준으로 사용. |
| bus 0 `0x24` | 8바이트 Toyota 회전율. |
| bus 1 `0x235` / `0x237` | 8바이트 순정 ACC 대상 상대속도/위치. 현대 corner235 객체와 주소가 같아도 같은 신호가 아니다. |
| bus 1 `0x192` / `0x194` | 요약 입력 4~8바이트. 실제 세 로그는 모두 4바이트. 원형 fused의 summary 필터는 꺼진 상태 유지. |

`0x80`/`0x85`의 존재나 첫 8바이트만으로 객체 트랙 호환성을 확정하지 않는다. 객체는 원형 0x80 레코드 decoder에서 읽고 `0x85`를 새 측정 객체로 바꾸지 않는다. 거리/횡위치/상대속도와 ground 속도는 원형 fused 결과다. 실제 ground metadata를 `vLead`에 넣고 완료 레코드마다 실제 MyTrack이 `aLead`와 `jLead`를 계산한다. 정상 빈 레코드는 점과 트랙을 제거하며 예측 객체를 만들어 채우지 않는다.

처음 정상 레코드 전에는 외부 100Hz 호출 기준 빈 정상 결과를 20Hz로 보내고 15초에 한 번 경고한다. 명목 record 주기는 0.06초이며 처음 빈 발행 간격 0.05초로 필터를 학습하지 않는다. 이미 정상 수신한 뒤 0.5초 초과 손실은 임시 불가, 명백한 CRC/순서/DLC/시각 오류는 canError와 이력 초기화로 보고한다. 부분 레코드만으로 오류 복구를 선언하지 않는다.

추가 조립 한계 0.15초는 각 연속 프레임 시각에서 그 레코드 첫 프레임 시각을 뺀 값에 적용한 기존 wrapper 한계다. 모델 EOF/발행 시각 차이의 150ms 정책과 별개이며 새 최적값으로 튜닝하지 않았다. 여러 record가 한 외부 batch에 있을 때 실제 시각·순서를 유지해 모든 record의 필터를 처리하되 반환은 마지막 결과다. 외부 자차 이력은 한 샘플만 늘린다. 시작/완료 시각이 겹쳐 측정 간격이 모호한 복수 record는 가짜 주기를 주지 않고 거절한다.

객체 ID는 원형 lifecycle을 사용하고 이력 초기화 뒤 별도 namespace로 과거 필터 재사용을 피한다. 음수·중복·비정수 또는 downstream Int32 상한 밖 ID는 거절한다. 코너 슬롯 예약 범위나 가짜 객체를 빌려 쓰지 않는다. 공유 MyTrack/DPath의 다른 차 규칙은 변경하지 않았다.

## 실제 로그에서 확인한 반례와 정정

첫 수신기 후보는 요약 주소를 전달하면서 DLC 8만 허용해 정상 DLC 4를 오류로 보았다. 원형 소스를 유지한 재생에서는 5,132회 길이 오류와 반복 초기화가 발생해 1,002레코드/77점만 전달됐다. 이 실패를 숨기거나 정상 로그 개수에 맞추려고 원본 CAN을 제거하지 않았다. vendor의 최소 4바이트 계약과 실제 기록에 맞춰 summary 4~8바이트/다른 지원 입력 8바이트로 구분한 뒤 새 소스로 재생했다.

| 익명 로그 | 정상 완료 레코드 | 실제 MyTrack 전달점 | 표본6 이상인 점 | 비영 aLead | 비영 jLead |
|---|---:|---:|---:|---:|---:|
| A | 479 | 246 | 162 | 162 | 142 |
| B | 990 | 115 | 74 | 71 | 67 |
| D | 930 | 6 | 0 | 0 | 0 |
| 합계 | 2,399 | 367 | 236 | 233 | 209 |

완료 record의 첫/완료 시각·실제 슬롯을 메모리에서 매칭했다. record 키 집합과 점 집합의 차이는 0이고 `dRel`, `yRel`, `vRel`, ground `vLead`는 원형 native 값을 Float32로 변환한 결과와 모두 일치했다. Float64→Float32 최대 절대 차이는 거리 9.37e-7m·횡위치 2.29e-7m·상대속도 2.31e-7m/s·ground 속도 1.17e-7m/s이며 물리 센서 오차가 아니다. 필수 6필드는 모두 유한했고 현재 MyTrack aLead/jLead와 반환값의 불일치도 0이었다.

fused를 선택해 실행한 최신 원형 upstream wrapper의 before `update`는 native 점을 반환한다. before `update_carrot`도 실제 Carrot Base를 실행했지만 self.pts/tracks가 비어 ground vLead와 가속도/jerk는 0이었다. 점 전체가 즉시 사라졌다는 결함으로 확대하지 않는다. 이 wrapper는 metadata=False이므로 before 위치·상대속도와 ground 기준을 분리해 비교했다.

원본 CS.radarInput의 exact batch·CAN 저장 순서·자차 속도/가속·receive 시각을 사용했다. gate now는 전체 저장 Event 헤더의 누적 최대값인 storage_max 가정이며 모든 입력/nested NS는 원본 epoch 그대로다. 실제 collector 수신·실행 지연이나 BOOTTIME/MONOTONIC 동일성은 미확인이다. 모델 5필드와 pose 4필드의 현재 wire 재해석 차이는 0이지만 전체 스키마 호환성 증명은 아니다. B의 staleEgoState 25회/D의 1회와 A/D의 순서 오류 각 1회는 보존했고 다음 정상 batch 전에 원형 재생성 경계를 따랐다. 새 수신기 CRC 실패는 0이었다.

앞서 CAN Event마다 직접 처리한 경로의 2,433레코드/369점과 원본 CS에 정확히 묶은 경로의 2,399레코드/367점은 입력 경계가 다르다. CS 범위 밖 CAN이나 거절된 batch를 몰래 보충해 개수를 맞추지 않았으며 두 결과를 같은 조건의 성능 비교로 쓰지 않는다.

같은 CAN을 packet별로 나눈 별도 합성 호출에서도 367점 6필드(aLead/jLead 포함)가 원본 CS batch와 같았다. 이 분할은 같은 원본 CS/receive를 반복한 API 감도 검사이며 실제 호출 주기나 독립 자차 표본이 아니다. 실제 accepted batch의 복수 정상 완료 record 사례는 0이므로 복수 record 계약은 별도 공개 합성 시험으로 검사한다.

현재 실제 DPath Controller를 원본 모델·pose로 2,792회 실행한 독립 모드 1은 A에서 175회 레이더 선행차를 선택했다. 원본 CP가 유도하는 -2는 0회다. 이는 Controller 단독 진단이며 전체 RadarD/SubMaster 건강·MPC·host 활성화·실차 제어를 한 연속 기록으로 입증한 결과가 아니다. 원본 carControl 15,358개는 enabled/longActive True 0, 기록 Panda 1,484표본은 controlsAllowed True 0이었다.

## PCM 모드0와 직접 종방향 변경

`ToyotaPcmSetSpeedSync`는 정확한 RAV4 2022·Toyota·PCM·직접 종방향·모드 0·유효 CAN에서만 관측한 순정 속도 변경이나 비활성→활성 전이를 카롯 기본속도로 반영한다. 최초 활성 표본은 기준만 저장하고 로컬 버튼·블루투스 입력이 같은 프레임에서 우선한다. 새 RES/SET CAN·버튼 이벤트를 생성하지 않는다. 다른 차량·순정 종방향·모드 1/2/3은 원형 동작을 유지한다. 앞차·커브·지도·카메라의 더 낮은 목표를 없애지 않는다.

직접 종방향 수치 보완은 정확한 RAV4 2022와 openpilotLongitudinalControl=True에서만 적용한다. 기존 Toyota 인터페이스의 명령 범위를 MPC와 최종 목표에 전달하고, 호스트 forceDecel을 당근 목표로 덮어쓰던 순서에서 목표 0을 유지한다. 이미 명시한 stopping·비양수 요청 중 이전 양수 가속/적분/P·D 보정이 다음 정규 0x343 CAN에 남는 경로를 막는다. 정규 frame%3 발행·재개·음수 적분·다른 차량/순정 경로는 유지한다.

현재 인터페이스가 반환하는 명령 범위는 해당 factory CP에서(-3.5,2.0)m/s²다. 새 물리 제동 능력이나 노면 마찰 값이 아니며 새 숫자로 하드코딩하지 않았다. forceDecel의 목표0 유지도 첫 CAN 즉시 최대 제동이라는 정책이 아니다. 기존 reset·순항 편안한 감속·명령 유지 틱과 신호 판단은 보존한다.

## 실행된 검사와 재현 경계

| 근거 | 실행 결과 | 한계 |
|---|---|---|
| 최종 공개 receiver 시험 | B4 체크섬 보강 후 53개 통과 | 실제 decoder/Base/MyTrack/capnp·합성 record. 미검사 wire header 의미·실물 firmware·전체 빌드가 아님. |
| 최종 실제 세 로그 재생 | B4 체크섬 보강 후에도 2,399레코드/367점, 레코드·슬롯 Float32 값 차이 0, 실제 B4 체크섬 오류 0. 동결 결과의 71개 전달 검사 실패 0 | source 32파일 전후 불변·vendor 9파일 원문 일치. 원본 제어 OFF·이미 개발에 사용한 세 로그. 보류 자료 성능/실차 안전 평가가 아님. |
| 최신 native·정지 시험 | 66개 통과, 별도 재실행도 동일 | 실제 Acados/Cython MPC·전체 planner/LongControl·Toyota 제어기/DBC. 가상 활성·합성 모델/센서·메모리 CAN. safety C TX hook/전체 host/물리 폐루프는 미실행. |
| PCM 공개 회귀 | 63개 통과 | 실제 순항 helper·PCM 클래스·전체 CarrotPlanner. 합성 CarState/서비스, MPC/CAN/실물 버튼은 미실행. |
| Toyota CP 생성 비교 | 74조건, 허용 외 필드 차이 0 | 빈 fingerprint/FW와 같은 요청의 생성자 비교. 실제 firmware 또는 37차종 전체 운용 회귀가 아님. |
| 별도 타차/공유 회귀 | 708개 통과, 프로세스 의존 2개 미검증 | 당시 receiver 49개와 함께 757개 통과했으나 receiver는 위 최종 53개로 따로 보고한다. 격리 DBC 생성/입출력 준비 후 component 회귀이며 전체 차량 검증이 아님. |

native 시험은 42개 종방향/24개 정지 시험을 합친 66개다. PCM과 합친 129개는 두 수집 순서에서 모두 통과했고 명시적 오프라인 선택 조건을 추가한 최종 129개 재실행도 통과했다. 반복 실행을 추가 커버리지로 합산하지 않는다. 기존 신호 fixture 3개도 별도로 통과했다. 초기 수집/메모리 Params 및 NumPy→Cap'n Proto fixture 실패와 정정 기록은 보존했다. 계산·solver를 가짜 성공 결과로 대체하지 않았다. CANParser는 Python backend, MPC solver는 실제 C/Cython이며 둘을 같은 native 검증으로 섞지 않는다.

최종 검토에서 B4 속도 payload에 합성 한 비트 손상을 넣고 원래 Toyota 체크섬을 유지했을 때 표준 CANParser는 거절하지만 수신기가 vRel에 반영하던 경계 결함을 확인했다. 기존 Toyota 체크섬 규칙으로 오류를 거절하고 이력을 초기화하며 정상 입력으로 복구하는 경로를 보강했다. 최종 수신기 source는 `e93450c08166e0f6e9c284a0a0fe7894f0e8d297791c3688c10f7ab432a014b8`이며 회귀 53개가 통과했다. 체크섬 정의가 없는 0x24나 다른 ARS 신호에 추측한 체크섬을 추가하지 않았다. 최종 source의 실제 세 로그 재생도 각각 479레코드/246점·990레코드/115점·930레코드/6점으로 같았고 실제 B4 체크섬 오류와 원형 대비 Float32 값 차이는 0이었다. 최종 재생은 앞선 DLC 보강 결과와 별도 실행으로 확인했으며 이전 결과를 소급해 바꾸지 않았다.

별도 타차/공유 시험에서는 초기 18개 환경 실패와 DBC 준비 assertion을 보존했다. 임시 DBC 2개 생성과 입출력 placeholder 준비 뒤 component 회귀가 통과했으며, 실제 Linux msgq/Params 프로세스가 필요한 2개는 검사하지 않았다. 환경 준비를 실제 차량 CAN 수신이나 전체 프로세스 성공으로 확대하지 않는다.

공개 시험 파일은 다음과 같다. 개발자의 개인 경로나 실제 로그를 하드코딩하지 않았다.

- `opendbc_repo/opendbc/car/toyota/tests/test_ars510_carrot.py`
- `openpilot/selfdrive/car/tests/test_toyota_pcm_mode0.py`
- `openpilot/selfdrive/controls/tests/test_rav4_longitudinal.py`
- `opendbc_repo/opendbc/car/toyota/tests/test_stopping_command.py`

프로젝트 공식 의존성과 `3.12.3 <= Python < 3.13` 환경을 준비한다. 원형 비교에는 `2ec25da3c10e369eaf4ad0313fde3280e5a8b06e`의 Git 객체가 필요하므로 source ZIP만으로는 실행할 수 없으며 정상 Git clone을 사용한다. `CARROT_OFFLINE_VALIDATION=1`을 해당 시험 프로세스에 명시해 오프라인 입출력 준비를 선택한다. 기본 전체 pytest 수집에서 전역 IO 대체물이 자동으로 개입하는 방식으로 사용하지 않는다. receiver 단독 미빌드 환경에서는 `tools/ars510_validation/offline_io.py`가 없는 Params 생성자를 거절하며 계산 코드는 그대로 읽는다. PCM/native 시험의 `native_runtime.py`는 운영 저장소/로그/소켓만 격리한다. receiver와 PCM 시험에는 MPC 빌드가 필요하지 않다.

명시적 선택 조건이 없는 기본 수집에서는 이 IO 격리를 쓰는 3개 시험 모듈을 의도적으로 건너뛴다. 이 skip을 알고리즘 통과로 세지 않는다.

고정 의존성 확인에서는 `pycapnp==2.1.0` 환경의 현재 receiver 53개와 native/PCM 129개를 합쳐 182개를 실행해 통과했다. 처음 혼합 실행의 Params 초기화 순서 실패는 보존했고, 새 프로세스에서 메모리 IO를 계산 모듈보다 먼저 준비해 정정했다. 별도 추가 재실행에 사용한 pycapnp 2.2.4 환경과 구분하며, 이 버전을 프로젝트의 권장 고정 의존성으로 바꾸지 않는다. 이 검사는 전체 공식 의존성 설치나 장치 빌드 검증이 아니다.

새 개발 clone에서 이 변경을 적용한 뒤 native 시험을 재현하려면 먼저 공식 SConscript의 solver target을 빌드한다. `c_generated_code`는 Git에 포함되지 않으며 완성된 디렉터리가 있다고 가정하지 않는다. 아래 절차는 운영 설치나 기존 검증 바이너리 폴더에서 실행하지 않는다. 같은 ABI/의존성 환경에서 기존에 없는 새 동결 디렉터리에 현재 Python과 생성 코드를 함께 복사하고 현재 source와 대조한다.

```bash
set -e
git cat-file -e 2ec25da3c10e369eaf4ad0313fde3280e5a8b06e^{commit}
scons -j2 openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/c_generated_code/acados_ocp_solver_pyx.so
MPC_VALIDATION_SNAPSHOT="$PWD/.validation-rav4-mpc-new"
mkdir "$MPC_VALIDATION_SNAPSHOT"
cp openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py "$MPC_VALIDATION_SNAPSHOT/"
cp -a openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/c_generated_code "$MPC_VALIDATION_SNAPSHOT/"
cmp openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py "$MPC_VALIDATION_SNAPSHOT/long_mpc.py"
```

`mkdir`는 기존 경로가 있으면 실패하도록 `-p` 없이 사용한다. 실패한 빌드·source 불일치·경로 충돌을 무시하고 파일을 덮어쓰지 않는다. 테스트 loader도 동결 Python과 현재 source의 본문 동등성을 다시 확인한다. 이 공식 SCons 명령 자체를 이번 검증에서 새로 실행한 것은 아니다. 보고한 native 시험은 현재 Python 본문과 같음을 확인한 실제 Acados/Cython solver 사본을 사용했으며 새 전체 프로젝트 rebuild 결과가 아니다.

```bash
PYTHONPATH="$PWD/opendbc_repo:$PWD" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 CARROT_OFFLINE_VALIDATION=1 \
CARROT_VALIDATION_BUILD="$MPC_VALIDATION_SNAPSHOT" \
python -m pytest --noconftest --rootdir=. --confcutdir=. -c tools/ars510_validation/pytest.ini -p no:cacheprovider -q \
  openpilot/selfdrive/controls/tests/test_rav4_longitudinal.py \
  opendbc_repo/opendbc/car/toyota/tests/test_stopping_command.py
```

receiver와 PCM은 repo 루트에서 각각 명시적으로 IO를 준비할 수 있다. 다음 예시는 계산 코드가 설치된 repo와 `opendbc_repo`를 Python 검색 경로에 포함한다.

```bash
PYTHONPATH="$PWD/opendbc_repo:$PWD" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 CARROT_OFFLINE_VALIDATION=1 python -c 'from tools.ars510_validation.offline_io import prepare; prepare(); import pytest; raise SystemExit(pytest.main(["--noconftest", "--rootdir=.", "--confcutdir=.", "-c", "tools/ars510_validation/pytest.ini", "-p", "no:cacheprovider", "-q", "opendbc_repo/opendbc/car/toyota/tests/test_ars510_carrot.py"]))'

PYTHONPATH="$PWD/opendbc_repo:$PWD" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 CARROT_OFFLINE_VALIDATION=1 python -c 'from tools.ars510_validation.native_runtime import prepare_io; prepare_io(); import pytest; raise SystemExit(pytest.main(["--noconftest", "--rootdir=.", "--confcutdir=.", "-c", "tools/ars510_validation/pytest.ini", "-p", "no:cacheprovider", "-q", "openpilot/selfdrive/car/tests/test_toyota_pcm_mode0.py"]))'
```

이는 운영 장치 fixture·원형 root conftest를 실행한 전체 빌드 성공 명령이 아니다. `/dev/null`을 pytest 설정 경로로 쓰지 않아 저장소 밖 상위 디렉터리까지 수집된 초기 환경 실패를 반복하지 않는다. 실제 로그 재생은 원본 서비스·CP·CAN metadata가 포함된 rlog가 필요하며 공유 결과에는 익명 개수/차이만 남긴다. `Vision Only` 문구가 바뀌었다는 이유로 정상 객체/제어 권한/실물 안전을 통과 처리하지 않는다.

## 포함하지 않은 기능과 남은 검증

이 PR은 이전 조사에서 다룬 근거리 기본 동작 변경, 공통 Panda 제어 권한 복원, 카메라 변경, 전체 신호 보조 또는 현대 Bosch 변경을 포팅하지 않는다. 최신 베이스의 타차·Bosch·신호 코드와 공유 필터를 유지하며 이전 조사 결과를 이번 PR의 실행 결과로 세지 않는다. σ/Q, age, 근거리·거리 문턱, 가변 dt, 물리 회생 제동 또는 외부 ACC 필터의 값을 추측해 조정하지 않았다.

실제 레이더 ECU/펌웨어 식별, 생성 CAN에 대한 현차/Panda 수신 권한, PCS/AEB 유지, 하이브리드 회생/마찰/엔진 제동 배분, 실제 제동력·충돌 회피, Konik 장치 전체 빌드와 실시간 실행 지연은 미완료다. 기존 alpha-longitudinal의 ECU 초기화 결정도 남아 있어 수신 패치만으로 PCS/AEB가 보존된다고 판단할 수 없다. 순정 hybrid 회생 자체와 openpilot 가감속 제어 활성 여부를 같은 기능으로 보지 않는다. 외부 Toyota Radar ACC Filter의 firmware·프로토콜·회생/PCS 보장은 확인하지 않았다.

다음 검증에는 부품/firmware 식별 근거, PCS/AEB 상태의 별도 검증, 활성/비활성·페달·취소 전이가 포함된 익명 CAN/상태 로그와 센서 취득·producer 발행·collector 수신 시각 구분이 필요하다. 이 자료 없이 소프트웨어 점 전달 성공을 실제 차량 제어 승인으로 확대하지 않는다.
