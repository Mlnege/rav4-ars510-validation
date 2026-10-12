# 정상 활성·전체 호스트 지연 실험의 독립 검토

상태 전환·건강 확인·상위 제어 권한을 True로 고정하는 우회는 확인되지 않았다. 원형 클래스 본문과 메시지 건강 확인을 실행하고, 정상 PCM 수신으로 C 권한이 올라오는 구조다. 다만 **건강한 합성 입력을 전제로 한 호스트 판단 체인**이다. 실제 CAN 상태 파싱, 차량 초기화, Toyota 제어 메시지 생성·전송, 송신 안전 검사, 독립 MCU heartbeat까지 검증한 전체 차량 실험은 아니다.

읽기 검토와 프로세스 안의 상수·모듈 출처 확인만 수행했다. 기존 정상/지연 실험을 다시 실행하지 않았고, 이 문서 외에는 파일을 수정하지 않았다. 아래 정상 700틱 결과는 root가 직접 실행한 보존 결과를 독립적으로 읽어 확인한 값이며, 검토자가 700틱을 새로 실행했다는 뜻이 아니다.

## 검토 대상과 버전

`whole_baseline.py`, `whole_chain.py`, `whole_inputs.py`, `whole_io.py`, `whole_objects.py`와 해당 저장소 원형을 읽었다. 작성 중인 `whole_fault_one.py`도 cancel 종류를 구분하기 위해 읽었다. 이 도구는 root가 작업 중이므로 아래 해시 이후 버전은 별도 확인이 필요하다.

| 파일/결과 | 읽은 SHA-256 |
|---|---|
| whole_baseline.py | `1da388f3665f11e4aff99064da75d268ad77b2ca97c78c63134c01f04b5b4e19` |
| whole_inputs.py | `6874242b2e0f38db7689e2dd765aa9385941f945f83af10b11808a35950207e4` |
| whole_io.py | `d933e679aa29e5686af9a91c13d25c6c96e4375e63a11e5b29e30ddbea26922e` |
| whole_objects.py | `0e1ff7a15b626d44ee949adeaa617b5e2341694999fc13e1988732295a93eee3` |
| whole_chain.py | `ffc5902a62704da7420012cdcf569f9f6f629a9bf9b5abb6cb09378d7a88b6de` |
| whole_fault_one.py | `e2bd39b1a03e20f994fbe7a47015e1bf62fc5adb847024bc9d250a64a9844a93` |
| 보존 정상 700틱 결과 | `0529de3904cfed3cc488cbcecf14a20239ccb6386d74b281846195e14eb0a11d` |

## AST 본문·상수·모듈 출처

`load_definitions()`는 원본 AST에서 클래스·함수 노드를 선택한 뒤 본문을 수정하지 않고 실행한다(`whole_io.py:147–155`). 전체 모듈의 import·전역 초기화는 다시 구성한다. 따라서 본문이 같다는 사실과 모든 전역/입출력의 동등성은 별도로 검토해야 한다.

`source_constants()`는 지정한 원본 할당 노드를 실제로 읽어 전역에 적용한다(`whole_objects.py:90–120`). 초기 namespace의 임시 값만 쓰는 구조가 아니었다. 프로세스에서 로드한 실제 전역을 직접 확인했다.

| 전역 | 직접 확인한 값 | 판단 |
|---|---|---|
| REPLAY / SIMULATION / TESTING_CLOSET | 모두 False | 해당 특수 실행 분기로 활성/건강 검사를 완화하지 않음 |
| IGNORED_SAFETY_MODES | silent / noOutput | 원본 값과 일치 |
| 상태·Panda 유형·인격 enum 연결 | 실제 Cap’n Proto enum과 원본 역방향 매핑 | 별도 허용 상태 enum을 만들지 않음 |
| DT_CTRL / DT_MDL | 0.01 / 0.05초 | 원본 값과 일치 |
| LAT_SMOOTH_SECONDS | 0.0초 | 원본 modeld 할당을 읽은 값 |
| LAT_CURVATURE_SATURATION_ACCEL | 0.1 | 원본 controls 할당과 일치 |
| XIAOGE_SOURCE_HEARTBEAT_NS | 1,000,000,000 | 원본 card 할당과 일치 |
| XIAOGE_LANE_ERROR_LOG_INTERVAL_NS | 5,000,000,000 | 원본 card 할당과 일치 |

