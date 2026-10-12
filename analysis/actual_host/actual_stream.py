"""실제 저장순서로 ARS/원형 DPath를 실행하고 결과를 메모리 호스트 입력으로 연결한다."""
from collections import Counter
from dataclasses import dataclass
import hashlib
import math

from whole_io import SOURCE,car,log
from log_io import events


HOST_INPUTS={'carState','modelV2','livePose','liveCalibration','liveParameters','liveTorqueParameters',
  'deviceState','peripheralState','pandaStates','driverMonitoringState','managerState','roadCameraState',
  'driverCameraState','wideRoadCameraState','liveDelay','lateralPlan','driverAssistance','accelerometer','gyroscope',
  'gpsLocation','gpsLocationExternal','carrotMan','drivingModelData'}


def current_event(old,origin):
  # 기록 스키마와 최신 cereal의 동일 wire layout를 메모리 변환한다. 원본은 수정하지 않는다.
  with log.Event.from_bytes(old.as_builder().to_bytes()) as decoded:
    value=decoded.as_builder()
  kind=value.which()
  value.logMonoTime=int(value.logMonoTime)-origin+100_000_000_000
  body=getattr(value,kind)
  for name in ('timestampEof','timestampSof','timestamp'):
    if hasattr(body,'schema') and name in body.schema.fields:
      stamp=int(getattr(body,name))
      if stamp>0:setattr(body,name,stamp-origin+100_000_000_000)
  return value


@dataclass
class Delivery:
  receive_s:float
  kind:str
  event:object|None=None
  frames:list|None=None


