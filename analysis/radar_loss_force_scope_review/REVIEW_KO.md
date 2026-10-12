# 기존 호스트 감속 요청 보존 후보의 독립 범위 검토

후보는 **정확 Toyota RAV4 2022의 OP 직접 종방향 제어에서 기존 호스트 forceDecel 요청을 당근 목표 속도가 덮어쓰지 않게 전달하는 좁은 Python 변경**이다. 다른 Toyota와 순정 종방향 RAV4 2022의 현재 생산 호출은 새 옵션 False를 전달한다. `CP.radarUnavailable=True`를 바꾸지 않는다. 즉시 해제·3초 soft-disable 타이머·PCM/PCS·신호 판단 정책의 정의를 바꾸는 diff는 없다.

이는 읽기·diff·문법/AST 비교 결과다. 새 주행 시험, 후보 동작 시험 또는 native 재빌드를 실행하지 않았으며 감속 효과·안전성을 확인했다는 결론은 아니다.

## 변경 내용과 적용 조건

현재 생산 소스와 후보 두 파일의 정규화 diff는 `candidate_diff.patch`, SHA256 및 함수별 AST 비교는 `fingerprints.json`에 보존했다. 변경 함수는 `LongitudinalMpc.update`와 `LongitudinalPlanner.update`뿐이다. 나머지 함수 본문과 생성 함수는 AST 비교에서 같다.

| 항목 | 후보 동작 | 범위 |
|---|---|---|
| MPC 옵션 | 마지막 선택 인자 `force_slow_decel=False` 추가 | 기존 호출은 인자를 생략해도 원래 동작. 기본 True가 아니다 |
| 목표 속도 | 당근 `v_cruise/stop_dist/mode`를 읽은 뒤 옵션 True이면 로컬 `v_cruise=0.0` | CP·Carrot 내부 상태·레이더 객체·정지 latch를 수정하지 않는다 |
| 생산 호출 | `controlsState.forceDecel AND actuator_accel_limits is not None` 전달 | 생성자에서 한계가 설정되는 조건은 Toyota·정확 `TOYOTA_RAV4_TSS2_2022`·OP 종방향 True |
| 다른 Toyota | 생성자의 한계 None → 새 옵션 False | 현재 생산 호출 기준 기존 행동 |
| RAV4 2022 순정 종방향 | OP 종방향 False → 한계 None → 새 옵션 False | 브랜드/차종만 같다고 적용되지 않는다 |
| RAV4 2022 직접 종방향, forceDecel False | 새 옵션 False | 기존 목표 읽기 동작 |
| RAV4 2022 직접 종방향, radarUnavailable True, forceDecel True | 새 옵션 True | 미지원 레이더를 켜는 것이 아니다. 이 조건은 radarUnavailable을 변경하거나 우회하는 설정이 아니다 |

현재 생성자에서 `actuator_accel_limits`는 None으로 시작하고 위 정확 차량 조건에서만 기존 Toyota 인터페이스의 가속도 한계를 읽어 설정한다. 유효하지 않은 한계이면 기존 예외를 유지한다. 이 분기 자체는 후보 diff의 새 변경이 아니다.

적용 조건에는 PCM Button Mode 0, 레이더 lead 소실, 오류 종류, 신호 색 또는 longActive가 직접 포함되지 않는다. 따라서 이를 “mode0 전용”, “레이더 소실 전용” 또는 “활성 제어 틱에서만 계산하는 옵션”이라고 확대·축소해 설명하면 부정확하다. 실제 명령 권한은 계속 기존 호스트·LongControl·Toyota·안전 계층에서 판단한다.

`LongitudinalMpc`는 일반 계산 클래스라 차량을 직접 검사하지 않는다. 다른 호출자가 새 옵션을 명시적으로 True로 넘기면 해당 계산에도 적용된다. 독립적으로 검색한 현재 생산 호출은 `LongitudinalPlanner`의 한 곳이며 여기서는 정확 차량 조건에 제한된다. 향후 호출 추가·한계 속성 변경 시 같은 범위를 다시 확인해야 한다.

## native 바이너리와 기존 정책

MPC의 C 생성 모델·목적 함수 생성·상태/파라미터 차원·solver API 정의는 diff에서 바뀌지 않는다. 수정은 Python 실행 중 목표 값을 정한 뒤 기존 solver 입력을 구성하는 경로다. 따라서 이 후보만을 위해 native 모델을 다시 생성하거나 `.so`를 바꿀 필요는 없다. 바이너리를 재사용할 수 있다는 판단과 새 입력의 수치 결과를 검증했다는 주장은 다르다.

