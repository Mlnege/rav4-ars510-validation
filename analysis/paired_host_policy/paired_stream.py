"""원본 epoch와 순서 보존 배치로 ARS·DPath를 실행하고 메모리 호스트 입력을 만든다."""
from collections import Counter
from dataclasses import dataclass

from whole_io import ROOT, car, log, Clock, clock_inputs, MemoryBus, memory_messaging
from log_io import events


HOST_INPUTS = {'carState','modelV2','livePose','liveCalibration','liveParameters','liveTorqueParameters',
  'deviceState','peripheralState','pandaStates','driverMonitoringState','managerState','roadCameraState',
  'driverCameraState','wideRoadCameraState','liveDelay','lateralPlan','driverAssistance','accelerometer','gyroscope',
  'gpsLocation','gpsLocationExternal','carrotMan','drivingModelData'}


@dataclass
class Delivery:
  receive_ns: int
  kind: str
  event: object = None
  frames: object = None


def wire_event(old):
  # 모든 nested NS를 원본 epoch로 유지하며 값/헤더를 fresh-now로 치환하지 않는다.
  with log.Event.from_bytes(old.as_builder().to_bytes()) as reader:
    return reader.as_builder()


def cp_copy(cp):
  with car.CarParams.from_bytes(cp.to_bytes()) as reader:
    value = reader.as_builder()
  cp.clear_write_flag()
  return value


def cp_view(cp):
  fields = ('carFingerprint','flags','openpilotLongitudinalControl','pcmCruise','radarUnavailable',
            'alternativeExperience','passive','notCar','secOcRequired','mass','wheelbase','centerToFront',
            'steerRatio','radarDelay','longitudinalActuatorDelay','enableDsu','enableBsm','minEnableSpeed','minSteerSpeed')
  result = {name: getattr(cp,name) for name in fields}
  result['safetyConfigs'] = [{'model':str(s.safetyModel),'raw':int(s.safetyModel.raw),'param':int(s.safetyParam)}
                           for s in cp.safetyConfigs]
  result['firmware_count'] = len(cp.carFw)
  return result


