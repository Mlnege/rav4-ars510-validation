# 레이더 점 소실·자료 오류·선행차 예측과 제동 계획 읽기 진단

기존 실패는 한 가지 ‘레이더 없음’으로 설명할 수 없다. **정상 빈 점 집합, 오류 자료, 오래된 점, 선택된 lead 소실**은 서로 다른 상태다. 정상 빈 레이더에서도 비전 lead가 남을 수 있고, 점이 있어도 거리 조건에서 lead 선택이 사라질 수 있다. 제동 계획은 최종 lead.status와 필터된 거리·속도·가속·Tau를 사용한다. 실제 제어 권한의 오류 차단은 별도 SelfdriveD/Controls 경로다.

이번 작업은 기존 source·합성 JSON/CSV 읽기와 신규 extract_preserved.py의 **읽기 추출·산술·지문 수집**만 직접 실행했다. 새 plant/MPC/C·주행 테스트는 실행하지 않았고 기존 source·결과·.so·Params·release·outputs·차량을 변경하지 않았다. observations.json은 보존 trace의 변곡값이며 실차 CAN이나 새 시뮬레이션 결과가 아니다. input_manifest.json은 현재 읽은31개 입력·source 지문을 기록한다.

## 상태별 실제 source 처리

| 상태 | ARS/점·필터 처리 | DPath·계획·권한의 의미 |
|---|---|---|
| 정상 완성 record에 출판점0 | vendor interface.py:584–624의 AGE/far/path/유효성·미해결속도 조건 등으로 점을 보류할 수 있다. errors는False | liveTracks.valid=True일 수 있다. RadarInterfaceBase는 새점집합에 없는 MyTrack을 제거한다. 비전 fallback이 있으면 lead.status는True일 수 있음 |
| CAN 없음·미완성·부분 수신 | 완성 결과 전 update가None일 수 있다. 마지막 result를 새 측정으로 만들지는 않는다 | 마지막 liveTracks/점은 소비자에 남을 수 있으나 publication skew·alive·다음 오류/timeout과 별개다. 새 메시지 없음과 정상 빈 메시지는 다름 |
| CRC/sequence/DLC/시간 오류 | strict assembler/adapter가 history를 지우고 빈 canError·temporary unavailable 반환 | 오류를 지우지 않고 전달. 생산 radarcan의 message.valid=False→DPath aggregate valid/error→SelfdriveD 이벤트 경로를 구분 |
| 완성 record stale | adapter는 마지막 record 첫 시각 기준0.5초 초과에서 reset/temporary unavailable | 원형 radarcan의 receive 기준100ms·전체 poll/inputTimeout과 같은 조건이 아니다 |
| old publication | DPath controller.py:750–755가 |E−P|>0.15초 또는 비유한이면 점 스냅샷을빈집합으로 만든다 | 비전 또는 제한된 matcher hold가 남을 수 있다. 무제한 마지막 lead 유지나 자동 오류 최대제동은 아님 |
| measured=False 점 | MyTrack.update는 count/가속·jerk 이력을 초기화하고 count6 미만 출력가속/jerk0 | LeadAccelTau의 빠른 제동 확인은측정된 연속 표본을 요구한다. 예측점은 새측정의 증거가 아니다 |
| 최종 lead.status=False | MPC.process_lead는 내부 계산용50m·vEgo+10m/s·가속0을 사용 | 센서 RadarPoint를 생성/출판한 것이 아니다. 이전 real lead를 그대로 유지하는 예측도 아니다 |

healthy empty의 원형 errors=False는 물리 장애가 없다는 제조사 판정이 아니라 이 library가 해당 record를 정상 처리했다는 의미다. 특정 점이 보류된 이유는 diagnostics/원형 조건에서 확인해야 하며, 실제 ECU가 객체를 송신하지 않았다고 동일시하지 않는다.

## filtered aLead·Tau·미래 위치의 연결

native fused는 raw 객체 속도와 신선한 ACC 목표 속도 관측을 내부 가중치로 결합하고 vRel=fused ground speed−B4 ego로 만든다(interface.py:568–590). ACC가 없어도 complete CRC와 geometry가 정상이면 정상 처리할 수 있다. 지원 메시지의 stale/idle로 ACC 대응이 없어지는 것과0x80 record 자체가 틀리는 것은 다르다.

MyTrack은 전달 vLead를 통해 가속·jerk를 추정하고, count6 미만일 때 aLead/jLead를0으로 쓴다(radar_tracks.py:126–139). DPath의 live 스냅샷은 현재 CS.vEgo+vRel로 vLead를 재구성하므로 B4와 CS 속도 기준·시각도 별도 요소다. aLeadK는 이 필터 흐름의 값이며 원본 센서 aRel을 직접 최대제동 명령으로 바꾼 값이 아니다.

