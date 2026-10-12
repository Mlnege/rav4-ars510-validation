# 신호 정지 기억·운전자 개입·시간 정책의 읽기 설계 감사

같은 운전자 가속 입력인데 계획 주기와 맞는지에 따라 신호 정지 개입이 10초 억제되거나 빨강 재확인 뒤 복귀하는 차이가 보존된 전체 체인에서 확인됐다. 이 차이를 단순 분기 순서 변경으로 통일하면 현재 빨강을 다시 잡는 조건까지 10초 동안 막을 수 있다. 따라서 “같아졌다”를 “더 안전하다”로 판단할 수 없다. 먼저 운전자 개입의 의미, 비활성 사유, 정지 기억과 제어 권한, 시간 출처를 같은 계약으로 정해야 한다.

이번 단계는 읽기 설계 감사다. 허용된 이 문서 하나만 작성했으며 새 시험, 코어·기존 helper·결과·native binary 변경, 새 시간/권한/신호 정책 구현은 없다. 아래 전체33조건 수치는 `work/signal_host_can_integration/frozen_results.json`, `suite_final_summary.json`, 개별 result와 source를 **읽은 결과**다. 이 검토자가 이번에 직접 재실행한 결과라고 보고하지 않는다. 현물 인식·안전성 결론이나 실차 활성화 근거로 사용하지 않는다.

## 보존된 전체 연결에서 관측된 것

기록에는 전이31조건 429판정, moving2조건 18판정, 정상 baseline17판정이 있다. 현재 기록의 판정 실패0은 도구가 지정한 관측·불변 조건의 결과이며 모든 상황의 안전성을 뜻하지 않는다. 최초 invalid_can 기대조건 실패1개를 보존했고 그 조건만 재실행했다. 나머지30조건을 다시 실행했다고 과장하지 않는다. 설정은 메모리 SpeedFromPCM0/LongActuatorDelay20/AlphaTrue/SignalMode2/Tracks0/NNFF0이다.

| 읽은 조건 | 실제 보존 관측 | 의미와 한계 |
|---|---|---|
| gas500ms, model 틱에 맞춘0ms | Start context enabled=True가 새 gas를 봄. hold103.50초 제거, cooldown113.50초,107.49초까지 hold 없음. gas release104.00초, 첫 양수 제어104.05초, C허용 양수 ACC CAN114개 | cooldown은 신호 veto 억제 기간이다. 10초 동안 차량을 정지시키는 명령이 아님 |
| gas500ms, phase10/20/30/40ms | 다음 model 틱이 이미 CCfalse를 봄. hold103.55초 제거, Start cooldown 미설정,104.20초 빨강 재획득. 첫 양수 제어104.05초, C허용 양수 ACC CAN5개 | 같은 운전자 입력의 위상 차이에 따른 분기·신호 복귀 차이. 물리 차량 운동은 적분하지 않음 |
| gas10ms pulse, phase40ms |20Hz 계획은 gasTrue를 한 번도 못 봄.103.55초 이전 CCfalse로 hold 제거,103.75초 재획득. 양수 LoC/CAN0 | 정지 기억 손실과 실제 양수 요청은 다른 결과다. gas를 앞에 옮겨도 관측하지 못한 pulse를 되살릴 수 없음 |
| 끊김 없는 red/unknown/stale800ms/관측 중단 | hold 유지, 양수 LoC/CAN0 | 이미 확인한 빨강의 불확실성 보존 경로. 신규 빨강 인식의 정확도 증거 아님 |
| 같은 상자의 green | before104.20초/after104.25초 veto 해제, 양수 LoC104.75/104.80초 | green은 원형 진행 모델의 veto를 제거한다. 독립 출발 권한을 생성하지 않음 |
| 새 session의 green | 기존 hold 유지, 새 green release anchor는 없음 | session 변경은 전체 guard.reset과 다른 동작 |
| CANvalidFalse | 첫 계획 validFalse/context enabledTrue에서 hold 유지. 호스트 canError immediate-disable 뒤 다음 계획 context disabled로 holdreset, 양수0 | 자료 유효성만의 정지 기억 정책과 전체 호스트 권한 해제를 분리 |
| 취소·제동·DM 장기 비활성 후 PCM 재시작 | 원형 disabled→명시적 정상 PCM 재시작 경로와 빨강 재확인 창에서 C허용 양수 ACC CAN5개 기록 | gas 자동 복귀와 다른 재시작 권한. 단순 reset 보존만으로 모든 재시작을 안전하게 바꿀 수 없음 |
| DM600ms 중단 | softDisabling에서도 enabled/active/longActiveTrue, hold 유지 | soft disable은 단순 CCfalse 입력이 아님 |
| modelEOF fresh/old2초 moving 비교 | 각750host틱 중 Prepare485틱 active, healthy read109회, 최초102.65초, 계획/LoC 최저-.5m/s². oldEOF2초도 context enabled/validTrue | model의 획득 시각을 수신 건강과 묶지 않는 현재 계약. 오래된 geometry의 현물 정확도를 보증하지 않음 |

