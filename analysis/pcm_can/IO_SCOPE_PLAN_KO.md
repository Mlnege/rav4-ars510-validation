# Mode0 호스트 → 실제 Toyota CAN 생성 → 메모리 C 안전 검사

생산 코드와 앞선 Mode0/whole 결과는 그대로 두고 새 폴더의 도구만 실행한다. 정상 disabled 초기 상태와 원형 초기화/PCM enable을 먼저 생성한다. 실제 CI.init는 기존 I/O sink이며 원형 ECU/UDS 초기화 본문은 실행하지 않는다.

| 요구 입력/소스 | 메모리 실험 입력 | 근거와 한계 |
|---|---|---|
| 실제 CI.CS.out | CI.update I/O 반환과 같은 CarState builder | interfaces.py468–497에서 원형 update가 저장하는 위치. Toyota CI.update/수신 DBC는 이번에도 미실행 |
| CS.out vEgo/vEgoRaw/aEgo/standstill, steeringTorque/Eps/rate/angle/offset | 기존 건강 fixture의15m/s, aEgo0, standstillFalse, 조향0 | 실제 피드백/브레이크/모터/ECU 물리가 아니다. 고정 aEgo에서는 제어기 적분 보정이 계속 발생할 수 있음 |
| CS.gvc | 고정0m/s² | carstate.py63의 원형 VSC1S07.GVC. 실제 측정/수신은 하지 않음 |
| CS.pcm_acc_status | PCM enabled면8, disabled면0이라는 명시적 합성 내부 상태 | carstate.py166 CRUISE_STATE에서 입력된다. 실제 로그 해독값/firmware state 검증이 아니다 |
| CS.acc_type / pcm_follow_distance / lkas_hud | 실제 생성자 기본 acc_type1, 고정 follow distance3, 실제 생성자 빈HUD | carstate.py48–52/154/181/184. 정확한 stock camera/거리 표시 실물은 미검증. 원형 거리 버튼 조정도 메모리에서 관찰 |
| CC와 Model/Radar | 원형 state_update→carState→native 계획→SelfdriveD/Controls 큐의 실제 CC | 상위 enabled/longActive 고정 없이 생성. ARS live/SignalMode2는 포함하지 않음 |
| CI.apply | 원형 CarInterfaceBase.apply 실행 → 실제 Toyota CarController.update/실제 CANPacker | interfaces.py331–338. 실제 CAN 생성은 메모리 반환 목록에 한정 |
| C permission | 같은 Probe에 정상 PCM/휠/토크/브레이크 메모리 RX | controlsAllowed=True 직접 설정하지 않음. get_controls_allowed와 get_longitudinal_allowed를 따로 관찰 |
| C TX | 매 생성 메시지의 실제 address/payload/bus를 같은 원형 safety_tx_hook에 입력 | 패킷 자체 체크섬은 기존 probe_make_packet이 생성. 차량 프로토콜 checksum은 실제 DBC/독립 Toyota checksum으로 별도 검사. TX는 메모리 함수 호출이며 드라이버/USB/소켓/차량 연결 없음 |

| 원형 생성 메시지 | 조건/주기(제어기 frame) | 검사 범위 |
|---|---|---|
| 0x2E4 STEERING_LKA | 매 호출100Hz, DLC5 | 실제 DBC torque/request/checksum + 실제 C 검사. 이 시나리오의 횡방향 피드백0을 실차 조향 검증으로 확대하지 않음 |
| 0x191 STEERING_LTA | TSS2에서2프레임마다50Hz, DLC8 | 현재 torque CP에서 요청/angle/winddown0, 실제 DBC/counter/checksum/C 검사 |
| 0x343 ACC_CONTROL | directLong에서3프레임마다 약33.33Hz, DLC8 | ACCEL_CMD signed16×0.001, ACC_TYPE, PERMIT_BRAKING, CANCEL_REQ, DISTANCE. 이 DBC에는 전체 작동 상태를 뜻하는 CanActive 필드가 없어 새로 정의하지 않음 |
| 0x412 LKAS_HUD |20프레임마다5Hz 또는 alert/cancel 때 추가 | 실제 DBC/C 검사. stock HUD copy가 빈 합성 입력임을 분리 |
| 0x411 PCS_HUD |100프레임마다1Hz 또는 alert/cancel, 원형 CP enableDsu/DISABLE_RADAR 조건 | 실제 생성/DBC/C 검사를 기록하지만 원형 PCS_INDICATOR1 등의 의미를 순정 PCS/AEB 보존 증거로 사용하지 않음 |
| 0x750 radar tester-present |20프레임마다5Hz, 원형 CP DISABLE_RADAR 조건 | 기존 C가 허용하는 정확한 tester-present 바이트 검사. 생성/검사는 메모리뿐이며 실제 송신/레이더 비활성화/UDS 초기화 없음 |

0x343의 예상 C 판정은 directLong에서 `raw_accel==0`이거나 `get_longitudinal_allowed()==True`와 -3500..2000 범위를 모두 충족할 때 허용이다. 가속 pedal에서는 alternativeExperience1으로 controlsAllowed=True가 남아도 longitudinal_allowed=False일 수 있으므로 두 권한을 합치지 않는다. 첫 페달/취소 틱은 이전 큐CC가 실제 제어기에 도착할 수 있고, 이 메시지가 C에서 차단되는 것도 올바른 검사 결과다. 허용되도록 source/권한을 고치지 않는다.

검사 계획: 정상 활성/PCM 설정속도 변화/지도40/곡선과 지도32/취소(PCM off 동반 및 버튼만)/gas/brake/MAINoff와 정상 PCM off→on 재시작. checksum·DBC decode·주기·C 권한 변화 없음·0x343 부호/범위/허용 조건을 확인한다. ECU 응답·PCS/AEB·회생·실물 Panda heartbeat·Konik 일정과 차량 제동은 미검증으로 남긴다.
