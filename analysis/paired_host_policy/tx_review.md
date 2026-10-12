# 기록 정책 통합 도구의 TX 기대값·실행 경계 독립 읽기 검토

읽은 새 코드의 **silent/relay, elm327, Toyota73·585 ACC 기대식은 현재 C source의 해당 조건과 일치**한다. Toyota 모드의 steering·HUD·진단 메시지는 expected_tx=None으로 남겨, 복잡한 조건을 임의 허용으로 바꾸지 않았다. 따라서 정의한 기대값의 불일치가 없더라도 **생성 메시지 전부의 정책 기대값을 검증한 결과는 아니다.** 실제 C의 반환 관측과 별도 기대식 대조를 구분해야 한다.

이 문서는 whole_objects.py/policy_io.py 및 연결된 run.py·namespace 도구·원형 source를 읽고 기존 결과 JSON을 대조한 감사다. 새 테스트·C 호출·로그 재생·빌드·차량 송신을 실행하지 않았다. 이 새 문서만 작성했고 source/기존파일/outputs/release/라이브러리를 수정하지 않았다. B에게 직접 요청하지 않고 root에만 읽기 결과를 전달했다.

## 읽은 버전

| 파일 | 읽은 SHA-256 |
|---|---|
| whole_objects.py | 4645210fdfecffb7703acad3f1f2bb73f5174fe1e264e01b99d3f1b9e73190e0 |
| policy_io.py | e35882a9877c2562134aa1fa19b96c7a82cbba1d9afbe8265608a0a14a0555d8 |
| run.py | 8242edc7f4a1c5e8f17204b2a073c48731e699e83eb039fe335b2d5c822d5800 |
| whole_io.py | 5dd434ff3fce1406b2782c7f1237157308ad84ce13584855931c46b148ac4f9d |
| 로드하는 recorded_panda_mode_replay/run.py | 24386c4a8aa959f39f1b0d86e416e1cade94c0d317f346b7f3bfa0159126510e |

읽은 source 기준이며 작성 중 도구의 이후 변경이나 다른 실행의 지문을 이 값으로 대신하지 않는다. 생산 source의 버전은 앞선 REVIEW_KO.md에서 식별한 현재 동결 코드와 대조했다.

## TX 기대 정의

| 조건 | 새 helper의 expected_tx | 현재 C source와 대조한 범위 |
|---|---|---|
| relay_before=True | 모든 메시지0 | safety.h:292의 최종 반환이 relay를 차단한다. whitelist/메시지 조건이 허용해도 최종 거부 |
| mode0 silent | 모든 메시지0 | safety.h의 SAFETY_SILENT→nooutput_hooks와 safety_defaults.h의 false TX. 새로운 권한 부여 없음 |
| mode3 elm327 | DLC8·허용 진단 주소·특수0x24b의 ISO frame type 조건 | safety_elm327.h:11–33와 대응. 일반/29bit 진단 주소의 mask와0x24b 예외를 그대로 비교한다. C는 elm327에서 일반 TX whitelist를 우회하고 이 원형 hook을 판단한다 |
| mode2 Toyota73,0x343 | bus0·DLC8·inactive raw0 또는 long_before와−3500..2000 | safety_toyota.h:196–202 및 safety.h:621–625. raw 단위 가속 범위이며 실제 차량 감속 능력 보증이 아니다 |
| mode2 Toyota585,0x343 | bus0·DLC8·inactive raw0·data[3]의 CANCEL_REQ | safety_toyota.h:205–211의 STOCK_LONGITUDINAL 비트512 조건. long 권한이 있더라도 stock 정책은 비영 가속을 허용하지 않는다 |
| mode2,0x750 진단 | None | actual C TX는 실행하지만 독립 기대식은 정의하지 않았다. tester_present_exact는 payload 대조이며 C whitelist/모드 정책 기대값과 다르다 |
| mode2,steering/HUD/그 밖 메시지 | None | 원형 C 반환과 해독 자료를 관측한다. steering 역사·torque/angle/req와 whitelist 전체를 별도 판정한 것은 아니다 |
| 다른 mode | None, relay이면0 | 현재 선언한 정책 밖의 허용값을 추측하지 않는다 |

