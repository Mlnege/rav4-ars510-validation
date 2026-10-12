"""원형/수정 C 안전 라이브러리만 실행하는 로컬 검사. 차량 송신 경로가 없다."""

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path


class Probe:
  def __init__(self, path):
    self.lib = ctypes.CDLL(str(path.resolve()))
    self.lib.set_safety_hooks.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
    self.lib.set_controls_allowed.argtypes = [ctypes.c_bool]
    self.lib.set_gas_pressed_prev.argtypes = [ctypes.c_bool]
    self.lib.set_relay_malfunction.argtypes = [ctypes.c_bool]
    self.lib.set_alternative_experience.argtypes = [ctypes.c_int]
    self.lib.set_timer.argtypes = [ctypes.c_uint32]
    self.lib.get_controls_allowed.restype = ctypes.c_bool
    self.lib.get_longitudinal_allowed.restype = ctypes.c_bool
    for name in ('probe_tx', 'probe_rx', 'probe_fwd'):
      getattr(self.lib, name).argtypes = [ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint8,
                                        ctypes.POINTER(ctypes.c_uint8)]
    self.lib.probe_helper_accel.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]

  def reset(self, *, stock=False, allowed=False, gas=False, relay=False, alternative=0):
    if self.lib.set_safety_hooks(2, 73 | (512 if stock else 0)) != 0:
      raise RuntimeError('Toyota safety hook을 찾지 못했습니다')
    self.lib.init_tests()
    self.lib.set_controls_allowed(allowed)
    self.lib.set_gas_pressed_prev(gas)
    self.lib.set_relay_malfunction(relay)
    self.lib.set_alternative_experience(alternative)

  def packet(self, direction, address, data, bus=0):
    payload = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    return getattr(self.lib, 'probe_' + direction)(address, bus, len(data), payload)


def accel_payload(raw, *, cancel=False):
  return (raw & 65535).to_bytes(2, 'big') + bytes([0, int(cancel), 0, 0, 0, 0])


def toyota_payload(address, data):
  value = bytearray(data)
  value[-1] = (len(value) + (address >> 8) + (address & 255) + sum(value[:-1])) & 255
  return bytes(value)


def pcm(*, engaged=True, gas=False):
  return toyota_payload(0x1d2, bytes([(32 if engaged else 0) | (0 if gas else 16), 0, 0, 0, 0, 0, 0, 0]))


def wheels(speed):
  return round((speed * 3.6 + 67.67) * 100).to_bytes(2, 'big') * 4


@contextlib.contextmanager
def quiet_c_stdout():
  # C의 진단 print만 폐기하며 검사 결과·사실·오류는 JSON으로 남긴다.
  libc = ctypes.CDLL(None)
  libc.fflush(None)
  saved = os.dup(1)
  with open(os.devnull, 'wb') as stream:
    os.dup2(stream.fileno(), 1)
    try:
      yield
    finally:
      libc.fflush(None)
      os.dup2(saved, 1)
      os.close(saved)


