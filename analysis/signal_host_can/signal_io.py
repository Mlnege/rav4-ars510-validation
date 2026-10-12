"""원형 신호 파일 입출력만 메모리로 옮기고 실제 Runtime 반환을 관찰한다."""
import ast
import io
from pathlib import Path
from types import SimpleNamespace
import time

from whole_io import SOURCE, load_definitions


native_namespace={'Path':Path,'io':io}
load_definitions('tools/ars510_validation/signal/native_signal.py',native_namespace,{'MemoryObservationPath'})
NativeMemoryPath=native_namespace['MemoryObservationPath']


class MemorySignalPath(NativeMemoryPath):
  def read_text(self, *args, **kwargs):
    if self.name not in self.storage:
      raise FileNotFoundError(self.name)
    return self.storage[self.name].decode('utf-8')

  def __fspath__(self):
    return self.name


def observation_path_io(value):
  if isinstance(value,NativeMemoryPath):return value
  value=Path(value)
  if str(value).startswith('/dev/shm/carrot_signal') or value.name=='revalidated_enabled':
    return MemorySignalPath(str(value))
  return value


def install_io():
  # actual flag_override와 requested는 그대로다. 선택 관측과 미사용 leaf flag 파일만 메모리다.
  from openpilot.selfdrive.carrot import signal_assist_runtime, signal_start_guard, signal_stop_prepare_runtime
  for module in (signal_assist_runtime,signal_start_guard,signal_stop_prepare_runtime):
    module.Path=observation_path_io
  MemorySignalPath.storage.clear()


namespace={}
load_definitions('tools/ars510_validation/signal/core.py',namespace,{'observation_record'})
observation_record=namespace['observation_record']
trajectory_tree=ast.parse((SOURCE/'tools/ars510_validation/signal/native_signal.py').read_text())
trajectory_class=next(n for n in trajectory_tree.body if isinstance(n,ast.ClassDef) and n.name=='NativeSignalHarness')
trajectory_method=next(n for n in trajectory_class.body if isinstance(n,ast.FunctionDef) and n.name=='model_trajectory')


def model_trajectory(model,cs,speed):
  from openpilot.selfdrive.modeld.constants import ModelConstants
  original_namespace={'ModelConstants':ModelConstants}
  exec(compile(ast.Module(body=[trajectory_method],type_ignores=[]),'<원형 합성 trajectory helper>','exec'),original_namespace)
  original_namespace['model_trajectory'](SimpleNamespace(sm={'modelV2':model,'carState':cs}),speed,None)


class ObservationProducer:
  def __init__(self,messaging):
    self.metadata=messaging.SubMaster(['deviceState','roadCameraState'])
    self.published=[]
    self.last=None
    self.road_history=[]

  def publish(self,now,*,color='red',latency=.1,session='synthetic_whole_signal',provenance=True):
    from openpilot.selfdrive.modeld.signal_tracking_shadow import tracking_camera_profile
    from openpilot.selfdrive.carrot.signal_start_guard import publish_start_observation
    from openpilot.selfdrive.carrot.signal_stop_prepare_runtime import publish_prepare_observation
    self.metadata.update(0)
    acquisition=now-latency
    record=observation_record(acquisition,round(acquisition*20),color,session=session)
    profile=tracking_camera_profile(SimpleNamespace(width=1928,height=1208),self.metadata,now)
    if provenance and profile is not None:
      record['source_size']=profile['source_size']
      record['coordinate_transform']=profile['coordinate_transform']
    publish_start_observation(record)
    publish_prepare_observation(record)
    value={'delivery_time':now,'acquisition_time':acquisition,'frame_id':record['frame_id'],
      'session':session,'color':color,'profile':profile,'provenance_supplied':provenance and profile is not None,
      'metadata':{key:{'seen':self.metadata.seen[key],'alive':self.metadata.alive[key],
        'valid':self.metadata.valid[key],'receive_time':self.metadata.recv_time[key],
        'header':self.metadata.logMonoTime[key]} for key in ('deviceState','roadCameraState')}}
    acquired_ns=record['timestamp_eof']
    match=next((item for item in reversed(self.road_history) if item['frame_id']==record['frame_id']
                and item['timestamp_eof']==acquired_ns),None)
    before_history=bool(self.road_history and acquired_ns<self.road_history[0]['timestamp_eof'])
    value.update(camera_history_exact_match=match is not None,camera_history_match=match,
      camera_history_missing_kind='before_started_history' if match is None and before_history else
        'no_exact_published_camera_frame' if match is None else None,
      camera_history_scope='합성 메모리 roadCameraState 발행 기록. 실제 영상/센서 lineage 증명은 아님.')
    self.published.append(value)
    self.last=value
    return value


class RuntimeObservation:
  def __init__(self):
    self.latest={}
    self.calls=[]

  def attach(self,runtime,label):
    original=runtime.read
    def observed_read(sm,now=None):
      # 실제 원형 반환을 그대로 돌려준다. context나 observation의 값을 바꾸지 않는다.
      observation,context=original(sm,now)
      current=context['now']
      value={'runtime':label,'time':current,'runtime_config_enabled':runtime.enabled,
        'runtime_enabled_since':runtime.enabled_since,
        'context':{k:v for k,v in context.items() if not callable(v)},
        'observation_timestamp':observation.get('timestamp') if observation is not None else None,
        'observation_frame_id':observation.get('frame_id') if observation is not None else None,
        'observation_session':observation.get('session') if observation is not None else None,
        'observation_age':current-observation['timestamp'] if observation is not None else None,
        'input_sd_enabled':bool(sm['selfdriveState'].enabled),
        'input_cc_enabled':bool(sm['carControl'].enabled),'input_cc_longActive':bool(sm['carControl'].longActive),
        'input_cs_gas':bool(sm['carState'].gasPressed),'input_cs_brake':bool(sm['carState'].brakePressed),
        'input_cs_speed':float(sm['carState'].vEgo),'input_model_eof':int(sm['modelV2'].timestampEof),
        'input_model_frame_id':int(sm['modelV2'].frameId),'input_model_header':int(sm.logMonoTime['modelV2']),
        'input_model_receive_time':sm.recv_time['modelV2'],
        'input_pose_timestamp':int(sm['livePose'].timestamp),'input_pose_header':int(sm.logMonoTime['livePose']),
        'input_pose_receive_time':sm.recv_time['livePose'],
        'health':{key:{'seen':sm.seen[key],'valid':sm.valid[key],'alive':sm.alive[key],
          'receive_time':sm.recv_time[key],'header':sm.logMonoTime[key]} for key in
          ('carState','modelV2','radarState','selfdriveState','carControl','livePose')}}
      if label=='prepare' and runtime.extra is not None:
        value['extra_health']={key:{'seen':runtime.extra.seen[key],'valid':runtime.extra.valid[key],
          'alive':runtime.extra.alive[key],'receive_time':runtime.extra.recv_time[key],
          'header':runtime.extra.logMonoTime[key]} for key in ('deviceState','roadCameraState','liveCalibration')}
      self.latest[label]=value
      self.calls.append(value)
      return observation,context
    runtime.read=observed_read
