# 실제 ARS 로그와 전체 호스트 연결의 읽기 계약 감사

현재 준비 코드는 원본 CarParams의 radarUnavailable=True를 유지한 offline=True ARS 어댑터와 독립 mode1 DPath 인스턴스를 사용한다. 새 run_file 경로는 실제 순정 CAN 전체를 C RX로 전달하고, 원본 CarState의 PCM OFF·기어·페달·문·벨트 값을 보존하는 방향이다. 이 점은 코드에서 확인했다. 다만 CarState 표본 유지·빈 CAN placeholder·수신 시각 가정·스키마 변환·최종 타임라인 소비는 별도 검증이 필요하다. 데이터 경로를 연결했다고 원래 차량 권한이나 실제 CAN 파서·센서 수신 건강까지 검증했다고 말할 수 없다.

이번 단계는 **읽기 감사만** 수행했다. 새 시험/시뮬레이션/도구 실행, 코어·기존 helper·native·원본 결과 수정은 하지 않았다. 작성 파일은 이 문서 하나다. B에게 새 요청이나 메시지를 보내지 않았고 root에만 읽기 발견을 전달했다. 준비 파일은 다른 담당자가 작성 중이므로 이 감사는 읽은 코드 상태와 실행 전 검증 항목을 구분한다.

## 읽은 범위와 이미 존재하는 결과

`work/ars_host_can_replay/IO_SCOPE_PLAN_KO.md`, `actual_stream.py`, 이후 생성된 `run_file.py`, `whole_io.py`, `whole_inputs.py`, `whole_objects.py`, `log_io.py`, `profile_inputs.py`, `compare_offline.py`, 익명 input_profile/offline_comparison JSON을 읽었다. 생산 source의 Ars510OfflineRadarInterface, RadarInterfaceBase, DPathRadarD, effective_radar_track_mode, card/SelfdriveD 및 Toyota C 안전 훅도 대조했다.

다음 수치는 다른 담당자의 보존된 익명 JSON을 읽은 값이다. 이번 감사자의 신규 실행 결과가 아니다.

| 파일 alias | 기존 offline replay 점/모델 처리/레이더 선행 선택 | 읽은 입력 상태 |
|---|---|---|
| log_a |246점/623모델/175레이더 선행 선택 |CarState3,362개 중 brake2,986/belt1,497/drive1,295, PCM available/enabled/positive speed 모두0 |
| log_b |117점/1,019모델/선행0 |CarState6,022개 중 gas4,046/brake612/drive6,022, PCM 상태 모두0 |
| log_c |원본 CarParams 부족, 점0 |차량상태·모델 자료를 채워 전체 호스트 성공으로 만들면 안 됨 |
| log_d |6점/1,150모델/선행0 |CarState6,017개 중 door4,516/belt5,915/brake995/drive41, PCM 상태 모두0 |

합계369점/2,433record/CRC실패0/레이더 선행 선택175는 기존 replay 비교 결과다. CP가 있던3파일의 original_radarUnavailable=True 및 CP불변이 기록돼 있다. profile에는 CarState15,401개·CarControl15,358개가 집계됐다. IO 계획은 원본 CC가 모두 OFF라고 명시한다. profile 자체는 CarControl.enabled/longActive 빈도를 별도로 출력하지 않으므로, 그 OFF 증거를 새 호스트 출력과 대조할 때 입력·생성 출력의 출처를 구분해야 한다.

Panda controlsAllowed=True는3파일 모두0회다. bus0 순정0x343/0x2e4도 각파일에 존재한다. 실제 input_profile의 저장순서 header 역전은 log_a10,225/log_b24,250/log_d18,686회이고 CAN header 역전은0회다. “로그 전체를 header 정렬해도 같은 입력”이라고 가정할 수 없다. livePose·calibration·DM·radarState에 유효성False인 표본도 있으므로 이를 제거하거나 정상값으로 채우면 안 된다.

## 확인된 코드 보존과 제한

