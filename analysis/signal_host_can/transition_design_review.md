# 신호 보조의 운전자 입력·비활성 전이 독립 검토

원형 소스에서 StartGuard와 Prepare의 운전자 입력 처리 순서가 다름을 확인했다. StartGuard는 enabled/drive가 False이면 gas 처리 전에 reset하고 반환한다. Prepare는 시계 검사 뒤 gas/brake의 10초 억제 시간을 먼저 설정한 후 enabled 등을 검사한다. 이 순서 차이는 원형 20Hz 호출과 자연적인 gasOverride에서 서로 다른 입력 조합을 만들 수 있다. **소스상 분기 차이이며 이번 읽기 검토로 전체 실행 결함이나 실차 안전성을 확정하지 않았다.**

기존 23조건은 gas=False인 CC-only 등의 합성 입력 전이다. 새로운 전체 호스트·Toyota CAN·C 권한 시험은 이와 별개로 실제 상태 전환이 만든 CC를 소비해야 한다. 이번 작업은 이 문서만 작성했으며 source·기존 결과·작성 중 벤치·바이너리는 수정하지 않았다. 새로운 실행 테스트도 하지 않았다.

## 검토한 소스

| 파일 | 읽은 SHA-256 |
|---|---|
| signal_assist_runtime.py | `7b45df853f5474ca86a7407ab455b4978e5936607428dc64b37007f7a57a47a2` |
| signal_start_guard.py | `f3ce89f60a7527f94075f0c470dd59e235a65f4ec621512416f3a5f12f171f10` |
| signal_stop_prepare.py | `f5c206efc2b4ff7d676d06ec4da558a3fe5b0f4901a56a920fa0ee193ee32c39` |
| signal_stop_prepare_runtime.py | `69980533b791c48525e6793e2a2d6702d077561507f1dca18c3c01490880ddba` |
| carrot_functions.py | `4f7f313f06889a258d4104bd286f04fd0c80fb0a6a07cb7760466a396cfa26d8` |
| controlsd.py | `695609a1088d70b9a0cb07f8a68bf6fdd5a2a88b078c0d4d39a29cdbdd8f92cc` |

호출 연결의 `signal_mode.py`, `longitudinal_planner.py`, 호스트 사건/상태 전환, 부분 `probe_final.py`, 새 신호 벤치의 signal_io·actor 순서도 읽었다. 도구에서 SourceSignalAssistRuntime 등으로 부르는 판단 코드는 저장소의 `SignalAssistRuntime.read()`를 뜻한다. 별도의 새 권한 정책이 아니다.

## Runtime enabled와 valid는 다르다

원형 `SignalAssistRuntime.read()`의 enabled 조건은 설정 활성과 **sd.enabled && CC.longActive**다. CC.enabled 자체를 조건으로 쓰지 않는다(`signal_assist_runtime.py:76–80`).

valid는 carState/modelV2/radarState/selfdriveState/carControl의 seen·valid·alive·수신 나이 0~250ms와 carState.canValid를 검사한다. enabled False와 valid False는 다른 조건이다. 수신 나이와 관측 내용의 촬영 timestamp도 별개다.

SignalMode2에서 production의 retired `assist_enabled`는 False이며 Start/Prepare 경로를 사용한다(`signal_mode.py:flag_override`). 새 전체 벤치가 기존 NativeSignalHarness를 직접 import해 설정/소켓을 다시 대체하지 않고, 관측 writer와 입력 형식만 가져오는 계획은 적절하다. Runtime 반환·context.enabled/valid를 덮어쓰면 자연적인 전이를 검사하지 못한다.

PrepareRuntime는 여기에 자세·보정·카메라 프로파일·추가 서비스의 수신 나이와 실수 유효성·회전 조건을 더 검사한다. `actuate`는 Mode2일 때만 True다. Mode1에서 관찰 가능한 PrepareDecision과 실제 감속 적용을 합치면 안 된다. Mode 전환은 Prepare의 확인 이력을 reset하고 이전 mode_since보다 앞인 관측을 제외한다. 설정 읽기에는 0.5초 캐시가 있어 즉시 변경으로 가정하지 않아야 한다.

## 상태 전이와 억제 시간

