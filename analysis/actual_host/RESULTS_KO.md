# 실제 ARS 자료와 비활성 호스트의 오프라인 연결 결과

제공된 기록에서 실제 CAN으로 해독한 **369개 점 발행과 CRC 정상 2,433레코드**를 원형 DPath에 연결했고, 그중 **레이더 선행차 선택 175회가 실제 C/Cython MPC 입력까지 전달**됐다. 가짜 레이더 객체나 가짜 영상 선행차를 추가하지 않았다.

호스트·Toyota 제어기·CAN 생성·현재 C 안전 검사까지 메모리에서 실행했다. 원본의 순정 크루즈 OFF, 페달, 기어, 문, 벨트와 순정 CAN을 보존한 결과 활성화 횟수는 0이었다. 생성한 CAN 26,302개는 현재 테스트 C 설정에서 모두 거부됐다. 이는 **자료 전달과 비활성 상태의 관측 결과**이며 실제 차량 제어 성공 결과가 아니다.

| 익명 입력 | ARS 점 발행 | CRC 정상 레코드 | DPath 레이더 선행 선택 | 호스트 MPC 갱신 | MPC의 레이더 선행 소비 | 생성 CAN / C 거부 |
|---|---:|---:|---:|---:|---:|---:|
| log_a | 246 | 481 | 175 | 623 | 175 | 5,624 / 5,624 |
| log_b | 117 | 1,021 | 0 | 986 | 0 | 9,757 / 9,757 |
| log_c | 0 | 0 | 미실행 | 미실행 | 미실행 | 미실행 |
| log_d | 6 | 931 | 0 | 1,150 | 0 | 10,921 / 10,921 |
| 합계 | 369 | 2,433 | 175 | 2,759 | 175 | 26,302 / 26,302 |

점 발행 수는 서로 다른 객체의 수가 아니다. log_c에는 초기 정보와 경계 이벤트만 있고 CP/차량상태/모델/CAN이 없어 필요한 자료를 추측으로 채우지 않았다.

기존 replay를 이번 폴더에서 직접 다시 실행한 `offline_comparison.json`은 같은 369/2,433/175를 얻었다. 이전에 전파하지 않던 `radarErrors`를 수정한 **현재 replay 버전**을 읽었으며 실행 전후 지문은 `c5d91ef5c12dd3ca537d0de65e1b338fe25fcac31478e7059e299fb41cb9f1a6`로 같다. 원형 DPath의 모델 처리 2,792회 중 새 100Hz 수신 가정에서는 log_b 모델 33개가 같은 수신 묶음에서 합쳐져 MPC는 2,759회 실행됐다. 이 차이를 숨기거나 2,792회 전체를 MPC 처리로 보고하지 않는다. MPC의 전체 `lead0/lead1` 선택 262회에는 원본 영상 선행차가 포함되므로 ARS만의 선택 횟수로 쓰지 않는다.

## 원형으로 실행한 부분과 입출력 대체

| 부분 | 실행 범위 | 미실행 또는 대체 범위 |
|---|---|---|
| ARS 해독 | 원본 CAN 순서·헤더, offline=True 어댑터, 원형 fused/MyTrack | ECU 실물/펌웨어 정체, 차량 live 등록 |
| DPath | 원본 CS·model·pose를 공급한 실제 `DPathRadarD.update`, 수신 검증용 독립 mode1 controller | CP.radarUnavailable 변경 및 운영 mode 변경 없음 |
| 수신 건강 | 원형 SubMaster/FrequencyTracker가 메모리 메시지의 valid/alive/frequency를 판단 | 실제 소켓, OS 지연, 물리 수집기 동작 |
| 호스트 권한 | 원형 Card.state_update/step, VCruiseCarrot, SelfdriveD, StateMachine, Controls | CI.update 반환 경계는 원본 기록 CS; 실제 차량 파서 전체는 미실행 |
| 계획 | 실제 CarrotPlanner/LongitudinalPlanner와 기존 native C/Cython MPC | 실제 운행 응답과 차량 운동 재현 없음 |
| Toyota 출력 | 실제 CI.apply/CarController/CANPacker와 기존 DBC 해독·체크섬 검사 | 생성 CAN은 메모리만; 소켓·Panda·차량 송신 없음 |
| C 권한 | 원본 CAN 전체를 현재 C RX/TX hook에 공급 | 실제 Panda의 설정·MCU heartbeat·물리 준비·릴레이 검증 없음 |
| 초기화 | 원형 Card가 초기화 조건을 판단하고 메모리 init sink를 호출 | 실제 CI.init/UDS 본문 실행 없음 |

