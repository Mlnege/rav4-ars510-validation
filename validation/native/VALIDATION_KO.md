# RAV4 ARS510 · 실제 native 종방향 계산 검증

2026-10-12, 원형 CarrotPilot `carrot-wip` 기준 커밋 `0e4ee1bdbef3ad7284b136fddf31592e3f8a785f`.

실제 CarrotPlanner → LongitudinalPlanner → acados MPC → LongControl → Toyota CarController → 실제 CANParser를 연결해 **메모리 안에서** 검증했다. ARS 경로는 합성 패킷 → 원형 ARS 조립/CRC/fused → 실제 RadarInterfaceBase/MyTrack → Cap’n Proto liveTracks 직렬화 → 실제 DPathRadarController → 위 종방향 경로다. 계산기·제어기를 가짜 함수로 바꾸지 않았다. 차량·Panda·운영 Params·실제 CAN 송신에 접근하지 않았다.

## 바뀐 계산과 원형 보존 범위

원형 공통 MPC는 최대 제동 명령을 −4.0m/s²로 계산하지만 Toyota 공개 인터페이스와 CarController는 −3.5m/s²~+2.0m/s² 명령만 허용한다. 같은 가상 차량에서 MPC 목표가 −4.0이어도 실제 생성된 ACC_CONTROL 명령은 −3.5에 묶이는 불일치를 재현했다.

`TOYOTA_RAV4_TSS2_2022`·Toyota·기존 직접 종방향 제어 조건에만 공개 `CarInterface.get_pid_accel_limits` 값을 사용한다. MPC의 최소 가속도 실행 파라미터, 수렴을 위한 최소 앞차 거리 계산, 최대 가속도, 보조 처리 뒤 최종 목표를 같은 명령 범위에 맞췄다. 유한성·부호·공통 허용 범위를 확인할 수 없는 설정은 거절한다. **명령 한계는 실제 타이어 마찰·실측 제동력 보장이 아니다.** 크루즈의 편안한 감속 정책, 앞차 가속도 유지시간, 가속도 변화 정책, 운전 성향 필터는 그대로다.

다른 Toyota의 실제 폐루프를 원형/수정 Python 소스로 각각 실행했다. RAV4 2023 및 C-HR TSS2의 30초 시험에서 각600행×12개 동역학·명령·상태 값이 완전히 일치했다.

## 근거리 정지 대상 유지

원형 DPath는 비전·전방 후보의 거리0.5m 하한 아래에서 대상을 제외한다. ARS 합성 시험에서는 처음0.49m 앞에 정지했으나, 이 경계 아래에서 앞차가 사라지고 다시 출발하는 결과를 재현했다.

새 `retain_confirmed_near_front`는 기본값False다. 정상 matcher가 이미 L1으로 채택한 동일 frontRadar ID의 측정점만 다음 조건에서 유지한다.

- 기존 정상 L1의 거리>0.5m, 비전 확인 확률≥0.6, 지상속도 절댓값≤0.3m/s, 자차속도≤0.5m/s.
- 현재 동일 ID의 실제 measured 점이 있으며 원본·투영 거리 모두양수, 투영 거리≤0.5m, 중앙 경로·횡거리 절댓값≤0.5m.
- 원본 거리·속도·가속도 등 사용 값이 유한하며 원본 지상속도도 정지대역 안에 있음.
- 유한·양수·순방향 시각과 기존0.15초 publication skew 한계를 만족하고, 이전 상대속도 예측과의 거리 차이가0.125m 이하.

새 ID, 중복 ID, 빈 측정, 미측정 점, NaN, 이동 물체, 옆 물체, 역행·오래된 시각은 유지하지 않는다. 같은 오래된 레이더 발행시각을 반복해도 유효기간이 늘어나지 않는다. 점이 없어지면 바로 해제한다. 정상 matcher가0.5m 위 대상을 다시 채택하면 기존 경로로 넘긴다. 현재 비전 확률을 만들어내지 않으며 유지 출력의 modelProb는0이다. 운전자 가속·제동·취소 권한은 기존 제어기·safety가 판정한다. 이 controller는 해당 입력 권한을 대신 판정하지 않는다.

런타임에서는 정확한 RAV4 2022·직접 종방향 제어·`radarUnavailable=False` 조건에만 선택 기능을 전달한다. 실제 인터페이스가 만드는 현재 RAV4 CP는 `radarUnavailable=True`이므로 **이 기능도 꺼진 채로 유지**된다. CP 전체 전후 일치를 직접 검사했다. 시뮬레이션만 명시적으로 True를 전달했다. 신규 근거리 획득 기준은 바꾸지 않았다.

원형 controller 소스를 별도 모듈로 그대로 불러와 기본값False의6개 모드×100회 전체 출력 구조를 비교했으며600회 모두 일치했다.

## FUSED의 ACC 관측을 분리한 시험

