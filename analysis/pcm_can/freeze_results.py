"""호스트·실제 Toyota 생성·메모리 C TX 결과와 한계를 함께 고정한다."""
from collections import Counter
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
  suite=json.loads((WORK/'suite_summary.json').read_text())
  baseline=json.loads((WORK/'baseline.json').read_text())
  replay=json.loads((WORK/'can_revalidation_summary.json').read_text())
  namespace=json.loads((WORK/'namespace_audit.json').read_text())
  history=json.loads((ROOT/'work/validation_run/release_stopping_reproduction.json').read_text())
  cases=[json.loads((WORK/'cases'/row['kind']/'result.json').read_text()) for row in suite['cases']]
  generated=[row for case in cases for row in case['generated_can_rows']]
  accel=[row for row in generated if row['address']==0x343]
  release_observations={}
  for case in cases:
    if case['kind'] in ('gas_restart','brake_restart','button_cancel_restart','cancel_restart','main_off_restart'):
      field='gas' if case['kind']=='gas_restart' else 'brake' if case['kind']=='brake_restart' else None
      if field is not None:
        released=next(r for r in case['rows'] if not r[field])
        release_observations[case['kind']]={k:released[k] for k in ('time','state','enabled','active','longActive','engaged','c_controlsAllowed','c_longitudinal_allowed')}
  native_folder=LAB/'work/native_sim/build_unique/c_generated_code'
  native={name:sha(native_folder/name) for name in history['native_solver_before']}
  safety=sha(LAB/'work/safety_validation/libsafety_download_native.so')
  all_hashes={}
  for case in cases:
    for name,digest in case['source_hashes'].items():all_hashes.setdefault(name,set()).add(digest)
  source_same=all(len(values)==1 and sha(SOURCE/name) in values for name,values in all_hashes.items())
  metadata={
    'recorded_utc':datetime.now(UTC).isoformat(),'case_count':len(cases),
    'host_can_assertion_count':sum(len(c['checks']) for c in cases),
    'host_can_assertion_failures':sum(len(c['failures']) for c in cases),'process_errors':suite['process_errors'],
    'independent_c_replay_assertions':replay['assertion_count'],'independent_c_replay_failures':replay['failure_count'],
    'generated_message_count':len(generated),'generated_accel_count':len(accel),
    'c_accepted':sum(r['actual_tx']==1 for r in generated),'c_blocked':sum(r['actual_tx']==0 for r in generated),
    'expected_blocked':sum(r['expected_tx']==0 for r in generated),
    'c_tx_mismatches':sum(not r['tx_matches_expected'] for r in generated),
    'tx_authority_mutations':sum(not r['tx_does_not_create_authority'] for r in generated),
    'messages_by_address':{hex(key):value for key,value in sorted(Counter(r['address'] for r in generated).items())},
    'dbc_message_count':sum(r['dbc_parse_updated'] is not None for r in generated),
    'dbc_decode_failures':sum(r['dbc_parse_updated'] is False for r in generated),
    'toyota_checksum_message_count':sum(r['toyota_checksum_ok'] is not None for r in generated),
    'toyota_checksum_failures':sum(r['toyota_checksum_ok'] is False for r in generated),
    'raw_accel_min':min(r['raw_accel_signed'] for r in accel),'raw_accel_max':max(r['raw_accel_signed'] for r in accel),
    'controller_apply_count':sum(c['last']['actual_ci_apply_calls'] for c in cases),
    'card_state_update_count':sum(c['last']['ci_update_io_calls'] for c in cases),
    'baseline_additional_can_messages':len(baseline['generated_messages']),
    'source_hashes':{name:next(iter(values)) for name,values in all_hashes.items()},
    'all_case_source_hashes_still_same':source_same,'native_solver_hashes':native,
    'native_solver_matches_prior_immutable':native==history['native_solver_before'],
    'safety_library_hash':safety,'safety_matches_prior_immutable':safety==history['safety_library_sha256'],
    'namespace_method_count':sum(len(c['methods']) for c in namespace['classes']),
    'namespace_constant_count':sum(len(c['constants']) for c in namespace['classes']),
    'namespace_all_resolved':namespace['all_tested_method_globals_resolved'],
    'namespace_all_constants_same':namespace['all_source_constants_equal'],
    'configuration':baseline['configuration'],'cases':suite['cases'],
    'driver_pedal_release_observations':release_observations,
    'actual_card_state_update':True,'actual_ci_apply':True,'actual_toyota_carcontroller':True,
    'actual_canpacker':True,'can_backend':'python (original CANPacker/Parser; Cython CAN unavailable)',
    'actual_generated_message_dbc_decode':True,'actual_c_memory_rx_permission':True,'actual_c_memory_tx':True,
    'actual_ci_update':False,'actual_vehicle_receive_can_parser':False,'actual_vehicle_init_or_tx':False,
    'actual_carrotserv_network_route':False,'live_ars_or_signal_mode2':False,'physical_compatibility_confirmed':False,
    'scope_ko':'합성 수신/feedback/메모리 설정의 원형 호스트→실제 CI.apply/ToyotaCC/CANPacker/DBC decode→같은 실제 C TX. 판정/상위권한 고정 대체 없음. 물리 ECU/MCU/PCS/회생/차량 초기화·송신은 미검증.'}
  (WORK/'frozen_results.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
  by_kind={c['kind']:c for c in cases}
  lines=[
    '# Mode0 호스트 → Toyota CAN 생성 → 메모리 C 권한 검사',
    '',
    f'원형 호스트 속도·권한 체인에서 실제 Toyota CarController/CANPacker가 생성한 {len(generated):,}개 CAN 메시지를 같은 C 안전 검사에 연결했다. 11개 시나리오의 {metadata["host_can_assertion_count"]}개 판정이 직접 통과했고, 추가 독립 재생 {metadata["independent_c_replay_assertions"]}개 판정도 통과했다. C 판정 불일치·TX에 의한 권한 생성은 모두0이다. 취소·가속·제동·MAINoff 첫 틱의 이전 큐 양수 가감속 메시지4개는 예상대로 차단됐으므로 이것을 오류로 세지 않는다.',
    '',
    '## 실제 코드와 합성 입력의 경계',
    '',
    '실제 Card 생성자/state_update/state_publish/controls_update/step, VCruiseCarrot/Mode0, CarrotPlanner/LongitudinalPlanner, 기존 C/Cython MPC, SelfdriveD/StateMachine, Controls/LongControl을 유지했다. CI.apply는 이번에는 sink 대신 실제 CarInterfaceBase.apply→Toyota CarController.update→원형 CANPacker를 호출한다. 원형 Card가 실제 capnp sendcan 메모리 이벤트도 발행한다. 이후 같은 정상 PCM RX 기반 C probe가 각 실제 address/payload/bus의 TX hook 판정을 수행한다. 드라이버·USB·Panda·차량 소켓은 없다.',
    '',
    'CI.update 반환은 여전히 합성 CarState이다. Toyota CAN 수신/DBC 파서는 실행하지 않았고 canValid는 건강 입력 선언이다. actual CI.CS.out에는 이 builder를 저장한다. ego15m/s·aEgo0·GVC0·steering feedback0·stock follow distance3·stock camera HUD빈값·PCM status8/0은 명시적인 입력 가정이다. CS.out와 GVC를 실제 측정값이라고 하지 않는다. 제동/모터/엔진/ECU 반응을 제어 출력으로 적분한 실험도 아니다.',
    '',
    '원형 get_params의 RAV4 2022 alpha 인수로 CP flags1372/pcmCruiseTrue/directLongTrue/radarUnavailableTrue를 생성한다. 원형 Card constructor가 memory alternativeExperience1과 passivity를 정한다. 메모리 SpeedFromPCM0/LongActuatorDelay20/AlphaTrue, Tracks0/Signal0/NNFF0이다. disabled/initializedFalse에서 정상 초기화와 PCM enable으로 활성화했다. CI.init 본문은 실행하지 않고 원형 준비 조건이 I/O sink를1회 호출했다. MCU/ECU 실제 준비나 운영 설정을 검증한 결과가 아니다.',
    '',
    '## 정상 생성과 제한',
    '',
    '| 입력/경계 | 실제 결과 |',
    '|---|---|',
    '| 정상 PCM75→90 및75→60→85 | 실제 Mode0→발행CarState 속도 반영. 기본 연비 +2km/h 때문에 계획은92 또는62/87일 수 있음 |',
    f'| 지도40 | CS설정75 유지, 계획40, Controls 최소{by_kind["map40"]["min_control_accel"]:.3f}m/s²; 음수0x343 생성과 C허용 확인 |',
    f'| 합성 곡선/지도40+곡선 | 원형 curve_speed/VisionCurveSpeed 계산의 정수32가 계획에 반영. Controls 최소{by_kind["combined"]["min_control_accel"]:.3f}m/s²; 실제 음수CAN/C허용 확인 |',
    '| 무효cap0 / navigation 중단 | 무효0 무시, 원형1초 나이 조건 뒤 제한해제. 신선한 직선 모델로 곡선 제한도 복귀 |',
    f'| 실제 생성0x343 | {len(accel):,}개; 독립 signed16 raw와 DBC ACCEL_CMD×1000 동일. 관측범위 raw {metadata["raw_accel_min"]}..{metadata["raw_accel_max"]}, C한계-3500..2000 안 |',
    f'| DBC/체크섬 | DBC에 정의된 메시지 {metadata["dbc_message_count"]:,}개 정상해독, 체크섬 정의가 있는 {metadata["toyota_checksum_message_count"]:,}개 모두 정상. 0x750는 임의DBC를 정의하지 않고 기존 exact tester-present만 검사 |',
    '',
    '곡선 계산에는 실제 source 함수를 썼지만 모델은 합성 반경50m 궤적이다. CarrotMan desiredSpeed 발행과 지도 cap40은 합성 I/O이며 CarrotServ/지도 서버/GPS는 미실행이다. ARS 실제 수신 트랙과 SignalMode2도 이 경로에 추가하지 않았다.',
    '',
    '## 일반 권한과 종방향 권한을 따로 확인',
    '',
    '| 조건 첫 가감속 메시지 | host 새 longActive | card 이전CC longActive | C controls / long_allowed | 실제 raw0x343 / C TX |',
    '|---|---|---|---|---|',
  ]
  for kind in ('cancel_restart','button_cancel_restart','gas_restart','brake_restart','main_off_restart'):
    case=by_kind[kind]
    row=case['fault_first_accel_can']
    lines.append(f'| {kind} | {case["first"]["longActive"]} | {row["cc_longActive"]} | {row["c_controls_before"]} / {row["c_longitudinal_before"]} | {row["raw_accel_signed"]} / {row["actual_tx"]} |')
  lines.extend([
    '',
    '첫 운전자 입력에 원형 host는 longActive를 False로 만들지만, 명시한 actor 순서에서는 card가 이미 큐에 있던 직전CC를 적용한다. actual Controller frame을 고치지 않고 건강한 틱을 한 번 더 돌려 첫 fault를3프레임 ACC 경계에 맞췄다. 실제 raw1114(1.114m/s²)가 남은 순간에도 가속 alt1의 controlsAllowedTrue/long_allowedFalse를 실제 C getter가 구분했고 TX0으로 차단했다. 브레이크/PCMoff/MAINoff도 같은 예상 차단을 확인했다. 다음 CC는 비활성이고 원형33.33Hz의 다음 ACC에는 raw0가 나오며 비활성 명령은 C에서 허용한다.',
    '',
    '버튼 취소만 넣었을 때는 PCM engaged가 아직True라 C권한이 남는다. 이 경우 첫 이전 큐 양수는 C가 허용하고 다음 ACC 경계에서 원형 host의raw0가 나온다. 이것을 PCMoff 동반 취소와 혼동하지 않는다.',
    '',
    f'가속 페달 override는 enabled=True를 유지하므로0.20초 후 페달을 뗀 {release_observations["gas_restart"]["time"]:.2f}초에 state=enabled/longActive=True/C.long_allowed=True로 실제 복귀했다. 이때 PCM engaged는 계속True였고 PCMoff/on을 아직 넣지 않았다. 제동 해제 {release_observations["brake_restart"]["time"]:.2f}초에는 state=disabled/longActive=False가 유지됐다. 이후 각 시나리오의 정상 PCMoff→on 전환과80km/h 재활성화는 별도 입력이다. 가속해제 복귀와 disabled 취소/제동의 재시작을 하나로 묶지 않는다. 이 검사는 SignalMode0이므로 Signal2의 red-hold가 페달복귀 때 보존되는지까지 검증한 결과가 아니다.',
    '',
    '독립 저장CAN 재생에서 전 메시지의 C relay_malfunctionFalse와 원래 controls/long_allowed/TX 결과를 실제 getter로 다시 확인했다. LKA torque0, LTA request/request2/angle/winddown0, 정확한 bus0/주소/DLC도 저장해독 값 전체에서 확인했다. 따라서 비ACC expectedTX1은 이 비작동 조향/relayFalse/정확형식 조건 안의 기대값이다. 임의 다른 torque/angle/relay 상태를 허용하는 규칙으로 확장하지 않는다. C가TX로권한을만들지않는검사는매메시지before/aftergetter를비교했다.',
    '',
    '## 실제 제어기 주기와 PCS/진단 메시지',
    '',
    '| 메시지 | 전체 생성 수 | 실제 검사/한계 |',
    '|---|---|---|',
  ])
  descriptions={0x2e4:'매 actual Controller frame, DLC5. 원형 DBC checksum/torque0 검사',
    0x191:'2 Controller frame마다, DLC8. 비작동LTA/counter/checksum 검사',
    0x343:'3 Controller frame/30ms마다, DLC8. signed 가속·C권한·한계 검사',
    0x412:'20frame 기본5Hz와 cancel/alert 추가 발행. 단일 고정5Hz라고 하지 않음',
    0x411:'100frame 기본1Hz와 cancel/alert 추가 발행. PCS_INDICATOR1/PCS_OFF1 관측',
    0x750:'20frame 기본5Hz. 정확한 radar tester-present 바이트만; DBC추측정의 없음'}
  for address,count in sorted(Counter(r['address'] for r in generated).items()):
    lines.append(f'| {hex(address)} | {count:,} | {descriptions[address]} |')
  lines.extend([
    '',
    '최초apply는 합성시각100.51초이며 Controller frame0다. 전체 호스트 틱과 Controller frame은51틱 차이가 있으므로 주기는 actual Controller frame/생성시각으로 검증했다. 0x343는3frame/30ms, LKA1frame, LTA2frame이 전 구간 일치했다. 버튼취소/제동 이후 PCM이남은구간의 반복cancel 때문에 UI/PCS HUD가 추가 발행될 수 있다.',
    '',
    '0x411는 원형 helper가 PCS_INDICATOR=1와PCS_OFF=1을 작성했고 C는 이를 허용한다. C의 허용은 PCS body효능이나 순정PCS/AEB보존 검증이 아니다. 0x750의 tester-present 허용도 실제 UDS초기화/ECU응답/PCS유지 증거가 아니다. 이 원형 alpha CP에는 stock-radar disable 경로가 있으므로 물리 송신/CI.init는 계속 금지했다. 실제 PRE_COLLISION actuation0x283/0x183는 이 제어기 경로에서 생성하지 않았다. 별도 실차 PCS/AEB와 회생 검증이 필요하다.',
    '',
    '이 DBC에 전체 종방향 작동을 표시하는 CanActive 필드는 없다. CC.longActive, C.controlsAllowed, C.long_allowed, 가속raw!=0, C TX허용은 별개의 값으로 보고한다. 새신호/버튼스팸/RES·SET CAN은 만들지 않았다. 원형 거리버튼DISTANCE 조정은 고정 stock follow거리와 기존 leadDistanceBars가 다른 경우 메모리에서 발생할 수 있고 신규버튼프로토콜 구현이 아니다.',
    '',
    '## 원형 보존과 재현',
    '',
    f'호스트3클래스19메서드/25상수의 원형 namespace 대조가 일치했다. 실제 Controller apply {metadata["controller_apply_count"]:,}회, Card.state_update 합성 반환 {metadata["card_state_update_count"]:,}회다. 추가 정상baseline의 CAN {metadata["baseline_additional_can_messages"]:,}개는 이11시나리오 총계에 중복 합산하지 않았다. 원형 source hash는 각 실행/현재파일과 같고 MPC6개/C안전 라이브러리는 이전 immutable hash와 같다. 수신/생성 CANPacker/Parser backend는 원형 Python이고 MPC/C안전은 실제 native다. 전체 Konik/ARM/운영빌드 성공을 뜻하지 않는다.',
    '',
    '```sh',
    '# WSL Ubuntu에서 프로젝트 루트 기준, 기존 격리환경/immutable build 읽기',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_can_authority_integration/run_baseline.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_can_authority_integration/run_suite.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_can_authority_integration/audit_namespace.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_can_authority_integration/revalidate_can.py',
    'work/download_e2e/work/offline-venv/bin/python work/pcm_can_authority_integration/freeze_results.py',
    '```',
    '',
    '실제Toyota CAN 수신/CI.update, stockCamera/GVC/aEgo보정, firmware/ECU와트랙연결, 실물Panda/heartbeat/relay, OS실시간일정, 제동거리/회생/PCS·AEB/차량안전은 미검증이다. 생성CAN과C hook의메모리정합성을이범위까지입증했다. source·기존fixture/results·.so·venv·운영Params·차량은바꾸지않았으며 새파일은 work/pcm_can_authority_integration 안에만 있다.',
  ])
  (WORK/'RESULTS_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
  # 실행 중 stdout파일과 자신을 제외하고 완성된 증거 파일 해시를 별도 고정한다.
  files=[p for p in WORK.rglob('*') if p.is_file() and p.suffix in ('.py','.md','.json','.log') and
         p.name not in ('evidence_manifest.json','freeze_execution.log')]
  manifest={'recorded_utc':datetime.now(UTC).isoformat(),'files':{str(p.relative_to(WORK)):sha(p) for p in sorted(files)}}
  (WORK/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
  gates=['all_case_source_hashes_still_same','native_solver_matches_prior_immutable','safety_matches_prior_immutable',
         'namespace_all_resolved','namespace_all_constants_same']
  assert not metadata['process_errors'] and not metadata['host_can_assertion_failures'] and not metadata['independent_c_replay_failures']
  assert all(metadata[k] for k in gates) and metadata['c_tx_mismatches']==0 and metadata['tx_authority_mutations']==0
  assert metadata['c_blocked']==metadata['expected_blocked']==4
  print(json.dumps({k:metadata[k] for k in ('case_count','host_can_assertion_count','independent_c_replay_assertions',
      'generated_message_count','generated_accel_count','c_blocked','c_tx_mismatches',*gates)},ensure_ascii=False))


if __name__=='__main__':main()