| 경계 | 현재 읽은 사실 | 검증·보고 제한 |
|---|---|---|
| 원본 CP | actual_stream.py:44-55는 기록 CP를 메모리 변환해 offline=True adapter 생성. 시작/끝직렬화비교를metrics에넣음 |original CP 부족파일은부족으로반환. host factory CP는다른가정이므로“원본CP가host까지그대로사용”이라고보고하면안됨 |
| 별도 mode1 |actual_stream.py:56-59에서 독립 controller만enable_radar_tracks=1. 운영Params/차량RadarInterface등록없음 |original radarUnavailable=True이면 운영effective mode는-2. 독립mode1이실차레이더지원·종방향활성권한이아님 |
| 실제 CAN 저장순서 |actual_stream.py:105-114는 address/data/src 전체목록을동일순서로adapter에주고원본CAN header사용 |CRC/record순서·DLC/버스·support235/237/B4를삭제·재타임스탬프하지않는지대조. 사용자의rawCAN은출판하지않음 |
| CarState/model/pose |HOST_INPUTS를메모리로복사하고header/선택timestamp만동일offset정규화 |wire layout·필드·enum의의미가현스키마와같다는추가대조필요. unknown/누락값을True로채우면안됨 |
| DPath 판정 |실제source SubMaster와 DPathRadarD.update를사용. rr.errors를radar_state.radarErrors에복사 |DPath의valid와errors는별개. 건강한빈점과임시불가빈점을같게만들면안됨 |
| pose 건강 예외 |actual_stream.py:71-72의ignore_alive/ignore_valid=['livePose']는생산DPathmain과같음 |이는pose가건강하다는뜻이아님. DPathyaw fallback과host/신호의pose필수gate를분리해보고 |
| raw stock C RX |run_file.py:73-79는실제CAN전체를C RX에전달하고VehiclePermissionInput.update를호출하지않음 |복사된합성RX메서드가존재하지만현재실제입력runner에서사용되지않음. 실차수신/MCU준비의증거는아님 |
| 자연권한OFF |run_file.py:82-91는원본CS body표본을유지하며PCM ON을합성하지않음 |원본OFF가host enabledFalse/CcontrolsFalse/relay차단으로이어지는지실제결과에서확인해야함 |
| 원형host 계산 |실제Card/SelfdriveD/Controls/VCruise/Carrot/MPC/CI.apply를연결하도록작성 |CI.update는원본CS를반환하는IO대체. 실제ToyotaCAN상태파서를실행했다고보고하지않음 |
| 운영·차량 |실제CI.init는sink, TX는메모리반환/C훅검사 |운영Params·Panda·ECU/PCS/UDS·실차활성/송신의검증아님 |

`effective_radar_track_mode`는 Hyundai 외 차량에서 radarUnavailable=True이면-2를 반환한다(`carrot/radar/__init__.py:4-12`). 원형 DPath의 near-front 유지정책도 exactRAV4 directLong이면서 radarUnavailable=False일 때만 켜진다(`radard_dpath.py:105-107`). 독립mode1로override한단일검증instance를운영factoryCP의자동지원으로연결하면안된다. 어댑터는offline=False를거절하고exactRAV4/RADAR_ACC를검사한다(`ars510_offline.py:87-91`).

## 숨은 정상값 대입·삭제 위험의 위치

복사된 `whole_inputs.event`는 valid=True, canValid=True, drive, 정상door/belt,15m/s/75km/h, 정상pose/calibration/device/DM/process를만드는합성factory다(`whole_inputs.py:44-59`, `:79`, `:120-125`). `VehiclePermissionInput.update`도wheels15/torque0/brake/PCM을합성해C RX에넣는다(`:24-30`). 이함수들을raw replay에서그대로사용하면원본권한OFF·브레이크·기어·문·벨트·순정송신을정상조건으로덮는위험이있다. **새run_file은그event/update를호출하지않고실제timeline을사용하므로현재runner에그문제를확정한것은아니다.** 향후counterfactual ON profile이추가되면원본OFF replay와별도실험으로명시해야한다.

