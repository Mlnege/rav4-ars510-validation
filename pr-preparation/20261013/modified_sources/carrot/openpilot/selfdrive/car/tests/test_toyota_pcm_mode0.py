"""RAV4 직접 제어 모드0의 PCM 관측·로컬 입력·당근 속도 제한 회귀.

메모리 Params와 블루투스 입출력만 격리한다. 실제 순항·당근 플래너의 전체
계산을 실행하지만 MPC·호스트 권한·실차 CAN·물리 제동 시험은 아니다.
"""
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest

if os.environ.get("CARROT_OFFLINE_VALIDATION") != "1":
  pytest.skip("격리된 새 검사 프로세스에서 CARROT_OFFLINE_VALIDATION=1이 필요합니다", allow_module_level=True)

import numpy as np

from tools.ars510_validation.native_runtime import MemoryParams, prepare_io, repo_defaults  # noqa: TID251

if getattr(sys.modules.get("openpilot.common.params"), "Params", None) is not MemoryParams:
  prepare_io()

from openpilot.cereal import car, log
import openpilot.selfdrive.car.cruise as cruise
from openpilot.selfdrive.car.toyota_pcm_speed import ToyotaPcmSetSpeedSync
from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
from openpilot.selfdrive.carrot.signal_assist import SignalAssist
from openpilot.selfdrive.carrot.signal_start_guard import SignalStartGuard
from openpilot.selfdrive.carrot.signal_stop_prepare import SignalStopPrepare
from openpilot.selfdrive.modeld.constants import ModelConstants

REPO_ROOT = Path(__file__).resolve().parents[4]
BASE_COMMIT = "2ec25da3c10e369eaf4ad0313fde3280e5a8b06e"


def make_cp(**overrides):
  values = {"brand": "toyota", "carFingerprint": "TOYOTA_RAV4_TSS2_2022", "pcmCruise": True,
            "openpilotLongitudinalControl": True}
  values.update(overrides)
  return car.CarParams(**values)


def make_cs(speed=75.0, *, enabled=False, cluster=None, **overrides):
  return car.CarState(
    gearShifter="drive", canValid=True, vEgo=21.0, vEgoCluster=21.0,
    cruiseState={"available": True, "enabled": enabled, "speed": speed / 3.6,
                 "speedCluster": (speed + 1.0 if cluster is None else cluster) / 3.6},
    **overrides,
  )


def snapshot(value):
  serialized = value.to_bytes()
  value.clear_write_flag()
  return serialized


def assert_speed(result, speed, cluster=None):
  assert result is not None
  assert result[0] == pytest.approx(speed, abs=1e-4)
  assert result[1] == pytest.approx(speed + 1.0 if cluster is None else cluster, abs=1e-4)


def test_first_already_enabled_sample_and_steady_pcm_only_establish_baseline():
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(enabled=True)
  assert sync.update(cp, 0, cs) is None
  for _ in range(4):
    assert sync.update(cp, 0, cs) is None


def test_observed_enable_and_resume_edges_apply_stock_speed_without_button_events():
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs()
  before = snapshot(cp)
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 75)
  cs.cruiseState.enabled = False
  cs.cruiseState.speed = 80 / 3.6
  cs.cruiseState.speedCluster = 81 / 3.6
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 80)
  assert not cs.buttonEvents
  assert snapshot(cp) == before


@pytest.mark.parametrize("new_speed, changed", [(74, True), (80, True), (75.49, False), (75.5, True)])
def test_observed_stock_speed_change_uses_half_kph_threshold(new_speed, changed):
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(enabled=True)
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.speed = new_speed / 3.6
  cs.cruiseState.speedCluster = (new_speed + 1) / 3.6
  result = sync.update(cp, 0, cs)
  if changed:
    assert_speed(result, new_speed)
  else:
    assert result is None


