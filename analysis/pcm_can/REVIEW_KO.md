# Mode0·Toyota CAN·C 권한 연결의 독립 읽기 검토

현재 계획은 원형 Mode0·계획·호스트 권한 흐름에서 나온 CC를 실제 Toyota 제어기와 CANPacker에 전달하고, 생성된 메시지를 같은 C 안전 라이브러리에서 검사하는 **메모리 실험**으로 해석할 수 있다. 가속 페달의 조향/종방향 권한 차이와 이전 큐 CC의 예상 거부를 분리한 방향은 적절하다. C 허용이 실제 ECU 호환성·PCS/AEB 유지·실차 적용을 증명한다는 해석은 성립하지 않는다.

이번 검토는 소스·DBC·현재 계획·보존 정상 JSON 읽기만 수행했다. 새로운 C 실행·주행 테스트를 하지 않았으며 허용된 이 문서 외에는 수정하지 않았다. 작성 중인 도구의 모든 시나리오가 통과했다고 보고하지 않는다.

## 범위와 읽은 버전

`IO_SCOPE_PLAN_KO.md`, 연결 도구의 `CardInterfaceIO.apply`, 원형 `CarInterfaceBase.apply`, Toyota `CarController`, `toyotacan`, DBC, `safety_tx_hook`, Toyota C hook, 가속 페달 정책을 읽었다.

| 파일 | 읽은 SHA-256 |
|---|---|
| Toyota carcontroller.py | `f09cebd050f822a5c181f6c706cc3eb752c3f90bca24f5415a86b7506d502d97` |
| safety.h | `264acef46827c278c8a741106506506323ec27842eaf21856a16386ebe084dfe` |
| safety/safety_toyota.h | `a5c87dd55bce5a8f44e85e173784db42648a4982a95107dfe57a2479ec5d5cc0` |
| IO_SCOPE_PLAN_KO.md | `c95785b200cad107c9d600b7a0039596f3a7b29dc505bd2920f84bb41e047e3e` |
| 작성 중 whole_objects.py | `bac4e0fd9335948af7ace132adf231c93b724f03cecf9a08ee98374e8393d48d` |

도구는 작성 중이므로 이후 결과에는 최종 도구와 읽은 C 라이브러리 해시를 함께 기록해야 한다. 기존 생산 코어·MPC·공유 바이너리를 변경하는 작업은 수행하지 않았다.

현재 정상 JSON의 구성은 `SpeedFromPCM=0`, `AlphaLongitudinalEnabled=1`, `LongActuatorDelay=20`, `EnableRadarTracks=0`, `SignalAssistMode=0`이다. 원형 card.state_update와 Mode0 helper를 이번 연결에서는 실행한다. CI.update의 차량 상태 반환은 여전히 합성 입력이며 실제 Toyota 수신 파서는 실행하지 않는다. 보존 JSON에서 75→90km/h 설정속도 연결을 읽었지만, 이것으로 ARS live·신호 보조 Mode2·실차 상태 획득까지 통합되었다고 표현하면 안 된다.

## 실제 생성 경계

원형 `CarInterfaceBase.apply()`는 모델·레이더 참조를 CS에 저장하고 `self.CC.update()`를 호출한다(`opendbc/car/interfaces.py:331–336`). 현재 연결 도구는 이 실제 함수를 실행한 다음 반환된 메시지를 원형 C TX 함수로 검사한다(`whole_objects.py:157–196`). Toyota 제어기의 정지 요청 비양수 보정과 기존 MPC 명령 범위도 그대로 둔다.

실제 CI.init는 실행하지 않는다. CI.update 반환의 `CS.out`, gvc=0, pcm_acc_status=8/0, follow_distance=3은 명시한 합성 입력이다. ECU 상태 8이 해당 실제 한국 차량에서 같은 의미로 관찰되었다는 증거는 아니다. CANPacker/CANParser는 현재 Python 구현의 원형 알고리즘이며 C/Cython CAN 구현의 성능 시험이라고 부르면 안 된다. C 안전 라이브러리와 MPC C/Cython은 별도 경계다.

