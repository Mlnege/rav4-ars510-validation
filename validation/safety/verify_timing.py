"""실제 C RX 시간·해제·재활성화와 PCS 전달의 독립 오프라인 검사."""

import argparse
import json
from pathlib import Path

from verify_compiled import Probe, accel_payload, pcm, quiet_c_stdout, toyota_payload, wheels


def seed_received_state(p, now):
  p.lib.set_timer(now)
  accepted = [
    p.packet('rx', 0xaa, wheels(20.0)),
    p.packet('rx', 0x260, toyota_payload(0x260, bytes(8))),
    p.packet('rx', 0x226, bytes(8)),
    p.packet('rx', 0x1d2, pcm()),
  ]
  if accepted != [1, 1, 1, 1]:
    raise RuntimeError('필수 RX 데이터가 실제 C 검사를 통과하지 못했습니다')


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('library', type=Path)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  p = Probe(args.library)
  rows = []
  def check(name, actual, expected):
    rows.append({'name': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})

  with quiet_c_stdout():
    for base in (0, 123456, 0xfffffe00):
      for elapsed in (0, 29999, 30000, 999999, 1000000, 1000001, 2000000):
        p.reset()
        seed_received_state(p, base)
        check(f'{base}/{elapsed}/initial_enabled', p.lib.get_controls_allowed(), True)
        p.lib.set_timer((base + elapsed) & 0xffffffff)
        p.lib.safety_tick_current_safety_config()
        expected = elapsed <= 1000000
        check(f'{base}/{elapsed}/controls', p.lib.get_controls_allowed(), expected)
        check(f'{base}/{elapsed}/tx', p.packet('tx', 0x343, accel_payload(-1000)), int(expected))
        check(f'{base}/{elapsed}/state_after_tx', p.lib.get_controls_allowed(), expected)

    p.reset()
    seed_received_state(p, 100000)
    p.lib.set_timer(99999)
    p.lib.safety_tick_current_safety_config()
    check('backward_hardware_time/disengage', p.lib.get_controls_allowed(), False)
    check('backward_hardware_time/tx', p.packet('tx', 0x343, accel_payload(-1000)), 0)

    # 송신을 반복해도 끊긴 RX의 제어 권한은 회복되지 않는다.
    p.reset()
    seed_received_state(p, 0)
    p.lib.set_timer(2000000)
    p.lib.safety_tick_current_safety_config()
    for i in range(200):
      check(f'timeout_tx_repeat/{i}', p.packet('tx', 0x343, accel_payload(-1000)), 0)
    check('timeout_tx_repeat/controls', p.lib.get_controls_allowed(), False)

    # 실제 PCM off→on 수신에 의해서만 다시 허용된다.
    p.packet('rx', 0x1d2, pcm(engaged=False))
    seed_received_state(p, 2000100)
    check('fresh_pcm_off_on/reengage', p.lib.get_controls_allowed(), True)
    check('fresh_pcm_off_on/tx', p.packet('tx', 0x343, accel_payload(-1000)), 1)

    # PCS의 기존 전달 정책과 relay 차단을 실제 packet 입력으로 확인한다.
    for stock in (False, True):
      for active in (False, True):
        p.reset(stock=stock, allowed=active)
        check(f'pcs_passthrough/{stock}/{active}', p.packet('fwd', 0x283, bytes(7), 2), 0)
        p.lib.set_relay_malfunction(True)
        check(f'pcs_relay_block/{stock}/{active}', p.packet('fwd', 0x283, bytes(7), 2), -1)

  failures = [row for row in rows if not row['passed']]
  result = {'cases': len(rows), 'failures': len(failures), 'failed_cases': failures, 'all_passed': not failures}
  args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps({k: v for k, v in result.items() if k != 'failed_cases'}, ensure_ascii=False))
  raise SystemExit(0 if result['all_passed'] else 1)


if __name__ == '__main__':
  main()
