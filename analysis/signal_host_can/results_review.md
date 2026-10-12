# 신호 호스트·CAN 보존 결과의 독립 검토

같은 500ms 가속 입력과 빨강 신호 입력에서도 모델 갱신 위상에 따라 **신호 출발금지 기능의 복귀 기간이 달라지는 소프트웨어 동작**이 보존 결과에서 확인된다. 0ms와 10ms 조건의 Runtime 입력·억제 타이머·정지 기억·허용된 생성 CAN을 직접 대조했고 소스의 분기 순서와 일치했다. 이를 실제 차량의 이동·충돌 위험량 또는 어떤 복귀 정책이 정답이라는 결론으로 확대하면 안 된다.

이번 검토는 새 실행을 하지 않은 **보존 결과 읽기 감사**다. `RESULTS_KO.md`, `frozen_results.json`, 초기 실패와 수정 결과, 대표 전이 8개 및 moving 2개의 상세 JSON을 읽었다. 상세 10파일의 manifest 해시와 실제 파일이 일치했고, 객체/호스트 행에서 양수 허용 CAN 등의 개수를 따로 계산했다. source·helper·결과·바이너리는 수정하지 않았으며 이 문서만 추가했다.

root가 별도로 gas0/gas10/moving2를 독립 복사 재실행해 exit0·양수 허용 CAN 114 대 5·정지 기억 재획득 104.20초·Prepare 485틱을 확인했다고 전달했다. 이는 root의 대표 3조건 재실행이다. 검토자가 33조건을 새로 실행했다거나 전체 31전이를 한 번 더 실행했다는 뜻은 아니다.

## 읽은 결과 묶음

| 파일 | SHA-256 |
|---|---|
| RESULTS_KO.md | `a34ad9eb7bd995445d82f2341d1b33cfae3b183d5864a512bb478c838b642c7f` |
| frozen_results.json | `7b9fcd747644ad3983224413408b55c42450d1609ca13db2e545782e1cc3c88b` |
| evidence_manifest.json | `34d0c98bee68ddce7ceb2685cd7671d74bf89fe1b9398fb884a35acc0d8916d7` |

저장소의 StartGuard/Prepare/StateMachine/Controls/C TX 조건과 대조했다. StartGuard 원형 해시는 `f3ce89f60a7527f94075f0c470dd59e235a65f4ec621512416f3a5f12f171f10`, Prepare는 `f5c206efc2b4ff7d676d06ec4da558a3fe5b0f4901a56a920fa0ee193ee32c39`, C safety.h는 `264acef46827c278c8a741106506506323ec27842eaf21856a16386ebe084dfe`로 보존 결과의 값과 같았다. 새 정책을 적용한 소스의 결과가 아니다.

고정 요약의 전이 31조건·moving 2조건은 총 33관찰이다. 현재 전이 429개 판정·baseline 17개·moving 18개의 실패는 0으로 기록되었다. 최초 전이 실행에는 invalid_can 기대 오류 1개가 있었고, 해당 조건만 새 기대 조건으로 재실행했다. 초기 오류는 보존되어 있다. 나머지 30조건의 기존 직접 결과와 수정된 1조건을 합친 현재 기록이다.

이 판정 수는 소스 불변·정상 권한·DBC·체크섬·기대 C 거부 등 정의한 조건의 결과다. **모든 빨강 조건에서 양수 출력이 없다는 판정을 통과한 것이 아니다.** 가속 이후의 양수 출력은 관찰 항목으로 따로 기록되어 있다.

## 500ms 가속 위상의 확정 관찰

아래 시각은 실제 로그나 장치 절대 시각이 아닌 합성 시계다. 가속 기준 시작은 103.50초, 계획은 20Hz, 호스트/CC는 100Hz, C 판정은 생성 메시지마다 실행한다. 각 조건은 동일한 정상 활성·빨강 정지 기준 뒤 시작했다.