def read_dataset(path, schema, basis):
  from opendbc.car.toyota.ars510_offline import Ars510OfflineRadarInterface
  from openpilot.selfdrive.carrot.radar.can_batch import RadarCanBatches,RadarEgoSample
  from openpilot.selfdrive.carrot.radar_motion import DPathRadarController
  from openpilot.selfdrive.carrot.radar_motion.timing import front_radar_distance_delay_s
  from openpilot.selfdrive.carrot.radar.radard_dpath import DPathRadarD
  original_cp = None
  with events(path,schema.Event) as stream:
    for value in stream:
      if value.which()=='carParams':
        with car.CarParams.from_bytes(value.carParams.as_builder().to_bytes()) as reader:
          original_cp=reader.as_builder()
        break
  if original_cp is None:return None,{'status':'insufficient_carParams'},[],None
  cp_before = original_cp.to_bytes()
  original_cp.clear_write_flag()
  adapter = Ars510OfflineRadarInterface(cp_copy(original_cp),offline=True)
  radar = DPathRadarD(cp_copy(original_cp))
  radar.controller = DPathRadarController(enable_radar_tracks=1,production_live_tracks=True,
      front_radar_measurement_delay_s=front_radar_distance_delay_s(original_cp))
  buffer = RadarCanBatches()
  radar_bus = MemoryBus()
  messaging = memory_messaging(radar_bus)
  sm = messaging.SubMaster(['modelV2','carState','liveTracks','livePose'],poll='modelV2',
      ignore_alive=['livePose'],ignore_valid=['livePose'])
  clock = Clock()
  timeline=[]
  counts,batch_errors,radar_errors,accumulated=Counter(),Counter(),Counter(),Counter()
  origin=now_ns=None
  rr=car.RadarData.new_message()
  rr.errors.radarUnavailableTemporary=True
  have_state=have_tracks=needs_reset=False
  first_record_ns=None
  last_error_publish=0
  original_metadata_changes=0
  error_before_record=error_after_record=0
  with events(path,schema.Event) as stream,clock_inputs(clock):
    for old in stream:
      kind,header=old.which(),int(old.logMonoTime)
      if origin is None:origin=header
      if now_ns is None:now_ns=header
      if basis=='storage_max' or kind in ('can','carState'):
        now_ns=max(now_ns,header)
      clock.now=now_ns*1e-9
      value=wire_event(old) if kind in HOST_INPUTS else None
      if value is not None:
        timeline.append(Delivery(now_ns,kind,value))
        if kind in ('carState','modelV2','livePose'):radar_bus.emit(kind,value)
      if kind=='can':
        frames=[(int(f.address),bytes(f.dat),int(f.src)) for f in old.can]
        timeline.append(Delivery(now_ns,'can',frames=frames))
        buffer.add_can([(header,frames)])
        counts['can_events']+=1
        counts['all_can_items']+=len(frames)
      elif kind=='carState':
        before=old.carState.radarInput.to_dict()
        buffer.add_state(RadarEgoSample.from_car_state(old.carState))
        original_metadata_changes+=int(before!=old.carState.radarInput.to_dict())
        counts['source_cs']+=1
        have_state=True
      if kind in ('can','carState'):
        while (batch:=buffer.take(now_ns)) is not None:
          ego,packets,error=batch
          if error:
            batch_errors[error]+=1
            needs_reset=True
            if now_ns-last_error_publish>=50_000_000:
              rr=car.RadarData.new_message()
              rr.errors.canError=True
              last_error_publish=now_ns
              counts['batch_error_publications']+=1
            else:
              counts['batch_error_publications_throttled']+=1
              continue
          else:
            if needs_reset:
              accumulated.update({k:v for k,v in adapter.diagnostics.items() if k not in ('namespace_offset','active_points')})
              adapter=Ars510OfflineRadarInterface(cp_copy(original_cp),offline=True)
              needs_reset=False
              counts['adapter_restarts']+=1
            counts['accepted_batches']+=1
            counts['paired_can_packets']+=len(packets)
            counts['paired_can_frames']+=sum(len(frames) for _,frames in packets)
            result=adapter.update_carrot(ego.v_ego,ego.a_ego,ego.receive_ns*1e-9,packets)
            if result is None:continue
            rr=result
            counts['adapter_result_publications']+=1
            counts['points']+=len(rr.points)
            if first_record_ns is None and adapter.diagnostics['records']>0:first_record_ns=now_ns
          error_flags=rr.errors.to_dict()
          error_before_record+=int(any(error_flags.values()) and first_record_ns is None)
          error_after_record+=int(any(error_flags.values()) and first_record_ns is not None)
          radar_errors.update({k:int(v) for k,v in error_flags.items()})
          output=messaging.new_message('liveTracks',valid=not any(error_flags.values()),logMonoTime=now_ns)
          output.liveTracks=rr
          timeline.append(Delivery(now_ns,'liveTracks',output))
          radar_bus.emit('liveTracks',output)
          have_tracks=True
          counts['liveTracks_publications']+=1
      if kind=='modelV2' and have_state and have_tracks:
        sm.update(0)
        radar.update(sm,rr)
        output=messaging.new_message('radarState',valid=radar.radar_state_valid,logMonoTime=now_ns)
        output.radarState=radar.radar_state
        with log.Event.from_bytes(output.to_bytes()) as reader:output=reader.as_builder()
        timeline.append(Delivery(now_ns,'radarState',output))
        counts['dpath_models']+=1
        counts['dpath_lead_selections']+=sum(bool(l.status and l.radar) for l in (output.radarState.leadOne,output.radarState.leadTwo))
        counts['radarState_error_models']+=int(any(output.radarState.radarErrors.to_dict().values()))
  accumulated.update({k:v for k,v in adapter.diagnostics.items() if k not in ('namespace_offset','active_points')})
  metrics={'status':'paired_decoder_and_dpath','counts':dict(counts),'batch_errors':dict(batch_errors),
    'radar_error_counts':dict(radar_errors),'adapter_diagnostics':dict(accumulated),
    'error_publications_before_first_record':error_before_record,'error_publications_after_first_record':error_after_record,
    'first_record_relative_s':(first_record_ns-origin)*1e-9 if first_record_ns is not None else None,
    'original_cp_unchanged':cp_before==original_cp.to_bytes(),'original_batch_metadata_unchanged':original_metadata_changes==0,
    'pending_states_at_end':len(buffer.states),'unpaired_can_at_end':len(buffer.can),
    'full_radarcan_loop_executed':False,'clock_basis':basis,
    'scope_ko':'원본 epoch·저장순서의 batch gate/adapter/DPath. 소켓/main 전체 inputTimeout/실제 처리 deadline은 미실행. 새 발행 헤더는 명시한 가정 clock이며 원본 입력 헤더/NS는 그대로.'}
  original_cp.clear_write_flag()
  return original_cp,metrics,timeline,origin
