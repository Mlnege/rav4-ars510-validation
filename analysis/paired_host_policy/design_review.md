# 정확한 레이더 묶음·기록 정책·호스트 연결 독립 읽기 설계 검토

새 통합 검사는 **원본 CP와 CS/CAN 묶음의 연결, 기록된 Panda 모드의 C 상태, 호스트가 만든 명령**을 각각 보존하고 같은 명시적 시각 가정에서 연결해야 한다. 기존 369점/175선택/26,302거부는 이번 검사에 맞춰야 하는 정답이 아니다. 소스·시각·구성이 달라지는 부분과 실제 입출력을 대체하는 부분을 분리하면 오프라인 자료 전달을 검토할 수 있다. 실차 활성·ECU 준비·제동 응답·PCS/AEB 보증까지 검증할 수 있는 설계는 아니다.

이번 작업은 동결 도구·생산 source·새 IO_SCOPE_PLAN_KO 및 작성 중 helper 읽기와 파일 지문 식별만 수행했다. 로그 재생·테스트·호스트·MPC·C·빌드·차량 송신을 새로 실행하지 않았다. 허용한 이 문서만 작성했고 기존 파일·출력·release·라이브러리는 수정하지 않았다. B에게 직접 요청하지 않았으며 발견은 root에 전달했다. 새 runner와 결과가 아직 완성되기 전의 **설계 감사**이므로 아래 요구를 이미 통과한 검사로 보고하지 않는다.

## 읽은 계약과 현재 준비 상태

생산 can_batch.py/radarcan.py, card.py/alternative_experience.py, Toyota CarState/CarInterface/CarController와 공통 interface, DPathRadarD, ARS offline adapter, 현재 Toyota/elm327/공통 C 안전 source를 읽었다. 동결 actual_host/paired quality/recorded_panda_modes 도구와 새 paired_host_policy_integration의 계획·whole_io.py·whole_objects.py·log_io.py도 대조했다.

| 주요 생산 파일 | 읽은 SHA-256 |
|---|---|
| card.py | de239706c6194073d5758c7314d060146e4404b55648cdba90d183a59883b1a2 |
| can_batch.py | 73d72c3c45ef500886af90224cf3f64fbb3f2ca6c638bdc65b9986f0b83ec040 |
| radarcan.py | 3f2da75508194aa86179056574fa87fb0259c7aa65c45fd318b26325ef1c500b |
| radard_dpath.py | f3f3506398dd9bd939b96c83ab21409d8daf3f326fccabb6adf79fb1948d7be2 |
| ars510_offline.py | 8b471914b92466fb9589c298b976fe377eea18e7c111e81f89258cab45d12a50 |
| toyota/carcontroller.py | f09cebd050f822a5c181f6c706cc3eb752c3f90bca24f5415a86b7506d502d97 |
| safety.h | 264acef46827c278c8a741106506506323ec27842eaf21856a16386ebe084dfe |
| safety_toyota.h | a5c87dd55bce5a8f44e85e173784db42648a4982a95107dfe57a2479ec5d5cc0 |

새 계획은 storage_max/1Hz 위상0의 대표 log_a/log_b부터 실행하며, 원본 epoch·별도 순서 보존 batch 입력·원본 CP 복사·Card 출력과 원본 메타 분리·기록 C 모드와 통지 분리를 명시했다. 그 계획은 확인한 주요 위험을 다룬다. 다만 시작 점검의 복사 helper에는 아직 factory car_params/initialise 정의와 최신 메시지만 반환하는 MemorySocket이 있었다. 이 함수가 새 runner에서 그대로 호출된다는 증거는 아직 없으므로 **작성 중인 실행 결함으로 단정하지 않는다.** 최종 실행 source에서 실제 호출 경계가 달라졌는지 확인할 항목이다.

## 단계별 실행·입출력 구분

