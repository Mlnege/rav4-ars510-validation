# 레이더 선행차 소실과 정지·재출발 연결 조사

첫 근거리 모의 사례의 핵심은 **레이더 점이 완전히 사라진 것이 아니라, 남아 있는 점이 선행차로 선택되지 않으면서 상위 정지 요청이 풀린 것**이다. 반면 신호 정지 사례에서 수정한 문제는 **정지 요청이 유지되는데도 Toyota의 이전 양수 요청과 제어 보정이 새 양수 CAN 명령으로 남는 것**이었다. 현재 Toyota 정지 보강은 두 번째 조건에만 적용된다. 이 보강이 첫 근거리 사례의 상위 재출발까지 해결했다고 볼 근거는 없다.

이번 조사에서는 기존 CSV·JSON과 현재 소스를 직접 읽었다. 새 모의 실행, 새 회귀 검사, 실제 차량 연결, CAN 송신 및 정책 변경은 하지 않았다. 표의 수치는 기존 동결 결과에서 읽은 값이며, 현재 소스로 첫 근거리 시험을 다시 실행한 결과가 아니다.

## 자료와 당시 실행 전제

작업공간은 `$LAB`이다. 새 자료는 `work/radar_loss_stop_transition/`에만 작성했다. `frozen_read03/fingerprints.json`은 현재 읽은 생산 소스와 기존 결과 32개 파일의 SHA256, 파일 크기 및 읽기 전후 불변 여부를 담는다. `evidence.json`은 변곡 행과 제한된 요약값, `current_source_excerpt.json`은 현재 소스의 관련 행을 보존한다. 모든 32개 파일의 읽기 전후 지문은 같았다.

| 자료 | 확인한 범위 | 제한 |
|---|---|---|
| 첫 `native_sim/stop_inspection` | 정지 차량 110m 앞, 자차 초기 25m/s, 진행 의도의 모델, 합성 ARS 입력, 순정 ACC 대상 보조 입력 없음. native MPC 240회 상태 0, ACC 명령 400개·디코딩 오류 0, ARS 레코드 200개·CRC 오류 0 | 기존 요약에는 당시 전체 소스 지문·commit이 없다. solver 클래스명은 실제 C/Cython 실행을 기록하지만 현재 전체 소스와의 동일성까지 입증하지 않는다 |
| 현재 `closed_loop.py` | `SelfdriveState.enabled/active=True`, `CC.longActive=True`인 명목 활성 시험. `LongControl.update(True, ...)` 호출. `canValid=True`, drive, 가스·제동·버튼 기본 비입력, `pcm_acc_status=8` | 이는 전체 호스트가 권한을 도출하는 시험이 아니다. 당시 첫 near CSV에는 longActive, LongControl 상태, 이전 요청 및 적분 항목이 없으므로 당시 각 값을 직접 관측했다고 표현할 수 없다 |
| `closed_loop.py`의 정지 상태 | 자차 `standstill`은 속도에서 생성하지만 `cruiseState.standstill`은 설정하지 않아 스키마 기본값 False. 순정 PCM 상태도 명목 8 | 실제 PCM 상태 7·재개 버튼·가스·제동을 읽은 실차 정지·재출발 시험을 대체하지 않는다 |
| 신호 CAN 보강 전·후 동결 결과 | 실제 Signal/Carrot/MPC/LongControl/Toyota 명령 생성 연결, 모델·카메라·차량 응답은 합성. 보강 후 요약에 Toyota 소스 지문 기록 | Python CAN backend의 패킹·디코딩 검사이며 이 자료 자체는 실제 Panda 권한이나 실차 응답 검사가 아니다 |
| 신호 전체 호스트 33조건 | 원형 호스트의 자연 가스 override·재개와 실제 C 안전 라이브러리 메모리 검사. 합성 관측·차량 입력 | 레이더 선행차 소실 조건까지 결합한 시험이 아니다 |
| 원본 로그 기반 paired 호스트 | 원본 CAN·CS 메타·OFF 조건 보존, offline 레이더 입력과 native 계획 관찰 | 원본에서 enabled/active/longActive와 C 종방향 권한이 모두 0. 사용자의 long ON 운용 전제 검증을 대신하지 않는다. 파생 발행 헤더는 명시한 저장 순서 시계 가정이며 실물 ARS 발행 시각이 아니다 |