factory CP는 수동 RAV4 2022 식별과 `alpha_long=True`를 사용하는 시험 구성이다. 메모리 Params는 SpeedFromPCM=0, LongActuatorDelay=20, AlphaLongitudinalEnabled=True, NNFF=0이며 SignalAssistMode는 원형 기본 0이다. 원본 decoder CP는 바꾸지 않았고 원본과 시험 호스트의 `radarUnavailable=True`를 유지했다. 시험 CP의 directLong 구성은 원본 모든 기록의 제어 상태가 같다는 뜻이 아니다.

이전 합성 하네스에 있는 `whole_inputs.event` 및 `VehiclePermissionInput.update`는 호출하지 않았다. 마지막 함수의 호출 증거용 수신 카운터는 세 실행 모두 0이었다. C 권한은 초기 False에서 원본 RX만 읽었고 controlsAllowed=True를 넣는 단축 경로는 사용하지 않았다.

원본 CS의 canValid/canTimeout, ego 속도 3종·가속도, gas/brake, 문/벨트/기어, standstill, 조향각·토크 2종의 **15개 필드**를 각 Card 틱에서 직접 대조해 불일치 0을 확인했다. 순정 크루즈 available/enabled/설정속도의 입력 집계는 15,401개 CS에서 모두 OFF/0이었다. 원형 Card가 갱신하는 VCruise/UI/병합 blindspot와 radarInput까지 원본과 같다고 주장하지 않는다. GVC·PCM 상태·차간거리·camera HUD는 원본 CAN을 기존 Toyota DBC로 해독했다. 세 실행의 이 피드백 미수신 집계는 비어 있었다.

동일 메모리 설정을 사용한 **별도 초기 구성 표본**을 직접 실행했다. get_params 직후 alternativeExperience는 0이고, 원형 Card 생성자가 DisengageOnAccelerator 설정을 반영한 뒤에는 1이다. 기존 실행도 Card 생성 뒤의 CP를 C에 전달한다. 그 최종 표본은 Toyota safetyModel raw2/safetyParam73/alternativeExperience1/flags1372였으며 C 전달 인수 (2,73)/alt1과 같았다. initial controlsAllowed/longAllowed는 False이고 RX/합성 permission update/init sink 호출 모두 0이었다. 이 표본은 기존 세 재생을 다시 실행한 결과가 아니며 `factory_config_sample.json`에 분리했다. get_params 단독 alt0 표본도 보존했다.

다른 팀이 직접 실행한 원본 Panda 설정 집계를 읽어 대조했다. log_a/log_d는 기록 CP 및 Toyota 모드 Panda에서 param73/alt1이고 log_b는 param585/alt1이었다. 이번 factory/C 시험은 세 파일 모두 73/alt1이므로 **log_b의 기록 안전 정책을 그대로 재현한 C 시험은 아니다.** 585−73=512는 현재 Toyota 안전 source의 stock-longitudinal 비트다. 원본 Panda 집계는 초기 elm327 모드도 포함하며 모든 controlsAllowed=True와 safetyRxChecksInvalid=True 및 fault 표본은 0이었다. 이 별도 집계가 현재 C의 relay=True를 실물 고장으로 바꾸어 해석하지 않는다. 입력 설정 증거의 출처는 `work/panda_policy_probe/run01/results.json`이고 이번 하네스의 직접 실행으로 세지 않는다.

추가 원본 CP 대조에서 log_a의 1개와 log_d의 2개는 directLong=True/flags1372/param73, log_b의 2개는 directLong=False/flags1368/param585였다. 모두 pcmCruise=True/radarUnavailable=True/alt1이다. **전체 5개 원본 CP가 모두 directLong=True였다는 해석은 잘못이다.** 이번 결과의 recorded_cp_unchanged는 decoder가 읽은 원본 CP를 실행 전후 바꾸지 않았다는 검사이며, 합성 factory 호스트 CP가 원본 CP와 같다는 검사가 아니다. 특히 log_b에서 이 차이를 유지한다.

## 오류, 건강과 제어 OFF의 의미