LeadAccelTau는 source 설명 그대로 `a(t)=aLead*exp(-aLeadTau*t²/2)`의 **감쇠 계수**다. 숫자가 작으면 감속 예측을 더 오래 유지한다. measured·aLead/jerk 확인·서로 다른 연속 표본 및 최대0.15초 간격을 빠른 확인에 사용한다(lead_dynamics.py:29–82). 점이 없어지면 RadarLeadDynamics가 해당 identity의 상태를 제거하고, hold point 등 새 활성점 목록에 없는 identity의 Tau 조회는 기본1.5로 돌아갈 수 있다(controller.py:444–457). stale 예측에 신선한 제동 증거가 계속 쌓인다고 보면 안 된다.

MPC는 선택된 lead의 dRel/vLead/aLeadK/aLeadTau로 미래 궤적을 계산한다(long_mpc.py:375–408). 이어 속도에 따른 정지 등가거리를 더해 lead obstacle을 만들고 cruise/다른 lead/정지 목표와 비교한다(:447–469). 현재 거리를 수렴 가능한 제동거리로 올려 clipping하는 별도 조건도 있으므로 미래 위치 낙관을 Tau 하나의 효과로 단정하지 않는다.

보존 grid의8.00초 값은 다음과 같다. 모두 자차·선행차20m/s,7초부터 가상선행차−5m/s²의 합성 사례다. 미래열의 horizon은1.111111초이며 **자기 사례의 현재 ego 좌표 기준 lead 미래 위치**와 그 사례의 truth를 비교했다. 미래 차간거리·TTC나 실물 센서 오차를 측정한 값은 아니다.

| 사례 | MyTrack count·aLead | DPath 속도·Tau | 기록 미래 위치−자기 truth | MPC source / CAN 명령 |
|---|---|---|---:|---|
|55m/full |74 /−4.4701 |15.9364 /0.003960 |+0.934m |lead0 /−1.734m/s² |
|55m/missing |74 /−1.9160 |18.7075 /0.102976 |+7.051m |cruise /−0.163m/s² |
|60m/missing |13 /−1.9075 |18.6956 /0.511607 |+7.188m |cruise /−0.273m/s² |
|65m/missing |MyTrack 없음 /vision−5 |14.9500 /0.300000 |−0.718m |lead0 /−1.273m/s² |

55m pair는7초 count58로 이력이 준비된 상태에서도 차이가 난다. 따라서 cold 가속0이나 첫 L1 지연만으로 모든 실패를 설명할 수 없다. 60m missing은7.25초 vision→radar로 바뀌며 count1/aLead0/Tau1.5였다.65m missing은8초까지 vision을 사용하고8.9초 radar로 전환한다. 더 늦게 공개된65m에 접촉이 없고55m의 충분히 준비된 missing에 접촉이 있으므로 ‘늦은 첫점이면 반드시 충돌’이라는 설명도 성립하지 않는다. 거리가 다르고 제어 후 자차 궤적도 달라 효과량을 단순 차이로 빼지 않는다.

기존 far 조건만 끈60m 반례는 일찍이력에 들어갔지만13.61초 접촉, min_age만1은 첫radar7.25초·13.75초 접촉으로 기본과 같았다. 이 둘은 공개 software config의 분석 전용 반례다. 이번에 변경·재실행하지 않았으며 실차 프로파일이나 source 수정 정책으로 권장하지 않는다. 불확실성 코드47/내부σ 환산은 library의 likely 가정이지 제조사가 정의한 실물σ 확정이 아니다.

## 근거리8.60초의 점·선택·정지 요청 전이

보존 stop_inspection/observation.csv의8.60초에는 **point_count1, 인터페이스 점 dRel0.490326m, ego0.089816m/s, lead.status=False**였다. 점이 사라진 시점이 아니다. primary.py:797의 vision lead 최소거리와 moving/stationary/radar-only 선택의 기존0.5m 초과 조건을 구분해야 한다. 보존 near CSV에는 measured/error 플래그가 없으므로 그 필드를 관측한 것으로 추가하지 않았다.

기존 ArsRadarBridge는 DPathRadarController에 retain_confirmed_near_front를 전달하지 않아 기본False다(radar_bridge.py:36–37, controller.py:468). 생산 DPath도 **정확한 RAV4·directLong·radarUnavailable=False**일 때만 선택정책을 켠다(radard_dpath.py:105–107). 현재 CP.radarUnavailable=True라 그 생산 조건은 충족하지 않는다. offline 진단 mode1과 live 지원·CP 변경을 혼동하지 않는다.

선행차가 선택되지 않으면 controller는 비전 fallback을 시도하지만, 이 가까운 vision 거리 자체도0.5m 이하이면 source에서None이다. 그 결과 final lead가 없을 수 있다. MPC 내부 대체값은 최적화 실행을 위한 수치이며 sensor 객체 생성이 아니다. source에는 일반 last lead 무한유지 규칙이 없고, stationary dropout hold0.10초도 현재 vision/corner 지지와 경로 일치를 요구한다(primary.py:1437–1489). near-front 옵션은 과거 확인한 동일현재측정·시간·중앙·저속·연속성을 요구하며 새 근거리 반사 획득을 허용하는 옵션이 아니다(controller.py:551–593).

