# forceDecel 전달 후보 독립 소스 읽기 검토

현재 source에서 **Planner가 forceDecel로 만든 전달 속도0이 MPC의 carrot.v_cruise 재대입으로 사라지는 경로**를 확인했다. exact RAV4 2022/directLong caller에만 적용하는 optional 인자를 기본False로 추가하고 이 재대입 뒤에 목표0을 적용하는 후보는 해당 연결을 좁게 수정할 수 있다. 다만 이 소스 읽기로 첫 틱·모든 모드·최종 CAN의 감속 결과를 확정할 수 없다. 새 정책·패치·수치 없는 통과 테스트를 만들지 않았다.

읽은 범위는 현재 LongitudinalPlanner/LongitudinalMpc, preview·coasting·신호 후처리, ToyotaCC와 기존 B run01/부모 force_decel_observation이다. 새 benchmark·MPC/C·차량 송신·source 수정은 실행하지 않았고 이 문서만 추가했다. 앞의 레이더 소실 보고서와 변곡 JSON은 동결 상태를 유지한다.

## 확인된 전달 단절과 보존 관측

Controls는 DM alert3 또는 softDisabling 상태에서 controlsState.forceDecel을 발행한다(controlsd.py:436–438). Planner는 이 bool을 읽고 v_cruise=0으로 바꾼다(longitudinal_planner.py:163,224–225). 그 뒤 MPC.update의 초기 mode가 blended가 아니면 `v_cruise,stop_x,mode=carrot.v_cruise,carrot.stop_dist,carrot.mode`로 다시 덮는다(long_mpc.py:439–444). 이것은 source에서 확인한 순서다.

기존 temporary_rows의 첫 force 표본103.50초는 softDisabling/forceTrue/radar validFalse/leadFalse, carrot cruise21.388889m/s·planner UI cruise77kph·plan target+0.950203이었다. 같은 틱의 Planner/Controls 실행 순서와 다음 model 반영은 구분한다. 부모의 별도 보존 진단은 temporary/producer_stopped 각각 force-active300틱 모두 양수 제어·음수0이었다. 이는 **고정 ego 합성 입력·원형 전체 host/C의 보존 실행**이며 이 감사자의 새 재현이나 물리 감속거리 측정이 아니다.

후보는 새로운 오류 최대제동 정책이 아니라 기존 forceDecel 목표의 전달을 복원하는 범위로 설명해야 한다. forceDecel은 레이더 오류 외 DM/softDisabling에서도 발생하므로 ‘레이더 전용 조건’으로 한정된 효과라고 주장하면 안 된다. 권한·StateMachine·Panda·PCS·CP 플래그는 이 후보가 변경할 대상이 아니다.

## 모드별 적용 위치와 한계

| 경로 | 현재 source와 후보의 의미 | 확인해야 할 수치 범위 |
|---|---|---|
| acc→carrot.mode acc |carrot override 뒤 최종 v_cruise0을 적용하면 cruise obstacle이0 목표로 계산됨 |v_lower/v_upper clip·jerk/이전 가속 제약을 거치므로 즉시 모든 aTarget/CAN≤0을 소스만으로 보증하지 않음 |
| 초기 mode acc→carrot.mode blended |같은 override 줄에서 mode도 바뀜. local 최종 mode를 기준으로 분기해야 함 |초기 self.mode만보고 acc로 판정하는 테스트는 이 경우를 놓침 |
| 초기 mode blended |전달 v_cruise0은 원래 유지되며 stop_x1000 정책 사용 |blended cruise_target은 vEgo−2m/s 하한으로clip하고 model x/v/a를 함께 쓰므로0 목표가 즉시 정지 참조를 뜻하지 않음 |
| lead 존재 |실제 선택 lead 장애물은 계속 원형 계산 |더 강한 lead 제동을 약하게 만들지 않으며 closer lead/양수 선행차·Tau·identity 변경의 실제 출력 비교 필요 |
| force False |새 flag의 기본False와 caller gate로 원형 경로 유지 |일반 cruise·지도/커브·lead·신호·coasting의 기존 출력 배열과 같아야 함 |
| 다른 CP/stock b |exact RAV2022/directLong caller만True |RAV2023/CHR/다른 brand 및 RAV2022 stockFalse는 원형 경로. MPC 단독 API는 CP를 모르므로 책임은 caller에 있음 |

MPC에서 override가 끝난 뒤, cruise_target/obstacle이 만들어지기 전에 flag를 적용해야 한다. solver 이후 배열을 갑자기0으로 덮거나 stop_x/lead를 새로 만들면 이 후보의 범위를 넘는다. UI/Carrot cruise 표시를 바꾸는 것과 MPC 내부 요청 속도0 전달도 별개다.

acc 분기에서 v_cruise0/source cruise이면 `params[:,0]=-carrot.autoNaviSpeedDecelRate`라는 기존 분기가 새로 활성화된다(long_mpc.py:492–494). source 기본 AutoNaviSpeedDecelRate120은1.2m/s²이며 현재 command envelope−3.5..2 안이다. 실제 시험 설정과0/비유한·과도한 설정 경계를 별도로 확인해야 한다. 목표0이라는 이유로 MPC 하한이 검증된 actuator command 범위를 벗어나도록 임의 확장하면 안 된다. 이것은 실측 마찰계수·차량 최대제동 능력의 보증도 아니다.