| 단계 | 보존하거나 실제 실행해야 할 계약 | 대체·미검증 범위와 판정 주의 |
|---|---|---|
| 원본 CP | 기록 wire를 현재 schema로 읽고 핵심 제어 필드를 대조. a/d directLong·73, b stockLong·585 | factory get_params의 alpha_long=True 결과를 원본 CP라고 쓰면 안 된다. 5개 CP 표본은 direct True3/False2다. 자료 없는 log_c는 추측 CP 없이 부족 유지 |
| CP 소유 | decoder용 원본 복사본과 host/CI/Card용 복사본을 별도 보존 | Card 생성자는 alt/passive/safetyConfigs를 쓸 수 있다. 원본 직렬화 불변과 생성자 뒤 제어 필드 대조는 서로 다른 검사 |
| 메모리 Params | 원형 기본값과 요청 프로필을 명시 | SpeedFromPCM0/Delay20/AlphaTrue/NNFF0·Signal 기본0은 시험 프로필이다. 원본 CP의 directLong/585를 바꿀 권한이나 기록 설정 전체 동일 증거가 아니다 |
| CAN batch | 원본 CAN Event 순서/헤더/전체 frame 목록과 원본 CS.radarInput으로 순수 RadarCanBatches 실행 | CAN/CS batch 입력에 latest-only MemorySocket을 쓰지 않는다. canPacketCount는 frame 수가 아니라 Event 수다. 402개 미결합 CAN을 가짜 CS나 warmup으로 넣지 않는다 |
| decoder | 정확한 CS의 vEgo/aEgo/receive와 각 packet의 원래 헤더를 offline=True adapter에 공급 | DLC·조립·CRC·sequence·타임아웃과 MyTrack 처리는 원형이다. ECU 내부 측정 시각/FW 정체와 runtime 등록은 미검증 |
| 오류 경로 | batch 오류·adapter 오류·정상 회복을 구분, liveTracks valid/errors와 radarState.errors 유지 | batch 오류 때 빈 오류를 전달하고 다음 정상 batch 전 재생성하는 경계를 명시. 원형 radarcan 전체 poll/socket/processingTimeout을 실행하지 않았다면 그 사실을 분리 |
| DPath | 원형 DPathRadarD.update와 source SubMaster의 건강 판단 | CP.radarUnavailable=True 유지, 독립 mode1 controller는 진단용이다. 생산 RadarInterface 등록·현재 runtime 지원·near 정책 활성과 다르다 |
| CarState | batch용 원본 CS는 독립 보존. CI.update 반환은 원본 CS의 별도 복사본 | 실제 ToyotaCI.update 전체 CAN 파싱은 미실행이다. Card가 바꾸는 radarInput/UI/blindspot/canErrorCounter를 원본 전체 동일로 표현하지 않는다 |
| source health | 원형 valid/alive/frequency·자연 초기화·이벤트/StateMachine/Controls 실행 | fresh header/valid=True 재발행이나 ignore 목록 증가로 오래된 원본을 건강하게 만들지 않는다. source 자체의 ignore·10초 초기화 timeout과 실제 건강 통과를 구분 |
| 계획·제어 계산 | 실제 LongitudinalPlanner/CarrotPlanner/native MPC/LongControl·ToyotaCI.apply/CC | 관측 ego를 고정 입력으로 공급하는 자료 재생이다. CAN이 실제 차량 운동을 바꾸는 폐루프나 물리 제동 응답은 아니다 |
| CI.init | 원형 Card의 init 조건/호출 수만 관측하고 물리 init은 sink | DISABLE_RADAR의 실제 UDS disable_ecu는 실행하지 않는다. 메모리 ControlsReady가 기록 Panda 전환을 대신하지 않는다 |
| C RX/모드 | 원본 physical RX만 현재 C에 공급, 기록 mode/param/alt 변경만 정식 함수로 적용 | 초기 unknown은 선언 silent. 반복 표본 reset/init_tests/권한·relay setter 금지. clock/유예는 명시적 MCU 가정 |
| C TX | CI.apply가 만든 메모리 CAN을 그 순간 같은 C 상태의 TX hook에 공급 | 실제 sendcan socket/Panda/ECU 송신은 없다. 모드별 허용/기대 거부/판정 미정 범주를 구분. C 허용은 PCS·실물 호환 증거가 아니다 |

## Card의 원본 CP와 CarState 변경

Card 생성자는 전달된 CI.CP를 그대로 참조한다(card.py:124–129). DisengageOnAccelerator=False이면 get_alternative_experience가 gas disengage 비트 1을 설정한다. 또한 OpenpilotEnabledToggle/CC 존재/dashcamOnly에 따라 passive를 정하고 passive면 safetyConfigs를 noOutput으로 바꾼다(card.py:130–137). 따라서 Card 뒤 CP와 원본 CP가 같다고 미리 가정하지 않는다. 원본 CP의 핵심 필드, CI 생성 직후, Card 생성 뒤, C 전달 값을 각각 제한된 bool·설정 숫자로 대조해야 한다. memory AlphaTrue를 이유로 b의 원본 directLong=False/585를 factory73으로 교체하지 않는다.