| 관측 | log_a | log_b | log_d | 해석 |
|---|---:|---:|---:|---|
| 호스트 틱 | 3,365 | 6,022 | 6,020 | 가정한 100Hz 수신 격자 |
| 호스트 초기화 완료 틱 | 2,894 | 5,021 | 5,620 | 실제 CI.init 실행과 다름 |
| 호스트 enabled / longActive | 0 / 0 | 0 / 0 | 0 / 0 | 원본 OFF와 차단 이벤트 보존 |
| C controlsAllowed / longAllowed True 틱 | 0 / 0 | 0 / 0 | 0 / 0 | 현재 C 설정에서 원본 RX의 결과 |
| C relay 감지 틱 | 3,365 | 6,022 | 6,020 | 실물 릴레이 고장 확정이 아님 |
| radarState 오류가 있는 모델 | 44 | 0 | 27 | 총 71개 오류를 상위 자료에 보존 |
| 첫 완성 레코드 상대시각 | 6.089초 | 0.023초 | 5.347초 | 첫 자료 전의 임시 불가와 정상 자료를 구분 |

현재 C의 relay 값은 **선언한 factory CP·현재 안전 코드에 원본 순정 CAN을 넣어 관측한 메모리 결과**다. 원본 Panda 설정과의 차이는 위 별도 집계에서 읽은 근거이며 기록 펌웨어의 설치 코드·실물 릴레이 동작까지 대조하지 않았다. 순정 CAN에서 stock 송신을 발견했다고 실제 Panda 하드웨어 고장으로 단정하지 않는다. 생성 CAN의 거부 26,302개는 이 조건에 맞는 기대 결과이며 불일치 0이었다. 비영 ACC 요청도 0, 권한이 TX 때문에 생기는 변동도 0이었다. 비활성 ACC 0도 relay 조건에서 거부되므로 권한 False 검사만으로 설명을 단순화하지 않는다.

원형 SelfdriveD의 초기화 전 경로는 이벤트 판단 일부를 먼저 끝낸다. 따라서 초기 레이더 임시 불가가 자료에 보존돼도 모든 틱에서 radarTempUnavailable 이벤트가 반드시 생기는 것은 아니다. 문·벨트·기어·페달·pcmDisable 등 관측 이벤트와 valid/alive/frequency 부족 집계는 각 익명 result.json에 남겼다. 초기화 또는 제어를 성공시키기 위해 이벤트를 삭제하거나 건강 값을 True로 바꾸지 않았다.

원본 스트림에서 adapter timeout 진단은 0이다. CAN을 추가로 받지 않을 때 adapter를 별도로 빈 호출해 신규 timeout을 만들지는 않았다. 이러한 decoder timeout과 SubMaster의 liveTracks 수신 alive 판단은 다른 범위다. log_d에서는 실제 sequence error 1개와 history reset 1개를 그대로 기록했다. 첫 레코드 전 임시 불가를 마지막 정상 자료의 timeout으로 바꾸지 않았다.

## 시각과 생산 레이더 배치 경계

decoder는 원본 CAN 헤더와 저장순서를 사용한다. 새 호스트 배달은 저장순서를 유지하면서 지금까지 관찰한 최대 헤더를 100Hz 격자에 넣는 가정이다. CAN 자체의 헤더 역행은 세 로그 모두 0이지만 서로 다른 서비스의 저장 헤더는 앞뒤로 섞여 있다. CAN 순서를 헤더 정렬로 바꾸지 않았다. 호스트·DPath의 top-level header와 model/camera EOF·pose timestamp는 같은 상수 차이로 재배치했다.

원형 Card가 새 100Hz 헤더를 만들어 오래된 CS body를 신선한 것처럼 전달하지 않도록, downstream carState 배달은 새 기록 CS 표본이 있을 때만 수행하며 그 기록의 header/valid를 쓴다. 이는 **재생 입출력 대체**이고 생산 Card의 발행 동작과 그대로 같다는 뜻이 아니다. 한 틱 안의 여러 기록 CS는 마지막 표본으로 합쳐질 수 있다. 생성된 Card 헤더가 원본 수집 시각을 증명하지 않는다. 결과에 원본 CS 헤더의 나이 범위를 별도로 기록했다.

생산 radarcan은 원본 CS.radarInput의 firstCanMonoTime/lastCanMonoTime/canPacketCount/receiveMonoTime을 사용하는 `RadarCanBatches`와 100ms 수신나이 검사를 거친다. **이번 경로는 원본 CAN 이벤트를 direct-adapter에 넣으며 그 생산 배치 경계를 실행하지 않았다.** current_event는 원본 CS의 nested radarInput 시각을 재배치하지 않으며 원형 Card.state_update는 빈 CAN 수집 입출력의 새 radarInput을 쓴다. 이 필드는 원본 보존 범위에서 제외되고 이번 decoder/DPath 입력으로 소비하지 않는다.