기존 Planner는 이미 `forceDecel`이면 MPC 호출 전 `v_cruise=0.0`을 설정한다. 그러나 ACC 경로에서 MPC가 당근의 `v_cruise`를 다시 읽으면 그 0이 덮일 수 있다. 후보는 읽기 뒤에도 호스트 요청을 보존한다. `forceDecel`의 출처는 기존 `controlsd`의 운전자 주의 경고 또는 `selfdriveState.softDisabling`이며 레이더 소실에서만 생기는 신호가 아니다.

후보는 `StateMachine`, event 분류, CC.longActive 계산, PCM 상태/재개 명령, CarController 33.3Hz 송신, PCS/AEB, Panda, 신호의 red/green/reset/cooldown 소스를 수정하지 않는다. 사용자/즉시 해제 우선순위와 3초 soft-disable가 그대로다. 다만 기존 forceDecel이 유효한 동안 하위 목표에 실제로 전달되도록 바꾸므로 soft-disable 동안의 계획 궤적·정지 판정·후속 신호 판단 결과는 간접적으로 달라질 수 있다. “신호 정책 정의 불변”과 “신호 관련 모든 수치·상태 결과 동일”을 혼동하면 안 된다.

## 남은 주의사항

- 옵션은 목표 속도 0을 보존하며 가속도 명령의 즉각 음수 제한, shouldStop 강제 또는 운전자 재개 latch를 새로 만들지 않는다. 기존 가속도/jerk·정지 상태·정규 CAN 주기·큐·차량 응답 지연이 남는다.
- 건강한 빈 lead만 있고 호스트 forceDecel이 False인 근거리 소실 사례에는 이 후보의 새 경로가 작동하지 않는다. 앞선 near 실패 전체를 해결했다고 주장할 수 없다.
- ACC/혼합 모드를 새 조건으로 제한하지 않는다. 혼합 모드의 기존 목표 궤적 clipping도 그대로이므로 “모든 모드에서 즉시 정지 속도”를 보장하지 않는다.
- 목표 0에서 기존 ACC `source=='cruise'` 분기가 `autoNaviSpeedDecelRate`를 사용하는 경로는 유지된다. 실제 설정값·가속도 한계·reset·선행차 유무가 함께 적용되는 수치 검증은 후보 실행 담당자가 확인할 항목이며 이번 읽기 감사에서는 통과라고 보고하지 않았다.
- forceDecel 해제·일시 회복·가스/제동·PCM 재개·soft-disable 끝점에서 이전 계획과 상태가 어떻게 이어지는지는 동작 검증 사항이다. 새 freshness threshold나 lead 유지 정책의 근거가 이 diff에 생긴 것은 아니다.
- 원본 로그의 longActive OFF와 사용자가 설명한 long ON 운용 상태, 합성 계획 결과와 실물 PCS/AEB 유지·실차 안전성은 계속 구분해야 한다.

## 파일과 지문

- 후보 [MPC]($LAB/work/radar_loss_authority_root/candidate_sources/long_mpc.py:424): 옵션 424행, 목표 보존 447~449행. SHA256 `8d493b65acc3f5a4273bb436009d9ab99fdc573063e5f0581d23c45147b33b00`.
- 후보 [Planner]($LAB/work/radar_loss_authority_root/candidate_sources/longitudinal_planner.py:270): 생성자 제한 53~65행, 기존 forceDecel 163/224~225행, 새 호출 269~270행. SHA256 `63ac8ab4d0b00284808f6100d812795e9b7eae0de90c230e9ce97dde33f58617`.
- 현재 MPC SHA256 `b0a5c630260ad76b58033b8d44719992c4e008399b2c520e3692b556ce12e274`, 현재 Planner `01ead57b64c3bde5ae56bebefb015986e877014cc0d63885e77833e08f9b886f`이며 후보 원본 manifest와 일치했다.
- [forceDecel 출처]($LAB/work/carrotpilot/openpilot/selfdrive/controls/controlsd.py:436), [기존 해제·타이머]($LAB/work/carrotpilot/openpilot/selfdrive/selfdrived/state.py:25), [Toyota 한계 읽기]($LAB/work/carrotpilot/opendbc_repo/opendbc/car/toyota/interface.py:20).

생산 코드·후보 파일·기존 결과·native 바이너리·운영 설정·실차는 이 리뷰에서 변경하지 않았다. 새 파일은 지정 리뷰 폴더에만 남겼다.
