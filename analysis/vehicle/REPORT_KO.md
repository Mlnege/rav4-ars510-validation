# 차량 식별·HYBRID·종방향 설정 원인: 읽기 관찰

수동으로 정확한 Hybrid 문서명을 선택한 사실과 `carFw=0`/HYBRID=False는 함께 존재한다. 최신 source는 유효 수동 선택이면 펌웨어 조회를 생략하고, HYBRID bit는 조회된 hybrid ECU가 있을 때만 넣는다. 이 상태는 **비하이브리드 차량이나 잘못된 차종 선택의 증거가 아니다.**

로그는4개지만 carParams가 있는 것은3개이며 합계5개 CP다. 나머지는 initData만 있어 그 로그의 CP/FW/동작을 추정하지 않았다. 개인정보·VIN·펌웨어 문자열·ECU/네트워크 주소·위치·route 식별 필드에 접근하지 않고, 명시한 설정과 모델/범주/개수만 기록했다.

## 직접 확인한 사실

| 항목 | 관측 |
|---|---|
| 알려진 수동 선택 |4개 initData 모두 RAV4 Hybrid 2022 문서명에 정확히 대응하는 선택 |
| 실제 CP |3로그/5CP 모두 TOYOTA_RAV4_TSS2_2022, fixed, carFw0, HYBRID=False, RADAR_ACC=True |
| 레이더 |5CP 모두 radarUnavailable=True, 현재 source의 radar DBC 없음과 일치 |
| 직접 종방향 | AlphaLong 설정True인2로그의CP에서 DISABLE_RADAR=True/directLong=True; False인1로그에서 둘 다False |
| CP 지연 |5CP 모두 longitudinalActuatorDelay 약0.15초, radarDelay0 |
| 실제 LongActuatorDelay 설정 |**4개 initData에서 모두20을 직접 관측**. default20이라는 source 사실과 별개다. 누락 사례없음 |
| 실제 PCM 속도 모드 |4개 초기 설정의 SpeedFromPCM은1/3/0/0. CruiseButtonMode는0/0/3/3으로 별도 버튼 설정 |
| Radar Track 설정 |4개 초기 EnableRadarTracks는1/0/3/3. 초기 snapshot이므로 이후 변경까지 입증하지 않음 |
| 실제 제어 활성 |3개 로그의 carControl15,358개 모두 longActive=False/stateoff/요청accel0 |
| 회생 표시 |3개 carState15,401개 모두 regenBraking=False. Toyota source는 이 필드를 별도로 채우지 않음 |

따라서 제공 로그만으로 **실제 활성 종방향 제어의 지연·제동 응답·회생과 마찰제동의 배분**을 측정할 수 없다. CP의 기능 설정True와 실제 longActive=True는 다르다.

추가 bool 관측에서 carState15,401개 모두 cruiseState.available=False/enabled=False, selfdriveState15,398개 모두 enabled/active=False였다. accFaulted는모두False, canValid는모두True다. 설정/시뮬레이션에서 활성 상태를 가정한 시험은 그대로 별도 진행하지만, 이 실제 로그가 그 활성 조건을 충족했다고 보고하지 않는다.

## source 연결과 영향 범위

