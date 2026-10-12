"""실제 로그와 ARS 결과를 원형 호스트에 전달한다. 원본 제어 OFF/조건을 보존한다."""
import argparse
from collections import Counter
import ctypes
from datetime import datetime,UTC
import hashlib
import json
import math
import os

from whole_io import WORK,SOURCE,LAB,MemoryBus,memory_messaging,MemoryConfiguration,Clock,clock_inputs
from whole_io import SOURCE_HASHES,source_unchanged
from offline_io import repo_defaults
from log_io import inputs,recorded_schema
from actual_stream import read_dataset


class RecordedCsBus(MemoryBus):
  """원형 Card 출력과 원본 CS 배달 메타를 분리하는 재생 입출력."""
  def __init__(self):
    super().__init__()
    self.cs_source=None
    self.cs_version=0
    self.cs_delivered_version=-1
    self.cs_publish_attempts=0
    self.cs_deliveries=0
    self.cs_duplicate_attempts=0

  def emit(self,service,value):
    if service=='carState':
      self.cs_publish_attempts+=1
      if self.cs_source is None or self.cs_version==self.cs_delivered_version:
        self.cs_duplicate_attempts+=1
        return
      if isinstance(value,bytes):
        from whole_io import log
        with log.Event.from_bytes(value) as source:value=source.as_builder()
      value.logMonoTime=self.cs_source['header_ns']
      value.valid=self.cs_source['valid']
      self.cs_delivered_version=self.cs_version
      self.cs_deliveries+=1
    return super().emit(service,value)


SENSOR_FIELDS=('canValid','canTimeout','vEgo','vEgoRaw','vEgoCluster','aEgo','gasPressed','brakePressed',
  'doorOpen','seatbeltUnlatched','gearShifter','standstill','steeringAngleDeg','steeringTorque','steeringTorqueEps')


