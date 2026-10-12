# 전체 호스트·신호2 연결의 스키마와 입출력 읽기 검토

2026-10-12 20:38 KST 기준 읽기 검토다. 이번 단계에서는 새 시험이나 생산 코드 변경을 하지 않았다. 작성 파일은 이 문서 하나이며, B 담당자의 통합 도구·기존 helper·원본 결과·native binary를 변경하지 않았다. 이전 23조건 부분 신호 시험의 값은 직접 보존한 결과를 읽었고, B의 가스 override 결과는 담당자의 전달 결과로만 구분한다.

이번 설정의 “0/20/AlphaTrue/Signal2”는 메모리에서 `SpeedFromPCM=0`, `LongActuatorDelay=20`, `AlphaLongitudinalEnabled=1`, `SignalAssistMode=2`를 뜻한다. SignalAssistMode0과2를 동시에 켜는 의미가 아니다. 그 외 설정은 원형 기본값 및 이미 승인한 IO 조건을 명시해야 한다. 실제 CP flags, enabled/active/longActive, all_checks, Panda 권한을 True로 고정해서 기준 상태를 만들면 전체 권한 연결 검사가 성립하지 않는다.

처음 요청 경로 `work/signal_host_can_integration/IO_SCOPE.md`는 없었고, 담당자가 작성한 실제 파일 `IO_SCOPE_PLAN_KO.md`를 이후 읽었다. 이 계획은 원형 수신기/메모리 설정 보존, knownOX metadata, 모델 geometry, 원형 publisher/runtime, 비활성에서 자연 PCM enable, 가스 시작 5phase와 관측 발행 전후 비교를 명시한다. 이 검토의 주요 충돌·누락 항목도 계획에 반영됐다. 아래 내용은 source와 계획의 대조이며, 아직 실행하지 않은 새 통합 도구가 이 목록을 만족한다고 승인한 결과가 아니다.

## 실제 수신기와 권한 체인을 보존하는 연결

`work/timing_rootcause/whole_io.py:158`의 `memory_messaging`은 원형 new_message/수신/SubMaster/FrequencyTracker/PubMaster 본문을 로드하고 소켓만 메모리로 격리한다. 실제 SubMaster는 처음 seen=False, valid/alive/freq_ok가 정규 서비스에서 False이고, 메시지 수신으로 이를 계산한다(`cereal/messaging/__init__.py:173-195`, `:249-276`). 정상 서비스 입력과 실제 20/100Hz의 합성 시간 진행으로 상태가 만들어져야 한다. runtime baseline을 위해 이 수신 metadata를 직접 True로 대입하면 안 된다.

전체 체인의 시작은 원형 SelfdriveD 비활성·정상 health 초기화→실제 PCM/button event→StateMachine→SelfdriveState 발행→Controls→CC→card→Toyota 제어기→실제 C 안전 hook의 순서로 구분한다. CI.init는 승인된 물리 IO sink에서 호출 기록만 남기고 실제 UDS/ECU 초기화는 하지 않는다. C의 controlsAllowed는 정상 checksum/주기 RX로 도출하고 setter로 True를 주입하지 않는다. 합성 source의 센서 정상/유효 필드를 입력하는 것과 판정 결과를 고정하는 것은 다르다.

**NativeSignalHarness 모듈을 B에서 직접 import하는 것은 피해야 한다.** `tools/ars510_validation/signal/native_signal.py:19-24`는 import 시 `offline_io.prepare(solver_overlay=True)`를 호출한다. 이 함수는 messaging.SubMaster를 UnusedSubMaster로, Params를 MemoryParams로 바꾼다. 이미 만든 B의 원형 SubMaster·MemoryConfiguration을 덮으면 whole-host 연결의 IO 계약이 깨진다. B가 동일 프로세스에서 필요한 합성 스키마 필드만 새 IO builder에 명시하고, 원형 Runtime/CarrotPlanner를 B의 messaging 설치 후 import하는 방식이 적합하다. 계산 helper나 그 함수의 반환값을 재작성하는 권고가 아니다.

`SignalPrepareRuntime`은 원형 CarrotPlanner 생성 시 기본 연결된다(`carrot_functions.py:66-83`). 자신의 보조 SubMaster를 `liveCalibration/roadCameraState/deviceState`에 만들어 수신한다(`signal_stop_prepare_runtime.py:87-89`). B가 이 생성자에서 원형 memory_messaging을 사용하게 하면 별도 실제 수신기가 동일 메모리 버스의 metadata를 받을 수 있다. 이를 h.sm 같은 강제 metadata 묶음으로 바꾸거나 `extra.all_checks=True`로 대체할 필요가 없다.

