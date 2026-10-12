# 원본 배치·CP·Panda 정책을 연결한 호스트 관측

실제 제공 CAN과 정확한 CS.radarInput 배치로 **367점·CRC 정상 2,399레코드**를 처리했고, 실제 DPath가 선택한 **175회의 레이더 선행차 입력을 native MPC까지 전달**했다. 원본 CP/제어 OFF/운전자/valid/오류를 유지하며 원형 호스트와 Toyota CAN 생성 및 같은 C 상태의 RX/TX를 연결했다. 가짜 객체·factory CP·새 제어 권한을 넣지 않았다.

이것은 오프라인 자료 연결 결과다. 실제 CI.update·CI.init·소켓·Panda/차량 TX는 실행하지 않았다. 신호 Mode2·ARS live·실물 firmware·PCS/AEB·회생·차량 운동 응답은 이번 결과로 확정하지 않는다. 원본 시각 숫자를 공통 축으로 쓰는 재생 가정과 BOOTTIME/MONOTONIC의 실물 동등성도 구분한다.

| 입력 | 점 / 레코드 | batch 거절 | DPath 모델 / 오류모델 | MPC 모델 / 레이더 선행 입력 | 원본 CP |
|---|---:|---|---:|---:|---|
| log_a | 246 / 479 | 없음 | 623 / 45 | 623 / 175 | directLong=True, param73 |
| log_b | 115 / 990 | staleEgoState25 | 1,019 / 1 | 986 / 0 | directLong=False, stock param585 |
| log_c | 자료 부족 | 미실행 | 미실행 | 미실행 | 원본 CP 없음 |
| log_d | 6 / 930 | staleEgoState1 | 1,150 / 27 | 1,150 / 0 | directLong=True, param73 |
| 합계 | 367 / 2,399 | 26개 | 2,792 / 73 | 2,759 / 175 | 원본별 정책 유지 |

세 유효 입력의 각 18검사, 총 54검사를 직접 통과했다. 점 수는 객체 수가 아니라 발행한 점의 누계다. 기존 direct-adapter 369점/2,433레코드에 맞추지 않았고 정확한 batch subset과 stale 거절을 따른 결과는 동결 quality의 storage_max 367/2,399와 같다. DPath/MPC 수치는 새 연결에서 직접 관측했다. log_b의 모델 33개는 가정 100Hz 수신에서 합쳐졌으며 모두 MPC에 따로 처리됐다고 말하지 않는다. 전체 MPC의 영상·레이더 혼합 lead source 선택과 175회 ARS 입력도 구분한다.

## 원본과 입출력 대체

원본 최초 CP를 현재 cereal로 wire 변환한 별도 복사본을 호스트에 주입했다. factory get_params를 호출하지 않았다. decoder/DPath CP와 Card CP도 분리했다. 생성자 전후 검사한 19개 제어·차량 필드, safetyConfigs, FW 개수의 차이는 0이었다. 이것은 모든 schema ordinal 및 firmware identity 검증이 아니다. 부모의 별도 CP wire 핵심16필드/5표본 검사는 읽은 참고이며 이 실행으로 합산하지 않는다.

모든 원본 header·camera/model EOF·pose timestamp·nested radarInput NS는 epoch를 유지했다. 별도 wire 시간 검사를 직접 실행해 30,215개의 주요 서비스 header와 해당 camera/model/pose NS·CS nested 필드에서 차이 0을 확인했다. 원본 절대 값은 저장하지 않았다. native CAN/camera의 BOOTTIME와 Python Card의 MONOTONIC가 실제 장치에서도 같은 기원이라는 증명은 아니다. 기존 기록 liveTracks 헤더를 새 ARS 발행 시각으로 쓰지 않았다.

CAN/CS batch는 MemorySocket의 최신 메시지 병합과 분리한 순서 보존 목록에서 처리했다. 원형 RadarCanBatches.take와 offline=True 어댑터에 **그 배치 CS의 ego/receive 및 원래 packet 헤더**를 전달했다. 생산 radarcan의 소켓/main 전체 루프·전체 inputTimeout·wall 처리 deadline은 실행하지 않았다. DPath는 독립 진단 mode1만 쓰고 원본 radarUnavailable=True 및 운영 설정을 유지했다.