`whole_io.prepare()` 과정에서 일부 Python 의존 모듈과 기본값은 다운로드 검증 checkout에서 먼저 로드된다. 이를 주 저장소에서 로드했다고 표현하면 안 된다. 직접 읽은 `cereal`, `services`, `realtime`, `LongitudinalPlanner`, MPC Python 코드, `StateMachine` 6개는 주 저장소와 **줄바꿈 정규화 후 텍스트·AST가 완전히 같았다**. 원시 바이트 해시 차이는 여기서는 줄바꿈 차이였다. 선언 기본값도 205개 전부 같았고 차이 키는 0개였다. 잘못된 알고리즘 혼합이 확인된 것은 아니다.

이 확인은 명시한 모듈 6개와 기본값 파일의 비교다. 모든 전이적 의존 모듈·모든 하드웨어 구성의 동등성까지 입증하지 않았다. 향후 결과에는 실제 import 파일과 원시/정규화 해시, 고정 MPC·C 안전 라이브러리 해시를 함께 기록하는 편이 명확하다. `SOURCE_HASHES`의 네 AST 파일만으로 전체 실행 의존성을 증명할 수는 없다.

## 차량 구성·설정의 전제

차량 구성은 `CarInterface.get_params(..., alpha_long=True, ...)`를 명시적으로 호출해 만든 합성 RAV4 2022다(`whole_objects.py:134–144`). 해당 원형 분기에서 DISABLE_RADAR·직접 종방향 제어가 설정된다. 결과는 flags=1372, `notCar=False`, `pcmCruise=True`, `openpilotLongitudinalControl=True`, `radarUnavailable=True`였다. 레이더 사용 가능을 False에서 True로 바꾸는 패치는 없다.

`card`에 이미 만든 CI를 전달하므로 실제 차량 감지·펌웨어 조회·운영 AlphaLong 설정 읽기 분기를 지나지 않는다(`card.py:111–130`). 메모리 `AlphaLongitudinalEnabled`는 기본값이 선언되지 않아 False 취급이다. 따라서 **명시적으로 직접 제어 차량을 가정했다**고 표현해야 하며, 기본 설정만으로 실제 차량이 직접 제어 준비를 마쳤다고 표현하면 안 된다.

| 메모리 설정 | 확인한 선언/입력 | 이 실험의 범위 |
|---|---|---|
| OpenpilotEnabledToggle | 기본 1 | 제어기 사용 가능 전제 |
| DisengageOnAccelerator | 기본 0 | 원형이 alternativeExperience=1을 도출. 가속 페달 조건 해석에 반영해야 함 |
| UseWideCamera | 기본 1 | 세 카메라 스트림 목록·건강 입력을 제공 |
| SpeedFromPCM | 기본 2 | Mode0 PCM 설정속도 동기화 검사가 아님 |
| EnableRadarTracks | 기본 0 | ARS510 실제 연결 검사가 아님 |
| SignalAssistMode | 기본 0 | 보조 신호 인식·제동 통합 검사가 아님 |
| LongActuatorDelay | 기본 20 | 현재 코드의 선언 기본값을 사용. 실차 실측 지연 아님 |
| NNFF | 기본 0이고 도구에서도 0 지정 | 현재 선언 기본값과 같음. 신경망 조향 구성을 검증하지 않음 |

현재 추가된 `user_requested` 프로파일은 메모리에서 `SpeedFromPCM=0`, `AlphaLongitudinalEnabled=1`, `LongActuatorDelay=20`을 명시한다. 위 기본값 표와 정상 700틱 결과는 기본 프로파일의 범위다. 새 프로파일의 실행 결과를 이 검토에서 통과로 보고하지 않는다. 이 프로파일에서도 `card.state_update`가 대체되어 있으므로 Mode0의 실제 `v_cruise_helper` 입력 연결을 실행한 검사로 표현하면 안 된다. 운영 설정이나 실제 CP 파일을 바꾼 것은 아니다.

