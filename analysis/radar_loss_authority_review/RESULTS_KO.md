# 레이더 누락·오류와 감속 권한의 원형 실패 관측

원형 합성 ON 검사에서 **softDisabling의 감속 목표가 MPC에서 소실되는 경로를 직접 재현**했다. `forceDecel=True`가 발행돼 계획기는 v_cruise=0을 전달했지만, ACC 모드 MPC가 이를 `carrot.v_cruise=21.3889m/s(77km/h)`로 덮었다. 3초 soft 구간에 제어 가속과 생성 0x343이 양수로 남았고, 정상 PCM RX를 계속 받는 메모리 C는 그 요청을 허용했다.

이 결과는 **고정 ego15m/s·건강한 합성 빈 lead·정상 PCM ON**의 원형 코드 계약 검사다. 실제 레이더 객체나 앞차·차량 운동을 만들지 않았고 실제 차량 결함/충돌/제동거리/PCS/회생을 검증한 결과가 아니다. 원본 RAV4 로그는 제어 OFF였으므로 두 전제를 혼합하지 않는다.

## 읽기 경로와 조건

| 단계 | 실행 당시 원형 판단 | 근거 |
|---|---|---|
| 레이더 runtime 선택 | Toyota는 CP.radarUnavailable=True이면 설정값과 무관하게 mode-2 | radar/__init__.py:4–12, radard_dpath.py:91–94 |
| R9 ARS 진단 | 독립 mode1 수신기로 실제 batch를 해독. CP 플래그와 runtime 등록은 변경하지 않음 | 기존 paired_host_policy_integration 완료 자료 |
| 이벤트 | radarState Event.valid=False일 때 canError/temporary/fault/wrongConfig/오류없음으로 분기 | SelfdriveD:426–452 |
| 수신 중단 | generic all_checks→alive/frequency/valid 부족에 commIssue 등 | SelfdriveD:463–479 |
| 상태 | canError 즉시 해제. temp/fault/commIssue는 soft3초 | events.py:920–947, 1010–1018; state.py:20–68 |
| 활성 | softDisabling도 enabled/active 상태. longActive는 enabled 기반 | state.py:8–9, 115–121; controlsd.py:159 |
| 감속 요청 | Controls가 softDisabling을 forceDecel로 발행 | controlsd.py:436–438 |
| 계획 입력 | forceDecel을 읽고 지역 v_cruise를 0으로 만든 뒤 MPC.update에 전달 | 당시 planner 본문 사본:162, 224–225, 252–254 |
| 목표 손실 | non-blended 분기에서 v_cruise=carrot.v_cruise로 덮음 | 당시 MPC 본문 사본:441–444 |
| 빈 lead | status=False이면 내부 최적화용 먼 가상 장애물로 계산을 유지 | 당시 MPC 본문 사본:384–396 |

**CP.radarUnavailable가 레이더 오류를 곧 무시하게 만드는 조건은 없다.** 오류 이벤트의 해당 분기는 Event.valid=False를 본다. 정상 radarcan은 오류 결과와 publish_error를 valid=False로 발행하고 DPath는 입력 SubMaster의 all_checks를 출력 valid로 사용한다. 따라서 오류True+validTrue 입력은 이 producer 계약과 모순되는 합성 계약 검사다. 현재 정상 producer가 그 조합을 실제로 발행했다고 말하지 않는다.

LongitudinalPlanner는 lead.status와 수치를 MPC에 넘기며 일반 경로에서 radarErrors 자체를 직접 정지 명령으로 쓰지 않는다. `plan_send.valid`는 carState/controlsState/selfdriveState 체크를 사용한다(당시 사본467행). 일반 계획 valid가 RadarState의 모든 오류/나이를 독립적으로 차단한다고 해석하지 않는다. Controls는 호스트 활성 상태와 계획을 받아 LoC를 갱신한다. C는 radarState를 받지 않으며 계속된 정상 PCM RX의 독립 권한과 소프트웨어 longActive는 다른 경로다.

## 최초 실행의 상태 전이

