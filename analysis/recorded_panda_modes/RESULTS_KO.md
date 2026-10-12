# 기록 Panda 모드 전환을 따른 C 수신 진단

기록된 초기 elm327→Toyota 전환과 원본 안전 파라미터를 실제 C에 적용하자, **기록 CS 15,401개에서 메모리 relay 감지 True는 0**이었다. 처음부터 Toyota73과 테스트 counter2를 사용했던 이전 호스트 시험의 영구 relay 거부는 원본 운용을 그대로 재현한 결과가 아니다. 초기 순정 CAN을 최종 제어 모드에 귀속시킨 시험 전제가 그 관측을 설명한다.

이 결론은 **현재 코드·메모리 C·명시한 재생 시각 가정**의 결과다. 실물 릴레이 고장 여부, 설치 Panda 펌웨어 일치, 실제 CAN 전달·차량 안전은 확정하지 않는다. 이전 ARS 호스트의 생성 CAN 26,302개가 새 설정에서 모두 허용된다는 검사도 실행하지 않았다.

## 직접 실행 결과

세 유효 로그를 1Hz 시작 위상 두 가지로 각각 실행해 **6실행·60검사 실패 0**을 확인했다. 두 위상에서 아래 집계가 같다. 자료가 없는 log_c는 C 수신 진단을 실행하지 않았다.

| 익명 입력 | 원본 can 목록 항목 | 물리 RX → C | 송신 반환 통지 | 거부 통지 | 기록 CS / C relay True | Panda 표본 / C와 기록 controls 차이 |
|---|---:|---:|---:|---:|---:|---:|
| log_a | 176,103 | 137,267 | 38,824 | 12 | 3,362 / 0 | 329 / 0 |
| log_b | 341,266 | 263,966 | 77,294 | 6 | 6,022 / 0 | 577 / 0 |
| log_d | 320,946 | 245,882 | 75,048 | 16 | 6,017 / 0 | 578 / 0 |
| 합계 | 838,315 | 647,115 | 191,166 | 34 | 15,401 / 0 | 1,484 / 0 |

각 분류 합계는 원본 총항목과 같다. unknown source 유형은 0이었다. 물리 RX 647,115개는 실제 C RX hook에서 모두 1을 반환했다. 반환·거부 통지는 원본 src와 bytes를 바꾸지 않았으며, 물리 RX로 재주입하지 않았다. 두 위상의 실행을 합치면 물리 C RX 호출은 1,294,230회이며 고유 원본 프레임 수가 두 배라는 뜻은 아니다.

CS 및 Panda 관측에서 C controlsAllowed/longitudinalAllowed/relay/RX-invalid True는 모두 0이었다. 기록된 Panda controlsAllowed 및 safetyRxChecksInvalid도 모두 False이며 그 두 값과 C의 관측 차이는 0이었다. source 전체 메시지의 신호 의미나 모든 물리 ECU 건강을 입증하는 결과는 아니다. 알 수 없는 CAN은 현재 모드의 원형 RX 판단에 따라 처리된다.

## 기록 모드와 이전 시험의 차이

| 입력 | 초기 관측 설정 | Toyota 관측 설정 | 반복 Panda 표본을 reset하지 않은 수 | Toyota 모드에서 기록된 bus0 순정 명령 |
|---|---|---|---:|---|
| log_a | elm327 model3/param1/alt1 | Toyota model2/param73/alt1 | 327 | 0x2e4·0x343 없음 |
| log_b | elm327 model3/param1/alt0 | Toyota model2/param585/alt1 | 575 | 0x343 1,800개, 0x2e4 없음 |
| log_d | elm327 model3/param1/alt1 | Toyota model2/param73/alt1 | 576 | 0x2e4·0x343 없음 |

