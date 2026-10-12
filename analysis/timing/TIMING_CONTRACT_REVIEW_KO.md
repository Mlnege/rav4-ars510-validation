현재 확인된 근본 문제는 **검증 도구의 실제 경과시간, 센서 자료 시각, 계획 발행 시각, 제어 반복 횟수가 같은 시간으로 다뤄지지 않는 것**이다. 322.9ms 뒤처짐의 실제 발생 원인은 아직 특정하지 못했다. 지금까지의 장시간 기능 검사에서 위반 0이라는 결과를 실시간 자료 유효성·실차 정지 안전의 입증으로 확대할 수 없다.

원형 코드로 54개 관측을 직접 실행했다. `contract_results.json`이 수치 근거이며, `probe_contract.py`는 실행 도구다. 원형 SubMaster/FrequencyTracker/Ratekeeper 클래스와 실제 LongControl·StateMachine·신호·계획 클래스를 사용했다. 소켓을 여는 생성자는 호출하지 않고 시작 수신 상태만 메모리에 구성했다. controls의 시간식과 card의 최종 적용 메서드는 원형 본문을 수정 없이 추출했다. card 검사에서 CI.apply/송신은 호출 기록만 남기는 입출력 대체물이며 실제 CarController/CAN/Panda 실행으로 해석하지 않는다. 별도 이전 C 검사와 혼동하지 않는다. 분석 대상 22개 파일은 실제 실행 사본과 줄끝 LF 정규화 후 동일했고, 검사가 추출한 원본 파일의 해시도 실행 전후 같았다.

**실제 앱의 단계별 시각과 차단 계약**

아래 경로와 행은 현재 동결 소스 기준이며 표에서는 `openpilot/` 접두사를 생략했다. `opendbc/`는 `opendbc_repo/opendbc/`를 뜻한다. 기준 upstream은 `0e4ee1bdbef3ad7284b136fddf31592e3f8a785f`; 로컬 보정본의 정확한 파일 해시는 JSON에 있다. `logMonoTime`은 메시지 겉의 시각이고 `timestampEof`는 영상 획득에 관한 내용 시각이다. 둘을 같은 의미로 읽으면 안 된다.