ACC 기대식의 conditional 표현은 stock이면 raw0+cancel, direct이면 inactive 또는 long 권한·범위로 선택한다. bus/DLC 검사는 그 전체 조건 바깥에서 공통으로 적용한다. 현재73/585 모두0x343/bus0/DLC8이 해당 Toyota whitelist에 존재하므로 이 정의가 맞다. 임의 다른 param/ECU 형식까지 검증한 것으로 확대하지 않는다.

elm327의0x750 허용 관측이 Toyota73의 tester-present 정책 검증은 아니다. Toyota source에서는0x750/bus0/DLC8 whitelist와 정확한 0f023e0000000000 payload를 함께 적용하고, stock585의 기본 목록은 direct 목록과 다르다. 현재 helper는 이 Toyota 진단 기대값을 None으로 남겼으므로 `tester_present_exact=True`만으로 전체 C 진단 판정 통과라고 쓰지 않는다. 0x411 PCS 표시의 생성/C 반환은 실제 PCS/AEB 상태·보존 증거가 아니다.

이 읽기에서 기대식 오류나 안전 권한 우회를 확인하지는 않았다. 새 동작을 실행해 확인한 것도 아니다. malformed DLC/다른 bus/진단 특수주소의 경계 case를 이번 감사에서 새로 재현하지 않았으므로 전 범위 회귀 통과로 보고하지 않는다.

## 미정 TX를 판정 통과로 세지 않는 경계

run.py:170은 `all(tx_matches_expected is not False)`이며, expected_tx가 None이면 tx_matches_expected도 None이다. 따라서 이 True는 **정의한 기대식에서 관측 불일치가 없었다**는 뜻이고 미정 메시지에는 독립 판정이 없다. 정의한 표본이0이면 같은 식이 참이 되는 빈 집합 성질도 있으므로 정의/미정 수와 함께 읽어야 한다. 코드가 각각의 수를 run.py:185–186에 별도 저장하는 것은 타당하다.

기존 log_a_first/results.json을 읽은 값은 다음과 같다. 이 감사자의 신규 실행 결과가 아니다.

| 지표 | 보존 값 | 해석 |
|---|---:|---|
| 생성 CAN |5,624 |메모리 CI.apply의 생성 수 |
| 정의한 TX 기대 |1,081 |현재 명시한 모드·ACC/진단 조건의 독립 기대식 대조 범위 |
| 미정 TX 기대 |4,543 |기대식 미정. 전체 판정 통과 수에 포함하면 안 됨 |
| actual C 허용/거부 |5,488 /136 |실제 C hook 반환 관측. 정의/미정 기대식 범위와 다른 집계 |
| 비영 ACC 요청 |0 |비활성 기록의 결과. 활성 급제동/가속 검증이 아님 |
| 생성자 후 cp_changed_fields |빈 목록 |이 log_a 표본의 제한된 cp_view 필드만 비교한 결과 |

“C 전체5,624회 반환을 관측했다”와 “정의한1,081개 기대에서 불일치없음”은 함께 보고할 수 있다. “5,624개의 정책 판정 전건 통과”로 합치면 틀리다. DBC parse/checksum도 정의가 없는 tester-present 등이 None으로 남으며 `is not False` 검사만으로 모든 메시지가 동일한 checksum 검사를 받았다고 확대하지 않는다. TX 전후 controls/long 권한의 불변 검사는 기대식 정의 여부와 별개로 모든 생성 row를 확인하도록 돼 있다.

## 같은 C 상태와 기록 모드

RecordedPolicy는 ClockedProbe를 한 개 만들고 self.probe=self.clock.probe를 보관한다(policy_io.py:14–20). run.py:88–89가 이 객체를 interface.tx_permission에 전달하고, receive_can의 physical RX와 apply의 `p.packet('tx',...)`가 같은 Probe를 사용한다. 현재 코드 경로에서는 VehiclePermissionInput/Probe.reset을 생성하거나 호출하지 않는다. Probe.__init__은 ctypes 함수 signature binding뿐이며 init_tests·권한 setter는 별도 reset 메서드에 있고 그 메서드는 이 경로에서 호출되지 않는다.

