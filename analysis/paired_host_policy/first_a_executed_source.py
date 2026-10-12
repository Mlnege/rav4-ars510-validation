"""원본 batch·CP·Panda 정책을 원형 호스트와 실제 CAN/C에 오프라인 연결한다."""
import sys
sys.dont_write_bytecode=True
import argparse
from collections import Counter
import contextlib
from datetime import datetime,UTC
import hashlib
import io
import json
import math
from pathlib import Path
import traceback

from whole_io import WORK,ROOT,SOURCE,LAB,Clock,clock_inputs,MemoryBus,memory_messaging,MemoryConfiguration,source_unchanged
from log_io import inputs,recorded_schema
from paired_stream import read_dataset,cp_copy,cp_view
from policy_io import RecordedPolicy,module as policy_module
from offline_io import repo_defaults


SENSOR_FIELDS=('canValid','canTimeout','vEgo','vEgoRaw','vEgoCluster','aEgo','gasPressed','brakePressed',
  'doorOpen','seatbeltUnlatched','gearShifter','standstill','steeringAngleDeg','steeringTorque','steeringTorqueEps')
BATCH_FIELDS=('firstCanMonoTime','lastCanMonoTime','canPacketCount','receiveMonoTime')


class RecordedCsBus(MemoryBus):
  def __init__(self):
    super().__init__()
    self.cs_source=None
    self.version=0
    self.delivered=-1
    self.counts=Counter()

  def emit(self,service,value):
    if service=='carState':
      self.counts['cs_publish_attempts']+=1
      if self.cs_source is None or self.version==self.delivered:
        self.counts['duplicate_cs_delivery_suppressed']+=1
        return
      if isinstance(value,bytes):
        from whole_io import log
        with log.Event.from_bytes(value) as reader:value=reader.as_builder()
      value.logMonoTime=int(self.cs_source.logMonoTime)
      value.valid=bool(self.cs_source.valid)
      self.delivered=self.version
      self.counts['source_header_valid_deliveries']+=1
    return super().emit(service,value)


