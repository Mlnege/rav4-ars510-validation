"""원형 Carrot/native MPC/LongControl/Toyota CAN 계산을 가상 차량과 폐루프로 검증한다.

가상 선행차·모델 경로는 시뮬레이션 입력이며 실물 인식 정답이 아니다. 차량
응답은 명시한 지연과 1차 시정수 가정이다. CAN은 실제 DBC로 메모리 안에서만
생성·해석하며 소켓, 차량, 운영 Params 저장소는 접근하지 않는다.
"""
from collections import Counter, deque
import argparse
import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import time
from types import SimpleNamespace

import numpy as np
from offline_io import BUILD_ROOT, MemoryParams, REPO_ROOT, SimulationLog, prepare, repo_defaults

prepare(solver_overlay=True)
from openpilot.cereal import car, log
from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
from openpilot.selfdrive.carrot.signal_assist import SignalAssist
from openpilot.selfdrive.carrot.signal_start_guard import SignalStartGuard
from openpilot.selfdrive.carrot.signal_stop_prepare import SignalStopPrepare
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.selfdrive.modeld.constants import ModelConstants
from opendbc.can import CANParser
from opendbc.car import Bus, gen_empty_fingerprint
from opendbc.car.toyota.carcontroller import CarController
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.values import CAR, DBC
from opendbc.dbc.generator.generator import create_dbc


ORIGINAL_MONOTONIC = time.monotonic
WALL_CLOCK = time.perf_counter
VIRTUAL_NOW = 100.0
time.monotonic = lambda: VIRTUAL_NOW


@dataclass
class Scenario:
  name: str
  duration: float = 30.0
  initial_speed: float = 20.0
  cruise_speed: float = 25.0
  gap: float = 60.0
  lead_speed: float = 20.0
  lead: bool = False
  event_time: float = 5.0
  lead_brake: float = 0.0
  navigation_cap: float = 250.0
  navigation_source: str = "road"
  actuator_delay: float = 0.10
  actuator_tau: float = 0.15
  sensor_delay: float = 0.0
  personality: int = 1
  signal_case: str = "none"
  vision_probability: float = 0.99
  vision_distance_error: float = 0.0
  vision_speed_error: float = 0.0
  lead_lateral: float = 0.0
  model_intent: str = "cruise"


class Inputs(dict):
  def __init__(self):
    services = ("carrotMan", "livePose", "modelV2", "carState", "liveTracks", "radarState",
                "carControl", "controlsState", "selfdriveState", "liveParameters")
    self.seen = dict.fromkeys(services, True)
    self.alive = dict.fromkeys(services, True)
    self.valid = dict.fromkeys(services, True)
    self.recv_time = dict.fromkeys(services, VIRTUAL_NOW)
    self.logMonoTime = dict.fromkeys(services, int(VIRTUAL_NOW * 1e9))
    self.frame = 0

  def all_checks(self, services=None):
    return True