| 단계 | 사용하는 시각/주기 | 자료가 오래되거나 지연됐을 때의 현재 처리 | 예외 또는 빠진 연결 | 소스 근거 |
|---|---|---|---|---|
| 카메라 → modeld | 커널 SOF_BOOT_TS, EOF는 SOF+센서 readout 시간. C++ 메시지 헤더는 BOOTTIME | 카메라 수신/동기화·실행 진단이 있으며 modeld는 누락 frame ID를 세어 `frameDropPerc`에 반영 | 실제 노출/획득 시각과 메시지 발행 시각이 별개. 이번 검사에서 실물 센서/시계는 읽지 않음 | `system/camerad/cameras/spectra.cc:1418`, `:1573`; `cereal/messaging/messaging.h:49` |
| modeld → modelV2 | 약20Hz. Python 헤더는 추론 실행 후 `new_message` 호출 시 monotonic. EOF를 내용에 보존 | frame drop을 기록하며 selfdrived는 `frameDropPerc>20`을 modeldLagging으로 처리 | modeld의 행동 시점 보상은 `frame_delay=DT_MDL=50ms`, `action_delay=25ms`의 명목값. 실제 camera_age는 진단값. 헤더가 새로우면 오래된 EOF를 plan.processingDelay로 잡지 못함 | `selfdrive/modeld/modeld.py:466`, `:477`, `:505`, `:521`; `fill_model_msg.py:86`; `selfdrived.py:544` |
| modelV2 → plannerd | Toyota는 modelV2 업데이트가 계획 계산의 입력 시계. Hyundai만 별도 liveTracks 경로 | liveTracks 경로는 별도100ms 수신 검사와 레이더 유효성 검사. Toyota의 계산 진입은 updated/seen 확인 | Toyota 계산 진입 조건에 modelV2 원시 EOF 나이 상한을 찾지 못함. 이것만으로 전체 앱 결함이라고 단정하지 않음 | `selfdrive/controls/plannerd.py:46`, `:62`, `:86`, `:107` |
| 계산 → longitudinalPlan | 새 발행 헤더와 모델 헤더의 차이를 `processingDelay`로 저장. solver/전체 계획 시간을 따로 저장 | `plan.valid`는 carState/controlsState/selfdriveState의 all_checks | 이 valid 식에는 modelV2/radarState가 직접 포함되지 않는다. processingDelay의 직접 차단 소비자는 controlsd/card/LongControl에서 찾지 못함 | `controls/lib/longitudinal_planner.py:467`, `:470`, `:472` |
| 신호 관측 → 계획 보조 | moving red 관측200ms, 기반 서비스 수신250ms, pose 수신/자료200ms, camera 수신250ms | 실제 현재 시각으로 읽으면 오래된 관측/pose/context를 거절. 최종 prepare 적용도 지난 호출 이후 경과가200ms 초과이면 해제 | runtime 판단은 계산 초반, 최종 제한은 계산 뒤에 있다. elapsed는 관측 자체 나이가 아니다. 최초 helper 호출은 명목dt를 기본값으로 사용하므로 전체 시간 출처 계약을 대신하지 못함 | `carrot/signal_assist_runtime.py:88`; `signal_stop_prepare_runtime.py:96`, `:108`; `signal_stop_prepare.py:215`; `longitudinal_planner.py:380`, `:391`, `:398` |
| 정지 빨간불 출발 억제 | stopped red/green 관측650ms, 같은 물체 확인 등 | 오래되거나 불확실하면 확인 상태를 버려도 기존 빨간불 hold를 유지하며 오래된 green이 출발을 허용하지 않음. gas/비활성/잘못된 gear는 별도 원형 정책 | moving 보조200ms와 목적이 다르다. 자료가 오래됐다는 이유로 held red를 강제로 해제하면 안전 조건을 약화시키므로 금지 | `carrot/signal_start_guard.py:58`, `:97`, `:144` |
| longitudinalPlan → controlsd | 약100Hz. 계획 나이는 `(sm.frame-recv_frame)*10ms` | CC.longActive는 selfdriveState.enabled/overrideLongitudinal/CP.openpilotLongitudinalControl로 결정. 비활성이면 LoC reset | 반복 횟수는 실제 경과시간과 다를 수 있고, 새로 도착한 오래된 계획은 frame 나이0이다. 계획 processingDelay/EOF/valid를 이 식에서 직접 검사하지 않음 | `controls/controlsd.py:142`, `:160`, `:178`, `:183` |
| LongControl → 가속 수치 | aTarget/vTargetNow/shouldStop 및 활성 상태, 명목 DT_CTRL | 비활성은0. stopping/starting 상태는 원형 ramp/state. coasting 완화만 t_since_plan<=200ms 조건 | 보통 가속/감속 출력에는 t_since_plan 또는 processingDelay로 직접 해제하는 조건을 찾지 못함. standalone active=True 사례이므로 상위 앱 권한까지 통과했다는 뜻은 아님 | `controls/lib/longcontrol.py:133`, `:159`, `:183`, `:198` |
| controlsd → carControl | 발행 헤더는 새 monotonic. controlsState에는 계획 헤더를 따로 보존 | carControl/controlsState 메시지 valid는 CS.canValid | 새 제어 헤더만 보고 원래 계획/카메라 나이를 알 수 없다. 코드의 TODO도 all_checks와 순환 의존성을 언급 | `controls/controlsd.py:420`, `:425`, `:429`, `:453` |
| card → CI.apply/CarController | card 약100Hz; CarController의 일반 Toyota ACC는3회 호출마다 생성 | 최종 경계는 carControl all_alive. ImpactDashcamReboot는 명시 비활성. lateral startup은 별도 gate. 모델/레이더는 valid/alive가 아니면 None | card의 controls_update는 carControl.valid/freq_ok를 직접 조건으로 쓰지 않는다. carOutput.valid는 all_checks지만 실제 apply 조건과 다름. 본 검사에는 CI.init 호출0, 실차 송신0 | `car/card.py:312`, `:341`, `:351`, `:373`, `:375` |
| selfdrived → 활성 상태 | 수신 health·평균주파수·자체 Ratekeeper·frameDrop 등. 약100Hz | generic commIssue/AvgFreq/selfdrivedLagging/modeldLagging은 NO_ENTRY+SOFT_DISABLE. 지속시 명목3초 후 비활성, forceDecel도 별도 계산 경로 | 모든 지연이 즉시 종방향 권한을 끄는 방식이 아니다. soft-disable 기간에는 enabled/active가 참이다.3초 역시 반복 카운터라 실제 느려진 루프와 차이 가능. 초기화/모델 settling 등의 다른 분기도 있음 | `selfdrived/selfdrived.py:422`, `:463`; `events.py:920`, `:953`; `state.py:7`, `:43`, `:109`; `controlsd.py:436` |
| Panda C 안전 판정 | MCU 수신 타이머·차량 CAN checksum/주기·운전자/ACC 상태·명령 부호/한계 | 실제 RX 건강/권한/가스·브레이크/범위를 검사하는 별도 안전 계층 | CAN 명령에는 호스트의 modelV2/plan/영상 출처 시각이 없으므로 해당 데이터 나이를 Panda가 검증했다는 주장은 불가. 기존 Panda 권한 복원은 유지 | `opendbc/safety/safety.h:164`; `safety/safety_toyota.h:25` |

