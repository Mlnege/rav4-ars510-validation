"""실제 MPC·플래너의 RAV4 명령 범위와 감속 전달 회귀.

메모리 설정·정상 입력·가상 활성 상태에서 계산만 검사한다. 빈 선행차와 합성
모델 경로는 시험 입력이며 전체 호스트 권한·실물 인식·물리 제동 검증이 아니다.
CARROT_VALIDATION_BUILD에는 현재 소스와 같은 Python 본문 및 실제 native
MPC 바이너리를 포함한 별도의 동결 경로를 지정해야 한다.
"""
from pathlib import Path
import os
import subprocess
import sys
import time
from types import ModuleType

import pytest

if os.environ.get('CARROT_OFFLINE_VALIDATION') != '1':
  pytest.skip('격리된 새 검사 프로세스에서 CARROT_OFFLINE_VALIDATION=1이 필요합니다', allow_module_level=True)

import numpy as np

from tools.ars510_validation.native_runtime import MemoryParams, prepare, repo_defaults  # noqa: TID251

mpc_name = 'openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc'
if mpc_name not in sys.modules:
  prepare()
else:
  # IO만 준비된 수집 순서와 이미 다른 solver가 로드된 상태를 구분한다.
  if getattr(sys.modules.get('openpilot.common.params'), 'Params', None) is not MemoryParams:
    raise RuntimeError('이미 로드된 MPC의 설정 입출력 출처를 확인할 수 없습니다')
  build = os.environ.get('CARROT_VALIDATION_BUILD')
  if not build:
    raise RuntimeError('이미 로드된 MPC의 동결 경로를 지정해야 합니다')
  frozen = Path(build).resolve() / 'long_mpc.py'
  original = Path(__file__).resolve().parents[4] / 'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py'
  if (Path(sys.modules[mpc_name].__file__).resolve() != frozen or
      frozen.read_bytes().replace(b'\r\n', b'\n') != original.read_bytes().replace(b'\r\n', b'\n')):
    raise RuntimeError('이미 로드된 MPC의 경로·동결 본문이 검사할 소스와 다릅니다')

from opendbc.car import gen_empty_fingerprint
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.values import CAR
from openpilot.cereal import car, log
from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
from openpilot.selfdrive.carrot.signal_assist import SignalAssist
from openpilot.selfdrive.carrot.signal_start_guard import SignalStartGuard
from openpilot.selfdrive.carrot.signal_stop_prepare import SignalStopPrepare
from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import ACCEL_MIN, LongitudinalMpc
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.selfdrive.modeld.constants import ModelConstants


REPO_ROOT = Path(__file__).resolve().parents[4]
BASE_COMMIT = '2ec25da3c10e369eaf4ad0313fde3280e5a8b06e'


@pytest.fixture(autouse=True)
def isolated_params():
  previous = MemoryParams.values
  MemoryParams.values = repo_defaults()
  yield
  MemoryParams.values = previous


def vehicle_params(platform=CAR.TOYOTA_RAV4_TSS2_2022, direct=True):
  return CarInterface.get_params(platform, gen_empty_fingerprint(), [], direct, False, False)


def original_module(path, name):
  try:
    source = subprocess.check_output(['git', '-C', str(REPO_ROOT), 'show', f'{BASE_COMMIT}:{path}'], stderr=subprocess.PIPE)
  except (subprocess.CalledProcessError, OSError) as exc:
    pytest.fail(f'최신 베이스 원형 commit {BASE_COMMIT}의 {path}를 읽지 못했습니다: {type(exc).__name__}')
  module = ModuleType(name)
  module.__file__ = str(REPO_ROOT / path)
  exec(compile(source, f'<최신 베이스 원형 {path}>', 'exec'), module.__dict__)
  return module


@pytest.fixture(scope='module')
def original_planner_class():
  mpc = original_module('openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py', 'rav4_original_mpc')
  planner = original_module('openpilot/selfdrive/controls/lib/longitudinal_planner.py', 'rav4_original_planner')
  # 두 원형 전체 본문을 동일한 실제 solver에 연결한다. 계산 함수를 대체하지 않는다.
  planner.LongitudinalMpc = mpc.LongitudinalMpc
  return planner.LongitudinalPlanner