관측 전/후 발행으로 나눈 gas 위상 결과는 이번 자료에서 같았다. green처럼 한 계획 틱 차이가 난 다른 경로까지 항상 같다고 일반화하면 안 된다. 전체 결과의 CAN은 Python Toyota 생성·DBC 해독 및 실제 C hook의 메모리 판정까지다. 센서/stock feedback/ego0 또는 ego15/aEgo0/GVC0은 합성이고, 실제 CI.update/ECU/Panda/차량 TX·물리 운동은 아니다. C는 신호색·modelEOF를 판단하지 않으므로 C허용을 신호 인식·정지 안전성으로 번역하면 안 된다.

## 현재 정지 기억·reset·cooldown의 책임

`SignalAssistRuntime.read`의 context enabled는 feature enabled AND sd.enabled AND cc.longActive이고, valid는 seen/valid/alive와 수신 나이·canValid다(`signal_assist_runtime.py:76-80`). 이 한 Boolean에는 운전자 override, 실제 비활성, 기능 off, 국소 권한 차단이 합쳐질 수 있다. 소비자인 StartGuard가 같은 False만 받으면 비활성의 원인을 알아낼 수 없다.

| 현재 조건 | StartGuard의 원형 처리 | Prepare의 원형 처리·후단 |
|---|---|---|
| featureoff 또는 sd/CC 비활성 | enabled=False를 가장 먼저 처리. hold/warn/session/box/frame/timestamp/pending/count reset. last_now는 유한 now 또는 -inf로 갱신 | enabled 부적격이면 histories/priority/active reset. cap은 최종 activeFalse 때 해제 |
| driveFalse | 위 disabled reset과 같음. 기존 cooldown은 지우지 않음 | ineligible reset. 기존 cooldown·session/last_capture 등 모두를 초기화하는 함수는 아님 |
| sdTrue/CCfalse | 유효한 빨강·validTrue여도 context enabledFalse로 위 reset | 운용 권한 부적격. 이 상태를 gas라고 확정할 정보는 Boolean 하나에 없음 |
| enabledTrue + gasTrue | hold/anchor reset, last_now 갱신, cooldown=now+10. 유한 now가 아니면 cooldown=+inf | 유한/증가 now를 확인한 다음 gas 또는 brake가 있으면 cooldown=now+10, 이후 ineligible reset |
| gasTrue지만 enabledFalse | disabled 분기에서 먼저 return해 gas 분기를 건너뜀. 새 cooldown 설정 없음. 기존 cooldown은 유지 | clock 검사 통과 시 gas/brake는 enabled 검사 전 처리하여 cooldown 설정 |
| brake | StartGuard.update에는 brake 인수가 없다. host의 brake/cancel/disable 및 CC 상태를 통해 영향을 받음 | brake를 직접 확인해 cooldown 설정·active reset. 최종 cap도 brake 시 적용하지 않음 |
| context validFalse 또는 speed 비유한 | enabled/gas/clock 분기를 지난 뒤 pending/count만 지우고 기존 hold 유지 | ineligible로 active/history reset |
| 시계 비유한·과거로 이동 | enabled/gas 분기가 먼저다. 활성·gasFalse 경로에서는 hold 유지, pending/count/box/session 제거. last_now는 이전 값을 유지 | now 비유한 또는 <=last_now면 clock reset. last_now/cooldown은 reset에서 지우지 않음 |
| 관측 missing/unknown/stale/future/malformed | 기존 hold를 해제하지 않음. 확인 이력이 끊어지거나 새 확인 시작 | 신뢰할 fresh red가 없으면 stale/no_red/malformed 등의 reset으로 준비 감속 해제 |
| session 변경 | held red 자체는 유지. box·frame·timestamp·pending/count를 새로 시작. 새로운 session의 green만으로 old hold 해제하지 않음 | 새 session에 histories와 source frame/capture 이력을 다시 시작 |
| held 아닌데 speed>.3 | moving_no_entry reset. 신규 정지 veto를 잡지 않음 | moving prepare는 별도의5~82km/h 미만 속도·geometry·모델 조건 |
| 확인된 같은anchor green | released=True 후 reset. cooldown/last_now는 그 reset으로 지우지 않음 | green은 red 준비 감속의 신규 진입을 만들지 않음 |
| constructor/프로세스 재시작 | 새 instance는 hold=False, last_now/cooldown=-inf. 메모리 hold/cooldown 영속 저장 없음 | 새 instance에서 session/last_capture/history/cooldown 초기화 |

