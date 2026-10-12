# 새 paired 호스트 통합의 가정 발행시간 범위 읽기 검토

새 B 통합은 **G=storage_max라는 명시적 가정 시각으로 새 liveTracks/radarState 메시지를 만들고 원형 계산을 메모리에서 실행하는 모의 연결 검사**로 해석할 수 있다. 실제 ARS 운영 발행 P, 실제 소켓 수신, 실제 radarcan 처리 deadline이 측정·통과됐다는 뜻은 아니다. 계획서와 결과의 radar.scope/epoch_scope에는 이 구분이 들어 있다. 최종 공개 설명도 같은 한계를 앞부분에 유지해야 한다.

이 단계는 읽기만 수행했다. `paired_host_policy_integration/paired_stream.py`, run.py, IO_SCOPE_PLAN_KO.md, 현재 log_a/b/c/d_first의 결과와 기존시간진단을 읽었다. 새실행, 기존도구·결과·source·outputs/release/.so 수정, 물리제어는 없다. 허용된 이 문서 하나만 작성했고 root에만 보고했다. B 실행 결과의 수치는 **보존 JSON을 읽은 값**이며 이번 검토자의 재실행 결과가 아니다.

## 두 검사는 서로 다른 입력 조건이다

| 항목 | 기존 paired_publication_time_probe | 새 paired_host_policy_integration |
|---|---|---|
| 실제 운영 P |미관측 |미관측 |
| S/G 후보의 사용 |상대산술만계산,입력메시지/DPath에주입0 |G를새발행헤더로쓰는명시적모의입력 |
| 원본NS |원본epoch그대로읽음 |wire_event가원본header/nested NS를그대로복사 |
| 새 liveTracks/radarState |만들지않음 |계산결과를실제cereal메시지에담아메모리bus로발행 |
| DPath/host |미실행 |원형DPath.update·host/MPC·Toyota생성CAN/C메모리연결 |
| 실제소켓/처리deadline |미실행 |full_radarcan_loop_executed=False,실제deadline미실행 |
| 입증가능한범위 |F/K/R/S/E 및P후보의조건부상대산술 |선택한가정발행/배달clock에서원형계산이주고받는행동 |

기존 results.json의 P_candidates_used_as_input=False는그진단의사실로유지된다. 새 통합에서 P_assumed=G를입력으로쓴다는조건은그진단과다른실험이다. 두파일의조건을합쳐“미측정P를사용하지않고동일실험에서host까지연결했다”고보고하면안된다. 반대로새통합이선언된가정입력을사용했다는이유만으로기존진단을위반했다고판단할필요도없다.

## 기존 REPORT 문구의 해석

기존 REPORT의 “P를CS header나freshnow로채워DPath·수신gate가통과했다고보고할수없다”는문구는 **실제측정된운영P/운영수신deadline의검증으로보고할수없다**는범위다. 가정이라고표시한모의메시지·시각을입력해계산을검사하는것까지일괄금지한다는뜻으로확대해석하지않는다. 기존문서도 P=S/G를가정의산술로구분했다.

새 통합의허용되는표현은 “P_assumed=G를입력한오프라인모의clock에서원형DPath/호스트의계산·오류전달·기록OFF권한행동을관찰했다”이다. 허용되지않는표현은 “실제ARS P가신선하고동기화돼150ms/skew와100ms deadline을통과했다”, “실제radarcan발행/소켓수신까지실차와같다”이다. 가정을실물측정값으로승격하지않으면두설명은모순되지않는다. 이검토에서는동결기존REPORT를수정하지않았다.

## 코드에서 확인한 G 발행

paired_stream.py:86-90는storage_max일때이전까지모든기록header의최대값을now_ns로쓰고clock.now에넣는다. 원본input은wire_event로같은header와nestedNS를복사한다(:25-28). 그뒤새결과메시지는다르게생성한다.

- `:140-143`: 새liveTracks의logMonoTime=now_ns,같은now_ns의Delivery로메모리bus에넣는다.
- `:147-152`: model event에서원형DPath.update를호출하고새radarState의logMonoTime=now_ns로직렬화한다.
- `:159-164`: full_radarcan_loop_executed=False와“새발행헤더는명시한가정clock·소켓/main전체inputTimeout/실제처리deadline미실행”을metrics에기록한다.

따라서wire_event의“freshnow치환없음”주석은 **원본입력header/NS**에해당한다. 새derived메시지의가정header까지없다는뜻은아니다. 새RadarState header도liveTracks의P와다른메시지발행역할이며,둘다이모의clock에서계산됐다고명시해야한다.

