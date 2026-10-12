# 원본 CS·CAN 묶음 → offline ARS 어댑터 직접 재생

원본 CarState.radarInput과 독립 CAN stream을 원형 RadarCanBatches로 묶어, 정확히 해당 CS의 vEgo/aEgo/receiveMonoTime을 offline Ars510 어댑터에 전달했다. 기존 CAN Event/latestCS/header 직접 경로는369점·2,433record를 다시 재현했다. 새 두 시각 가정에서는 **367점·2,400 또는2,399record**였다. 수치를맞추는상수·필터·시각변경은하지않았고, 차이를그대로보존했다.

log_b에서 없어진2점은 첫CS 이전에 출판된 점이 아니다. 직접경로에서만완성된2개record의점이며, 두record 모두새경로에서staleEgoState로거절한CAN 묶음범위와시간구간이겹쳤다. 한record는완성packet자체가거절범위안이고다른record는중간구간이겹친다. 새경로에서record를정상디코딩했지만fused필터가그2점을추가로숨긴결과는0이었다. 이현상은선택한저장순서→consumer clock가정의결과이며 실제차량의collector지연이동일했다고입증한것은아니다.

## 실행·준비 오류·동결

허용 신규도구 `paired_adapter_replay.py`만구현했고출력은신규 `paired_run01` 아래에썼다. 원래probe/canonical분류파일 및그결과는변경하지않았다. 최초에는보호source목록에존재하지않는decoder.py를적어어댑터실행전FileNotFoundError가났고 `initial_preparation_failure.json`으로보존했다. 실제record.py/objects.py/interface.py 등파일명을확인해수정했다. 데이터나원형어댑터의실패가아니다.

첫 정상직접실행 `paired_run01/results.json`은2026-10-12 **22:57:44.212~22:57:53.935 KST**,처리구간9.723838초였다. 이후레코드기반익명count를추가해차이원인을확인했고각실행·source사본을cause_run02/cause_run03_final/cause_run04_frozen에따로보존했다. 알고리즘변경없이관측count만보강했다. 최종동결실행은2026-10-12 **23:04:51.982~23:05:01.202 KST**,9.220941초,exit0이다. 최종Ruff 직접검사도오류0이었다.

최종source SHA256: `7565826f714ddc91076fa1e5bfda21393a4f48b458210b1cc3f290ee35f95b7d`.

최종 `cause_run04_frozen/results.json` SHA256: `a6a9036eb5a73d1611ca1b23eaff39e5ac6141bc23e5d17f79297826d500a62c`.

준비오류는초기1건을보존했고최종preparation_errors는0이다. source지문과원본파일크기·수정시각은각실행전후같았다. 원본CP직렬화가같고3유효파일의radarUnavailable=True를유지했다. bootstrap은process-local-access-forbidden을반환해운영Params의객체생성/접근을차단했다. offline=True 이외의운용mode/CPflag강제나livehook은없다.

## 비교한 두 경로와 시각 가정

직접reference는기존replay와같이저장CAN Event마다원본CANheader를calltime으로쓰고,저장순서상latestCS를사용한다. 첫CS전vEgo/aEgo초기값0인기존reference정책도별도로표시했다. 그런초기화가 실제차량ego관측이라는뜻은아니다.

새paired 경로는원형RadarEgoSample.from_car_state와RadarCanBatches를독립stream으로그대로사용한다. 각CANpacket의원본header/payload/src/DLC/순서와CS metadata는변경하지않았다. 정상take의해당CS vEgo/aEgo/receiveMonoTime으로adapter.update_carrot를호출했다. 메타에없는402개CAN을warmup이나추측ego묶음으로넣지않았다. 원형batch오류뒤다음정상묶음에서는생산radarcan과같이adapter를재생성하고그횟수를따로집계했다.

| gate now 이름 | 사용한 가정 | 공통 제한 |
|---|---|---|
| input_max |저장순서에서CAN/CS header의이전까지최대값. 다른서비스header는clock에넣지않음 |실제receiver/collector시각이아님 |
| storage_max |모든저장Event header의이전까지최대값. model/device등다른서비스도포함 |인과배달가정의추가비교이며실제collector와동일하다고말하지않음 |

두경로모두adapter의외부calltime은원본CS.receiveMonoTime이고,내부packet마다원래CANheader를유지했다. gate now와adapter calltime을혼동하지않는다. 현재100ms source기준을늘리거나,now/receive를통과하도록바꾸거나,header정렬·가짜record주기를만들지않았다.

## 파일별 직접 결과

| alias | 기존direct record/점 | paired input_max record/점 | paired storage_max record/점 | CRC 실패 |
|---|---|---|---|---:|
| log_a |481 /246 |479 /246 |479 /246 |전경로0 |
| log_b |1,021 /117 |991 /115 |990 /115 |전경로0 |
| log_c |원본CP 부족 |추측CP 없이부족으로종료 |추측CP 없이부족으로종료 |판단대상없음 |
| log_d |931 /6 |930 /6 |930 /6 |전경로0 |
| 합계 |2,433 /369 |2,400 /367 |2,399 /367 |0 |

모든출판점의필수거리/횡위치/상대속도/절대속도/가속·jerk 유한값검사에서비유한점은0이었다. 개별값·좌표·객체ID는저장하지않았다. 같은완성record가양쪽에서점을출판한경우출판점**개수**차이는0이었다. 좌표·속도·가속의전값이같다는검사는아니다.

