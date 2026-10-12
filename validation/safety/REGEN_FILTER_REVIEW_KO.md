# RAV4 Hybrid 회생제동·OneClone Radar ACC Filter 검토

2026-10-12. 읽기 전용 조사이며 Toyota 차량 코드·CAN 송신·설정·펌웨어·제품 구매·차량 연결은 변경하지 않았다.

## 결론

RAV4 Hybrid의 순정 회생제동 기능과 **CarrotPilot의 가감속 요청에서 실제 회생제동이 얼마나 사용되는지**는 별도 문제다. Toyota의 공식 설명은 RAV4 Hybrid가 제동 에너지를 배터리에 회수하는 HEV임을 확인한다. 그러나 현재 코드·첨부 로그·OneClone 판매 설명만으로 이번 한국 출고 차량에서 회생이 정상 적용된다거나, 필터 장착으로 회생이 복구된다고 확정할 수 없다. [Toyota Canada 공식 설명](https://www.toyota.ca/en/connect/2022/hybrid-electric-batteries/)

OneClone 제품은 일부 2022 RAV4 등의 레이더 ACC 충돌을 해결하기 위한 CAN 필터로 소개된다. 판매 페이지는 0x343 종방향 신호의 경로와 지원 차종 일부를 설명하지만 **회생제동, 한국형 ECU/펌웨어 호환표, 프레임 명세, PCS/AEB 보존 보증**은 제공하지 않는다. 이 제품을 회생제동 활성화 장치로 판단할 근거는 없다. [OneClone Toyota Radar ACC Filter](https://oneclone.net/product/toyota-radar-acc-filter/)

## 확인한 실제 Toyota 구현

기준은 CarrotPilot `carrot-wip`의 `0e4ee1bdbef3ad7284b136fddf31592e3f8a785f`이며, 이번 안전 복원 패치는 아래 Toyota 차량 코드를 수정하지 않았다.

| 항목 | 실제 코드 | 판단 |
|---|---|---|
| `HYBRID` | `toyota/interface.py:53–57`은 펌웨어 조회 목록의 hybrid ECU 존재로 설정하고 `:149–151`은 종방향 액추에이터 지연을 0.05초로 선택한다 | 회생 요청 플래그가 아니다. 첨부 `carFw`가 비어 있고 CP flags 1368/1372에는 HYBRID 비트 1이 없다. 실제 CP의 지연은 약 0.15초였다. 하이브리드 차량이라는 사실과 소프트웨어의 응답 지연 선택을 별도로 점검해야 한다. 회생 실패 원인으로 확정하지 않았고 플래그를 강제로 설정하지 않았다. |
| `ACC_TYPE` | `toyota/carstate.py:50` 초기값은 1, `:153–154`는 레이더를 비활성화하지 않은 TSS2에서 순정 ACC_CONTROL 값을 읽는다. `:157–164`는 저속 잠금 관련 조건을 설명한다 | 전용 회생 모드 신호라는 근거가 없다. 임의로 값을 바꾸면 안 된다. |
| `PERMIT_BRAKING` | `toyota/carcontroller.py:207–245`는 경사와 가속 요청·정지 상태에 따라 제동 허용을 결정한다. `toyotacan.py:43–56`은 ACCEL_CMD/ACC_TYPE/PERMIT_BRAKING 등을 일반 ACC_CONTROL 메시지로 만든다 | 회생과 마찰 제동의 분담 명령이 아니다. 회생을 늘리려고 이 값을 고정하거나 제동을 막으면 안 된다. |
| 레이더 비활성화 | `toyota/interface.py:156–160`의 UDS 통신 제어와 `carcontroller.py:288–290`의 유지 메시지 | 레이더 출력 경로와 관련된다. 이를 제거하거나 새로운 필터 플래그를 추가하지 않았다. |
| 필터 자동 인식 | 현재 Toyota CarInterface/flags에는 OneClone 전용 인식·펌웨어 검증·회생 분담 경로가 없다 | 제품 장착을 가정해 CP 플래그를 바꾸는 구현을 만들 수 없다. |

근거: [하이브리드·UDS 조건](https://github.com/ajouatom/openpilot/blob/0e4ee1bdbef3ad7284b136fddf31592e3f8a785f/opendbc_repo/opendbc/car/toyota/interface.py), [ACC_TYPE 수신](https://github.com/ajouatom/openpilot/blob/0e4ee1bdbef3ad7284b136fddf31592e3f8a785f/opendbc_repo/opendbc/car/toyota/carstate.py#L153), [제동 허용 계산](https://github.com/ajouatom/openpilot/blob/0e4ee1bdbef3ad7284b136fddf31592e3f8a785f/opendbc_repo/opendbc/car/toyota/carcontroller.py#L207), [일반 가속도 팩커](https://github.com/ajouatom/openpilot/blob/0e4ee1bdbef3ad7284b136fddf31592e3f8a785f/opendbc_repo/opendbc/car/toyota/toyotacan.py#L43).

## 필터와 PCS/AEB: 근거와 한계

ARS510 작성자의 자체 기록은 레이더의 차량 쪽 메시지 9개를 끊는 UDS 방식과, 레이더의 0x343만 차단하는 smartDSU 계열 필터 방식을 비교한다. 기록된 필터 구성에서는 원래 PCS 메시지가 차량 쪽으로 전달되고, UDS 구성에서는 0x283/0x344 등 레이더의 차량 쪽 출력이 끊겼다고 설명한다. 버스 1 객체 데이터가 계속 수신돼도 차량 쪽 PCS 작동을 증명하지 못한다. 이 결과는 작성자의 특정 차량·펌웨어 기록이며 OneClone의 모든 제품이나 이번 한국 차량의 보증이 아니다. [ARS510 버스 비교](https://github.com/ds-sebastian/ars510-radar/blob/673eb8e609e303feff2c15dd250592c383962156/docs/13_car_bus_messages.md#openpilot-longitudinal-filter-or-disable), [작성자의 AEB/PCS 조사](https://github.com/ds-sebastian/ars510-radar/blob/673eb8e609e303feff2c15dd250592c383962156/docs/15_aeb_pcs.md)

이 자료에는 UDS/필터가 이번 차량의 회생 분담을 바꾸거나 복구한다는 검증이 없다. **레이더 통신 비활성화가 회생제동 실패 원인이라는 주장은 현재 미검증**이다. 단순 PCS 경고 유무, 레이더 객체 수, 하이브리드 표시, 배터리 SOC 상승만으로 회생 분담을 확정하지 않는다.

## 가능한 수신 진단과 부족한 자료

기록 당시 전체 스키마로 실제 rlog의 CarParams만 수신 분석한 결과는 다음과 같다. 원본 데이터는 메모리에서 읽었고 공개용 값만 `hybrid_response_delay_observed.json`에 기록했다.

| 로그 | CP flags | HYBRID 비트 | carFw 항목 | 실제 longitudinalActuatorDelay |
|---|---:|---|---:|---:|
| rlog.zst | 1372 | 없음 | 0 | 약 0.15초 |
| rlog_06.zst | 1368, 두 CP 동일 | 없음 | 0 | 약 0.15초 |
| rlog_11.zst | CP 없음 | 자료 없음 | 자료 없음 | 자료 없음 |
| rlog_12.zst | 1372, 두 CP 동일 | 없음 | 0 | 약 0.15초 |

0.15초는 기록된 제어 응답 모델의 값이며 실제 모터의 응답 지연을 새로 측정한 값이 아니다. 하이브리드 전용 0.05초 선택이 이루어지지 않은 사실을 회생제동이 꺼졌다는 뜻으로 바꾸면 안 된다. 차량·ECU 식별을 보강하고 현재 장치 CP와 물리 응답을 비교할 후속 점검 항목이다.

기존 Toyota DBC에는 아래 수신 신호가 있다. 이를 읽을 수 있다는 것과 회생 기여도를 측정했다는 것은 다르다. [고정 DBC 정의](https://github.com/ajouatom/openpilot/blob/0e4ee1bdbef3ad7284b136fddf31592e3f8a785f/opendbc_repo/opendbc/dbc/generator/toyota/_toyota_2017.dbc)

| 버스 0 후보 | 기존 정의 | 한계 |
|---|---|---|
| 0x127 `GEAR_PACKET_HYBRID.FDRVREAL` | 부호 있는 11비트, 25N/코드. DBC 주석은 엔진·모터의 바퀴 구동력이며 크리프·회생·엔진 제동을 포함한다고 설명한다 | 음수만으로 순수 회생 토크를 분리할 수 없다. |
| 0x0A6 `BRAKE.BRAKE_FORCE` | 8비트, 40N/코드. DBC 주석은 하이브리드의 마찰 제동력이라고 설명한다 | 이번 ECU의 실제 물리값·정확도는 추가 대조가 필요하다. |
| 0x2FF `SDSU` | 커뮤니티 DBC에는 FD_BUTTON/STATE가 정의돼 있다 | 현재 DBC는 8바이트, ARS510의 특정 필터 기록은 4바이트다. 주소 하나만으로 OneClone 모델·상태를 검증할 수 없다. |

기존 분석의 전체 주소 통계에서 0x127은 세 주 로그에 각각 2,124/3,761/3,761회, 0x0A6은 2,919/5,136/5,134회 보인다. 0x2FF는 관찰되지 않았다. 필터 heartbeat 부재만으로 제품 미장착도 확정하지 않는다. 최초 주소 통계와 별도로 아래 수신 probe를 실행했다.

### 이번 후속 수신 probe 결과

주 검증 에이전트가 `tools/ars510_validation/regen_probe.py`로 네 실제 로그를 읽었고, `work/validation_run/regen_force_probe.json`의 익명 결과를 이 검토에서 다시 확인했다. 기존 DBC와 독립 비트 추출을 대조한 0x127 표본 **9,646개**, 0x0A6 표본 **13,189개**에서 디코딩 불일치가 없었다. 0x127의 정의된 Toyota 체크섬 오류도 없었다. 0x0A6에는 현재 DBC의 체크섬 정의가 없어 별도 체크섬 통과로 표현하지 않는다.

| 로그 | 0x127 해석값 | 0x0A6의 raw=255 | 실제 CC 활성 상태 |
|---|---|---:|---|
| rlog.zst | 0~1,200N, 음수 표본 없음 | 219개 | 3,354표본 모두 enabled/longActive=False |
| rlog_06.zst | -400~3,525N, 음수 1,045개 | 0개 | 5,997표본 모두 enabled/longActive=False |
| rlog_11.zst | 대상 CAN/CC 자료 없음 | 자료 없음 | 자료 없음 |
| rlog_12.zst | 0~1,200N, 음수 표본 없음 | 556개 | 6,007표본 모두 enabled/longActive=False |

표의 힘은 **DBC 공식으로 환산한 관측값**이며 ECU 물리 교정값을 확인한 결과가 아니다. 특히 0x0A6의 raw=255는 포화·무효·기타 의미가 미확정이므로 10,200N의 실제 마찰 제동력이 발생했다고 확정하지 않는다. rlog_06의 음수 구동력도 엔진 제동과 회생이 섞일 수 있어 순수 회생 토크나 회수 에너지를 확정할 수 없다. 총 15,358 CC 표본이 비활성이었으므로 **활성 CarrotPilot 회생 실패/성공 시험이 아니다**. 관측 가능한 기존 수신 신호를 확인했으며 `pure_regenerative_braking`와 `energy_recovery_Wh`는 계속 미확인이다.

다음 자료가 있어야 수신 분석과 호환 설계를 구체화할 수 있다.

1. 한국형 차량의 레이더·Hybrid/브레이크 ECU 식별과 펌웨어, 현재 경고·고장 상태. VIN이나 장치 식별자는 공개 자료에서 제외한다.
2. OneClone의 정확한 하드웨어·펌웨어 버전, 회로/배선, 차단·수정·전달 프레임 명세, 전원/통신 실패 때의 동작, 한국형 2022 Hybrid 호환 근거 및 PCS/AEB 유지 자료.
3. 같은 시각의 ACCEL_CMD/ACC_TYPE/PERMIT_BRAKING, 원래/필터 뒤 0x343, 원래 0x283/0x344/0x411, CAN 유효성, CC 활성 상태, 실제 감속도와 운전자 조작 기록.
4. 공식 정의·단위가 확인된 HV 배터리 전류/전압/SOC/온도, 모터 발전 토크·회전수, 마찰 제동력 자료. 신호 주소나 진단 명령을 추측해 만들지 않는다.

초기 분석은 이미 저장된 로그의 기존 신호를 읽고 메시지 신선도·중복 0x343·PCS 전달 여부·제동력 관측 가능성을 비교하는 수신 전용 진단으로 제한한다. 전기 에너지 회수와 엔진 제동·마찰 제동을 분리할 근거가 없으면 결과는 `미확인`으로 남긴다. 기본 lab-only 자동 재생은 이 제한과 양립한다.

`regenAvailable=True`, 새로운 필터 탐지 플래그, 미검증 CAN/DID/비트 배치, UDS 제거, PCS/AEB 비활성화, 순정 경고 숨김, Panda 제한 우회, 실차 송신 또는 구매·배포를 이 문서만으로 구현하거나 실행하면 안 된다. 제품 사양 검증과 물리 제동 검증을 마친 뒤 별도 검토할 부분이다.

공식 Toyota 2022 Quick Reference Guide의 검색 발췌도 확인했으나 PDF 직접 열기는 403으로 실패했다. 이 보고서의 기본 회생 설명에는 직접 읽은 Toyota Canada 공식 페이지를 사용했고, 외부 포럼의 회생 주장·제3자 수리 매뉴얼의 미확인 진단 항목을 구현 근거로 사용하지 않았다.