최초 계획과 실행 result.json의 ‘실제 collector 수신시각 없음’ 문구는 부정확했다. 이후 다른 팀 검사가 원본 15,401개 CS의 radarInput 메타와 CAN 배치 일치를 직접 확인하고 원본 CS 헤더에서 원형 batch take가 15,401개를 받아들이는 결과를 보고했다. 이것은 **별도 실행의 근거**이며 이번 direct-adapter가 같은 경계를 실행했다는 뜻이 아니다. 보고된 최대 oldestCAN→receive 149.58ms의 16packet 묶음과 receive→CS 최대 18.40ms는, 100ms 검사가 가장 오래된 CAN의 나이가 아니라 receive 나이라는 차이를 보여준다. 물리 수집기 지연 보증이나 새 cutoff 구현 근거로 확대하지 않는다.

기존 결과의 `actual_gvc_assumed=0.0`도 이전 하네스에서 남은 설명 필드다. 실행 코드는 원본 CAN의 GVC를 기존 DBC로 읽었다. 이 문구를 원본 입력값 대체의 증거로 쓰지 않는다. 원본 결과를 덮지 않고 `frozen_results.json`의 정정 설명에 분리했다.

## 직접 검증과 보존

세 유효 로그의 각 12개 실행 불변식은 모두 통과했다. 로그 하나의 자료 부족은 건너뛰고 전체 성공으로 세지 않았다. 타임라인 잔여 항목 0, 체크한 센서 불일치 0, 정의된 C 기대값 불일치 0, 생성 메시지의 DBC 해독·정의된 체크섬 오류 0, MPC 비정상 status 0이었다. AST로 로드한 원형 호스트 3개 클래스의 19개 메서드 globals와 25개 상수를 별도 namespace 검사로 직접 대조해 누락·차이 0을 확인했다. 이 검사는 전체 하드웨어 모듈 import·GPU 실행이나 미실행 메서드까지 검증한 결과가 아니다.

완료한 각 실행에서 기록한 source 5개 지문을 실행 중 비교했고 현재 지문도 대조한다. native MPC 6개 파일과 안전 C 라이브러리는 이전 동결 빌드 지문과 비교한다. 현재 release의 변경 source 지문 대조는 **완료 후 현재 상태의 추가 검사**이며 실행 전에 모든 source 파일을 새로 지문 수집했다는 뜻이 아니다. 이번 폴더 밖 생산 source, 기존 결과, 빌드, 가상환경, 운영 설정은 바꾸지 않았다.

최초 준비 오류 3개는 기록 schema의 List에 schema 접근, capnp builder에 as_builder 호출, PubMaster 직렬화 bytes 처리에서 발생했다. 이 입출력 준비 오류는 로그로 보존했고 해당 경계만 수정한 후 네 입력의 직접 실행을 마쳤다. 실제 source 판정 조건을 대체해 통과시키지 않았다. 실행 stdout은 기본 공개 대상에 넣지 않으며 공개 근거는 익명 JSON·보고서·검증 도구로 제한한다. 원본 rlog, 객체 ID/좌표 CSV, 원본 절대 시각, GPS/개인정보/펌웨어 원문은 이번 폴더 결과에 저장하지 않는다.

재실행에는 이 폴더의 whole_io.py/whole_objects.py/whole_inputs.py/log_io.py/actual_stream.py/run_file.py 6개가 필요하다. 같은 workspace의 work 직하에 새 폴더로 복사하면 WORK가 새 경로가 되어 결과를 새 files/<익명명>/result.json에 작성한다. 원본 결과와 기존 빌드에는 쓰지 않는다. 읽기 의존성은 work/carrotpilot, work/input의 제공 로그·기록 schema, work/download_e2e의 offline-venv·native_sim/offline_io.py·build_unique와 safety_validation/verify_compiled.py·dbcs·libsafety_download_native.so다.

WSL에서 기존 offline-venv Python으로 새 폴더의 `run_file.py log_a`를 실행한다. 입력 이름은 log_a/log_b/log_c/log_d만 받는다. 실제 초기화·송신은 실행하지 않는다. 이 자료 전달 결과로 실물 ECU 호환성, firmware identity, PCS/AEB, 회생제동, ARS live 사용, 신호 Mode2 통합, 실제 차량 응답을 확정할 수 없다. 다음 수신 검증은 원본 radarInput을 같은 시각 공간으로 재배치한 별도 경로에서 RadarCanBatches를 실행해야 하며 이번 175회에 맞추기 위한 변경은 하지 않는다.