StartGuard.reset의 보존/삭제는 `signal_start_guard.py:66-77`, 전체 우선순위는 `:144-176`이다. **reset은 cooldown을 지우지 않는다.** 따라서 기능 off, 기어 변경, confirmed-green reset이 이미 설정된 cooldown을 자동으로 제거한 것으로 해석하면 안 된다. 반대로 새 프로세스는 cooldown을 상속하지 않는다.

Prepare.reset도 histories/priority/active만 지운다(`signal_stop_prepare.py:234-240`). session/last_frame/last_capture/last_now/cooldown/last_sound는 별도 변경 없이는 남는다. Prepare의 clock→gas/brake→eligibility→관측 순서는 `:242-277`이며 StartGuard와 동일한 reset 모델이 아니다. 두 기능의 “정지” 또는 “off” 이름만으로 상태 의미를 통합하면 안 된다.

Clock가 잘못된 순간 gasTrue이면 StartGuard의 gas 분기가 clock 검사보다 앞서 +inf cooldown을 만들 수 있다는 것은 source상 반례다. 이 감사에서 실제 호스트로 재현한 결과는 아니다. 실제 consumer MONOTONIC의 정상 경로와 replay/부팅/잘못된 입력 clock을 구분해야 한다. clock 회복이 이전 운전자 상태를 삭제할지 유지할지도 명시하지 않은 채 숫자만 clamp하거나 시계를 모델 EOF에 맞추면 안 된다.

## 기능 모드·명시적 비활성·재시작

SignalAssistMode0은 off, mode1/2는 StartGuard를 켜고, moving Prepare의 실제 감속 적용은 mode2만 허용한다. retired assist_enabled는 False다(`signal_mode.py:35-50`). 따라서 mode1을 모든 제어가 없는 표시 전용으로 설명하면 틀리다. 같은 start-veto 기능은 살아 있다.

