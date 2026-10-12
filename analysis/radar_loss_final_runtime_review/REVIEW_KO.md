# 감속 전달 최종 wrapper의 module binding 독립 읽기 검토

최초 final 준비 실패는 **이미 download clone에 묶인 openpilot package가 옛 Planner를 찾았기 때문**이다. 새 wrapper는 main Planner를 정식 module 이름으로 명시 로드하고, frozen MPC/Cython 경로와 지문을 따로 검사한다. 후보 exec는 다른 방식으로 새 전체 Python 본문을 실행한 검사였으며 old __file__ 표식만으로 옛 본문이 실행됐다고 판단할 수 없다. 두 방식과 과거 파일 지문 범위를 구분해야 한다.

이번 감사자는 source·wrapper·보존 결과·파일 지문을 읽고 비교했다. wrapper·MPC/C·benchmark·차량 송신을 새로 실행하지 않았고 driving source·.so·기존 도구/결과·outputs/release를 수정하지 않았다. 허용된 이 새 문서만 작성했다. root의 직접 실행 결과와 이 감사자의 읽기 확인은 아래에서 분리한다.

## import 순서로 확인한 원인

1. whole_io는 main 경로와 LAB/native_sim을 sys.path에 넣고 offline_io.prepare를 호출한다.
2. 실제 offline_io는 download_e2e 쪽 파일이다. 그 REPO_ROOT는 download clone이며 prepare는 해당 root/opendbc 경로를 앞에 넣는다.
3. prepare 안에서 openpilot.cereal과 openpilot.selfdrive.controls.lib.longitudinal_mpc_lib를 import한다. 이때 openpilot 및 중간 package들의 __path__/sys.modules가 download clone에 묶인다.
4. whole_io가 이후 sys.path 앞에 main을 다시 넣어도 이미 존재하는 package.__path__와 module cache는 자동으로 바뀌지 않는다.
5. MPC package에 새 frozen BUILD 경로를 prepend하면 그 안의 long_mpc는 선택될 수 있지만 sibling longitudinal_planner는 기존 parent package 경로를 따라 download 파일을 찾는다.

따라서 sys.path와 현재작업폴더가 main이라는 사실만으로 모든 imported module이 main이라고 주장하면 안 된다. 이것은 filesystem namespace·module cache 문제이며 새로운 solver 수렴 실패나 실제 차량 오류가 아니다.

## 최초 실패·후보 overlay·최종 명시 loader

| 단계 | 실제 읽은 코드 경계 | 결과/의미 |
|---|---|---|
| run_final_initial.py |mpc 새 BUILD·planner 일반 import·Cython import 뒤 __file__ assert |planner assert가 run.main 이전에 있다. final_preparation_failure는 cases_executed0·native_rebuiltFalse인 준비 실패 근거 |
| run_candidate.py |두 후보파일 전체를 compile(content,candidate_path) 후 기존 module.__dict__에서 exec |새 함수/클래스 정의를 실제로 바꿔 사용한 Python overlay. __file__/__spec__/parent package 표식은 원형 import 값이 남을 수 있음 |
| run_final.py |같은 정식 planner 이름의 spec_from_file_location(main_path), module_from_spec, sys.modules 등록 뒤 exec_module |일반 import가 선택한 download 경로에 의존하지 않고 main Planner 본문을 명시 로드 |
| Chain 생성 |__init__ 안에서 그 뒤 `from …longitudinal_planner import LongitudinalPlanner` 실행 |이 호출은 새 sys.modules module에서 class를 받는 코드 경로. 사전에 저장한 old class 변수 전부를 자동 교체하는 것은 아님 |

최초 wrapper의 assert 이전에도 import/top-level Python 실행은 있었다. ‘cases0’은 전체 imports조차 없었다는 뜻이 아니라 실제 case/host 실행을 시작하기 전 실패했다는 의미다. 초기 실패를 native test 실패 또는 새 감속 기능의 실패로 합산하지 않는다.

candidate exec는 module.__dict__를 완전히 비우지 않으므로 새 본문에 없는 이전 global/import가 남을 수 있고 metadata도 old이다. 하지만 현재 source를 읽으면 **두 전체 본문의 새 class 정의**를 차례로 실행했으며, Planner 본문의 from-import는 앞서 덮어쓴 MPC class를 가져온다. candidate 파일의 SHA와 실행 body를 근거로 보고하고 ‘original __file__ 경로의 파일이 수정됐다’거나 ‘전체 main module tree를 새로 import했다’고 말하지 않는다.

최종 명시 loader도 모든 dependency package를 main으로 바꾸지는 않는다. 같은 parent package의 옛 attribute/다른 module/앞서 저장된 class 참조가 남을 수 있다. 현재 Chain의 from-import 위치와 local planner 변수는 새 module을 사용하는 경로지만, 전체 process의 모든 namespace를 정리한 결과로 확대하지 않는다. Params/messaging·physical I/O 예외 역시 계속 남는다.

## body·경로·지문의 구분

