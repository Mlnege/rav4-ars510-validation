"""신호 판단을 고치지 않고 원형 호스트의 자연 입력/권한 전이를 비교한다."""
import argparse
from datetime import datetime, UTC
import hashlib
import json

from whole_io import WORK, SOURCE, Clock, clock_inputs, SOURCE_HASHES, source_unchanged
from whole_chain import Chain
from run_baseline import json_clean


def main():
  parser=argparse.ArgumentParser()
  parser.add_argument('kind',choices=['red','green','unknown','stale','obs_missing','bad_provenance','invalid_can',
    'cancel_restart','brake_restart','dm_soft','dm_hard','model_freeze','plan_freeze','session_green','gas','gas_one_tick'])
  parser.add_argument('--phase-ms',type=int,default=0,choices=[0,10,20,30,40])
  parser.add_argument('--order',choices=['before','after'],default='before')
  args=parser.parse_args()
  clock=Clock()
  with clock_inputs(clock):
    chain=Chain(clock)
    warm=chain.warm(signal_order=args.order).copy()
    assert warm['signal_start_hold'] and warm['signal_runtime_start']['context']['valid']
    assert warm['signal_runtime_start']['context']['enabled']
    start=clock.now+.01
    fault_start=len(chain.rows)
    duration=8. if args.kind=='dm_hard' else 4.
    gas_duration=.01 if args.kind=='gas_one_tick' else .5
    phase=args.phase_ms*.001
    dm_reenable_time=None
    for index in range(round(duration/.01)):
      clock.now=start+index*.01
      elapsed=index*.01
      kw={'signal_order':args.order}
      if args.kind=='green':kw['signal_color']='green'
      if args.kind=='unknown':kw['signal_color']='unknown'
      if args.kind=='stale':kw['signal_latency']=.8
      if args.kind=='obs_missing':kw['signal_publish']=False
      if args.kind=='bad_provenance':kw['signal_provenance']=False
      if args.kind=='invalid_can':kw['can_valid']=elapsed>=.4
      if args.kind=='session_green':kw.update(signal_color='green',signal_session='new_synthetic_session')
      if args.kind=='cancel_restart':kw.update(cancel=elapsed<.1,engaged=elapsed>=1.)
      if args.kind=='brake_restart':kw.update(brake=elapsed<.2,engaged=elapsed<.8 or elapsed>=1.2)
      if args.kind in ('gas','gas_one_tick'):kw['gas']=phase<=elapsed<phase+gas_duration-1e-9
      if args.kind=='dm_soft' and elapsed<.6:kw['freeze_services']=('driverMonitoringState',)
      if args.kind=='dm_hard':
        if elapsed<4.:kw['freeze_services']=('driverMonitoringState',)
        else:
          # 실제 건강 판정이 복구된 뒤 명시적 PCMoff/on만 입력한다. 상위 판단을 고정하지 않는다.
          if dm_reenable_time is None and chain.sd.sm.all_checks():dm_reenable_time=clock.now+.2
          kw['engaged']=dm_reenable_time is not None and clock.now>=dm_reenable_time
      if args.kind=='model_freeze':kw['freeze_model']=elapsed<.6
      if args.kind=='plan_freeze':kw['freeze_plan']=elapsed<.6
      chain.step(**kw)
    rows=chain.rows[fault_start:]
    calls=[r for r in chain.signal_trace.calls if r['time']>=start-1e-8]
    contexts=[r for r in calls if r['runtime']=='start']
    generated=[r for r in chain.physical.generated_rows if r['time_ns']>=round(start*1e9)]
    accel=[r for r in generated if r['address']==0x343]
    held=[r for r in rows if r['signal_start_hold']]
    released=[r for r in rows if r['signal_start_released'] and r['guard_decision_this_tick']]
    positives=[r for r in rows if r['accel']>1e-6 and r['longActive']]
    positive_can=[r for r in accel if r['raw_accel_signed']>0 and r['actual_tx']==1]
    published=chain.observations.published
    checks={'normal_original_baseline':warm['enabled'] and warm['longActive'] and warm['signal_start_hold'],
      'normal_initial_disabled':not any(chain.init_snapshot.values()),
      'mode2_without_retired_assist':chain.configuration['SignalAssistMode']=='2' and chain.carrot.signal_assist is None,
      'all_c_tx_expected':all(r['tx_matches_expected'] for r in chain.physical.generated_rows),
      'no_tx_authority_creation':all(r['tx_does_not_create_authority'] for r in chain.physical.generated_rows),
      'all_dbc_generated_messages_decode':all(r['dbc_parse_updated'] is not False for r in chain.physical.generated_rows),
      'all_defined_checksums_correct':all(r['toyota_checksum_ok'] is not False for r in chain.physical.generated_rows),
      'no_nonzero_without_c_long_authority':all(not(r['actual_tx']==1 and r['raw_accel_signed']!=0 and not r['c_longitudinal_before']) for r in accel),
      'source_unchanged':source_unchanged(),'no_physical_init':not chain.physical.actual_init_executed,
      'no_controls_true_shortcut':chain.permission.shortcut_controls_true_calls==0,
      'model_camera_source_recorded':all(r['input_model_eof']>0 and r['input_model_frame_id']>0 for r in calls)}
    if args.kind in ('red','unknown','stale','obs_missing','session_green'):
      checks['held_red_not_released_without_confirmed_same_anchor_green']=all(r['signal_start_hold'] for r in rows) and not released
      checks['held_plan_not_positive']=all(r['plan_aTarget']<=0 and r['plan_should_stop'] for r in held)
    if args.kind=='green':checks['same_anchor_green_releases_veto']=bool(released) and not rows[-1]['signal_start_hold']
    if args.kind=='bad_provenance':
      checks['prepare_rejects_missing_ox_transform']=all(not r['context']['valid'] for r in calls if r['runtime']=='prepare')
      checks['start_guard_is_distinct_from_geometry_gate']=all(r['signal_start_hold'] for r in rows)
    if args.kind=='invalid_can':
      checks['actual_context_invalid_seen']=any(not r['context']['valid'] and r['context']['enabled'] for r in contexts)
      active_invalid=[r for r in rows if r['guard_decision_this_tick'] and
        r['signal_runtime_start']['context']['enabled'] and not r['signal_runtime_start']['context']['valid']]
      checks['start_preserves_hold_during_active_invalid_context']=bool(active_invalid) and all(r['signal_start_hold'] for r in active_invalid)
      checks['original_can_error_disables_host']=not rows[0]['enabled'] and not rows[0]['longActive'] and 'canError' in rows[0]['events']
      checks['disabled_runtime_resets_hold']=any(r['guard_decision_this_tick'] and not r['signal_runtime_start']['context']['enabled'] and
        not r['signal_start_hold'] and r['signal_start_reason']=='disabled' for r in rows)
    if args.kind in ('gas','gas_one_tick'):
      checks['natural_host_gas_override_seen']=any(r['gas'] and r['enabled'] and not r['longActive'] for r in rows)
      checks['natural_gas_release_long_active']=any(not r['gas'] and r['longActive'] and r['time']>=start+phase+gas_duration for r in rows)
    if args.kind in ('cancel_restart','brake_restart'):
      checks['actual_driver_disables_host']=any(not r['enabled'] and not r['longActive'] for r in rows)
      checks['normal_pcm_enable_restart']=rows[-1]['enabled'] and rows[-1]['longActive']
    if args.kind=='dm_soft':checks['actual_soft_disabling_seen']=any(r['state']=='softDisabling' for r in rows)
    if args.kind=='dm_hard':
      checks['actual_soft_then_disabled_seen']=any(r['state']=='softDisabling' for r in rows) and any(r['state']=='disabled' for r in rows)
      checks['enabled_false_runtime_seen']=any(not r['context']['enabled'] for r in contexts)
    files=['openpilot/selfdrive/carrot/signal_mode.py','openpilot/selfdrive/carrot/signal_assist_runtime.py',
      'openpilot/selfdrive/carrot/signal_start_guard.py','openpilot/selfdrive/carrot/signal_stop_prepare_runtime.py',
      'openpilot/selfdrive/carrot/signal_stop_prepare.py','openpilot/selfdrive/carrot/carrot_functions.py',
      'openpilot/selfdrive/controls/lib/longitudinal_planner.py','opendbc_repo/opendbc/car/toyota/carcontroller.py',
      'opendbc_repo/opendbc/safety/safety.h','opendbc_repo/opendbc/safety/safety/safety_toyota.h',
      'openpilot/common/transformations/camera.py','openpilot/selfdrive/modeld/signal_tracking_shadow.py']
    hashes=dict(SOURCE_HASHES)
    hashes.update({name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in files})
    start_after_gas=[r for r in contexts if r['time']>=start+phase and r['input_cs_gas']]
    release_after_gas=[r for r in rows if r['time']>=start+phase+gas_duration and not r['gas']]
    restored_hold=next((r for r in release_after_gas if r['signal_start_hold']),None)
    reset_rows=[r for r in rows if not r['signal_start_hold']]
    result={'kind':args.kind,'phase_ms':args.phase_ms,'order':args.order,'gas_duration_s':gas_duration,
      'recorded_utc':datetime.now(UTC).isoformat(),'checks':checks,'failures':[name for name,passed in checks.items() if not passed],
      'initial':chain.init_snapshot,'configuration':chain.configuration,'normal_baseline':warm,
      'fault_start':start,'model_tick_origin':100.,'model_period_s':.05,
      'gas_requested_start':start+phase if args.kind.startswith('gas') else None,
      'gas_requested_release':start+phase+gas_duration if args.kind.startswith('gas') else None,
      'first_actual_gas_context':start_after_gas[0] if start_after_gas else None,
      'first_release_host':release_after_gas[0] if args.kind.startswith('gas') and release_after_gas else None,
      'first_hold_removed':reset_rows[0] if reset_rows else None,'first_hold_restored_after_gas':restored_hold if args.kind.startswith('gas') else None,
      'first_veto_release':released[0] if released else None,'first_positive_control':positives[0] if positives else None,
      'first_positive_allowed_can':positive_can[0] if positive_can else None,
      'positive_control_ticks':len(positives),'positive_allowed_can_count':len(positive_can),
      'actual_dm_reenable_time':dm_reenable_time,
      'first':rows[0],'last':rows[-1],'rows':rows,'runtime_calls':calls,'publications':published,
      'camera_history':chain.observations.road_history,
      'camera_lineage':{'publication_count':len(published),'exact_matches':sum(r['camera_history_exact_match'] for r in published),
        'startup_before_history':sum(r['camera_history_missing_kind']=='before_started_history' for r in published),
        'after_enable_missing':sum(not r['camera_history_exact_match'] for r in published if r['delivery_time']>=102.),
        'scope_ko':'발행된 합성 roadCameraState frameId와EOF 쌍 대조. 실제영상 lineage가 아님.'},
      'generated_can':generated,'can_count':len(generated),'can_accel_count':len(accel),
      'expected_deny_count':sum(r['expected_tx']==0 for r in generated),'actual_deny_count':sum(r['actual_tx']==0 for r in generated),
      'events':sorted({e for r in rows for e in r['events']}),'source_hashes':hashes,
      'actual_image_recognition':False,'actual_ci_update':False,'actual_ci_init':False,'actual_vehicle_tx':False,
      'actual_mcu_heartbeat':False,'actual_ars_live':False,'physical_motion_integrated':False,
      'scope_ko':'원형 host+mode2 runtime/guard/prepare+native MPC/LoC+Toyota생성CAN+실제C 메모리검사. 신호/영상규격/CS/stock/GVC/정지차량입력은합성. helper enabled/valid/CC를강제하지않음. 신호veto cooldown은10초정지명령이아니며driverintent/permission상실을분리. PCS/regen/인식정확도/실차미검증.'}
    folder=WORK/'cases'/f'{args.kind}_{args.phase_ms}ms_{args.order}'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'result.json').write_text(json.dumps(json_clean(result),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'kind':args.kind,'phase_ms':args.phase_ms,'order':args.order,'failures':result['failures'],
      'first_hold_removed':reset_rows[0]['time'] if reset_rows else None,
      'first_positive_control':positives[0]['time'] if positives else None,
      'positive_allowed_can':len(positive_can),'can_count':len(generated),'actual_denied':result['actual_deny_count'],
      'first_gas_runtime_enabled':start_after_gas[0]['context']['enabled'] if start_after_gas else None,
      'hold_restore_after_gas':restored_hold['time'] if args.kind.startswith('gas') and restored_hold else None},ensure_ascii=False))
    raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