Card.state_update는 실제 소켓을 drain한 뒤 recv_ns를 얻고, CI.update 반환 CS의 radarInput을 새 packet bounds/count/recv_ns로 쓴다(card.py:204–214,254–257). 원본 CS의 builder를 공유하면 기록 batch 메타가 덮인다. batch에서는 미리 복사한 원본 RadarEgoSample/CS를 사용하고 Card에서는 별도 복사본을 써야 한다. 빈 CAN placeholder에서 새로 생긴 first/last/count=0은 기록 메타가 없었다는 근거가 아니다. 동작을 그대로 실행하면서 출력 변경을 관측하는 것과 원본 출력의 모든 필드를 유지하는 것은 다른 경계다.

CarState의 원본 Event.valid와 CS.canValid는 별개다. source Card.state_publish는 새 Event.valid=CS.canValid와 현재 헤더를 만든다. 원본 표본의 valid/header를 보존해 downstream에 배달하는 경계는 **명시적 재생 I/O 대체**로 표기해야 한다. 같은 held body를 매100Hz마다 새 header로 정상 발행하지 않고 새 기록 표본의 전달 수·병합 수·header age를 따로 남기는 편이 정확하다. 원형 SM의 recv_time 기반 alive와 원본 header age도 같은 지표가 아니다.

## 내부 Toyota 피드백의 빠진 범위

기존 proxy는 실제 CAN을 Python DBC parser로 읽어 GVC/PCM_CRUISE 상태/PCM follow distance/카메라 HUD를 내부 CS에 공급한다. 첫 메시지가 아직 없거나 오래됐을 때의 기본값·마지막 값·freshness는 전체 CI.update 검증과 다르므로 별도 집계 대상이다. source 보존 표본이 15개 필드라면 그 범위 밖의 전체 내부 상태까지 같다고 확대하지 않는다.

추가로 Toyota CarState는 TSS2이면서 DISABLE_RADAR가 꺼진 경우 ACC_CONTROL.ACC_TYPE을 CS.acc_type에 읽는다(carstate.py:153–154). 기존 proxy의 parser 목록에는 이 내부 값 갱신이 없고 CarState 초기값은 1이다. a/d의 disable 분기와 b의 stock 분기를 구분해야 한다. 현재 b의 제어 OFF·취소False 경로라면 이 값이 생성 ACC에 쓰이지 않을 수 있으므로 지금 확인한 실행 결함은 아니다. final source/결과에서 이 값의 관측/기본값/미사용 범위를 밝히고, 임의로 검증되지 않은 ACC_TYPE이나 가짜 firmware를 정의하지 않는다. 실제 CI.update 대신 original CS 반환이라는 기본 한계는 유지한다.

## 시각 계약

| 시각 | 사용 주체·의미 | 같은 값으로 취급하면 안 되는 범위 |
|---|---|---|
| Cᵢ: CAN Event 헤더 | 원본 packet 순서와 assembler/support cache | 하드웨어 개별 frame 수신·ECU 내부 객체 획득 시각을 보증하지 않는다 |
| F/K: record 첫/마지막 프레임 | 원형 fused filter는 F의 dt, 조립은 K−F. MyTrack은 고정0.06초 | F/K를 임의로 receive 또는 모델 EOF로 바꾸지 않는다. RadarPoint에는 F/K가 전달되지 않는다 |
| R: 원본 CS.receiveMonoTime | 정확한 batch와 ego 결합, adapter 외부 호출 | Card가 새로 만든 R 또는 publication P로 대체하지 않는다 |
| S: 원본 CS Event 헤더 | recorded state 배달 메타·age 관측 | 최신 synthetic Card 헤더와 다르다. 비동기 저장의 앞뒤 관계만으로 실제 app 수신 순서를 확정하지 않는다 |
| N: 저장순서 최대 헤더 | 이번 storage_max의 가정 consumer clock, source batch age N−R | 실제 수집기/소켓/OS wall receipt가 아니다. input_max는 별도의 clock 가정이며 섞지 않는다 |
| P: 새 liveTracks 발행 헤더 | DPath가 모델 EOF E−P로 투영하고 CP.radarDelay를 더함 | 직접 replay의 CAN 헤더 publication 대용과 다르다. 175선택을 맞추려고 P를 F/R/E로 강제하지 않는다 |
| E: model timestampEof | 원형 DPath 측정 시각;0이면 모델 헤더 fallback | message 헤더와 획득 EOF는 서로 다른 시각이다. 카메라 readout/BOOT·MONOTONIC clock 기원은 실물 검증 대상 |
| H:100Hz host tick | timeline 배달 후 Card/계획/상태/Controls 순서를 실행하는 가정 격자 | source 함수 호출이 전체 프로세스 스케줄러/실시간 성능 측정은 아니다. 같은 tick의 복수 model/CS 병합 수를 기록 |
| U:C timer µs·counter | 같은 RX/TX C 상태에서 elapsed µs와 외부1Hz 위상을 진행 | 실제 MCU boot/heartbeat/시계가 아니다. 모드 전환 reset과 시간 진행을 분리하고 uint32 wrap을 명시 |