| 입력 조건 | StartGuard | Prepare |
|---|---|---|
| enabled=False 또는 drive=False | 먼저 전체 guard reset. hold·상자·session·확인 이력 삭제. gas 분기는 실행하지 않음 | 시계가 정상이면 gas/brake 여부를 먼저 처리한 후 부적격 reset |
| enabled=True, gas=True | reset 후 cooldown=현재 시각+10초 | enabled 여부와 관계없이 샘플된 gas/brake마다 cooldown=현재 시각+10초, active/history reset |
| enabled=True, valid=False, gas=False | pending/count는 삭제하지만 기존 hold는 보존 | active와 확인 이력을 reset |
| brake=True | 이 guard API에는 brake 인수가 없음. 호스트가 이후 enabled/CC를 내리는 경로와 구분 | gas와 동일하게 억제 시간 설정 후 reset |
| 관측 없음·미확인·오래됨 | enabled가 유지되면 기존 hold를 해제하는 근거가 아님 | 새 보조 감속 자격·확인 이력을 잃을 수 있음 |
| 시계 역행/비유한 | 활성 조건/gas 처리 뒤 검사. 기존 hold를 보존하면서 확인 상자·session 등을 지움 | 가장 먼저 검사하고 active/history reset. 이 경우 gas/brake 억제 시간 갱신 전에 반환 |

근거: `signal_start_guard.py:144–176`, `signal_stop_prepare.py:233–252`. StartGuard.reset은 cooldown과 last_now를 지우지 않는다. Prepare.reset도 cooldown·last_now·last_sound를 지우지 않으며 session/frame/capture는 일반 reset에서 보존한다. 같은 이름의 reset이 같은 기억을 지우는 함수라고 가정하면 안 된다.

**10초 cooldown은 출발을 10초 막는 기능이 아니다.** Start의 driver_cooldown은 기본 hold=False인 결정을 반환하고, Prepare는 보조 감속 active를 끈다. 운전자 가속 의도를 본 뒤 신호 보조 개입을 억제하는 기간이다. 원형 모델·호스트·C 권한이 이후 진행을 허용하면 이 cooldown만으로 정지를 보장하지 않는다.

Start의 빨강은 신선한 관측 최소 2개와 150ms 확인, 초록 해제는 같은 앵커에서 최소 3개와 700ms 확인을 요구한다. 단순 color 문자열이나 새 초록 상자만으로 해제되는 구조가 아니다. 새로운 빨강 획득은 hold가 없을 때 속도 절댓값 0.3m/s 이하여야 한다. Prepare는 5~82km/h의 움직이는 상황·확인 600ms·기하/모델/차선 조건을 별도로 요구한다. 정지 speed=0 시험에서 Prepare active가 False인 것은 움직이는 감속 실패의 증거가 아니다.

## 자연적인 gasOverride와 부분 CC-only의 차이

기본 DisengageOnAccelerator=0에서는 가속 사건이 OVERRIDE_LONGITUDINAL이고 원형 StateMachine의 overriding 상태는 sd.enabled와 sd.active를 유지한다. Controls는 overrideLongitudinal 사건 때문에 CC.longActive를 False로 만든다(`car_specific.py:gasPressedOverride`, `events.py:790`, `state.py:ACTIVE_STATES`, `controlsd.py:CC.longActive`).

따라서 ‘CC False/sd True’라는 축약은 정확하지 않다. 자연 가속 입력에서는 **CC.enabled=True, CC.longActive=False, sd.enabled=True**일 수 있다. C도 alternativeExperience=1에서 controls_allowed=True를 유지하지만 gas_pressed 때문에 longitudinal_allowed=False가 된다. 이 둘을 같은 권한으로 해석하면 안 된다.

| 조건 | 입력을 만드는 경로 | gas·운전자 의도 | 원형 신호 분기 해석 |
|---|---|---|---|
| 기존 CC-only 50/500ms | SchemaInputs.touch 뒤 CC.longActive만 False로 명시 배치 | gas=False, brake=False | 자연 gas 분기·cooldown 없이 enabled False reset을 검사 |
| 기존 sd+CC off | 두 합성 활성 필드를 명시 배치 | gas=False, brake=False | 실제 취소/브레이크/PCM 전이를 도출한 것이 아님 |
| 기존 valid-only | 활성 입력 유지, model 유효성만 False | gas=False | Start가 hold를 보존하는 다른 계약 |
| 자연 gasOverride | CarState.gas→원형 사건→StateMachine→Controls | 실제 메모리 gas 입력 존재 | planner가 어떤 시점의 gas·이전 CC를 같이 읽었는지에 따라 분기 가능 |
| 자연 brake/취소/PCM off | 별도 운전자·PCM 입력과 원형 상태 전이 | 가속 의도와 다름 | sd/CC 비활성과 C 권한 변화를 따로 확인. 재활성은 원형 PCM/입력 조건에 맡김 |