## 정상 신호 기준 상태에 필요한 입력

| 항목 | 현재 source 계약 | 합성 입력 준비와 관측 |
|---|---|---|
| 원형 메시지 공통 | Python new_message 기본 valid=False, 헤더=`int(time.monotonic()*1e9)` (`messaging/__init__.py:41-54`) | 명시적 정상 sensor fixture만 valid=True로 발행. disabled/invalid 사례에서는 원래 필드·헤더를 보존하고 변화를 기록. 수신기는 헤더/recv_time을 따로 기록 |
| SignalMode2 | `signal_mode.py:24-50`의 .5초 설정 재확인. start/prepare 플래그는 mode>0, retired assist_enabled는 항상 False | 메모리 설정을 원형 생성 전에 넣고 해당 시각에 실제 읽도록 진행. 캐시/활성화 시점은 기록. legacy moving assist와 mode2 prepare를 합치지 않음 |
| 기본 context 서비스 | carState/modelV2/radarState/selfdriveState/carControl 모두 seen/valid/alive 및 `0<=now-recv_time<=.25` (`signal_assist_runtime.py:76-80`) | 본래 서비스 스키마·원형 SubMaster 수신 결과로 만족시킴. no-lead radarState 메시지는 입력 상태이며 실제 레이더 객체 증거가 아님 |
| context enabled/drive | `feature enabled AND sd.enabled AND cc.longActive`, canValid, 기어 drive | sd/CC는 원형 host가 발행한 값을 사용. 동일 phase의 gas/brake/override 및 제어기 상태도 함께 기록 |
| CarState | canValid, 기어 drive, 유한 vEgo/aEgo/vCruise, gas/brake/blinker/steer 상태, 실제 PCM available/enabled | 정상 입력 수신으로 health/enable을 도출. 신호 moving prepare는 `5/3.6<speed<82/3.6`, 정지 guard 신규 진입은 abs(speed)<=.3 |
| modelV2 계산 배열 | position.x/velocity.x/acceleration.x가 ModelConstants.IDX_N=33, orientationRate.z 등 기본 계획 입력 (`longitudinal_planner.py:120-145`) | 미래 진행·모델 정지 의도를 명시적으로 구분. 정지 차량 진행 검사에는 향후 진행 궤적을 넣어야 하며, 계산 결과를 강제로 go로 만들면 안 됨 |
| model geometry | roadEdges 2개 및 stds, laneLines 4개 및 probs/stds, 각 x/y/z의 동일 길이·유한값·오름차순 x (`signal_stop_prepare.py:18-78`) | known fixture는 road y=-4/+4, std=.2, lane y=-5.4/-1.8/+1.8/+5.4, probs=.9/std=.2, z=0, x=0..200. 현 whole_inputs의 geometry 누락을 보충할 경우 합성 입력으로 명시 |
| liveCalibration | seen/valid/alive/recv age<=2, calStatus=calibrated, 유한 rpyCalib 3개 | known fixture rpy=[0,0,0]. 실제 차체 보정의 증거가 아님 |
| deviceState/roadCameraState | 각 seen/valid/alive, device age<=2, road age<=.25 | knownOX는 deviceType=tizi, sensor=ox03c10. actual frame width/height/stride를 처리하지 않는 메모리 시험에서는 영상 호환 확인으로 말하지 않음 |
| livePose | 수신 age<=.2, pose.timestamp age<=.2, inputsOK/posenetOK/sensorsOK, angularVelocityDevice.valid 및 orientationNED.valid (`signal_stop_prepare_runtime.py:106-124`) | known fixture angular x/y/z=0, std=.001, 각 std 유한·>=0. 회전/불확실도 계산 원형 유지. 실제 센서 잡음 측정이 아님 |
| geometry 회전 | calibration 변환 후 yaw abs<=1.5deg/s, std norm<=2deg/s | known fixture는 범위 내. 불충족하면 context turning/invalid 판정을 그대로 유지 |
| OX 관측 좌표 | JSON size=[1344,760], source_size=[1928,1208], coordinate_transform=full_frame_resize | 공식 DEVICE_CAMERAS의 tizi/OX forward K를 `diag(1344/1928,760/1208,1)@K`로 쓰는 원형 함수를 유지. crop/회전/다른device는 거절 |
| signal JSON 공통 | version=1, stream=road, 비어 있지 않은 session, 증가 frame_id/timestamp, 최대32768 bytes | 원형 publisher→메모리 파일/명시적 IO 경로→원형 runtime read. 권한 판정 함수/관측 파서를 mock하지 않음 |
| start 관측 | 원형 publisher는 box/raw를 전달, fresh red 150ms/2표본, green 700ms/3표본 확인. MAX_AGE=.65/MAX_GAP=.7 (`signal_start_guard.py:118-141`) | 같은 상자를 유지한 red→green/unknown, restart/session/newbox/reorder를 별도로 구분. 초록은 veto 제거일 뿐 출발 요청을 발행하지 않음 |
| prepare 관측 | tracks에 id,box,age=0,state=red/green,observations>=3,evidence.raw=state/source=detected/quality .5..1. red_score .4..1/green_score<.08 | known 단일 red는 box=[667,260,707,270], id=1,observations=10,quality=.9,red_score=.9,green_score=0. 이것은 인식 모델 출력 형식의 합성값 |
| prepare 확인 | obs age<=.2, gap<=.25, 동일 신호 id의 4 fresh 표본 이상 및 .6초, 형상/거리/차로 corridor 유효 | 새 신호 id에 기존 확인 시간을 상속하지 않음. 신호거리25..140은 상자 크기·장착 높이 가정의 가능 범위이며 실측 정지선 거리가 아님 |
| 최종 prepare cap | active/mode2/reset 없음/gas·brake·lead 없음/elapsed<=.2/shouldStop 아님/mpc acc (`longitudinal_planner.py:390-409`) | 약-.5m/s²까지 .25m/s³로 변화하는 완만한 감속. 신호 전체 정지·실차 제동능력의 증거가 아님 |