| 단계 | 실제 source 근거 | 영향과 해석 |
|---|---|---|
| 수동 차종 | selected_car.py:1, car_helpers.py:174-186 | Hybrid 문서명도 같은 RAV4 2022 플랫폼에 대응. valid selection은 skip_fw_query=True |
| 조회 생략 | car_helpers.py:106-134 | 수동/고정FINGERPRINT/SKIP_FW_QUERY 경로에서는 carFw=[]로 설정. active query 실패와 다른 경로 |
| cache | car_helpers.py:112-127 | query를 실제 수행하는 경우만 FW가 있는 cache를 사용. 수동 skip 경로는 cache 존재여부와 무관하게 생략 |
| HYBRID | toyota/interface.py:53-57 | car_fw의 ECU 범주에 hybrid가 있을 때만 bit 추가. 빈 목록이면 추가안함 |
| RADAR_ACC/DBC | toyota/values.py:96-101,264-270 | 플랫폼의 정적 RADAR_ACC가 radar DBC를 제외. carFw0 때문에 radar DBC가 사라진 것이 아님 |
| Vision Only | toyota/interface.py:110, radar/effective_radar_track_mode | radar DBC 없음→radarUnavailable=True. Toyota에서는 Track Mode 설정만으로 활성화되지 않음 |
| directLong | toyota/interface.py:113-131 | RADAR_ACC와 AlphaLong 조건에서 기존 DISABLE_RADAR/directLong 경로. 새로운 활성화/UDS 실행없음 |
| gear | toyota/carstate.py:35-38,74-80 | **HYBRID가 아닌 SECOC flag**로 GEAR_PACKET_HYBRID/GEAR_PACKET 선택. 관측CP의 SECOC는False |
| GVC | toyota/carstate.py:62-63 | non-SECOC에서 VSC1S07.GVC 사용. HYBRID 분기없음 |
| brake | toyota/carstate.py:70-71 | BRAKE_MODULE.BRAKE_PRESSED와 ESP_CONTROL.BRAKE_HOLD_ACTIVE. HYBRID 분기없음 |
| CP actuator delay | toyota/interface.py:149-151, interfaces.py:450 | HYBRID가 있으면 CP 값을0.05초로 변경, 없으면 표준0.15초. 측정된 실물 지연이라는 뜻이 아님 |
| 실제 Carrot 계획 지연 | longitudinal_planner.py:296-306 | CP 값 대신 LongActuatorDelay×0.01를 사용. 관측20→0.20초, DT_MDL 더한 action_t0.25초 |
| Toyota 피드백 | toyota/carcontroller.py:219-241 | 저속GVC/고속aEgo 혼합, aego 필터0.25초, 미래0.25~0.5초 보정,33.3Hz PID. HYBRID 분기없음 |
| LongControl | longcontrol.py:120-126 | Toyota는 추가 가속도 PID 대신 계획 목표를 전달. 마지막 PCM 보정은 CarController |
| regen 해석 | toyota/carstate.py 전체 | Toyota regenBraking 전용 파싱없음. GVC/aEgo/brakePressed만으로 모터 회생·마찰제동·경사·저항을 분리할 수 없음 |

현재 source에서 ToyotaFlags.HYBRID의 직접 사용은 interface의 flag 생성과 CP 지연 설정뿐이었다. 따라서 누락을 gear/GVC/brake 파서 오류로 곧바로 연결하거나, HYBRID flag를 강제로 넣으면 해결된다고 판단하지 않는다. 이 조사에서 flag·설정·UDS·차량 I/O 변경은0이다.

## 실제 CAN과 신호 범주

현재 non-SECOC 기어 입력인 GEAR_PACKET(0x3bc)은3로그에서35/60/60회, 이름에 HYBRID가 붙은0x127은2,124/3,761/3,761회 관측됐다. 기존 DBC로 원형 CANParser에서 해석하면 숫자코드는다르지만 두 메시지에서 동일한 D/P 범주가 각각 관측된다. 동시각 일대일 기어 검사는 아직 하지 않았으므로 두 메시지가 항상 동일하거나 현재 선택이 최적이라고 확정하지 않는다.

GVC(VSC1S07,0x320)는730/1,284/1,283회, 브레이크 메시지(0x226)는1,459/2,566/2,568회 관측됐다. 움직인 로그에서 GVC 음수539회, carState 음수aEgo2,718회 중 brakePressed=False2,106회가 있다. 이는 감속 관측이지 회생제동의 직접 증거가 아니다. regenBraking=False도 회생이 없었다는 증거가 아니다.

DBC의 XGVCINV raw bit도 범주로 기록했지만 이름만으로 정확한 유효성 의미를 새로 정의하지 않았다. 원형 source는 해당 bit로 GVC를 gating하지 않는다. 모터 토크·배터리 충전전력·유압 등 검증된 추가 신호가 없으면 회생 배분을 산출하지 않는다.

## 원형 수동선택 재현과 과거 원인 구분

`probe_manual_skip.py`는 실제 get_car의 수동 선택 및 실제 fingerprint 함수를 실행했다. Params STRING 반환형을 원형대로 메모리에서 제공하고 CAN 수신은 빈 packet, 송신은 즉시 예외로 막았다. 원형 fingerprint를 그대로 호출하는 관찰 wrapper로 인자를 기록한 뒤 CP/CI 생성 전에 종료했다. Linux에 없는 진행 표시 패키지는 이미 설치된 순수 Python tqdm을 읽었고 시스템 설치는하지 않았다. 로그 출력도 메모리/폐기하여 식별자 출력에 접근하지 않았다.