현재 `inspect_stop.py`는 객체 가속도 항목 등을 포함한 14열 관측 CSV를 쓰지만, 첫 동결 관측 CSV는 11열이다. 따라서 현재 도구 지문을 첫 실행의 지문으로 소급할 수 없다. 파일 시스템 저장 시각만으로 정확한 당시 코드 버전을 확정하지 않았다. 첫 near의 세부 권한·PCM 전제는 현재 도구의 명목 계약과 보존 설명을 함께 읽은 조건부 해석이며, 당시 모든 내부 상태의 기록은 아니다.

## 정지 요청에서 새 CAN 명령까지의 연결

| 단계 | 정지·재출발 조건과 역할 | 레이더 lead.status와의 관계 |
|---|---|---|
| DPath 선행차 선택 | 현재 비전 선행차 변환은 거리 0.5m 이하를 배제한다. 같은 현재 레이더 점을 유지하는 선택적 보강은 기존 확인 대상·정지 근처·동일 점·시간·거리 연속성 등을 요구한다 | 객체 점 존재와 lead.status는 다르다. 완전 소실·새 점·잘못된 시간까지 유지하지 않는다 |
| CarrotPlanner | 활성 신호 hold 또는 Start hold가 있으면 e2eStopped·목표 속도 0을 우선한다. 그 외에는 선행차/신호/가스/기존 상태로 lead·cruise·정지 상태를 전환한다 | lead.status=False 자체로 영구 정지나 운전자 재개 대기를 새로 만들지 않는다. 신호가 없는 lead/cruise 상태에서 선행차가 없어지면 cruise로 갈 수 있다 |
| MPC | 두 선행차 상태를 읽고 선행차·크루즈·정지 장애물 중 제한 조건으로 궤적을 계산한다. 선행차가 없으면 원형 수치 계산용 빈 대상 처리가 사용된다 | 빈 대상의 50m·자차 속도+10m/s는 내부 최적화 값이며 실제 레이더 객체로 만들어 발행한 값이 아니다. 빈 상태 자체가 정지 장애물은 아니다 |
| LongitudinalPlanner | ACC 모드의 shouldStop은 계획 궤적의 두 시점 속도가 정지 기준 이하인지로 결정한다. Start hold는 별도로 shouldStop=True·속도 0·가속도 최대 0을 강제한다 | hasLead는 선행차 상태를 담는 별도 항목이다. hasLead=False와 shouldStop=True/False는 동일 조건이 아니다 |
| LongControl | active=False이면 off. shouldStop=False이고 PCM cruise standstill=False이며 브레이크가 아니면 stopping에서 starting 또는 pid로 전환할 수 있다. shouldStop 유지 또는 softHold는 stopping 경로를 유지한다 | 자차 속도 0만으로 stopping을 영구 유지하지 않는다. 가까운 lead는 stopping 진입을 돕지만 이미 풀린 shouldStop을 별도로 복원하지 않는다 |
| Toyota CarController | 정확 RAV4 2022·longActive·stopping·요청 가속도<=0에서 이전 양수 요청과 양수 적분을 정리하고 최종 새 요청도 <=0으로 제한한다 | lead.status를 읽어 정지 요청을 보존하는 기능이 아니다. 상위가 이미 go/pid로 전환하면 이 stopping 보강의 조건이 성립하지 않을 수 있다 |
| 호스트 권한 | CC.longActive는 enabled·종방향 override 없음·OP 종방향 설정에서 도출한다. 비활성이면 LongControl을 reset한다 | 건강한 빈 선행차와 레이더 오류는 다른 입력이다. 레이더 임시 오류는 soft-disable, CAN 오류는 immediate-disable 등 기존 사건 경로를 따른다 |

