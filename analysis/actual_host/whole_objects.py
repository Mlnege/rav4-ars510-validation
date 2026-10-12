"""원형 클래스 전체를 로드하고 판정과 무관한 물리 입출력만 격리한다."""
from collections import deque,Counter
import math
import json
from numbers import Number
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import numpy as np

from whole_io import SOURCE, LAB, MemoryConfiguration, load_definitions, PhysicalInterfaceSink, AbsentFaultFile
from whole_io import car, log
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_CTRL, DT_MDL, Ratekeeper
from openpilot.common.realtime import Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.common.pid import MultiplicativeUnwindPID
from openpilot.common.impact_dashcam import ImpactDashcam
from openpilot.common.runtime_diagnostics import communication_snapshot, RuntimeDiagnostics
from openpilot.common.gps import get_gps_location_service
from openpilot.system.hardware import HARDWARE
from openpilot.system.version import get_build_metadata
from openpilot.selfdrive.car.car_specific import CarSpecificEvents, MockCarState
from openpilot.selfdrive.car.cruise import VCruiseCarrot
from openpilot.selfdrive.pandad.pandad_api_impl import can_capnp_to_list, can_list_to_can_capnp
from openpilot.selfdrive.car.openpilot_toggle import CruiseMainOpenpilotToggle
from openpilot.selfdrive.car.alternative_experience import get_alternative_experience
from openpilot.selfdrive.car.card_diagnostics import should_log_card_diagnostics
from openpilot.selfdrive.locationd.helpers import PoseCalibrator, Pose
from openpilot.selfdrive.selfdrived.helpers import ExcessiveActuationCheck
from openpilot.selfdrive.selfdrived.events import Events, ET, EmptyAlert
from openpilot.selfdrive.selfdrived.state import StateMachine
from openpilot.selfdrive.selfdrived.impact_detector import ImpactDetector
from openpilot.selfdrive.selfdrived.alertmanager import AlertManager, set_offroad_alert
from openpilot.selfdrive.selfdrived.camera_config import get_camera_packets
from openpilot.selfdrive.controls.lib.cutin_alert import CutinAlertCandidate, CutinAlertTracker, promoted_cutin_candidates
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.controls.lib.latcontrol import LatControl, MIN_LATERAL_CONTROL_SPEED
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle, STEER_ANGLE_SATURATION_THRESHOLD
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature, get_lag_adjusted_curvature, is_volkswagen_meb, CONTROL_N
from openpilot.selfdrive.controls.lib.steer_ratio import resolve_vehicle_model_steer_ratio
from openpilot.selfdrive.controls.lib.lateral_readiness import LateralStartupGate, lateral_vehicle_parameters
from openpilot.selfdrive.carrot.carrot_controls import CarrotControls
from openpilot.selfdrive.carrot.carrot_man_input import get_carrot_man
from openpilot.selfdrive.monitoring.dm_alerts import driver_monitoring_hud_alert
from openpilot.selfdrive.modeld.constants import ModelConstants
from opendbc.car import structs, gen_empty_fingerprint
from opendbc.car.vehicle_model import VehicleModel
from opendbc.car.car_helpers import get_car
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.values import CAR
from opendbc.car.volkswagen.values import MEB_CURVATURE_PID_KP, MEB_CURVATURE_PID_KI, MEB_CURVATURE_PID_KF, MEB_CURVATURE_MAX
from openpilot.selfdrive.carrot.xiaoge.xiaoge_vision import (
  XiaogeVisionResult, apply_xiaoge_vision_result, parse_xiaoge_vision_payload, xiaoge_blindspot_vision,
)


class CameraInventoryIO:
  @staticmethod
  def available_streams(name, block=False):
    # 실제 연결이 아니라 테스트 입력의 스트림 목록만 반환한다.
    return ("VISION_STREAM_ROAD", "VISION_STREAM_DRIVER", "VISION_STREAM_WIDE_ROAD")