추가 Carrot 준비 조건은 High 운전 모드 아님, trafficLightDetectMode!=0, mode=acc, traffic_starting_count=0, user_stop_distance<0, 모델 stopping 상태 아님이다(`carrot_functions.py:711-730`). 이를 직접 덮어 baseline을 만들기보다 원형 기본 설정/정상 입력에서 도출하고, 만족하지 않으면 원인을 기록해야 한다. 정지 StartGuard 기준과 moving Prepare 기준은 속도·모델 정지 의도가 달라 동일한 한 표본에서 모두 active=True를 요구하면 안 된다.

## 서비스·시간·관측 이력의 함정

원형 SERVICE_LIST는 carState/carControl/selfdriveState 100Hz, modelV2/radarState/livePose/roadCameraState 20Hz, liveCalibration4Hz, deviceState2Hz다(`cereal/services.py:37-87`). 원형 SubMaster alive는 `현재-마지막수신<10/frequency`, freq_ok는 실제 수신 간격의 FrequencyTracker이며 runtime의 별도 .25/.2초 나이 조건과 같지 않다. 프레임을 매 계획마다 발행한 스키마 fixture의 성공을 모든 실제 서비스 주파수가 정상이라는 증거로 쓰지 않는다. B는 SERVICE_LIST 주기에 따라 발행하고, 원형 poll/conflation을 유지하면서 결과를 기록해야 한다.

Mode 활성화와 Prepare mode_since는 이전 관측을 버린다(`signal_assist_runtime.py:44-63`, `signal_stop_prepare_runtime.py:77-86`). 생성 직후 mode2·context enabled가 확인되기 전에 발행한 EOF는 mode_since보다 과거일 수 있다. baseline 전에 충분한 정상 수신/확인 시간이 필요하며, 오래된 관측 timestamp를 새 시각으로 바꾸어 이를 통과시키면 안 된다.

NativeSignalHarness의 SchemaInputs는 모델 궤적을 만들지만 modelV2.timestampEof/frameId를 쓰지 않아 기본0일 수 있다(`signal/core.py:83-150`, `native_signal.py:140-170`). 그 상태도 start/prepare context를 통과한다. 현재 runtime은 observation의 자체 timestamp/frame/session을 검사하고 modelV2 EOF와 signal frameId의 동등성을 직접 검사하지 않는다. 그러므로 B는 model/road/signal 각 EOF·frameId·producer 헤더·수신 시각을 명시적으로 보존해야 한다. 기존 native 기준 상태 성공은 같은 영상에서 나왔다는 출처 이력의 증거가 아니다. 없는 cross-reference guard를 시험 도구에 구현해 생산 코드의 거절 동작으로 보고해서도 안 된다.