def execute(alias,basis,phase,folder):
  import os
  os.chdir(SOURCE)
  MemoryConfiguration.values=repo_defaults()
  MemoryConfiguration.bytes_values={}
  MemoryConfiguration.values.update(SpeedFromPCM='0',LongActuatorDelay='20',AlphaLongitudinalEnabled='1',NNFF='0')
  schema_parser,schema=recorded_schema()
  original_cp,radar_metrics,timeline,origin=read_dataset(dict(inputs())[alias],schema,basis)
  if original_cp is None:return {'alias':alias,'status':'insufficient_carParams','whole_host_executed':False}
  bus=RecordedCsBus()
  messaging=memory_messaging(bus)
  clock=Clock()
  clock.now=origin*1e-9
  from whole_objects import initialise
  from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
  from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
  host_cp=cp_copy(original_cp)
  cp_before=cp_view(host_cp)
  counts,events,health_invalid,health_dead,health_frequency=Counter(),Counter(),Counter(),Counter(),Counter()
  last_cs=None
  index=0
  age=[]
  with clock_inputs(clock):
    cp,sd,controls,card,interface=initialise(messaging,host_cp)
    cp_after=cp_view(cp)
    policy=RecordedPolicy(origin,phase)
    interface.tx_permission=policy
    initial={'sd_initialized':bool(sd.initialized),'sd_enabled':bool(sd.enabled),'sd_active':bool(sd.active),
             'card_initialized_prev':bool(card.initialized_prev),'c_state':policy.clock.state()}
    sm=messaging.SubMaster(['carControl','carState','controlsState','liveParameters','radarState',
      'liveTracks','modelV2','selfdriveState','carrotMan','livePose'],poll='modelV2',ignore_avg_freq=['radarState'])
    pm=messaging.PubMaster(['longitudinalPlan'])
    planner=LongitudinalPlanner(cp)
    carrot=CarrotPlanner()
    event_names=controls.state_control.__globals__['log'].OnroadEvent.EventName.schema.enumerants
    end=max(item.receive_ns for item in timeline)
    for tick in range(math.ceil((end-origin)/10_000_000)+1):
      now_ns=origin+tick*10_000_000
      clock.now=now_ns*1e-9
      policy.advance(now_ns)
      while index<len(timeline) and timeline[index].receive_ns<=now_ns:
        item=timeline[index];index+=1
        if item.kind=='can':
          policy.receive_can(item.frames)
          interface.receive_feedback(item.receive_ns,item.frames)
          # 물리 수집을 실행하지 않는 빈 CAN 입출력. batch용 원본은 위 준비 단계에서 별도 보존한다.
          empty=messaging.new_message('can',0,valid=True,logMonoTime=now_ns)
          bus.emit('can',empty)
        elif item.kind=='carState':
          last_cs=item.event.carState.as_reader()
          bus.cs_source=item.event
          bus.version+=1
        else:
          if item.kind=='pandaStates':policy.receive_panda(item.event,now_ns)
          bus.emit(item.kind,item.event)
      if last_cs is None:continue
      original_batch={name:int(getattr(last_cs.radarInput,name)) for name in BATCH_FIELDS}
      interface.next_state=last_cs.as_builder()
      card.step()
      counts['checked_sensor_mismatches']+=int(any(getattr(last_cs,k)!=getattr(card.CS_prev,k) for k in SENSOR_FIELDS))
      counts['original_pcm_body_mismatches']+=int(any(getattr(last_cs.cruiseState,k)!=getattr(card.CS_prev.cruiseState,k)
                                                    for k in ('available','enabled','speed','speedCluster')))
      counts['original_batch_body_mutations']+=int(original_batch!={name:int(getattr(last_cs.radarInput,name)) for name in BATCH_FIELDS})
      counts['card_batch_copy_changed_ticks']+=int(original_batch!={name:int(getattr(card.CS_prev.radarInput,name)) for name in BATCH_FIELDS})
      age.append((now_ns-int(bus.cs_source.logMonoTime))/1e6)
      card.rk.monitor_time()
      if sm.sock['modelV2'].queue:
        sm.update(0)
        planner.update(sm,carrot)
        planner.publish(sm,pm,carrot)
        counts['native_mpc_models']+=1
        counts['radar_lead_consumed_models']+=int(sm['radarState'].leadOne.status and sm['radarState'].leadOne.radar)
        counts['radar_lead_with_valid_state']+=int(sm['radarState'].leadOne.status and sm['radarState'].leadOne.radar and sm.valid['radarState'])
        counts['mpc_lead_source_models']+=int(str(planner.mpc.source) in ('lead0','lead1'))
        counts['mpc_solver_nonzero']+=int(planner.mpc.solution_status!=0)
      sd.step()
      sd.rk.monitor_time()
      controls.update()
      cc,lac=controls.state_control()
      controls.publish(cc,lac)
      state=policy.clock.state()
      counts['host_ticks']+=1
      counts['host_initialized']+=bool(sd.initialized)
      counts['host_enabled']+=bool(sd.enabled)
      counts['host_active']+=bool(sd.active)
      counts['longActive']+=bool(cc.longActive)
      for key in ('controls','long','relay','rx_invalid'):counts['c_'+key+'_true_ticks']+=state[key]
      for value in sd.events.names:
        name=next((key for key,num in event_names.items() if num==int(value)),str(int(value)))
        events[name]+=1
      for service,value in sd.sm.valid.items():health_invalid[service]+=int(not value)
      for service,value in sd.sm.alive.items():health_dead[service]+=int(not value)
      for service,value in sd.sm.freq_ok.items():health_frequency[service]+=int(not value)
    generated=interface.generated_rows
    by_tx=Counter()
    for row in generated:
      by_tx[f"mode{row['c_mode']}/param{row['c_param']}/{row['message']}/tx{row['actual_tx']}"]+=1
    checks={'initial_host_disabled':not any(initial[k] for k in ('sd_initialized','sd_enabled','sd_active','card_initialized_prev')),
      'all_timeline_consumed':index==len(timeline),'original_cp_decoder_unchanged':radar_metrics['original_cp_unchanged'],
      'source_batch_metadata_unmodified':radar_metrics['original_batch_metadata_unchanged'] and counts['original_batch_body_mutations']==0,
      'checked_sensor_fields_preserved':counts['checked_sensor_mismatches']==0,
      'original_pcm_body_preserved':counts['original_pcm_body_mismatches']==0,
      'c_packet_categories_sum':sum(policy.counts[k] for k in ('physical_rx','returned_notifications','rejected_notifications','unknown_src'))==policy.counts['all_can_items'],
      'all_original_can_items_consumed':policy.counts['all_can_items']==radar_metrics['counts']['all_can_items'],
      'unknown_can_source_absent':policy.counts['unknown_src']==0,
      'physical_rx_all_valid':policy.counts['physical_rx_return_1']==policy.counts['physical_rx'],
      'tx_does_not_create_permission':all(r['tx_does_not_create_authority'] for r in generated),
      'defined_c_expectations_match':all(r['tx_matches_expected'] is not False for r in generated),
      'dbc_decoding_valid':all(r['dbc_parse_updated'] is not False for r in generated),
      'defined_can_checksums_valid':all(r['toyota_checksum_ok'] is not False for r in generated),
      'no_physical_init':not interface.actual_init_executed,'ast_loaded_sources_unchanged':source_unchanged(),
      'native_solver_status_zero':counts['mpc_solver_nonzero']==0,
      'recorded_direct_stock_cp_retained':cp_before['openpilotLongitudinalControl']==cp_after['openpilotLongitudinalControl']
          and cp_before['safetyConfigs']==cp_after['safetyConfigs'] and cp_before['radarUnavailable']==cp_after['radarUnavailable']}
    return {'alias':alias,'status':'paired_original_cp_host_can_observed','clock_basis':basis,'phase_us':phase,
      'initial':initial,'cp_before_constructor':cp_before,'cp_after_constructor':cp_after,
      'cp_changed_fields':[key for key in cp_before if cp_before[key]!=cp_after[key]],
      'radar':radar_metrics,'counts':dict(counts),'policy':policy.summary(),
      'host_event_counts':dict(events),'invalid_counts':dict(health_invalid),'no_alive_counts':dict(health_dead),
      'no_frequency_counts':dict(health_frequency),'timeline_count':len(timeline),'timeline_consumed':index,
      'carState_delivery':dict(bus.counts),'source_cs_header_age_ms_range':[min(age),max(age)],
      'can_count':len(generated),'can_by_policy_message_tx':dict(by_tx),
      'defined_tx_expectations':sum(r['expected_tx'] is not None for r in generated),
      'undefined_tx_expectations':sum(r['expected_tx'] is None for r in generated),
      'nonzero_accel_requests':sum(r['address']==0x343 and r['raw_accel_signed']!=0 for r in generated),
      'c_tx_accept_count':sum(r['actual_tx']==1 for r in generated),'c_tx_deny_count':sum(r['actual_tx']==0 for r in generated),
      'feedback_missing_counts':dict(interface.feedback_missing),'feedback_default_scope':dict(interface.feedback_default_scope),
      'actual_ci_apply_calls':interface.actual_ci_apply_calls,'init_io_sink_calls':interface.init_io_sink_calls,
      'checks':checks,'failures':[key for key,passed in checks.items() if not passed],
      'actual_ci_update':False,'physical_ci_init':False,'physical_tx':False,
      'epoch_scope_ko':'원본 모든 NS를 보존. BOOTTIME/MONOTONIC 숫자의 공통축은 재생 가정이며 장치 동등성 증명이 아님.',
      'card_scope_ko':'batch용 원본 CS는 분리 보존. Card용 복사본의 radarInput/UI 변경을 집계하며 그 새 메타를 원본 batch로 쓰지 않는다.',
      'scope_ko':'오프라인 원본 batch→ARS/DPath→원형 비활성 호스트/nativeMPC→Toyota 생성CAN/기록 정책의 동일C 상태. 실물 펌웨어·차량·PCS·회생·ARS live는 미검증.'}