| 보존 시점 | 관측 | 해석 |
|---|---|---|
|8.60초 |점1인데 leadFalse |일반 선택 거리 경계와 default-off 근거리 옵션을 구분 |
|8.70초 |shouldStop=False, planner target +0.244498 |최종 lead 상실 이후 정지 요청이 해제된 계획. 계속 정지 요청을 유지한 사례가 아님 |
|9.05초20Hz 표본 |유지된 CAN 명령 +0.040 |실제 새 CAN 발행시각을 직접 저장한 열은 아니다. source33.3Hz cadence와 표본 시각을 구분 |
|10.31초 |가상 geometry 최초 접촉 |보존 요약값. 접촉 이후 음수 거리/최종 속도를 유효 제동 결과로 해석하지 않음 |

계획의 shouldStop은 lead 존재 bool을 직접 그대로 복사한 값이 아니다. get_accel_from_plan은 action_t 및1초 뒤 속도 예측 둘이 정지속도 미만인지로 판단하며(drive_helpers.py:109–126), ACC 모드는 그 MPC 결과를 사용한다(longitudinal_planner.py:296–367). source에서 lead 제약이 없고 cruise 목표가 남으면 양수 계획이 나올 수 있다. LongControl·Toyota 출력은 별도 상태·잔여 명령·정규 발행 주기를 거치므로8.70초의 양수 목표와9.05초의 양수 표본 사이를 동일한 순간으로 취급하지 않는다.

이 전이는 이전 신호 사례의 **shouldStop 유지·음수 요청 중 양수 잔여**와 다른 원인이다. 현재 Toyota STOP 정정은 stopping/비양수 요청 등 한정 조건의 잔여 보정이고, 여기처럼 정지 요청이 해제되어 양수 요청이 된 상태까지 같은 수정으로 처리한다고 주장하지 않는다. 보존 near 사례는 당시 전체 코어 지문이 없으므로 현재 STOP 수정의 새 재검증 결과로도 세지 않는다.

기존 witness 결과의 full+near=True는 contact 없이0속도였지만 missing+near=True는 여전히10.31초 접촉했다. 이 옵션 하나가 모든 관측 계약 실패를 해결했다는 증거는 아니다. 이번에는 그 차이의 누락된 개별 measured/anchor 조건을 새로 만들어 확정하지 않았다. 현재 radarUnavailable=True/default-off 조건을 유지하며 live 정책 선택이나 안전성 결론을 내리지 않는다.

## 자료오류와 실제 권한·활성 합성 plant의 한계

LongitudinalPlanner/MPC 계산은 rr.errors 자체의 즉시 최대제동 분기를 갖지 않고 선택된 lead 상태·운동값을 읽는다. source SelfdriveD는 invalid radarState에서 canError를 immediateDisable/noEntry, temporary/fault를 softDisable/noEntry로 연결한다(selfdrived.py:440–452, events.py:940–948,1010–1018). softDisable은 상태기계의 시간·현재 상태에 따르는 것이며 오류 수신 즉시 물리 최대제동을 보장하는 기능이 아니다.

기존 NativeClosedLoopPlant의 Inputs.all_checks는True이고 CC.longActive/LongControl.update는 명시적 활성 입력이다(closed_loop.py:69–81,146,237). 건강 상태기계·실제 Panda 권한을 source 전체로 실행하는 하네스가 아니다. 따라서 그 plant에서 자료오류/lead 소실 후 가속을 보았다고 생산차의 fault 차단이 없었다고 말할 수 없다. 반대로 실제 r9 자료의367점/2,399CRC/175입력은 원본OFF 관측이므로 활성 센서 소실 뒤 물리 제동 응답을 보장하지도 않는다. 이번 실제 CAN 재생은 새로 실행하지 않았다.

확인한 것은 소프트웨어 선택·필터·미래예측·계획과 별도 권한 경로의 연결이다. 시간 한계·필터·CP·신호·정책을 바꾸어 수치를 맞추거나 물리적 안전 결론을 확정하지 않았다. 실제 동일 객체의 연속 CAN/측정·발행 시각/활성 제어·오류/ECU 정체·PCS/AEB·운동 응답은 추가 근거가 필요하다.

## 직접 추출·동결

extract_preserved.py는 합성 grid6개와 near CSV/요약·witness 요약을 읽어 observations.json으로 선택값을 저장했다. 직접 실행 exit0이며 신규MPC/native/Safety 실행0·실차TX0이다. 처음에는 지문 목록의 CarController 경로 누락으로 KeyError가 났고 목록만 보강해 읽기 추출을 완료했다. initial_extraction_failure.json에 그 준비오류를 남겼다. 이후 접촉 이후 최종속도는 해석하지 않도록 출력에서None으로 정리했고 기존 파일은 변경하지 않았다.

읽은 입력·source·추출 도구31개 지문은 input_manifest.json에 있다. grid에 기록된3 source 지문은 현재 세 파일과 모두 같았다. 그 사실을 실행 당시 모든 native/코어 지문 계측으로 확대하지 않는다. report·추출 source·변곡 JSON·지문·준비오류 기록을 지정 폴더에서 동결한다. 같은 주행 pass를 반복 실행하지 않았다.