| 가속 위상 | 첫 Runtime read에서 읽은 조합 | Start 억제 종료 | 빨강 정지 기억 복구 | C 허용 양수 CAN |
|---:|---|---|---|---:|
| 0ms | sd.enabled=True, CC.enabled=True, **CC.longActive=True**, gas=True | 113.50초 | 4초 관찰 창 안에서 없음 | 114개 |
| 10ms | sd.enabled=True, CC.enabled=True, **CC.longActive=False**, gas=True | 미설정 | 104.20초 | 5개 |
| 20ms | 10ms와 같은 분기 조합 | 미설정 | 104.20초 | 5개 |
| 30ms | 10ms와 같은 분기 조합 | 미설정 | 104.20초 | 5개 |
| 40ms | 10ms와 같은 분기 조합 | 미설정 | 104.20초 | 5개 |

0ms와 10ms 상세 JSON에서 위 첫 read·타이머·CAN 개수를 직접 확인했다. 20/30/40ms 및 before/after의 같은 분포는 고정 요약과 대조했다. 0ms는 400개 호스트 행 전부 hold=False였고, 10ms는 65개 행이 hold=False였다. 10ms 조건에서 가속 해제 뒤 첫 새 모델 read 104.05초부터 104.20초까지는 150ms 재확인 창이다. 가속 해제 입력 자체 104.01초부터의 차이는 190ms이므로 ‘150ms’의 기준점을 혼동하지 않아야 한다.

소스는 StartGuard에서 `not enabled or not drive`를 gas보다 먼저 검사한다(`signal_start_guard.py:145–153`). Runtime의 enabled는 설정 활성·sd.enabled·CC.longActive의 조합이다(`signal_assist_runtime.py:79`). 0ms는 새 gas와 이전 활성 CC를 읽고 driver_gas를 처리한다. 다른 위상은 앞선 호스트 틱이 만든 CC.longActive=False를 먼저 읽어 disabled reset으로 반환한다. 같은 운전자 입력에 대해 읽는 순서가 달라진 원인이 trace와 소스에서 연결된다.

10초 cooldown은 출발 금지 시간이 아니라 **신호 보조의 운전자 override 억제 시간**이다. 이 기간의 StartDecision은 hold=False다. 따라서 0ms의 114개를 ‘10초 정지 보장이 실패했다’고 부르면 잘못된 정책 해석이다. 동시에 같은 입력에서 114 대 5로 달라진 복귀 행동은 스케줄 위상에 의존하는 명확한 관찰이다.

첫 양수 LongControl은 두 대표 조건 모두 104.05초이고 첫 C 허용 양수 CAN은 104.08초였다. 입력→모델 판단→LongControl→이전 CC 적용→Toyota 생성→C 허용을 같은 시각으로 합치면 안 된다. 가속 중 C longitudinal_allowed는 False이며 해제 뒤 권한이 정상 복구하면 C는 신호색을 해석하지 않고 허용 범위의 명령을 받아들인다.

가스0의 억제 종료 113.50초까지 실행한 결과는 아니다. 관찰은 103.50~107.49초의 4초 창이다. 10초 전 기간의 출력이나 그 뒤 동작, 영구적인 정지 기억 소실까지 확인한 것으로 보고하면 안 된다.

## 대조군이 제한하는 해석

| 대조 조건 | 상세 기록에서 확인한 결과 | 의미 |
|---|---|---|
| 같은 앵커 green, 파일 before | release 104.20초, 첫 양수 LoC 104.75초, 첫 허용 양수 CAN 104.89초 | 초록이 신호 출발금지만 해제하고 명시한 모델 진행 입력·기존 제어가 이후 출력을 생성 |
| 같은 앵커 green, 파일 after | release 104.25초, 첫 양수 LoC 104.80초, 첫 허용 양수 CAN 104.95초 | 파일 read 순서로 release/LoC는 50ms, CAN은 원형 주기/보정 경계에서 60ms 차이 |
| 40ms 시작·10ms gas pulse | 실제 gas 호스트 1틱, Start gas read 0회. hold 103.55초 소실→103.75초 복구. 양수 LoC/CAN 0 | 정지 기억 소실만으로 양수 출력을 단정할 수 없다는 반례 |
| red/unknown/오래된 관측/파일 중단 | 요약의 before/after에서 hold 유지·양수 0 | enabled 유지 중 unknown/stale만으로 정지 기억을 해제하는 일반 결함으로 확대하지 않음 |
| 새 session green | 기존 hold 유지·양수 0 | session 변경의 해제 앵커 reset과 enabled False의 전체 reset은 다름 |

