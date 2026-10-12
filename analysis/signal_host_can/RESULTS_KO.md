# Mode0 호스트 + SignalMode2 + Toyota CAN/C 메모리 연결

정상 비활성 상태에서 원형 초기화·PCM enable·실제 신호 수신기·redhold·Toyota CAN 생성·C TX 검사까지 연결했다. 전이31조건의 현재 기록 429개 판정과 moving2조건 18개 판정은 실패0이다. 최초31조건 실행에서는 invalid_can 기대 조건1개가 잘못됐으며 원본 실패를 보존했다. 소스 canError 정책을 확인하고 그 조건만 새 검사로 재실행했다. 나머지30조건을 다시 실행한 결과로 과장하지 않는다.

## 정상 baseline와 합성 입력

최초700틱 baseline은 생성 시SD/CC/readyFalse → 원형 준비100.50초 → PCM102.00초 enable → redhold102.20초 획득, 이후480틱 유지다. 현재17개 검사가 통과했고 앞선16개 버전은root가 독립 복사 재실행했다. Start runtime의actualSubMaster context valid/enabledTrue99회, Prepare OX geometry context valid130회, 실제생성CAN1,264개를 확인했다. 실제SignalAssistRuntime.read를Start/Prepare가상속해사용한다. Mode2에서retired assist_enabled는False이며 legacySignalAssist를직접주입하지않았다.

NativeSignalHarness/core 모듈 자체는 import 시 messaging/Params를 덮으므로 직접 import하지 않았다. 검증된 관측 스키마/필드와 합성 trajectory 함수 본문만 읽었다. 판정은 원형 CarrotPlanner()/StartRuntime/PrepareRuntime/SubMaster/StateMachine/Controls/CANPacker/C에서 실행했다. Runtime read 관찰 wrapper는 원형 반환값을 그대로 전달해enabled/valid를바꾸지않는다. 파일 읽기/임시교체만 메모리다. 실제 CI.init·UDS·드라이버·Panda·차량소켓은 실행하지 않는다.

설정은 메모리 Mode0/LongActuatorDelay20/AlphaTrue/SignalAssist2/Tracks0/NNFF0이다. 실제factoryCP flags1372/PCMTrue/directLongTrue/radarUnavailableTrue/minEnableSpeed-1은강제로바꾸지않았다. 정상 C 권한은같은실제hook의PCM메모리RX로생성했고 controlsAllowed=True setter는0회다. 실제차량준비/MCU heartbeat는미검증이다.

ego0/standstillTrue/GVC0/aEgo0, calibrated rpy0와정상XYZ pose, tizi/OX03C10/1928×1208, 33개lane/road 배열, 동일synthetic housing의red/green/unknown은명시적합성입력이다. 실제영상 인식/차선 귀속/거리 측정/센서 캘리브레이션을입증하지않는다. 원형frame-profile이knownOX를판정하여source_size/full_frame_resize를실제publisher스키마에담았다.

## 획득 시각과 발행 카메라 기록

모델EOF/frameId와관측EOF/frameId를각각기록했다. 관측latency100ms 가정의획득EOF/frameId가실제로앞서메모리버스에발행된roadCameraState의쌍과일치하는지history에서정확대조했다. baseline140관측중138일치,99.90/99.95초의처음2개는100초부터시작한history이전에해당한다. PCM활성화/hold이후불일치0이다. 이조건을새신호판정/허용규칙으로넣지않았고 진단만추가했다. 실제영상픽셀·커널센서 lineage는아니다. 모델currentEOF와100ms전관측을같은프레임으로강제하지않았다.

관측정체/오래된EOF/다른session은별도조건이다. 프레임ID를시간으로생성한합성camera history가일치한결과를실물drop/reorder/부팅clock검증으로확대하지않는다. 가상MONOTONIC100Hz이며BOOTTIME/MONOTONIC 실제장치관계와OS 지연은미검증이다.

## 500ms 가속 입력의20Hz 위상

기준model tick은103.50초, host/CC100Hz와계획20Hz다. phase0/10/20/30/40ms를나누고관측파일을계획전/후에발행했다. 이때drivergas=True와기존부분23조건의gas=False/수동CCoff를같은원인이나검사로합산하지않는다.

| 가속 시작 위상 | 첫 source context / Start cooldown | hold 제거 → 재획득 | 첫 양수LoC / C허용 양수CAN |
|---|---|---|---|
| 0ms | enabled=True,gas=True; cooldown=113.5 | 103.50 → 4초창내없음 | 104.05 / 114개 |
| 10ms | enabled=False,gas=True; cooldown=negative_infinity | 103.55 → 104.2 | 104.05 / 5개 |
| 20ms | enabled=False,gas=True; cooldown=negative_infinity | 103.55 → 104.2 | 104.05 / 5개 |
| 30ms | enabled=False,gas=True; cooldown=negative_infinity | 103.55 → 104.2 | 104.05 / 5개 |
| 40ms | enabled=False,gas=True; cooldown=negative_infinity | 103.55 → 104.2 | 104.05 / 5개 |

phase0은새gas와이전CC.longActiveTrue를먼저본sourceStartGuard의gas분기로hold/anchor를reset하고cooldown113.50초를설정했다. 나머지phase는다음model틱에이미CC.longActiveFalse를봐 enabled=False 분기가gas보다앞서reset하며cooldown을설정하지않았다. Prepare는gas/brake를enabled앞에서검사하므로같은cooldown규칙이아니다.