class PlannerInputs(dict):
  """소켓 없이 실제 스키마 값과 선언한 정상 입력 메타데이터를 제공한다."""
  def __init__(self):
    super().__init__()
    services = ('carState', 'controlsState', 'selfdriveState', 'carControl', 'radarState', 'modelV2', 'carrotMan', 'livePose')
    self.seen = dict.fromkeys(services, True)
    self.alive = dict.fromkeys(services, True)
    self.valid = dict.fromkeys(services, True)
    self.recv_time = dict.fromkeys(services, 100.0)
    self.logMonoTime = dict.fromkeys(services, 100_000_000_000)
    self.frame = 0

  def all_checks(self, services=None):
    selected = self.valid if services is None else services
    return all(self.seen[key] and self.alive[key] and self.valid[key] for key in selected)

  def refresh(self, now, *, speed=15.0, force=False, blended=False, desired_accel=0.0):
    times = np.asarray(ModelConstants.T_IDXS)
    model_velocity = np.minimum(25.0, speed + .5 + .8 * times)
    model_velocity[0] = speed
    previous_velocity = np.concatenate(([model_velocity[0]], model_velocity[:-1]))
    positions = np.cumsum(np.diff(times, prepend=0.0) * (model_velocity + previous_velocity) * .5)
    model = log.ModelDataV2()
    for field in ('position', 'velocity', 'acceleration', 'orientationRate'):
      vector = getattr(model, field)
      vector.x = positions.tolist() if field == 'position' else model_velocity.tolist() if field == 'velocity' else [0.] * len(times)
      vector.y = vector.z = [0.] * len(times)
      vector.t = times.tolist()
    model.action.desiredAcceleration = desired_accel
    model.action.desiredVelocity = 25.0
    model.meta.disengagePredictions.gasPressProbs = [1.] * 6
    model.timestampEof = int(now * 1e9)
    model.frameId = self.frame + 1
    self.update(
      carState=car.CarState(vEgo=speed, vEgoRaw=speed, vEgoCluster=speed, aEgo=0., canValid=True,
                           gearShifter='drive', vCruise=90., vCruiseCluster=90., vCluRatio=1.,
                           cruiseState={'enabled': True, 'available': True, 'speed': 25.}),
      controlsState=log.ControlsState(longControlState=LongCtrlState.pid, forceDecel=force),
      selfdriveState=log.SelfdriveState(enabled=True, active=True, experimentalMode=blended, personality=1),
      carControl=car.CarControl(enabled=True, longActive=True, orientationNED=[0., 0., 0.]),
      radarState=log.RadarState(), modelV2=model, livePose=log.LivePose(),
      carrotMan=log.Event.new_message().init('carrotMan'),
    )
    self['carrotMan'].desiredSpeed = 250
    self['carrotMan'].activeCarrot = 2
    self['carrotMan'].desiredSource = 'road'
    for key in self.recv_time:
      self.recv_time[key], self.logMonoTime[key] = now, int(now * 1e9)
    self.frame += 1


def planner_series(monkeypatch, CP, *, force=False, blended=False, cls=LongitudinalPlanner, desired_accel=0.0):
  MemoryParams.values = repo_defaults()
  carrot = CarrotPlanner(signal_assist=SignalAssist(), start_guard=SignalStartGuard(), stop_prepare=SignalStopPrepare())
  planner = cls(CP, init_v=15.0)
  inputs = PlannerInputs()
  targets, solutions = [], []
  for index in range(40):
    now = 100.0 + index * .05
    monkeypatch.setattr(time, 'monotonic', lambda now=now: now)
    inputs.refresh(now, force=force and index >= 20, blended=blended, desired_accel=desired_accel)
    planner.update(inputs, carrot)
    assert planner.mpc.solution_status == 0
    assert type(planner.mpc.solver).__name__ == 'AcadosOcpSolverCython'
    assert np.isfinite(planner.output_a_target) and np.all(np.isfinite(planner.mpc.a_solution))
    targets.append(planner.output_a_target)
    solutions.append(planner.mpc.a_solution.copy())
  return planner, np.asarray(targets), np.asarray(solutions)


@pytest.mark.parametrize('bad', [
  (), (0., 2.), (-3.5, 0.), (1., 2.), (-3.5, -1.), (-4.1, 2.), (-3.5, 2.6),
  (np.nan, 2.), (-3.5, np.inf), (-np.inf, 2.), (False, 2.), (-3.5, True),
  (-3.5, np.bool_(True)), ('숫자가 아님', 2.), (-3.5,), (-3.5, 2., 3.), 0,
])
def test_invalid_envelope_is_rejected_before_solver_setup(bad):
  with pytest.raises(ValueError):
    LongitudinalMpc(actuator_accel_limits=bad)