Toyota의 실제 CarState는 PCM `CRUISE_STATE == 7`을 cruise standstill로 읽는 별도 조건을 갖는다. 첫 명목 시험의 PCM 8·스키마 False와 실차 PCM 정지 상태를 동일하게 취급하면 안 된다. 또한 CarController의 `standstill_req`는 자차 정지 진입과 PCM 상태에 따른 송신 항목이며, 상위 shouldStop을 영구 유지하는 상태가 아니다. `permit_braking=True`도 제동을 허용하는 항목이지 독립적으로 정지 가속도를 만드는 요청이 아니다.

저속에서는 Toyota CAN의 lead 표시를 `hud.leadVisible OR vEgo<12m/s`로 보낸다. 이 항목이 True라고 해서 DPath가 실제 레이더 선행차를 확인했다고 해석할 수 없다. 첫 명목 도구도 HUD leadVisible을 시나리오 값으로 설정한다.

## 첫 근거리 사례의 변곡점

아래 시간은 합성 시험 경과초이다. 관측 CSV는 계획에 입력되는 시점, 제어 CSV는 해당 주기 차량 적분 결과를 포함하므로 같은 표기 시각의 자차 속도·실제 간격을 완전히 같은 표본으로 합치지 않았다. 객체 ID는 재기록하지 않았다.

| 경과초 | 남아 있는 점 / 선택된 선행차 | 상위 목표·정지 요청 | 관측된 ACC 명령 | 의미 |
|---:|---|---|---:|---|
| 7.85 | 점 1개·거리 약 0.9747m / 선행차 True | 이 행은 관측 CSV | 해당 행에 없음 | 근거리 진입 전에 실제 측정점과 선택 대상이 있었다 |
| 8.00 | 별도 제어 표본 | shouldStop=1, 목표 약 -1.109m/s² | -1.194m/s² | 정지 요청 구간 |
| 8.50 | 점 1개·약 0.5049m / 선행차 True | shouldStop=1, 목표 -0.3601 | -1.210 | 0.5m 경계 앞 |
| 8.60 | 점 1개·약 0.4903m / 선행차 False | shouldStop=1, 목표 -0.2291 | -1.211 | 측정점은 남아 있고 선택된 선행차가 사라졌다 |
| 8.70 | 점 1개 / 선행차 False | 자차 속도 0, shouldStop=0, 목표 +0.2445 | -1.124 | 상위 계획이 정지에서 진행 요청으로 바뀌었다 |
| 9.00 | 점 1개 / 선행차 False | shouldStop=0, 목표 +0.7679 | -0.079 | 기존 제동 명령이 풀리는 구간 |
| 9.05 | 점 1개 / 선행차 False | shouldStop=0, 목표 +0.8340 | +0.040 | 20Hz 제어 CSV에서 처음 관측된 양수 명령 |
| 9.15 | 선행차 False | shouldStop=0, 목표 +0.9530 | +0.540 | 모의 차량이 다시 움직인다 |
| 9.78 | 요약의 100Hz 차량 표본 | 실제 간격 0.4m 기준 아래 첫 진입 | 별도 정확 송신 표본 없음 | 시나리오의 여유 거리 위반 |
| 10.31 | 요약의 기하학적 겹침 | 앞차와 자차 위치 겹침 | 이후 궤적은 유효한 충돌 물리 모델이 아님 | 최초 겹침 시각까지만 실패 분석에 사용 |

9.05초는 20Hz CSV에 저장된 명령 관측 시각이다. 최초 33.3Hz CAN 생성 시각을 이 CSV만으로 9.05초 또는 다른 특정 시각이라고 확정하지 않았다. 첫 near에는 LongControl 상태·이전 요청·적분이 저장되지 않아, 8.70초의 shouldStop 해제가 source 조건상 stopping 해제에 연결될 수 있다는 판단과 당시 정확 내부 상태 관측을 구분한다.

거리 0.5m 경계와 `vision_lead_from_model` 배제 조건은 현재 소스와 변곡이 일치한다. 다만 당시 선택기의 모든 내부 점수·원인 분기를 로그로 기록하지 않았으므로 단일 조건 하나만이 당시 전체 원인이었다고 단정하지 않는다. 확인된 사실은 점 1개가 남아 있는데도 lead.status=False이고 이후 shouldStop이 풀렸다는 것이다.

