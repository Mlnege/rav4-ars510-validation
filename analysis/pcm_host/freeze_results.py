"""직접 실행한 합성 호스트 연결 결과와 원형/바이너리 증거를 따로 고정한다."""
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path

WORK=Path(__file__).resolve().parent
ROOT=WORK.parent.parent
SOURCE=ROOT/'work/carrotpilot'
LAB=ROOT/'work/download_e2e'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
  baseline=json.loads((WORK/'baseline.json').read_text())
  suite=json.loads((WORK/'suite_summary.json').read_text())
  namespace=json.loads((WORK/'namespace_audit.json').read_text())
  history=json.loads((ROOT/'work/validation_run/release_stopping_reproduction.json').read_text())
  cases=[json.loads((WORK/'cases'/row['kind']/'result.json').read_text()) for row in suite['cases']]
  native_folder=LAB/'work/native_sim/build_unique/c_generated_code'
  native={name:sha(native_folder/name) for name in history['native_solver_before']}
  safety=sha(LAB/'work/safety_validation/libsafety_download_native.so')
  all_hashes={}
  for case in cases:
    for name,digest in case['source_hashes'].items():
      all_hashes.setdefault(name,set()).add(digest)
  source_same=all(len(values)==1 and sha(SOURCE/name) in values for name,values in all_hashes.items())
  result={
    'recorded_utc':datetime.now(UTC).isoformat(),'case_count':len(cases),
    'assertion_count':sum(len(c['checks']) for c in cases),'assertion_failures':sum(len(c['failures']) for c in cases),
    'process_errors':suite['process_errors'],'state_update_io_call_count':sum(c['last']['ci_update_io_calls'] for c in cases),
    'baseline_extra_state_update_io_calls':baseline['changed_speed_final']['ci_update_io_calls'],
    'source_hashes':{name:next(iter(values)) for name,values in all_hashes.items()},
    'all_case_source_hashes_still_same':source_same,'native_solver_hashes':native,
    'native_solver_matches_prior_immutable':native==history['native_solver_before'],
    'safety_library_hash':safety,'safety_matches_prior_immutable':safety==history['safety_library_sha256'],
    'namespace_method_count':sum(len(c['methods']) for c in namespace['classes']),
    'namespace_constant_count':sum(len(c['constants']) for c in namespace['classes']),
    'namespace_all_resolved':namespace['all_tested_method_globals_resolved'],
    'namespace_all_constants_same':namespace['all_source_constants_equal'],
    'configuration':baseline['configuration'],'cases':suite['cases'],
    'actual_ci_update':False,'actual_can_parser':False,'actual_card_state_update':True,
    'actual_capnp_can_conversion':True,'actual_native_mpc':True,'actual_c_memory_rx_permission':True,
    'actual_carrotserv_network_route':False,'actual_vehicle_init_or_tx':False,
    'live_ars_or_signal_mode2':False,'physical_compatibility_confirmed':False,
    'scope_ko':'원형 호스트 상태/속도/계획/권한 연결 검사. CI.update/수집/설정/발행 경계는 명시적 메모리 I/O, source 판단 고정 치환 없음. 원형 곡선 계산은 합성 모델에 실행하며 지도 cap은 합성. 실제 ECU·PCS·회생·Konik 일정을 입증하지 않음.'}
  # 이 과정의 stdout 로그는 실행 중 열려 있으므로 최종 증거 해시에 포함하지 않는다.
  files=[p for p in WORK.rglob('*') if p.is_file() and p.suffix in ('.py','.md','.json','.log') and p.name not in ('frozen_results.json','RESULTS_KO.md','freeze_execution.log')]
  result['evidence_hashes']={str(p.relative_to(WORK)):sha(p) for p in sorted(files)}
  (WORK/'frozen_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  by_kind={c['kind']:c for c in cases}
  lines=[
    '# Mode0 수신 속도와 호스트 권한 연결 검사 결과',
    '',
    f'원형 Card.state_update를 추가한 새 검사에서 {len(cases)}개 시나리오의 {result["assertion_count"]}개 판정이 직접 통과했다. 실패 {result["assertion_failures"]}개, 실행 오류 {result["process_errors"]}개다. 기존 whole authority 검사는 이 메서드를 차량 상태 I/O로 대체했으므로, 그 결과에서 실제 속도 helper까지 통합됐다고 확장할 수 없다. 이번 새 결과가 그 빠진 호스트 경로를 확인한다.',
    '',
    '## 실제 실행과 입력 대체',
    '',
    '원형 Car 클래스의 생성자/state_update/state_publish/controls_update/step 전체를 실행했다. VCruiseCarrot와 ToyotaPcmSetSpeedSync를 바꾸지 않고, 실제 capnp 차량 상태 발행 → 원형 CarrotPlanner/LongitudinalPlanner → 기존 C/Cython MPC → SelfdriveD/StateMachine → Controls/LongControl → card의 적용 경계로 연결했다. SubMaster의 수신/빈도/유효 판정도 원형 메시지 반복으로 형성했다. SIMULATION/REPLAY와 상위 enabled/active 강제 고정은 없다.',
    '',
    'CAN 소켓은 빈 CAN 프레임 목록의 실제 capnp 이벤트를 100 Hz로 전달한다. pandad capnp 변환은 실제 실행하지만, CI.update는 건강한 합성 CarState builder를 반환하는 I/O 대체다. 따라서 Toyota CAN 파서/DBC에서 PCM 속도를 해독했다고 주장하지 않는다. canValid=True는 합성 입력의 선언이다. 실제 CI.init/apply와 차량 송신은 실행하지 않았다. 원형 초기화 조건이 I/O sink init를 1회 호출한 뒤 initialized_prev/ControlsReady를 만들었다. 독립 실제 C Toyota 안전 수신 권한은 정상 메모리 PCM RX로 생성했고 controlsAllowed=True 직접 설정은 0회다. 실물 Panda/MCU heartbeat/PCS 준비는 미검증이다.',
    '',
    '공장 get_params에 정확한 RAV4 2022와 alpha_long=True 인수를 사용했다. 메모리 설정은 SpeedFromPCM=0, LongActuatorDelay=20, AlphaLongitudinalEnabled=True, EnableRadarTracks=0, SignalAssistMode=0, NNFF=0이다. CP flags=1372, pcmCruise=True, directLong=True, radarUnavailable=True, alternativeExperience=1은 원형 생성 결과다. CP의 longitudinalActuatorDelay 약0.15초와 사용자가 입력한 계획 보정0.20초는 다른 값이다. 운영 설정/CP flags/FW를 강제로 바꾸지 않았다.',
    '',
    '## 직접 비교',
    '',
    '| 입력 | 실제 차량 상태/계획의 결과 | 제어 출력/권한 |',
    '|---|---|---|',
    f'| 초기 MAIN/PCM 활성화 | 생성 시 모두 비활성 → 초기화100.50초 → PCM 상승102.00초 → 설정75km/h | 정상 enabled/active/longActive=True; init sink1회 |',
    '| PCM 속도75→90 | 실제 helper와 발행 carState.vCruise90; 계획92 | 기본 CruiseEcoControl=2의 +2 여유분이다. 동일속도라고 설명하지 않는다 |',
    '| PCM75→60→85 | carState.vCruise가 모든 해당 틱에서60/85 | 계획은 각각62/87. ego54km/h 고정이므로 이 속도 변경만으로 강제 감속을 기대하지 않는다 |',
    f'| 지도 cap40 | 설정/표시75 유지, 계획40 | Controls 최소 {by_kind["map40"]["min_control_accel"]:.3f}m/s² |',
    f'| 합성 곡선 + 원형 계산 | yaw0.3rad/s·속도15m/s의 반경50m 경로에서 cap{by_kind["curve"]["first"]["curve_cap_kph"]:.3f}km/h; 실제 desiredSpeed 정수32와 계획32 | Controls 최소 {by_kind["curve"]["min_control_accel"]:.3f}m/s²; 신선한 직선 이후 계획77로 복귀 |',
    f'| 지도40 + 곡선 | 더 낮은 곡선 정수32가 계획에 적용 | Controls 최소 {by_kind["combined"]["min_control_accel"]:.3f}m/s² |',
    '| 무효 cap0 / 발행 중단 | 0은 사용하지 않음. 수신 중단 후 기존 get_carrot_man의1초 나이 조건으로 cap 해제 | 무효 기본 메시지가 정지 명령이 되지 않음 |',
    '| 취소·가속·제동·MAIN 해제 | 첫 틱 longActive=False; 다음 틱 card 큐에서도 비활성. 정상 PCM off/on을 입력한 재시작 후 설정80 | 취소/제동/MAIN은 disabled, 가속은 권한 상태 overriding에서도 longActive=False |',
    '',
    '곡선 계산에는 원형 curve_speed/VisionCurveSpeed를 사용했다. 하지만 모델은 합성 원 궤적이며 CarrotMan 발행은 합성 I/O다. CarrotServ 서버·지도 route 조합·GPS·실제 도로 곡률은 실행/검증하지 않았다. 지도 cap40 역시 실제 내비게이션 측정값이 아니다. SignalMode2와 ARS live 통합도 이번 범위에 포함하지 않는다.',
    '',
    '## 큐 시점과 독립 권한',
    '',
    '| 조건 첫 틱 | State/enabled/active/longActive | card 이전 큐 longActive / 다음 틱 | 실제 C controlsAllowed |',
    '|---|---|---|---|',
  ]
  for kind in ('cancel_restart','button_cancel_restart','gas_restart','brake_restart','main_off_restart'):
    case=by_kind[kind]
    a,b=case['first'],case['second']
    lines.append(f'| {kind} | {a["state"]}/{a["enabled"]}/{a["active"]}/{a["longActive"]} | {a["card_latest_longActive"]} / {b["card_latest_longActive"]} | {a["c_controlsAllowed"]} |')
  lines.extend([
    '',
    '위 순서는 외부입력 → card 상태발행/이전CC 적용 → model20Hz계획 → selfdrived → controls100Hz발행이다. 취소 첫 틱에 card 이전CC가 활성인 것은 이 명시적인 큐 실행 순서에 따른 값이며 실차 결함으로 단정하지 않는다. 버튼 취소만 넣은 첫 틱에는 C controlsAllowed가 유지된다. 가속도 alternativeExperience=1에 따라 이 플래그는 유지될 수 있으며, controlsAllowed만으로 가속 중 종방향 명령 허용이라고 해석하지 않는다. 이 검사는 실제 C TX hook을 전체 생성 명령에 연결한 검사가 아니다. 페달/취소 해제만으로 재개됐다는 결론도 아니다. 각 재시작 입력은 실제 스키마의 PCM off→on 전환을 별도로 포함한다.',
    '',
    '## 원형 불변성과 재현 범위',
    '',
    f'판정3클래스 {result["namespace_method_count"]}메서드의 global binding이 모두 해결됐고, 원형 상수 {result["namespace_constant_count"]}개가 일치했다. 각 결과가 기록한 원형 source hash는 서로 같으며 현재 파일과도 일치한다. MPC 공유 라이브러리6개와 실제 C 안전 라이브러리는 앞선 독립 다운로드 검사의 immutable hash와 모두 같다. Card.state_update 합성 I/O 호출은 시나리오 합계 {result["state_update_io_call_count"]}틱, 별도 baseline {result["baseline_extra_state_update_io_calls"]}틱이다.',
    '',
    '실행 명령(WSL Ubuntu, 프로젝트 루트에서):',
    '',
    '```sh',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_host_integration/run_baseline.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_host_integration/run_suite.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_host_integration/audit_namespace.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_host_integration/freeze_results.py',
    '```',
    '',
    '결과는 가상100Hz와 고정 ego15m/s의 호스트 연결 검사다. 실제 차량 속도를 제어 출력으로 적분하지 않으므로 실제 제동 거리/충돌 회피/회생 전류를 평가한 결과가 아니다. OS 실시간 일정과 MCU/차량 ECU의 독립 정지도 미검증이다. 최종 CI.apply가 I/O sink이므로 전체 Toyota CarController 생성 CAN/TX의 실차 성공을 뜻하지 않는다. 실제 수집/파서부터 검증하려면 원형 Toyota CI.update에 검증된 수신 CAN과 정확한 firmware/DBC를 공급하는 별도 경로가 필요하다.',
    '',
    '생산 source, 기존 whole_* 도구/결과, 공유 라이브러리, venv, 운영 Params, 차량 설치는 변경하지 않았다. 새 파일은 work/pcm_host_integration 안에만 추가/수정했다. 기존 결과를 이 새 결과로 덮어쓰지 않았다.',
  ])
  (WORK/'RESULTS_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
  gates=['all_case_source_hashes_still_same','native_solver_matches_prior_immutable','safety_matches_prior_immutable',
         'namespace_all_resolved','namespace_all_constants_same']
  assert not result['process_errors'] and not result['assertion_failures'] and all(result[k] for k in gates)
  print(json.dumps({k:result[k] for k in ('case_count','assertion_count','assertion_failures','state_update_io_call_count',*gates)},ensure_ascii=False))


if __name__=='__main__':main()