기본값은 코드 선언값이며 현재 차량의 실제 저장 설정이라고 주장할 수 없다. MemoryParams는 디스크 저장·원자성·비동기 쓰기를 재현하지 않는다. `get()`도 원형 Params의 형식 있는 반환값 대신 대부분 bytes를 반환한다. 이번 `UseWideCamera=1` 등의 관찰 값은 같은 조건을 만들지만, 예를 들어 `bool(get(...))`에서 `b'0'`를 쓰는 다른 설정 검사는 원형 bool False와 다를 수 있다. 가상의 설정 전환 전체를 검증한 API 대체라고 표현하면 안 된다.

## 정상 초기화·활성 결과의 의미

보존 정상 결과의 생성 도구 해시는 현재 읽은 baseline/input/IO/object 파일과 일치했다. 다음 순서를 확인했다. 시각 100초는 합성 시계의 시작값이며 실제 로그 절대 시각이 아니다.

| 틱 | 합성 시각 | 원형 건강 확인·상태 | C 권한 | 적용 경계 |
|---:|---:|---|---|---|
| 0 | 100.00초 | initialized/enabled/active/longActive 모두 False, all_checks=False | False | 적용 0 |
| 49 | 100.49초 | 아직 초기화 전, all_checks=False | False | 적용 0 |
| 50 | 100.50초 | all_checks=True 이후 initialized=True, enabled=False | False | 아직 적용 0 |
| 51 | 100.51초 | 초기화 상태를 다음 card 틱이 소비 | False | 초기화 sink 1회, 첫 적용 sink |
| 200 | 102.00초 | PCM 활성 입력으로 enabled/active/longActive=True | True | 앞 틱 CC를 적용하는 순서 |
| 699 | 106.99초 | 정상 활성 유지 | True | 적용 sink 누적 649회 |

원형 `data_sample()`은 `CS.canValid && sm.all_checks()` 또는 10초 타임아웃 등의 조건으로 초기화한다(`selfdrived.py:572–609`). 기준 결과는 0.5초에 all_checks가 True였고 특수 실행 전역은 False이므로 10초 타임아웃이나 SIMULATION 활성 지름길로 초기화한 결과가 아니다. 원형 `FrequencyTracker`, `SubMaster.all_alive/all_freq_ok/all_valid/all_checks` 본문도 실행한다.

단, `canValid=True`, 메시지 `valid=True`, 장치 시작·온도 정상·카메라/자세/운전자 감시 정상은 **합성 입력의 전제**다. 실제 센서가 이 건강 상태를 만들었음을 증명한 것이 아니다. 카메라 목록은 `CameraInventoryIO`가 있다고 응답한 목록이다. 원형 조건문은 실행하지만 물리 카메라가 연결되었다고 입증하지 않는다. manager 입력의 실행 프로세스 목록도 합성이어서 실제 모든 프로세스의 상태를 관찰하지 않는다.

## 생략한 물리·입출력 경계

`card.state_update` 대체는 CAN 소켓만 격리하는 것보다 범위가 넓다. 원형에서 수행하는 CAN 디코딩, `CI.update`, CAN 누락/타임아웃 누적, radarInput 시각 연결, 보조 비전 반영, `v_cruise_helper.update_v_cruise/initialize_v_cruise`, softHold·activateCruise·latEnabled 전달 등을 실행하지 않고 준비한 CarState를 반환한다(`card.py:202–298`, `whole_chain.py:45–49`). 이는 명시된 차량 상태 입력 경계지만, 이 전체 기능이 통과했다고 보고하면 안 된다.

`CardInterfaceIO.init()`은 실제 Toyota 초기화를 실행하지 않는다. 원형 Toyota 초기화의 레이더 통신 제어 요청도 실행하지 않았다. `ControlsReady=True`는 원형 card 코드가 **반환된 초기화 sink 뒤에 메모리로 쓴 값**이다. 실제 ECU 준비나 pandad 안전 모드 전환 handshake가 성공한 증거가 아니다.