## 현재 정지 보강이 해결한 별도 문제

신호 `stopped_red_green_go`의 합성 첫 행을 0초로 정규화해 읽었다. 보강 후 요약의 Toyota 소스 지문과 이번 현재 파일 지문은 모두 `f09cebd050f822a5c181f6c706cc3eb752c3f90bca24f5415a86b7506d502d97`로 같다. 이는 보강 후 기존 결과와 해당 Toyota 파일의 동일성을 확인한 것이며, 이번에 근거리 사례를 재실행했다는 뜻이 아니다.

| 경과초 | hold / shouldStop | 보강 전 기존 결과 | 보강 후 기존 결과 |
|---:|---|---|---|
| 2.13 | False / False | LoC +0.6735, 새 CAN +0.623 | pid, 이전 요청 +0.600, 적분 +0.0234, 새 CAN +0.623 |
| 2.15 | True / True | LoC -0.003, 새 ACC 메시지 없음, 직전 +0.623 유지 | stopping, 새 ACC 메시지 없음, 직전 +0.623 유지 |
| 2.16 | True / True | 정규 새 CAN +0.502 | 첫 정규 새 CAN -0.006, 이전 요청 -0.006, 적분 0 |
| 2.28 | True / True | 정규 새 CAN +0.019 | 정규 새 CAN -0.042 |
| 2.31 | True / True | 첫 음수 새 CAN -0.033 | 정규 새 CAN -0.051 |

보강 전에는 hold 뒤 양수로 관측된 제어 표본 16틱 중 정규 새 ACC 양수 메시지도 5개 있었다. 보강 후에는 새 정규 메시지부터 음수이며, 정규 발행 전 직전 양수 메시지 유지 1틱이 남았다. 추가 비정규 송신으로 이 간격을 가리지 않았다. 원형 송신은 100Hz 제어의 3프레임마다 한 번, 즉 약 33.3Hz이다.

보강 후 모의 물리 가속도가 음수가 되는 2.57초는 지정한 차량 응답 지연·시정수의 결과다. 실제 차량 응답 보장이나 새 CAN 명령 발생 시각과 같은 값이 아니다. 초록 관측이 hold를 해제해도 모델의 shouldStop이 남아 있는 별도 사례는 진행하지 않는다. 초록이나 레이더 소실 자체가 새로운 호스트 가속 권한을 부여한다고 표현하지 않았다.

## 근거리 유지 선택 정책의 의미와 한계

기존 `witness_sensitivity`의 정지 대상 비교도 새로 실행하지 않고 읽었다.

| 합성 순정 ACC 보조 입력 / 근거리 유지 옵션 | 기존 결과 | 해석 범위 |
|---|---|---|
| 없음 / False | 첫 겹침 10.31초 | 첫 near와 같은 상위 진행 전환이 남는다 |
| 없음 / True | 첫 겹침 10.31초 | 옵션만 켜도 기존 필터·확인 전제가 부족하면 해결되지 않는다 |
| 지속 보조 입력 / False | 첫 겹침 10.31초 | 0.5m 경계 아래 유지가 없으면 이 합성 사례는 실패 |
| 지속 보조 입력 / True | 겹침 없음, 최소 간격 0.493034m, 최종 속도 0 | 명시한 합성 입력과 선택적 옵션 조건에서의 관측이다. 실차 정지 안전성 결론이 아니다 |

보조 CAN의 CHECK_BYTE는 검증되지 않은 0 자리값이라는 기록이 있다. 이를 실물 ECU가 받아들이는 프레임이라고 주장하지 않는다. 겹침이 발생한 세 경우의 최종 음수 간격·접촉 이후 속도를 유효한 제동 성능으로 비교하지 않았다.

