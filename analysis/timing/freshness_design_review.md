# 모델·계획 자료 나이의 책임 경계 읽기 검토

정규 주기로 도착한다는 사실과 모델이 관측한 장면이 최신이라는 사실은 현재 코드에서 별도 조건이다. 기본 호스트 경로는 주로 수신 간격·평균 주파수·valid·프로세스 지연을 확인하며, 원래 영상 EOF나 producer 헤더의 나이를 보통 종방향 요청의 허용 조건으로 끝까지 연결하지 않는다. 그래서 보존된 호스트 검사에서 획득 시각 또는 모델 헤더가4초 오래된 자료를 정규 수신해도 longActive가 유지된 결과는 읽은 소스와 일치한다.

이 단계는 읽기 검토다. 새 실행·코어/동결 helper/원본 JSON/native 바이너리 변경은 없고 이 문서만 작성했다. 아래30조건 수치는 다른 담당자가 직접 실행해 보존한 `work/timing_rootcause/whole_cases_summary.json` 및 각 `result.json`을 읽은 결과이며, 이 검토자가 새로 재실행한 결과로 보고하지 않는다. SignalAssistMode2 부분 검사와 SignalAssistMode0 기본 호스트 검사는 구분한다. 차량 연결·원본 영상·현장 소음/보정·ECU/Panda의 독립 동작 및 PCS/AEB 보존은 검증되지 않았다.

## 시각을 먼저 구분해야 하는 이유

| 시각 | 뜻 | 현재 확인한 출처 |
|---|---|---|
| 카메라 SOF/EOF | 센서가 획득한 장면의 시각. EOF는 SOF+센서 readout | `system/camerad/cameras/spectra.cc:232`의 SOF_BOOT_TS, `:1573`의 EOF 계산 |
| modelV2.logMonoTime | 추론 이후 Python 메시지를 생성한 producer 시각 | `selfdrive/modeld/modeld.py:505`, `cereal/messaging/__init__.py:45` |
| modelV2.timestampEof | 모델이 사용한 영상의 획득 시각 | `selfdrive/modeld/fill_model_msg.py:86` |
| SubMaster.recv_time/recv_frame | receiver가 마지막으로 메시지를 받은 시각/자기 반복 번호 | `cereal/messaging/__init__.py:265` |
| plan.modelMonoTime | 그 계획이 참조하는 모델 producer 헤더 | `controls/lib/longitudinal_planner.py:470` |
| plan.logMonoTime | 계획 producer의 새 발행 시각 | `longitudinal_planner.py:465`, `messaging/__init__.py:45` |
| plan.processingDelay | 계획 헤더−참조 모델 헤더. capture-to-control 총지연이 아님 | `longitudinal_planner.py:472` |
| Controls의 t_since_plan | `(receiver.frame−plan.recv_frame)×DT_CTRL` | `controls/controlsd.py:178` |

Python modelV2 producer와 계획 producer는 현재 소스상 둘 다 `time.monotonic()`으로 헤더를 만든다. 이 정상 Python 경로의 `plan.modelMonoTime`도 modelV2의 동일 헤더를 그대로 복사하므로 같은 시계 영역이다. 다만 replay/다른 producer/장치 빌드까지 같은 계약이라는 일반화는 금지한다. `plan.modelMonoTime`은 EOF가 아니다.

## 현재 판정은 어디에서 무엇을 책임지는가

