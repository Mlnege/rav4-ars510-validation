"""원형 시간 계약에만 오류 입력을 넣는 독립 메모리 검사. 차량/운영 설정 접근 없음."""
import ast
import contextlib
from datetime import datetime, UTC
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time
import typing
import sys


WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
SOURCE = ROOT / "work/carrotpilot"
LAB = ROOT / "work/download_e2e"
os.environ["CARROT_VALIDATION_BUILD"] = str(LAB / "work/native_sim/build_unique")
sys.path.insert(0, str(LAB / "work/native_sim"))
from offline_io import prepare
prepare(solver_overlay=True)
import capnp
from openpilot.cereal import car, log
from openpilot.cereal.services import SERVICE_LIST
from openpilot.common.utils import MovingAverage
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.controls.lib.lateral_readiness import LateralStartupGate
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.selfdrive.selfdrived.state import StateMachine
from tools.ars510_validation.signal.native_signal import NativeSignalHarness, ReplayClock, input_clock


sources = {}
observations = []


def source(path):
  full = SOURCE / path
  raw = full.read_bytes()
  sources[path] = hashlib.sha256(raw).hexdigest()
  return ast.parse(raw.decode("utf-8"))


def extracted(path, selector, namespace):
  tree = source(path)
  nodes = selector(tree)
  # 타입 주석만 지연 평가한다. 원형 계산/분기/함수 본문은 수정하지 않는다.
  body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes]
  module = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
  exec(compile(module, str(SOURCE / path), "exec"), namespace)
  return namespace


class Clock:
  def __init__(self, value=100.):
    self.value = value

  def monotonic(self):
    return self.value

  def monotonic_ns(self):
    return round(self.value * 1e9)


ns = dict(vars(typing), os=os, time=time, capnp=capnp, log=log, SERVICE_LIST=SERVICE_LIST, MovingAverage=MovingAverage)
extracted("openpilot/cereal/messaging/__init__.py",
          lambda tree: [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in ("SubMaster", "FrequencyTracker")], ns)
SubMaster, FrequencyTracker = ns["SubMaster"], ns["FrequencyTracker"]


def receiver(services):
  # 실제 소켓을 여는 __init__ 대신 같은 시작 필드만 구성한다. update_msgs와 모든 판정은 원형이다.
  sm = SubMaster.__new__(SubMaster)
  sm.frame, sm.services = -1, services
  sm.seen = dict.fromkeys(services, False)
  sm.updated = dict.fromkeys(services, False)
  sm.recv_time = dict.fromkeys(services, 0.)
  sm.recv_frame = dict.fromkeys(services, 0)
  sm.logMonoTime = dict.fromkeys(services, 0)
  sm.valid = dict.fromkeys(services, False)
  sm.alive = dict.fromkeys(services, False)
  sm.freq_ok = dict.fromkeys(services, False)
  sm.static_freq_services = set(services)
  sm.data = {}
  sm.ignore_average_freq = sm.ignore_alive = sm.ignore_valid = []
  sm.simulation = False
  sm.freq_tracker = {s: FrequencyTracker(SERVICE_LIST[s].frequency, 100., s == "carControl",
                                        service_freq_range=SERVICE_LIST[s].frequency_range) for s in services}
  return sm


def packet(service, timestamp, *, valid=True):
  event = log.Event.new_message(valid=valid, logMonoTime=round(timestamp*1e9))
  event.init(service)
  return event


def warm_receiver(services=("modelV2", "longitudinalPlan", "carControl"), source_age=0.):
  sm = receiver(services)
  for index in range(501):
    now = 100. + index*.01
    messages = [packet(s, now-source_age) for s in services if s == "carControl" or index % 5 == 0]
    sm.update_msgs(now, messages)
  return sm, now