| 근거 | 확인되는 내용 | 확인되지 않는 내용 |
|---|---|---|
| __file__/resolved path assert |이번 import가 가리킨 실제 모듈 파일·준비 전제 |후속 exec로 본문을 바꾼 module의 모든 동작 동일성·loaded page 전체 |
| compile filename과 candidate SHA |실행한 후보 텍스트 출처·그 class/body 변경 |__file__ 자체가 candidate로 바뀐 것 또는 모든 dependency import 동일성 |
| declared source_before/after |기록한 경로 파일의 실행 전후 byte 불변 |그 파일이 항상 실제 imported module이었다는 증명 |
| frozen MPC Python+native6 전후 SHA |이번 최종 wrapper에서 protected7 파일의 불변 |새 native 수치코드 생성/재빌드·모든 runtime library/메모리 page 전수 검사 |

현재 main/download Planner 텍스트를 읽기 비교했을 때 차이는 새 force_slow_decel caller 및 한국어 주석 두 줄이다. 따라서 이 현재 차이를 과거 검사에 소급해 “과거에도 다른 함수가 실행됐다”고 확정하면 안 된다. 반대로 main 파일의 SHA만 기록해 옛 cache를 쓴 새 패치를 검증했다고도 말할 수 없다. 버전별 실제 module binding을 별도 근거로 보존해야 한다.

두 candidate 파일과 현재 main 수정 파일은 LF 정규화 후 바이트가 같다. raw SHA 차이는 줄끝을 포함한 저장 형식의 차이이며 이 두 파일의 Python 본문 차이가 아니다. 독립 읽기에서 확인한 값은 다음과 같다.

| 파일 | candidate raw SHA | main raw SHA |
|---|---|---|
| longitudinal_planner.py |63ac8ab4d0b00284808f6100d812795e9b7eae0de90c230e9ce97dde33f58617 |ccbbb7a1c2dc0dda3de7c2d2d39890d2a5e77b8ff9d0faca0a2261a9747f2f2e |
| long_mpc.py |8d493b65acc3f5a4273bb436009d9ab99fdc573063e5f0581d23c45147b33b00 |2fa824f243a7438150adedcfebc3d3cf03bccb3447d368f54ee89824fb0c8f5e |

## 최종 wrapper 보존 결과의 범위

읽은 final/runtime_and_behavior.json은 새 frozen MPC Python, main Planner, 새 c_generated_code의 Cython 위치를 기록한다. run_final.py가 이 세 경로를 assert한 뒤 run.main을 호출한다. protected는 MPC Python1개+native6개이며 전후7지문이 같고 현재 파일에도 불일치0이었다. Planner 자체는 그 protected 목록 밖이지만 run.main의 source_before/after에 main Planner SHA ccbbb7…가 기록돼 현재 파일과 같았다. 새 native build=False/actual vehicle TX=False였다.

보존 final/run01은8조건·기존80판정·실패0, source/안전C 불변을 기록한다. wrapper의5개 감속 관측 및 종료시각 판정도True다. 이것은 **root가 직접 실행한 결과를 읽은 것**이며 이 감사자가 재실행한 결과가 아니다. 명시 loader가 실제 사용한 수정 body와 경로를 확정했다는 범위로 제시할 수 있다.

감속 behavior check는 forceDecel+longActive 표본에서 음수 accel이 **한 번 이상** 있었는지를 검사한다. 첫 틱부터 전부 비양수라는 판정은 아니다. 보존 결과는temporary/radar_fault/wrong_config/invalid_without_error 각각 양수CAN11·음수89,producer_stopped 양수28·음수87이었다. 후자에는 오류 감지까지의 정상 구간도 포함된다. ‘음수 관측 True’를 남은 양수 없음·즉시 최대제동으로 확대하지 않는다. 건강한빈값과 validTrue/error 플래그 조합은 양수133 관측으로 별도 유지됐다.

현재 결과는 가상시각·고정 ego·합성 정상 PCM 권한/오류 전이·메모리 생성 CAN/C의 검사다. ARS 원본 객체/DPath 입력 소실·실제 socket/Panda·firmware·PCS/AEB·실차 감속거리·ARM전체빌드를 이 wrapper가 검증한 것은 아니다. 후보 결과, 최초 준비 실패, 올바른 final module binding과 native 지문을 각각 보존한 설명이 필요하다.

## 읽은 wrapper 지문·완료

- run_final_initial.py: b0d4edb5f91cd2eb4877b8bf06d7de5a71fbfaffcf459cc9b9e28c6c85785798
- run_candidate.py: 18fddfd88e62125907b91901f6b917d0b7d6fc05cb50c943766413d8fb096f7d
- run_final.py: 74d8552bc07a6d8e32cdfd745c67e1389d71dc94331c4c7ae5db6af35b057d4b

확인한 원인은 먼저 로드된 package binding이며 새 loader는 해당 Planner 선택을 명시화한다. candidate exec의 body와 metadata 차이를 실제 실행 여부와 혼동하지 않았다. 새 실행·수정·재빌드 없이 현재 파일과 보존 근거를 독립 읽기했다. 위 범위를 넘는 과거 전체 namespace 보증이나 실차 안전 결론은 내리지 않았다.
