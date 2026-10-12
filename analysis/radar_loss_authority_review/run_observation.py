"""정상 PCM 활성화 뒤 빈 lead/오류/producer 중단을 원형 호스트에서 분리한다."""
import sys
sys.dont_write_bytecode=True
from collections import Counter
import contextlib
from datetime import datetime,UTC
import hashlib
import io
import json
import os
from pathlib import Path
import traceback

from whole_io import ROOT,WORK,SOURCE,LAB,Clock,clock_inputs,source_unchanged
from whole_chain import Chain
sys.path.insert(0,str(LAB/'work/safety_validation'))
from verify_compiled import quiet_c_stdout


CASES=[('healthy_empty',None,True,False),('can_error','canError',False,False),
 ('temporary','radarUnavailableTemporary',False,False),('producer_stopped',None,True,True)]


@contextlib.contextmanager
def hide_stderr():
  saved=os.dup(2)
  with open(os.devnull,'wb') as sink:
    os.dup2(sink.fileno(),2)
    try:yield
    finally:
      os.dup2(saved,2)
      os.close(saved)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def one_case(kind,error,valid,freeze):
  clock=Clock()
  with clock_inputs(clock):
    chain=Chain(clock)
    chain.observe_mpc_inputs()
    warm=chain.warm().copy()
    assert chain.cp.radarUnavailable,'원형Unavailable 전제 변경'
    start=clock.now+.01
    begin=len(chain.rows)
    can_begin=len(chain.physical.generated_rows)
    for index in range(400):
      clock.now=start+index*.01
      chain.step(freeze_radar=freeze,radar_valid=valid,radar_error=error)
    rows=chain.rows[begin:]
    cans=chain.physical.generated_rows[can_begin:]
    accel=[r for r in cans if r['address']==0x343]
    states=Counter(r['state'] for r in rows)
    transitions=[]
    previous=None
    for index,r in enumerate(rows):
      marker=(r['state'],r['enabled'],r['active'],r['longActive'],r['controls_force_decel'],
              r['radar_valid'],r['radar_alive'],r['radar_frequency_ok'])
      if marker!=previous:
        transitions.append({'relative_s':index*.01,'state':r['state'],'enabled':r['enabled'],'active':r['active'],
          'longActive':r['longActive'],'forceDecel':r['controls_force_decel'],
          'soft_disable_timer':r['soft_disable_timer'],'radar_valid':r['radar_valid'],
          'radar_alive':r['radar_alive'],'radar_frequency_ok':r['radar_frequency_ok'],
          'events':r['events'],'control_accel':r['accel'],'plan_aTarget':r['plan_aTarget'],
          'card_previous_cc_active':r['card_latest_longActive'],'c_controlsAllowed':r['c_controlsAllowed']})
        previous=marker
    checks={'normal_enable_from_false':not any(chain.init_snapshot.values()) and warm['enabled'] and warm['longActive'],
      'cp_unavailable_remains_true':bool(chain.cp.radarUnavailable),
      'empty_leads_no_invented_objects':all(not r['leadOne_status'] and not r['leadTwo_status'] for r in rows),
      'no_controls_true_shortcut':chain.permission.shortcut_controls_true_calls==0,
      'no_physical_initialization':not chain.physical.actual_init_executed,
      'source_ast_unchanged':source_unchanged(),
      'actual_native_solver_status_zero':all(r['native_solver_status']==0 for r in rows),
      'tx_does_not_create_permission':all(r['tx_does_not_create_authority'] for r in cans),
      'defined_accel_tx_expectations_match':all(r['tx_matches_expected'] is not False for r in cans),
      'dbc_defined_checksums_valid':all(r['toyota_checksum_ok'] is not False for r in cans)}
    summary={'kind':kind,'checks':checks,'failures':[k for k,v in checks.items() if not v],
      'initial':chain.init_snapshot,'warm_enabled':warm['enabled'],'warm_longActive':warm['longActive'],
      'cp':{'radarUnavailable':bool(chain.cp.radarUnavailable),'directLong':bool(chain.cp.openpilotLongitudinalControl),
        'flags':int(chain.cp.flags),'safetyParam':int(chain.cp.safetyConfigs[0].safetyParam),
        'alternativeExperience':int(chain.cp.alternativeExperience)},
      'state_counts':dict(states),'transitions':transitions,'final':rows[-1],
      'first':rows[0],'second':rows[1],
      'first_not_longActive_s':next((i*.01 for i,r in enumerate(rows) if not r['longActive']),None),
      'first_softDisabling_s':next((i*.01 for i,r in enumerate(rows) if r['state']=='softDisabling'),None),
      'positive_accel_ticks':sum(r['accel']>1e-6 for r in rows),'negative_accel_ticks':sum(r['accel']<-1e-6 for r in rows),
      'force_decel_ticks':sum(r['controls_force_decel'] for r in rows),
      'control_accel_range':[min(r['accel'] for r in rows),max(r['accel'] for r in rows)],
      'can_count':len(cans),'accel_can_count':len(accel),'actual_c_accept':sum(r['actual_tx']==1 for r in cans),
      'actual_c_deny':sum(r['actual_tx']==0 for r in cans),'defined_tx_count':sum(r['expected_tx'] is not None for r in cans),
      'undefined_tx_count':sum(r['expected_tx'] is None for r in cans),
      'positive_accel_can':sum(r['raw_accel_signed']>0 for r in accel),
      'negative_accel_can':sum(r['raw_accel_signed']<0 for r in accel),
      'zero_accel_can':sum(r['raw_accel_signed']==0 for r in accel),
      'c_controls_true_ticks':sum(r['c_controlsAllowed'] for r in rows),
      'mpc_force_zero_input_count':sum(r['mpc_observed_inputs']['forceDecel_at_planner'] and r['mpc_observed_inputs']['input_v_cruise_ms']==0 for r in rows),
      'mpc_force_input_zero_effective_positive_count':sum(r['mpc_observed_inputs']['forceDecel_at_planner'] and r['mpc_observed_inputs']['input_v_cruise_ms']==0 and r['mpc_observed_inputs'].get('effective_v_cruise_ms',0)>0 for r in rows),
      'force_decel_stop_command_propagation_failed':any(r['mpc_observed_inputs']['forceDecel_at_planner'] and r['mpc_observed_inputs']['input_v_cruise_ms']==0 and r['mpc_observed_inputs'].get('effective_v_cruise_ms',0)>0 for r in rows),
      'trace_count':chain.mpc_trace_count,
      'contract_inconsistent_input':kind=='error_with_valid_true',
      'scope_ko':'합성 건강 빈 lead와 정상PCM ON. 실제 radar point/물리 장면은 만들지 않음. 메모리 Toyota CAN/C TX와 고정ego15m/s이며 차량 운동/실물MCU/PCS/회생은 미검증.'}
    return summary,rows


