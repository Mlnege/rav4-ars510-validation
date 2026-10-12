"""계산을 재실행하지 않고 원형 실패와 관측·본문 사본의 지문을 고정한다."""
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path


WORK=Path(__file__).resolve().parent
ROOT=WORK.parent.parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())


def main():
  first=read(WORK/'run01/results.json')
  observation=read(WORK/'run02_observation/results.json')
  archive=[]
  for relative,name in (
    ('openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py','long_mpc_original_lf.py'),
    ('openpilot/selfdrive/controls/lib/longitudinal_planner.py','longitudinal_planner_original_lf.py')):
    path=WORK/'original_source_archive'/name
    data=path.read_bytes()
    raw_reconstructed=hashlib.sha256(data.replace(b'\n',b'\r\n')).hexdigest()
    archive.append({'source':relative,'archive':path.relative_to(WORK).as_posix(),
      'sha256_lf':sha(path),'execution_main_sha256_raw':observation['source_before'][relative],
      'lf_to_crlf_sha256':raw_reconstructed,
      'same_body_as_execution_main':raw_reconstructed==observation['source_before'][relative]})
  unique=[]
  for case in observation['cases']:
    rows=read(WORK/'run02_observation'/f"{case['kind']}_rows.json")
    trace_by_time={r['mpc_observed_inputs']['planner_call_time']:r['mpc_observed_inputs'] for r in rows}
    force=[t for t in trace_by_time.values() if t['forceDecel_at_planner'] and t['input_v_cruise_ms']==0]
    lost=[t for t in force if t.get('effective_v_cruise_ms',0)>0]
    witness=next((r for r in rows if r['mpc_observed_inputs']['forceDecel_at_planner']
      and r['mpc_observed_inputs']['input_v_cruise_ms']==0 and r['generated_accel_frames']),None)
    unique.append({'kind':case['kind'],'unique_phase_plan_calls':len(trace_by_time),
      'force_zero_input_plan_calls':len(force),'effective_zero_goal_lost_plan_calls':len(lost),
      'witness':{'relative_s':witness['time']-rows[0]['time'],'state':witness['state'],
        'enabled':witness['enabled'],'longActive':witness['longActive'],'forceDecel':witness['controls_force_decel'],
        'plan_shouldStop':witness['plan_should_stop'],'plan_aTarget':witness['plan_aTarget'],
        'mpc_input':witness['mpc_observed_inputs'],'generated343':witness['generated_accel_frames']}
        if witness else None})
  checks={'first_8_cases_preserved':len(first['cases'])==8 and not first['preparation_errors'],
    'observation_4_cases_preserved':len(observation['cases'])==4 and not observation['preparation_errors'],
    'recorded_source_8_before_after_equal':first['source_unchanged'] and observation['source_unchanged'],
    'compiled_c_unchanged_during_runs':first['library_unchanged'] and observation['library_unchanged'],
    'old_source_lf_body_matches_recorded_crlf':all(r['same_body_as_execution_main'] for r in archive),
    'original_run_code_matches_recorded_sha':sha(WORK/'run01/executed_run.py')==first['script_sha256'],
    'observation_code_matches_recorded_sha':sha(WORK/'run02_observation/executed_run_observation.py')==observation['script_sha256']}
  report={'generated_utc':datetime.now(UTC).isoformat(),'new_dynamic_execution':False,
    'first_run_structural_checks':first['checks_executed'],'observation_structural_checks':observation['checks_executed'],
    'checks':checks,'failures':[k for k,v in checks.items() if not v],
    'source_body_archive':archive,'unique_planner_observations':unique,
    'behavioral_failures_observed':[r['kind'] for r in unique if r['effective_zero_goal_lost_plan_calls']>0],
    'behavioral_scope_ko':'구조 검사 통과와 soft 감속 목표 전달 실패는 별도다. 현재 parent 수정 source를 과거 실행에 소급하지 않는다.',
    'original_result_hashes':{'run01':sha(WORK/'run01/results.json'),'run02_observation':sha(WORK/'run02_observation/results.json')},
    'recorded_radar_reference':{'path':'work/radar_loss_root_review/recorded_radar_contract.json',
       'sha256':sha(ROOT/'work/radar_loss_root_review/recorded_radar_contract.json'),
       'scope_ko':'부모의 별도 원본 OFF 로그 집계를 읽은 근거다. 이 에이전트의 동적 검사 건수에 합하지 않는다.'}}
  (WORK/'frozen_observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  paths=sorted(p for p in WORK.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='evidence_manifest.json')
  manifest={'generated_utc':datetime.now(UTC).isoformat(),'artifact_hashes':{p.relative_to(WORK).as_posix():sha(p) for p in paths}}
  (WORK/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'checks':len(checks),'metadata_failures':report['failures'],
    'behavioral_failure_cases':report['behavioral_failures_observed'],
    'unique_force_zero_goal_lost':{r['kind']:r['effective_zero_goal_lost_plan_calls'] for r in unique},
    'artifacts':len(paths)},ensure_ascii=False))
  raise SystemExit(1 if report['failures'] else 0)


if __name__=='__main__':main()