원형 fused는0x80 객체목록 외에0x235/0x237의 순정 ACC 선택 대상 관측을 함께 사용한다. 이를 빠뜨린 합성 입력에서는 속도·거리 필터가 급제동을 늦게 반영한다. 같은 실제 DPath/종방향 계산에서 정확한 센서 가정 입력은 정지했지만 ACC 관측 없는 ARS 합성 입력은 접촉했다.

`witness_bridge.py`는 기존 `ars510_radar_bus.dbc`와 vendor `support.py`의 확정 필드만 합성한다. 거리0.025m, 상대속도0.125m/s, 상대가속도0.125m/s², STATE/PRESENT를 기존 decoder와 실제 native CANParser로 함께 검증했다. **CHECK_BYTE는 실물 검증 알고리즘을 확인하지 않아0 placeholder다. ECU가 받아들일 유효 프레임이나 실차 호환 증거로 부르지 않는다.** 실제 차량 송신 횟수는0이다.

다음은 최신 Python 소스·고정 native 빌드의20초 가상 주행 결과다. 차량 반응 가정은 명령 지연0.10초+1차 응답 시정수0.15초다. 카메라·앞차·경로는 합성 입력이다.

| 조건 | ACC 관측 | 근거리 선택 기능 | 결과 |
|---|---|---|---|
| 정지차110m, 자차25m/s | full | False | 처음 정지 뒤 재출발,10.31초 첫 위치 겹침 |
| 같은 조건 | full | True | 최솟거리0.4930m, 최종속도0, 위치 겹침없음 |
| 같은 조건 | missing | True | 기존 L1 신뢰 조건 미충족,10.31초 첫 겹침; 미해결로 유지 |
| 앞차60m, 둘 다20m/s,7초부터 앞차−5m/s² | full | False | 최솟거리7.4506m, 최종속도0, 겹침없음 |
| 같은 급제동 | missing | False |13.75초 첫 겹침 |
| 같은 급제동 | idle | False |13.75초 첫 겹침 |
| 같은 급제동 |3초 이후 stale | False |13.75초 첫 겹침 |

각 케이스에서 MPC400회 모두 상태0, ACC_CONTROL 디코딩 오류0이었다. **수치 계산 성공과 장애물 회피 성공은 서로 다른 결과다.** 0.493m 정지는 여유가 작으며 실물 안전 정지 성공으로 일반화하지 않는다. 가상 충돌 뒤 차가 통과하는 물리 모델은 만들지 않았다. 결과 JSON의 `post_contact_trajectory_valid=False`에서는 접촉 뒤 음수 거리·속도를 유효 제동 결과로 해석하지 않고 `first_geometric_overlap_s`까지만 해석한다.

추가 비교에서는 실제 DPath 정확센서 가정으로 정지차110m의 원형8.62초 접촉이 수정 후0.5042m 앞 정지로 바뀌었다. 앞차25m/s·80m·−6m/s² 시험의 여유는8.0908m→9.4474m였다. 기존 Honda형 고정 aLeadTau=1.5 fixture는 실제 DPath 가속도 동역학과 다르므로 그 결과를 별도로 분리했다.

코너·지도 속도 제한50km/h 시험은 모두 최종50.006km/h, 가속 시험은 최종25.0006m/s였다. 이 수치는 계산 경로를 검증하는 결과이며 실물 신호등·지도 정확도의 검증이 아니다.

## native 빌드와 실행 환경

WSL Ubuntu, 격리 Python3.12.15, `comma-deps-acados==0.2.2.post103`, CasADi3.6.7, NumPy2.5.4를 사용했다. 실제 `AcadosOcpSolverCython`이 동작한다. Params·소켓·로그 입출력만 프로세스 안에 격리했다. 소켓 생성은 오류로 막는다.

원형 SCons의 계산 모델·비용식·Cython 경로를 따라 작업 폴더에서 C/Cython을 빌드했다. 공식 wheel의 생성 Makefile이 개발 소스 트리 경로를 가정해 Cython을 못 찾는 문제는 wheel의 실제 TEMPLATE_DIR로 연결해 해결했다. `build()`의 반환과 별개로 실제 확장 파일 존재를 검사했다. C 모델 수식은 바꾸지 않았다.

| 항목 | SHA256 |
|---|---|
| 원형 MPC Python | `b70e3844ba36be9d6b0ad9346d0795dd7fe159e009368065f671056a41a7c54e` |
| 수정 MPC Python | `b0a5c630260ad76b58033b8d44719992c4e008399b2c520e3692b556ce12e274` |
| 원형 planner Python | `414b33f56c1addac9bb594cd6e283c361032e1e674028f314bf6bc4c6aaa51e8` |
| 수정 planner Python | `01ead57b64c3bde5ae56bebefb015986e877014cc0d63885e77833e08f9b886f` |
| 최종 controller Python | `0a2efb2712991ce495f4bb4991cc9ab1352673e96318ff5302fc5bd0d17a34f5` |
| 최종 radard_dpath Python | `f3f3506398dd9bd939b96c83ab21409d8daf3f326fccabb6adf79fb1948d7be2` |
| Cython native 확장, 수정 전후동일 | `5809fa9a1481c56a8e61a9df82f4d32f11a6f1acbafbfc7fdefbd93389c14592` |
| acados solver native 라이브러리, 수정 전후동일 | `2cf19053e5712920719b54ba8f970fcfd178ffe4acd5c77e3170a423b030eb71` |

