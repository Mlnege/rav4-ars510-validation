"""기존 판단 연결 관측을 동결하고 입력/전송 범위와 물리 미검증을 기록한다."""
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path

WORK=Path(__file__).resolve().parent
ROOT=WORK.parent.parent
base=json.loads((WORK/'whole_default_cases_frozen_summary.json').read_text())
user=json.loads((WORK/'whole_user_profile_summary.json').read_text())
namespace=json.loads((WORK/'namespace_audit.json').read_text())
details=[]
for folder in sorted((WORK/'whole_cases').glob('*')):
  if (folder/'result.json').exists():
    r=json.loads((folder/'result.json').read_text())
    details.append({'kind':r['kind'],'delay_s':r['delay_s'],
      'file':str((folder/'result.json').relative_to(WORK)),
      'initial':r['initial'],'baseline':r['normal_enable_baseline'],
      'first':r['fault_first'],'second':r['fault_second'],'last':r['fault_last'],
      'first_long_inactive_time':r['first_long_inactive_time'],'first_soft_disable_time':r['first_soft_disable_time'],
      'events':r['events'],'rows':len(r['fault_rows']),'source_unchanged':r['source_unchanged'],
      'shortcut_controls_true_calls':r['shortcut_controls_true_calls']})
manifest={str(path.relative_to(WORK)):hashlib.sha256(path.read_bytes()).hexdigest()
          for path in WORK.rglob('*') if path.is_file() and path.suffix in ('.py','.json','.md')
          and path.name!='whole_authority_frozen.json'}
report={'recorded_utc':datetime.now(UTC).isoformat(),'baseline_30':base,'baseline_details':details,
        'user_profile_9':user,'namespace_globals_resolved':namespace['all_tested_method_globals_resolved'],
        'namespace_constants_equal':namespace['all_source_constants_equal'],
        'namespace_methods':sum(len(item['methods']) for item in namespace['classes']),
        'namespace_constants':sum(len(item['constants']) for item in namespace['classes']),
        'runtime_authority_test_scope':'호스트 Python 판정 메서드 연결. 영상/차량상태 생성은 합성 입력, 물리 CI초기화/전송/MCUheartbeat 미검증.',
        'configuration_scope':'기본profile은원형get_params alpha_long=True의명시적합성CP. 기본Params SpeedFromPCM2/EnableRadarTracks0/SignalAssistMode0이며AlphaLongitudinalEnabled키없음. user_requested는메모리0/20/AlphaTrue profile만. 실제사용자운영설정 검증 아님.',
        'signal_and_live_ars_not_integrated':True,'physical_safety_confirmed':False,
        'source_policy_changed':False,'producer_time_threshold_added':False,
        'ci_initialization_scope':'actual_init_executed=False. 초기화IOsink호출만. 사전CAN CRC증거와무관하게ECU/UDS/Panda/차량준비미실행.',
        'clock_body_scope':'model timestampEof는획득/본문출처. logMonoTime은producer헤더. recv_time은원형수신. 새producer헤더의oldbody와header까지old인배달을분리. 물리차량운동은이테스트에서적분하지않음.',
        'source_unchanged':all(row['source_unchanged'] for row in details),
        'input_readiness_fixed_without_bypassing':'첫100Hz planner poll fixture실패를보존하고원형Toyota model20Hz호출로수정. startup/DM/comm event삭제 및enabled/active/longActive 강제값없음.',
        'artifact_sha256':manifest}
(WORK/'whole_authority_frozen.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'base_cases':len(base['cases']),'user_profile_cases':len(user['cases']),
                  'base_process_errors':base['process_errors'],'user_process_errors':user['process_errors'],
                  'source_unchanged':report['source_unchanged'],'namespace_globals_resolved':report['namespace_globals_resolved']},ensure_ascii=False))
