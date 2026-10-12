# 원본 RadarInput 존재·CAN 묶음 정합성 직접 진단

원본 CarState **15,401개 전부에 radarInput이 실제 wire 포인터로 존재**했고, firstCanMonoTime/lastCanMonoTime/canPacketCount/receiveMonoTime 네 값도 모두 양수였다. 저장된 CAN header에서 각 묶음의 첫·마지막 시각과 패킷 수가15,401개 모두 정확히 일치했다. 원본 메타데이터가 없거나0이어서 새 레이더 경로를 쓸 수 없다는 설명은 이3개 로그의 CS 자료에는 해당하지 않는다. log_c는 CarState가없어근거부족이다.

최종 고정 도구는Windows 격리 venv에서 직접 실행해exit0으로 완료했다. 22:35:34.274 KST 실행은처리구간1.212369초였고,그뒤root 요청의 --output-dir 호환 옵션·기존results.json 덮어쓰기 거절·bytecode 외부생성 방지만 추가해 run03_frozen으로4파일을한번더직접확인했다. 계산값·집계는같았다. source/스키마/도구 해시는 각실행의시작과끝이같고 원본파일의크기·수정시각도모두같았다. 새Card metadata 생성,운영Params 접근,CP변경,raw payload/원본절대시각/식별자 출력,CAN송신은없었다. Ruff도직접오류0으로종료했다.

## 직접 읽은 원본 값의 집계

| alias | CarState | radarInput wire 존재 | 네 필드0/누락 | CAN 첫·마지막·count 정확 일치 | 묶음 count 빈도 |
|---|---:|---:|---:|---:|---|
| log_a |3,362 |3,362 |0 |3,362 |1packet3,361회,9packet1회 |
| log_b |6,022 |6,022 |0 |6,022 |1packet6,021회,9packet1회 |
| log_c |0 |관측 없음 |판단 불가 |판단 불가 |없음 |
| log_d |6,017 |6,017 |0 |6,017 |1packet6,016회,16packet1회 |
| 합계 |15,401 |15,401 |0 |15,401 |15,398회 단일packet,3회 복수packet |

여기서 packetCount는 CAN **Event 묶음 수**이고 개별 CAN frame 수가 아니다. pycapnp Reader의 `_has('radarInput')`로 구조 포인터의 실제 존재를 확인했으므로, 스키마가 최신 필드를 선언해 기본0을 읽은 것과 다르다. schema radarInput@93와 네 하위필드도 존재했다. 원본CS event.valid 및 body.canValid는이번15,401개에서모두True였고,CAN event.validFalse는0이었다.

receive 시각 역전/동일값 반복,앞선 묶음과first/last겹침,receive가CS발행보다미래,마지막CAN이receive보다미래,packetCount512초과,빈묶음인데first/last양수 등 진단한 정합성 오류는 모두0이었다. 기록된CAN stream의header역전/중복도0이었다. 정확히매칭한header재사용은0이었다.

원본CAN Event15,834개 중 CS metadata가 가리킨 것은15,432개다. log_a137/log_b136/log_d129,합계402개의CAN header는어떤기록CS metadata에도묶이지않았다. 이는CS metadata의각묶음정합성실패가아니다. 해당CAN이왜CS묶음밖에남았는지는이번도구에서원인분류하지않았으며,실제로소켓에서유실됐다고판정하지않는다.

## 시각의 상대 차이

원본절대시각은저장하지않았고,두원본값이모두양수일때만차이를ms로집계했다. timestamp0과의차이는원본절대시각을드러낼수있어계산하지않았다.

| alias | CS 발행 header − receive 범위(ms) | receive − 마지막 CAN 범위(ms) | receive − 첫 CAN 최대(ms) |
|---|---|---|---:|
| log_a |1.433412~7.381280 |0.051459~8.866567 |87.256220 |
| log_b |1.481875~15.641941 |0.043639~7.467063 |81.903750 |
| log_d |1.411699~18.395472 |0.035574~10.013718 |149.579820 |

source `MAX_INPUT_AGE_NS=100,000,000`은`RadarCanBatches.take`에서 **now−state.receive_ns**를검사한다(`can_batch.py:61`). 가장오래된CAN packet−now를동일식으로검사하는것이아니다. log_d의16packet묶음1개는첫CAN→receive가149.579820ms였지만receive→CS발행은100ms미만이었다. 이를“원형100ms gate 실패”나“신규 threshold가 필요하다”고즉시판정하면틀리다.

