"""실제 Toyota CarController의 메모리 CAN 결과를 실제 C 안전 판정에 연결한다.

CarInterface.init, 차량 연결, CAN 송신, Params 저장 또는 ECU 비활성화는 없다.
"""

import argparse
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from verify_compiled import Probe, pcm, quiet_c_stdout, toyota_payload, wheels


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('library', type=Path)
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--repo', type=Path)
  args = parser.parse_args()
  root = (args.repo or Path(__file__).resolve().parents[1] / 'carrotpilot').resolve()
  sys.path[:0] = [str(root), str(root / 'opendbc_repo')]
  from tools.ars510_offline.bootstrap import prepare
  prepare()
  import opendbc
  import opendbc.can.dbc
  dbc_folder = Path(__file__).resolve().parent / 'dbcs'
  if not (dbc_folder / 'toyota_nodsu_pt_generated.dbc').is_file():
    raise RuntimeError('먼저 원형 DBC 생성기를 사용하는 run_upstream_tests.py를 실행하세요')
  opendbc.DBC_PATH = opendbc.can.dbc.DBC_PATH = str(dbc_folder)
  from opendbc.car import Bus, structs
  import opendbc.car.interfaces as interfaces
  controller_module = importlib.import_module('opendbc.car.toyota.carcontroller')
  from opendbc.car.toyota.interface import CarInterface
  from opendbc.car.toyota.values import CAR, DBC

  class MemoryConfiguration:
    # 운영 Params를 읽거나 쓰지 않는다. 알고리즘은 원본이고 시험 입력은 기본값이다.
    def get_bool(self, key):
      if key not in ('NNFF', 'DisableMinSteerSpeed'):
        raise RuntimeError('예상하지 않은 설정 접근: ' + key)
      return False

    def get_int(self, key):
      if key not in ('CustomSteerMax', 'CustomSteerDeltaUp', 'CustomSteerDeltaDown'):
        raise RuntimeError('예상하지 않은 설정 접근: ' + key)
      return 0

  original_interface_params = interfaces.Params
  original_controller_params = controller_module.Params
  interfaces.Params = controller_module.Params = MemoryConfiguration
  try:
    candidate = CAR.TOYOTA_RAV4_TSS2_2022
    cp = CarInterface.get_params(candidate, {0: {}, 1: {}, 2: {}}, [], True, False, False)
    original_cp = cp.to_dict()
    stock_cp = CarInterface.get_params(candidate, {0: {}, 1: {}, 2: {}}, [], False, False, False)
    source = {'platform': str(candidate), 'flags': int(cp.flags), 'radarUnavailable': bool(cp.radarUnavailable),
              'openpilotLongitudinalControl': bool(cp.openpilotLongitudinalControl),
              'longitudinalActuatorDelay_s': float(cp.longitudinalActuatorDelay),
              'safetyParam': int(cp.safetyConfigs[0].safetyParam),
              'factory_alpha_long': True, 'car_interface_init_called': False,
              'params_scope': 'explicit_memory_read_defaults_only'}

    def generate(request):
      controller = controller_module.CarController(DBC[candidate], cp)
      out = structs.CarState(vEgo=20., vEgoRaw=20., aEgo=0., standstill=False,
                             gearShifter='drive', cruiseState={'available': True, 'enabled': True})
      state = SimpleNamespace(out=out, pcm_acc_status=8, pcm_follow_distance=3,
                              acc_type=1, gvc=0., lkas_hud={})
      command = structs.CarControl(enabled=True, longActive=True, latActive=False,
                                   actuators={'accel': request, 'longControlState': 'pid'},
                                   hudControl={'leadVisible': True, 'leadDistanceBars': 1})
      # 실제 card 입력과 같이 reader를 전달한다. 구현의 as_builder 호출을 대체하지 않는다.
      _, messages = controller.update(command.as_reader(), state, 1_000_000_000)
      acceleration = [m for m in messages if m[0] == 0x343]
      if len(acceleration) != 1:
        raise RuntimeError('원형 CarController가 0x343 하나를 생성하지 않았습니다')
      address, payload, bus = acceleration[0]
      if len(payload) != 8 or bus != 0:
        raise RuntimeError('실제 DBC 출력의 형식이 다릅니다')
      checksum = (len(payload) + (address >> 8) + (address & 255) + sum(payload[:-1])) & 255
      if payload[-1] != checksum:
        raise RuntimeError('실제 Toyota 체크섬이 다릅니다')
      return (address, bytes(payload), bus), [m[0] for m in messages]

    p = Probe(args.library)
    results = []
    for requested in (-1.0, 1.0):
      message, addresses = generate(requested)
      address, data, bus = message
      raw_accel = int.from_bytes(data[:2], 'big', signed=True)
      if raw_accel == 0 or (raw_accel > 0) != (requested > 0):
        raise RuntimeError('원형 제어기의 출력 부호가 요청과 다릅니다')
      for case in ('active_fresh', 'inactive', 'gas', 'brake', 'timeout', 'stock_long'):
        parameter = int(stock_cp.safetyConfigs[0].safetyParam) if case == 'stock_long' else int(cp.safetyConfigs[0].safetyParam)
        assert p.lib.set_safety_hooks(2, parameter) == 0
        p.lib.init_tests()
        if case != 'inactive':
          p.packet('rx', 0xaa, wheels(20.0))
          p.packet('rx', 0x260, toyota_payload(0x260, bytes(8)))
          p.packet('rx', 0x226, bytes(8))
          p.packet('rx', 0x1d2, pcm())
          if not p.lib.get_controls_allowed():
            raise RuntimeError('실제 정상 RX에서 제어 허용이 만들어지지 않았습니다')
        if case == 'gas':
          p.packet('rx', 0x1d2, pcm(gas=True))
        elif case == 'brake':
          p.packet('rx', 0x226, bytes([0, 0, 0, 0, 32, 0, 0, 0]))
        elif case == 'timeout':
          p.lib.set_timer(2_000_000)
          p.lib.safety_tick_current_safety_config()
        before = bool(p.lib.get_controls_allowed())
        actual = p.packet('tx', address, data, bus)
        after = bool(p.lib.get_controls_allowed())
        expected = int(case == 'active_fresh')
        results.append({'requested_accel_mps2': requested, 'generated_accel_raw_signed': raw_accel,
                        'case': case, 'controls_before': before, 'controls_after': after,
                        'expected_tx': expected, 'actual_tx': actual,
                        'passed': actual == expected and before == after,
                        'generated_message_addresses': [hex(a) for a in addresses]})
    if cp.to_dict() != original_cp:
      raise RuntimeError('CarParams가 변경되었습니다')
  finally:
    interfaces.Params = original_interface_params
    controller_module.Params = original_controller_params

  summary = {'source': source, 'cases': len(results), 'failures': sum(not r['passed'] for r in results),
             'carparams_unchanged': True, 'rows': results,
             'actual_vehicle_transmission': False,
             'pcs_notice': 'alpha-long 원형 CP는 UDS/PCS off 경로를 포함한다. 메모리에서 생성한 0x411/0x750은 송신하거나 PCS 보존 증거로 취급하지 않았다.'}
  args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, ensure_ascii=False))
  raise SystemExit(0 if not summary['failures'] else 1)


if __name__ == '__main__':
  with quiet_c_stdout():
    try:
      main()
    except SystemExit as result:
      status = result.code
  print('verify_generated_toyota_can_exit=' + str(status))
  raise SystemExit(status)