현재 계획의 **원본 epoch 유지**는 nested 시각을 빠뜨려 batch 경계를 깨뜨리는 재배치 위험을 줄인다. 그래도 host Clock.now·새 메시지 P·SM recv_time을 생성자 호출 전부터 그 epoch와 일치시키고, C 타이머는 명시적으로 별도 상대 µs로 변환해야 한다. wall/perf/thread CPU 측정은 원본 시각으로 위조하지 않는다. storage_max에 소프트웨어 연산 wall 비용이 자동 포함되는 것은 아니므로 처리 deadline 통과 보증으로 쓸 수 없다.

재배치를 별도 선택한다면 같은 상수 offset을 CAN/CS header, nested radarInput.first/last/receive, model/camera EOF/SOF, livePose timestamp와 소비하는 message-reference NS에 모두 적용해야 한다. 0 sentinel은 0으로 유지하고 processingDelay·주기·지연 같은 duration에는 offset을 넣지 않는다. 이 목록만으로 모든 schema 필드를 자동 확정하지 않는다. 실제 소비하는 NS 필드를 source/schema로 열거하고 전후 차이·batch count·상대 age 불변을 먼저 대조해야 한다. 옛 current_event는 top-level/EOF 일부만 바꾸고 nested radarInput은 바꾸지 않았으므로 새 정확한 묶음 경로에 그대로 쓰는 것은 부적절하다.

## source health·actor 순서·원본 제어 OFF

원형 SelfdriveD는 CS.canValid와 sm.all_checks로 초기화하거나 frame*DT_CTRL>10초 timeout으로 초기화한다(selfdrived.py:584–585). initialized=True만으로 건강한 서비스 전체가 통과했다고 보고하지 않는다. REPLAY/SIMULATION/TESTING_CLOSET의 단축 초기화나 새 ignore를 넣지 않고, 원형 AST globals·상수·기본값을 최종 실행 source와 대조해야 한다. 카메라 inventory·외부 fault 파일·Params·socket 대체는 source 건강 판단을 실행했다는 사실과 별도로 표시한다.

Card.step은 이전 큐 carControl로 apply하고 다음 Controls가 새 CC를 만드는 순서가 될 수 있다(card.py:444–449). 선택한 actor 순서와 1틱 큐를 명시하고 raw RX→C 상태·Panda 전환·host apply/TX의 순서를 보존해야 한다. sourceSelfdriveD는 Panda model/param/alt mismatch를 원래 유예·이벤트로 처리한다(selfdrived.py:383–396). 그 mismatch를 원본 CP와 맞추려고 Panda metadata나 C 권한을 고정하면 안 된다. 원본 OFF·페달·기어·문/벨트·invalid 자료를 유지한 결과 enabled/longActive가0이면 비활성 자료 연결로 보고한다.

레이더 단계와100Hz host 단계가 별도 준비/소비인 이번 계획은 계산 그래프 연결과 원본 자료 사용을 확인할 수 있다. DPath를 사전 계산한 timeline이면 같은 live actor가 실제 소켓에서 동시 실행한 검사가 아니며, 차량 운동 피드백도 없다. model 업데이트/점 발행/선행 선택/실제 MPC 입력/선택 source/호스트 활성/C 허용의 카운트를 따로 기록해야 한다. CRC 정상 record, shared record별 점 개수, 좌표·속도 전값 동일도 서로 다른 지표다.

## 같은 C 상태와 모드별 TX 전제