첫 Panda 관측 전은 실제 초기 모드를 알 수 없으므로 명시적인 silent 모드0을 사용했다. 각 실행의 set_safety_hooks는 이 초기 1회와 기록 설정 변경 2회뿐이었다. 반복 관측마다 relay나 권한을 초기화하지 않았다. 기록 model/param이 달라질 때 원형 set_safety_hooks를 호출했으며 이 함수가 원형대로 counter·relay·controls·RX 상태를 초기화했다. 이러한 정식 모드 변경과 강제 relay setter 우회를 구분한다. controlsAllowed/relay setter, init_tests, 임의 counter reset은 모두 호출하지 않았다.

현재 Toyota source에서 param의 512 비트는 STOCK_LONGITUDINAL이다. 그래서 log_b의 585는 순정 0x343을 relay 위반으로 판정하지 않는다. 저장 헤더만 기준으로 최초 Toyota 관측 이후 0x343은 1,801개였지만 저장순서의 최신 Panda 모드를 적용한 이번 실행에서는 1,800개였다. 한 항목의 서비스 간 순서 차이를 숨기지 않는다. 실물 모드 전환 순간을 첫 Panda 발행 헤더로 확정한 것은 아니다.

이전 호스트 C 시험은 세 파일 모두 선언 factory Toyota73을 처음부터 적용했다. init_tests는 safety_mode_cnt=2로 시작해 원형의 초기 전환 유예를 생략했다. 그 조건에서 startup 순정 0x2e4/0x343은 relay 감지를 만들 수 있다. 새 진단은 같은 순정 프레임을 지우지 않고 당시 관측 elm327 또는 초기 silent에서 처리하고 정상 모드 전환을 따라갔다. C source에 허용 조건을 새로 넣거나 안전 한계를 바꾸지 않았다.

## 원본 can 목록에는 수신 이외의 통지도 있다

첫 실행은 모든 can 목록 항목을 RX로 넣어 42검사 중 6개가 실패했다. -1 반환은 log_a 38,836개, log_b 77,300개, log_d 75,064개였다. 직접 src/길이를 집계한 결과 전부 src128/130 또는 src192였다. C packet helper의 bus≤7 조건에 맞지 않는 통지 항목을 물리 bus로 전달한 하네스 분류 오류였다.

원형 `openpilot/selfdrive/pandad/panda.h` 23~24행은 거부 offset0xc0와 반환 offset0x80을 정의한다. `panda.cc` 280~285행은 rejected/returned 표시를 기록 src에 더하고, `panda/python/__init__.py` 70~74행도 같은 규칙으로 해석한다. firmware의 can 목록에는 송신 반환·거부 통지가 함께 전달될 수 있으므로 이를 bus128/192에서 새로 수신한 CAN이라고 해석하면 안 된다.

주 에이전트 승인 후 이 범주만 정정했다. 모든 기록 항목의 bytes/src/순서와 수량을 보존했으며 genuine RX만 C RX에 공급하고 통지는 별도 집계했다. 통지 src의 offset을 제거해 물리 RX처럼 만들지 않았다. 원본 송신 통지를 TX hook에 재실행하지도 않았다. 최초 실패 JSON과 당시 코드 사본·지문을 별도로 보존했다. 최초 코드 SHA는 `d5d8315bab68d3d07308d99b5c8a6606ba977e20916fccc25f495cdd576064c3`이다.

이전 ARS whole-host 실행도 모든 목록 항목을 RX에 넣었지만 이러한 -1 통지를 집계하지 않았다. 그 기존 동결 결과는 그대로 보존한다. 당시 물리 RX는 공급됐지만 통지 항목까지 실제 C RX로 정상 처리됐다는 해석은 정정해야 한다. 이 분류 문제와 처음부터 최종 Toyota73을 적용한 모드 전제 문제는 다르다. 통지의 -1 자체가 이전 relay True를 만든 원인으로 단정하지 않는다.

## 시간과 재생 경계