반면현재 `CardInterfaceIO.update`는원본CS body를받으면서도gvc=0, pcm_acc_status=8 또는0, pcm_follow_distance=3을대입한다(`whole_objects.py:151-154`). actualGVC=0가정은run_file보고서에명시돼있다. 이 값들은정상stock ECU피드백을읽은것이아니다. 원본body의door/belt/drive/gas/brake/PCM 상태와이내부stock가정을섞지말고, 실제CI.update/stock파서미실행을분리한다. 실제GVC·피치·PCM상태·follow거리별제어/회생반응증거로확대할수없다.

현재 `run_file.py:84`는CarState의원본Event.header와event.valid를버리고body만 last_cs로저장한다. 이를매100HzCard가새메시지header로발행하므로downstream의CS alive/frequency는**명시한표본유지IO의새발행**을검사한다. 마지막원본CS의획득/발행/수신나이가최신이라는증거가아니다. sourceCS event.valid와body.canValid가다른경우도별도로보존·대조해야한다. 이번profile의CS event.valid가모두True여도일반적인유효성보존을추정하면안된다.

현재actualCAN을C RX에넣은뒤 `run_file.py:80-81`은Card쪽버스에valid=True/현재header의빈CAN event만발행한다. 실제ToyotaCI.update 대신CS body반환을쓰므로sourceCAN파서·CAN timeout의부정자료경로를전건검증한것이아니다. 원형Card.state_update의can_rcv_valid는패킷내용이아니라can_strs개수를보는경로도있다(`card.py:229-237`). 빈packet이있다는사실과실제프레임수신·state freshness를혼동하지않는다. rawC RX와ARSdecoder에는실제frames가남아있다는현재source보존사실도같이명시한다.

CameraInventoryIO는ROAD/DRIVER/WIDE 스트림이있다고반환하고, external inference fault 파일은AbsentFaultFile로격리한다(`whole_objects.py:63-68`, `:230`). 실제카메라서비스수신자료를쓰더라도이경계는장치inventoy/원형외부fault준비증거가아니다. 부족한manager/DM/sensor자료를추가합성하거나source의ignore목록을늘려baseline을만들면그범위를명시해야한다. currently enabled/all_checks/controlsAllowed=True 직접고정을읽은runner에서찾지는못했지만, 그사실만으로모든helper·최종정상조건이실물이라는뜻은아니다.

## 레이더 오류·임시불가·timeout 전파

Adapter 초기rr는radarUnavailableTemporary=True이고liveTracks.valid는rr.errors가없을때만True다(`actual_stream.py:79`, `:120-129`). 원형DPath.update는radar_state_valid=sm.all_checks와rr.errors복사를수행한다(`radard_dpath.py:113-118`). sourceSelfdriveD는invalidRadarState의canError/radarUnavailableTemporary/radarFault/wrongConfig를각원형event로연결한다(`selfdrived.py:426-446`). 새로운host에서오류를지우고lead만옮기는것은금지해야하며, invalidFalse와healthyemptyTrue가원래그대로읽히는지확인한다.

Adapter는partial/missing/CRC·순서/DLC 오류·timeout에서history를비우고빈오류결과를낸다. 현재actual_stream은**CAN event가올때만**adapter.update_carrot를호출한다(`:114`). CAN전체가멈추고model만계속되는구간에서는새adapter timeout출력이없을수있고, 마지막rr.errors와별도로원형liveTracks alive가만료될수있다. 이가능성은읽기에서예측한실행전항목이다. radarError를즉시내는결과와수신aliveFalse만생기는결과를나눠야한다. 어댑터에100Hz빈입력을넣는추가실험을선택해도stored-header기존decoder대조와다른수신clock실험으로표시하며원본record수를늘리지않는다.