def test_local_change_wins_and_refreshes_stock_baseline_for_next_frame():
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(enabled=True)
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.speed = 80 / 3.6
  assert sync.update(cp, 0, cs, local_changed=True) is None
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.speed = 81 / 3.6
  cs.cruiseState.speedCluster = 82 / 3.6
  assert_speed(sync.update(cp, 0, cs), 81)


@pytest.mark.parametrize("overrides, mode", [
  ({"brand": "honda"}, 0), ({"brand": "hyundai"}, 0),
  ({"carFingerprint": "TOYOTA_RAV4_TSS2"}, 0), ({"carFingerprint": "TOYOTA_RAV4_TSS2_2023"}, 0),
  ({"pcmCruise": False}, 0), ({"openpilotLongitudinalControl": False}, 0),
  ({}, 1), ({}, 2), ({}, 3),
])
def test_other_vehicle_control_or_speed_modes_cannot_enter_new_path(overrides, mode):
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(**overrides), make_cs()
  assert sync.update(cp, mode, cs) is None
  cs.cruiseState.enabled = True
  assert sync.update(cp, mode, cs) is None
  cs.cruiseState.speed = 80 / 3.6
  assert sync.update(cp, mode, cs) is None


@pytest.mark.parametrize("invalid", [0, -1, 145.001, 146, 255, math.nan, math.inf])
def test_invalid_speed_resets_observation_and_cannot_replay_old_enable_edge(invalid):
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs()
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 75)
  cs.cruiseState.speed = invalid / 3.6
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.speed = 80 / 3.6
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.speed = 81 / 3.6
  cs.cruiseState.speedCluster = 82 / 3.6
  assert_speed(sync.update(cp, 0, cs), 81)


@pytest.mark.parametrize("invalid_state", ["can", "available", "mode"])
def test_lost_input_or_mode_switch_requires_a_new_valid_baseline(invalid_state):
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs()
  sync.update(cp, 0, cs)
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 75)
  if invalid_state == "can":
    cs.canValid = False
  elif invalid_state == "available":
    cs.cruiseState.available = False
  assert sync.update(cp, 2 if invalid_state == "mode" else 0, cs) is None
  cs.canValid = cs.cruiseState.available = True
  cs.cruiseState.speed = 80 / 3.6
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = False
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = True
  cs.cruiseState.speedCluster = 81 / 3.6
  assert_speed(sync.update(cp, 0, cs), 80)


@pytest.mark.parametrize("cluster", [0, -1, math.nan, math.inf, 255])
def test_invalid_cluster_speed_falls_back_to_valid_base_speed(cluster):
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(cluster=cluster)
  sync.update(cp, 0, cs)
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 75, 75)


def test_capnp_float32_rounding_does_not_drop_the_declared_145_kph_boundary():
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(145, cluster=145)
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = True
  result = sync.update(cp, 0, cs)
  assert_speed(result, 145, 145)
  assert result[0] <= 145


class OfflineButtonReader:
  is_repeat = False

  def __init__(self):
    self.action = None

  def read(self, allowed=True):
    action, self.action = self.action, None
    return action if allowed else None