| 단계/담당 | 현재 확인하는 것 | 확인하지 않는 연결/주의점 | 정확한 소스 |
|---|---|---|---|
| modeld producer | frame drop, 모델 실행/보정 유효성. EOF를 결과에 보존하고 camera_age를 진단 | action의 지연 보상은 명목50ms+25ms 및 장치 지연 설정이다. `camera_age_at_run_ms`를 임의 나이 차단으로 쓰는 경로를 읽은 구간에서 찾지 못함. 새 헤더가 오래된 EOF를 최신으로 바꾸지 않음 | `modeld/modeld.py:466`, `:477`, `:521`; `fill_model_msg.py:77` |
| 각 SubMaster receiver | seen/valid, 마지막 수신에서의 alive, 수신 평균 주파수 | alive는 producer 헤더나 영상 획득 나이 검사와 다름. 계속 오래된 메시지가 와도 recv_time은 새 값 | `cereal/messaging/__init__.py:255`, `:265`, `:274`, `:287` |
| SERVICE_LIST | modelV2와longitudinalPlan 명목20Hz,carControl100Hz. 원형 alive=`나이<10/frequency` | 모델/계획 수신 약500ms와 CC 수신100ms는 서로 다른 서비스 계약이다. plan 주파수 허용 범위14~25Hz와 명목 alive 계산을 구분 | `cereal/services.py:57`, `:61`, `:87`; `messaging/__init__.py:275` |
| plannerd Toyota 진입 | modelV2 updated/seen 및 producer 헤더의25ms 최소 간격 | 수신/진입시각이 오래된 원본 내용의 나이를 대신하지 않음. Hyundai liveTracks의100ms 경로를 Toyota의 계약으로 적용하면 안 됨 | `controls/plannerd.py:24`, `:99`, `:103`, `:107` |
| LongitudinalPlanner 발행 | carState/controlsState/selfdriveState의all_checks, solver/실행시간 진단, modelMonoTime 보존 | plan.valid 식에 modelV2/radarState를 직접 넣지 않음. processingDelay를 저장해도 소비자가 이를 차단 조건으로 쓰지 않으면 권한 효과 없음 | `controls/lib/longitudinal_planner.py:467`, `:470`, `:472` |
| selfdrived health/events | 서비스 alive/frequency/valid, 프로세스 상태, Ratekeeper.lagging, model frameDropPerc | 정상 주기로 오는 old header/body는 수신 건강을 만족할 수 있음. 초기화/모델 settling/ignore 목록의 예외를 함께 봐야 함 | `selfdrived/selfdrived.py:427`, `:463`, `:544`; `:89`의ignore 설정 |
| StateMachine | commIssue/AvgFreq/modeldLagging/selfdrivedLagging의SOFT_DISABLE 및 NO_ENTRY. 지속시 명목3초 후 비활성 | softDisabling은 enabled/active 상태다.3초는 DT_CTRL 반복 카운터여서 전체 host pause의 벽시계와 다름. user/immediate disable은 우선 | `selfdrived/events.py:920`, `:924`, `:929`, `:953`; `selfdrived/state.py:7`, `:9`, `:43`, `:109` |
| Controls.state_control | CC.longActive=`selfdriveState.enabled && !overrideLongitudinal && CP.openpilotLongitudinalControl` | 이 식은 active가 아니라enabled를 쓴다. plan.valid/processingDelay/modelMonoTime/EOF 나이를 직접 허용 조건으로 쓰는 경로를 읽은 메서드에서 찾지 못함 | `controls/controlsd.py:160`, `:178`, `:183` |
| LongControl | 활성, aTarget/vTargetNow/shouldStop, 상태/램프/출력 한계 | t_since_plan의200ms 조건은 coasting 완화에만 사용. 보통 요청에는 같은 직접 나이 차단이 없음. 단독 active=True 결과를 전체 앱 권한 증거로 쓰면 안 됨 | `controls/lib/longcontrol.py:133`, `:159`, `:183`, `:198` |
| Controls 발행 | 새 controlsState/CC 헤더, valid=CS.canValid, controlsState에plan 헤더 기록 | 새 CC 헤더가 원본 영상/계획의 나이를 알려주지 않음. 소스TODO도all_checks 순환 의존성을 언급 | `controls/controlsd.py:420`, `:425`, `:429`, `:453` |
| card 적용 경계 | carControl all_alive, 별도 reboot/lateral startup 조건 | carControl.valid/freq_ok는 이 적용 조건에 직접 포함되지 않음. model/radar가invalid/dead면None 전달하지만 CC의 원래 plan/영상 나이는 별도 전달되지 않음 | `car/card.py:351`, `:373`, `:375` |
| CarController/Panda | 차량별 명령 한계·주기·운전자/ACC·RX 건강 등 다른 안전 계층 | 일반 Toyota CAN 명령은 원래 camera/model/plan 시각을 담지 않는다. Panda가 모델 획득 나이를 확인했다고 보고할 수 없음 | `opendbc_repo/opendbc/car/toyota/carcontroller.py`, `opendbc_repo/opendbc/safety/safety_toyota.h` |

