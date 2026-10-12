# Mode0 호스트 + SignalMode2 + Toyota 생성 CAN + 메모리 C 검사 계획

신규 도구/결과만 이 폴더에 쓴다. 기존 모든 결과·생산 source·immutable MPC/C 라이브러리·운영 Params는 변경하지 않는다. 실제 CI.init/UDS/소켓/Panda/차량 TX를 실행하지 않는다.

| 경계/조건 | 실제 입력/실행 계획 | 미검증/금지 |
|---|---|---|
| NativeSignalHarness 자료 | native_signal.py/core.py의 스키마 필드와 관측 writer 형식만 읽어 옮긴다. 이 모듈들은 import 시 prepare가 messaging/Params를 다시 대체하므로 직접 import하지 않는다 | NativeSignalHarness가 고정한 enabled/valid/seen/all_checks를 전체 호스트에서 사용하지 않음 |
| 메시지 건강 | 원형 SubMaster/FrequencyTracker에 기존 정상100/20Hz 메모리 서비스 발행. 실제 seen/valid/alive/recv_time 형성 | 건강 판정을 True로 고정하지 않음. 가상시각은 벽시계/실물 BOOTTIME 검증이 아님 |
| 설정 | 원형 MemoryConfiguration 읽기값 Mode0/LongActDelay20/AlphaTrue/SignalAssist2, 실제 factoryCP와 원형 Card constructor | 운영 Params/CP flags force 금지. 기존 signal_mode.flag_override가 retired assist_enabled=False, start/prepare>0을 정하게 함 |
| 신호 관측 파일 | 기존 publish_start_observation/publish_prepare_observation을 실행. JSON 크기/해석은 원형, 파일 읽기/임시교체만 메모리 저장소 | 원형 Runtime.read/Guard/Prepare 판단 치환 금지. 실제 이미지/추적/신호 인식 성공은 아님 |
| 관측 스키마 | version1/road/size1344×760, session/frame_id/timestamp_eof, 검증된 box·raw color·age0·observations10/evidence품질 | 없는 CAN/신호 필드를 정의하지 않음. EOF와 producer/delivery 시각을 분리 |
| known OX metadata | deviceType=tizi, roadCameraState.sensor=ox03c10, 합성 frame dimensions1928×1208 → 원형 tracking_camera_profile로 source_size/full_frame_resize 생성 | 실제 camerad NV12 버퍼/하드웨어 metadata/실물 보정값은 아님. 매치하지 않으면 source prepare가 차단하도록 유지 |
| geometry/pose | core.py 기존33개 laneLine/roadEdge XYZ·probs/stds, liveCalibration calibrated/rpy0, 실제 XYZ pose스키마 valid/std와 입력 건강 | 실제 획득 좌표/차선 귀속/거리 측정·카메라 정확도는 미검증 |
| 초기화/활성화 | disabled·CCFalse에서 원형 건강 준비→MAIN available→정상PCM enable. enabled/longActive는 SelfdriveD/StateMachine/Controls가 생성 | 전체 호스트 baseline가 막히면 조건을 지우지 않고 실패/NoEntry 원인을 기록 |
| 정지 red-hold | 명시한 합성 ego0/standstillTrue/GVC0, 모델의 미래 진행 의도는 NativeHarness의 기존33노드 계산 형식. 원형 runtime의 actualSubMaster valid/enabled와 StartGuard red 확정 관찰 | standstill에서 모델 자체 정지와 신호 hold를 혼동하지 않음. 미래 모델 진행 의도도 실제 계획/이미지 예측이 아님 |
| Toyota/C | 앞선 실제CI.apply/ToyotaCC/CANPacker/출력DBC decode와 같은 메모리C hook. 정상 PCM RX로 권한 생성 | C controlsAllowed setter True0. CI.update/stock feedback/ECU반응은 합성. PCS/회생/ARS live 미검증 |

기본 actor 순서: 외부 CS/센서 → card(이전큐CC) → model20Hz 계획(원형 runtime) → selfdrived → controls100Hz → 다음 card. 관측 파일 발행은 model 직전/직후를 별도로 비교한다. 원형 read를 관찰하는 wrapper가 마지막 context를 기록하되 원형 반환과 판단을 그대로 전달하며 enabled/valid를 덮어쓰지 않는다.

정상 baseline부터 red-hold 획득·유지를 확인한 후 green/unknown/관측 stale/수신서비스 중단·가스해제·제동/취소·PCM재시작을 비교한다. gas 시작은 model tick에서0/10/20/30/40ms로 나눈다. 새gas와 이전CCtrue를 먼저 보면 guard gas branch의10초 cooldown이 생길 수 있고, 이미CCfalse를 보면 enabled=False branch가 먼저 reset할 수 있다. 이 소스 순서 의심은 실제 출력 전에는 결함/안전성으로 확정하지 않는다. 기존23조건은 gas=False의CC-only 대체이므로 자연gas 경로와 구분한다.

매행 원시 EOF/관측 delivery/read age, CS gas/brake/ego, 수신 sd.enabled·CCenabled/longActive, actual Runtime enabled/valid, guard hold/anchor/cooldown, 새 CC/plan/native status, 생성0x343 signedraw, C controls/long_allowed/TX 결과를 기록한다. softDisabling은 enabled=True와 active=True를 유지하므로 LongActive=False와 같은 상태라고 가정하지 않는다. 현재 source 그대로 관찰하고 새 watchdog·200ms 정책·권한 우회는 구현하지 않는다.
