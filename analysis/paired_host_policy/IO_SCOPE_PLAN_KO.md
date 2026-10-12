# 원본 레이더 배치와 기록 정책의 호스트 연결 계획

대표 log_a/log_b를 storage_max 수신 가정과 1Hz 위상0으로 먼저 실행한다. 생산 source·기존 결과·운영 설정·공유 빌드는 변경하지 않는다. 실패나 다른 개수가 나오면 보존하며 기존 369점/175선택에 맞추지 않는다.

| 경계 | 실행할 원형 | 명시한 입출력과 한계 |
|---|---|---|
| 입력 | 기록 schema와 원형 replay events | 원본 body와 모든 시각을 메모리에서 읽는다. 원문·좌표·ID·절대 원본 시각은 저장하지 않는다 |
| 시각 | 원본 epoch 유지 | header·CS nested radarInput·camera/model/pose의 NS는 재배치하지 않는다. 저장순서 최대 헤더가 가정 배달 시각이며 MCU는 별도 상대 타이머·1Hz 위상0이다 |
| 레이더 batch | 원형 RadarCanBatches/RadarEgoSample | 원본 CAN/CS의 별도 순서 보존 목록을 사용한다. MemorySocket의 최신 메시지 병합을 batch 수집에 쓰지 않는다 |
| 해독 | offline=True ARS adapter | 정확한 batch CS의 ego/receive와 원본 packet header·bytes를 공급한다. 원본 CP는 별도 복사본으로 유지한다 |
| 오류 | 원형 batch 오류와 adapter 오류 | 초기 no-record와 정상 처리 이후 오류를 분리. 오류를 liveTracks/radarState에 보존하고 정상 회복 시 adapter 재생성 범위를 기록한다. radarcan 소켓/main 전체 루프는 실행하지 않는다 |
| DPath | 원형 DPathRadarD.update | 원본 CS/model/pose와 독립 진단 mode1 controller만 사용. CP.radarUnavailable=True 유지, runtime 등록 없음 |
| CP/호스트 | 원본 CP wire→현재 cereal, 원형 Card/SelfdriveD/StateMachine/Controls | factory get_params를 호출하지 않는다. 원본 CP a/d direct73, b stock585를 공급하고 생성자가 변경한 제어 필드를 전후 대조한다 |
| Card 상태 | 원형 Card.state_update/VCruiseCarrot/step | CI.update 반환만 원본 CS의 별도 복사본. Card가 덮는 radarInput/UI 필드를 관찰하고 batch용 원본 CS와 혼동하지 않는다. 원본 header/valid의 새 표본 배달만 수행한다 |
| 계획/출력 | 원형 CarrotPlanner/LongitudinalPlanner·실제 native MPC·Toyota CI.apply/CC/CANPacker | 관측한 ego/모델 자료이며 차량 운동 반응은 미검증. 물리 CI.init은 sink, 실제 전체 CI.update 미실행 |
| Panda 정책 | 기록 mode/param/alt 변경만 실제 C set_safety_hooks | 정상 모드 변경만 reset. init_tests·controls/relay setter·반복 reset 금지. 실제 설치 펌웨어/MCU heartbeat는 미확인 |
| CAN 분류 | 원본 physical RX·returned/rejected 통지 | 전체 항목 소비 및 범주 합계 확인. physical RX만 실제 C RX, 통지 bytes/src는 유지하고 재주입하지 않는다 |
| C TX | 실제 생성 CAN의 현재 hook | Toyota direct/stock 정책을 구분한다. 검사 정의가 없는 steering/다른 모드의 결과를 임의 허용으로 대체하지 않는다. TX가 권한을 만들지 않는지도 관찰한다 |

레이더·DPath 준비 단계와 100Hz 호스트 소비는 같은 runner 안에서 분리된 메모리 서비스로 연결한다. 레이더 batch와 model 처리는 원본 저장순서의 가정 수신 시각에서 실행하며 호스트 수신은 100Hz 격자로 올린다. 이에 따른 표본 병합·배달 나이를 기록하고 실제 소켓 스케줄러 동작으로 주장하지 않는다. input_max는 CAN/CS 헤더만 시각을 진행하는 별도 가정이며 필요할 때 새 조건으로 실행한다.

동결 참고는 radar_input_contract_probe의 paired_adapter_replay_quality.py/paired_run01/quality_run05_frozen, recorded_panda_mode_replay, ars_host_can_replay다. quality의 storage_max 결과는 a246점/479레코드, b115점/990레코드·staleEgoState25개다. 신규 DPath와 호스트 결과는 별도 측정한다. 원본 CP wire 핵심 필드 일치는 부모의 cp_wire_contract_probe 독립 결과이며 이번 생성자 검증과 구분한다.

메모리 Params는 요청 프로필 SpeedFromPCM0/LongActuatorDelay20/AlphaTrue/NNFF0이며 원본 CP의 directLong/안전 파라미터를 변경하는 근거로 쓰지 않는다. SignalAssistMode는 원형 기본0이다. 원본 PCM OFF·운전자/문/벨트/기어·valid·오류를 유지한다. ARS live/실제 TX/운영 Params/회생/PCS/AEB는 미검증이며 적용하지 않는다.

native pandad CAN 헤더와 camera EOF는 BOOTTIME, Python Card 수신/발행은 MONOTONIC source 경로다. 원본 epoch의 숫자를 공통 축으로 쓰는 것은 이 자료의 재생 가정이며 실제 장치 clock 동등성·절전 이력을 증명하지 않는다. 원본 liveTracks 서비스는 입력에 넣지 않고 새 ARS shadow 처리에서 만드는 가정 발행 P를 따로 사용한다. 실제 wall 처리 시각으로 주장하지 않는다. stock ACC_TYPE는 원형 Toyota의 powertrain ACC_CONTROL 신호를 추가로 해독하고 미수신 기본값은 별도 집계한다.

재실행 파일은 새 work 직하 폴더로 재배치 가능하게 만들고 alias/clock/위상 CLI와 새 출력 폴더를 요구한다. stdout/stderr의 원본 코어 출력은 폐기하며 익명 검사 요약만 반환한다.