MPC Python 실행 파라미터를 바꾼 뒤 새 native 전체 빌드가 성공했고, native 확장·solver 해시가 원형과 같았다. 따라서 native 식 변경과 실행 시 차량 명령 제약 변경을 구분할 수 있다. 이 두 파일의 빌드/컴파일 성공이 장치 전체 openpilot 빌드나 차종 실차 시험 성공을 뜻하지 않는다.

실행 중 같은 `.so`를 다시 빌드해 덮어쓰던 때 신호 worker가219초 후 조기 종료한 환경 충돌이 있었다. 수치 결함과 분리했으며 고정 snapshot으로 재시작했다. 현재 `build_snapshot_b0a5c630260ad76b`의source 및6개 native 해시를 검증하고 동결했다. builder는 기존 manifest/.so 경로를 덮어쓰지 않고 새 경로를 요구한다.

## 직접 실행한 검사와 재현 경로

- `test_actuator_bounds.py`:27건.
- `test_near_front_retention.py`:41건.6개 모드×100회 원형 전체 출력 비교와 실제 CP dormant 검사 포함.
- `test_acc_witness_encoding.py`:6건. 공개 DBC byte 일치 및 actual CANParser 확인.
- 위 native 디렉터리 함께 실행:74 passed,4.50초. 이후 DBC 경로를 저장소 내 byte동일 fixture로 수정하고6건을 재실행하여 통과했다.
- 기존 전방·코너 DPath 회귀528건과 신규40건을 함께 실행:568 passed,6.72초.
- 수정 controller/radard 및 신규 테스트 Ruff 통과, source AST 컴파일 통과.

현재 작업 환경 재현 예시:

```bash
export CARROT_VALIDATION_BUILD="$(pwd)/work/native_sim/build_snapshot_b0a5c630260ad76b"
export PYTHONDONTWRITEBYTECODE=1
cd work/carrotpilot
../linux_runtime/venv/bin/python -m pytest -q --noconftest \
  -c tools/ars510_offline/pytest.ini -p no:cacheprovider tools/ars510_validation/native
cd ../native_sim
../linux_runtime/venv/bin/python paired_native.py
../linux_runtime/venv/bin/python paired_native.py --default-regression
../linux_runtime/venv/bin/python witness_sensitivity.py
```

`offline_io.py`·`closed_loop.py`·`radar_bridge.py`·`witness_bridge.py`, 고정 solver 경로, 원형 `baseline_build/long_mpc.py`·`longitudinal_planner.py`·`controller.py`가 필요하다. ACC DBC는 저장소의 `tools/ars510_offline/dbc/ars510_radar_bus.dbc`를 쓴다. 공개 배포에서 보조 코드가 `validation/native`에 있다면 배포 setup이 해당 경로·Carrot 소스 경로를 지정해야 한다. 운영 Params를 설정하거나 실차 제어를 활성화하는 재현 명령은 없다.

주요 결과 파일은 `paired_results/summary.json`, `paired_results/default_regression.json`, `stop_inspection/observation.csv`, `brake_inspection/observation.csv`, `coupled_sensitivity/summary.json`, `witness_sensitivity/summary.json`이다. root의 실시간 장기 검증은 별도 worker·별도 시각/해시 기록이며 이 문서의20~45초 가상 주행을 실제1시간 검증으로 합산하지 않는다.

## 남은 확인

1. 실제 ECU/펌웨어 식별과 실제0x235/0x237 대상이 객체목록의 동일 물체와 일치하는지 확인해야 한다. 현재 `carFw=0`과 CAN ID 존재만으로는 확정하지 않는다.
2. missing/idle/stale ACC 관측의 fused 급제동 실패는 미해결이다. 필터 숫자를 임의로 바꾸거나 상태를 추정하지 않았다.
3. 실제 정지 대상·급제동·물체 소실·끼어들기 구간의0x80/0x85/0x235/0x237, B4/24, modelV2/liveTracks/radarState/longitudinalPlan/carState/carControl를 같은 시각으로 추가 검증해야 한다. 거리·상대속도·제동 응답에는 실물 기준이 필요하다.
4. PCS/AEB 유지·운전자 개입·프로세스 상태 감시·실제 장치 타이밍·타이어/노면 제동력은 이 명목 폐루프의 합성 입력으로 입증하지 않는다. 실제 LongControl 호출의 active=True와 I/O 검사True는 명목 주행 가정이며 전체 controlsd 권한 검사의 대체가 아니다.
5. Konik 실제 카메라 프로파일·신호 인식은 별도 camera/signal 검증 결과로 판단해야 한다. 본 문서의 합성 ModelDataV2는 실물 인식 정답이 아니다.