원형 Card.state_update/VCruiseCarrot/step, SelfdriveD/StateMachine/Controls, CarrotPlanner/LongitudinalPlanner와 native C/Cython MPC를 실행했다. 실제 CI.update 반환만 원본 CS 복사본으로 대체했고 실제 CI.apply/Toyota 제어기/CANPacker를 실행했다. 원형 Card가 복사본의 radarInput/UI를 바꾸는 15,407틱을 기록했으며 **batch용 원본 변형은 0**이었다. Card가 새로 만든 메타를 원본 레이더 배치로 재사용하지 않았다. 원본 CS의 header/valid는 새 표본에만 배달하고 반복 복사본 배달은 억제했다. 그 수신과 표본 유지·병합은 명시적 재생 입출력이다.

체크한 15개 센서 필드와 PCM available/enabled/speed/speedCluster 불일치는 0이었다. 원본 OFF·문/벨트/기어/페달·서비스 valid를 정상 True로 바꾸지 않았다. 메모리 Params는 SpeedFromPCM0/LongActuatorDelay20/AlphaTrue/NNFF0이며 실제 운영값을 읽거나 수정한 결과가 아니다. 원본 CP의 direct/stock 값을 바꾸는 근거로 사용하지 않았고 SignalAssistMode는 기본0이다.

GVC/PCM 상태·차간거리/HUD는 기존 DBC로 실제 CAN을 해독했다. stock log_b는 원형 ACC_CONTROL의 ACC_TYPE도 해독했고 미수신 집계 0이었다. DISABLE_RADAR 플래그가 있는 a/d는 원형 CarState 경로처럼 ACC_TYPE의 생성자 기본1을 유지하고 각각 3,365/6,020틱을 별도 기본값 범위로 집계했다. 이 기본값을 센서 관측으로 보고하지 않는다. 전체 Toyota CI.update를 검증한 것은 아니다.

## 오류와 원본 OFF

| 오류 관측 | log_a | log_b | log_d |
|---|---:|---:|---:|
| 첫 완성 레코드 전 오류 발행 | 468 | 1 | 396 |
| 첫 완성 레코드 이후 오류 발행 | 9 | 55 | 9 |
| batch 오류 발행 / 제한 | 0 / 0 | 8 / 17 | 1 / 0 |

batch 오류를 liveTracks.canError로 전달하고 정상 batch 회복 앞에서 어댑터를 재생성했다. 초기 no-record와 처리 이후 오류를 구분했고 DPath.radarErrors를 유지했다. source의 50ms 오류 발행 제한도 분리했다. 오류 플래그는 겹칠 수 있어 단순 합계로 객체 수나 유실 수를 만들지 않는다. 원형 SubMaster의 valid/alive/frequency 부족 및 SelfdriveD 이벤트는 각 first 결과에 집계했다. 누락·차단을 삭제해 초기화나 활성화를 만들지 않았다.

총 호스트 15,407틱에서 enabled/active/longActive와 C controlsAllowed/longAllowed/relay/RX-invalid True는 모두 0이었다. 정상 소프트웨어 초기화가 성립해도 물리 CI.init은 sink였으며 실제 차량 준비를 증명하지 않는다. 사용자 설정의 모든 기능·실제 운행 활성화를 시험한 결과도 아니다.

## 단일 C 상태와 TX 검사 범위

기록 정책의 RX와 실제 생성 CAN TX는 **같은 단일 C 상태**를 사용했다. 모드/param 변경만 원형 set_safety_hooks로 적용했다. 반복 Panda 표본·ControlsReady에 C reset을 연결하지 않았고 init_tests·권한/relay setter를 호출하지 않았다. 1Hz counter 증가와 phase0은 외부 MCU 시간 진행의 명시적 가정이다. 물리 MCU heartbeat·설치 코드·relay 동작은 미검증이다.

기록 can 목록 838,315개는 physical RX 647,115·반환191,166·거부통지34로 전부 소비했고 unknown0이었다. 모든 physical RX가 실제 C hook에서 1을 반환했다. 통지 bytes/src는 수정하거나 RX로 재주입하지 않았다. 메시지 수신 허용은 모든 ECU 신호 의미·건강·실물 호환성을 입증하는 결과가 아니다.

| 입력 | 생성 CAN | 실제 C 허용 / 거부 | 독립 기대값 정의 / 미정 |
|---|---:|---:|---:|
| log_a | 5,624 | 5,488 / 136 | 1,081 / 4,543 |
| log_b | 7,781 | 7,781 / 0 | 0 / 7,781 |
| log_d | 10,921 | 10,643 / 278 | 2,110 / 8,811 |
| 합계 | 24,326 | 23,912 / 414 | 3,191 / 21,135 |