softDisabling에서 Controls가 `forceDecel`을 발행하고 planner가 이를 소비하는 기존 경로도 있다(`controlsd.py:436`, `longitudinal_planner.py:163`, `:224`). 그러나 모델이 중단해 Toyota 계획 진입이 없는 상황에는 새 planner 결과를 당연히 받을 수 있다고 가정할 수 없다. 권한 해제와 감속 요청을 어느 단계가 책임지고 실제 마지막 소비자까지 전달하는지를 별도로 확인해야 한다.

## 보존된30조건의 읽은 결과

summary에는30/30 returncode0·source_unchanged=true·정상 비활성→정상enable baseline longActive=true가 기록돼 있다. returncode0은 도구 완료이며 아래 모든 fault가 안전하게 즉시 차단됐다는 뜻이 아니다. SignalAssistMode0 조건은 부모가 명시한 기본 host 검사 범위와 기본 `params_keys.h:282` 및 helper 경로로 확인한다. 일부 보존된 개별 JSON에는 SignalAssistMode 설정 열이 없어 그 파일만으로 장치 설정을 새로 측정했다고 주장하지 않는다.

| 입력 | 읽은 보존 결과 | 경계/한계 |
|---|---|---|
| 정규20Hz 수신, EOF4초 과거, producer 헤더 새 값(no_drop_4000ms) | 첫 fault EOF age4s/header age0/processingDelay0, plan.valid/longActive true.80행(103.50~104.29)의 관측 끝도longActive true | 지연값4초는 자료 나이이고 관측 창은 약0.8초다.4초 동안 실차가 활성이라는 주장이 아님. 합성 원본 시각을 늦춘 연속 stream이며 실제 영상/움직이는 객체 입력 아님 |
| 정규 수신, producer 헤더까지4초 과거(delayed_message_4000ms) | 첫 fault EOF/header age4s, plan.processingDelay4s, receive age0, plan.valid/longActive true.동일80행 끝도true | receive-time 기반alive가 만족하고 processingDelay가 직접 권한 차단에 쓰이지 않는 것과 일치 |
| model 또는plan 송신만600ms 중단 | commIssue·softDisabling 기록, 관측 창에서first long inactive는없음 |500ms 수신 기준 이후에도 기존 soft-disable 유예가 있으므로 즉시 해제로 해석하지 않음 |
| model 또는plan 송신4초 중단 | fault 시작103.50,첫softDisabling103.95,첫longInactive106.95.최종disabled/출력0 | 이 fixture에서 약0.45초 건강 검출+명목3초 카운터와 일치한다. 정확한 실차 반응시간 아님 |
| whole host 판단 loop4초 중단 후 재개 | 재개107.50부터fresh 입력, cameraFrameRate/selfdrivedLagging/systemReady 기록.400행 끝111.49는enabled/longActive true,firstInactive없음 | 중단 기간에는호스트판정이진행하지않는다.재개 후 fault 회복은 지속fault의3초 카운터와 다름. 독립 MCU/heartbeat/실물 차량 운동 미실행 |
| cancel/gas/brake | 세323ms 비교에서firstLongInactive103.50,각기buttonCancel/pcmDisable·gasPressedOverride·pedalPressed | 운전자 경로가 반례 없이 보존됐는지 향후 guard에서도 비교 필요. 새 실차/Panda 검사 아님 |

## SignalAssistMode2와 이 결과가 충돌하지 않는 이유

앞서 직접 수행한 부분 신호 bench는 actual SignalPrepareRuntime/StartGuard/planner/MPC/LongControl을 실행했지만 host 전체 enabled를 도출한 시험은 아니었다. mode2 정상 context를 먼저 확인한 뒤 자료를 보존하고 실제 현재 시각을323ms 전진시키면 runtime context가 거절되는 것을 관측했다. 고정 ReplayClock은 실제 CPU/대기 지연을 자료 나이에 전달하지 못하므로 그 경우를 따로 보존했다.

