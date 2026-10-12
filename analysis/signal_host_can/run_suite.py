"""독립 프로세스에서 원형 신호/호스트 시간 위상만 비교한다."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import sys

WORK=Path(__file__).resolve().parent
CASES=[('gas',phase,order) for order in ('before','after') for phase in (0,10,20,30,40)]
CASES += [(kind,0,order) for order in ('before','after') for kind in ('red','green','unknown','stale','obs_missing')]
CASES += [(kind,0,'before') for kind in ('bad_provenance','invalid_can','cancel_restart','brake_restart',
                                     'dm_soft','dm_hard','model_freeze','plan_freeze','session_green')]
CASES += [('gas_one_tick',40,'before'),('gas_one_tick',40,'after')]


def run(item):
  kind,phase,order=item
  folder=WORK/'cases'/f'{kind}_{phase}ms_{order}'
  folder.mkdir(parents=True,exist_ok=True)
  with (folder/'execution.log').open('w',encoding='utf-8') as stream:
    p=subprocess.run([sys.executable,str(WORK/'run_case.py'),kind,'--phase-ms',str(phase),'--order',order],
                     stdout=stream,stderr=subprocess.STDOUT)
  row={'kind':kind,'phase_ms':phase,'order':order,'returncode':p.returncode}
  if (folder/'result.json').exists():
    r=json.loads((folder/'result.json').read_text())
    row.update(checks=r['checks'],failures=r['failures'],events=r['events'],can_count=r['can_count'],
      positive_allowed_can_count=r['positive_allowed_can_count'],expected_deny_count=r['expected_deny_count'],
      actual_deny_count=r['actual_deny_count'],camera_lineage=r['camera_lineage'],
      first_positive_control_time=r['first_positive_control']['time'] if r['first_positive_control'] else None,
      first_hold_removed_time=r['first_hold_removed']['time'] if r['first_hold_removed'] else None,
      first_hold_restored_time=r['first_hold_restored_after_gas']['time'] if r['first_hold_restored_after_gas'] else None)
  return row


results=[]
with ThreadPoolExecutor(max_workers=2) as pool:
  for future in as_completed([pool.submit(run,item) for item in CASES]):
    row=future.result()
    results.append(row)
    (WORK/'suite_progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in row.items() if k not in ('checks','events','camera_lineage')},ensure_ascii=False),flush=True)
report={'cases':results,'case_count':len(results),'process_errors':sum(r['returncode']!=0 for r in results)}
(WORK/'suite_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(1 if report['process_errors'] else 0)