기대값은 silent·elm327 진단주소/8byte 규칙 및 Toyota의 0x343 direct/stock 정책과 relay 전제에 한정했다. 정의한 3,191개의 불일치는 0이었다. **미정 21,135개를 독립 정책 검증 통과로 세지 않는다.** 특히 b의 기대값 정의는 0개다. 실제 C 반환, TX 전후 권한 불변, 생성 DBC 해독과 정의된 체크섬 오류 0을 서로 다른 근거로 보고한다.

log_b에서는 LKA/LTA/HUD만 생성됐고 ACC는 생성되지 않았다. a/d의 비영 ACC 요청도 0이었다. 허용 23,912개가 종방향 권한 획득이나 차량 송신을 뜻하지 않는다. LKA/LTA request/torque의 비작동 값을 당시 별도로 집계하지 않았으므로 그 불변식 통과 또는 전체 steering 정책 독립 검증을 주장하지 않는다. source의 비활성 분기 읽기와 실제 관측 수치를 구분한다. 진단/HUD의 C 허용도 물리 UDS 초기화나 PCS/AEB 효능·보존 증거가 아니다.

## 코드 버전·추가 관측·독립 재실행

최초 log_*_first 결과는 그대로 보존했다. 이 final_observation은 **그 완료 결과를 읽은 별도 최종 정리**이며 새 전체 실행으로 세지 않는다. 준비/실행 exception은 네 입력 모두 없었고 c는 자료 부족으로 유지했다. 상태의 레이더 오류·stale 거절은 준비 실패와 구분한다.

a 최초 runner SHA는 `8242edc7f4a1c5e8f17204b2a073c48731e699e83eb039fe335b2d5c822d5800`다. 그 뒤 source12 전후 지문과 하위 프로세스 stderr 보호만 추가했고 계산 경로는 바꾸지 않았다. 초기 코드를 되돌린 사본이 당시 SHA와 정확히 일치함을 직접 확인해 보존했다. 현재 runner는 `8c76d85216784f569816d662cc226c6426a6a032f6e5e32de6a554b48735ec06`이다. 최초 a는 AST source5와 C 라이브러리를 실행 중 대조했고 넓은 source12 지문은 b/d부터 있다. 이전 검사 범위를 소급해 넓히지 않는다.

부모는 현재 여섯 helper를 지문 동일 복사한 별도 폴더에서 a/b를 각각 직접 재실행했다. 두 case에서 34개 의미 결과군 차이0, 각18검사 통과, source12와 C 라이브러리 불변을 확인했다. 이것은 **부모의 별도 실행**이며 이 에이전트의 54검사와 합쳐 새 전체 실행 수를 만들지 않는다. 출처는 work/paired_host_policy_root/comparison.json이다. 새 namespace 검사도 직접 실행해 원형3클래스/19메서드 globals·25상수의 누락/차이0을 확인했다.

stdout/stderr의 원본 코어 출력은 폐기하며 익명 요약만 반환한다. 첫 a에서는 하위 Git의 source 파일명 CRLF 경고가 보였고, 이후 OS stderr 보호도 추가했다. 원본 rlog/CAN 원문·생성 payload·객체 ID/좌표·원본 절대시각·VIN/펌웨어 문자열은 결과에 저장하지 않았다. source·기존 결과·공유 라이브러리·운영 설정·outputs/release는 변경하지 않았다.

대표 재실행은 run.py/whole_io.py/whole_objects.py/log_io.py/paired_stream.py/policy_io.py 여섯 파일을 새 work 직하 폴더에 복사한다. 기존 offline-venv Python으로 `run.py --alias log_a --clock-basis storage_max --phase-us 0 --output-dir 새폴더/log_a_independent`를 실행한다. 결과가 이미 있는 폴더는 쓰지 않는다. ROOT=WORK.parent.parent라 같은 workspace의 work 직하에서 재배치할 수 있다. 추가 read 의존성은 기록 schema·rlog, 현재 carrotpilot source, 동결 recorded_panda_mode_replay/run.py, download_e2e의 offline_io/기존 native build·verify_compiled.py·DBC·C 라이브러리다.

현재 통합 실행은 storage_max/phase0만 완료했다. input_max·다른 위상·실제 wall 지연·전체 radarcan 루프·정책 미정 TX의 독립 oracle·실물 차량을 검사했다고 말하지 않는다. 완료한 범위는 실제 batch 자료와 원본 CP·기록 정책을 원형의 비활성 호스트 및 메모리 CAN/C까지 연결한 관측이다.