## 메시지별 생성·권한 조건

다음은 이 RAV4 2022 직접 종방향 제어·토크 조향 CP의 생성 조건이다. 모두 송신 버스 0이며, 새로운 버스나 신호를 정의하지 않았다. 주기는 **실제 Toyota 제어기 호출 frame** 기준이다. 호출이 100Hz일 때만 표의 Hz가 성립하며 실제 차량 전달 간격과는 다르다.

| CAN ID·원형 메시지 | 길이 | 원형 생성 조건·명목 주기 | C의 허용 조건 |
|---|---:|---|---|
| 0x2E4 STEERING_LKA | 5바이트 | 매 호출, 명목 100Hz. latActive False이면 torque=0. 조향 속도/사용자 토크·기존 rate limit 적용 | 주소·버스·길이와 relay 정상 확인. 비영 torque에는 controls_allowed 및 토크·증가/감소·EPS 차이·시간 한계 필요. 현재 fixture의 torque=0 허용을 실제 조향 성능으로 확대하지 않음 |
| 0x191 STEERING_LTA | 8바이트 | TSS2에서 frame%2==0, 명목 50Hz. 이 토크 조향 CP에서는 request 2개·각도·winddown 모두 0 | LTA 안전 모드가 아닌 현재 CP에서는 request·각도·winddown 중 비영 값이 있으면 거부. 비작동 메시지는 controls_allowed False에서도 허용 가능 |
| 0x343 ACC_CONTROL | 8바이트 | directLong에서 frame%3==0, 명목 33.33Hz. 기존 rate limit·PID·-3.5..2.0m/s² clip 적용 | directLong 조건에서 signed raw_accel=0 또는 longitudinal_allowed True와 -3500..2000 범위. relay 정상·정확 버스/길이도 필요 |
| 0x412 LKAS_HUD | 8바이트 | frame%20==0, 명목 5Hz. 경고가 나타나거나 사라질 때와 cancel 때 추가 발행 | 현재 Toyota C에서는 표시 본문별 controls 권한을 검사하지 않음. 허용 목록의 주소·버스·길이와 relay 조건 적용 |
| 0x411 PCS_HUD | 8바이트 | frame%100==0, 명목 1Hz 또는 위 추가 UI 발행. enableDsu 또는 DISABLE_RADAR 조건 필요 | 직접 종방향용 허용 목록에 있음. PCS 표시 내용이나 실제 PCS 기능 상태를 C가 검증하지 않음 |
| 0x750 radar tester-present | 8바이트 | DISABLE_RADAR에서 frame%20==0, 명목 5Hz | 버스0/길이8 허용 목록과 정확한 `0f 02 3e 00 00 00 00 00`만 허용. 다른 진단 요청은 이 경로에서 허용되지 않음 |

근거: `carcontroller.py:141`, `:153`, `:192`, `:288–303`; `toyotacan.py`의 해당 생성 함수; `safety/safety_toyota.h:6–25`, `:148–320`; `safety.h:259–291`, `:621–625`.

현재 factory는 carFw가 빈 목록이므로 enableDsu=False다(`toyota/interface.py:50–53`). 이 CP에서 STATIC_DSU_MSGS의 다른 bus 메시지를 새로 필요하다고 추측하면 안 된다. SecOC 0x131 또는 다른 Toyota의 취소 메시지도 이 CP의 생성 목록으로 확대하지 않았다.

0x343 ACCEL_CMD는 DBC의 signed16, 0.001m/s² 신호다. 현재 DBC에는 전체 작동 상태를 뜻하는 `CanActive`라는 필드가 없다. PERMIT_BRAKING·CANCEL_REQ·ACC_TYPE 등의 존재와 실제 ECU 동작 의미는 구분해야 한다. 특히 DBC의 PERMIT_BRAKING 주석 자체도 효과가 완전히 확인됐다고 선언하지 않는다.

HUD 추가 발행은 정상 소스 예외다. 0x412를 항상 정확히 200ms, 0x411을 항상 정확히 1초라고 검사하면 cancel/경고 때 정상 발행을 실패로 오분류할 수 있다. C TX 허용 함수는 이 명목 주기 자체를 보장하지 않는다. 최초 card 적용이 시작된 시점에서 controller_frame=0을 기준으로 검사해야 한다.