run01을 직접 실행해 8조건/구조 불변식80개, 준비 오류0·구조 실패0을 얻었다. **구조 검사 통과는 soft 감속 행동 성공이 아니다.** 원형 source8과 C 라이브러리 지문은 각 실행 전후 같았다. 초기 False에서 실제 원형 PCM 이벤트와 정상 메모리 C RX로 활성화했고, CP.radarUnavailable=True를 유지했다. C/호스트 권한 setter·init_tests·실제 CI.init·차량 TX는 호출하지 않았다.

| 입력 | 상태·longActive 결과 | 양수 제어 틱 / 양수 ACC frame | 해석 |
|---|---|---:|---|
| 건강한 빈 lead | 4초 enabled/longActive 유지 | 400 / 133 | 장애물을 관측한 실제 장면이 없는 정상 크루즈 fixture |
| canError=True/valid=True | 같은 enabled 유지 | 400 / 133 | producer 계약 불일치 합성 입력 |
| canError=True/valid=False | 첫 틱 disabled/longActive=False | 0 / 0 | 즉시 해제 경로 |
| temporary/valid=False | 300틱 soft 뒤 disabled | 300 / 100 | forceDecel 전달 손실 관측 |
| radarFault 또는 wrongConfig/valid=False | 300틱 soft 뒤 disabled | 각각300 / 100 | 같은 경로 |
| valid=False/오류 없음 | commIssue, 300틱 soft 뒤 disabled | 300 / 100 | 같은 경로 |
| radarState 발행 중단 | 0.45초에 commIssue→soft, 3.45초에 해제 | 345 / 115 | alive 검출 뒤 3초 상태기계. MCU deadline과 다름 |

카드는 SelfdriveD/Controls보다 먼저 실행해 이전 CC를 적용하는 명시적 큐 순서다. 해제 첫 틱의 이전 CC와 다음 틱 비활성 CC를 구분했다. 이 위상에서는 canError 첫 틱에 0x343 발행이 없었고 다음 발행은 0이었다. 다른 위상에서도 같은 순간 값을 보장했다고 확대하지 않는다.

## 추가 읽기 trace가 확인한 실제 목표 덮어쓰기

run02_observation은 첫 결과를 덮지 않고 healthy/canError/temporary/producer-stop 4조건만 다시 관측했다. 원형 MPC.update의 인수와 코드 지역변수만 Python trace로 읽었고 args/locals/return을 바꾸지 않았다. 동일 원형 함수·native C/Cython solver·Toyota CC·메모리 C TX를 실행했다. 구조40검사는 통과했지만 **temporary·producer-stop 두 조건의 감속 목표 전달은 실패**했다.

| temporary 가상 상대시각 | state / longActive / forceDecel | MPC 인수 → 실제 지역 목표 | plan aTarget / shouldStop | 생성343 / C |
|---|---|---|---|---|
| 0.00초 | soft / True / True | 직전 모델21.3889 →21.3889 | +0.9502 / False | 이 틱 발행 없음 |
| 0.05초 | soft / True / True | **0.0 →21.3889** | +0.9664 / False | 이 틱 발행 없음 |
| 0.10초 | soft / True / True | **0.0 →21.3889** | +0.9819 / False | +1.149m/s² / 허용1 |
| 2.99초 | soft / True / True | **0.0 →21.3889** | +1.2068 / False | 이 틱 발행 없음 |
| 3.00초 | disabled / False / False | 이전 계획의0.0 →21.3889 | +1.2055 / False | 이 틱 발행 없음 |
| 3.01초 | disabled / False / False | 이전 계획 유지 | 계획값과 별개로 제어0 | 0.0 / 허용1 |

각 temporary·producer-stop에서 **고유 계획호출60회**의 인수0이 양수 지역 목표로 덮였다. 최초 summary의300은 100Hz 행에 반복 저장한 같은 trace 수이며 300회의 계획 계산으로 세지 않는다. 전체 네 조건의 warm+후속 trace는 각각150회였고 후속4초 고유 계획은80회다. `forceDecel_at_planner`와 새 Controls 발행 forceDecel의 위상 차이를 행에 함께 보존했다.