원형 moving prepare는 관측 timestamp age200ms/간격250ms(`signal_stop_prepare.py:215`, `:259`), 기반 서비스 수신250ms(`signal_assist_runtime.py:77`), pose 수신/자료200ms 및 camera 수신250ms(`signal_stop_prepare_runtime.py:97`, `:108`)를 검사한다. 최종 prepare 적용에는 호출 elapsed<=200ms가 별도 있다(`longitudinal_planner.py:398`). 이 조건은 완만한 신호 감속 보조를 허용/해제하며 기본 model/planner/CC 전체 권한의 TTL로 정의돼 있지 않다.

정지 red hold는 다른 목적이다. 관측650ms·동일 물체 확인을 사용하고, unknown/stale/invalid/시계 역행은 기존hold를 보존한다(`signal_start_guard.py:58`, `:97`, `:154`, `:163`). enabled=false나잘못된gear는reset한다(`:145`),gas는운전자 정책으로reset/cooldown한다(`:149`). 모든 오래된 자료를 하나의200ms 기준으로 해제하면 현재red-hold 보존 조건을 약화시킬 수 있다. 사진의 색/차로 의미와 안전성은 이 논리 검사로 입증되지 않는다.

## BOOTTIME/MONOTONIC의 위험과 필요한 증거

