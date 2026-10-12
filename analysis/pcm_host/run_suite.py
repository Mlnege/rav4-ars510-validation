"""새 도구만 실행하고 매 case 원형 입력 경계 및 실패 결과를 보존한다."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys

WORK=Path(__file__).resolve().parent
KINDS=['speed_down','map40','curve','combined','invalid_cap','stale_cap','cancel_restart',
       'button_cancel_restart','gas_restart','brake_restart','main_off_restart']

def run(kind):
  folder=WORK/'cases'/kind
  folder.mkdir(parents=True,exist_ok=True)
  with (folder/'execution.log').open('w',encoding='utf-8') as stream:
    p=subprocess.run([sys.executable,str(WORK/'run_case.py'),kind],stdout=stream,stderr=subprocess.STDOUT)
  r={'kind':kind,'returncode':p.returncode}
  if (folder/'result.json').exists():
    body=json.loads((folder/'result.json').read_text())
    r.update(checks=body['checks'],failures=body['failures'],events=body['events'],
      min_control_accel=body['min_control_accel'],first=body['first'],last=body['last'])
  return r

results=[]
with ThreadPoolExecutor(max_workers=2) as pool:
  for future in as_completed([pool.submit(run,kind) for kind in KINDS]):
    row=future.result()
    results.append(row)
    (WORK/'suite_progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in row.items() if key not in ('first','last','checks')},ensure_ascii=False),flush=True)
(WORK/'suite_summary.json').write_text(json.dumps({'cases':results,'process_errors':sum(r['returncode']!=0 for r in results)},ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(1 if any(r['returncode']!=0 for r in results) else 0)