def verify(probe, exhaustive=False):
  cases = []
  def check(name, actual, expected):
    cases.append({'name': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})

  for raw in (-32768, -3501, -3500, -1, 0, 1, 2000, 2001, 32767):
    for allowed in (False, True):
      for gas in (False, True):
        probe.reset(allowed=allowed, gas=gas)
        expected = int((allowed and not gas and -3500 <= raw <= 2000) or raw == 0)
        prefix = f'accel={raw},allowed={allowed},gas={gas}'
        check(prefix + ',tx', probe.packet('tx', 0x343, accel_payload(raw)), expected)
        check(prefix + ',state', probe.lib.get_controls_allowed(), allowed)

  for stock in (False, True):
    for allowed in (False, True):
      for raw in (-1000, 0, 1000):
        for cancel in (False, True):
          probe.reset(stock=stock, allowed=allowed)
          expected = int((cancel and raw == 0) if stock else (allowed or raw == 0))
          name = f'stock={stock},allowed={allowed},accel={raw},cancel={cancel}'
          check(name + ',tx', probe.packet('tx', 0x343, accel_payload(raw, cancel=cancel)), expected)
          check(name + ',state', probe.lib.get_controls_allowed(), allowed)

  invalid = [(0x343, 1, accel_payload(1000)), (0x343, 0, accel_payload(1000)[:7]),
             (0x343, 0, accel_payload(1000) + bytes(4)), (0x7ff, 0, accel_payload(1000))]
  for address, bus, data in invalid:
    probe.reset()
    name = f'invalid_addr={address},bus={bus},length={len(data)}'
    check(name + ',tx', probe.packet('tx', address, data, bus), 0)
    check(name + ',state', probe.lib.get_controls_allowed(), False)
  probe.reset(relay=True)
  check('relay,tx', probe.packet('tx', 0x343, accel_payload(1000)), 0)
  check('relay,state', probe.lib.get_controls_allowed(), False)

  # 정식 수신 검사에 통과한 PCM/브레이크/차속 프레임으로 해제를 재현한다.
  for event in ('brake', 'gas', 'cancel', 'invalid_checksum', 'rx_timeout'):
    probe.reset()
    check(event + ',wheels_rx', probe.packet('rx', 0xaa, wheels(20.0)), 1)
    check(event + ',pcm_engage_rx', probe.packet('rx', 0x1d2, pcm()), 1)
    check(event + ',engaged', probe.lib.get_controls_allowed(), True)
    if event == 'brake':
      check(event + ',event_rx', probe.packet('rx', 0x226, bytes([0, 0, 0, 0, 32, 0, 0, 0])), 1)
    elif event == 'gas':
      check(event + ',event_rx', probe.packet('rx', 0x1d2, pcm(gas=True)), 1)
    elif event == 'cancel':
      check(event + ',event_rx', probe.packet('rx', 0x1d2, pcm(engaged=False)), 1)
    elif event == 'invalid_checksum':
      corrupt = bytearray(pcm()); corrupt[-1] ^= 1
      check(event + ',event_rx', probe.packet('rx', 0x1d2, bytes(corrupt)), 0)
    else:
      probe.lib.set_timer(2_000_000)
      probe.lib.safety_tick_current_safety_config()
    check(event + ',disengaged_before_tx', probe.lib.get_controls_allowed(), False)
    check(event + ',tx', probe.packet('tx', 0x343, accel_payload(1000)), 0)
    check(event + ',still_disengaged', probe.lib.get_controls_allowed(), False)

  probe.reset(alternative=1)
  probe.packet('rx', 0xaa, wheels(20.0)); probe.packet('rx', 0x1d2, pcm())
  probe.packet('rx', 0x1d2, pcm(gas=True))
  check('alternative_gas,controls_retained', probe.lib.get_controls_allowed(), True)
  check('alternative_gas,long_allowed', probe.lib.get_longitudinal_allowed(), False)
  check('alternative_gas,tx', probe.packet('tx', 0x343, accel_payload(1000)), 0)

  # 통신 경로 차이는 제어 허용 상태와 별개이며 순정 ACC 유지 경로도 보존한다.
  for stock in (False, True):
    probe.reset(stock=stock)
    check(f'stock={stock},fwd_acc', probe.packet('fwd', 0x343, bytes(8), 2), 0 if stock else -1)
    check(f'stock={stock},fwd_pcs', probe.packet('fwd', 0x283, bytes(7), 2), 0)

  exhaust = {'cases': 0, 'tx_mismatches': 0, 'state_mutations': 0}
  if exhaustive:
    for allowed in (False, True):
      for gas in (False, True):
        probe.reset(allowed=allowed, gas=gas)
        for unsigned in range(65536):
          raw = unsigned if unsigned < 32768 else unsigned - 65536
          probe.lib.set_controls_allowed(allowed)
          expected = int((allowed and not gas and -3500 <= raw <= 2000) or raw == 0)
          tx = probe.packet('tx', 0x343, accel_payload(raw))
          exhaust['cases'] += 1
          exhaust['tx_mismatches'] += tx != expected
          exhaust['state_mutations'] += probe.lib.get_controls_allowed() != allowed
  failed = [case for case in cases if not case['passed']]
  return {'named_cases': len(cases), 'named_failures': len(failed), 'failed_cases': failed,
          'exhaustive_signed16': exhaust,
          'all_passed': not failed and not exhaust['tx_mismatches'] and not exhaust['state_mutations']}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('library', type=Path)
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--exhaustive', action='store_true')
  args = parser.parse_args()
  with quiet_c_stdout():
    result = verify(Probe(args.library), args.exhaustive)
  result['library_sha256'] = hashlib.sha256(args.library.read_bytes()).hexdigest()
  args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
  print(json.dumps({k: v for k, v in result.items() if k != 'failed_cases'}, ensure_ascii=False))
  raise SystemExit(0 if result['all_passed'] else 1)


if __name__ == '__main__':
  main()
