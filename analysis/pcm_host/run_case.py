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
    checks={'normal_initial_disabled':not any(chain.init_snapshot.values()),
      'normal_enable':warm['enabled'] and warm['longActive'],
      'mode0_actual_helper':all(r['helper_mode']==0 for r in chain.rows),
      'state_update_each_tick':chain.physical.update_io_calls==len(chain.rows),
      'normal_can_packets_no_invented_frames':all(r['can_packet_count']==1 and r['actual_can_frame_count']==0 for r in chain.rows),
      'no_actual_ci_init':not chain.physical.actual_init_executed,'source_unchanged':source_unchanged()}
    if args.kind=='speed_down':
      checks.update(pcm60_received=all(r['cs_vCruise']==60. for r in rows[:200]),
        pcm85_received=all(r['cs_vCruise']==85. for r in rows[200:]))
    if args.kind in ('map40','combined'):
      checks['lower_cap_used']=all(r['planner_cruise_kph']<=40. for r in rows[10:])
      checks['negative_accel_reaches_controls']=min(r['accel'] for r in rows)<-.5
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
    files=['openpilot/selfdrive/car/cruise.py','openpilot/selfdrive/car/toyota_pcm_speed.py',
      'openpilot/selfdrive/carrot/carrot_functions.py','openpilot/selfdrive/carrot/carrot_man_input.py',
      'openpilot/selfdrive/carrot/curve_speed.py','openpilot/selfdrive/controls/lib/longitudinal_planner.py',
      'openpilot/selfdrive/pandad/pandad_api_impl.py']
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
      'actual_card_state_update':True,'actual_ci_update':False,'actual_can_parser':False,
      'actual_c_permission_normal_rx':True,'shortcut_controls_true_calls':chain.permission.shortcut_controls_true_calls,
      'init_io_sink_calls':chain.physical.init_io_sink_calls,'actual_init_executed':False,'actual_vehicle_tx':False,
      'physical_ready_verified':False,'independent_mcu_heartbeat':False,'actual_carrotserv_network_route':False,
      'live_ars_and_signal_mode2_included':False,
      'scope_ko':'공장 CP를 쓰는 메모리 설정/합성 건강 입력의 원형 호스트 판정 연결. CAN capnp 변환만 실제이고 차량 파서는 미실행. 곡선 cap 계산은 원형이지만 모델/지도 제한 입력과 CarrotMan 발행 경계는 합성. 100Hz 가상 시간, 고정 ego54km/h이며 실제 제동 거리/장치 일정/회생/PCS의 보증이 아님.'}
    folder=WORK/'cases'/args.kind
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'kind':args.kind,'failures':result['failures'],'first_cs':rows[0]['cs_vCruise'],
      'last_cs':rows[-1]['cs_vCruise'],'last_plan':rows[-1]['planner_cruise_kph'],
      'min_control_accel':result['min_control_accel'],'events':result['events']},ensure_ascii=False))
    raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
