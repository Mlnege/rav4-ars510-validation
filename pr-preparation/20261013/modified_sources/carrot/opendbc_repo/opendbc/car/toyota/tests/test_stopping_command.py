"""RAV4의 정지 요청·실제 메모리 CAN과 타차 원형 보존 회귀.

운영 설정과 소켓을 격리하고 실제 제어기·PID·DBC를 계산한다. 가상 활성 입력을
전체 호스트 권한·실차 제동 증거로 확대하지 않는다. CAN은 메모리에서만 생성한다.
"""
from pathlib import Path
import os
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

if os.environ.get('CARROT_OFFLINE_VALIDATION') != '1':
  pytest.skip('격리된 새 검사 프로세스에서 CARROT_OFFLINE_VALIDATION=1이 필요합니다', allow_module_level=True)

from tools.ars510_validation.native_runtime import MemoryParams, prepare, repo_defaults

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
  original = Path(__file__).resolve().parents[5] / 'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py'
  if (Path(sys.modules[mpc_name].__file__).resolve() != frozen or
      frozen.read_bytes().replace(b'\r\n', b'\n') != original.read_bytes().replace(b'\r\n', b'\n')):
    raise RuntimeError('이미 로드된 MPC의 경로·동결 본문이 검사할 소스와 다릅니다')

from opendbc.can import CANParser
from opendbc.car import Bus, gen_empty_fingerprint
from opendbc.car.common.pid import PIDController
from opendbc.car.structs import CarControl, CarState
from opendbc.car.toyota.carcontroller import CarController
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.toyotacan import toyota_checksum
from opendbc.car.toyota.values import CAR, DBC
from opendbc.dbc.generator.generator import create_dbc
from openpilot.cereal import log
from openpilot.selfdrive.controls.lib.longcontrol import LongControl, LongCtrlState


REPO_ROOT = Path(__file__).resolve().parents[5]
BASE_COMMIT = '2ec25da3c10e369eaf4ad0313fde3280e5a8b06e'


@pytest.fixture(autouse=True)
def isolated_params():
  previous = MemoryParams.values
  MemoryParams.values = repo_defaults()
  yield
  MemoryParams.values = previous


@pytest.fixture(scope='module')
def toyota_dbc(tmp_path_factory):
  folder = tmp_path_factory.mktemp('toyota_stopping_dbc')
  create_dbc(str(REPO_ROOT / 'opendbc_repo/opendbc/dbc/generator/toyota'), 'toyota_nodsu_pt.dbc', str(folder))
  return folder / 'toyota_nodsu_pt_generated.dbc'


@pytest.fixture(scope='module')
def original_controller_class():
  path = 'opendbc_repo/opendbc/car/toyota/carcontroller.py'
  try:
    source = subprocess.check_output(['git', '-C', str(REPO_ROOT), 'show', f'{BASE_COMMIT}:{path}'], stderr=subprocess.PIPE)
  except (subprocess.CalledProcessError, OSError) as exc:
    pytest.fail(f'최신 베이스 원형 commit {BASE_COMMIT}의 Toyota 제어기를 읽지 못했습니다: {type(exc).__name__}')
  module = ModuleType('rav4_original_toyota_controller')
  module.__file__ = str(REPO_ROOT / path)
  exec(compile(source, '<최신 베이스 원형 Toyota CarController>', 'exec'), module.__dict__)
  return module.CarController


def vehicle_params(platform=CAR.TOYOTA_RAV4_TSS2_2022, direct=True):
  return CarInterface.get_params(platform, gen_empty_fingerprint(), [], direct, False, False)


def controller(dbc, CP=None, cls=CarController):
  CP = vehicle_params() if CP is None else CP
  names = DBC[CP.carFingerprint].copy()
  names[Bus.pt] = str(dbc)
  result = cls(names, CP)
  result.prev_accel, result.long_pid.i = .623, .12
  return result


def inputs(request=-.003, *, mode='stopping', active=True, pitch=0., acceleration=0., speed=0.):
  cc = CarControl(enabled=active, longActive=active, latActive=False, orientationNED=[0., pitch, 0.])
  cc.actuators.accel, cc.actuators.longControlState = request, mode
  cc.hudControl.leadDistanceBars = 2
  out = CarState(vEgo=speed, vEgoRaw=speed, aEgo=acceleration, standstill=speed == 0., canValid=True,
                 gearShifter='drive', cruiseState={'enabled': active, 'available': True})
  cs = SimpleNamespace(out=out, gvc=acceleration, acc_type=1, pcm_acc_status=8, pcm_follow_distance=2, lkas_hud={})
  return cc, cs


def step(control, cc, cs, index=0):
  _, can = control.update(cc.as_reader(), cs, 10_000_000_000 + index * 10_000_000)
  packets = [(address, data, bus) for address, data, bus in can if address == 0x343 and bus == 0]
  return can, packets


def decoded(dbc, packets, index=0):
  parser = CANParser(str(dbc), [('ACC_CONTROL', 33)], 0)
  assert parser.update([(10_000_000_000 + index * 10_000_000, packets)]) == {0x343}
  for address, data, bus in packets:
    assert bus == 0 and len(data) == 8
    assert toyota_checksum(address, None, bytearray(data)) == data[-1]
  return float(parser.vl['ACC_CONTROL']['ACCEL_CMD'])