def main():
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--alias',choices=['log_a','log_b','log_c','log_d'],required=True)
  parser.add_argument('--clock-basis',choices=['storage_max','input_max'],default='storage_max')
  parser.add_argument('--phase-us',type=int,choices=[0,500000],default=0)
  parser.add_argument('--output-dir',type=Path,required=True)
  args=parser.parse_args()
  if (args.output_dir/'results.json').exists():raise RuntimeError('새 출력 폴더가 필요합니다')
  args.output_dir.mkdir(parents=True,exist_ok=True)
  library=LAB/'work/safety_validation/libsafety_download_native.so'
  before=hashlib.sha256(library.read_bytes()).hexdigest()
  try:
    with policy_module.quiet_c_stdout(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
      result=execute(args.alias,args.clock_basis,args.phase_us,args.output_dir)
  except Exception as error:
    result={'alias':args.alias,'status':'preparation_or_execution_error','error_type':type(error).__name__,
      'source_frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)],
      'scope_ko':'원본이 포함될 수 있는 오류 메시지/값은 저장하지 않는다. 준비 실패를 전체 성공으로 보고하지 않는다.'}
  result['generated_utc']=datetime.now(UTC).isoformat()
  result['library_sha256_before']=before
  result['library_sha256_after']=hashlib.sha256(library.read_bytes()).hexdigest()
  result['library_unchanged']=before==result['library_sha256_after']
  result['runner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  (args.output_dir/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
  print(json.dumps({'alias':args.alias,'status':result['status'],'counts':result.get('counts'),
                    'failures':result.get('failures'),'error_type':result.get('error_type')},ensure_ascii=False))
  raise SystemExit(1 if result['status']=='preparation_or_execution_error' or result.get('failures') or not result['library_unchanged'] else 0)


if __name__=='__main__':main()
