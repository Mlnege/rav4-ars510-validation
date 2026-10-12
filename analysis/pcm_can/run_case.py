"""같은 원형 연결에서 속도/제한/운전자 입력을 독립 과정으로 비교한다."""
import argparse
from datetime import datetime, UTC
import hashlib
import json

from whole_io import WORK, SOURCE, Clock, clock_inputs, SOURCE_HASHES, source_unchanged
from whole_chain import Chain


def main():
  parser=argparse.ArgumentParser()
  parser.add_argument('kind',choices=['speed_down','map40','curve','combined','invalid_cap','stale_cap',
    'cancel_restart','button_cancel_restart','gas_restart','brake_restart','main_off_restart'])
  args=parser.parse_args()
  clock=Clock()
  with clock_inputs(clock):
    chain=Chain(clock)
    warm=chain.warm().copy()
    # 원형 frame을 고치지 않고 건강한 실제 틱을 더 돌려33.33Hz 메시지 경계를 관측한다.
    while chain.physical.actual.CC.frame % 3:
      clock.now+=.01
      chain.step()
    warm=chain.rows[-1].copy()
    start=clock.now+.01
    change_start=len(chain.rows)
    for index in range(500):
      clock.now=start+index*.01
      elapsed=index*.01
      kw={}
      if args.kind=='speed_down': kw.update(pcm_kph=60. if elapsed<2. else 85.)
      if args.kind=='map40': kw.update(map_cap_kph=40.)
      if args.kind=='curve': kw.update(curve_yaw=.3 if elapsed<2. else 0.)
      if args.kind=='combined': kw.update(map_cap_kph=40.,curve_yaw=.3)
      if args.kind=='invalid_cap': kw.update(map_cap_kph=0.)
      if args.kind=='stale_cap': kw.update(map_cap_kph=40.,freeze_navigation=elapsed>=.5)
      if args.kind=='cancel_restart': kw.update(engaged=elapsed>=1.,cancel=elapsed<.05,pcm_kph=80.)
      if args.kind=='button_cancel_restart':
        kw.update(engaged=(elapsed<.8 or elapsed>=1.2),cancel=elapsed<.05,pcm_kph=80.)
      if args.kind=='gas_restart':
        kw.update(gas=elapsed<.2,engaged=(elapsed<.8 or elapsed>=1.2),pcm_kph=80.)
      if args.kind=='brake_restart':
        kw.update(brake=elapsed<.2,engaged=(elapsed<.8 or elapsed>=1.2),pcm_kph=80.)
      if args.kind=='main_off_restart':
        kw.update(available=elapsed>=.5,engaged=elapsed>=1.,pcm_kph=80.)
      chain.step(**kw)
    rows=chain.rows[change_start:]
    generated=chain.physical.generated_rows
    accel_rows=[r for r in generated if r['address']==0x343]
    fault_generated=[r for r in generated if r['time_ns']>=round(start*1e9)]
    fault_accel=[r for r in fault_generated if r['address']==0x343]
    addresses=sorted({r['address'] for r in generated})
    checks={'normal_initial_disabled':not any(chain.init_snapshot.values()),
      'normal_enable':warm['enabled'] and warm['longActive'],
      'mode0_actual_helper':all(r['helper_mode']==0 for r in chain.rows),
      'state_update_each_tick':chain.physical.update_io_calls==len(chain.rows),
      'normal_can_packets_no_invented_frames':all(r['can_packet_count']==1 and r['actual_can_frame_count']==0 for r in chain.rows),
      'no_actual_ci_init':not chain.physical.actual_init_executed,'source_unchanged':source_unchanged()}
    checks.update(actual_ci_apply_has_generated_can=chain.physical.actual_ci_apply_calls>0 and bool(generated),
      all_actual_c_tx_matches_expected=all(r['tx_matches_expected'] for r in generated),
      tx_never_creates_authority=all(r['tx_does_not_create_authority'] for r in generated),
      all_dbc_messages_decoded=all(r['dbc_parse_updated'] for r in generated if r['dbc_parse_updated'] is not None),
      all_dbc_sizes_match=all(r['dbc_size_ok'] for r in generated if r['dbc_size_ok'] is not None),
      all_toyota_checksums_match=all(r['toyota_checksum_ok'] for r in generated if r['toyota_checksum_ok'] is not None),
      no_protocol_signals_created=all(r['address'] in (0x343,0x2e4,0x191,0x412,0x411,0x750) for r in generated),
      tester_present_exact=all(r['tester_present_exact'] for r in generated if r['address']==0x750),
      dbc_accel_matches_independent_signed=all(abs(r['decoded_signals']['ACCEL_CMD']-r['raw_accel_signed']*.001)<1e-9 for r in accel_rows),
      accel_generation_exact_3_frames=all(b['controller_frame']-a['controller_frame']==3 for a,b in zip(accel_rows,accel_rows[1:])),
      accel_generation_exact_30ms=all(b['time_ns']-a['time_ns']==30_000_000 for a,b in zip(accel_rows,accel_rows[1:])),
      lka_every_frame=all(b['controller_frame']-a['controller_frame']==1 for a,b in zip([r for r in generated if r['address']==0x2e4],[r for r in generated if r['address']==0x2e4][1:])),
      lta_every_2_frames=all(b['controller_frame']-a['controller_frame']==2 for a,b in zip([r for r in generated if r['address']==0x191],[r for r in generated if r['address']==0x191][1:])),
      generated_accel_stays_c_range=all(-3500<=r['raw_accel_signed']<=2000 for r in accel_rows),
      no_nonzero_accel_allowed_without_long_authority=all(not(r['actual_tx']==1 and r['raw_accel_signed']!=0 and not r['c_longitudinal_before']) for r in accel_rows),
      no_controls_true_shortcut=chain.permission.shortcut_controls_true_calls==0)
    if args.kind=='speed_down':
      checks.update(pcm60_received=all(r['cs_vCruise']==60. for r in rows[:200]),
        pcm85_received=all(r['cs_vCruise']==85. for r in rows[200:]))
    if args.kind in ('map40','combined'):
      checks['lower_cap_used']=all(r['planner_cruise_kph']<=40. for r in rows[10:])
      checks['negative_accel_reaches_controls']=min(r['accel'] for r in rows)<-.5
      checks['negative_accel_generated_and_c_allowed']=any(r['raw_accel_signed']<0 and r['actual_tx']==1 for r in fault_accel)
    if args.kind in ('curve','combined'):
      checks['original_curve_has_constraint']=any(r['curve_cap_kph'] is not None and r['curve_cap_kph']<40. for r in rows)
      checks['curve_cap_used']=all(r['planner_cruise_kph']<=r['navigation_emitted_kph'] for r in rows[10:200])
    if args.kind=='curve':checks['fresh_straight_releases_cap']=rows[-1]['planner_cruise_kph']>rows[190]['planner_cruise_kph']
    if args.kind=='invalid_cap':checks['zero_cap_ignored']=all(r['planner_cruise_kph']>=75. for r in rows)
    if args.kind=='stale_cap':checks.update(cap_used_initial=rows[40]['planner_cruise_kph']<=40.,
      cap_expires_after_1s=rows[-1]['navigation_age']>1. and rows[-1]['planner_cruise_kph']>=75.)
    if args.kind in ('cancel_restart','button_cancel_restart','gas_restart','brake_restart','main_off_restart'):
      checks.update(driver_condition_stops_long=not rows[0]['longActive'],
        card_next_queue_inactive=not rows[1]['card_latest_longActive'],
        normal_pcm_restart=rows[-1]['enabled'] and rows[-1]['longActive'],
        restart_speed80=rows[-1]['cs_vCruise']==80.)
      checks['inactive_zero_can_follows']=any(r['raw_accel_signed']==0 and not r['cc_longActive'] and r['actual_tx']==1 for r in fault_accel[:15])
      if args.kind!='button_cancel_restart':
        checks['previous_active_can_blocked_on_driver_condition']=fault_accel[0]['raw_accel_signed']!=0 and fault_accel[0]['actual_tx']==0
      else:
        checks['button_only_does_not_fabricate_c_pcm_cancel']=fault_accel[0]['c_controls_before'] and fault_accel[0]['actual_tx']==1
      if args.kind=='gas_restart':
        checks['gas_alt1_controls_and_long_authority_separate']=fault_accel[0]['c_controls_before'] and not fault_accel[0]['c_longitudinal_before']
    files=['openpilot/selfdrive/car/cruise.py','openpilot/selfdrive/car/toyota_pcm_speed.py',
      'openpilot/selfdrive/carrot/carrot_functions.py','openpilot/selfdrive/carrot/carrot_man_input.py',
      'openpilot/selfdrive/carrot/curve_speed.py','openpilot/selfdrive/controls/lib/longitudinal_planner.py',
      'openpilot/selfdrive/pandad/pandad_api_impl.py','opendbc_repo/opendbc/car/toyota/carcontroller.py',
      'opendbc_repo/opendbc/car/toyota/toyotacan.py','opendbc_repo/opendbc/car/interfaces.py',
      'opendbc_repo/opendbc/can/packer.py','opendbc_repo/opendbc/can/parser.py',
      'opendbc_repo/opendbc/safety/safety.h','opendbc_repo/opendbc/safety/safety/safety_toyota.h']
    hashes=dict(SOURCE_HASHES)
    hashes.update({name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in files})
    result={'kind':args.kind,'recorded_utc':datetime.now(UTC).isoformat(),'checks':checks,
      'failures':[name for name,passed in checks.items() if not passed],'initial':chain.init_snapshot,
      'configuration':chain.configuration,'cp':{'fingerprint':str(chain.cp.carFingerprint),'flags':int(chain.cp.flags),
        'pcmCruise':bool(chain.cp.pcmCruise),'directLong':bool(chain.cp.openpilotLongitudinalControl),
        'radarUnavailable':bool(chain.cp.radarUnavailable),'alternativeExperience':int(chain.cp.alternativeExperience),
        'alpha_get_params_argument':True,'longitudinalActuatorDelay':float(chain.cp.longitudinalActuatorDelay)},
      'warm':warm,'first':rows[0],'second':rows[1],'last':rows[-1],
      'midpoint':rows[200],'min_control_accel':min(r['accel'] for r in rows),'rows':rows,
      'events':sorted({e for r in rows for e in r['events']}),'source_hashes':hashes,
      'generated_can_rows':generated,'fault_first_accel_can':fault_accel[0],'addresses':addresses,
      'can_tx_counts':{'generated':len(generated),'accepted':sum(r['actual_tx']==1 for r in generated),
        'blocked':sum(r['actual_tx']==0 for r in generated),'expected_blocked':sum(r['expected_tx']==0 for r in generated),
        'accel':len(accel_rows),'fault_accel':len(fault_accel)},
      'actual_ci_apply':True,'actual_toyota_carcontroller':True,'actual_canpacker':True,'actual_c_tx_memory':True,
      'actual_card_state_update':True,'actual_ci_update':False,'actual_can_parser':False,
      'actual_c_permission_normal_rx':True,'shortcut_controls_true_calls':chain.permission.shortcut_controls_true_calls,
      'init_io_sink_calls':chain.physical.init_io_sink_calls,'actual_init_executed':False,'actual_vehicle_tx':False,
      'physical_ready_verified':False,'independent_mcu_heartbeat':False,'actual_carrotserv_network_route':False,
      'live_ars_and_signal_mode2_included':False,
      'feedback_assumptions':{'ego_mps':15.,'aEgo_mps2':0.,'gvc_mps2':0.,'stock_follow_distance':3,
        'stock_lkas_hud':'actual constructor empty value','pcm_acc_status':'8 if enabled else0, fixture assumption'},
      'scope_ko':'공장 CP와 메모리 설정/합성 건강 입력의 원형 호스트 판정→실제 CI.apply/ToyotaCC/CANPacker→같은 실제 C 메모리 TX. 수신 차량 파서는 미실행. 곡선 계산은 원형, 모델/지도/CarrotMan 발행은 합성. 가상100Hz·고정ego54km/h/aEgo0/GVC0이며 실제 제동/장치일정/회생/PCS 보증이 아님.'}
    folder=WORK/'cases'/args.kind
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'kind':args.kind,'failures':result['failures'],'first_cs':rows[0]['cs_vCruise'],
      'last_cs':rows[-1]['cs_vCruise'],'last_plan':rows[-1]['planner_cruise_kph'],
      'min_control_accel':result['min_control_accel'],'events':result['events'],'can_tx_counts':result['can_tx_counts']},ensure_ascii=False))
    raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
