"""차량별 기존 TX 검사가 거절한 조향이 실제 C 송신 판정에서 차단되는지 확인."""

import argparse
import json
from pathlib import Path

from verify_compiled import Probe, quiet_c_stdout


def payload(kind, torque):
  if kind == 'honda':
    return (torque & 65535).to_bytes(2, 'big') + bytes(3)
  if kind == 'hyundai':
    return (((torque + 1024) << 16) | (1 << 27)).to_bytes(4, 'little') + bytes(4)
  data = bytearray(16)
  raw = torque + 1024
  data[5] = (raw & 127) << 1
  data[6] = ((raw >> 7) & 15) | 16
  return bytes(data)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('library', type=Path)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  p = Probe(args.library)
  rows = []
  cases = [('honda', 1, 0xe4, 5), ('hyundai', 8, 0x340, 8), ('hyundai_canfd', 28, 0x12a, 16)]
  with quiet_c_stdout():
    for name, mode, address, length in cases:
      for allowed, torque, expected in ((False, 1, 0), (False, 0, 1), (True, 1, 1)):
        assert p.lib.set_safety_hooks(mode, 0) == 0
        p.lib.init_tests()
        p.lib.set_controls_allowed(allowed)
        actual = p.packet('tx', address, payload(name, torque))
        rows.append({'brand': name, 'case': 'authority', 'controls_allowed': allowed, 'torque_code': torque,
                     'address': hex(address), 'length': length, 'expected': expected, 'actual': actual,
                     'passed': expected == actual})
      if name != 'honda':
        assert p.lib.set_safety_hooks(mode, 0) == 0
        p.lib.init_tests()
        p.lib.set_controls_allowed(True)
        p.lib.set_desired_torque_last(600)
        p.lib.set_rt_torque_last(600)
        actual = p.packet('tx', address, payload(name, 600))
        rows.append({'brand': name, 'case': 'above_existing_512_limit', 'torque_code': 600,
                     'expected': 0, 'actual': actual, 'passed': actual == 0})
  result = {'cases': len(rows), 'failures': sum(not r['passed'] for r in rows), 'rows': rows,
            'note': '합성 메모리 패킷으로 원형 C 판정만 호출한다. 실제 ECU 수용·물리 조향 증거가 아니다.'}
  args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps(result, ensure_ascii=False))
  raise SystemExit(0 if not result['failures'] else 1)


if __name__ == '__main__':
  main()