class SubMaster(dict):
  """가상 활성 입력과 정상 서비스 메타데이터를 메모리에서만 제공한다."""
  def __init__(self, cs=None, *, speed=250, source="road", enabled=True):
    event = log.Event.new_message()
    event.init("carrotMan")
    event.carrotMan.desiredSpeed = speed
    event.carrotMan.desiredSource = source
    model = log.ModelDataV2()
    times = np.asarray(ModelConstants.T_IDXS)
    velocity = np.minimum(30.0, 21.5 + .8 * times)
    velocity[0] = 21.0
    prior = np.concatenate(([velocity[0]], velocity[:-1]))
    position = np.cumsum(np.diff(times, prepend=0.) * (velocity + prior) * .5)
    for field in ("position", "velocity", "acceleration", "orientationRate"):
      vector = getattr(model, field)
      vector.x = position.tolist() if field == "position" else velocity.tolist() if field == "velocity" else [0.] * len(times)
      vector.y = vector.z = [0.] * len(times)
      vector.t = times.tolist()
    model.timestampEof = 100_000_000_000
    model.frameId = 1
    super().__init__(carControl=car.CarControl(enabled=enabled), carState=cs, carrotMan=event.carrotMan,
                     selfdriveState=log.SelfdriveState(enabled=enabled, personality=1), modelV2=model,
                     radarState=log.RadarState(), livePose=log.LivePose())
    services = (*self, "longitudinalPlan", "drivingModelData")
    self.alive = dict.fromkeys(services, True)
    self.alive["longitudinalPlan"] = self.alive["drivingModelData"] = False
    self.valid = dict.fromkeys(services, True)
    self.seen = dict.fromkeys(services, True)
    self.recv_time = dict.fromkeys(services, 100.0)
    self.logMonoTime = dict.fromkeys(services, 100_000_000_000)
    self.frame = 0

  def all_checks(self, services=None):
    keys = self if services is None else services
    return all(self.seen[key] and self.alive[key] and self.valid[key] for key in keys)


@pytest.fixture(autouse=True)
def isolated_params():
  previous = MemoryParams.values
  MemoryParams.values = repo_defaults()
  MemoryParams.values["SpeedFromPCM"] = "0"
  yield
  MemoryParams.values = previous


def make_helper(CP, cls=cruise.VCruiseCarrot):
  helper = cls(CP)
  helper.bluetooth_commands = OfflineButtonReader()
  helper.v_cruise_kph = 83.0
  helper.cruise_state_available_last = True
  return helper


@pytest.fixture
def full_helper(monkeypatch):
  # 블루투스 수신만 메모리로 격리하고 실제 버튼·순항 상태 계산을 실행한다.
  monkeypatch.setattr(time, "monotonic", lambda: 100.0)
  return make_helper(make_cp())


def enable_observed_cruise(helper, *, speed=75):
  cs = make_cs(speed)
  sm = SubMaster(cs)
  helper.update_v_cruise(cs, sm, True)
  cs.cruiseState.enabled = True
  helper.update_v_cruise(cs, sm, True)
  return cs, sm


def test_actual_cruise_helper_follows_set_adjust_cancel_resume_and_keeps_cp(full_helper):
  before = snapshot(full_helper.CP)
  cs, sm = enable_observed_cruise(full_helper)
  assert full_helper.v_cruise_kph == pytest.approx(75, abs=1e-4)
  assert full_helper.v_cruise_cluster_kph == pytest.approx(76, abs=1e-4)
  for speed, enabled, expected in ((74, True, 74), (74, False, 74), (74, True, 74), (80, True, 80)):
    cs.cruiseState.speed = speed / 3.6
    cs.cruiseState.speedCluster = (speed + 1) / 3.6
    cs.cruiseState.enabled = enabled
    full_helper.update_v_cruise(cs, sm, True)
    assert full_helper.v_cruise_kph == pytest.approx(expected, abs=1e-4)
  assert not cs.buttonEvents
  assert snapshot(full_helper.CP) == before


def test_stable_stock_sample_does_not_overwrite_actual_bluetooth_button_change(full_helper):
  cs, sm = enable_observed_cruise(full_helper)
  cs.cruiseState.speed = 80 / 3.6
  cs.cruiseState.speedCluster = 81 / 3.6
  full_helper.bluetooth_commands.action = "accelCruise"
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == pytest.approx(76, abs=1e-4)
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == pytest.approx(76, abs=1e-4)


def test_existing_pcm_minimum_clip_remains_in_the_actual_cruise_helper(full_helper):
  cs, sm = enable_observed_cruise(full_helper, speed=20)
  assert full_helper.v_cruise_kph == 30
  cs.cruiseState.speed = 255 / 3.6
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == 30


@pytest.mark.parametrize("mode, expected", [(1, 75), (2, 83), (3, 75)])
def test_existing_pcm_mode_speed_selection_remains_unchanged(full_helper, mode, expected):
  full_helper.params.put_int_nonblocking("SpeedFromPCM", mode)
  full_helper.frame = 0
  cs, sm = enable_observed_cruise(full_helper)
  assert full_helper.v_cruise_kph == pytest.approx(expected, abs=1e-4)


