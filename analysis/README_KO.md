# 근본 원인 분리 분석의 범위

소스 63개·패치 8개의 개수와 주행 제어 코드는 유지한다. r7에서는 오프라인 replay.py의 오류 전파 누락만 고쳐 patch01과 manifest 지문을 갱신했다. 실제 CAN의 읽기 관찰과 합성 입력 실험을 구분하며, 실제 PC의 실행 시간도 가상 제어 시간과 분리한다. 분석 코드에 쓰인 절대 작업 경로는 공개 문서·JSON에서 `$LAB`으로 제거했다. `published_analysis_manifest.json`은 원래 실행 근거의 지문과 공개 파일의 지문을 함께 기록한다. 문서에 있는 원래 결과 SHA는 경로 제거 전 파일이며 공개 SHA256SUMS와 구분한다.

실제 로그의 시각 분석은 원본 데이터를 포함하지 않는다. 실행 도구는 당시 작업 폴더 배치를 기준으로 작성됐다. 재현할 경우 준비한 격리 검증 공간과 로컬 원본 로그를 사용하고, `observe_timing.py`는 격리 공간의 `work/log_timing_observation/`에 복사한다. 기본 입력은 그 공간의 `work/input/`이며 결과는 도구와 같은 폴더에 생긴다. 원본 로그를 GitHub에 올리지 않는다.

속도 기준 도구는 `--source-dir`, `--logs-dir`, `--output-dir`를 명시할 수 있다. `validation/native/fusion_contract_grid.py`와 `validation/signal/diagnostic_timing_run06.py`는 기존 원격 준비 도구가 별도 검증 공간에 함께 복사한다. native 계산에는 먼저 별도 고유 빌드를 만들고 CARROT_VALIDATION_BUILD로 지정해야 한다. 실행 중인 빌드를 덮어쓰지 않는다.

`results/host_chain/`의 부모 재실행은 비활성 초기값부터 정상 이벤트로 켜진 호스트 판단을 확인한다. 기본30·추가메모리9 관측과 독립읽기검토를 함께 보존한다. 차량상태 수집·파싱, 물리 CI.init/apply 및 독립 MCU heartbeat는 실행하지 않는다. 기본 메모리 설정은 사용자 실물 설정 전체와 같지 않으며, PCM모드0 속도helper·실물 신호 인식·ARSlive·실차 CAN 전달을 함께 검증한 결과가 아니다. 부분 메모리 적용649회를 실제 CAN 송신 횟수로 읽지 않는다. analysis/host_authority의 도구는 당시 별도 다운로드 검증 checkout·DBC·C라이브러리를사용한 연구배치의 보존본이며 원격준비명령에서자동실행하지않는다. 작업 폴더 배치와 source 의존파일의 정규화지문을 먼저 대조하고, 원형 uv.lock의 tqdm4.70.1 등 의존성을 격리된 가상환경에 준비해야 한다. 운영 설치에 패키지를 추가하지 않는다. 재생하면서 CI.init/apply sink를 실물 함수로 바꾸지 않는다.

압축 계측에는 합성 센서·가상 제어 시각과 실제 PC에서 측정한 실행 시간·단계 비용이 함께 있으며 서로 구분한다. 기존 322ms의 발생 원인이나 실차 제동·회생·PCS/AEB 안전성을 입증하지 않는다. 신선한 producer헤더와 오래된 획득내용, 오래된 producer헤더의 정규 수신, 메시지 미수신은 서로 다른 조건이다. 현재 작업은 계속 진행 중이며 실차 배포 허용은 False다.