Runtime의 feature 확인 및 Params mode cache는 .5초 주기다. mode0→1/2 전환은 enabled_since 이후 관측만 사용하고, feature off가 읽히면 context disabled로 StartGuard를 reset한다(`signal_assist_runtime.py:55-70`). mode1↔2는 feature Boolean이 계속 True라 StartGuard에 별도 mode-change reset이 없다. Prepare는 mode가 변할 때 별도 reset·mode_since를 설정하고 이전 관측을 제외한다(`signal_stop_prepare_runtime.py:73-83`). 기존 cooldown은 그 reset으로 지우지 않는다. constructor에서 이미 feature가 켜져 있던 경로와, 실제 off→on 전환의 enabled_since도 구분해야 한다.

explicit cancel/PCM off, 운전자 gas override, 임시 데이터 무효, 기어 park/reverse, 기능 off, 실제 프로세스 재시작은 각각 다른 의도와 권한 경계다. 현재 context enabledFalse만으로 이를 모두 reset하지만, 보강에서 그 reset을 모두 보존으로 바꾸면 사용자가 끈 기능이나 다른 정차/차로의 오래된 신호 기억을 재활성화 때 되살릴 수 있다. featureoff에서는 새 신호 제동·출발 veto를 강제로 남기지 않아야 한다는 기존 opt-in 의미와 함께 검토해야 한다. 이 문서는 새 정책을 선택하지 않는다.

## 단순 보강 위치별 반례

| 후보 위치/방향 | 해결할 수 있는 제한된 문제 | 새 반례와 확인이 필요한 계약 |
|---|---|---|
| gas 검사를 enabled보다 앞에 이동 |20Hz가 gasTrue를 읽은 위상 사이에서 cooldown 설정 유무를 통일할 수 있음 | phase10~40ms의 현재150ms 빨강 재확인을10초 막음. 지속 gas를 매 계획 읽으면 기존 phase0의 onset+10초가 마지막 관측+10초로 연장될 수 있음. featureoff/driveFalse에서도 hidden cooldown 생성 가능.20Hz가 놓친10ms pulse는 해결 못함 |
| StartGuard를 Prepare와 동일하게 gas/brake 처리 | 두 기능 이름의 표면적 통일 | Prepare는 moving 완만한 cap이고 Start는 stopped latch다. brake/cancel에10초 veto 억제를 새로 주면 명시적 재시작과 빨강 재획득 의미가 바뀜. 동일 숫자10초가 같은 driver intent를 뜻한다는 근거 없음 |
| CCfalse 동안 hold/anchor를 항상 보존 | 권한 일시 중단으로 생기는150ms 재확인 창을 줄일 수 있음 | explicit gas/cancel/featureoff/park/새session/장치재시작 후 stale anchor를 되살릴 수 있음. 운전자 pedal 우선·다른신호/차로·재시작 상태를 구분해야 함 |
| context enabled에서 CC.longActive를 제외 | sdTrue의 자연 override 중에도 gas를 관측할 수 있음 | 신호 state가 제어 권한 없는 구간에서 계속 진행하고 green/준비 이벤트를 갱신할 수 있음. feature·drive·driver·신뢰도와 최종 명령 권한을 각각 어디서 소유할지 새 계약 필요 |
|100Hz 기존 driver event를20Hz 신호 판단에 이력으로 전달 | 짧은 pulse와 model 위상 차이를 인지할 수 있음 | 이벤트의 source/onset/release/seq와 수신 지연·중복·원인이 필요.20Hz 최신 snapshot만이 이미 놓친 의도를 복구하지 못함. 새필드/보관 규약을 승인 없이 구현하면 원형 schema/재시작 의미가 달라짐 |
| Controls 국소 freshness guard로 CC만 차단·자동 복귀 | 오래된 producer/ref 헤더 요청의 사용 경계를 만들 수 있음 | gasFalse인데 CCfalse→Start reset을 만드는 기존부분 반례. fresh 복귀 시unknown/green/red 확인 전양수창 가능. sd 상태·3초softDisable·driver override와 새 국소권한 정책을 혼동하면 안 됨 |
| modelEOF 나이로 Prepare context만 무효 | 현재 oldEOF2초 geometry 사용을 구분할 수 있음 | EOF BOOTTIME와 consumer MONOTONIC의 실제원점 확인이 선행. cap 해제는 target를 더 양수로 만들 수 있어 “자료거절=물리적으로더안전”은 아님. source/reference·현재신호·pose/calibration의 시간 일치도 필요 |
| producer valid만 강화 | 명백한 source 부적격을 표현 | Controls/card가 같은 valid를 명령 권한에 직접 쓰지 않는 경로는 남음. 모든 all_checks를 얹으면 순환의존성/초기화/정상 비동기 메시지 경로가 깨질 수 있음 |
|150ms 확인을 없애거나 latch를 강제복구 | 일부 재확인 창을 숨길 수 있음 | 단발 오인식·다른상자·session/reorder·camera pitch 확인 규칙을 약화. 검증된 관측 없이 새객체/정지 기억을 생성하는 것은 금지된 추측 구현 |
| cooldown을 단순삭제/줄임 | 현재0ms의오래된veto억제 관측을 없앨 수 있음 | 기존 수동gas override 의미를 바꾸고 가속중 신호오인식 개입을 만들 수 있음. 실제운전자 의도·속도·오인식 자료 없이 안전하다고 판단할 수 없음 |