현재 첫DPath실행은have_state와tracks_time을얻은뒤model이도착해야한다(`actual_stream.py:130`). 초기빈radarState를정상True로채워startup를통과시키면안된다. 원형DPath의modeltrigger와host수신기에서아직보지못한상태는그대로missing/invalid로남겨야한다.

## 원본 순서·header·receiver clock의 계약

Actual_stream은저장순서를유지하고delivery_ns=max(이전까지header,현재header)를사용한다(`:91-94`). 이것은단조화된**배달시각가정**이지실제collector수신시각이아니다. 순서를보존해도한시각에여러message가몰려FrequencyTracker가계산하는주기나conflation이원본producer의주기와달라질수있다. header역전이많은자료에서는원본발행·획득·저장순서·호스트100Hz수신을각각기록해야한다. header정렬이나동일시각에새record주기를부여하면이미검증한엄격0x80조립과의비교가깨진다.

Current_event는현재Event로wire재해석하고logMonoTime과양수timestampEof/timestampSof/timestamp에동일offset을적용한다(`:17-30`). 리스트payload는schema가없어조건을건너뛰는현재버전이다. 이변환의검증은old/current형식의각핵심field·enum·valid가같은지,필드별단위와clockdomain이무엇인지,0/누락값을정상시간으로채우지않는지다. 모든timestamp이름이동일clock/ns라는가정은서비스별로확인해야한다. 같은offset을더했다고MONOTONIC/BOOTTIME원점차이가교정된것은아니다.

Model EOF를써서DPath측정시각을만들고liveTracks의header와차이를전달하는것은원형이다(`radard_dpath.py:79-83`, `:120-133`). CRC완성record시각/최신CS시각/표본headertime/causal delivery/EOF가각기다르다. 저장순서상latestCS가CANheader보다미래에해당할수있음을별도통계로확인하고B4와CS/wheels차이를출처별로해석해야한다. header/EOF가늦어졌다고age를0으로clamp하거나원래invalid표본을지워선택175를맞추면안된다.

Run_file의100Hz끝점은 `range(round((end-100)/.01)+1)`이다(`:70`). round결과가end보다작으면마지막수ms의timeline항목이남을수있다. 실제삭제가발생했다고아직확정한것은아니며, **최종index==len(timeline)**·남은항목개수/종류·처리한CAN/CS/model/derivedRadarState수를대조하는실행전gate가필요하다. 누락을점/hostcount가비슷하다는이유로숨기지않는다.

## 실제 stock RX·원본 OFF·차량 조건을 보존할 검증 항목

| 검증 항목 | 필요한 근거/실패 보존 |
|---|---|
| original CP/factory CP |recorded CP는decoder전후직렬화같음,radarUnavailable=True. hostfactory의fingerprint/directLong/safetyParam/alternativeExperience/PCM/radarUnavailable은별도가정목록으로비교. 실물firmware identity는미확인 |
| input/output 권한 |원본CC/SD/Panda/PCM OFF빈도와현재host enabled/active/CC.longActive/Ccontrols/longAllowed를각출처별집계. 원본CC를새host버스에주입해활성값을고정하지않음 |
| rawC RX 완전성 |bus/address/DLC별원본개수와C에전달개수·거절/유효성개수를대조. stock0x343/0x2e4·PCM/brake/torque/wheels삭제없음. Ctimer/RX검사/relay결과·hook설정/추가가정기록 |
| stock relay 차단 |ToyotaC는bus0 stock0x2e4,비stocklong일때0x343을generic_rx_checks에전달(`safety_toyota.h:140-145`). relay/권한차단을초기화·filter·허용setter로지우지않음. 실제차단발생은실행결과로확인 |
| driver·차체 상태 |gas/brake/standstill/drive·park·reverse/door/belt/button·PCM값이변환전후같음. 원형wrongGear/reverseGear/door/seatbelt/driverdisable event를원인으로보존. 정상값강제로enable하지않음 |
| source health |old/current Event.valid와body.canValid/pose·calibration·DM/parameters flags 대조. source배달·새Card발행·heldCS 나이를별도집계. ignoredpose는생산DPath예외이고healthy 증명아님 |
| ARS decoder |파일별record/CRC·점/sequence/DLC/timeout/drop/reorder·historyreset대조. 완성record와point수다른경로를삭제/임의재생성하지않음 |
| derivedRadarState |liveTracks.errors→DPath.radarErrors→host의직렬화값/valid가일치. temporary/error빈점과정상빈점 구분. canError→event 및missingStatestartup보존 |
| DPath→계획 |175선택의기존독립비교와actualDPath fullupdate의health·시각차이설명. sourceRadarState lead도같은mode/model/clock에서실제로planner가받았는지집계. 부족/invalid상태에서lead성공만골라전체성공으로보고안함 |
| host·MPC·CAN/C |정상초기화가막히면그상태보고. native solverstatus/원형계획·LoC·Toyota생성·DBC/정의checksum/Caccept·deny를분리. expected_tx=None인복잡한조향을“전건C판정맞음”에포함하지않음 |
| 범위·비공개 |actualCAN/trackID/좌표/절대원본time/GPS/FW/개인정보는메모리만. 보고서는alias/상대시간/익명개수. generatedCAN행도허용항목만저장하고rawpayload/derivedprivate좌표를전체dump하지않음 |

