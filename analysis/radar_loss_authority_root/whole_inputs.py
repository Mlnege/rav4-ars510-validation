"""초기화·권한 체인에 공급하는 명시적 합성 스키마 입력과 실제 C PCM 수신."""
import ctypes
from pathlib import Path
import sys

import numpy as np

from whole_io import LAB, car, log, SERVICE_LIST

sys.path.insert(0, str(LAB / "work/safety_validation"))
from verify_compiled import Probe, pcm, wheels, toyota_payload


class VehiclePermissionInput:
  """독립 Panda/ECU 준비는 미검증. 실제 C 정상 RX가 반환한 권한만 읽는다."""
  def __init__(self, cp):
    self.probe = Probe(LAB / "work/safety_validation/libsafety_download_native.so")
    assert self.probe.lib.set_safety_hooks(2, int(cp.safetyConfigs[0].safetyParam)) == 0
    # 원형 모드 초기화가 만든 False 상태를 유지한다. 테스트 counter2 우회는 사용하지 않는다.
    self.probe.lib.set_timer(0)
    self.probe.lib.set_alternative_experience(int(cp.alternativeExperience))
    self.received = 0
    self.shortcut_controls_true_calls = 0

  def update(self, now, *, engaged, gas=False, brake=False):
    p = self.probe
    p.lib.set_timer(round(now*1e6))
    p.packet("rx", 0xaa, wheels(15.))
    p.packet("rx", 0x260, toyota_payload(0x260, bytes(8)))
    p.packet("rx", 0x226, bytes([0, 0, 0, 0, 32 if brake else 0, 0, 0, 0]))
    p.packet("rx", 0x1d2, pcm(engaged=engaged, gas=gas))
    p.lib.safety_tick_current_safety_config()
    self.received += 4

  def allowed(self):
    return bool(self.probe.lib.get_controls_allowed())

  def invalid(self):
    return bool(ctypes.c_bool.in_dll(self.probe.lib, "safety_rx_checks_invalid").value)


def event(messaging, service, *, now, cp, permission, engaged=False, available=False,
          gas=False, brake=False, cancel=False, model_age=0., model_drop=0., acquisition=None, header=None):
  sizes = {"pandaStates": 1, "onroadEvents": 0}
  value = messaging.new_message(service, sizes.get(service), valid=True,
                                logMonoTime=round((now if header is None else header)*1e9))
  body = getattr(value, service)
  if service == "carState":
    body.canValid, body.canTimeout, body.gearShifter = True, False, "drive"
    body.vEgo = body.vEgoRaw = body.vEgoCluster = 15.
    body.aEgo = 0.
    body.latEnabled = True
    body.vCluRatio = 1.
    body.vCruise = body.vCruiseCluster = 75.
    body.cruiseState.available = available
    body.cruiseState.enabled = engaged
    body.cruiseState.speed = body.cruiseState.speedCluster = 75/3.6
    body.gasPressed, body.brakePressed = gas, brake
    body.buttonEvents = [{"type": "cancel", "pressed": True}] if cancel else []
    body.doorOpen, body.seatbeltUnlatched = False, False
  elif service == "modelV2":
    origin = now-model_age if acquisition is None else acquisition
    body.timestampEof = round(origin*1e9)
    body.frameId = max(0, round(origin*20))
    body.frameDropPerc = model_drop
    body.position.x = np.linspace(0., 200., 33).tolist()
    body.position.y = body.position.z = [0.] * 33
    body.position.t = np.linspace(0., 10., 33).tolist()
    body.velocity.x = [15.] * 33
    body.velocity.y = body.velocity.z = [0.] * 33
    body.acceleration.x = body.acceleration.y = body.acceleration.z = [0.] * 33
    body.orientationRate.x = body.orientationRate.y = body.orientationRate.z = [0.] * 33
    body.action.desiredVelocity = 15.
    body.action.desiredAcceleration = 0.
    body.action.desiredCurvature = 0.
    body.meta.laneChangeState = "off"
    body.meta.hardBrakePredicted = False
  elif service == "livePose":
    body.timestamp = round(now*1e9)
    body.inputsOK = body.posenetOK = body.sensorsOK = True
    for name in ("orientationNED", "velocityDevice", "accelerationDevice", "angularVelocityDevice"):
      xyz = getattr(body, name)
      xyz.valid = True
      xyz.x = xyz.y = xyz.z = 0.
      xyz.xStd = xyz.yStd = xyz.zStd = .001
  elif service == "liveCalibration":
    body.calStatus = "calibrated"
    body.rpyCalib = [0., 0., 0.]
  elif service == "liveParameters":
    body.valid = body.sensorValid = body.posenetValid = True
    body.steerRatio = float(cp.steerRatio)
    body.stiffnessFactor = 1.
    body.angleOffsetDeg = body.roll = 0.
  elif service == "liveTorqueParameters":
    body.useParams = False
  elif service == "deviceState":
    body.started = True
    body.deviceType = "tizi"
    body.thermalStatus = "green"
    body.freeSpacePercent = 90.
    body.memoryUsagePercent = 20
    body.fanSpeedPercentDesired = 0
  elif service == "peripheralState":
    body.pandaType = "uno"
    body.fanSpeedRpm = 1000
  elif service == "pandaStates":
    panda = body[0]
    panda.safetyModel = cp.safetyConfigs[0].safetyModel
    panda.safetyParam = cp.safetyConfigs[0].safetyParam
    panda.alternativeExperience = cp.alternativeExperience
    panda.controlsAllowed = permission.allowed()
    panda.safetyRxChecksInvalid = permission.invalid()
    panda.pandaType = "uno"
    panda.faults = []
  elif service == "driverMonitoringState":
    body.dm2Disabled = False
    body.lockout = False
    body.alertLevel = "none"
    body.activePolicy = "vision"
    body.visionPolicyState.uncertainOffroadAlertPercent = 0
  elif service == "managerState":
    body.rebootRequired = False
    processes = body.init("processes", 4)
    for node, name in zip(processes, ("card", "controlsd", "selfdrived", "plannerd"), strict=True):
      node.name, node.running, node.shouldBeRunning = name, True, True
  elif service == "controlsState":
    body.lateralControlState.init("torqueState")
    body.longControlState = "off"
  elif service == "selfdriveState":
    body.state = "disabled"
    body.enabled = body.active = False
    body.personality = "standard"
  elif service == "roadCameraState":
    body.sensor = "ox03c10"
    body.frameId = round(now*20)
    body.timestampEof = round(now*1e9)
  elif service in ("driverCameraState", "wideRoadCameraState"):
    body.frameId = round(now*20)
    body.timestampEof = round(now*1e9)
  elif service == "liveDelay":
    body.lateralDelay = .15
  elif service == "accelerometer":
    body.source = "lsm6ds3trc"
    body.init("acceleration").v = [0., 0., 9.80665]
    body.timestamp = round(now*1e9)
  elif service == "gyroscope":
    body.source = "lsm6ds3trc"
    body.init("gyro").v = [0., 0., 0.]
    body.timestamp = round(now*1e9)
  return value


EXTERNAL_SERVICES = ("carState", "modelV2", "radarState", "livePose", "liveCalibration", "liveParameters",
                     "liveTorqueParameters", "deviceState", "peripheralState", "pandaStates", "driverMonitoringState",
                     "managerState", "roadCameraState", "driverCameraState", "wideRoadCameraState", "liveDelay",
                     "lateralPlan", "driverAssistance", "accelerometer", "gyroscope", "gpsLocation", "gpsLocationExternal",
                     "carrotMan")
