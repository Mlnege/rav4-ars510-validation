"""같은 원형 C 수신 재생 함수를 한 입력·한 위상으로 독립 실행한다."""
import argparse
from datetime import datetime, UTC
import json

import capnp

from run import ROOT, WORK, SOURCE, LIBRARY, INPUTS, load_events, dataset, replay, sha, quiet_c_stdout


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--alias', choices=[x[0] for x in INPUTS], required=True)
  parser.add_argument('--phase-us', type=int, choices=[0, 500000], default=0)
  args = parser.parse_args()
  folder = ROOT / 'work/input/carrot_schemas'
  schema_parser = capnp.SchemaParser()
  schema = schema_parser.load(str(folder / 'log.capnp'), imports=[str(folder), str(folder / 'include')])
  sources = ['tools/ars510_offline/replay.py', 'panda/board/main.c', 'panda/python/__init__.py',
             'openpilot/selfdrive/pandad/panda.h', 'openpilot/selfdrive/pandad/panda.cc',
             'opendbc_repo/opendbc/safety/safety.h',
             'opendbc_repo/opendbc/safety/safety/safety_toyota.h',
             'opendbc_repo/opendbc/safety/tests/libsafety/safety_helpers.h']
  before = {p: sha(SOURCE / p) for p in sources}
  library_before = sha(LIBRARY)
  with quiet_c_stdout():
    rows, profile = dataset(ROOT / 'work/input' / dict(INPUTS)[args.alias], schema, load_events())
    observed = replay(args.alias, rows, profile, args.phase_us)
  after = {p: sha(SOURCE / p) for p in sources}
  report = {'generated_utc': datetime.now(UTC).isoformat(), 'result': observed,
            'source_hashes_before': before, 'source_hashes_after': after,
            'source_unchanged': before == after,
            'library_sha256_before': library_before, 'library_sha256_after': sha(LIBRARY),
            'library_unchanged': library_before == sha(LIBRARY),
            'engine_sha256': sha(WORK / 'run.py'),
            'scope_ko': '동일 함수를 새 C 메모리 상태에서 직접 실행한 단일 진단. 기존 전체 결과를 덮지 않는다.'}
  (WORK / 'single_case_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps({'alias': args.alias, 'phase_us': args.phase_us,
                    'failures': observed.get('failures'), 'carState_c_samples': observed.get('carState_c_samples'),
                    'source_unchanged': report['source_unchanged'], 'library_unchanged': report['library_unchanged']}, ensure_ascii=False))
  raise SystemExit(1 if observed.get('failures') or not report['source_unchanged'] or not report['library_unchanged'] else 0)


if __name__ == '__main__':
  main()