## 실행한 원형 코드와 검사 범위

도구는production can_batch.py의 전체 순수 클래스 본문을 그대로 로드했다. 실제기록CS를`RadarEgoSample.from_car_state`로읽고,기록CAN header에맞는묶음을`RadarCanBatches.take`에주었다. payload는 이클래스가읽지않으므로metadata매칭용빈frame목록을사용했다. decoder나차량제어함수의반환값을mock하지않았고새CS필드를생성하지않았다.

다만CS별로독립buffer를만들어파일전체의CANheader범위를확인한것이다. 전체receiver socket순서/queue상한/conflation/실제collector지연을검증한것은아니다. `take(now)`의now는해당**기록CS 발행 header**로정했다. 이가정에서15,401개accepted,missing/stale/pending0이었다. 실제radarcan처리시각이나실제운영100msdeadline의검사라고확대하지않는다.

생산radarcan은추가로CAN전체입력나이와CS입력나이·processingTimeout을보고,reset/빈오류liveTracks를발행한다(`radarcan.py:78-100`). 이번에는그프로세스·socket·Params·차량RadarInterface를실행하지않았다. 실제CarState.receiveMonoTime이관측됐다는것과원본소프트웨어의receiverclock내역을완전히알고있다는것도구분한다.

## 새 host/Card 메타데이터와 원본을 혼동하지 않을 것

생산Card는CI.update뒤에수신CAN의first/last/count와recv_ns로radarInput을새로쓴다(`card.py:254-257`). B의빈CAN placeholder·heldCS 경로에서이값을새로쓴결과는이번원본값의증거가아니다. 원본에는이미정확한묶음메타가있으므로,원본CS관측과새Card생성값의차이는별도비교해야한다.

또한 B current_event는현재Event header와body상위EOF/SOF/timestamp에동일offset을적용하지만,nested radarInput의first/last/receive에는아직그offset을적용하지않는읽기상태였다. 원본metadata를정규화된CANheader와매칭하려면같은epoch/domain이라는전제가필요하다. **이진단은원본시각끼리비교했고어느필드도수정하지않았다.** 원본field를복원한다는이유로임의시각·packetCount를생성하거나,100ms통과를위해receive를새now로바꾸면안된다.

## 도구·근거·재현

최종도구 `probe.py`와동일한`probe_final.py`를동결했다. `run03_frozen/results.json`이호환옵션을포함한최종익명집계이며,run01/run02_final도보존했다. 초기실행뒤신규도구의정렬/unused import만정리하고receive시각역전·묶음중복·CANheader범위재사용·미결합개수를추가집계한후전체4파일을다시직접실행했다. 원형알고리즘은변경하지않았다.

run02 정합성계산을완료한도구SHA256은 `3ebfe77ecae973aff1868a0f391b1e46415e456f4822b0205957958d6f869b3c`, 해당결과SHA256은 `c40af02fd45c6bde4422e06e2602c08caf0c1ee5f3fee8f2a5c58687dde43449`이다. root 호환옵션을포함한최종고정도구SHA256은 `4763cf7a6e9878d792c626a7179fff0e3627bcb1c474b079367ce28c2b069537`, run03_frozen/results.json SHA256은 `0af2a288bb55def86c1228ca660e09be088e013d68dfdb260c621eb500c5334d`이다. 최종실행은22:39:31.533 KST,처리구간1.185471초였다.

```powershell
# 프로젝트 루트에서 기존 격리 venv 사용. 새 출력 폴더만 생성한다.
& work\venv\Scripts\python.exe -B work\radar_input_contract_probe\probe_final.py --output-dir work\radar_input_contract_probe\independent_replay
# 대표 한 파일만 확인하려면 --aliases log_a 추가
```

완료:스키마와wire필드존재/0값/packet범위/receive정합성/상대시각/원형metadata gate의직접진단. 미완료:실제radarcan소켓·전체호스트·collectorclock·ECU/firmware·ARS live·차량권한·PCS/AEB·물리안전. 메타데이터가존재한다는결과를실차활성화근거로쓰지않는다.