SubMaster의 alive는 **마지막 수신부터 지금까지**를 검사한다.20Hz modelV2/longitudinalPlan은10주기=500ms,100Hz carControl은100ms 미만이다. 이는 센서 내용의 생성 나이가 아니다. FrequencyTracker는20Hz 기준 최근 약1초/장기약10초 수신 간격 평균을 쓰며 한 창이 유효하면 통과한다. 저주파·ignore 목록·SIMULATION 등의 예외는 소비자마다 다르다. 실제 검사에서는 simulation=False, ignore 목록 빈 상태로 원형 판정을 실행했다. `cereal/messaging/__init__.py:139`, `:145`, `:160`, `:265`, `:274`, `:287`이 근거다.

**직접 실행에서 확인한 차이**

| 오류 입력/실행 | 관측 결과 | 이 결과가 뜻하는 범위 |
|---|---|---|
| 원형 SubMaster에 정규 주기로 계속 수신하지만 헤더는322.9ms 또는1초 오래되게 전달 | alive/freq_ok/valid/all_checks 모두 참 | 수신 건강은 원래 자료의 생성 나이 검사가 아님 |
| modelV2 또는 plan을322.9ms 추가 미수신 | alive 참.501ms에는 거짓 | model/plan의500ms 수신 정책. 전체 제어 권한을 개별적으로 측정한 결과는 아님 |
| carControl99ms/101ms 미수신 | 99ms 참/101ms 거짓 | 별도100ms 수신 경계가 실제로 있음 |
| 실제322.9ms sleep을 현재 frozen ReplayClock 안에서 실행 | 실제 경과323.19ms, CPU0.191ms, 합성 monotonic 경과0, processingDelay0, plan.valid 참 | 검사 도구가 실제 경과를 자료 나이로 전하지 않는 결함을 직접 재현. 장시간 worker의322.91ms 실제 원인은 재현한 것이 아님 |
| 센서 헤더/recv_time은 그대로 두고 합성 현재 시각만322.9ms 전진 | 원형 신호prepare runtime.valid/prepare_control_active 거짓, processingDelay322.9ms | 실제 나이를 원형 판단에 전달하면 신호 보조 차단을 시험할 수 있음. 이 사례의 plan.valid 참은 기존 harness의 캐시 health flags 조건이며 실제 SubMaster 결과와 분리 |
| 새 modelV2 헤더에 오래된 camera EOF를 담아 원형 publish | processingDelay0, plan.valid 참 | processingDelay는 capture-to-control 총지연이 아님 |
| 원형 publish에 modelV2/radarState valid=false | plan.valid 참. carState/controlsState/selfdriveState false는 plan.valid 거짓 | 직접 의존성 mask를 실행으로 확인. selfdrived의 별도 catch-all을 배제한 부분 검사 |
| standalone LongControl active=True, plan age/processingDelay0~4초, 목표±1 | 일반 출력은±1 유지 | 단독 age cutoff 부재. 실제 앱에서4초 내내 활성이라는 주장 금지 |
| 최종 moving-prepare 적용의 elapsed199ms/201ms |199ms에는 완만한 감속 cap,201ms에는 기본 목표로 복귀 | elapsed gate는 원형 동작. 빨간불 정지 hold 해제와 다른 경로 |
| 실제 StateMachine에 네 통신/지연 이벤트를 지속 입력 | 첫 호출은 softDisabling이며 enabled/active 참.301번째 호출에서 비활성 | 명목3초 지속 해제 계약. 원형 update_events 전체와 하드웨어를 실행한 검사는 아님 |
| 원형 card.controls_update, carControl alive=true, valid=false 또는 freq_ok=false | CI.apply IO sink를1회 호출. alive=false면0회 | card 경계의 명시 조건 확인. 실제 Toyota CAN/Panda 통과 검사로 해석하지 않음 |
| 원형100Hz Ratekeeper에322.9ms 경과 주입 | lagging property 참. print_delay_threshold=None일 때 monitor_time 반환은 거짓 | 반환값과 lagging property가 다름. 실제 selfdrived는 property를 소비. controlsd/card의 monitor_time 자체는 즉시 권한 gate가 아님 |