기존 부분 도구는 실제 MPC·LongControl을 실행했지만 전체 SelfdriveD/Controls가 활성 상태를 도출하지 않았고 Toyota CAN/C TX도 실행하지 않았다. 그 결과의 양수 LongControl을 실물 가속, ACC CAN, 안전 사고와 동일시할 수 없다. 500ms는 50ms 계획 틱 10개이며 실제 host scheduler 정지 500ms 실험도 아니다. 이 구분을 바꿔 기존 결과를 새 전체 벤치 결과처럼 소개하면 안 된다.

## 가속 시작 위상 0/10/20/30/40ms

다음은 건강한 활성 기준, DisengageOnAccelerator=0, 20Hz planner, 100Hz 호스트, gas 지속 500ms, **외부CS→card→planner→SelfdriveD→Controls** 순서에서의 소스상 예상이다. M0를 다음 모델 계획 정각으로 정의한다. 실제 trace가 조건을 충족했는지 확인하기 전에는 재현 결과로 부르면 안 된다.

| 시작 위상 | 첫 gas를 읽는 model 틱 | 그 model이 읽을 수 있는 CC.longActive | StartGuard 예상 분기 | Prepare 예상 분기 |
|---:|---|---|---|---|
| 0ms | M0 | 가속 전에 발행된 True | 새 gas=True와 enabled=True를 함께 읽어 driver_gas, cooldown 설정 가능 | gas를 읽어 cooldown 설정 후 부적격 reset |
| 10ms | M0+50ms | 앞선 100Hz override가 만든 False | enabled False reset이 gas보다 먼저, 그 호출에서 cooldown 신규 설정 없음 | enabled False여도 gas부터 처리해 cooldown 설정 |
| 20ms | M0+50ms | False | 위와 동일한 가능성 | 위와 동일 |
| 30ms | M0+50ms | False | 위와 동일한 가능성 | 위와 동일 |
| 40ms | M0+50ms | False | 위와 동일한 가능성 | 위와 동일 |

0ms 첫 호출 뒤에도 gasOverride는 CC.longActive를 False로 만들므로 이후 Start 호출에서는 disabled reset이 먼저일 수 있다. 이 reset은 이미 만든 cooldown을 지우지 않는다. 그 결과 Start의 마지막 억제 갱신 시각이 가속 시작 M0이고, Prepare는 가속을 관측한 이후 model 틱마다 갱신할 수 있다. ‘가속 해제부터 10초’라는 동일 타이머로 묶으면 안 된다.

위 500ms 지속/정각 조건에서는 Prepare의 마지막 gas 샘플은 0ms 시작에서 M0+450ms, 나머지에서 M0+500ms일 수 있다. Start는 0ms에서 M0+10초 억제 종료가 설정될 수 있고 다른 위상에서는 신규 억제가 없을 수 있다. 이미 이전 cooldown이 있는 경우에는 이 예측도 달라지므로 깨끗한 기준 상태와 기존 타이머를 기록해야 한다.

gas 해제 틱에도 새 CarState.gas=False와 **이전 CC.longActive=False**를 같이 읽을 수 있다. 이후 원형 Controls가 다시 True를 발행한 뒤 다음 모델이 이를 읽는 순서를 기록해야 한다. gas의 시작 위상만 바꾸고 해제 위상을 기록하지 않으면 확인 창·억제 시간을 혼동한다.

한 100Hz 틱의 짧은 gas는 20Hz planner가 아예 관측하지 못할 수 있다. 예를 들어 40ms 시작·50ms 해제는 모델이 gas=False이지만 이전 CC=False를 읽는 조건을 만들 수 있다. 이는 필요한 추가 대조 조건이며 이번 검토가 실제 실행했다고 주장하는 결과는 아니다. 실제 앱의 독립 프로세스 스케줄은 선택된 actor 순서와 다를 수 있다.

## 같은 물체·파일 전달·초록 해제 조건

Start.observe의 session 변경은 기존 hold를 지우지 않고 상자 앵커·frame/timestamp·확인 이력을 지운다. 새 session의 초록만으로 기존 빨강의 해제 권리를 이어받을 수 없으며 빨강 앵커를 다시 확보해야 한다(`signal_start_guard.py:101–138`). 반면 enabled False의 전체 reset은 hold까지 삭제한다. 이후 hold=False에서 모델 진행이 반영되는 현상과 ‘초록이 정상 확인되어 release=True’인 현상은 다르다.

