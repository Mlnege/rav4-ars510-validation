"""실제 로그의 서비스·건강·페달·시각 부족을 True로 채우지 않고 집계한다."""
from collections import Counter
from datetime import datetime,UTC
import json
import math

from whole_io import WORK
from log_io import inputs,events,recorded_schema


def main():
  parser,schema=recorded_schema()
  reports=[]
  for alias,path in inputs():
    counts,valids,cs,dm,pose,panda,camera,calib=Counter(),Counter(),Counter(),Counter(),Counter(),Counter(),Counter(),Counter()
    first=last=previous=None
    header_reversals=0
    model_ages=[]
    safety_can=Counter()
    previous_can=None
    can_header_reversals=0
    with events(path,schema.Event) as stream:
      for event in stream:
        kind=event.which()
        ns=int(event.logMonoTime)
        if first is None:first=ns
        if previous is not None and ns<previous:header_reversals+=1
        previous=last=ns
        counts[kind]+=1
        valids[kind]+=int(bool(event.valid))
        if kind=='can':
          if previous_can is not None and ns<previous_can:can_header_reversals+=1
          previous_can=ns
          for frame in event.can:
            if frame.src==0 and frame.address in (0xaa,0x260,0x226,0x1d2,0x2e4,0x343):
              safety_can[hex(frame.address)]+=1
        elif kind=='carState':
          value=event.carState
          for field in ('canValid','canTimeout','gasPressed','brakePressed','doorOpen','seatbeltUnlatched','standstill'):
            cs[field]+=int(bool(getattr(value,field)))
          cs['drive']+=int(str(value.gearShifter)=='drive')
          cs['pcm_available']+=int(value.cruiseState.available)
          cs['pcm_enabled']+=int(value.cruiseState.enabled)
          cs['pcm_speed_positive']+=int(value.cruiseState.speed>0)
        elif kind=='driverMonitoringState':
          value=event.driverMonitoringState
          dm['disabled']+=int(value.dm2Disabled)
          dm['lockout']+=int(value.lockout)
          dm['no_alert']+=int(str(value.alertLevel)=='none')
        elif kind=='livePose':
          value=event.livePose
          for field in ('inputsOK','sensorsOK','posenetOK'):pose[field]+=int(bool(getattr(value,field)))
          pose['orientation_valid']+=int(value.orientationNED.valid)
          pose['angular_valid']+=int(value.angularVelocityDevice.valid)
        elif kind=='pandaStates':
          for p in event.pandaStates:
            panda['entries']+=1
            panda['controls_allowed']+=int(p.controlsAllowed)
            panda['rx_invalid']+=int(p.safetyRxChecksInvalid)
            panda['fault_entries']+=len(p.faults)
        elif kind=='roadCameraState':camera[str(event.roadCameraState.sensor)]+=1
        elif kind=='liveCalibration':calib[str(event.liveCalibration.calStatus)]+=1
        elif kind=='modelV2':
          eof=int(event.modelV2.timestampEof)
          if eof>0:model_ages.append((ns-eof)*1e-9)
    report={'alias':alias,'event_counts':dict(counts),'valid_event_counts':dict(valids),
      'carState_true_counts':dict(cs),'dm_counts':dict(dm),'pose_true_counts':dict(pose),
      'panda_counts':dict(panda),'camera_sensor_counts':dict(camera),'calibration_state_counts':dict(calib),
      'header_storage_order_reversals':header_reversals,'duration_s':(last-first)*1e-9 if last is not None else None,
      'can_header_storage_order_reversals':can_header_reversals,'bus0_safety_message_counts':dict(safety_can),
      'model_header_minus_eof_range_s':[min(model_ages),max(model_ages)] if model_ages else [None,None],
      'scope_ko':'저장된실제서비스집계. 원본시각/ID/위치/FW/RawCAN은출력안함. event.valid가물리건강/collector시각을증명하지않음.'}
    reports.append(report)
    print(json.dumps({'alias':alias,'events':sum(counts.values()),'carState':counts['carState'],
      'canValid_true':cs['canValid'],'gas_true':cs['gasPressed'],'brake_true':cs['brakePressed'],
      'dm_disabled':dm['disabled'],'pose_inputsOK':pose['inputsOK'],'header_reversals':header_reversals},ensure_ascii=False),flush=True)
  (WORK/'input_profile.json').write_text(json.dumps({'recorded_utc':datetime.now(UTC).isoformat(),'files':reports},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


if __name__=='__main__':main()