원본 저장순서를 유지하며 지금까지 본 최대 top-level 헤더를 메모리 수신 시각으로 사용했다. C 타이머는 최초 관측 이벤트를 기준으로 마이크로초를 진행한다. 원본 절대 시각은 결과에 저장하지 않았다. CAN bytes/주소/src를 정렬하거나 이동하지 않았다. 원본 CS 헤더가 도착한 순서에서 C 상태를 관측하고, CS 헤더와 가정 수신 시각 차이는 별도로 기록했다. 이 차이 최대는 log_a 96.154ms/log_b 187.103ms/log_d 100.704ms였다. 모든 CS에서 C clock을 원본 헤더와 같게 만들었다고 주장하지 않는다.

현재 `panda/board/main.c`는 8Hz 드라이버 tick 중 1Hz마다 safety_mode_cnt를 증가시키고 safety_tick을 호출한다. 기존 .so의 공개 counter에 동일한 외부 1Hz 증가만 반영했으며 counter를 임의로 0 또는 2로 쓰지 않았다. 기록 전환의 원형 set_safety_hooks가 만든 counter0은 유지한다. 1Hz 첫 실행을 상대 1초 또는 0.5초로 놓은 두 위상을 분리했다. 둘은 알려지지 않은 MCU 위상의 시험 가정이며 MCU 실제 clock·부팅 시각·heartbeat 경로 검증이 아니다.

원형의 relay 검사는 mode counter가 1을 넘을 때 stock 명령을 확인한다. 이번 실행은 유예를 제거하거나 무한히 연장하지 않았다. 반복 Panda 표본을 reset하지 않아 Toyota 전환 이후에도 counter가 계속 증가했다. 두 위상에서 조건부 relay 0이라는 결과를 실차 안전 통과로 확대하지 않는다.

## 실행·지문·인계

`run.py`는 원형 replay의 events 함수 본문만 로드해 기록 schema로 읽는다. Params/CI/CarController/MPC를 생성하지 않으며 운영 설정에 접근하지 않는다. mode/param/alt/controls/RX-invalid/fault 개수와 제한한 CS 상태만 읽었다. VIN/serial/펌웨어 문자열/위치/객체 ID/CAN 원문은 출력하지 않는다. 실제 CAN 소켓, 차량 TX, 실제 Panda 설정 변경, CI.init/UDS는 0이었다.

검사 항목은 모든 can 이벤트·항목 소비, 분류 합계, unknown 0, C mode/param 일치, 정상 모드 초기화 counter, 물리 RX hook 반환, 기록 CS 표본 수, reset 호출 수, 1Hz counter와 safety_tick 호출 수다. 6실행에서 모두 직접 통과했다. source 8개와 C 라이브러리 지문은 실행 전후 같았으며 기존 폴더와 생산 source는 바꾸지 않았다.

재실행은 기존 WSL offline-venv Python으로 새 work 직하 폴더에 복사한 `run.py`를 실행한다. read 의존성은 제공 로그와 schema, source의 replay events 본문, `work/download_e2e/work/safety_validation/verify_compiled.py`와 기존 libsafety_download_native.so다. 결과는 도구 폴더에만 작성된다. source/source schema/라이브러리가 같아야 같은 비교 범위를 주장할 수 있다. 모드와 clock을 따른 새 **C-only** 자료를 이전 whole-host/생성 CAN 결과와 섞어 활성 제어·ARS live·PCS/AEB·회생 보증으로 보고하지 않는다.

대표 입력만 독립 실행할 때는 새 work 직하 폴더에 `run.py`와 `single_case.py` 두 파일을 복사하고 기존 Python으로 `single_case.py --alias log_b --phase-us 0`을 실행한다. WORK는 도구 파일의 부모이며 ROOT=WORK.parent.parent라 같은 workspace의 work 직하에서 재배치할 수 있다. 단일 결과는 복사한 폴더의 `single_case_results.json`에만 저장한다. 전체 6실행의 results.json은 덮지 않는다.