C++ 카메라 EOF 및 메시지 헤더는 `CLOCK_BOOTTIME` 기반이다(`common/timing.h:12`, `cereal/messaging/messaging.h:49`). Python 헤더는 `time.monotonic()`이다. Linux의MONOTONIC은suspend 동안멈추고BOOTTIME은suspend를포함한다. 따라서 source clock을확인하지않고EOF_BOOTTIME을Python 현재시각에서빼면resume 후fresh EOF가미래로보이는등의오류가가능하다. 이것은소스/API 의미에서추론한위험이며Konik에서발생했다고새로측정한결과가아니다. [Linux 커널 시간 문서](https://docs.kernel.org/core-api/timekeeping.html), [Python3.12 시간 문서](https://docs.python.org/3.12/library/time.html#time.CLOCK_BOOTTIME).

WSL에서clock 차이가 작았던보존관측도실제장치의Python 빌드·절전이력·다른프로세스epoch를증명하지않는다. 현재장치에서`get_clock_info('monotonic').implementation`,동일시점BOOT/MONO 샘플의불확실도·resume 전후차이·프로세스restart/route boundary를수신전용으로확인할필요가있다. Python의절대기준은일반적으로정의되지않으므로다른clock의원점을함부로같다고보면안된다. [Python3.12 monotonic 문서](https://docs.python.org/3.12/library/time.html#time.monotonic).

이 위험을 이유로 전체 clock을 바꾸거나 EOF 나이를0으로 clamp하거나 invalid를fresh로재분류하면 안 된다. 먼저 clock 출처/원점/단위/획득·발행·수신 역할을 명시해야 한다. 특히MONOTONIC model/plan 헤더만의 검사는BOOTTIME EOF 검사를 해결한 것으로 광고할 수 없다.

## 제안된 exact RAV4 직접 종방향 header guard의 검토

부모의 좁은 제안은 exact RAV42022·직접 종방향에 한정해, 현재 `SERVICE_LIST`/SubMaster20Hz의`10/frequency` 생존 기준을 수신 나이 외에 Python model producer 헤더·plan 헤더·plan.modelMonoTime 나이에도 확인하자는 것이다. 현재 정상 Python source 경로라면 세 시각의영역이MONOTONIC이므로EOF−MONOTONIC 혼합을피한다는점은타당하다. 임의의새숫자나신호200ms 기준을기본제어로확대하는안이아니다.

그러나 수신 건강의10주기 정책을 곧바로 actuator freshness 정책으로 동일시하는 것은 별도 설계 결정이다. 기존 의미를 명확히 문서화하고 실제 소비 경계·상태 복원과 아래 반례를 확인해야 한다. 이 읽기 검토는 guard를 구현/승인/실차 활성화하지 않는다. fresh header+old EOF4초 사례는 이안으로 해결되지 않는다.

| 고려 항목/반례 | 필요한 판단·추가 근거 |
|---|---|
| exact scope | Toyota brand+정확한2022 식별자+OP longitudinal 조건을 명시. stock-long/다른Toyota/다른제조사 정상CAN·운전자 동작을 보존. 실물 차량 식별/firmware/설정 검증과 구분 |
| 참조=최신model 즉시동일 조건 | 정상20Hz 모델이 먼저 도착하고 MPC/plan이늦게도착하는10~수십ms 동안oldplan은아직신선하다. 즉시동일을요구하면주기적으로CC가꺼지고LoC/PID가reset될수있다. known model참조이력·인과순서와latest 값동일을구분 |
| plan 참조가 consumer 최신model보다앞서는 경우 | 서로다른conflated socket 읽기순서 때문에plan이 먼저 보이고관련model이다음update에보일수있다. 단순`ref>latest`를비정상으로확정하지말고원형 메시지순서/캐시이력 재현 |
| ref=0/future/invalid/명백한인과모순 | 정상producer의동일MONOTONIC 계약에서`modelRef<=planHeader<=now` 및valid/seen/clock 건전성을검토할수있다. positive참조라도어떤body를실제로사용했는지는시간값만으로증명되지않는다. replay·route restart·정확히경계 시각·정수ns/float 오차를별도시험 |
| model/plan/current CC 값의관계 | 새CC가oldplan 요청을복사할때CC.header만보면나이가새것처럼보인다. 실제참조와원본시각을계획/제어 소비자까지연결해야한다. latest model EOF를oldplan에붙이면자료를부당하게젊게만든다 |
| plan.valid=false만강화 | Controls와card의현재조건이같은방식으로valid를차단하지않으므로producervalid 변경만으로마지막적용을막았다고말할수없다. 반대로모든all_checks를강제하면소스TODO의순환의존성 및초기화경로가문제 |
| local CC.longActive 차단과3초soft disable | 기존유예를우회하는새국소권한정책이다. SelfdriveState.enabled를유지한채CC만꺼졌다다시켜지는경우LoC.reset/starting/stopping·재출발·코스팅·최종정규CAN/PID잔여상태를확인. 추가 주기외 CAN으로실패를가리지않음 |
| red hold reset(현재 읽기에서 추론한 반례) | Runtime.enabled는sd.enabled AND cc.longActive. guard가CC를false로만들면StartGuard.update(enabled=False)가held red를reset할수있다. 이후fresh자동복귀 때unknown/green/red와확인전양수요청을부분신호bench로직접확인해야한다. valid=false 시hold보존과enabled=false reset을혼동하지않음 |
| 운전자개입 | gas/brake/cancel/overrideLongitudinal 기존우선순위와이미받은CC/재개 첫틱을검사. invalidclock이나freshness복귀가운전자해제를뒤집어재활성화하면안됨 |
| forward recovery와clock 문제 | producer restart·신규epoch·queue역전·header미래·스케줄링지연·일시회복에대한거절/재개조건명시. BOOT EOF를같은MONO 기준으로검사하지않음 |

보강 후보 책임 위치는 producer의획득 유효성, planner의참조/발행 유효성, Controls의실제요청사용 경계, card의최종적용 경계다. 모든 위치에동일guard를복사하는것보다각자가소유하는시각과권한을정의해야한다. 소프트경고/무효자료의판정과재활성화상태를연결하고, 센서정지·계획정지·late delivery·새header/oldEOF·clock불일치를 각각검증한뒤 소유권을받아코드후보를작성할수있다.

## 현재 완료와 미완료

완료: 요청한30조건 보존결과 및원형source의판정경계를읽었고, 같은MONOTONIC header guard의가능범위와정상비동기참조·red-hold reset·복귀 반례를정리했다. Linux/Python 공식시간규약도확인했다. 이문서외write는없다.

미완료: proposed guard 실제구현/회귀, red-hold reset의이번부분bench 직접재현, 실제장치시계/캡처-추론-계획-CC-card 분포,실물인식/ECU/Panda독립정지·heartbeat·PCS/AEB 안전성. 4초늦은정규자료가호스트판정을통과한사실과실차가그대로4초주행했다는주장은구분한다. 과거검사기의322.9ms 원인도이읽기검토로확정하지않는다.