현재generated_rows에는메모리생성CAN payload/절대정규화time·decoded_signals가들어가지만run_file의공개JSON은aggregate만사용한다. 원형로그그대로의timeline나CS/model dict, rawstockpayload,actualtrackID를추가보고파일로직렬화하면privacy경계를넘는다. 제어기0x411 PCS 표시/0x750 tester-present생성·메모리C허용은PCS/AEB유지·ECU초기화증거가아니다.

## 현재 확인과 미확인

확인된코드사실: originalCP+offline=True와독립mode1,CP불변검사,저장순서실제frames,원형DPath오류복사,원형수신기,새runner의rawC RX와PCM OFF/body조건보존,actualCI.update대체와GVC/stock가정,상대시간·익명aggregate보고방식이다. 기존offline/profile결과는읽었다.

실행전예측/검증필요: heldCS가fresh해보이는효과·sourceevent.valid보존,빈CAN의timeout/파서한계,끝점timeline잔여,같은receiver clock에몰린header의frequency/conflation,스키마의미·timestampdomain,실제stockrelay차단및전체host의원본OFF보존이다. 이번감사에서이를새실행으로확정하지않았다.

실차활성/송신은금지범위다. firmware·ECU모델·ARS live·actualToyota수신파서·MCU heartbeat·Konik/ARM빌드·이미지인식·실차회생/제동/PCS·AEB안전성은이코드읽기로입증되지않는다. 전체host가원본OFF/차체/건강/stockrelay로막히면그것을성공적으로보존한관측으로보고하고,decoder/DPath/native계획/메모리CAN각모듈완료와실제운용가능성을분리한다.

읽은 준비 코드 버전의 SHA256은 IO_SCOPE_PLAN_KO.md=`266cc2f7513cc89489207a04cb45c3386847cb9d63242238344684789fa49ffe`, actual_stream.py=`f5dab256a30bfa45bdb965a03ab25c2ac8f33915d3979771557533fe392291c5`, run_file.py=`6fa48f9900fb0e4a3bc9e41a38b5f8ee21883e242d61a6453f20acfecb1a2a58`이다. 보존 input_profile.json=`742a1b5548c955f4b4ba88b841cc97eeb4a7e56b947fafb248d2830a4922da9f`, offline_comparison.json=`7b4f863848f22dbf223f6ad95dd56b825fb519fed0ce8d3f4092cdfa707ae8a0`을 읽었다. 이는 source 변경 금지 조건에서의 읽기 버전 식별이며 실제 재생 gate를 새로 실행한 해시가 아니다.