driver_cooldown은hold=False를반환하는신호veto억제/운전자override정책이며10초출발금지가아니다. 따라서phase0의가속해제후양수CAN114개를“10초정지보장실패”로판정하지않는다. 다른phase는빨간불재획득까지150ms창에서양수CAN5개를실제로허용했다. C는신호색을해석하지않고sourceCC권한/가스/부호한계만검사한다. 같은500ms운전자의도에서도읽는위상에따라veto복귀기간이다른source분기재현이며실차안전성/새정책결론은별도다.

before/after delivery에서가스위상결과는같았지만다른조건까지항상같다고가정하지않았다. 확인된green release는before104.20초/after104.25초, 양수LoC는104.75/104.80초로1계획틱차이가났다. 그양수요청은명시한모델미래진행입력과기존계획이만들며green이새로운go권한을생성한것이아니다.

phase40의10ms가스pulse에서는실제host override와CCfalse가한틱성립했다. 다음model이gasFalse+이전CCfalse를봐hold103.55초를지우고103.75초에재획득했지만양수LoC/CAN은0이다. 계획이gasTrue를보지못한이경로의기존Carrot정지카운터가창을덮었다. latch손실만으로양수제어가나왔다고단정하지않는다.

## 나머지 전이와 권한

| 조건 | 원형 결과/경계 |
|---|---|
| 연속red / unknown / 관측800ms stale / 관측파일중단 | before/after 모두hold유지, 양수LoC/CAN0 |
| 같은anchorgreen / 새sessiongreen | 같은anchor의확정green만veto해제. 새session은기존hold유지+greenreleaseanchor초기화이고전체Guard.reset과다름 |
| OX provenance누락 | 실제Prepare geometry context는False로차단. StartGuard는별도geometry없이기존hold유지하므로두기능을합쳐차단됐다고말하지않음 |
| CANvalidFalse | 첫plan은enabledTrue/validFalse에서hold유지. 같은틱host는원형canError로immediate-disable, 다음model은enabledFalse라holdreset. 양수0; 최초기대오류를보존 |
| 취소 / 제동 / PCM재시작 | 원형host disabled→정상PCMoff/on 재시작. red재획득전제/큐/제어주기를분리해양수창을실제기록 |
| DM0.6초freeze | 103.95초softDisabling: enabled/active/longActiveTrue, holdTrue. 부분CC-onlyFalse와같지않음 |
| DM4초freeze | 106.95초disabled: enabled/active/longActiveFalse. 다음107.00초runtimeFalse가hold를reset. 실제건강복구후PCM재시작과red재획득을기록 |
| model/plan0.6초freeze | 실제호스트soft-disable/회복을관찰, 이창에서는hold유지/양수0. 모델/계획중단시runtime가읽히지않는틱은lastcontext로분명기록 |

동일box/session을기본으로유지했다. session변경green은별도시험으로따로기록했다. 수신SD/CC와새로발행된CC, C controlsAllowed/longitudinal_allowed, generatedCANraw는각기다른시점/권한이므로분리했다. actualC의거부개수는예상한가스RX/ACC33.33Hz경계와맞으며거부자체를오류로세지않았다.

## Moving Prepare와model출처age

고정ego15m/s·GVC0의추가2조건에서원형Prepare는750틱중485틱active였고native계획/LoC최소-0.5m/s²를확인했다. 두조건은modelEOF만fresh0초/old2초로다르고header/수신·관측EOF·pose는신선하다. oldEOF2초에서도actualcontext valid/enabledTrue와active485틱은같았다. 현재SourceRuntime는수신건강과model의획득age를같은판정으로묶지않는다는재현이다. 오래된geometry의실차안전성보증이아니며새source-age cutoff는구현하지않았다.

전이CAN 25,918개와movingCAN 2,718개에서C판정불일치0/권한변경0, DBC해독오류0/정의된checksum오류0을직접확인했다. checksum은DBC에정의된메시지에만검사했고0x750는기존exact tester-present만확인했다. LKA torque0/LTA비작동/bus0/주소DLC전제를추가대조했다. 실제0x411의PCS_INDICATOR1/PCS_OFF1과0x750생성/메모리C허용은PCS보존/ECU준비증거가아니다. 실제CI.init/UDS/차량송신은없다.

## 원형 보존과 직접 재현

실행한host3클래스19메서드global과25상수는원형namespace와일치했다. 현재source hash와각실행source hash가같고기존immutable MPC6개/C라이브러리도같다. 새주기/권한/신호정책·Panda보호조건을바꾸지않았다. 동결결과JSON과증거manifest에각case/최초실패/실행로그를함께기록한다.

```sh
# WSL Ubuntu, 프로젝트 루트, 기존 격리 venv와immutable build 읽기
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/run_baseline.py
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/run_case.py gas --phase-ms 0 --order before
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/run_case.py gas --phase-ms 10 --order before
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/run_suite.py
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/run_moving.py --model-age 2
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/audit_namespace.py
work/download_e2e/work/offline-venv/bin/python work/signal_host_can_integration/freeze_results.py
```

실제이미지/신호인식정확도·커널카메라metadata·시계동기·Toyota수신CAN파서/firmware·ECU/GVC/브레이크/모터반응·MCU heartbeat/relay·차량제동거리·회생·PCS/AEB·ARS live·Konik/ARM운영빌드는미검증이다. 기존fixture/results/source/.so/환경/운영Params/차량은바꾸지않고새폴더파일만작성했다.