| alias | 원본CANpacket | source CS | input_max accepted /stale | storage_max accepted /stale | paired CANpacket 사용(input/storage) |
|---|---:|---:|---|---|---|
| log_a |3,507 |3,362 |3,362 /0 |3,362 /0 |3,370 /3,370 |
| log_b |6,166 |6,022 |6,002 /20 |5,997 /25 |6,010 /6,005 |
| log_d |6,161 |6,017 |6,016 /1 |6,016 /1 |6,031 /6,031 |
| 합계 |15,834 |15,401 |15,380 /21 |15,375 /26 |15,411 /15,406 |

원형CAN buffer의512개상한으로삭제된packet0,최종pending state0,최종미결합buffer0이다. 로그중CS보다먼저CAN이필요한끝점에도달하지않아take가잠시pending한횟수는A32/B194/D59회이며,이를오류나영구유실로세지않았다. 빈묶음은0이었다.

402개의metadata미결합과별도로stale gate에서입력clock21개/storageclock26개CS를거절해추가CAN을사용하지않았다. source범위밖CAN총discard는input_max423개,storage_max428개다. 처음CS앞396/CS범위사이6/끝뒤0이라는기존402개분류는동결그대로다. 추가로버린21/26개는이번clock가정에서의나이gate영향이며metadata가누락됐다는뜻이아니다.

## record/점 차이의 확인 근거

log_b의direct첫CS전완성record는24개였지만그구간의출판점은0이었다. 새paired는그초기미결합CAN을관계없는CS에붙이지않으므로직접경로의초기decoder상태와다르게시작한다. 초기·범위사이부족,gate거절및재생성으로record수가달라질수있다.

log_a는direct와paired 점246개는같았지만paired에sequence_error1/orphan64가있고record2개가적었다. log_b는input/storage에서각4/8번외부batch-error후adapter재생성,orphan453/438,record30/31개감소였다. log_d는각1번재생성,sequence_error1/orphan153,record1개감소였다. CRC잘못해독으로점수를맞춘현상은관측하지않았으며각경로CRC실패0이다.

log_b의없는2점은각각완성record의비공개시각키를메모리에서대조해확인했다. 두경로공유출판record의점개수차이0,paired에서record를해독했지만해당점을withhold한경우0,paired에서record자체가완성되지않은direct점2였다. 두record구간모두거절된batch범위와겹쳤고그중1개의완성packet이거절범위안이었다. 개별record키/절대시각/객체ID/좌표는JSON에쓰지않고count만남겼다. 이것은가정한receiverclock에서의반례분리이며실제차량에서2점이유실됐다는증거는아니다.

## 시간·오류·timeout 분리

| alias | input_max gate now−CSreceive 최대(ms) | storage_max 최대(ms) | paired call−마지막완성record 시작 범위(ms) |
|---|---:|---:|---|
| log_a |90.212837 |97.915112 |27.449665~49.124799 |
| log_b |189.163281 |189.532865 |27.104257~47.181578 |
| log_d |100.373853 |102.572810 |27.949231~43.195465 |

앞선metadata probe는기록CS의**자기발행header**를now로쓰면15,401개모두100ms안이었다. 이번에는저장순서에서이미본더새로운header를now로잡았다. 그차이가stale gate21/26개를만드는것이며,두검사가같은수신clock를사용한것이아니다. 저장순서가실제독립socket수신순서인지원본만으로확정하지않는다.

paired call−record완성header는A0.056459~0.150524ms/B0.062764~1.950625ms/D0.039584~2.473651ms였다. 최초record프레임시각과마지막완성프레임시각을구분했다. 이번입력에서한call에복수완성record는0이므로통계가각완성record에해당한다. 원래collector와현재wall clock의직접비교가아니다.

adapter 자체timeouts/assembly_timeout/CRC/비유한input/시간역전은전경로0이었다. 이것을full radarcan processingTimeout·CAN전체inputTimeout까지통과했다고보고하면안된다. 소켓/main20ms poll·실제CPU대기·PM error발행·host는실행하지않았다. Adapter의반환오류와원형batchgate오류를분리했다. 반환RadarData오류수는direct1,161/input912/storage929이며,입력호출범위와decoder초기화가다르므로오류수가적다는것을개선의증거로해석하지않는다. batch gate 오류는별도21/26개로보존했다.

## 재현과 완료 범위

원본파일·생산source·.so·기존결과·outputs/release는변경하지않았다. 기존bootstrap만사용해설정저장소접근을프로세스에서차단했고,originalCP+offline=True만사용했다. DPath·175선택·MPC/host·Toyota송신·PCS/AEB·실차활성·실제ARS ECU/FW/MCU 준비는이번단계에서검증하지않았다.

```powershell
# 프로젝트 루트, 기존 venv, 새출력폴더만사용한다.
& work\venv\Scripts\python.exe -B work\radar_input_contract_probe\paired_adapter_replay.py --output-dir work\radar_input_contract_probe\paired_run01\independent_replay
# 대표파일만확인하려면 --aliases log_a --clock-bases input_max 추가
```

이도구는동결probe.py를입력위치·원형순수class로더에사용하고canonical분류파일의지문도읽는다. 복사재현시세파일을같은새work 하위폴더에함께두거나기존source경로에서새output-dir를사용하면된다. 기존results.json이있는폴더는덮어쓰지않는다.

완료:원형독립batch→정확CSreceive/ego→offlineadapter의직접실행,직접369/2433경로대조,두clock가정·기록범위·CRC/오류/점·record시각차이의익명분리다. 미완료:실제collector clock확정,full radarcan/소켓연결,DPath/host coupling,실차호환·인식·안전성. 기존369/175에맞추기위해데이터·필터·시각·threshold를변경하지않았다.
