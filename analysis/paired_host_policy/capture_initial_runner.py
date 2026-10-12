"""관측·stdout 보호만 보강하기 전의 최초 실행 코드 사본을 지문으로 확인한다."""
import hashlib
import json
from pathlib import Path


WORK=Path(__file__).resolve().parent


def main():
  current=(WORK/'run.py').read_text()
  initial=current.replace('import math\nimport os\n','import math\n')
  start=initial.index('@contextlib.contextmanager\ndef discard_native_stderr():')
  end=initial.index('class RecordedCsBus',start)
  initial=initial[:start]+initial[end:]
  start=initial.index("  sources=['openpilot/selfdrive/carrot/radar/can_batch.py'")
  end=initial.index('  try:\n',start)
  initial=initial[:start]+initial[end:]
  initial=initial.replace('policy_module.quiet_c_stdout(),discard_native_stderr(),','policy_module.quiet_c_stdout(),')
  start=initial.index("  result['source_hashes_before']=source_before")
  end=initial.index("  result['runner_sha256']",start)
  initial=initial[:start]+initial[end:]
  initial=initial.replace(" or not result['source_unchanged'] else 0)"," else 0)")
  first=json.loads((WORK/'log_a_first/results.json').read_text())
  actual=hashlib.sha256(initial.encode()).hexdigest()
  same=actual==first['runner_sha256']
  if same:(WORK/'first_a_executed_source.py').write_text(initial,encoding='utf-8')
  report={'first_runner_sha256':first['runner_sha256'],'reconstructed_sha256':actual,'same':same,
          'scope_ko':'최초 실행 뒤 추가한 source 지문/하위 stderr 보호만 되돌려 당시 SHA와 대조. 새 계산 실행이나 최초 결과 수정은 하지 않는다.'}
  (WORK/'initial_source_capture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(report,ensure_ascii=False))
  raise SystemExit(1 if not same else 0)


if __name__=='__main__':main()