G는저장된producer header에서정한clock이며offline CPU가실제로해독을끝낸MONOTONIC 시각을계측한것이아니다. P_assumed=G는원형message schema에들어가는모의header일뿐이다. native 계산을실행한것과그계산의실제운영스케줄·publication latency를검증한것은분리한다.

## 현재 계획서·결과 scope의 충분한 부분과 보강할 설명

IO_SCOPE_PLAN_KO.md:20는호스트100Hz격자·표본병합/배달나이가가정이며실제소켓스케줄러동작을주장하지않는다고명시한다. `:26`은 BOOTTIME/MONOTONIC 공통축이재생가정이며실제장치동등성·절전이력의증명이아님,기존운영liveTracks를입력하지않음,새ARS shadow의가정P를별도사용,실제wall처리시각을주장하지않음을명시한다. 사람이이계획서를읽는경우발행시간범위는충분히구분돼있다.

현재유효3결과의nested radar.scope는가정clock/실제deadline미실행을기록하며full_radarcan_loop_executed=False다. top-level epoch_scope는BOOTTIME/MONOTONIC 숫자공통축의가정,scope는오프라인비활성호스트·실물펌웨어/차량/PCS/회생/ARS live 미검증을명시한다. physical_ci_init/physical_tx/actual_ci_update도False다. 이는운영시간을검증한것으로과장하지않는근거다.

최종요약은중첩scope를따로찾아야만한계가보이지않도록, **P_assumed=storage_max/실제P미관측/소켓·processing deadline미검증**을맨앞에함께적는것이좋다. 기계판독필드에도P_actual_observed=False,P_assumed_source=storage_max,P_candidates_used_as_input=True,actual_socket_timing_verified=False,actual_processing_deadline_verified=False처럼역할을분리할수있다. 이는읽기보고서의메타데이터설명후보이며이번에새정책·코드를구현한것이아니다.

`RESULTS_KO.md`라는최종요약파일은이번읽기시점에없었다. 현재계획서·source·결과JSON에대해범위를확인한것이며,아직읽지못한최종공개문구까지검토통과했다고보고하지않는다.

## 결과 수치가 뜻하는 범위

읽은log_a_first는가정clock에서DPath계산→호스트계획이레이더선행을소비한모델175개를기록한다. nativeMPC623회,status오류0,host_enabled/active/longActive와C권한활성은0이었다. 이는오프라인데이터경로와원형OFF조건의관측이지실제P/운영활성·실차성능의확인이아니다. 175라는수가기존reference와같아도P가원본에기록됐거나그clock가정이실물과동일하다는증거가되지않는다.

log_b_first는nativeMPC986회/물리레이더선행소비0,log_d_first는1,150회/0이고모두host활성0이다. log_c는원본CP부족이다. 모듈별실행·보존scope를명시할수있지만이수를기존100ms deadline 통과/real100Hz소켓시간·실물ARS호환과합산하지않는다.

원형DPath는liveTracks header를radar_time으로읽고camera EOF와의차이를쓴다. 그러므로P_assumed=G가source algorithm의실제입력이라는점은인정하되,그가정에서나온lead선택/수신건강판정이라고해석한다. 미래운영P에는CS전달·ARSC++/Python시계영역·radarcanpoll/해독/직렬화·receiver스케줄링의차이가있을수있다. 그추가시간이관측되지않은채후속skew·deadline의실물동등성을확정하지않는다.

100ms batch gate는그G와원본R의비교,150ms DPath skew는E와가정P_G의비교다. 서로다른의미를“신선도전건통과”한묶음으로보고하지않는다. fullradarcan의process 후now 검사와no-input poll timeout은미실행이고, 메모리receiver의G/100Hz배달역시실제wall장애를입증하지않는다.

## 읽은 지문·완료와 미완료

paired_stream.py SHA256: `f1dbd4cc8888ce8908528378058d082dc0be24f681123bc24efad8bf2bb24a6d`.

run.py SHA256: `8c76d85216784f569816d662cc226c6426a6a032f6e5e32de6a554b48735ec06`.

IO_SCOPE_PLAN_KO.md SHA256: `8eea7e0e501be75ab4355b939c3d33320b301ef66ad89a7c921ce5da8bb37c4f`.

기존시간REPORT SHA256은 `1a70acc0bcce6f179b3e5b90317cec65b05c0efa5c2a66044f3c577abc167014` 그대로였다. 이읽기수치는새실행gate가아니다. 준비파일은다른담당자의현재버전이므로지문식별과추후stage동기화를구분한다.

완료는P가정과실제미관측P·소켓/처리deadline의scope대조및두검사의차이정리다. 실제P/collector/clock동기/운영deadline/실차안전성,최종공개문구검토는미완료다. 새실행이나기존file/source/.so/outputs/release수정은하지않았다.
