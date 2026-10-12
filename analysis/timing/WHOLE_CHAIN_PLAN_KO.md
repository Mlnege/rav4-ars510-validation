이번 단계는 **호스트 Python의 권한 판단 연결**을 검사한다. 아직 결과가 아니라 실행 설계다. 활성 상태를 참으로 넣어 시작하지 않고 원형의 비활성 상태에서 정상 carState/PCM 또는 button 입력이 만든 이벤트로 활성화한다. 실제 차량·ECU·Panda 장치 준비, 영상 인식, 실제 제동·회생 성능을 검사하는 범위는 아니다.

실행할 원형은 SelfdriveD.data_sample/update_events 및 필요한 원형 보조 메서드, Events/StateMachine.update, Controls의 전체 state_control/publish, Car의 전체 controls_update와 확인 가능한 step 연결이다. SubMaster 생성·수신·FrequencyTracker 판정도 소켓만 메모리 전달물로 바꾸고 원형 코드로 실행한다. source 본문 일부를 삭제하거나 `enabled/active/longActive/all_checks`를 고정 함수로 대신하지 않는다. 실제 메서드 실행이 불가능해 부분 경로만 실행한 경우 그 범위를 명시하며 전체 권한 연결 성공이라고 부르지 않는다.

| 입력 또는 초기화 항목 | 입력 계획/출처 | 실제 원형에서 결정할 값 | 확인 상태 |
|---|---|---|---|
| CarParams | 정확한2022 식별자로 현재 CarInterface.get_params의 오프라인 반환. 원본 옵션/flags 유지 | pcmCruise/longitudinal/safety 설정. 시간 실험으로 바꾸지 않음 | 계획, 실행값·해시 기록 예정 |
| 설정 저장소 | 원형 params_keys 기본값과 CarParams 직렬화만 메모리 저장. 양수/음수 사례의 관련 설정은 별도 명시 | 실제 get/put/remove 호출. 운영 저장소 없음 | 계획 |
| 하드웨어/서비스 입력 | 실제 Cap'n Proto 스키마에 명시한 정상 자료: CAN 상태·기어·calibration/pose·DM·manager·device 등 | 모든 all_checks/alive/valid/frequency는 SubMaster 원형. sensor/health 값은 테스트 입력 | 계획, 입력 필드 표/정상 기준 검사로 확인 예정 |
| SelfdriveD 초기화 | __init__와 data_sample의 정상 데이터 경로. SIMULATION/REPLAY false | initialized/초기 이벤트/건강 상태 | True 직접 주입 금지 |
| 활성 상태 | 원형 car event가 만드는 PCM/button enable → StateMachine | enabled/active/state → 실제 메시지 → CC.longActive | True 직접 주입 금지 |
| driver cancel/gas/brake | carState 또는 정상 PCM 수신 입력 변화 | 실제 car events/StateMachine/CC 및 card 적용 여부 | 정상 비교 기준으로 먼저 실행 예정 |
| Panda 상태 입력 | 가능한 경우 기존 실제 C 메모리 RX의 정상 PCM/wheels/torque/brake 수신으로 controlsAllowed 도출. source shortcut setter 사용 안 함 | 실제 C의 반환을 입력으로 사용 | MCU/heartbeat/물리 장치 준비는 별도 미검증 |
| card 최초 CI.init | 부모 승인에 따라 물리 IO sink로 호출만 기록 | 원형 card가 ControlsReady/initialized_prev를 스스로 만들게 함 | actual_init_executed=False, init_io_sink_calls 명시. ECU/UDS/펌웨어 준비 미실행 |
| CI.apply/송신 | 실제 CC를 기록하는 메모리 IO sink. 부분 CAN 계산을 추가하면 별도 범위로 표시 | 원형 card 조건을 통과했는지, 입력 CC 상태 | 실제 송신0. CarController/전체 CAN 안전 검증과 구분 |
| 누락 데이터/시간 | 생성·획득·발행·배달·수신·현재 시각을 각각 기록 | 원형 parser/health/이벤트/상태/제어 경계 판단 | 생산 watchdog/flags 수정 금지 |

| 사례 범주 |50/150/323/600/4000ms가 의미하는 것 | 유지되는 입력 | 제외/한계 |
|---|---|---|---|
| 정규 수신, 오래된 내용 | 원본 획득/내용 시각만 과거. 발행·수신 헤더는 새 값 | 정상20/100Hz 수신, body의 원시 출처 시각 보존 | 실제 신경망 인식 결과 검증 아님 |
| 지연된 오래된 메시지 | 획득/body/producer 헤더까지 그대로 보존해 늦게 전달 | 원형 receive-time은 실제 전달 시각. valid/processingDelay는 원본값을 별도 기록 | 새 헤더로 포장한 오래된 body 사례와 구분 |
| producer freeze | 모델만 또는 계획만 해당 기간 중단 | 나머지 서비스·호스트 판단 loop는 진행 | 한 컴포넌트 정지이며 전체 CPU 정지가 아님 |
| whole host CPU stall | 호스트 판단/발행 loop 전체를 중단한 뒤 시각을 전진시켜 재개 | 독립 차량/MCU의 가정은 명시하며 호스트 카운터는 건너뛰어 증가시키지 않음 | 실제 OS scheduler/MCU heartbeat/Panda 장치 정지의 재현이 아님 |
| 실제 sleep323ms 비교 | 벽시계 대기 후 원본 출처 보존 여부와 실제 시각 전진을 따로 비교 | 오래된 내용/새 헤더 실험과 분리 | 한 번의 의도적 대기이며 기존322.91ms 원인 규명이 아님 |

시간 전진에 따라 차량 모형도 실제 경과를 적분하는 실험은 ars510_audit의 별도 계측과 협의한다. 이 권한 검사에서 고정10ms plant 결과를 실제 지연 중 차량 운동으로 해석하지 않는다. 기본 비교는 비활성·정상 초기화·정상 enable·편안한 주행·driver cancel/gas/brake·미수신이 먼저다. 조건이 빠졌거나 다른 startup event가 정상 비교를 막으면 원인을 보고하며 판정 조건을 약화시키지 않는다.
