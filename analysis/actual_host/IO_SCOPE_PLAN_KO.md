# 실제 ARS CAN → DPath → Mode0 호스트 → Toyota CAN/C 메모리 검사 경계

아래 표는 실행 전의 초기 계획이다. 완료한 실행 범위와 정정은 RESULTS_KO.md가 우선한다. 실제 자료를 조사한 뒤 합성 PCM ON은 제외했고, 원본 PCM/페달/문/벨트/기어/순정 CAN을 보존했다. 현재 replay는 오류 전파 수정 후 버전 c5d91e…이며 옛 오류 누락 설명은 현재 버전에 적용하지 않는다. 원본 CS.radarInput 수신 메타도 존재하므로 ‘collector 수신시각 없음’은 잘못된 초기 설명이다. 이번 direct-adapter 경로는 이 생산 배치 메타를 소비하지 않으며 nested 시각 재배치와 RadarCanBatches를 실행하지 않았다.

새 도구와 익명 결과만 이 폴더에 작성한다. 기존 source/결과/immutable 라이브러리/운영설정/차량은 바꾸지 않는다. 실제 CI.init·UDS·CAN소켓·Panda·차량TX는 실행하지 않는다.

| 단계 | 근거/실행 계획 | 분리해야 하는 한계 |
|---|---|---|
| 기존 실제CAN replay 대조 | 원형 tools/ars510_offline/replay와현재adapter/DPath를같은rlog/기록스키마에실행하여총369점·정상CRC2433·DPath선행선택175를대조 | 자료4개중CP없는1개는부족으로유지. 실제ECUidentity/FW/PCS검증아님 |
| 실제입력 읽기 | 저장순서의실제 CAN/CarState/modelV2/livePose와header·EOF를메모리에서읽음. 원본센서값은가능한보존하고거짓트랙/vision lead를만들지않음 | 실제collector receive timestamp가없다. logMonoTime은발행header이며센서획득/수신이같다고가정하지않음 |
| decoder/adapter | original CP를유지한offline=True Ars510OfflineRadarInterface,원형fused/MyTrack | B4 ego와CarState/wheels가다를수있어별도통계. record시작/완성/header/수신가정시간분리. CP.radarUnavailable=False/livehook금지 |
| DPath | 독립수신검증instance mode1, 실제원본model/pose·vEgo/rr를기존replay와같은순서·시각에공급 | originalCP의Unavailable유지. 현재replay는lead만직렬화하고rr.errors를RState에복사하지않으므로새호스트는원형RadarData errors를버리지않고명시적전달/차단을조사 |
| old→current schema | 기존형식payload를최신실제cereal로메모리직렬화변환. 시각정규화시전필드의동일offset과domain을기록 | 스키마누락을정상True로채우지않음. 실제절대원본time/IDs/위치/FW원문은출판자료에넣지않음 |
| host I/O와활성화 | 원형Card/VCruiseCarrot/SelfdriveD/StateMachine/Controls/CarrotPlanner/LongPlanner 유지. 수신CI.update는원본CS builder 반환 I/O, actualCI.apply/ToyotaCC/CANPacker 사용 | factoryRAV2022/directLong·PCMavailable/enable·stock목표는사용자longON의명시적합성가정. 원본모든CC OFF15,358개와혼동하지않음. 실제MCU권한/UDS준비아님 |
| 필수추가센서/건강 | 실제로그Device/DM/Panda/calibration/parameters/camera/process/sensors가있는지먼저집계. 원형SM으로실제 seen/valid/alive/freq 형성 | 필수자료부족/부적격/주기불일치가있으면원인보존. enabled/allchecks/DM/hardware를True로고정해전체성공을만들지않음 |
| C RX/TX | 현재C라이브러리의같은actual TXhook에실제생성CAN을메모리로넣음. 권한source는실제수신또는명시적PCM가정의정상memory RX로구분 | 실제rawStockECU/PCMoff를읽으면relay/권한으로막힐수있다. 차단을지우거나setControlsTrue하지않음. drivergas/brake와C.longAllowed분리 |
| privacy/출판 | 계산은원본시간/필드로메모리실행가능. 보고서는파일별익명alias/상대시각·개수·허용/차단·유효성통계 | rawrlog/CAN원문·실제trackID·절대원본시간·GPS/개인정보/FW원문을파일/출판자료로덤프하지않음. 기존replay의pointCSV도필요하면메모리sink만사용 |

재생순서는우선기존replay와동일한저장순서/원본header를대조한다. 신규호스트의100Hz수신clock은원본발행시각과구분한가정이며,파일의다른서비스header가앞뒤로섞였을때어떻게배달시각을매핑했는지기록한다. 헤더정렬로CAN기록순서를바꾸거나record주기를새로만들어점수를늘리지않는다. 필요하면원본clock의동일offset정규화와causal delivery(max observed header) 조건을서로다른실험으로분리한다.

실행목표는actual점/lead가원형호스트계획으로전달되는데이터경로다. 실제초기화/활성조건이막히면그상태로고정하고decoder·DPath·nativeplanner/CAN메모리등모듈별완료만보고한다. 고정/관측피드백에서CAN요청이생기는것은실제응답·적용·충돌회피·회생·PCS안전성증명이아니다. full신호2와이미지모델통합은이번ARS단계와별도다.