@pytest.fixture(scope="module")
def planner_cap_class():
  return CarrotPlanner


def planner_cap(planner_cap_class, sm, base):
  # 메서드 일부를 추출하지 않고 실제 당근 플래너의 전체 update를 실행한다.
  planner = planner_cap_class(signal_assist=SignalAssist(), start_guard=SignalStartGuard(), stop_prepare=SignalStopPrepare())
  return planner.update(sm, base, "acc")


@pytest.mark.parametrize("source, desired", [("vturn", 55), ("route", 45), ("cam", 30)])
def test_mode0_button_sync_preserves_original_curve_map_camera_cap(full_helper, planner_cap_class, source, desired):
  cs, sm = enable_observed_cruise(full_helper)
  sm["carrotMan"].desiredSpeed = desired
  sm["carrotMan"].desiredSource = source
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == pytest.approx(75, abs=1e-4)
  assert planner_cap(planner_cap_class, sm, full_helper.v_cruise_kph) == desired
  full_helper.v_cruise_kph = 60.0
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == 60.0
  assert planner_cap(planner_cap_class, sm, full_helper.v_cruise_kph) == desired


def test_stale_navigation_expires_without_stable_pcm_overwriting_local_base(full_helper, planner_cap_class):
  cs, sm = enable_observed_cruise(full_helper)
  full_helper.v_cruise_kph = 60.0
  sm["carrotMan"].desiredSpeed = 45
  assert planner_cap(planner_cap_class, sm, 60) == 45
  sm.recv_time["carrotMan"] = 98.0
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == 60
  assert planner_cap(planner_cap_class, sm, 60) == 60


def test_observed_disabled_unset_speed_allows_the_first_positive_set():
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(0, cluster=0)
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.speed = 60 / 3.6
  cs.cruiseState.speedCluster = 61 / 3.6
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 60)


def test_mode_switch_into_already_enabled_cruise_does_not_invent_a_set_edge():
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(0, cluster=0)
  assert sync.update(cp, 2, cs) is None
  cs.cruiseState.speed = 60 / 3.6
  cs.cruiseState.speedCluster = 61 / 3.6
  cs.cruiseState.enabled = True
  assert sync.update(cp, 0, cs) is None
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = False
  assert sync.update(cp, 0, cs) is None
  cs.cruiseState.enabled = True
  assert_speed(sync.update(cp, 0, cs), 60)


@pytest.mark.parametrize("speed, enabled, valid, available, mode", [
  (0, True, True, True, 0), (math.nan, False, True, True, 0), (255, False, True, True, 0),
  (0, False, False, True, 0), (0, False, True, False, 0), (0, False, True, True, 2),
])
def test_invalid_or_out_of_scope_sample_cannot_create_a_false_set_edge(speed, enabled, valid, available, mode):
  sync = ToyotaPcmSetSpeedSync()
  cp, cs = make_cp(), make_cs(speed, enabled=enabled)
  cs.canValid = valid
  cs.cruiseState.available = available
  assert sync.update(cp, mode, cs) is None
  cs.canValid = cs.cruiseState.available = True
  cs.cruiseState.speed = 60 / 3.6
  cs.cruiseState.speedCluster = 61 / 3.6
  cs.cruiseState.enabled = True
  assert sync.update(cp, 0, cs) is None


def test_actual_helper_preserves_unset_zero_then_applies_the_first_physical_set(full_helper):
  cp_before = snapshot(full_helper.CP)
  cs = make_cs(0, cluster=0)
  sm = SubMaster(cs)
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == 83
  cs.cruiseState.speed = 60 / 3.6
  cs.cruiseState.speedCluster = 61 / 3.6
  cs.cruiseState.enabled = True
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == pytest.approx(60, abs=1e-4)
  assert full_helper.v_cruise_cluster_kph == pytest.approx(61, abs=1e-4)
  assert not cs.buttonEvents
  assert snapshot(full_helper.CP) == cp_before