다음 시각은 별도 열로 기록하는 것이 적합하다: consumer now, model producer header/EOF/frameId, road header/EOF/frameId, signal acquisition timestamp/frameId/session, 각 SubMaster recv_time, pose.timestamp, plan header/modelMonoTime/processingDelay, CC header 및 card의 수신/최종 정규 CAN 생성 시각. Ns 정수와 초 float 변환은 1ns 미래 입력을 인위적으로 만들지 않도록 동일 생성 계약을 사용한다.

현재 Python model/plan 메시지 헤더는 MONOTONIC이지만 camerad EOF는 BOOTTIME이다. livePose의 body timestamp도 단순 Python 발행 시각이 아니라 kf.t에서 나온다(`locationd.py:250`); cameraOdometry 처리 시 EOF에서 지연을 빼서 필터 시각으로 쓰는 경로가 있다(`:168-170`). 실제 장치에서 source clock의 원점·resume 전후 차이를 확인하지 않은 채 서로 뺀 값을 물리적인 획득 나이로 단정하면 안 된다. 합성 검사에서는 같은 합성 시계 영역으로 fixture를 배치했다는 한계를 명시한다.

`SourceModelTimestampClock` 이름은 이번에 읽은 생산 신호 모듈과 기존 helper에 존재하지 않았다. 계획된 시간 IO wrapper를 뜻한다면 **모델 헤더/EOF에 consumer now를 계속 맞추는 방식**을 stale 시험에 사용하지 않아야 한다. 모델 producer가 멈추면 그 시계도 멈춰서 signal/pose 나이가 증가하지 않을 수 있고, whole-host 실제 대기 뒤에도 frozen-clock 효과가 생긴다. stale model EOF로 now를 뒤로 돌리면 clock discontinuity와 수신 나이를 시험도구가 만들어낸다. 이는 생산 알고리즘 결과가 아니라 시계 IO 계약 오류다. baseline의 합성 현재와 고장 사례의 실제 경과/원본 헤더 보존을 분리하고, 시계 원점 차이를 알고리즘 hotfix로 숨기지 않는다.

## CC-only 비활성과 자연 가스 override의 차이

직접 완료한 23조건 부분 시험은 **gas=False**이며 sd.enabled=True인 상태에 CC.longActive만 False인 합성 입력을 줬다. 500ms 뒤 red 재개 시150ms 확인 창에서 양수 LongControl 출력이 나왔고, unknown/green은2초 관측 내 hold 복구나 green release 이벤트 없이 원형 모델 진행 의도가 반영됐다. 이 시험은 운전자가 출발 의도를 표시하지 않은 국소 차단·복귀의 반례다. 실제 header guard나 전체 host의 자동 재활성화가 동일 반례를 만들었다고 확정하지 않는다.

B가 별도로 전달한 Mode0 호스트+Toyota/C 검사에서는 정상 gas input으로 overriding/enabledTrue/activeTrue/CC.longActiveFalse가 만들어지고, gas 해제 후 PCM off/on 없이 enabled/CC.longActiveTrue로 복귀했다고 한다. 이 검토자는 그 실행을 새로 재현하지 않았다. 이 결과는 원형 host가 sdTrue/CCfalse 상태를 만들 수 있다는 근거지만, Signal2 red hold까지 연결한 검사 결과는 아니다.

원형 source에서는 `car_specific.py:240-241`이 gasPressedOverride를 만들고, `events.py:790-796`은 overrideLongitudinal을 지정한다. StateMachine overriding→enabled 복귀는 override event가 사라지면 일어난다(`selfdrived/state.py:84-89`). Controls의 longActive 식은 이 event와 CP 조건을 쓴다(`controlsd.py:160`). 이는 운전자 의도가 있는 기존 정책이므로 국소 freshness 차단과 동일시하거나 자동 회복을 새로 구현할 근거로 쓰면 안 된다.

특히 StartGuard의 분기 순서는 **enabled=False reset/return→gas=True reset+10초 cooldown**이다(`signal_start_guard.py:144-153`). planner가 새 gas와 이미 False인 CC를 받으면 먼저 return해 10초 cooldown을 설정하지 않는다. 새 gas와 이전 True CC를 먼저 받는 계획 틱에서는 gas 분기로 cooldown을 설정한다. Prepare는 gas/brake cooldown을 enabled 검사보다 먼저 설정한다(`signal_stop_prepare.py:247-251`). 따라서 “가스면 항상10초 대기”라고 일괄 보고할 수 없다.