`CardInterfaceIO.apply()`는 Toyota CarController·CANPacker·체크섬·실제 송신을 실행하지 않고 호출된 CC를 기록하며 빈 CAN 목록을 반환한다(`whole_io.py:179–195`). 따라서 649회는 호스트의 적용 판단이 sink를 호출한 횟수다. 649회 실제 제어 메시지를 만들거나 차량에 적용했다는 뜻이 아니다. `can_list_to_can_capnp` 대체 역시 빈 목록의 형식 경계이며 CAN 전달 시간을 검증하지 않는다.

실제 `CarInterface` 객체는 읽기 전용 계산과 파라미터 접근에 사용되지만, 이것으로 생략한 초기화/수신/제어 출력까지 실행했다고 확대해서는 안 된다. 실제 CANParser 실행 성능은 이번 검사가 아니다. MPC는 고정 빌드의 C/Cython이고, 별도 권한 검사는 C 안전 라이브러리이며, 두 경계도 구분해야 한다.

## C 권한과 취소 종류

`VehiclePermissionInput`은 C 안전 라이브러리에 Toyota 안전 hook·원형 CP safetyParam·alternativeExperience를 설정하고 정상 바퀴/조향/브레이크/PCM RX를 넣는다(`whole_inputs.py:15–32`). 권한을 True로 직접 쓰는 함수를 호출하지 않는다. `Probe`에 그런 테스트 함수가 있다는 사실과 이 경로에서 호출했다는 주장은 구분해야 한다. 정상 결과의 shortcut 호출은 0이며 처음 False→PCM 활성 뒤 True 전이와 일치한다.

그러나 C 라이브러리는 host 틱에서 호출하는 테스트 객체다. 실제 독립 MCU가 아니다. 처음부터 지정된 Toyota hook을 사용하고 PandaState의 모델/파라미터 일치는 CP로 구성한다. 실제 firmware 조회·안전 모드 교체·heartbeat·USB/CAN 하드웨어 전달 과정이 성공했음을 증명하지 않는다. TX hook도 호출하지 않으므로 권한 False 시 실제 생성된 명령을 거부했는지 검증하지 않았다.

작성 중인 fault 도구는 현재 취소를 둘로 나눈다.

- `cancel`: `engaged=False`를 지속하고 처음 50ms에 cancel 버튼 입력도 제공한다. C가 정상 PCM 비활성 RX를 받는 조건이 함께 있다. 이 결과를 버튼 입력만의 효과라고 부르면 안 된다.
- `button_only_cancel`: PCM은 계속 활성인 상태에서 cancel 버튼 이벤트만 처음 50ms 제공한다. C 입력 함수에는 cancel 자체가 없으므로 이 조건에서는 C PCM 권한이 유지될 수 있다. 이 문서에서는 소스 구분만 확인했으며 해당 새 실행 결과를 통과로 보고하지 않는다.

원형 Toyota가 실제 CAN에서 이 같은 buttonEvents를 만드는지, 블루투스 취소·PCM 비활성·실제 버튼이 어떻게 연결되는지는 별도 입력 검증이다. 합성 스키마의 버튼 이벤트 시험을 실제 차량 버튼 프로토콜 시험으로 확대하면 안 된다.

## 선택 순서·한 틱 큐

명시된 순서는 외부 입력/C RX→card 상태 발행·**이전 CC** 적용→모델 도착 시 planner→SelfdriveD→Controls 새 CC 발행이다(`whole_chain.py:54–84`). 새 CC는 다음 card 틱에서 소비한다. 이는 이 실험의 선택된 순서이며 실제 분리 프로세스의 모든 스케줄링 순서를 대표하지 않는다.

취소 틱의 새 `longActive=False`와 같은 틱의 적용 sink에 전달된 이전 `longActive=True`는 함께 존재할 수 있다. 둘을 같은 명령의 모순으로 취급해서는 안 된다. 반대로 새 권한이 내려갔다고 이미 큐에 있던 명령까지 실제 차에서 거부했다고 주장할 수 없다. C 권한은 독립 단계이고 이번 apply sink는 C TX를 실행하지 않는다.

원형 card는 적용 경계에서 carControl의 alive를 확인한다. 건강/권한 검사를 새로 건너뛴 도구 코드는 보이지 않았지만, 어떤 입력을 그 틱에 먼저 소비했는지는 중요하다. 취소·브레이크·가속·C 권한 False 조건의 보고에는 새 CC, 이전 CC 적용, C 권한, 실제 TX 판정 여부를 각각 기록해야 한다.