일관된 정책은 onset/release/마지막 관측 중 무엇에서10초를 세는지, 짧은 pulse도 같은 override인지, gas를 떼면 원래신호를 재획득하는지, 명시적 PCM restart를 요구하는지부터 정의해야 한다. 현재 숫자150ms·10초·Prepare600ms는 서로 다른 증거/운전자/기하 확인 의미다. 새 threshold를 임의로 정하거나 TTL을 늘려 반례를 감추지 않는다.

## 여러 증상을 함께 다루려면 필요한 공통 계약

1. **입력과 driver intent의 출처.** gas/brake/cancel/PCM/feature/gear는 실제 어떤 source와 사건 시각에서 나온 값인지, 활성 권한의 어떤 이유로 False가 됐는지 알아야 한다. 최신 Boolean snapshot과 이미 발생한 driver event는 다르다. 기존 schema에서 신뢰할 근거를 확보할 방법부터 검증하고 새 CAN bit/명령을 발명하지 않는다.
2. **정지 증거와 명령 권한의 분리.** 같은 red anchor·확인 시간·신선도 상태를 유지하는 것과 실제 제동 명령을 허용하는 것은 별개다. 일시권한 pause·명시적off·driver override·새session·process restart별 삭제/보존 필드와 복귀 조건을 정의해야 한다. 유효성False와 enabledFalse의현재차이를 의도 없이 하나로 합치지 않는다.
3. **단일 consumer 시간과 서로 다른 source 시간.** 현재now, 획득EOF, producer헤더, 수신시각, 참조model/plan, event발생시각을 각각기록한다. 실제BOOT/MONO 관계·단위·부팅/절전/프로세스epoch가확인되지않으면자료나이를물리시각이라고단정하지않는다. 모델이멈춰도consumer시계가계속진행해야하며 frozen/model-following clock로old자료를젊게만들지않는다.
4. **참조·이력의 인과 관계.** 새model과old하지만아직fresh한plan은정상비동기상태일수있다. 최신model헤더와plan참조의즉시동등을요구하지않고known참조이력·과거/future/부팅/중복/역전 및관련geometry를검증해야한다. 신호100ms전관측과model현재EOF를같은프레임으로억지로묶지않는다.
5. **우선순위와 회복의 소유자.** driver개입·명시적disable·건강fault·신호veto·cap·원형model정지의우선순위를사유별로정의한다. freshness회복이drivercancel을자동으로취소하거나기능off를켜면안된다. 회복단계에서기존StateMachine/LoC/PID/CarController 상태와마지막정규CAN을함께확인해야한다.
6. **최종 출력의 의미.** red latch, shouldStop, aTarget, LoC출력, Toyota명령, C허용,이미전달된명령,물리응답은다른값이다.150ms latch손실과10ms pulse의양수0같은반례를보존한다. 기존33.33Hz정규CAN 사이이미전달된명령을새주기외송신으로가리지않는다.
7. **기능·차량 범위.** 신호정책은공통CarrotPlanner에있고현재SignalMode>0 opt-in은exactRAV4만의코드가아니다. exactRAV4 CarController의nonpositive stopping보강과공통신호정책의범위는다르다. mode0/1/2·stock/directlong·다른Toyota·다른브랜드/카메라의원형정상동작을어디까지보존할지선택전명시해야한다.