상자는 IoU 0.6 이상 일치가 기준이고 초록 상자가 앵커를 주변 신호로 움직이지 못하게 한다. 빨강은 새 앵커를 잡을 수 있다. session을 매 프레임 새로 만들거나 색 변경 때 box/ID를 임의 교체하면 동일 물체 확인·해제 자격 자체가 바뀐다. 그런 조건을 정상 같은 신호의 빨강→초록 대조로 사용하면 안 된다.

Prepare는 session과 후보 track ID별 확인 이력을 사용한다. 후보 box는 매번 기하 필터를 거치지만 같은 synthetic ID를 붙인 것만으로 실제 같은 물체임이 입증되지는 않는다. 같은 ID 아래 다른 box를 넣거나 새 물체에 기존 확인 이력을 주면 검사가 전제한 물체 증거를 바꾼다. 이 synthetic 입력으로 실제 추적 식별 성능을 주장하면 안 된다.

메모리 파일 저장소·tmp 교체는 허용된 I/O 대체다. JSON 파서·크기 제한·writer·Runtime 반환을 그대로 실행하는지 확인해야 한다. `signal_order=before/after`는 planner가 읽을 관측을 한 번 늦출 수 있으므로 별도 축으로 표시한다. EOF, 발행·전달·read 시각, frame/session/box가 각각 같았는지를 기록해야 한다. 최신 파일을 반복 읽었다고 새 영상 증거가 늘어나는 것이 아니다.

## 전체 벤치에 필요한 대조군과 기록

각 조건은 원형 정상 준비→PCM 활성→신선한 빨강 hold 기준을 먼저 만족해야 한다. 상위 enabled/longActive를 수동으로 바꿔 기준을 맞추지 않는다. 필요한 비교는 다음과 같다.

- 끊김 없는 빨강·미확인·같은 앵커 초록의 정상 기준. 초록 확인 시간과 모델 자체 정지/진행 의도를 분리한다.
- 자연 gas 500ms의 시작 0/10/20/30/40ms, 해제 위상, 기존 cooldown 없는 기준. driver intent가 있는 결과를 기존 gas=False CC-only 23조건과 구분한다.
- 유효성만 깨진 입력과 자연 취소/브레이크/PCM off→on. 호스트 비활성 원인·C 권한·재활성 의도를 같은 종류로 묶지 않는다.
- 필요한 경우 한 틱 gas, 이전 cooldown이 남은 조건, 모델 정지 의도 조건. 호출 빈도를 높여 누락한 driver gas를 인위적으로 guard에 전달하지 않는다.
- session·box·ID를 그대로 둔 주 대조와 의도적으로 바꾼 별도 식별 대조. 관측 파일 before/after도 독립 비교로 유지한다.
- 움직이는 Prepare는 speed>5km/h·geometry valid·lead/model stopping/turning 없음의 자체 기준으로 확인한다. 정지 Start 시험의 Prepare 부적격과 섞지 않는다.

필수 trace는 실제 runtime read 시점의 sd.enabled/active, CC.enabled/longActive, CarState gas/brake/speed, context enabled/valid/drive, 관측 촬영·전달·read 시각, guard hold/anchor/session/pending/count/cooldown, Prepare active/history/cooldown/actuate, 계획 shouldStop/aTarget, LongControl 상태·출력, 새 CC와 이전 CC 적용, 생성 CAN과 C controls/longitudinal/TX 판정이다.

추적용 read wrapper는 원형 반환을 그대로 돌려주고 판단 함수를 추가 호출하거나 context를 바꾸지 않아야 한다. driver gas/brake가 들어온 첫 틱의 이전 비영 ACC가 C에서 거부되는 것은 기대 거부로 분리한다. C에서 새 메시지를 거부했다는 결과가 이미 차량에 전송된 명령의 물리 유지 시간까지 검증한 것은 아니다.

## 결론

소스에서 확인된 분기·actor 순서 차이를 재현 가능한 조건으로 정리했다. 아직 전체 자연 gas 위상의 실행 결과를 확인한 것이 아니며 생산 코드를 수정할 결함으로 확정하지 않았다. 억제 타이머와 빨강 정지 기억은 운전자 의도 정책을 포함하므로 부분 CC-only 반례를 그대로 자연 운전 원인으로 삼으면 안 된다.

이 자료는 실제 영상/인식·동일 신호 귀속·ECU 응답·PCS/AEB·회생 제동·독립 MCU·ARS live·실물 가속을 검증하지 않는다. 한국어 읽기 보고서 한 파일만 추가했으며 허용 범위 밖 HANDOFF와 기존 결과는 수정하지 않았다.