**측정 문제, 운영체제 대기, 알고리즘 계약의 구분**

현재 paced 도구의 `execution_max`는 `harness.step` 전후만 측정한다. 사례가 바뀔 때의 NativeSignalHarness 생성은 그 앞에 있고, CSV 쓰기/flush와 psutil 읽기는 그 뒤에 있다. control lateness는 처음 정한 전체 벽시계 일정과 비교하므로 이 구간들을 포함한다. 따라서 최대 step52.76ms와 control lateness322.91ms는 서로 모순이 아니며, 그 차이를 전부 MPC 시간 또는 운영체제 문제로 몰면 안 된다. `tools/ars510_validation/signal/native_signal_can_paced.py:60`, `:95`, `:108`, `:141`이 측정 위치다.

`input_clock`은 monotonic/time을 합성 시각으로 바꾸고, `SchemaInputs.touch`는 모든 서비스의 헤더·수신시각·pose 시각을 한 번에 새로 쓴다. 실제 일정이 뒤처져도 step 인자로 다시 명목 schedule을 넣는다. 같은 스레드에서100Hz 제어를 기다리는 동안 이 합성 시각은 진행하지 않는다. `time.monotonic_ns`나 perf_counter까지 같은 방식으로 바뀌는 것도 아니다. 기능 계산은 실제 코드지만 자료의 실제 나이와 독립 프로세스 간 대기는 모델링하지 않는다. 기존35분/61분 검사 결과를 폐기하는 것이 아니라 **계산 기능, 실제 호출 간격 측정, 자료 기한 준수**를 구분해야 한다. `native_signal.py:77`, `:162`, `:181`; `core.py:136`; `native_signal_can_paced.py:89`, `:110`이 근거다.

가상 차량도 LongControl 호출마다 명목10ms로 이동한다. 실제로 호출이323ms 멈춰도 그동안의 실제 차량 운동을 적분한 검사는 아니다. 누락한 실제 경과를 임의로 더해 검사를 통과시키거나, 모델상의 정지 결과를 실제 AEB/회생/제동 성능으로 확정해서는 안 된다. 기존 가상 입력·응답 모형의 결과는 해당 가정 아래에서만 해석한다.