class NativeClosedLoopPlant:
  """원형 plant의 속도·거리 적분에 실제 제어 루프와 가정한 응답 지연을 연결한다."""
  dt = 0.01
  model_divisor = 5

  def __init__(self, scenario, *, radar_bridge=None, CP=None):
    self.scenario = scenario
    MemoryParams.values = repo_defaults()
    MemoryParams.values["SignalAssistMode"] = "0"
    # 다른 실제 차량 파라미터의 회귀도 같은 입력·응답 가정으로 비교할 수 있다.
    self.CP = CP if CP is not None else CarInterface.get_params(
      CAR.TOYOTA_RAV4_TSS2_2022, gen_empty_fingerprint(), [], True, False, False)
    self.carrot = CarrotPlanner(signal_assist=SignalAssist(), start_guard=SignalStartGuard(), stop_prepare=SignalStopPrepare())
    self.planner = LongitudinalPlanner(self.CP, init_v=scenario.initial_speed)
    self.long_control = LongControl(self.CP)
    generated_dbc_dir = Path(__file__).parent / "dbc"
    generated_dbc_dir.mkdir(exist_ok=True)
    generated_dbc = generated_dbc_dir / "toyota_nodsu_pt_generated.dbc"
    if not generated_dbc.exists():
      create_dbc(str(REPO_ROOT / "opendbc_repo/opendbc/dbc/generator/toyota"), "toyota_nodsu_pt.dbc", str(generated_dbc_dir))
    local_dbc = DBC[self.CP.carFingerprint].copy()
    local_dbc[Bus.pt] = str(generated_dbc)
    self.controller = CarController(local_dbc, self.CP)
    self.parser = CANParser(str(generated_dbc), [("ACC_CONTROL", 33)], 0)
    self.radar_bridge = radar_bridge
    self.speed = scenario.initial_speed
    self.distance = 0.0
    self.acceleration = 0.0
    self.lead_speed = scenario.lead_speed
    self.lead_acceleration = 0.0
    self.lead_distance = scenario.gap
    self.command = 0.0
    self.accel_queue = deque()
    self.observation_queue = deque()
    self.lead_observation = None
    self.step_index = 0
    self.native_status = Counter()
    self.decoder_failures = 0
    self.acc_messages = 0
    self.sm = Inputs()
    self.rows = []
    self.minimum_gap = math.inf
    self.first_negative_command = None
    self.first_negative_accel = None
    self.max_a = -math.inf
    self.min_a = math.inf
    self.max_jerk = 0.0
    self.max_moving_jerk = 0.0
    self.first_overlap = None
    self.first_unsafe_clearance = None
    self.wall_times = []
    self.long_plan = None

  def _messages(self, now):
    scenario = self.scenario
    cs = car.CarState(vEgo=float(self.speed), vEgoRaw=float(self.speed), vEgoCluster=float(self.speed),
                      aEgo=float(self.acceleration), standstill=bool(self.speed < 0.01), canValid=True,
                      gearShifter="drive", vCruise=scenario.cruise_speed * 3.6, vCruiseCluster=scenario.cruise_speed * 3.6,
                      vCluRatio=1.0, cruiseState={"enabled": True, "available": True, "speed": scenario.cruise_speed})
    control = log.ControlsState(longControlState=self.long_control.long_control_state, forceDecel=False,
                                desiredCurvature=0.0, curvature=0.0)
    state = log.SelfdriveState(enabled=True, active=True, experimentalMode=False, personality=scenario.personality)
    cc = car.CarControl(enabled=True, longActive=True, latActive=False, orientationNED=[0.0, 0.0, 0.0])
    cc.hudControl.leadDistanceBars = scenario.personality + 1
    cc.hudControl.leadVisible = scenario.lead
    radar = log.RadarState()
    true_gap = self.lead_distance - self.distance
    self.observation_queue.append((now, true_gap, self.lead_speed, self.lead_acceleration))
    while self.observation_queue and self.observation_queue[0][0] <= now - scenario.sensor_delay:
      self.lead_observation = self.observation_queue.popleft()
    if scenario.lead and self.lead_observation is not None:
      _, observed_gap, observed_speed, observed_accel = self.lead_observation
      lead = log.RadarState.LeadData(dRel=float(max(0.0, observed_gap)), yRel=0.0, vRel=float(observed_speed-self.speed),
                                     vLead=float(observed_speed), vLeadK=float(observed_speed), aLeadK=float(observed_accel),
                                     aLeadTau=1.5, status=True, modelProb=.99, radar=True, radarTrackId=1001)
      radar.leadOne = lead
    model = log.ModelDataV2()
    values = np.array(ModelConstants.T_IDXS)
    # Honda용 원형 plant의 ego+.5 고정은 Carrot에서 정지 의도로 해석될 수 있다.
    # 가속 시험은 계산식을 바꾸지 않고 입력 모델의 미래 진행 의도를 명시한다.
    if scenario.model_intent == "cruise":
      model_velocity = np.minimum(max(scenario.cruise_speed, 1.0), self.speed + .5 + .8 * values)
      model_velocity[0] = self.speed
    else:
      model_velocity = np.full_like(values, self.speed + .5)
      model_velocity[0] = self.speed
    previous_velocity = np.concatenate(([model_velocity[0]], model_velocity[:-1]))
    model.position.x = np.cumsum(np.diff(values, prepend=0) * (model_velocity+previous_velocity)*.5).tolist()
    model.position.y = [0.0] * len(values)
    model.position.z = [0.0] * len(values)
    model.velocity.x = model_velocity.tolist()
    model.velocity.y = [0.0] * len(values)
    model.velocity.z = [0.0] * len(values)
    model.acceleration.x = [0.0] * len(values)
    model.acceleration.y = [0.0] * len(values)
    model.acceleration.z = [0.0] * len(values)
    model.orientationRate.z = [0.0] * len(values)
    model.action.desiredAcceleration = self.acceleration
    model.meta.disengagePredictions.gasPressProbs = [1.0] * 6
    if scenario.lead:
      vision = model.init("leadsV3", 1)[0]
      vision.prob = scenario.vision_probability
      vision.x = [float(true_gap + 1.52 + scenario.vision_distance_error)] * 4
      vision.y = [float(-scenario.lead_lateral)] * 4
      vision.v = [float(self.lead_speed + scenario.vision_speed_error)] * 4
      vision.a = [float(self.lead_acceleration)] * 4
      vision.xStd = [1.0] * 4
      vision.yStd = [0.5] * 4
      vision.vStd = [1.0] * 4
    model.frameId = self.step_index // self.model_divisor + 1
    model.timestampEof = int(VIRTUAL_NOW * 1e9)
    if self.step_index % self.model_divisor == 0:
      self.last_model = model
    else:
      model = self.last_model
    if self.radar_bridge is not None:
      radar = self.radar_bridge.update(
        now_s=VIRTUAL_NOW, v_ego=self.speed, a_ego=self.acceleration, model=model,
        truth={"present": scenario.lead, "gap_m": true_gap, "lead_speed_mps": self.lead_speed,
               "lead_accel_mps2": self.lead_acceleration,
               "y_rel_m": scenario.lead_lateral},
      )
    nav = log.Event.new_message().init("carrotMan")
    nav.desiredSpeed = int(round(scenario.navigation_cap if now >= scenario.event_time else 250.0))
    nav.desiredSource = scenario.navigation_source
    nav.activeCarrot = 2
    self.sm.update(carState=cs, controlsState=control, selfdriveState=state, carControl=cc, radarState=radar,
                   modelV2=model, carrotMan=nav, liveParameters=log.LiveParametersData())
    self.sm.recv_time["carrotMan"] = VIRTUAL_NOW
    self.sm.logMonoTime["modelV2"] = int(model.timestampEof)
    return cs, cc

  def step(self):
    global VIRTUAL_NOW
    now = self.step_index * self.dt
    VIRTUAL_NOW = 100.0 + now
    previous_lead_speed = self.lead_speed
    if self.scenario.lead and now >= self.scenario.event_time:
      self.lead_speed = max(0.0, self.lead_speed - self.scenario.lead_brake * self.dt)
    self.lead_acceleration = (self.lead_speed-previous_lead_speed)/self.dt
    cs, cc = self._messages(now)
    if self.step_index % self.model_divisor == 0:
      start = WALL_CLOCK()
      self.planner.update(self.sm, self.carrot)
      self.wall_times.append((WALL_CLOCK()-start)*1000)
      self.native_status[self.planner.mpc.solution_status] += 1
      self.long_plan = log.LongitudinalPlan(aTarget=float(self.planner.output_a_target),
                                            vTargetNow=float(self.planner.output_v_target_now),
                                            jTargetNow=float(self.planner.output_j_target_now),
                                            shouldStop=bool(self.planner.output_should_stop),
                                            cruiseTarget=self.planner.v_cruise_kph,
                                            fcw=bool(self.planner.fcw))
      self.model_time = now
    accel, a_target, jerk = self.long_control.update(True, cs, self.long_plan, (-3.5, 2.0), now-self.model_time,
                                                   self.sm["radarState"])
    cc.actuators.accel = float(accel)
    cc.actuators.aTarget = float(a_target)
    cc.actuators.jerk = float(jerk)
    cc.actuators.longControlState = self.long_control.long_control_state
    state = SimpleNamespace(out=cs, gvc=self.acceleration, acc_type=1, pcm_acc_status=8,
                            pcm_follow_distance=4-cc.hudControl.leadDistanceBars, lkas_hud={})
    _, generated_can = self.controller.update(cc.as_reader(), state, int(VIRTUAL_NOW*1e9))
    acceleration_messages = [(addr, data, bus) for addr, data, bus in generated_can if addr == 0x343 and bus == 0]
    if acceleration_messages:
      addresses = self.parser.update([(int(VIRTUAL_NOW*1e9), acceleration_messages)])
      if 0x343 not in addresses:
        self.decoder_failures += 1
      else:
        self.command = self.parser.vl["ACC_CONTROL"]["ACCEL_CMD"]
        self.acc_messages += 1
    self.accel_queue.append((now, self.command))
    delayed = 0.0
    while self.accel_queue and self.accel_queue[0][0] <= now-self.scenario.actuator_delay:
      _, delayed = self.accel_queue.popleft()
      self.delayed_command = delayed
    delayed = getattr(self, "delayed_command", 0.0)
    previous_accel = self.acceleration
    previous_speed = self.speed
    response = 1.0 if self.scenario.actuator_tau <= 0 else min(1.0, self.dt/self.scenario.actuator_tau)
    self.acceleration += response * (delayed-self.acceleration)
    self.speed = max(0.0, self.speed+self.acceleration*self.dt)
    if self.speed == 0.0 and self.acceleration < 0:
      self.acceleration = 0.0
    self.distance += self.speed*self.dt
    self.lead_distance += self.lead_speed*self.dt
    gap = self.lead_distance-self.distance
    if self.scenario.lead:
      self.minimum_gap = min(self.minimum_gap, gap)
      if gap < .4 and self.first_unsafe_clearance is None:
        self.first_unsafe_clearance = now
      if gap < 0.0 and self.first_overlap is None:
        self.first_overlap = now
    if now >= self.scenario.event_time:
      if self.command < -.1 and self.first_negative_command is None:
        self.first_negative_command = now-self.scenario.event_time
      if self.acceleration < -.1 and self.first_negative_accel is None:
        self.first_negative_accel = now-self.scenario.event_time
    self.max_a = max(self.max_a, self.acceleration)
    self.min_a = min(self.min_a, self.acceleration)
    self.max_jerk = max(self.max_jerk, abs(self.acceleration-previous_accel)/self.dt)
    if previous_speed > .5 and self.speed > .5:
      self.max_moving_jerk = max(self.max_moving_jerk, abs(self.acceleration-previous_accel)/self.dt)
    if self.step_index % self.model_divisor == 0:
      self.rows.append([now, self.distance, self.speed, self.acceleration, self.command,
                        self.lead_speed, gap, self.planner.v_cruise_kph, self.planner.output_a_target,
                        int(self.planner.output_should_stop), int(self.planner.fcw), self.planner.mpc.solution_status])
    self.step_index += 1

  def run(self, outdir=None):
    while self.step_index*self.dt < self.scenario.duration:
      self.step()
    rows = np.asarray(self.rows)
    result = asdict(self.scenario) | {
      "steps": self.step_index, "model_steps": len(self.wall_times), "native_status": dict(self.native_status),
      "final_speed": self.speed, "minimum_gap": self.minimum_gap if self.scenario.lead else None,
      "collision": bool(self.scenario.lead and self.minimum_gap < .4), "minimum_accel": self.min_a,
      "geometric_overlap": bool(self.scenario.lead and self.minimum_gap < 0),
      "clearance_rule_m": .4,
      "first_geometric_overlap_s": self.first_overlap, "first_unsafe_clearance_s": self.first_unsafe_clearance,
      "maximum_accel": self.max_a, "maximum_jerk": self.max_jerk,
      "maximum_moving_jerk": self.max_moving_jerk,
      "brake_command_delay": self.first_negative_command, "brake_response_delay": self.first_negative_accel,
      "native_work_mean_ms": float(np.mean(self.wall_times)), "native_work_p99_ms": float(np.percentile(self.wall_times, 99)),
      "acc_control_messages": self.acc_messages, "acc_control_decode_errors": self.decoder_failures,
      "finite": bool(np.all(np.isfinite(rows))),
      "native_solver": type(self.planner.mpc.solver).__module__ + "." + type(self.planner.mpc.solver).__name__,
    }
    if outdir:
      outdir.mkdir(parents=True, exist_ok=True)
      with (outdir/(self.scenario.name+".csv")).open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["t_s", "ego_x_m", "ego_v_mps", "ego_a_mps2", "acc_command_mps2", "lead_v_mps", "gap_m",
                         "cruise_target_kph", "planner_a_target", "should_stop", "fcw", "native_status"])
        writer.writerows(self.rows)
    return result


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--out", type=Path, default=Path(__file__).parent/"results")
  parser.add_argument("--smoke", action="store_true")
  args = parser.parse_args()
  cases = [Scenario("cruise_accel", initial_speed=0.0, duration=10 if args.smoke else 45),
           Scenario("front_brake", lead=True, initial_speed=25, lead_speed=25, cruise_speed=25, gap=80,
                    lead_brake=6, duration=30),
           Scenario("stopped_front", lead=True, initial_speed=25, lead_speed=0, cruise_speed=25, gap=110, duration=30),
           Scenario("curve_cap", initial_speed=25, cruise_speed=25, navigation_cap=50, navigation_source="vturn", duration=30),
           Scenario("map_cap", initial_speed=25, cruise_speed=25, navigation_cap=50, navigation_source="route", duration=30)]
  if args.smoke:
    cases = cases[:1]
  results = []
  for scenario in cases:
    result = NativeClosedLoopPlant(scenario).run(args.out)
    results.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
  args.out.mkdir(parents=True, exist_ok=True)
  (args.out/"summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
  main()