def test_real_longcontrol_stop_transition_reaches_first_regular_can(toyota_dbc, original_controller_class):
  CP = vehicle_params()
  before = CP.to_dict()
  control = controller(toyota_dbc, CP)
  cc, cs = inputs()
  long_control = LongControl(CP)
  plan = log.LongitudinalPlan(shouldStop=True, aTarget=0., vTargetNow=0., jTargetNow=0.)
  command, _, _ = long_control.update(True, cs.out, plan, CarInterface.get_pid_accel_limits(CP, 0., 0.), 0., log.RadarState())
  assert long_control.long_control_state == LongCtrlState.stopping and command < 0.
  # 실제 제어 출력과 같은 수치를 스키마가 받는 Python float로 직렬화한다.
  cc.actuators.accel, cc.actuators.longControlState = float(command), long_control.long_control_state
  baseline = controller(toyota_dbc, CP, original_controller_class)
  assert decoded(toyota_dbc, step(baseline, cc, cs)[1]) > 0.
  assert decoded(toyota_dbc, step(control, cc, cs)[1]) <= 0.
  assert control.prev_accel <= 0. and control.long_pid.i <= 0.
  assert CP.to_dict() == before


@pytest.mark.parametrize('pitch,acceleration,speed', [(-.15, -.5, 0.), (.15, -.5, .5), (0., .3, .5), (0., -1., 2.)])
@pytest.mark.parametrize('kp,kd', [(0., 0.), (.5, 0.), (2., .2)])
def test_pitch_measurement_and_pid_cannot_emit_positive_stopping_command(toyota_dbc, pitch, acceleration, speed, kp, kd):
  control = controller(toyota_dbc)
  limits = CarInterface.get_pid_accel_limits(control.CP, speed, 0.)
  control.long_pid = PIDController(kp, .25, k_f=1., k_d=kd, pos_limit=limits[1], neg_limit=limits[0], rate=1/.03)
  control.long_pid.i = .3
  cc, cs = inputs(pitch=pitch, acceleration=acceleration, speed=speed)
  assert decoded(toyota_dbc, step(control, cc, cs)[1]) <= 0.
  assert control.long_pid.i <= 0. and control.long_pid.control <= 0.


def test_negative_integral_is_preserved_without_crossing_zero(toyota_dbc):
  control = controller(toyota_dbc)
  control.prev_accel, control.long_pid.i = -.5, -.2
  cc, cs = inputs()
  step(control, cc, cs)
  assert control.long_pid.i == pytest.approx(-.1991)
  control.long_pid.i = -.0005
  control.frame = 3
  assert decoded(toyota_dbc, step(control, cc, cs, 3)[1], 3) <= 0.
  assert control.long_pid.i <= 0.


def test_regular_cadence_preserves_old_command_between_sends(toyota_dbc):
  control = controller(toyota_dbc)
  control.frame, control.accel = 1, .623
  cc, cs = inputs()
  assert not step(control, cc, cs, 1)[1] and control.accel == .623
  assert not step(control, cc, cs, 2)[1] and control.accel == .623
  created = []
  for index in range(3, 13):
    packets = step(control, cc, cs, index)[1]
    if packets:
      created.append(index)
      assert decoded(toyota_dbc, packets, index) <= 0.
  assert created == [3, 6, 9, 12]


def test_real_longcontrol_pid_restart_accepts_positive_request(toyota_dbc):
  control = controller(toyota_dbc)
  cc, cs = inputs()
  long_control = LongControl(control.CP)
  radar = log.RadarState()
  limits = CarInterface.get_pid_accel_limits(control.CP, 0., 0.)
  for index in range(10):
    plan = log.LongitudinalPlan(shouldStop=index == 0, aTarget=.5 if index else 0., vTargetNow=1., jTargetNow=0.)
    command, _, _ = long_control.update(True, cs.out, plan, limits, 0., radar)
    cc.actuators.accel, cc.actuators.longControlState = float(command), long_control.long_control_state
    packets = step(control, cc, cs, index)[1]
    if index == 0:
      assert long_control.long_control_state == LongCtrlState.stopping
      assert decoded(toyota_dbc, packets, index) <= 0.
    elif packets:
      assert long_control.long_control_state == LongCtrlState.pid
      assert decoded(toyota_dbc, packets, index) > 0.


@pytest.mark.parametrize('platform,direct,mode,accel_request,active', [
  (CAR.TOYOTA_RAV4_TSS2_2023, True, 'stopping', -.003, True),
  (CAR.TOYOTA_CHR_TSS2, True, 'stopping', -.003, True),
  (CAR.TOYOTA_RAV4_TSS2, True, 'stopping', -.003, True),
  (CAR.TOYOTA_RAV4_TSS2_2022, False, 'stopping', -.003, True),
  (CAR.TOYOTA_RAV4_TSS2_2022, True, 'stopping', -.003, False),
  (CAR.TOYOTA_RAV4_TSS2_2022, True, 'stopping', .1, True),
  (CAR.TOYOTA_RAV4_TSS2_2022, True, 'starting', .3, True),
  (CAR.TOYOTA_RAV4_TSS2_2022, True, 'pid', -.003, True),
])
def test_non_target_paths_match_original_can_arrays(toyota_dbc, original_controller_class, platform, direct, mode, accel_request, active):
  CP = vehicle_params(platform, direct)
  saved = CP.to_dict()
  before = controller(toyota_dbc, CP, original_controller_class)
  after = controller(toyota_dbc, CP)
  cc, cs = inputs(accel_request, mode=mode, active=active)
  for index in range(30):
    assert step(before, cc, cs, index)[0] == step(after, cc, cs, index)[0]
  assert CP.to_dict() == saved
