"""소켓과 설정 저장소만 격리한 원형 신호 회귀 검사를 실행한다."""
from pathlib import Path
import argparse
import contextlib
import json
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'native_sim'))
from offline_io import prepare

prepare(solver_overlay=True)
import pytest

parser = argparse.ArgumentParser()
parser.add_argument('--original-fixtures', action='store_true')
parser.add_argument('--head-tracking', action='store_true')
args = parser.parse_args()
name = 'legacy_original_fixtures' if args.original_fixtures else 'legacy_head_tracking' if args.head_tracking else 'legacy_regression'
output = WORK / 'signal_validation' / name
output.mkdir(exist_ok=True)
tests = [
  'openpilot/selfdrive/carrot/tests/test_signal_assist.py',
  'openpilot/selfdrive/carrot/tests/test_signal_assist_runtime.py',
  'openpilot/selfdrive/carrot/tests/test_signal_start_guard.py',
  'openpilot/selfdrive/carrot/tests/test_signal_stop_prepare.py',
  'openpilot/selfdrive/carrot/tests/test_signal_red_priority.py',
  'openpilot/selfdrive/carrot/tests/test_signal_mode.py',
  'openpilot/selfdrive/carrot/tests/test_signal_display.py',
  'openpilot/selfdrive/modeld/tests/test_signal_tracking_shadow.py',
]
if args.original_fixtures:
  originals = output / 'original_fixtures'
  originals.mkdir(exist_ok=True)
  for index, name in enumerate(tests):
    if name.endswith(('test_signal_start_guard.py', 'test_signal_tracking_shadow.py')):
      original = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=WORK / 'carrotpilot',
                                capture_output=True, text=True, encoding='utf-8', check=True).stdout
      target = originals / Path(name).name
      target.write_text(original, encoding='utf-8')
      tests[index] = str(target)
if args.head_tracking:
  from openpilot.selfdrive.modeld import signal_tracking_shadow as worker
  name = 'openpilot/selfdrive/modeld/signal_tracking_shadow.py'
  original = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=WORK / 'carrotpilot',
                            capture_output=True, text=True, encoding='utf-8', check=True).stdout
  # 기준 소스는 이 검사 프로세스에서만 불러오고 작업 파일은 바꾸지 않는다.
  exec(compile(original, 'HEAD:' + name, 'exec'), worker.__dict__)
  tests = ['openpilot/selfdrive/modeld/tests/test_signal_tracking_shadow.py']
started = time.perf_counter()
with (output / 'stdout.txt').open('w', encoding='utf-8') as stdout, (output / 'stderr.txt').open('w', encoding='utf-8') as stderr:
  with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
    result = pytest.main(['-q', '--noconftest', '-p', 'no:cacheprovider', '-c', str(WORK / 'signal_validation' / 'pytest.ini'),
                          '--rootdir=tools/ars510_validation/signal',
                          '--basetemp=' + str(output / 'pytest_temp'), *tests])
summary = {'exit_code': int(result), 'wall_seconds': time.perf_counter() - started,
           'scope': 'original_existing_tests_with_io_only_bootstrap', 'tests': tests}
(output / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print((output / 'stdout.txt').read_text(encoding='utf-8'))
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(result)