def test_source_envelope_and_existing_cruise_preference():
  CP = vehicle_params()
  limits = CarInterface.get_pid_accel_limits(CP, 15., 25.)
  planner = LongitudinalPlanner(CP)
  assert limits == (-3.5, 2.)
  assert planner.actuator_accel_limits == limits and planner.mpc.minimum_accel == limits[0]
  planner.mpc.set_accel_limits(-2., 2.5)
  assert planner.mpc.cruise_min_a == -2. and planner.mpc.max_a == limits[1]
  planner.mpc.set_cur_state(25., 0.)
  lead = log.RadarState.LeadData(status=True, dRel=1., vLead=0., vLeadK=0.)
  trajectory, _ = planner.mpc.process_lead(lead)
  assert trajectory[0, 0] == pytest.approx(25.**2 / (-4. * limits[0]))


@pytest.mark.parametrize('bad', [None, (-4.5, 2.), (-3.5, 0.), (np.nan, 2.)])
def test_invalid_public_interface_result_is_not_guessed(monkeypatch, bad):
  CP = vehicle_params()
  monkeypatch.setattr(CarInterface, 'get_pid_accel_limits', lambda *args: bad)
  with pytest.raises(ValueError):
    LongitudinalPlanner(CP)


def test_default_mpc_limits_are_preserved():
  mpc = LongitudinalMpc()
  assert mpc.actuator_accel_limits is None and mpc.minimum_accel == ACCEL_MIN
  mpc.set_accel_limits(-2., 3.)
  assert mpc.cruise_min_a == -2. and mpc.max_a == 3.


def test_rav4_host_request_reaches_actual_mpc_and_braking_target(monkeypatch):
  CP = vehicle_params()
  before = CP.to_dict()
  _, normal, _ = planner_series(monkeypatch, CP)
  planner, requested, _ = planner_series(monkeypatch, CP, force=True)
  np.testing.assert_array_equal(normal[:20], requested[:20])
  assert np.all(normal[20:] > 0.)
  assert np.any(requested[21:] < -.1) and requested[-1] < 0.
  assert planner.mpc.source == 'cruise'
  assert np.all(requested >= planner.actuator_accel_limits[0])
  assert np.all(requested <= planner.actuator_accel_limits[1])
  assert CP.to_dict() == before


def test_rav4_blended_host_request_retains_actual_braking_target(monkeypatch):
  CP = vehicle_params()
  _, normal, _ = planner_series(monkeypatch, CP, blended=True, desired_accel=.8)
  planner, requested, _ = planner_series(monkeypatch, CP, force=True, blended=True, desired_accel=.8)
  np.testing.assert_array_equal(normal[:20], requested[:20])
  assert np.all(normal[20:] > 0.)
  assert planner.mpc.mode == 'blended' and np.any(requested[21:] < -.1)
  assert requested[-1] < 0.
  assert np.all(requested >= planner.actuator_accel_limits[0])
  assert np.all(requested <= planner.actuator_accel_limits[1])


def test_blended_final_model_target_is_bounded_after_all_output_steps(monkeypatch):
  planner, targets, _ = planner_series(monkeypatch, vehicle_params(), blended=True, desired_accel=-7.)
  assert planner.mpc.mode == 'blended'
  assert np.all(targets == planner.actuator_accel_limits[0])


@pytest.mark.parametrize('platform,direct', [
  (CAR.TOYOTA_RAV4_TSS2_2022, False), (CAR.TOYOTA_RAV4_TSS2_2023, True),
  (CAR.TOYOTA_RAV4_TSS2, True), (CAR.TOYOTA_CHR_TSS2, True),
])
@pytest.mark.parametrize('blended', [False, True])
@pytest.mark.parametrize('force', [False, True])
def test_other_vehicle_and_stock_paths_match_latest_original(monkeypatch, original_planner_class, platform, direct, blended, force):
  CP = vehicle_params(platform, direct)
  before = CP.to_dict()
  _, expected, expected_solution = planner_series(monkeypatch, CP, force=force, blended=blended, cls=original_planner_class)
  planner, actual, actual_solution = planner_series(monkeypatch, CP, force=force, blended=blended)
  assert planner.actuator_accel_limits is None and planner.mpc.minimum_accel == ACCEL_MIN
  np.testing.assert_array_equal(actual, expected)
  np.testing.assert_array_equal(actual_solution, expected_solution)
  assert CP.to_dict() == before
