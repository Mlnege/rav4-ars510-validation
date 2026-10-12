"""최초 실행을 덮지 않고 완료한 관측 합계와 지문을 별도 고정한다."""
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path


WORK=Path(__file__).resolve().parent
ROOT=WORK.parent.parent
FINAL=WORK/'final_observation'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
  FINAL.mkdir(exist_ok=True)
  cases=[read(WORK/f'{alias}_first/results.json') for alias in ('log_a','log_b','log_c','log_d')]
  usable=[r for r in cases if r['status']=='paired_original_cp_host_can_observed']
  counts={name:sum(r.get(name,0) for r in usable) for name in
    ('can_count','c_tx_accept_count','c_tx_deny_count','defined_tx_expectations','undefined_tx_expectations','nonzero_accel_requests')}
  counts.update({name:sum(r['counts'].get(name,0) for r in usable) for name in
    ('host_ticks','host_enabled','host_active','longActive','native_mpc_models','radar_lead_consumed_models',
     'c_controls_true_ticks','c_long_true_ticks','c_relay_true_ticks','c_rx_invalid_true_ticks')})
  counts['points']=sum(r['radar']['counts']['points'] for r in usable)
  counts['records']=sum(r['radar']['adapter_diagnostics']['records'] for r in usable)
  counts['radarState_error_models']=sum(r['radar']['counts']['radarState_error_models'] for r in usable)
  counts.update({name:sum(r['policy']['counts'].get(name,0) for r in usable) for name in
    ('all_can_items','physical_rx','returned_notifications','rejected_notifications','unknown_src')})
  namespace=read(WORK/'namespace_audit.json')
  times=read(WORK/'wire_time_results.json')
  capture=read(WORK/'initial_source_capture.json')
  independent_path=ROOT/'work/paired_host_policy_root/comparison.json'
  independent=read(independent_path)
  checks={'three_original_data_runs_completed':len(usable)==3 and all(not r['failures'] for r in usable),
    'fifty_four_direct_checks_passed':sum(len(r['checks']) for r in usable)==54,
    'insufficient_c_not_filled':cases[2]['status']=='insufficient_carParams' and not cases[2]['whole_host_executed'],
    'native_radar_inputs_observed':counts['radar_lead_consumed_models']==175,
    'recorded_off_conditions_preserved':all(counts[k]==0 for k in ('host_enabled','host_active','longActive','nonzero_accel_requests')),
    'c_rx_categories_match_all_items':counts['all_can_items']==sum(counts[k] for k in
      ('physical_rx','returned_notifications','rejected_notifications','unknown_src')) and counts['unknown_src']==0,
    'known_and_unknown_tx_scope_preserved':counts['can_count']==counts['defined_tx_expectations']+counts['undefined_tx_expectations'],
    'c_tx_results_sum_to_generated':counts['can_count']==counts['c_tx_accept_count']+counts['c_tx_deny_count'],
    'separate_wire_time_check_zero_differences':times['failed_count']==0,
    'namespace_bindings_and_constants_match':namespace['all_tested_method_globals_resolved'] and namespace['all_source_constants_equal'],
    'first_a_executed_code_preserved':capture['same'] and sha(WORK/'first_a_executed_source.py')==capture['first_runner_sha256'],
    'b_d_broader_sources_unchanged':all(r['source_unchanged'] for r in usable if r['alias']!='log_a'),
    'all_shared_library_fingerprints_unchanged':all(r['library_unchanged'] for r in cases),
  }
  result={'generated_utc':datetime.now(UTC).isoformat(),'counts':counts,'checks':checks,
    'failures':[k for k,v in checks.items() if not v],
    'original_result_hashes':{r['alias']:sha(WORK/f"{r['alias']}_first/results.json") for r in cases},
    'original_runner_fingerprints':{r['alias']:r['runner_sha256'] for r in cases},
    'current_runner_sha256':sha(WORK/'run.py'),
    'independent_parent_execution':{'path':independent_path.relative_to(ROOT).as_posix(),'sha256':sha(independent_path),
       'comparison':independent,'scope_ko':'부모가 지문 동일 복사본에서 별도 직접 실행한 a/b. 이 에이전트의 새 실행 건수에 합하지 않는다.'},
    'scope_ko':'기존 first 결과를 읽은 별도 최종 관측 정리. 새 전체 실행·전체 TX 정책 검증·실차 안전 증명으로 세지 않는다.',
    'unmeasured_scope_ko':['LKA/LTA의 request/torque 비작동 값을 별도 직접 집계하지 않았다.',
      '독립 TX 기대값 미정 21,135개는 실제 hook 반환·권한불변·DBC/정의 checksum 관측 범위다.',
      'a 최초 실행의 넓은 source12 전후 지문은 없으며 AST source5+공유C 지문을 확인했다. b/d 및 부모의 a/b 재실행은 source12 전후를 확인했다.',
      '1Hz phase0·storage_max만 통합 실행했다. input_max와 다른 위상은 현재 미실행이다.']}
  (FINAL/'frozen_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  paths=sorted(p for p in WORK.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='evidence_manifest.json')
  manifest={'generated_utc':datetime.now(UTC).isoformat(),'artifact_hashes':{p.relative_to(WORK).as_posix():sha(p) for p in paths}}
  (FINAL/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'checks':len(checks),'failures':result['failures'],'counts':counts,'artifacts':len(paths)},ensure_ascii=False))
  raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