def main():
  folder=WORK/'run02_observation'
  if (folder/'results.json').exists():raise RuntimeError('기존 결과를 덮지 않습니다')
  folder.mkdir(parents=True,exist_ok=True)
  protected=['openpilot/selfdrive/selfdrived/selfdrived.py','openpilot/selfdrive/selfdrived/state.py',
    'openpilot/selfdrive/selfdrived/events.py','openpilot/selfdrive/controls/controlsd.py',
    'openpilot/selfdrive/controls/lib/longitudinal_planner.py',
    'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py',
    'openpilot/selfdrive/carrot/radar/radard_dpath.py','opendbc_repo/opendbc/car/toyota/carcontroller.py']
  before={p:sha(SOURCE/p) for p in protected}
  library=LAB/'work/safety_validation/libsafety_download_native.so'
  library_before=sha(library)
  results=[]
  errors=[]
  with quiet_c_stdout(),hide_stderr(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    for kind,error,valid,freeze in CASES:
      try:
        summary,rows=one_case(kind,error,valid,freeze)
        results.append(summary)
        (folder/(kind+'_rows.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
      except Exception as problem:
        errors.append({'kind':kind,'type':type(problem).__name__,
          'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(problem.__traceback__)]})
        break
  after={p:sha(SOURCE/p) for p in protected}
  report={'generated_utc':datetime.now(UTC).isoformat(),'cases':results,'preparation_errors':errors,
    'source_before':before,'source_after':after,'source_unchanged':before==after,
    'library_sha256_before':library_before,'library_sha256_after':sha(library),'library_unchanged':library_before==sha(library),
    'script_sha256':sha(Path(__file__)),'checks_executed':sum(len(r['checks']) for r in results),
    'failures':[{'kind':r['kind'],'failed':r['failures']} for r in results if r['failures']],
    'actual_ci_update':False,'actual_ci_apply':True,'actual_vehicle_tx':False,
    'init_tests_calls':0,'operating_params_modified':False,
    'scope_ko':'원본 로그 OFF 관측과 별도인 합성 ON 계약 검사. 핵심 source 판단을 바꾸지 않고 메모리 radarState 공급만 다르게 했다. 실제 레이더 point/ARSdecoder/DPath 입력손실·실차를 검증하지 않는다.'}
  (folder/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'cases':len(results),'checks':report['checks_executed'],'errors':errors,'failures':report['failures'],
    'states':{r['kind']:r['state_counts'] for r in results}},ensure_ascii=False))
  raise SystemExit(1 if errors or report['failures'] or not report['source_unchanged'] or not report['library_unchanged'] else 0)


if __name__=='__main__':main()
