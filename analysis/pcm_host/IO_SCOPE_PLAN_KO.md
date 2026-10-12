# Mode0 수신 속도와 호스트 권한 연결 검사의 입력 경계

생산 코드를 바꾸지 않고 원형 `Car.state_update`를 추가 실행한다. 기존 시간/권한 실험은 이 메서드를 차량 상태 I/O로 대체했으므로 실제 `VCruiseCarrot` 연결을 입증하지 못했다. 기존 결과와 도구는 보존하고 새 폴더의 복사본만 수정한다.

| 경계/필드 | 입력 방식 | 실제 실행되는 원형 판단 | 검증하지 않는 부분 |
|---|---|---|---|
| can socket / raw drain | 메모리 소켓에 빈 CAN 목록을 가진 실제 Cap'n Proto 이벤트, 정상 100 Hz | 원형 CAN 이벤트 변환, state_update 수신 시각/패킷 수 기록 | 차량 CAN 프레임 수집, Panda 통신, Toyota CAN 파서 |
| CI.update 반환 | 스키마가 정의한 CarState builder: canValid, drive, vEgo, cruiseState.available/enabled/speed/speedCluster, gas/brake, buttonEvents | 반환 뒤 원형 state_update 전부 | 원형 Toyota CI.update/DBC 디코딩은 실행하지 않음. canValid는 건강한 합성 입력의 선언 |
| Card 속도/상태 | 초기 생성자는 원형, enabled/initialized 기본 False | VCruiseCarrot.update_v_cruise, ToyotaPcmSetSpeedSync, carState 발행, 원형 init 조건 | 실제 ECU 초기화/UDS, 실차 준비. CI.init는 호출 횟수만 기록하는 I/O sink |
| 설정/CP | 원형 get_params의 정확한 RAV4 2022 + alpha 인수, 메모리 SpeedFromPCM0/LongActuatorDelay20/AlphaTrue | 원형 get_params/constructor/Params 읽기 | 운영 설정, 사용자 실제 flags/FW/장치 설치와 같다는 주장. flags 강제 수정 없음 |
| CarrotMan 속도 제한 | 유효한 스키마 desiredSpeed, activeCarrot 등의 명시적 합성 메시지. 곡선은 원형 curve_speed/VisionCurveSpeed로 합성 model에서 산출 가능 | 실제 get_carrot_man 건강/나이 검사, CarrotPlanner→LongitudinalPlanner/MPC | 지도 경로 서버·GPS·CarrotServ 네트워크 실행/지도 품질. 지도 cap 자체는 합성 입력 |
| 모델/레이더/운전자/장치 입력 | 기존 건강 fixture를 새 폴더에 복사. 실제 소스 SubMaster가 반복 메시지로 alive/valid/freq 형성 | 원형 update_events→StateMachine→Controls.state_control→CC | 실제 카메라/운전자 모델/ARS510 live/SignalMode2 통합 |
| Panda permission 입력 | 실제 C Toyota hook에 정상 PCM 메모리 RX, getter 결과로 pandaStates 필드 생성 | 실제 C 수신에 따른 controlsAllowed, 원형 호스트 불일치 검사 | 실제 MCU heartbeat/차량 ECU, CAN TX 및 물리 PCS/AEB 준비 |
| 최종 CI.apply/sendcan | 원형 card.controls_update 경계 후 메모리 I/O sink | 큐의 CC, enabled/longActive/accel 및 호출 기록 | 실제 CarController 생성 CAN, 실차 송신, 실제 제동 응답 |

정상 disabled→MAIN available→PCM enabled를 먼저 검증한다. 그 뒤 속도 상승/하강과 낮은 cap, 취소·가속·제동, 정상 재시작을 비교한다. 실제 버튼 CAN을 새로 만들거나 RES/SET 송신으로 설명하지 않는다. 실패한 입력 조건은 지우지 않고 결과에 기록한다.

실행 순서: 외부 입력 → 원형 card.state_update/state_publish 및 이전 큐 CC 적용 → 20 Hz 원형 계획 → 원형 selfdrived → 100 Hz 원형 controls 발행. 최초 페달/취소 틱의 card 이전 CC와 다음 틱의 새 CC를 분리한다.