## 시계·전체 호스트 정지의 한계

`clock_inputs()`는 `time.monotonic/monotonic_ns`를 합성 시계로 바꾼다. `perf_counter/thread_time`의 실제 시간 측정은 남긴다(`whole_io.py:80–90`). 한 step 내부에서는 합성 시각이 고정되어 실행 비용이 메시지 `processingDelay` 등에 그대로 반영되지 않을 수 있다. 이 결과로 실제 메시지 처리 시간이 0이라고 해석하면 안 된다.

card·SelfdriveD의 Ratekeeper 본문과 `monitor_time()`은 실행한다. `Controls.run()`의 별도 Ratekeeper 감시는 직접 `update/state_control/publish`를 호출하는 chain에서는 실행하지 않는다. 실제 소켓 대기·poll timeout·프로세스별 CPU affinity/FIFO 스케줄·설정 갱신 스레드도 이 단일 선택 순서로 재현하지 않는다. 원형 soft-disable 타이머 등은 틱/DT_CTRL 기반 정책 그대로이며 실제 벽시계 경과와 별도로 해석해야 한다.

`whole_stall`은 합성 시계를 앞으로 옮기는 입력이고 실제 host sleep은 아니다. `actual_sleep`은 실제 대기를 측정한 뒤 합성 시계도 그만큼 옮긴다. 둘은 구분해 보고해야 한다(`whole_fault_one.py:31–39`).

정지 중 외부 모델·카메라·ECU publisher와 C RX가 독립적으로 실행되지는 않는다. 재개 후 같은 host 호출이 새로운 합성 입력과 정상/운전자 C RX를 만든다. 원형 SubMaster의 alive/frequency 계산은 실행하지만 재개 직전 독립 MCU의 RX 타임아웃·heartbeat 소실·차량 이동·이미 전송된 명령 유지까지 재현한 것은 아니다. 도구의 `whole_host_stall_mcu_rx_during_gap_executed=False`와 `independent_mcu_heartbeat_verified=False`는 적절한 한계 표기다.

외부 입력을 재개 때 과거 100Hz burst로 날조하지 않는 처리는 타당하지만, 실제 소켓에 누적된 모델의 획득/게시/수신 순서와 동일하다는 뜻은 아니다. 이번 공통 합성 시계는 실제 BOOTTIME/MONOTONIC 시계 차이도 재현하지 않는다. 오래된 model EOF와 새 헤더가 주어진 조건은 특정 입력 계약의 반례이지 실제 장치가 그 조건을 만들었다는 증거가 아니다.

## 결론과 후속 판단 경계

기준 조건에서 상위 활성·초기화·C 정상 RX 권한을 직접 True로 바꾸는 우회는 확인되지 않았다. source 건강 확인과 상태 전환으로 정상 활성되는 **호스트 판단 경로**를 검사하는 도구로 해석할 수 있다. 전체 차량 입력·초기화·Panda heartbeat·Toyota 출력·C 송신 안전·실물 제동의 성공은 여전히 미검증이다.

지연 조건에서 권한이나 오래된 목표가 유지된 관찰이 나오더라도, 먼저 메시지 획득·헤더·수신 시각, 독립 publisher, C 권한 시계, 이전 CC 큐, 실제 TX 경계를 분리해야 한다. 이 도구만으로 센서 고장·단일 지연 원인·실차 제동 결함을 확정하거나 생산 코드의 새로운 시간 차단 기준을 정하는 것은 이르다. 특히 실제 독립 MCU 정지가 빠진 상태에서 host 재개 결과만으로 안전 거부 시간까지 주장하면 안 된다.

다음 단계가 필요하면 동일 고정 소스에서 명시된 하나의 경계를 추가해 판정을 비교하는 방식이 적절하다. 현재 검토에서는 새로운 정책·상수·권한·필터·실차 제어 변경을 제안하거나 적용하지 않았다. 사용자 인계 파일도 허용 수정 범위 밖이므로 갱신하지 않았다.
