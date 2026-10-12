"""부호·영점 오프셋·비활성 코드가 다른 실제 제조사 설정의 원형 C 검증."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path

from verify_compiled import Probe, quiet_c_stdout


# 고정 소스 safety_*.h의 값. 제한이나 비활성 코드를 넓혀 통과시키지 않는다.
LIMITS = {
  'toyota': (-3500, 2000, 0),
  'hyundai': (-400, 250, 0),
  'honda_rivian': (-350, 200, 0),
  'tesla': (288, 425, 375),
  'ford': (4231, 5641, 5128),
  'volkswagen_mqb_pq_meb': (-3500, 2000, 3010),
}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('library', type=Path)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  p = Probe(args.library)
  p.lib.probe_helper_accel_encoded.argtypes = [ctypes.c_int] * 4
  result = {}
  with quiet_c_stdout():
    for brand, (minimum, maximum, inactive) in LIMITS.items():
      count = invalid = mutated = 0
      for allowed in (False, True):
        for gas in (False, True):
          p.reset(allowed=allowed, gas=gas)
          for unsigned in range(65536):
            raw = unsigned if unsigned < 32768 else unsigned - 65536
            p.lib.set_controls_allowed(allowed)
            expected_violation = not ((allowed and not gas and minimum <= raw <= maximum) or raw == inactive)
            actual = p.lib.probe_helper_accel_encoded(raw, minimum, maximum, inactive)
            invalid += bool(actual) != expected_violation
            mutated += p.lib.get_controls_allowed() != allowed
            count += 1
      result[brand] = {'cases': count, 'limit_violation_mismatches': invalid, 'controls_mutations': mutated}
  summary = {'profiles': result, 'all_passed': all(not x['limit_violation_mismatches'] and not x['controls_mutations'] for x in result.values()),
             'library_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest()}
  args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps(summary, ensure_ascii=False))
  raise SystemExit(0 if summary['all_passed'] else 1)


if __name__ == '__main__':
  main()