10ms pulse의 경우 planner가 실제 gas=True를 보지 않았지만 이전 CC=False를 읽었다. 기존 정지 카운터 등이 재획득 창을 덮은 기록과 일치한다. 이 한 조건이 모든 짧은 입력/차량 상태에서 안전함을 보장하지는 않으며, 500ms 조건의 반례를 무효화하지도 않는다.

## invalid_can의 최초 기대 오류

최초 실패는 `start_preserves_hold_when_valid_false`였다. 부분 valid-only 실험의 ‘상위 enabled를 유지하면서 valid만 False’라는 기대를 전체 host의 4초 구간에 적용한 오류다.

수정된 상세 기록의 103.50초 첫 planner read는 이전 sd/CC 활성과 새 canValid=False를 함께 읽어 context enabled=True/valid=False이고 hold=True를 보존한다. 같은 틱의 호스트는 원형 canError 사건으로 enabled/active/longActive를 False로 만든다. 원형 events.py의 canError는 IMMEDIATE_DISABLE이며 StateMachine은 이를 즉시 반영한다. 103.55초 다음 모델은 disabled context를 읽어 hold를 reset한다. 양수 LoC/CAN은 0이다.

따라서 이 기대 정정은 원형 결함을 고친 핫픽스가 아니다. production source 변경도 없다. 입력은 CarState.canValid=False이며 C에는 별도의 정상 합성 RX를 계속 제공하므로 실제 CAN checksum/버스/MCU 실패를 재현했다고 해석하면 안 된다. 최초 실패·설명·수정 결과를 모두 보존한 보고는 적절하다.

## DM soft/hard와 권한

보존 DM soft 기록에서 103.95초 softDisabling은 enabled=True, active=True, CC.longActive=True, hold=True였다. 이는 원형 ACTIVE_STATES/ENABLED_STATES에 softDisabling이 포함된 정책과 일치한다. softDisable을 CC-only False와 같은 입력으로 취급하면 안 된다.

DM hard 기록은 같은 soft 전이 뒤 106.95초 disabled가 되어 enabled/active/longActive=False였다. 그 틱의 마지막 신호 판단은 아직 이전 model read이므로 hold=True가 남아 있고, 다음 107.00초 model read에서 disabled reset이 실행됐다. 실제 건강 복구 뒤 명시한 PCM off/on으로 재시작한 이후 양수 허용 CAN 5개가 관찰된다. 이 재시작을 가속 release와 같은 driver intent로 합치지 않아야 한다.

모델/계획 중단에서는 판단 함수가 그 틱에 호출되지 않을 수도 있다. lastcontext·lastdecision을 새 판단 결과로 표시하면 안 된다. 기록의 `guard_decision_this_tick`과 runtime call 시각을 사용해 source 실행 여부를 구분해야 한다.

## 모델 취득 표식 2초 대조의 범위

moving0/2 상세 JSON에서 각각 750개 호스트 행 중 Prepare active 485개, healthy+enabled Prepare read 109개, 최소 plan/LongControl -0.5m/s²를 직접 다시 집계했다. 원본 JSON 값과 일치했고 두 상세 파일도 manifest와 일치했다.

old2 조건에서는 Runtime read 시 모델 EOF의 선언된 나이가 약 2초지만 model header·수신은 신선하고, 신호 관측 EOF·자세·보정·합성 기하 입력도 신선한 조건으로 구성된다. event 생성 함수의 model_age는 EOF뿐 아니라 frameId도 과거 origin으로 만든다. **문자 그대로 EOF 한 필드만 바꾼 검사가 아니다.**

모델 배열·미래 진행 궤적은 같은 합성 계산으로 구성했다. 실제 2초 전에 촬영한 영상·차선·거리 추정을 가져오거나 2초의 차량 이동을 적분한 것이 아니다. 모델 producer의 실제 frameAge/frameDrop·실행 지연·카메라 버퍼 조합이나 실제 geometry가 2초 오래된 상황은 이 자료로 입증되지 않는다.