이 순서 반례는 이번 단계에서 source로 확인한 조건이며 whole-host+Signal2에서 아직 직접 실행한 결과가 아니다. B의 step은 card→planner→selfdrived→Controls 순서이고 실제 앱은 독립 프로세스라 서비스 도착 순서가 달라질 수 있다(`whole_chain.py:74-86`). 가스 시작을 model20Hz에 정렬한 경우와 10ms/다른 phase로 시작한 경우, gas release와 명시적 cancel/brake를 분리해 실제 runtime enabled/valid, guard.cooldown/last_now/hold/session/box, Prepare cooldown, CC/selfdrive 상태 및 마지막 CAN을 기록해야 한다. 후보에 맞추어 권한 값을 덮어 넣는 검사는 피한다.

## 실행 전 확인 목록과 남은 한계

1. 신호 모듈을 import한 뒤에도 B의 원형 SubMaster/MemoryConfiguration 설치가 유지됐는지 확인한다.
2. 소켓 없는 실제 수신기 생성부터 정상 주파수·valid·seen이 생기고, SelfdriveD 초기화·PCM enable·C RX 권한이 원형대로 도출되는지 기록한다.
3. stopped-red guard와 moving prepare를 별도 정상 기준으로 먼저 확인한다. context/geometry/관측·확인 시간 중 막힌 조건을 기록하고 완화하지 않는다.
4. 같은 관측 상자·session·id를 유지한 red/green/unknown, source invalid/receive stale/header stale/old EOF/clock change를 구분한다. 새 header가 old body를 최신으로 보이게 만드는 사례를 그대로 보존한다.
5. driver gas/cancel/brake와 국소 CC-only 차단을 동일 복귀 권한으로 취급하지 않는다. 가스 onset phase와 각 cooldown 값을 보존한다.
6. 실제 native MPC, Python LongControl/CarController/CANParser, 실제 C safety hook, IO sink를 메타데이터에서 각각 표시한다. C hook 통과는 물리 Panda/MCU heartbeat·ECU 제동 성능·PCS 유지·인식 정확도 검증이 아니다.

기존 핵심 파일의 읽기 시 SHA256은 다음과 같다. 이 표는 새 test gate 결과가 아니다.

| 파일 | SHA256 |
|---|---|
| native_signal.py | 794eabd81940d04835036bdc37ba900d51981e6f5685f18af1ba18c3630d0ac3 |
| signal/core.py | 2244f41f2af5eb0ee9773d455b23cb74c7ebb3b90857f35765c78d0e38b2f1f5 |
| signal_assist_runtime.py | 7b45df853f5474ca86a7407ab455b4978e5936607428dc64b37007f7a57a47a2 |
| signal_start_guard.py | f3ce89f60a7527f94075f0c470dd59e235a65f4ec621512416f3a5f12f171f10 |
| signal_stop_prepare_runtime.py | 69980533b791c48525e6793e2a2d6702d077561507f1dca18c3c01490880ddba |
| signal_stop_prepare.py | f5c206efc2b4ff7d676d06ec4da558a3fe5b0f4901a56a920fa0ee193ee32c39 |
| signal_mode.py | 4828bad0087f470203aa0bc8803d717b641cbfaad42309426acfd3429c6058f8 |
| whole_io.py | d933e679aa29e5686af9a91c13d25c6c96e4375e63a11e5b29e30ddbea26922e |
| whole_inputs.py | 6874242b2e0f38db7689e2dd765aa9385941f945f83af10b11808a35950207e4 |
| whole_chain.py | ffc5902a62704da7420012cdcf569f9f6f629a9bf9b5abb6cb09378d7a88b6de |
| signal_host_can_integration/IO_SCOPE_PLAN_KO.md | 3d0676e495642767ac77753947917aeb3d78776b5b7e6b6126f80b949c81753e |

완료는 source 대조·schema/IO 목록·시계 반례·driver intent 차이 정리다. B 통합 실행의 정상 baseline·Signal2→원형 host→Toyota CAN→실제 C hook 연결 결과, raw 모델/사진 인식, 실차 camera/calibration·ARS ECU 확인 및 안전성은 이 읽기 단계에서 입증하지 않았다. 생산 코드 및 새 hotfix는 제안·적용하지 않았다.