for source_age in (0., .3229, 1.):
  sm, now = warm_receiver(source_age=source_age)
  observations.append({"kind": "source_age_vs_receive_age", "source_age_s": source_age,
                       "all_checks": sm.all_checks(), "alive": sm.alive.copy(), "freq_ok": sm.freq_ok.copy(),
                       "receive_age_s": now-sm.recv_time["modelV2"],
                       "model_header_age_s": now-sm.logMonoTime["modelV2"]*1e-9})
for service in ("modelV2", "longitudinalPlan", "carControl"):
  for gap in (.099, .101, .3229, .499, .501):
    sm, now = warm_receiver()
    sm.update_msgs(now+gap, [])
    observations.append({"kind": "missing_receive", "service": service, "gap_s": gap,
                         "alive": sm.alive[service], "freq_ok": sm.freq_ok[service],
                         "all_checks_service": sm.all_checks([service])})

clock = Clock()
rk_ns = {"time": clock, "MovingAverage": MovingAverage, "getproctitle": lambda: "offline_timing_probe"}
extracted("openpilot/common/realtime.py", lambda tree: [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Ratekeeper"], rk_ns)
rk = rk_ns["Ratekeeper"](100, print_delay_threshold=None)
for index in range(110):
  clock.value = 100.+index*.01
  rk.monitor_time()
clock.value += .3229
returned = rk.monitor_time()
observations.append({"kind": "ratekeeper_single_stall", "injected_gap_s": .3229,
                     "monitor_return_lagged": returned, "lagging_property": rk.lagging,
                     "average_interval_s": rk.avg_dt.get_average(), "remaining_s": rk.remaining})

control_tree = source("openpilot/selfdrive/controls/controlsd.py")
control_class = next(node for node in control_tree.body if isinstance(node, ast.ClassDef) and node.name == "Controls")
control_method = next(node for node in control_class.body if isinstance(node, ast.FunctionDef) and node.name == "state_control")
assignment = next(node for node in ast.walk(control_method) if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "t_since_plan" for target in node.targets))
age_code = compile(ast.fix_missing_locations(ast.Module(body=[assignment], type_ignores=[])), "<원형 controls 시간식>", "exec")
for frame_gap in (0, 1, 32):
  scope = {"self": SimpleNamespace(sm=SimpleNamespace(frame=500+frame_gap, recv_frame={"longitudinalPlan": 500})), "DT_CTRL": DT_CTRL}
  exec(age_code, scope)
  observations.append({"kind": "controls_frame_age", "real_gap_fixture_s": .3229, "frame_gap": frame_gap,
                       "t_since_plan_s": scope["t_since_plan"]})

with input_clock(ReplayClock()):
  h = NativeSignalHarness(WORK / "transport", camera_profile="ox03c10")
  h.step(100., signal_mode=0)
  cp = h.cp
  for plan_age in (0., .199, .201, .3229, 1., 4.):
    for target in (-1., 1.):
      controller = LongControl(cp)
      state = car.CarState(vEgo=15., aEgo=0., canValid=True, gearShifter="drive",
                           cruiseState={"enabled": True, "available": True})
      plan = log.LongitudinalPlan(aTarget=target, vTargetNow=15., jTargetNow=0., shouldStop=False,
                                 processingDelay=plan_age, longitudinalPlanSource="cruise")
      output = controller.update(True, state, plan, (-3.5, 2.), plan_age, log.RadarState())[0]
      observations.append({"kind": "ordinary_long_control_age", "plan_age_s": plan_age,
                           "processing_delay_s": plan_age, "a_target": target, "output_accel": float(output),
                           "state": str(controller.long_control_state), "standalone_only": True})

for event_name in ("commIssue", "commIssueAvgFreq", "selfdrivedLagging", "modeldLagging"):
  machine, events = StateMachine(), Events()
  events.add(log.OnroadEvent.EventName.pcmEnable)
  with contextlib.redirect_stdout(io.StringIO()):
    machine.update(events)
  events.clear()
  events.add(getattr(log.OnroadEvent.EventName, event_name))
  first, disabled_at = None, None
  with contextlib.redirect_stdout(io.StringIO()):
    for index in range(1, 304):
      enabled, active = machine.update(events)
      if first is None:
        first = {"enabled": enabled, "active": active, "state": str(machine.state)}
      if not enabled:
        disabled_at = index
        break
  observations.append({"kind": "state_machine_communication_fault", "event": event_name,
                       "first_update": first, "disabled_at_update": disabled_at,
                       "nominal_counter_seconds": (disabled_at-1)*DT_CTRL if disabled_at is not None else None,
                       "counter_uses_wall_time": False})

clock = ReplayClock()
with input_clock(clock):
  h = NativeSignalHarness(WORK / "transport_clock", clock=clock, camera_profile="ox03c10")
  for index in range(100):
    h.step(100.+index*.05)
  wall_start, cpu_start = time.perf_counter(), time.thread_time()
  mono_start = time.monotonic()
  time.sleep(.3229)
  h.planner.publish(h.sm, h.sink, h.carrot)
  observations.append({"kind": "frozen_replay_clock_stall", "requested_wall_stall_s": .3229,
                       "measured_wall_s": time.perf_counter()-wall_start,
                       "thread_cpu_s": time.thread_time()-cpu_start,
                       "monotonic_advance_s": time.monotonic()-mono_start,
                       "plan_processing_delay_s": float(h.sink.event.longitudinalPlan.processingDelay),
                       "plan_valid": bool(h.sink.event.valid),
                       "interpretation_ko": "실제 322.9ms 원인을 재현한 것이 아니라 같은 길이의 IO 대기를 주입한 측정 계약 검사."})
  clock.now += .3229
  old_sm_timestamp = h.sm.logMonoTime["modelV2"]
  observation, context = h.prepare_runtime.read(h.sm, clock.now)
  h.planner.update(h.sm, h.carrot)
  h.planner.publish(h.sm, h.sink, h.carrot)
  observations.append({"kind": "advanced_clock_preserved_source", "advance_s": .3229,
                       "model_header_preserved": h.sm.logMonoTime["modelV2"] == old_sm_timestamp,
                       "prepare_runtime_valid": bool(context["valid"]),
                       "prepare_control_active": bool(h.carrot.prepare_control_active),
                       "plan_processing_delay_s": float(h.sink.event.longitudinalPlan.processingDelay),
                       "plan_valid": bool(h.sink.event.valid), "cached_harness_validity": True})
  h.sm.touch(clock.now)
  h.sm["modelV2"].timestampEof = round((clock.now-.3229)*1e9)
  h.planner.publish(h.sm, h.sink, h.carrot)
  observations.append({"kind": "fresh_model_header_old_camera_eof", "camera_eof_age_s": .3229,
                       "processing_delay_s": float(h.sink.event.longitudinalPlan.processingDelay),
                       "plan_valid": bool(h.sink.event.valid)})
  for service in ("modelV2", "radarState", "carState", "controlsState", "selfdriveState"):
    h.sm.valid[service] = False
    h.planner.publish(h.sm, h.sink, h.carrot)
    observations.append({"kind": "plan_publisher_dependency", "invalid_service": service,
                         "plan_valid": bool(h.sink.event.valid)})
    h.sm.valid[service] = True
  for elapsed in (.05, .199, .201, .3229):
    h.planner.output_a_target, h.planner.output_should_stop = .2, False
    h.planner._signal_prepare_time = 100.
    h.planner._signal_prepare_previous = 0.
    from openpilot.selfdrive.carrot.signal_stop_prepare import PrepareAccel
    h.planner._signal_prepare_accel = PrepareAccel()
    h.planner.apply_signal_stop_prepare(h.sm, SimpleNamespace(prepare_decision=SimpleNamespace(active=True),
                                         prepare_control_active=True), False, now=100.+elapsed)
    observations.append({"kind": "final_prepare_elapsed", "elapsed_s": elapsed,
                         "result_accel": float(h.planner.output_a_target)})

# 원형 card 메서드 전체를 실행하되 CI.apply와 송신은 호출 기록만 남기는 IO sink다.
card_tree = source("openpilot/selfdrive/car/card.py")
card_class = next(node for node in card_tree.body if isinstance(node, ast.ClassDef) and node.name == "Car")
card_method = next(node for node in card_class.body if isinstance(node, ast.FunctionDef) and node.name == "controls_update")
clock = Clock()
card_ns = {"car": car, "time": clock, "REPLAY": False,
           "can_list_to_can_capnp": lambda messages, **kwargs: {"messages": messages, **kwargs}}
extracted("openpilot/selfdrive/car/card.py", lambda tree: [card_method], card_ns)


class NoLiveParams:
  def get_bool(self, key):
    if key != "ImpactDashcamReboot":
      raise RuntimeError("운영 설정 접근 차단: " + key)
    return False


for alive, valid, frequency in ((True, True, True), (True, False, True), (True, True, False), (False, True, True)):
  calls, sends = [], []
  sm, now = warm_receiver(("carControl",))
  sm.alive["carControl"], sm.valid["carControl"], sm.freq_ok["carControl"] = alive, valid, frequency
  sm.data["modelV2"], sm.data["radarState"] = log.ModelDataV2(), log.RadarState()
  sm.valid.update(modelV2=False, radarState=False)
  sm.alive.update(modelV2=False, radarState=False)
  clock.value = now
  cc = car.CarControl(enabled=True, longActive=True, latActive=False, actuators={"accel": 1.})
  state = car.CarState(canValid=True, vEgo=15.)
  fixture = SimpleNamespace(initialized_prev=True, params=NoLiveParams(), sm=sm,
    lateral_startup=LateralStartupGate(ready=True), card_diag_recv_ns=clock.monotonic_ns(),
    card_diag_stage_current={}, card_diag_stage_names=[], card_diag_process_max_us=0,
    card_diag_slow_process=0, card_diag_frames=0,
    CI=SimpleNamespace(apply=lambda *args: (calls.append(args) or car.CarControl.Actuators(), [])),
    pm=SimpleNamespace(send=lambda *args: sends.append(args)))
  card_ns["controls_update"](fixture, state, cc)
  observations.append({"kind": "card_application_boundary", "carcontrol_alive": alive, "carcontrol_valid": valid,
                       "carcontrol_freq_ok": frequency, "apply_calls": len(calls), "memory_send_calls": len(sends),
                       "init_called": False, "vehicle_can_sent": False,
                       "scope_ko": "원형 메서드 분기 검사. CI.apply/전송 IO sink만 교체했으며 이 검사에서 CarController/CAN/Panda는 실행하지 않음."})

report = {"recorded_utc": datetime.now(UTC).isoformat(), "observations": observations, "source_sha256": sources,
          "source_unchanged": all(hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() == value for path, value in sources.items()),
          "runtime": {"python": sys.version, "monotonic": vars(time.get_clock_info("monotonic")),
                      "perf_counter": vars(time.get_clock_info("perf_counter")), "scheduler_policy": os.sched_getscheduler(0)},
          "execution_scope_ko": "원형 SubMaster/FrequencyTracker/Ratekeeper source class와 원형 state/LongControl/신호/계획 클래스를 실행. 소켓 생성자만 배제한 수신 상태 fixture와 실제 Cap'n Proto 사용. 표기한 controls 시간식 및 card 메서드는 AST로 수정 없이 추출. IO·시각만 합성하며 운영 Params·차량·Panda·환경 파일·기존 소스를 수정하지 않음.",
          "physical_safety_proven": False, "actual_322ms_rootcause_identified": False}
WORK.mkdir(exist_ok=True)
(WORK / "contract_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"observations": len(observations), "source_unchanged": report["source_unchanged"],
                  "physical_safety_proven": False}, ensure_ascii=False))
