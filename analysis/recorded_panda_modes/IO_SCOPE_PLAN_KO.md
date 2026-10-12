# 기록 Panda 모드와 실제 C 수신의 재생 계획

기존 ARS 호스트 시험은 처음부터 선언 Toyota param73과 init_tests의 mode counter2를 사용했다. 원본에는 초기 elm327 모드가 있고 그 구간에서 순정 송신이 기록됐다. 이 차이를 새 폴더에서 C 수신만 실행해 조사한다. 기존 결과·source·.so·운영 설정·출판 폴더는 바꾸지 않는다.

| 입력/판단 | 실행 방법 | 제외 범위 |
|---|---|---|
| 기록 schema | 제공한 schema로 원형 replay의 events 본문만 읽어 실행 | 펌웨어/serial/VIN/위치 필드 읽기·출력 없음 |
| 모드 | pandaStates 첫 항목의 safetyModel/param/alternativeExperience만 읽음. model/param이 달라질 때만 실제 set_safety_hooks 호출 | 반복 표본마다 reset 금지. 실물 전환 순간과 설치 펌웨어는 미확인 |
| 초기 상태 | 첫 기록 Panda 전에는 명시적 silent 모드0. 정상 set_safety_hooks가 만든 False 상태 | 초기 실제 Panda 모드라고 주장하지 않음 |
| CAN | 원본 CAN 전체 bytes/bus/address/저장순서를 실제 C RX에 공급 | 삭제·다른 bus로 이동·가짜 신호/패킷 추가 없음 |
| 관측 | 원본 CS 발행 헤더가 도착할 때 controlsAllowed/longAllowed/relay/RX-invalid 집계 | CS 신호로 권한을 만들거나 기록의 판정을 C에 강제하지 않음 |
| 시간 | 저장순서의 max-header를 메모리 수신 시각으로 사용. 원본 CS 헤더와 이 가정 시각 차이를 집계 | 물리 CAN collector/MCU timer와 같다는 보증 없음 |
| mode counter | board/main.c의 1Hz counter 증가와 safety_tick을 재현. 같은 .so의 공개 counter에는 매 1Hz 증가만 반영 | init_tests 호출 없음. controlsAllowed/relay setter 및 임의 counter 리셋 없음 |
| 위상 | 최초 전체 기록을 기준으로 1Hz 시작 1초/0.5초 두 가정을 별도 실행 | 기록으로 MCU 1Hz 위상을 알아냈다고 주장하지 않음 |
| 출력 | 익명 파일별 개수·모드·상대시각·유효성·차이 | raw CAN·원본 절대시각·좌표·펌웨어·객체 식별자 저장 없음 |

정상 set_safety_hooks는 원형 source 자체가 mode counter, relay 및 controls 상태를 초기화하는 정식 모드 변경이다. 이 동작과 사용자가 금지한 직접 setter·반복 reset 우회를 구분한다. C 시험 라이브러리의 init_tests는 counter=2로 시작해 전환 유예를 생략하므로 사용하지 않는다. 1Hz 입력은 하드웨어 드라이버의 시간 진행을 대신하는 명시적 입출력이며, 원형 safety_tick/generic_rx_checks 판단은 수정하지 않는다.

mode3(elm327)·mode2(Toyota)·param과 alternativeExperience는 기록값만 적용한다. 여러 Panda 항목이 있으면 단일 Panda 검증으로 확장하지 않고 실패/미지원 상태를 보존한다. 기록 이벤트 valid=False도 정상 전환으로 취급하지 않고 별도 집계한다. TX hook·CarController·MPC는 실행하지 않는다. 실제 CAN 소켓·Panda·차량·heartbeat·CI.init·UDS는 실행하지 않는다.

목표는 같은 원본 CAN에서 초기 고정 Toyota73과 기록 모드 정책이 다르게 relay를 판단할 수 있는지 확인하는 것이다. 신규 C 결과가 예전 생성 CAN 모두의 허용을 증명하거나 실물 릴레이 결함을 부정하는 결과라고 표현하지 않는다.

## 첫 실행 후 프로토콜 분류 정정

첫 실행은 can 목록의 모든 항목을 C RX로 넣어 6개 검사에서 실패했다. 원본 src128/130/192는 물리 bus가 아니라 returned/rejected 통지 offset이었다. 주 에이전트 승인으로 source panda.h의 0x80/0xc0 및 panda.cc/python unpack 규칙에 맞게 정정한다. 모든 항목을 소비하고 bytes/src를 변경하지 않으며, physical RX만 C RX에 넣고 통지는 별도 개수로 보존한다. 통지를 비트 제거 후 RX로 재주입하지 않는다. 각 분류의 합계와 원본 총항목을 대조하고 unknown source가 있으면 미지원으로 보고한다.

초기 실패 결과와 당시 실행 코드·SHA를 그대로 보존한다. 이전 ARS whole-host 시험도 통지 항목의 -1을 집계하지 않은 전체 RX 시도였으므로, 기존 동결 결과를 덮지 않고 새 보고서에서 수신 범위를 정정한다.