이 계약들은 아직 새 schema/정책/생산 코드로 구현되지 않았다. 한 Boolean과 분기 순서만으로 driver 의도와 source 나이 문제를 동시에 부작용 없이 해결했다고 주장할 수 없다.

## 정책 선택 전 추가로 필요한 자료와 검사

운전자가 gas를 누를 때 의도적으로 신호 veto를 얼마 동안 해제해야 하는지, pedal을 떼면 같은 빨강을 다시 확인해야 하는지, 기능off/명시적cancel/PCM재시작/장치restart에서 정지 기억을 버려야 하는지에 대한 제품 정책이 필요하다. 이 자료가 없는데 하나의 조건을 “안전한 정답”으로 정하면 다른 정상 운전 동작을 바꾼다. 기존 설정 명칭과 현재동작·차이·선택의영향을구체적으로정리한뒤정책후보를검토할수있다.

검사는 승인된 후보가 생긴 뒤 의미있는 경계를 확인한다. 기존33조건과 이전gasFalse 부분23조건을 각각보존하고, 0~50ms phase/짧은pulse/지속gas/해제/중복·지연전달/차량속도>.3·브레이크/취소/기어/모드0↔1↔2/동일·새session/clock rollback·future·invalid/모델·계획중단/soft·immediate disable/PCM·process restart를 조합한다. 함수별 unit 결과와 자연host→계획→LoC→Toyota정규CAN→실제C 결과를구분한다. 기존150ms확인·10초override·다른차량 경로를바꾸는조건은원형대비차이로보고하며일괄“회귀없음”을가정하지않는다.

현재 B는 고정ego0 또는15/GVC0/aEgo0이므로 양수CAN이 실제속도·거리·정지선 접근·회생/제동으로 이어지는지를 검증하지 않았다. 모델·관측 geometry가 최신/정확한지도 영상 없이 확정할 수 없다. 다음 시뮬레이션에서 실제경과 운동을 적분하더라도 명시한 plant·응답지연·피치/노이즈 가정의 결과일 뿐 현물 safety 결론은 아니다. 원본 영상·캡처/추론/계획/제어 시각·실물 firmware/stock/PCS·AEB 유지·MCU heartbeat·실차 제동/회생 자료가 별도로 필요하다.

## 읽은 근거와 현재 상태

보존 결과 SHA256: `frozen_results.json`=`7b9fcd747644ad3983224413408b55c42450d1609ca13db2e545782e1cc3c88b`, `suite_final_summary.json`=`b416e86dc149dc928e6ab7837ad72fb9a086fd86901fa89c61b7b4830f52d472`. 개별gas0/10ms·10ms pulse·moving oldEOF 결과의 원형context·cooldown·시간값도 읽었다. productionsource의분기·reset·mode·시간조건을대조했고, 기존시험source는그시험이현재무엇을확인하는지읽는용도로만사용했다. 이감사에서새gate를실행한결과는없다.

완료는 정책 상태표·단순 변경의 반례·공통 시간/권한/driver intent 계약·추가 근거 목록 작성이다. 후보 선택, 새 정책 구현, 테스트, 배포·실차 활성화 및 현물Safety 결론은 미완료이며 이번 허용 범위가 아니다. 원형 코어와 동결 도구·native·원본 결과는 변경하지 않았다.