## 두 권한과 운전자 입력

`get_alternative_experience(False)`는 원형 DISABLE_DISENGAGE_ON_GAS 비트를 포함한 값 1을 만든다. 이는 운영 설정을 바꿔 얻은 새 우회가 아니라 현재 메모리 DisengageOnAccelerator=0에 대한 원형 정책이다.

`generic_rx_checks()`는 이 비트가 있을 때 가속 페달의 상승으로 controls_allowed를 내리지 않는다. 그러나 `get_longitudinal_allowed()`는 항상 `controls_allowed && !gas_pressed_prev`다(`safety.h:299–300`, `:371–381`). 두 권한을 같은 것으로 취급하면 안 된다.

| 정상 RX 뒤 조건 | controls_allowed | longitudinal_allowed | 직접 종방향 0x343 비영 명령 |
|---|---|---|---|
| PCM 활성·가속/브레이크 없음 | True | True | 범위·기타 안전 조건을 충족할 때 허용 |
| 가속 페달, alternativeExperience=1 | 유지될 수 있음 | False | 양수·음수 모두 거부 |
| 브레이크 상승 또는 움직이는 중 브레이크 | False | False | 거부 |
| PCM 비활성 RX | False | False | 거부 |
| 버튼 이벤트만, PCM은 계속 활성 | C가 해당 버튼 RX를 받은 것은 아님 | 다른 C 조건에 따라 유지 가능 | 실제 C가 본 입력과 호스트 취소를 구분해야 함 |

raw_accel=0은 비작동 값으로 권한 False에서도 허용된다. 이것은 권한을 다시 생성했다는 뜻이 아니다. C TX 전후 controls_allowed와 longitudinal_allowed가 같아야 한다. `C_TXHook=True`는 주소·버스·길이·정해진 수치 정책을 통과한 소프트웨어 판정이다.

## 이전 큐 CC와 예상 거부 판정

순서는 정상/운전자 C RX→card가 이전 CC 적용→현재 planner/SelfdriveD/Controls의 새 CC 발행이다. 같은 첫 운전자 입력 틱에서 이전 CC의 longActive=True와 새 CC의 longActive=False가 공존할 수 있다.

이전 CC의 비영 0x343을 **같은 C probe의 새로운 운전자 RX 뒤에** 검사해서 거부하는 계획은 타당하다. 취소·브레이크·가속 틱의 expected deny를 실패 건수에 그대로 더하면 올바른 안전 거부를 결함으로 오분류한다. 현재 코드는 `actual_tx == expected_tx`를 비교하므로 이 구분을 표현한다. 새로운 시나리오 결과의 성공 판정에서도 이 비교를 유지해야 한다.

구분할 항목은 기대 허용, 기대 거부, 기대와 다른 허용, 기대와 다른 거부다. 기대 거부를 통과시키려고 C 권한을 True로 쓰거나 명령을 미리 0으로 바꾸면 검사할 이전 큐 경계를 없애므로 해서는 안 된다. 반대로 실제 송신된 과거 명령이 ECU에서 얼마 동안 유지되는지는 C 메모리 TX 거부로 검증되지 않는다.

현재 `expected_tx`에서 비ACC 메시지를 일괄 1로 두는 부분은 **현재 생성 fixture의 제한된 기대값**이다. LKA torque=0, LTA request/각도/winddown=0, relay=False, 정확한 여섯 ID·버스·길이가 확인될 때 적용할 수 있다. 향후 비영 조향·relay·다른 CP·변형 payload를 섞으면 이 단순 기대값을 그대로 일반화할 수 없다. 해당 불변식을 생성된 decoded 신호로 검사한다는 추가 계획은 적절하다. 별도 실제 조향 한계 통과를 뜻하지 않는다.

0x343의 단순 기대식도 직접 종방향 CP·정확 주소/버스/길이·relay 정상 전제다. stockLong CP에서는 CANCEL_REQ와 raw0 등의 추가 조건이 있으므로 이 기대식을 다른 Toyota에 그대로 적용하면 안 된다.