## 최종 aTarget과 downstream 재덮기

| 이후 처리 | source에서 확인한 성질 | 남은 제한 |
|---|---|---|
| lead acceleration response/gap/cutout relief |Planner는 이미not force 조건으로 세 요청을 막음(:246,261,265) |실제 선택된 lead 자체와 MPC 장애물은 지우지 않는다 |
| preview |apply_preview_target은 base/preview의min을 먼저 잡고 하한을제한함 |음수base를 양수로 올리는 분기는 보이지 않음. 양수base가 남으면 그 자체가 즉시0이 되는 보증은 아님 |
| e2e/blended target 결합 |min(MPC,e2e)와 shouldStop OR |음수 MPC를 더 높은 양수e2e로 바꾸지 않음. MPC 내부 blended 참조 결과는 별도검사 필요 |
| signal PrepareAccel |min(target,cap), 비활성이면 target 그대로 |신호 gentle cap이 더 강한 음수 목표를 양수로 올리지 않음 |
| signal StartGuard |hold이면 shouldStopTrue·vTarget0·min(aTarget,0) |force request가 신호 green/go/cooldown 정책을 바꿀 근거는 아님 |
| 최종 actuator clip |검증된 min<0<max 범위 |음수를 양수로 바꾸지 않지만 강도 제한과 실제 차량 응답은 별개 |
| coasting |not force 조건이False라 계획 target0/reset, controller는target>0일 때만relief |기존 coasting 기억의 transition 출력도 수치 있는 비교가 필요. 새 helper로 정상 coasting을 전부 끄는 정책은 아님 |
| LongControl/ToyotaCC |상태·이전 출력·rate limit·PID 보정을 거쳐 정규 CAN 생성 |음수 aTarget만으로 첫 정규 CAN 부호를 보증하지 않음. stopping 비양수 한정 정정은 PID softDisabling 전부에 적용되는 규칙이 아님 |

Planner 후처리에서 **이미 음수인 MPC 목표를 새 양수로 올리는 경로**는 읽은 범위에서 찾지 못했다. 그러나 목표0만으로 solver의 첫 aTarget이 음수임을 확정할 수 없고, 그 뒤 ToyotaCC의 양수 prev_accel/PID 잔여도 별도 문제다. 계획 목표·LongControl 결과·새 정규0x343 생성·그 사이 유지 명령을 나눠야 한다. 이전 shouldStop 유지 중 잔여양수 수정과 shouldStop 해제 후 가속을 같은 원인으로 합치지 않는다.

## 수치 검증이 필요한 경계

원래300틱/100양수 CAN 사례의 동일 입력·동일 native 계산에서 before/after로 effective MPC 요청 속도, mode/source, aTarget, LongControl, 새 정규 ACC_CMD, C 실제 권한/허용을 함께 기록해야 한다. 첫 model/제어/CAN의 스케줄 차이·최소감속/최대양수/시간·33.3Hz cadence를 명시하고, ‘first pass’와 새로운 비교를 섞지 않는다. 실제 감속거리로 해석할 plant 운동/실차는 이 고정 ego 하네스에 없다.

force False와 scope 밖 CP는 기존 배열 동일, force True는acc/blended·lead 있음/없음·coasting 상태·신호hold/prepare·gas/비활성·force 해제 후 복귀를 수치로 확인할 필요가 있다. 단순히 새 인자가True인지나 코드 한 줄의 존재를 검사하는 테스트는 전달 단절·실제 출력 문제의 증거가 되지 않는다. 수렴 status·command envelope와 기존 driver permission도 유지해야 한다.

## 실제 로드 코드와 동결 빌드

offline_io.py:103은 MPC package 검색 경로 앞에 immutable BUILD_ROOT를 넣는다. 따라서 primary long_mpc.py를 바꿔도 기존 build 폴더의 옛 Python 사본이 실행될 수 있다. 새 optional 인자/Planner caller 검사에서는 실제 loaded module 파일과 그 SHA를 확인하고 **새 immutable Python 사본**을 사용해야 한다. 기존 실행 중 .so/build를 덮어쓰지 않는다.

이 후보가 Python runtime 목표/parameter 선택만 바꾼다면 native 수치 방정식 변경·재빌드와 구분할 수 있다. source·overlay Python 버전·C/Cython 파일 지문을 각각기록하고, 예전MPC6파일after-check를 새 패치의 실행전/후 계측으로 재사용하지 않는다. 이번 추가 읽기에서는 그새버전을 생성·빌드·실행하지 않았다.

확인한 결과는 현재 전달 단절의 source 경로와 좁은 후보의 영향 범위다. 최종 감속 부호·블렌드 행동·잔여 출력·타차 동일성은 새 수치 검증 전까지 미확정이다. 임의 정책을 선택하거나 driving source·CP·Params·시간 상수·안전 권한을 수정하지 않았다.