streams = SimpleNamespace(VISION_STREAM_ROAD="VISION_STREAM_ROAD", VISION_STREAM_DRIVER="VISION_STREAM_DRIVER",
                          VISION_STREAM_WIDE_ROAD="VISION_STREAM_WIDE_ROAD")


def shared_namespace(messaging):
  namespace = dict(globals())
  namespace.update(messaging=messaging, Params=MemoryConfiguration, REPLAY=False, SIMULATION=False, TESTING_CLOSET=False,
    State=log.SelfdriveState.OpenpilotState, EventName=log.OnroadEvent.EventName,
    ThermalStatus=log.DeviceState.ThermalStatus, PandaType=log.PandaState.PandaType,
    LaneChangeState=log.LaneChangeState, LaneChangeDirection=log.LaneChangeDirection,
    AlertLevel=log.DriverMonitoringState.AlertLevel, MonitoringPolicy=log.DriverMonitoringState.MonitoringPolicy,
    ButtonType=car.CarState.ButtonEvent.Type, SafetyModel=car.CarParams.SafetyModel,
    VisionIpcClient=CameraInventoryIO, VisionStreamType=streams,
    LONGITUDINAL_PERSONALITY_MAP={v:k for k,v in log.LongitudinalPersonality.schema.enumerants.items()},
    IGNORED_SAFETY_MODES=(car.CarParams.SafetyModel.silent, car.CarParams.SafetyModel.noOutput))
  return namespace


def load_policies(messaging):
  namespace = shared_namespace(messaging)
  import ast
  def source_constants(path, target, wanted):
    tree = ast.parse((SOURCE/path).read_text())
    for node in tree.body:
      if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE/path), "exec"), target)
  source_constants("openpilot/selfdrive/selfdrived/selfdrived.py", namespace,
                   {'REPLAY','SIMULATION','TESTING_CLOSET','LONGITUDINAL_PERSONALITY_MAP','ThermalStatus','State',
                    'PandaType','LaneChangeState','LaneChangeDirection','EventName','ButtonType','SafetyModel',
                    'AlertLevel','MonitoringPolicy','IGNORED_SAFETY_MODES'})
  load_definitions("openpilot/selfdrive/selfdrived/selfdrived.py", namespace)
  SelfdriveD = namespace["SelfdriveD"]
  control_namespace = shared_namespace(messaging)
  # 원형 module의 상수 할당만 읽는다. modeld runtime/GPU는 실행하지 않는다.
  model_tree = ast.parse((SOURCE / "openpilot/selfdrive/modeld/modeld.py").read_text())
  wanted = next(node for node in model_tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "LAT_SMOOTH_SECONDS" for target in node.targets))
  exec(compile(ast.Module(body=[wanted], type_ignores=[]), "<원형 modeld 상수>", "exec"), control_namespace)
  control_namespace.update(interfaces={str(CAR.TOYOTA_RAV4_TSS2_2022): CarInterface},
                           ACTUATOR_FIELDS=tuple(car.CarControl.Actuators.schema.fields.keys()),
                           LAT_CURVATURE_SATURATION_ACCEL=.1)
  source_constants("openpilot/selfdrive/controls/controlsd.py", control_namespace,
                   {'State','LaneChangeState','LaneChangeDirection','ACTUATOR_FIELDS','LAT_CURVATURE_SATURATION_ACCEL'})
  load_definitions("openpilot/selfdrive/controls/controlsd.py", control_namespace)
  Controls = control_namespace["Controls"]
  card_namespace = shared_namespace(messaging)
  card_namespace.update(CAN_BACKEND="capnp 변환 실행, Toyota CAN 파서 미실행",
    can_list_to_can_capnp=can_list_to_can_capnp, can_capnp_to_list=can_capnp_to_list,
    XIAOGE_SOURCE_HEARTBEAT_NS=1_000_000_000, XIAOGE_LANE_ERROR_LOG_INTERVAL_NS=5_000_000_000)
  source_constants("openpilot/selfdrive/car/card.py", card_namespace,
                   {'REPLAY','EventName','ButtonType','XIAOGE_SOURCE_HEARTBEAT_NS','XIAOGE_LANE_ERROR_LOG_INTERVAL_NS'})
  load_definitions("openpilot/selfdrive/car/card.py", card_namespace)
  return SelfdriveD, Controls, card_namespace["Car"]