def test_actual_helper_does_not_treat_active_zero_as_a_trusted_disabled_sample(full_helper):
  cs = make_cs(0, enabled=True, cluster=0)
  sm = SubMaster(cs)
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == 83
  cs.cruiseState.speed = 60 / 3.6
  cs.cruiseState.speedCluster = 61 / 3.6
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.v_cruise_kph == 83


@pytest.fixture(scope="module")
def original_cruise_class():
  path = "openpilot/selfdrive/car/cruise.py"
  try:
    source = subprocess.check_output(["git", "-C", str(REPO_ROOT), "show", f"{BASE_COMMIT}:{path}"], stderr=subprocess.PIPE)
  except (subprocess.CalledProcessError, OSError) as exc:
    pytest.fail(f"최신 베이스 원형 commit {BASE_COMMIT}의 순항 소스를 읽지 못했습니다: {type(exc).__name__}")
  module = ModuleType("rav4_original_pcm_cruise")
  module.__file__ = str(REPO_ROOT / path)
  exec(compile(source, "<최신 베이스 원형 순항 전체 본문>", "exec"), module.__dict__)
  return module.VCruiseCarrot


@pytest.mark.parametrize("overrides,mode", [
  ({"brand": "honda"}, 0), ({"brand": "hyundai"}, 0),
  ({"carFingerprint": "TOYOTA_RAV4_TSS2"}, 0), ({"carFingerprint": "TOYOTA_RAV4_TSS2_2023"}, 0),
  ({"pcmCruise": False}, 0), ({"openpilotLongitudinalControl": False}, 0),
  ({}, 1), ({}, 2), ({}, 3),
])
def test_out_of_scope_full_helper_matches_latest_original(monkeypatch, original_cruise_class, overrides, mode):
  monkeypatch.setattr(time, "monotonic", lambda: 100.0)
  MemoryParams.values["SpeedFromPCM"] = str(mode)
  CP = make_cp(**overrides)
  saved = snapshot(CP)
  before, after = make_helper(CP, original_cruise_class), make_helper(CP)
  for index, (speed, enabled) in enumerate(((75., False), (75., True), (74., True), (74., False), (74., True), (80., True))):
    cs = make_cs(speed, enabled=enabled)
    sm = SubMaster(cs)
    if index == 2:
      before.bluetooth_commands.action = after.bluetooth_commands.action = "accelCruise"
    before.update_v_cruise(cs, sm, True)
    after.update_v_cruise(cs, sm, True)
    for name in ("v_cruise_kph", "v_cruise_cluster_kph", "_activate_cruise", "_cruise_ready", "_lat_enabled",
                 "_cruise_cancel_state", "_paddle_decel_active", "_soft_hold_active", "button_cnt"):
      assert getattr(before, name) == getattr(after, name), (index, name)
  assert snapshot(CP) == saved


def test_missing_can_valid_cannot_create_a_set_edge():
  sync = ToyotaPcmSetSpeedSync()
  cp = make_cp()
  state = SimpleNamespace(cruiseState=SimpleNamespace(available=True, enabled=False, speed=0.))
  assert sync.update(cp, 0, state) is None
  state.cruiseState.enabled, state.cruiseState.speed = True, 60. / 3.6
  assert sync.update(cp, 0, state) is None


def test_memory_bool_values_preserve_declared_steering_and_driver_setting(full_helper):
  assert not full_helper.disengage_on_accelerator
  full_helper.params.put_bool_nonblocking("DisengageOnAccelerator", True)
  full_helper.frame = 0
  cs, sm = make_cs(), SubMaster(make_cs())
  full_helper.update_v_cruise(cs, sm, True)
  assert full_helper.disengage_on_accelerator
  assert MemoryParams.values["DisengageOnAccelerator"] == "1"