기록 모드 Probe와 CI.apply TX는 **같은 C 상태**를 사용해야 한다. 별도 VehiclePermissionInput 생성자는 init_tests로 counter=2를 만들고 C 전역 상태를 바꾸므로 함께 호출해 기록 모드를 덮으면 안 된다. 같은 .so를 여러 CDLL/Probe로 읽어도 프로세스 C 전역 상태가 분리됐다고 가정하지 않는다. 메모리 ControlsReady는 실제 CI.init/Panda 준비와 다르며 C 모드 전환의 입력으로 쓰지 않는다. 기록상 mode/param 변경에만 정식 set_safety_hooks를 쓰고 반복 표본은 reset하지 않는다. alt-only 변경도 source와 동일하게 별도 처리한다.

| 당시 C 모드 | 생성 메시지에 적용할 source 조건 | 금지되는 단순화 |
|---|---|---|
| 첫 관측 전 silent | 무출력 정책. 초기 실제 모드가 알려진 것이 아니라 안전한 선언 입력 | 처음부터 Toyota73/counter2라고 고정하지 않는다 |
| elm327 | 원형 hook은 DLC8과 허용 진단 주소 규칙. 0x750은 주소상 가능하지만 Toyota 제어 ID는 규칙 밖 | 비ACC 전부허용, OFF이면 전부거부 둘 다 이 모드의 정확한 기대값이 아니다 |
| Toyota73 direct | 정확한 addr/bus/DLC whitelist·relay와 메시지별 조건.0x343은 inactive0 또는 long 권한과−3500..2000 | long 권한 False에서도 inactive0이 조건부 허용된다. unknown steering를 그냥허용하지 않는다 |
| Toyota585 stock | stock whitelist이며0x343은 inactive0에 CANCEL_REQ도 필요.0x411/0x750은 direct용 목록과 다름 | direct의주기/메시지/기대값을 b에복사하지 않는다 |

CarController는 direct CP에서0x343을 frame%3으로 만들고 stock CP에서는 cancel 시에만0 가속 cancel을 만든다(carcontroller.py:191–272).0x411과 tester-present0x750은 enableDsu/DISABLE_RADAR 조건과 각 주기가 있다(:293–303). 실측 생성 목록으로 bus/DLC·frame·정의된 checksum·DBC 해독을 검사하고 없는 메시지를 맞추기 위해 추가하지 않는다.0x411 PCS_OFF 표시나0x750 tester-present의 메모리 생성/C 허용은 순정 PCS/AEB 보존 또는 실제 UDS/firmware 호환 증거가 아니다.

공통 C는 gas alt1에서 controls_allowed를 유지할 수 있어도 longitudinal_allowed=controls_allowed&&!gas_pressed_prev로 판정한다(safety.h:299–300). TX 때문에 권한을 만들거나 변경하면 안 된다. 원본에서 C 권한이 False인 입력의 정상 inactive/cancel 허용과 예상 거부는 둘 다 정상 결과일 수 있다. relay 감지는 counter>1과 stock 메시지 조건을 사용하며 정식 모드 전환 reset·외부1Hz 위상은 실제 MCU clock/부팅/heartbeat 증명이 아니다.

## 완료 뒤 필요한 관측과 보고 제한

최종 source에서는 원본 CP/decoder CP/Card 뒤 CP/C 설정을 구분하고, 원본 CS 표본 수·valid/header 보존·Card 수정 범위·batch 수용/stale/pending/제외/재생성·같은 C RX/TX 상태·모드 변화 수·TX 권한 전후·모델 병합 수·MPC status·각 오류 전파를 익명 count/상대 분포로 확인해야 한다. 기대값을 정의하지 않은 모드/steering는 별도 관측으로 남기며 C 반환이 어떤 이유인지 추측으로 통과 처리하지 않는다. 처음 실패·준비 오류·정정은 보존하고 원형 결과를 덮지 않는다.

제공 데이터에는 순정 PCM OFF·비활성 제어 관측이 있으므로 이 설계가 성공해도 실제 활성 운전 타이밍·급제동·회생·신호 인식·ECU/펌웨어 정체·ARM전체빌드·PCS/AEB는 미검증이다. native MPC/C/Cython 및 안전 C와 Python CAN backend를 구분한다. 공개 결과에는 원본 절대 시각·payload·객체ID/좌표·VIN/serial/계정·시크릿을 저장하지 않고 개인 원본 CP bytes의 지문도 공개 근거로 추가하지 않는다. 실제 runtime hook/CP false/age cutoff/원형 필터/안전 제한을 이번 연결 성과로 바꾸지 않는다.
