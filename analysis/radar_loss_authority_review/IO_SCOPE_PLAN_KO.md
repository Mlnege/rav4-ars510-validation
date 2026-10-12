# 레이더 누락과 호스트 권한의 구분 검사

현재 SelfdriveD는 CP.radarUnavailable 자체로 레이더 오류를 무시하지 않는다. radarState Event.valid=False일 때 오류 종류에 따라 canError·radarTempUnavailable·radarFault 또는 commIssue를 만든다. 건강한 빈 lead, 오류True/validTrue, validFalse+오류, producer 중단을 분리한다.

읽기는 원형 SelfdriveD→StateMachine→Controls→LongitudinalPlanner/MPC와 radarcan/DPath producer 계약을 따른다. R9의 독립 진단 mode1과 실제 Toyota runtime의 radarUnavailable=True→mode-2 선택을 구분한다. R9 원본 OFF 결과는 읽기 참고로만 사용한다.

새 최소 합성 검사는 기존 PCM 호스트 하네스를 이 폴더에 복사한 것이다. 초기 False→정상 PCM MAIN/engage 이벤트로 원형 상태기계가 enabled를 만들고 실제 C는 정상 메모리 PCM RX로만 권한을 만든다. CP.radarUnavailable=True를 유지하며 운영 Params·CI.init·차량 TX는 실행하지 않는다. init_tests의 counter2 초기화도 제거했다. C/host 권한 setter를 사용하지 않는다.

입력 baseline은 고정 ego15m/s, 건강한 합성 모델/pose/기어/문/벨트/페달이며 radarState의 기본 lead.status=False다. 새 레이더 point나 실제 객체를 만들지 않는다. ‘point가 사라지면 DPath가 어떻게 lead를 선택하는가’ 전체 perception 검사는 포함하지 않는다. 모델 영상 lead로 대체될 수 있으므로 빈 lead 계약만 검사한다.

baseline의 정상 활성화 후 radarState를 4초 동안 건강한 빈 lead 유지, 오류True/validTrue, validFalse+canError/temp/fault/wrongConfig/오류없음, producer 중단으로 공급한다. 오류True/validTrue는 정상 radarcan→DPath producer 계약과 모순되는 합성 입력이며 실차 재현으로 표현하지 않는다. 센서 관측·차량 운동·ARS live·PCS/AEB·회생·실물 MCU heartbeat는 미검증이다.

원형 판정 메서드는 바꾸지 않고 합성 radarState 발행 경계만 조정한다. 가상100Hz/모델20Hz이며 실제 wall 스케줄링·제동 거리를 측정하지 않는다. source와 기존 결과/.so/outputs/release는 변경하지 않는다. stdout 원형 코어 출력은 폐기하고 익명 판정 결과만 저장한다.