현재 근거리 유지 옵션의 운용 연결은 정확 Toyota RAV4 2022·OP 종방향 설정·`not CP.radarUnavailable`을 요구한다. 원본 CP는 radarUnavailable=True이므로 이 정책은 실제 운용 연결에서 활성화되지 않는다. 이번 조사에서는 CP를 False로 바꾸거나 옵션을 켜지 않았다. 기존 합성 시험이 옵션 인자를 명시해 비교했다는 사실과 현재 원본 CP의 운용 조건을 분리한다.

이 옵션은 이미 확인한 동일한 **현재 측정점**을 제한된 조건에서 유지한다. 점 완전 누락·새 ID·시간 오류·움직이는 대상까지 정지를 보장하는 일반 소실 정책이 아니다. 따라서 근거리 경계 문제, CRC/패킷 오류, radar unavailable, 선행차의 실제 이탈을 하나의 소실 원인으로 합치면 안 된다.

## 신호 전체 호스트와 운전자 재개

전체 호스트의 기존 합성 가스 500ms 입력 결과를 비교 근거로 읽었다. 가스 입력 중 호스트가 자연 override로 CC.longActive=False를 만들고, 해제 뒤 정상 권한으로 재개했다. 임의 controls setter를 사용한 시험이 아니다.

| 기존 전체 호스트 조건 | 신호 판단의 읽기 순서 | 기존 결과 | 정지·재출발 해석 |
|---|---|---|---|
| 가스 시작이 계획 정각 0ms | 새 가스와 이전 CC 활성 입력을 먼저 읽음 | 10초 driver cooldown 설정, 4초 관찰 창의 C 허용 양수 CAN 114개 | cooldown은 신호 veto를 억제하는 운전자 override 정책이지 10초 정지 보장이 아니다 |
| 가스 시작이 계획 사이 10~40ms | 다음 계획에서 이미 비활성 CC를 읽음 | enabled reset이 가스 분기보다 먼저 실행, 빨강 재확인 150ms, C 허용 양수 CAN 5개 | 운전자 의도 입력의 위상에 따른 분기 차이이며 레이더 점 경계와는 다른 원인 |
| 10ms 가스 pulse | 계획이 가스 True를 읽지 못해도 이전 CC False를 읽음 | hold reset·재획득이 있지만 양수 LoC/CAN 0 | hold 소실만으로 반드시 가속이 발생하는 것은 아니다 |
| CAN invalid | 첫 판단은 valid False로 hold 보존, 호스트는 canError로 즉시 비활성, 다음 계획에서 disabled reset | 양수 CAN 0 | 건강한 빈 lead와 CAN 장애가 같은 상태가 아니다 |

신호 guard의 enabled reset과 가스 10초 veto 억제 정책, 모델 정지 의도, Carrot 정지 카운터 및 호스트 재개가 함께 결과를 바꾼다. CC만 수동 False로 만든 이전 부분 시험을 자연 가스 override 전체 호스트 시험과 같은 정책 입력으로 취급하지 않았다. 가스 처리를 앞당기거나 lead 소실에서 무조건 정지를 유지하는 정책은 이번 범위에서 선택·구현하지 않았다.

## long ON 전제와 실제 원본 로그의 구분

paired 호스트의 동결 요약은 host tick 15,407개, enabled 0, active 0, longActive 0, C 종방향 허용 tick 0, 비영 가속 요청 0이다. native 계획 2,759개에서 선행차 소비 175회가 관찰되었다고 해서 종방향 제어가 실제 활성 상태에서 검증되었다는 뜻은 아니다. 원본 설정의 OP 종방향 True도 실행 중 권한 True와 별개다.

사용자가 설명한 long ON 차량의 정지·재출발 호환성을 확정하려면 실제 그 운용 상태에서 선행차 소실 직전·직후의 원본 CAN, 정확 CS batch/receive 메타, PCM CRUISE_STATE와 버튼·가스·제동·softHold, enabled/active/longActive, source plan shouldStop·MPC 제한 대상, 신뢰 가능한 발행·수신 시간, 순정 PCS/AEB 상태를 함께 확인해야 한다. 실험적 제어 송신을 이 자료 확보의 전제로 삼지 않는다.