def main():
  ap=argparse.ArgumentParser()
  ap.add_argument('alias',choices=['log_a','log_b','log_c','log_d'])
  args=ap.parse_args()
  os.chdir(SOURCE)
  MemoryConfiguration.values=repo_defaults()
  MemoryConfiguration.bytes_values={}
  MemoryConfiguration.values.update(SpeedFromPCM='0',LongActuatorDelay='20',AlphaLongitudinalEnabled='1',NNFF='0')
  schema_parser,schema=recorded_schema()
  source_path=dict(inputs())[args.alias]
  module=memory_messaging(MemoryBus())
  recorded_cp,radar_metrics,timeline=read_dataset(source_path,schema.Event,module)
  folder=WORK/'files'/args.alias
  folder.mkdir(parents=True,exist_ok=True)
  if recorded_cp is None:
    result={'alias':args.alias,'status':'insufficient_recorded_carParams','radar':radar_metrics,
      'whole_host_executed':False,'scope_ko':'원본CP/차량상태/모델자료가없어도구가추측으로채우지않음.'}
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return
  clock=Clock()
  bus=RecordedCsBus()
  messaging=memory_messaging(bus)
  from whole_objects import initialise
  from whole_inputs import VehiclePermissionInput
  from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
  from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
  with clock_inputs(clock):
    cp,sd,controls,card,interface=initialise(messaging)
    initial={'sd_initialized':sd.initialized,'sd_enabled':sd.enabled,'sd_active':sd.active,
      'card_initialized_prev':card.initialized_prev}
    permission=VehiclePermissionInput(cp)
    interface.tx_permission=permission
    permission.probe.lib.get_relay_malfunction.restype=ctypes.c_bool
    planner_sm=messaging.SubMaster(['carControl','carState','controlsState','liveParameters','radarState',
      'liveTracks','modelV2','selfdriveState','carrotMan','livePose'],poll='modelV2',ignore_avg_freq=['radarState'])
    planner_pm=messaging.PubMaster(['longitudinalPlan'])
    planner=LongitudinalPlanner(cp)
    carrot=CarrotPlanner()
    counts=Counter()
    event_counts=Counter()
    invalid=Counter()
    no_alive=Counter()
    no_freq=Counter()
    last_cs=None
    sensor_copy_mismatches=0
    source_cs_ages=[]
    index=0
    raw_rx=0
    rstate_latest=None
    error_periods=[]
    state_last=None
    states={value:key for key,value in controls.state_control.__globals__['State'].schema.enumerants.items()}
    # 원형 초기화 조건과 상태 판단을 실행하고, 100Hz 수신 시각만 명시적 가정으로 만든다.
    end=max(item.receive_s for item in timeline)
    for tick in range(math.ceil((end-100.)/.01)+1):
      clock.now=100.+tick*.01
      permission.probe.lib.set_timer(round(clock.now*1e6))
      while index<len(timeline) and timeline[index].receive_s<=clock.now+1e-8:
        item=timeline[index];index+=1
        if item.kind=='can':
          raw_rx+=len(item.frames)
          for address,data,src in item.frames:
            # 실제 순정 메시지/PCM을 삭제하지 않고 C 수신/릴레이 감지도 실행한다.
            permission.probe.packet('rx',address,data,src)
          interface.receive_feedback(round(item.receive_s*1e9),item.frames)
          empty=messaging.new_message('can',0,valid=True,logMonoTime=round(clock.now*1e9))
          bus.emit('can',empty)
        elif item.kind=='carState':
          # 실제 문/벨트/기어/페달/PCM을 보존하고 VCruise 출력만 원형 코드가 갱신한다.
          last_cs=item.event.carState.as_reader()
          bus.cs_version+=1
          bus.cs_source={'header_ns':int(item.event.logMonoTime),'valid':bool(item.event.valid),
            'delivery_time':item.receive_s}
        else:
          bus.emit(item.kind,item.event)
          if item.kind=='radarState':rstate_latest=item.event
      permission.probe.lib.safety_tick_current_safety_config()
      if last_cs is None:continue
      # 마지막 CS 유지는 명시한 표본 유지 I/O이며, 로그 입력을 정상 True로 치환하지 않는다.
      interface.next_state=last_cs.as_builder()
      card.step()
      sensor_copy_mismatches+=int(any(getattr(card.CS_prev,name)!=getattr(last_cs,name) for name in SENSOR_FIELDS))
      source_cs_ages.append(clock.now-bus.cs_source['header_ns']*1e-9)
      card.rk.monitor_time()
      if planner_sm.sock['modelV2'].queue:
        planner_sm.update(0)
        planner.update(planner_sm,carrot)
        planner.publish(planner_sm,planner_pm,carrot)
        counts['native_model_updates']+=1
        counts['models_with_radar_lead']+=int(planner_sm['radarState'].leadOne.status and planner_sm['radarState'].leadOne.radar)
        counts['models_with_radar_lead_two']+=int(planner_sm['radarState'].leadTwo.status and planner_sm['radarState'].leadTwo.radar)
        counts['mpc_lead_source']+=int(str(planner.mpc.source) in ('lead0','lead1'))
        counts['solver_nonzero']+=int(planner.mpc.solution_status!=0)
      sd.step()
      sd.rk.monitor_time()
      controls.update()
      cc,lac=controls.state_control()
      controls.publish(cc,lac)
      counts['host_ticks']+=1
      counts['host_initialized']+=int(sd.initialized)
      counts['host_enabled']+=int(sd.enabled)
      counts['long_active']+=int(cc.longActive)
      counts['c_controls_allowed']+=int(permission.allowed())
      counts['c_long_allowed']+=int(permission.probe.lib.get_longitudinal_allowed())
      counts['c_relay_malfunction']+=int(permission.probe.lib.get_relay_malfunction())
      for value in sd.events.names:
        name=next((k for k,v in controls.state_control.__globals__['log'].OnroadEvent.EventName.schema.enumerants.items() if v==int(value)),str(int(value)))
        event_counts[name]+=1
      for name,value in sd.sm.valid.items():
        if not value:invalid[name]+=1
      for name,value in sd.sm.alive.items():
        if not value:no_alive[name]+=1
      for name,value in sd.sm.freq_ok.items():
        if not value:no_freq[name]+=1
      state=(states[int(sd.state_machine.state)],bool(cc.longActive),
        bool(rstate_latest and any(rstate_latest.radarState.radarErrors.to_dict().values())))
      if state!=state_last:
        error_periods.append({'relative_time_s':tick*.01,'host_state':state[0],'longActive':state[1],
          'radar_error':state[2],'c_relay':bool(permission.probe.lib.get_relay_malfunction())})
        state_last=state
    generated=interface.generated_rows
    accel=[r for r in generated if r['address']==0x343]
    checks={'original_initial_disabled':not any(initial.values()),'recorded_cp_unchanged':radar_metrics['original_cp_unchanged'],
      'all_timeline_delivered':index==len(timeline),'sensor_fields_preserved':sensor_copy_mismatches==0,
      'synthetic_permission_update_not_called':permission.received==0,
      'no_source_changes':source_unchanged(),'no_actual_init':not interface.actual_init_executed,
      'no_controls_true_shortcut':permission.shortcut_controls_true_calls==0,
      'no_tx_authority_creation':all(r['tx_does_not_create_authority'] for r in generated),
      'defined_c_expectations_match':all(r['tx_matches_expected'] is not False for r in generated),
      'all_dbc_decoded':all(r['dbc_parse_updated'] is not False for r in generated),
      'all_defined_checksum_valid':all(r['toyota_checksum_ok'] is not False for r in generated)}
    result={'alias':args.alias,'recorded_utc':datetime.now(UTC).isoformat(),'status':'actual_data_host_observed',
      'radar':radar_metrics,'initial':initial,'counts':dict(counts),'host_event_counts':dict(event_counts),
      'host_health_invalid_counts':dict(invalid),'host_health_no_alive_counts':dict(no_alive),
      'host_health_no_frequency_counts':dict(no_freq),'state_error_transitions':error_periods,
      'can_count':len(generated),'accel_can_count':len(accel),'actual_c_deny_count':sum(r['actual_tx']==0 for r in generated),
      'actual_c_accept_count':sum(r['actual_tx']==1 for r in generated),
      'actual_c_defined_expectation_count':sum(r['expected_tx'] is not None for r in generated),
      'actual_c_mismatch_count':sum(r['tx_matches_expected'] is False for r in generated),
      'can_nonzero_accel_count':sum(r['raw_accel_signed']!=0 for r in accel),
      'raw_receive_frame_count':raw_rx,'final_initialized':bool(sd.initialized),'final_enabled':bool(sd.enabled),
      'timeline_entries':len(timeline),'timeline_delivered':index,'timeline_remaining':len(timeline)-index,
      'sensor_preservation_mismatches':sensor_copy_mismatches,
      'carState_publish_attempts':bus.cs_publish_attempts,'carState_recorded_meta_deliveries':bus.cs_deliveries,
      'carState_duplicate_body_deliveries_suppressed':bus.cs_duplicate_attempts,
      'carState_source_header_age_range_s':[min(source_cs_ages),max(source_cs_ages)] if source_cs_ages else [None,None],
      'carState_metadata_io':'원형 Card.state_publish 실행. 하위 배달은 원본 CS 새 표본일 때만 수행하고 원본 header/valid를 보존하는 재생 I/O. 생성 100Hz header를 실제 CS 신선도로 주장하지 않는다.',
      'feedback_missing_sample_counts':dict(interface.feedback_missing),
      'feedback_scope':'기존 DBC로 실제 CAN의 GVC/PCM status/follow/HUD를 해독한다. 미수신은 생성자 기본값/미확인으로 집계하며 정상 True로 바꾸지 않는다. CI.update 전체는 미실행.',
      'checks':checks,'failures':[name for name,passed in checks.items() if not passed],
      'source_hashes':SOURCE_HASHES,'cp_assumption':{'factory_manual_rav4_2022':True,'alpha_get_params_argument':True,
        'directLong':bool(cp.openpilotLongitudinalControl),'radarUnavailable':bool(cp.radarUnavailable),
        'pcm_conditions':'원본의 available/enable/설정속도 OFF를 보존. 이번 baseline에는 합성 ON이 없음.'},
      'collector_clock_assumption':'저장순서 유지. 수신은 이전까지의 최대 header를 100Hz 격자에 배달하는 가정. 실제 collector 수신시각은 없음. decoder는 원본 CAN header와 순서를 보존.',
      'ci_update_actual':False,'ci_apply_actual':True,'actual_ci_init':False,'actual_vehicle_tx':False,
      'actual_gvc_assumed':0.,'actual_ars_live':False,'physical_response_confirmed':False,
      'scope_ko':'원본 CS/model/pose/필수 서비스와 실제 ARS→원형 DPath→host→native MPC→Toyota CAN/C 메모리. factoryCP만 선언하며 PCM/운전자/순정 CAN의 실제 OFF/값을 보존한다. 차단/부족을 True로 바꾸지 않고 원본 rlog/ID/위치/절대시각/FW를 공개 저장하지 않는다.'}
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'alias':args.alias,'failures':result['failures'],'points':radar_metrics['points'],
      'lead_selections':radar_metrics['radar_leads'],'host_ticks':counts['host_ticks'],'host_enabled':counts['host_enabled'],
      'models_with_radar_lead':counts['models_with_radar_lead'],'mpc_lead_source':counts['mpc_lead_source'],
      'generated_can':len(generated),'c_deny':result['actual_c_deny_count'],'c_relay_ticks':counts['c_relay_malfunction']},ensure_ascii=False))
    raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