CarrotPlanner는 75km/h PCM 설정에 fixture의 Eco+2를 반영해 v_cruise=77km/h를 유지했다. 원형 계획기는 forceDecel 때문에 별도 인수만0으로 만들고 Carrot 객체 값은 바꾸지 않았다. MPC의 ACC 분기가 그 객체 값으로 인수를 덮으면서 zero 목표가 사라졌고, source=cruise/solver status0의 정상 계산은 잘못 유지된 목표를 따랐다. 이는 이 입력에서 **QP 수치 실패보다 소프트웨어 목표 전달 순서의 문제**로 재현됐다.

C controlsAllowed는 정상 PCM ON RX가 계속돼 True였다. 허용은 새 권한 재생성이나 차량 재활성이라는 뜻이 아니다. host longActive가 False가 되면 실제 생성 ACC가0으로 바뀌었으며 C가 비활성0을 허용했다. 양수 제어/차량용 요청값/물리 차량 가속은 같은 값이 아니므로 각 층을 따로 기록했다.

## 원본 OFF 로그와 별도 근거

부모의 별도 원본 로그 집계를 읽었다. 원본 radarState2,792개는 모두 오류none, validTrue2,672/False120이다. leadOne statusTrue1,630개는 모두 radarFalse였고 leadTwo는 전부False였다. 원본 carControl15,358개는 enabled/longActiveTrue0이다. 이 **Vision Only·원본 OFF** 자료와 R9의 독립 ARS175선택 또는 새 합성 ON 실패를 혼합하지 않는다. 오류 없음이 실물 radar 탐지·PCS 안전성이나 active 경로 검증이라는 뜻도 아니다.

R9은 실제 CAN batch367점/2,399레코드를 독립 mode1에 전달하고 원본 OFF를 보존해 MPC175입력을 확인한 자료다. 이번 fixture는 새 radar point를 만들지 않고 기본 빈 lead.status=False를 공급했다. 실제 point 손실→DPath의 영상 대체/선택/보유 정책을 직접 검사한 것은 아니다. healthy 빈 lead에서 가속이 나온 것만으로 실제 앞차 누락 결함을 확정하지 않는다. source가 쓰는 내부 최적화용 가상 장애물은 실제 레이더 객체 발행과 구분한다.

## source 버전과 동결 인계

원형 run01/run02의 main raw source 지문은 MPC `b0a5c630…`, planner `01ead57b…`였다. MPC의 실제 로드 경로는 immutable build_unique의 Python overlay였으며 LF 본문 지문은 `7f647b9a…`다. planner LF 본문 사본은 `781b78157f…`다. LF→CRLF 변환 지문이 실행 당시 main raw와 정확히 같음을 별도 읽기 동결에서 확인한다. Python 본문/행 번호는 같지만 경로·줄바꿈 지문을 같다고 섞지 않는다.

실행 당시 원형 본문 두 개를 original_source_archive에 읽기 사본으로 보존했고 run01/run02의 실행 도구·Chain 사본과 원본 JSON/행을 유지했다. 부모는 이후 두 생산 lab Python source를 별도 후보와 같은 본문으로 수정했다. 그 현재 내용과 후보 검증은 부모의 새 작업이며 이 보고서의 **원형 실패를 소급 수정하지 않는다.** B는 이 이후 새 C/호스트 계산을 멈추고 결과·hash 정리만 했다. 모든 .so와 기존 결과/운영 Params/outputs/release는 변경하지 않았다.

최종 근거는 실행 당시 source8 before/after, C 라이브러리 hash, 당시 도구 SHA, 실제 인수·지역값 witness와 시각별 shouldStop/생성343/C 반환이다. 구조80+40 검사는 실차 안전 통과나 실패 해소120건으로 표현하지 않는다. 후보의 zero 목표 유지·후속 제어 응답·기존 건강 경로 회귀는 부모의 별도 검사가 필요하며 이 에이전트가 실행했다고 말하지 않는다.

합성 입력의 stock 피드백은 GVC0/PCM 상태8/차간3 가정이고 CI.update는 입력 반환만 대체했다. actual CI.apply/CarController/CANPacker와 C RX/TX는 메모리에서 실행했다. source 선언3초는100Hz 호출300틱이며 실제 wall·MCU/차량 heartbeat·실제 actuator 지연을 평가하지 않았다. model20Hz와 control100Hz의 큐 순서를 기록한 고정ego 검사다. 실제 펌웨어/차량/ARS live/PCS/AEB/회생은 미검증이다.