def read_dataset(path,event_schema,messaging):
  from opendbc.car.toyota.ars510_offline import Ars510OfflineRadarInterface
  from openpilot.selfdrive.carrot.radar_motion import DPathRadarController
  from openpilot.selfdrive.carrot.radar_motion.coordinates import device_yaw_to_radar
  from openpilot.selfdrive.carrot.radar_motion.timing import front_radar_distance_delay_s
  from openpilot.selfdrive.carrot.radar.radard_dpath import DPathRadarD
  original_cp=None
  with events(path,event_schema) as stream:
    for event in stream:
      if event.which()=='carParams':
        with car.CarParams.from_bytes(event.carParams.as_builder().to_bytes()) as old:
          original_cp=old.as_builder()
        break
  if original_cp is None:return None,{'status':'insufficient_carParams','points':0,'records':0},[]
  cp_before=original_cp.to_bytes()
  original_cp.clear_write_flag()
  adapter=Ars510OfflineRadarInterface(original_cp,offline=True)
  # 별도 수신검증 instance만 mode1이다. 실제 CP/Params/차량 RadarInterface에는 등록하지 않는다.
  radar_core=DPathRadarD(original_cp)
  radar_core.controller=DPathRadarController(enable_radar_tracks=1,production_live_tracks=True,
    front_radar_measurement_delay_s=front_radar_distance_delay_s(original_cp))
  class RecordedReadState:
    # all_checks는 아래 실제 source SubMaster의 값으로 전달한다. 자체 True 판정을 만들지 않는다.
    def __init__(self,actual):self.actual=actual
    def __getitem__(self,key):return self.actual[key]
    @property
    def logMonoTime(self):return self.actual.logMonoTime
    def all_checks(self):return self.actual.all_checks()
  # 호스트와 다른 원형 SubMaster에 동일 저장순서 이벤트를 공급한다.
  from whole_io import MemoryBus,memory_messaging,Clock,clock_inputs
  radar_bus=MemoryBus()
  radar_messaging=memory_messaging(radar_bus)
  sm=radar_messaging.SubMaster(['modelV2','carState','liveTracks','livePose'],poll='modelV2',
    ignore_alive=['livePose'],ignore_valid=['livePose'])
  clock=Clock()
  counts=Counter()
  timeline=[]
  latest_v=latest_a=yaw=0.
  have_state=False
  rr=car.RadarData.new_message()
  rr.errors.radarUnavailableTemporary=True
  tracks_time=None
  origin=None
  delivery_ns=None
  first_record=None
  error_last=True
  error_transitions=[]
  b4_deltas=[]
  from opendbc.car.toyota.ars510.interface import parse_toyota_speed_mps
  with clock_inputs(clock),events(path,event_schema) as stream:
    for old_event in stream:
      kind=old_event.which()
      ns=int(old_event.logMonoTime)
      if origin is None:origin=ns
      delivery_ns=ns if delivery_ns is None else max(delivery_ns,ns)
      clock.now=100.+(delivery_ns-origin)*1e-9
      if kind=='carState':
        latest_v,latest_a=float(old_event.carState.vEgo),float(old_event.carState.aEgo)
        have_state=True
      elif kind=='livePose':
        angular=old_event.livePose.angularVelocityDevice
        yaw=device_yaw_to_radar(float(angular.z)) if angular.valid and old_event.livePose.inputsOK and old_event.livePose.sensorsOK else 0.
      if kind in HOST_INPUTS:
        value=current_event(old_event,origin)
        timeline.append(Delivery(clock.now,kind,value))
        if kind in ('carState','modelV2','livePose'):
          radar_bus.emit(kind,value)
      if kind=='can':
        frames=[(int(f.address),bytes(f.dat),int(f.src)) for f in old_event.can]
        timeline.append(Delivery(clock.now,'can',frames=frames))
        for address,data,bus in frames:
          if bus==0 and address==0xb4:
            b4=parse_toyota_speed_mps(data)
            if b4 is not None and have_state:b4_deltas.append(b4-latest_v)
        # 기존 replay와동일한원본 CAN header/최신원본CS시각으로decoder를실행한다.
        result=adapter.update_carrot(latest_v,latest_a,ns*1e-9,[(ns,frames)])
        if result is not None:
          rr=result
          tracks_time=ns*1e-9
          counts['liveTracks']+=1
          counts['points']+=len(rr.points)
          error=any(rr.errors.to_dict().values())
          counts['error_liveTracks']+=int(error)
          if first_record is None and adapter.diagnostics['records']>0:first_record=(ns-origin)*1e-9
          if error!=error_last:
            error_transitions.append({'relative_time_s':(ns-origin)*1e-9,'error':error})
            error_last=error
          output=messaging.new_message('liveTracks',valid=not error,logMonoTime=ns-origin+100_000_000_000)
          output.liveTracks=rr
          timeline.append(Delivery(clock.now,'liveTracks',output))
          radar_bus.emit('liveTracks',output)
      elif kind=='modelV2' and have_state and tracks_time is not None:
        sm.update(0)
        # 원형 DPath.update 본문을 그대로 실행한다. points/model/pose와각EOF는동일offset만정규화했다.
        radar_core.update(sm,rr)
        output=messaging.new_message('radarState',valid=radar_core.radar_state_valid,
          logMonoTime=round(clock.now*1e9))
        output.radarState=radar_core.radar_state
        counts['models']+=1
        counts['radar_leads']+=sum(bool(lead.status and lead.radar) for lead in (output.radarState.leadOne,output.radarState.leadTwo))
        counts['rstate_errors']+=int(any(output.radarState.radarErrors.to_dict().values()))
        counts['rstate_valid']+=int(output.valid)
        # wire직렬화해서호스트가같은스키마입력을읽는다. actualtrackID/좌표는보고서에덤프하지않는다.
        with log.Event.from_bytes(output.to_bytes()) as checked: output=checked.as_builder()
        timeline.append(Delivery(clock.now,'radarState',output))
  after=original_cp.to_bytes()
  original_cp.clear_write_flag()
  metrics={'status':'decoded','points':counts['points'],'records':adapter.diagnostics['records'],
    'crc_failures':adapter.diagnostics['crc_failures'],'radar_leads':counts['radar_leads'],
    'model_updates':counts['models'],'liveTracks_publications':counts['liveTracks'],
    'liveTracks_error_publications':counts['error_liveTracks'],'radarState_errors':counts['rstate_errors'],
    'radarState_valid_publications':counts['rstate_valid'],
    'first_completed_record_relative_s':first_record,'error_transitions':error_transitions,
    'original_cp_unchanged':cp_before==after,'original_radarUnavailable':bool(original_cp.radarUnavailable),
    'record_time_basis':'decoder는원본CAN발행header. host/dPath시각은단일offset정규화,수신clock은저장순서max header가정.',
    'b4_vs_latest_cs_samples':len(b4_deltas),
    'b4_vs_latest_cs_delta_range_mps':[min(b4_deltas),max(b4_deltas)] if b4_deltas else [None,None],
    'diagnostics':adapter.diagnostics}
  return original_cp,metrics,timeline
