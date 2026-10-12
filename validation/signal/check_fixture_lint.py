"""수정 테스트의 lint와 원형 HEAD lint를 직접 실행해 기존 문제를 구분한다."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

WORK = Path(__file__).resolve().parents[1]
REPO = WORK / 'carrotpilot'
output = WORK / 'signal_validation' / 'fixture_lint'
output.mkdir(exist_ok=True)
files = ['openpilot/selfdrive/carrot/tests/test_signal_start_guard.py',
         'openpilot/selfdrive/modeld/tests/test_signal_tracking_shadow.py']
originals = []
for name in files:
  source = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=REPO, capture_output=True,
                          text=True, encoding='utf-8', check=True).stdout
  target = output / Path(name).name
  target.write_text(source, encoding='utf-8')
  originals.append(str(target))

def lint(names, label):
  value = subprocess.run([sys.executable, '-m', 'ruff', 'check', '--config', str(REPO/'pyproject.toml'),
                          '--output-format=json', *names], cwd=REPO, capture_output=True, text=True, encoding='utf-8')
  (output/(label+'.stdout.json')).write_text(value.stdout, encoding='utf-8')
  (output/(label+'.stderr.txt')).write_text(value.stderr, encoding='utf-8')
  messages = json.loads(value.stdout)
  return Counter((item['code'], item['message']) for item in messages)

before = lint(originals, 'head')
after = lint(files, 'current')
summary = {'head_total': before.total(), 'current_total': after.total(),
           'new_diagnostics': [{'code': key[0], 'message': key[1], 'count': count} for key, count in (after-before).items()],
           'unchanged_diagnostic_multiset': before == after}
(output/'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(int(bool(after-before)))