직접 결과: skip_fw_query=True, 실제 fingerprint완료, carFw0, 수신콜백203회, 송신0, OBD콜백1회는메모리기록뿐이다. 성공 모형으로 함수 결과를 대체하지 않았다. 이 재현은 **현재 source에서 실제로 조회가 생략됨**을 증명한다. 과거 해당 차량의 실행 trace를 직접 얻은 것은 아니므로, 과거 carFw0이 모두 이 이유였다고 단정하지 않는다.

실제4개 설정의 valid Hybrid 선택 + fixed/빈FW CP가 현재 source의 생략 경로와 강하게 일치한다. 펌웨어 조회가실행됐다가 실패했다는 직접 증거는 현재없다. FINGERPRINT/SKIP_FW_QUERY 환경 override나cache 내부값을 실제 장치에서 읽지 않았다. 추가 boot trace를 제공받을 경우 비밀정보를 제외한 query skipped/query attempted/response-count 범주만 확인해야 한다.

## 확인된 것·추론·미확인

- 확인:3로그/5CP의 빈FW·HYBRIDFalse,4개 Hybrid 선택·LongActuatorDelay20, 모든 관측 controloff, 현재 source의 skip 인자/빈FW 실행, parser 선택은SECOC 기반.
- 근거 있는 추론: 수동 Hybrid 선택 때문에 query를생략하여 HYBRID bit를 넣을 정보가없는 경로로 설명가능. 현재 source와 과거설정이일치하지만 과거실행trace가아님.
- 미확인: 실제 ECU/펌웨어식별, 한국형 Hybrid 동력계 신호의 추가 차이, 실제 활성 directLong 응답/regen배분, 실제 PCS/AEB 유지, 장치/경사/제동력 영향.

관측 도구는 `observe_allowlisted.py`, 결과는 `observations.json`이다. 수동 선택 재현은 `manual_skip_probe.json`이다. 전체 Params/CarParams dump, 개인 식별자·위치·route와 raw CAN payload는 저장하지 않는다.

## PCM 원본과 같은 시각으로 대조한 추가 결과

`pcm_bus_diagnosis.py`에서 기존 DBC의 PCM_CRUISE(0x1d2).CRUISE_ACTIVE와 PCM_CRUISE_2(0x1d3).MAIN_ON을bus0/1/2별로 읽었다. 각 프레임의 정확DLC8·공식 Toyota checksum·원형 CANParser 수락을 모두 확인한 뒤에만 값을 관측했다. 현재 Linux의 CAN raw backend는Python fallback으로 직접확인했다. acados MPC의 실제 C/Cython 계산과는별개다. 기존 기록 중'CAN native parser'표현은이부록에서정정하며 CAN native 컴파일이나장치CPU성능을입증했다고보지않는다. 누락·실패·오래된 자료의 기본값0을 실제0으로 취급하지 않았다.

| 항목 |bus0 |bus1 |bus2 |
|---|---:|---:|---:|
|MAIN_ON 유효 프레임 |4,979 |0 |653 |
|CRUISE_ACTIVE 유효 프레임 |4,978 |0 |653 |
|True 값 |0 |관측없음 |0 |
|DLC/체크섬/parser 거절 |0 |관측없음 |0 |

carState15,401개와 같은 mono시각의 가장최근 유효 bus0 프레임을 비교했다. available/enabled 각각15,401/15,401일치했고 mismatch0이었다. 최근 프레임 나이는 전부0~50ms였으므로, 제공 구간의 availableFalse는 메시지누락·default0·체크섬실패·bus0/2선택혼동으로 설명되지 않는다. **현재 DBC가 해석한 실제 MAIN_OFF/CRUISE_INACTIVE가 지속된 구간**이다. 물리적 버튼 조작 의도까지 직접 확인한 것은 아니다.

bus2의 최근성은 대부분 후반500ms 초과였으므로 현재CarState 원본bus0과 구분했다. RADARdisable=False인 moving 로그에서도 bus0의False가 지속돼 disableFlag만을 Off의 원인으로 지목할 수 없다. source는 RADAR_ACC 플랫폼에서도 이 두 PCM 필드를bus0에서 읽으며 DISABLE_RADAR가 해당 두 필드의 입력 버스를 바꾸지 않는다.

100ms 비교 경계는 진단용이고 실제 제어·timeout을 변경하지 않는다. 절대시간·개인위치·원본 payload는 저장하지 않았고, 결과는 `pcm_bus_observations.json`의 상대ms 범주/개수다. 실제 Main On/Set/Res/취소 전환을 포함한 기존 로그가 있으면 다음에 동일하게 비교해야 한다. 이를 얻기 위해 실험 CAN 송신이나 실차 제어를 수행하지 않는다.