ClockedProbe는 정식 silent 초기1회 및 기록 mode/param 변경에서만 set_safety_hooks를 사용한다. alt-only 변경은 set_alternative_experience로 처리하고 반복 Panda 표본은 no-reset count로 남긴다. 외부1Hz counter/safety_tick과 상대 µs timer를 진행하며, 실제 독립 MCU heartbeat/부팅/수신 clock은 재현하지 않는다. policy.summary의 setter/init_tests=0은 코드 경로 설명 값이며 모든 외부 호출을 동적으로 추적한 계측 결과가 아니다.

RX는 src0..7, 반환 통지는128..135, 거부 통지는192..199로 분리돼 있고 unknown은 별도 count다. 통지의 src를 줄여 RX로 바꾸거나 원본 송신을 TX로 재실행하지 않는다. host tick에서 policy.advance 뒤 기록 항목을 저장순서로 소비하고, 그 후 Card apply가 TX를 평가한다. 같은 tick에서는 C timer가 host tick에 맞춰 양자화된 가정이며 원래 C-only의 개별 Event 수신 clock과 같은 실행을 주장하지 않는다. TX가 mode/param을 바꾸는 코드도 없지만 실제 비동기 하드웨어 모드 변경 race를 시험한 것은 아니다.

## 생성자·네임스페이스·입출력 예외

새 initialise(messaging,cp)는 get_params를 호출하지 않고 전달한 원본 host CP 복사본으로 CarInterface를 만든다(whole_objects.py:247–258). run.py의 cp_view 전후와 원본 decoder CP 불변은 분리돼 있다. Card 생성자의 alt/passive/safetyConfig 변경 가능성은 source 그대로 남는다. log_a의 cp_changed_fields=[]를 아직 검사하지 않은 b/d나 모든 CP 필드 동일로 확대하지 않는다. recorded_direct_stock_cp_retained는 directLong/safetyConfigs/radarUnavailable 세 필드 비교이며 alt 등은 별도 cp_changed_fields에서 읽는다.

앞선 ACC_TYPE 한계에 대해 현재 code는 stock feedback parser에 ACC_CONTROL을 추가하고 DISABLE_RADAR이면 acc_type_disabled_radar 범주로 초기값 유지 분기를 분리했다(whole_objects.py:143,163–165). 현재 정확한 RAV4 범위에서 Toyota CarState의 대응 분기와 맞는다. 전체 ToyotaCI.update가 실행된 것은 아니며 stock 피드백의 마지막 관측값/미수신·freshness 한계는 계속 남는다.

원형 클래스/메서드 본문은 AST로 로드하고 필요한 source 상수 할당을 읽는다. 메모리 Params/messaging, camera inventory, 외부 fault 파일, CI.init/CI.update는 명시적 I/O 예외다. namespace 도구의 globals-resolved/선택 상수 비교가 전체 module import나 모든 import binding의 동일성을 증명하는 것은 아니다. 새 감사에서 namespace 도구를 실행하지 않았으므로 그 실행 결과도 새 통과로 말하지 않는다.

특히 Card의 CAN_BACKEND global은 “capnp 변환 실행, Toyota CAN 파서 미실행” 설명 문자열로 대체돼 있다(whole_objects.py:116). 이는 진단 metadata이며 권한 정책 변경이 아니지만 실제 backend 값과 같은 global binding은 아니다. 전체 ToyotaCI.update 파서는 미실행이고, stock feedback·생성 CAN의 CANParser/CANPacker는 **Python 경로를 실행**한다는 두 사실을 나눠 설명해야 한다. native C/Cython MPC와 안전 C의 실행을 CAN C++ backend 실행으로 바꾸어 보고하지 않는다.

## 완료 범위

이 추가 검토는 읽은 기대식의 source 대응·미정 판정 범위·단일 C 상태·원본 CP 생성자와 명시적 I/O 예외를 확인한 것이다. actual log_a_first의 일부 관측을 읽었으며 활성 제어·실물 ECU/FW·ARS live·CAN 전달·PCS/AEB·회생·운동 응답을 검증하지 않았다. 현재 helper/source를 새로 실행하거나 수정하지 않았다. 최종 실행 지문, 추가 입력의 결과, 정의/미정 집계와 문구 범위는 최종 결과 감사에서 다시 대조할 대상이다.