현재 Runtime은 모델의 seen/valid/alive/수신 나이와 내용 EOF 나이를 같은 판정으로 검사하지 않는다. Prepare는 관측·pose·camera metadata 나이를 별도로 검사한다. 그래서 이 명시한 취득 표식 대조를 통과한 것은 소스와 일치한다. 2초 오래된 실물 geometry가 안전하다는 증거도, 실제 장치에서 이 조합이 발생했다는 증거도 아니다. 임의 200ms cutoff를 새 생산 정책의 검증된 값으로 선택할 근거로 사용할 수 없다.

## C 검사·통과 수의 의미

고정 요약은 전이 CAN 25,918개와 moving CAN 2,718개, C 기대 불일치·권한 변이 0, 실제/기대 거부 각각 6개를 기록한다. 메시지 버스·길이, LKA torque0/LTA 비작동, 정의된 체크섬만의 검사 범위를 명시했다. 이 검토가 전체 모든 메시지의 C 실행을 다시 한 것은 아니다.

가속 입력 첫 틱의 이전 비영 ACC 거부는 예상 거부이며 검사 실패가 아니다. 가속 해제 후 양수 명령이 허용되는 것은 C가 기존 longitudinal 권한·수치 범위를 검사한 결과다. C 허용을 빨강 판단의 타당성, PCS/AEB 보존, 실제 ECU 응답 또는 실차 위험 제거로 해석하면 안 된다.

## 핫픽스 선택에 대한 판단

현재 근거는 **동일한 운전자 입력에서 Start의 gas 처리 여부가 스케줄 위상에 따라 바뀐다**는 행동 차이와 그 생성 CAN까지의 영향을 확인하기에 충분하다. 하지만 아래 정책 중 어느 것이 맞는지는 그 수치만으로 정해지지 않는다.

| 변경 방향 | 바꾸게 되는 의미 | 현재 부족한 확인 |
|---|---|---|
| 기존 10초 driver override 억제를 모든 위상에서 동일하게 적용 | 10~40ms도 0ms처럼 빨강 veto 복귀를 늦출 수 있음. 억제 처리 순서를 일관되게 하는 후보 | 설정 OFF·disengaged·CAN 무효·drive 아닌 상태와 gas를 어떻게 구분할지, 억제 시작/끝 시점, 짧은 pulse·긴 gas·재활성 회귀 |
| 비활성 후 기존 빨강 기억을 보존 | 가속 뒤 즉시 빨강 제한을 되살리거나 cancel/재시작 의미까지 바꿀 수 있음 | 운전자가 직접 진행한 후 같은 신호/정지 상황인지, 새 session·이동·정상 green 해제·driver override와의 충돌 |
| 모든 비활성/복귀에서 새로운 출발금지나 시간 차단을 부여 | 현재 모델/PCM 재시작 정책까지 새로 제한 | 실제 수신/취득 시계·독립 장치·복귀 의도·다른 차량/모드 범위의 근거 |

단순히 gas 분기를 앞으로 옮기는 후보도 모든 비활성 원인을 동일하게 취급하면 기존 정책 범위를 넓힌다. 20Hz가 보지 못한 10ms pulse는 그 재배치만으로 처리되지 않는다. 반대로 hold를 전부 보존하면 정상적인 driver override·수동 진행 이후의 다른 상황에서 이전 신호의 제한을 이어갈 수 있다. 기존 데이터는 그 물리 상황을 검증하지 않았다.

따라서 현재 r7에선 새로운 정책을 선택하거나 안전성이 검증된 핫픽스라고 공개하는 대신, 확정한 위상 의존과 driver intent 범위·반례를 그대로 보고하는 판단이 적절하다. 향후 수정은 명확히 선택한 복귀 계약을 기준으로 기존 red/green/unknown·gas 5위상·짧은 pulse·cancel/brake/PCM재시작·DM·invalid·Mode0/1/2·새 session 대조에서 비교해야 한다. 새 정책의 검사가 끝나기 전에는 기존 검사 통과 수를 그 핫픽스의 성과로 쓰면 안 된다.

실제 영상/신호 귀속·커널 시계·Toyota 수신 firmware·ECU/GVC/브레이크/모터 반응·MCU heartbeat·차량 이동·회생·PCS/AEB·ARS live·Konik 운영 빌드는 여전히 미검증이다. Source63/patch8을 변경하지 않았고 허용 범위 밖 HANDOFF도 수정하지 않았다.