## 체크섬·DBC와 C 패킷의 범위

실제 Toyota CANPacker가 만든 바이트를 DBC로 다시 읽고, CHECKSUM 계산 신호가 있는 메시지에 대해 주소·길이·마지막 바이트를 제외한 합계를 독립 확인하는 구성이다. 0x2E4·0x191·0x343에는 DBC CHECKSUM이 있다. 현재 0x411·0x412에는 그 CHECKSUM 신호가 없으며 0x750도 이 DBC의 신호 메시지가 아니다. 따라서 체크섬 결과 None을 False나 검증 완료 True로 바꾸면 안 된다.

C 테스트의 CANPacket 내부 체크섬과 차량 프로토콜의 Toyota checksum은 별개다. 올바른 C 패킷을 만들었다고 ECU가 Toyota 바이트를 수락했다고 주장할 수 없다. C hook도 모든 HUD 내용에 대한 차량 프로토콜 검사를 수행하지 않는다. DBC 정상 해독은 현재 정의와 일치한다는 뜻이며 firmware·시퀀스·하드웨어 응답 검증이 아니다.

## PCS 표시와 tester-present의 의미

원형 `create_fcw_command()`는 PCS_INDICATOR=1과 PCS_OFF=1을 넣는다. DBC의 값 설명에서 PCS_INDICATOR=1은 PCS가 사용자에 의해 꺼진 표시 범주다. 이것이 실제 PCS/AEB 제어 상태를 물리적으로 바꿨는지 또는 표시만 바꿨는지는 이 메모리 기록으로 확정할 수 없다. **이 비트를 보았다는 사실을 PCS/AEB 보존 증거로 쓰면 안 된다.**

C의 직접 종방향 허용 목록은 0x411을 허용하지만 그 PCS 표시 필드의 기능 의미를 검사하지 않는다. 코드에 PRE_COLLISION 계열 생성 함수가 따로 있다는 사실도 순정 PCS 경로가 살아 있다는 증거가 아니다. 이 대상 CarController 경로는 그 함수를 호출해 실물 PCS 기능을 시험하지 않는다.

0x750 tester-present는 source 주석상 레이더 비활성 상태를 유지하는 기존 경로다. 이번 기록은 기존 생성 함수가 정확한 진단 바이트를 만들고 C가 그 제한된 패턴을 허용했다는 메모리 관찰이다. 실제 CarInterface.init의 통신 제어 요청, ECU 응답, 레이더의 통신 상태 전환은 실행하지 않는다. 실제 레이더를 비활성화했다거나 순정 PCS/AEB가 유지됐다고 표현하면 안 된다.

C의 bus2→bus0 전달 규칙이나 AEB 자체 TX 제한을 소스에서 읽는 것만으로 물리 PCS/AEB 보존을 증명할 수도 없다. ECU 준비·배선·차량 firmware·독립 안전 장치가 검증되지 않았으므로 실제 송신·실차 호환성·안전성은 여전히 미확정이다. 원래의 PCS/AEB 비활성화 금지와 실차 실험 CAN 송신 금지는 유지한다.

## 최종 판단

현재 계획은 Mode0의 원형 상태 연결, 실제 Toyota CAN 생성, C 권한/송신 판정을 단계별로 묶는 메모리 검사로 적절하다. 명목 주기는 실제 controller frame 기준, 운전자 입력 직후 거부는 기대 판정 기준으로 검증해야 한다. 현재 source에서 확인되지 않은 CAN 신호나 새로운 버스 요구는 발견하지 않았다.

실차 firmware·PCS/AEB·독립 MCU heartbeat·물리 가감속·회생 제동·Konik 전달 지연은 이 검사로 입증되지 않는다. 작성 중인 도구의 최종 실행 결과는 별도로 확인해야 하며 이번 읽기 검토를 실행 통과 결과로 대체하지 않는다. 허용 범위가 이 문서 한 개이므로 HANDOFF도 수정하지 않았다.