후속 분석에서 구분할 반례는 현재 측정이 남은 0.5m 경계, 짧은 점 누락, 완전 lead 이탈, CAN/입력 시간 오류, 운전자 가스·제동·명시 재개, PCM 7↔8 전환, 모델 정지 지속/진행 의도 및 신호 hold 지속/해제이다. 새 threshold·재출발 정책·실차 활성화는 이 문서로 승인하거나 안전성이 확인되었다고 판단하지 않는다.

## 소스 위치와 재현 가능한 읽기

현재 소스의 주요 근거는 다음 파일의 보존 행이다.

- [Toyota CarController]($LAB/work/carrotpilot/opendbc_repo/opendbc/car/toyota/carcontroller.py:203): 정지 보강 203~248행, 정규 발행 192행, 저속 lead 표시 189행, 정지 요청 항목 176~182행.
- [Toyota CarState]($LAB/work/carrotpilot/opendbc_repo/opendbc/car/toyota/carstate.py:166): PCM 정지 상태 166~171행. [차량 설정]($LAB/work/carrotpilot/opendbc_repo/opendbc/car/toyota/interface.py:133): autoResumeSng와 TSS2 정지 기준 133~147행.
- [LongControl]($LAB/work/carrotpilot/openpilot/selfdrive/controls/lib/longcontrol.py:25): 상태 전이 25~63행, 정지 출력 153~175행.
- [CarrotPlanner]($LAB/work/carrotpilot/openpilot/selfdrive/carrot/carrot_functions.py:572): hold와 정지·진행 전이 572~647행.
- [MPC]($LAB/work/carrotpilot/openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py:384): 빈 대상 처리 384~406행, 상태 426행, 제한 대상 선택 488~491행.
- [계획의 정지 출력]($LAB/work/carrotpilot/openpilot/selfdrive/controls/lib/longitudinal_planner.py:414)과 [속도 궤적의 정지 판정]($LAB/work/carrotpilot/openpilot/selfdrive/controls/lib/drive_helpers.py:109).
- [비전 근거리 배제]($LAB/work/carrotpilot/openpilot/selfdrive/carrot/radar_motion/primary.py:797), [현재 점의 제한적 유지]($LAB/work/carrotpilot/openpilot/selfdrive/carrot/radar_motion/controller.py:548), [운용 연결 조건]($LAB/work/carrotpilot/openpilot/selfdrive/carrot/radar/radard_dpath.py:105).
- [종방향 권한]($LAB/work/carrotpilot/openpilot/selfdrive/controls/controlsd.py:160), [레이더 오류 사건]($LAB/work/carrotpilot/openpilot/selfdrive/selfdrived/selfdrived.py:426), [사건 분류]($LAB/work/carrotpilot/openpilot/selfdrive/selfdrived/events.py:940), [3초 soft-disable 상태]($LAB/work/carrotpilot/openpilot/selfdrive/selfdrived/state.py:39).
- [신호 reset·가스 순서]($LAB/work/carrotpilot/openpilot/selfdrive/carrot/signal_start_guard.py:144), [명목 시험 입력]($LAB/work/native_sim/closed_loop.py:137).

작업공간에서 아래 명령으로 같은 동결 자료를 새 하위 출력 폴더에 읽을 수 있다. 이미 있는 폴더는 덮어쓰지 않는다. 이는 계산 알고리즘을 다시 실행하는 명령이 아니다.

```powershell
$env:PYTHONIOENCODING='utf-8'
& work/venv/Scripts/python.exe work/radar_loss_stop_transition/collect_evidence.py --output-dir work/radar_loss_stop_transition/independent_read
```

최종 파일 읽기 직접 실행은 exit 0, 원본·현재 소스 32개 파일 지문 불변이었다. 준비 오류와 제외한 잘못된 선택 행은 `PREPARATION_NOTES_KO.md`에 기록했다. 현재 보강을 적용한 첫 near 재실행, 원본 long ON 실제 차량의 재개 동작, 실제 Panda/PCS/AEB 및 제동 응답은 이번 조사에서 검증하지 않았다.