이 WSL Python의 monotonic/perf_counter는 실제로 `CLOCK_MONOTONIC`을 사용했고 scheduler policy는 SCHED_OTHER(0)였다. 장치용 코드의 FIFO/CPU affinity는 PC에서 적용되지 않는다. sleep은 운영체제의 다른 작업 때문에 요청보다 길어질 수 있으며, perf_counter는 대기 시간도 포함한다. CPU 시간과 벽시계 시간을 따로 측정해야 계산 부담과 대기 부담을 구분할 수 있다. 이 운영체제 API 의미는 [Python 공식 time 문서](https://docs.python.org/3.12/library/time.html)가 근거다. 실제 worker의322.91ms가 파일 쓰기·생성·스케줄링 중 어디서 생겼는지는 새 단계별 계측 전까지 미확정이다.

C++ 카메라/메시지의 BOOTTIME와 Python MONOTONIC도 별개다. Linux에서 MONOTONIC은 suspend 중 멈추고 BOOTTIME은 suspend를 포함한다. 현재 WSL의7개 동시 샘플에서는 샘플링 불확실도 수준의 차이만 관측됐다. 실제 Konik의 Python 빌드·절전 이력을 읽은 결과가 아니다. 이것을322.9ms의 원인으로 확정하거나 시계를 통째로 바꾸지 않는다. API 의미는 [Linux 공식 시간 API 문서](https://docs.kernel.org/core-api/timekeeping.html), 소스는 `common/timing.h:12`, `cereal/messaging/messaging.h:49`, `cereal/messaging/__init__.py:45`이다.

**다음 검증과 수정 계획 제안 — 아직 코어 변경 없음**

1. 별도 계측 도구에서 생성/계획/제어/CAN 인코딩·디코딩/CSV·flush/psutil/대기 깨움을 각각 벽시계와 스레드 CPU 시각으로 기록한다. sensor acquisition, producer header, receiver receive time, processing end, actuator callback start를 별도 필드로 둔다. 오래된 body를 touch/new_message로 새 자료처럼 만들지 않는다. 독립 source/receiver 역할을 두고 원형 SubMaster.update_msgs로 health를 갱신한다. 현재 진행 중인 두 worker와 .so는 바꾸지 않는다.
2. 정상 반복뿐 아니라300ms 단발 지연, 지속 지연, 같은 오래된 body의 재발행, 모델만 정지/계획만 정지/제어만 정지, 데이터 도착 순서 역전, source/receiver 시계 차이를 구분해 원형 전체 이벤트→StateMachine→CC.longActive→card 적용 경로에 전달한다. 실제 carControl/Panda 권한까지 확인하기 전 LongControl 단독 결과를 실차 결함이라고 명명하지 않는다. 잘못된 green 또는 stale 때문에 빨간불 hold를 풀지 않는다.
3. 이 재현 결과를 검토한 뒤에만 적용 기한을 어느 단계가 책임질지 명시한다. 예를 들어 원본 시각과 수신 시각을 보존해 제어 경계에 전달하고, frame×10ms를 실제 경과와 혼동하지 않게 하는 방안을 검토한다. 임의로200ms를 모든 제어의 해제 기준으로 넣거나, selfdrived3초 정책/stock-long/driver override/정지 hold를 건너뛰지 않는다. 후보 패치는 정상 경로의 기존 CAN 배열 보존, 다른 Toyota/다른 제조사 회귀, 비활성·가스·브레이크·계획 손실·타임아웃을 먼저 비교해야 한다. 코어 수정 계획은 부모 검토 후 별도 파일 소유권을 받아 실행한다.

실물 clock 차이, 실제 camera-to-model/plan-to-CC/CC-to-card 분포, 송신하지 않는 수신 전용 관측에서의 ECU/PCS/AEB 상태는 추가 확인이 필요하다. 본 작업은 새 작업 폴더의 도구·보고서만 작성했고, 차량·운영 Params·Panda·장치/환경 파일·기존 동결 계산 소스는 변경하지 않았다.