class CardInterfaceIO(PhysicalInterfaceSink):
  """실제 CI의 읽기 전용 파라미터/계산 접근을 보존하고 초기화/송신만 제외한다."""
  def __init__(self, actual):
    super().__init__()
    self.actual = actual
    self.next_state = None
    self.update_io_calls = 0
    self.actual_ci_update_executed = False
    self.last_can_packets = []
    self.actual_ci_apply_calls = 0
    self.tx_permission = None
    self.generated_rows = []
    from opendbc.car import Bus
    from opendbc.car.toyota.values import DBC
    from opendbc.can import CANParser
    name = DBC[actual.CP.carFingerprint][Bus.pt]
    self.can_decoder = CANParser(name, [('ACC_CONTROL',0),('STEERING_LKA',0),('STEERING_LTA',0),
      ('LKAS_HUD',0),('PCS_HUD',0)], 0)
    self.feedback_pt=CANParser(name,[('VSC1S07',0),('PCM_CRUISE',0),('PCM_CRUISE_2',0)],0)
    self.feedback_camera=CANParser(name,[('LKAS_HUD',0)],2)
    self.feedback_seen=set()
    self.feedback_missing=Counter()

  def receive_feedback(self,nanos,frames):
    self.feedback_seen.update(self.feedback_pt.update([(nanos,frames)]))
    self.feedback_seen.update(self.feedback_camera.update([(nanos,frames)]))

  def update(self, can_list):
    # 수집/차량 상태 반환 경계만 대체한다. Card.state_update의 판단은 원형 그대로다.
    self.update_io_calls += 1
    self.last_can_packets = can_list
    if self.next_state is None:
      raise RuntimeError('명시적인 합성 CarState 입력이 없습니다')
    # 원형 CI.update가 마지막에 저장하는 위치와 필수 stock feedback의 합성 입력이다.
    self.actual.CS.out = self.next_state
    for message,signal,attribute in [('VSC1S07','GVC','gvc'),('PCM_CRUISE','CRUISE_STATE','pcm_acc_status'),
                                     ('PCM_CRUISE_2','PCM_FOLLOW_DISTANCE','pcm_follow_distance')]:
      address=self.feedback_pt.dbc.name_to_msg[message].address
      if address in self.feedback_seen:setattr(self.actual.CS,attribute,self.feedback_pt.vl[message][signal])
      else:
        self.feedback_missing[attribute]+=1
        if attribute=='pcm_acc_status':self.actual.CS.pcm_acc_status=0
    hud_address=self.feedback_camera.dbc.name_to_msg['LKAS_HUD'].address
    if hud_address in self.feedback_seen:self.actual.CS.lkas_hud=dict(self.feedback_camera.vl['LKAS_HUD'])
    else:self.feedback_missing['lkas_hud']+=1
    return self.next_state

  def apply(self, cc, now, model=None, radar=None):
    # 실제 apply와 Toyota 제어기는 메모리 CAN만 반환한다. 드라이버 송신은 없다.
    if self.tx_permission is None:
      raise RuntimeError('정상 RX로 생성한 C 권한 입력이 연결되지 않았습니다')
    frame = self.actual.CC.frame
    output, messages = self.actual.apply(cc, now, model, radar)
    self.actual_ci_apply_calls += 1
    self.apply_calls.append({'time_ns':now,'enabled':bool(cc.enabled),'longActive':bool(cc.longActive),
      'latActive':bool(cc.latActive),'accel':float(cc.actuators.accel),'cancel':bool(cc.cruiseControl.cancel),
      'model_supplied':model is not None,'radar_supplied':radar is not None,'controller_frame':frame,
      'generated_accel':float(output.accel),'generated_count':len(messages)})
    decoded = self.can_decoder.update([(now,messages)])
    p = self.tx_permission.probe
    for address,data,bus in messages:
      allowed_before = bool(p.lib.get_controls_allowed())
      long_before = bool(p.lib.get_longitudinal_allowed())
      import ctypes
      p.lib.get_relay_malfunction.restype=ctypes.c_bool
      relay_before=bool(p.lib.get_relay_malfunction())
      actual_tx = int(p.packet('tx',address,data,bus))
      allowed_after = bool(p.lib.get_controls_allowed())
      long_after = bool(p.lib.get_longitudinal_allowed())
      raw_accel = int.from_bytes(data[:2],'big',signed=True) if address==0x343 else None
      # 이 시나리오의 LKA torque/LTA actuation은0. 별도 횡방향 한계 검증은 아니다.
      # 실제 모델은 조향 요청도 만들 수 있다. 복잡한 조향 판정을 무조건 허용으로 대체하지 않는다.
      expected_tx = 0 if relay_before else int(raw_accel==0 or (long_before and -3500<=raw_accel<=2000)) if address==0x343 else None
      msg = self.can_decoder.dbc.addr_to_msg.get(address)
      signals = dict(self.can_decoder.vl[address]) if address in decoded else None
      checksum = None
      if msg is not None and any(s.calc_checksum is not None for s in msg.sigs.values()):
        checksum = data[-1] == (len(data)+(address>>8)+(address&255)+sum(data[:-1]))&255
      dbc_size_ok = len(data)==msg.size if msg is not None else None
      uds_ok = bytes(data)==bytes([15,2,62,0,0,0,0,0]) if address==0x750 else None
      self.generated_rows.append({'time_ns':now,'controller_frame':frame,'address':address,'bus':bus,'dlc':len(data),
        'message':msg.name if msg is not None else '원형 radar tester-present, 해당 DBC 메시지 없음',
        'cc_enabled':bool(cc.enabled),'cc_longActive':bool(cc.longActive),'cc_latActive':bool(cc.latActive),
        'cc_accel':float(cc.actuators.accel),'cc_cancel':bool(cc.cruiseControl.cancel),
        'c_controls_before':allowed_before,'c_controls_after':allowed_after,
        'c_longitudinal_before':long_before,'c_longitudinal_after':long_after,'actual_tx':actual_tx,
        'c_relay_before':relay_before,'expected_tx':expected_tx,'tx_matches_expected':actual_tx==expected_tx if expected_tx is not None else None,
        'tx_does_not_create_authority':allowed_before==allowed_after and long_before==long_after,
        'raw_accel_signed':raw_accel,'decoded_signals':signals,'toyota_checksum_ok':checksum,
        'dbc_size_ok':dbc_size_ok,'dbc_parse_updated':address in decoded if msg is not None else None,
        'tester_present_exact':uds_ok,'generated_payload_hex':bytes(data).hex()})
    return output,messages

  def __getattr__(self, key):
    return getattr(self.actual, key)


def car_params():
  import opendbc
  import opendbc.can.dbc
  path = LAB / "work/safety_validation/dbcs"
  if not path.is_dir():
    raise RuntimeError("검증용 원형 DBC 생성 폴더가 없습니다")
  opendbc.DBC_PATH = opendbc.can.dbc.DBC_PATH = str(path)
  # 이 설정은 테스트 입력만이며 운영 설정이나 권한 flag를 바꾸지 않는다.
  MemoryConfiguration.values["NNFF"] = "0"
  cp = CarInterface.get_params(CAR.TOYOTA_RAV4_TSS2_2022, gen_empty_fingerprint(), [], True, False, False)
  return cp


def initialise(messaging):
  cp = car_params()
  sd_class, control_class, card_class = load_policies(messaging)
  actual_ci = CarInterface(cp)
  proxy = CardInterfaceIO(actual_ci)
  card = card_class(proxy)
  sd = sd_class(cp)
  controls = control_class()
  # fault_active 자체는 원형 함수이며 외부 fault 파일 IO만 부재 입력으로 대체한다.
  from openpilot.selfdrive.modeld.jetlink import link
  link.FAULT = AbsentFaultFile()
  return cp, sd, controls, card, proxy
