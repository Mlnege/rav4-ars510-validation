"""각 사례를 독립 프로세스로 실행해 클래스/메모리 IO 상태가 섞이지 않게 한다."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
import json
from pathlib import Path
import subprocess
import sys


WORK=Path(__file__).resolve().parent
cases=[(kind,delay) for kind in ('no_drop','delayed_message','freeze_model','freeze_plan','whole_stall')
                   for delay in (.05,.15,.323,.6,4.)]
cases.extend((kind,delay) for kind,delay in (('cancel',.323),('gas',.323),('brake',.323),
                                          ('model_drop',.3),('actual_sleep',.323)))
results=[]


def run(item):
  kind,delay=item
  folder=WORK/'whole_cases'/(kind+'_'+str(round(delay*1000))+'ms')
  folder.mkdir(parents=True,exist_ok=True)
  command=[sys.executable,str(WORK/'whole_fault_one.py'),'--kind',kind,'--delay',str(delay),'--output',str(folder)]
  with (folder/'execution.log').open('w',encoding='utf-8') as stream:
    process=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
  row={'kind':kind,'delay_s':delay,'returncode':process.returncode,'folder':str(folder.relative_to(WORK))}
  if (folder/'result.json').exists():
    data=json.loads((folder/'result.json').read_text())
    row.update(events=data['events'],first_long_inactive_time=data['first_long_inactive_time'],
               first_soft_disable_time=data['first_soft_disable_time'],source_unchanged=data['source_unchanged'],
               initial=data['initial'],normal_baseline_longActive=data['normal_enable_baseline']['longActive'])
  return row


with ThreadPoolExecutor(max_workers=2) as pool:
  pending=[pool.submit(run,case) for case in cases]
  for future in as_completed(pending):
    row=future.result()
    results.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    (WORK/'whole_cases_progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
report={'recorded_utc':datetime.now(UTC).isoformat(),'cases':results,'process_errors':sum(row['returncode']!=0 for row in results),
        'scope_ko':'호스트 원형 판정 연결. 각 프로세스가 정상 비활성부터 원형 초기화와 정상enable을 먼저 입증한 뒤 fault를 입력. 다른 프로세스/Panda·ECU 물리 및 heartbeat 안전 보증 아님.'}
(WORK/'whole_cases_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(0 if report['process_errors']==0 else 1)
