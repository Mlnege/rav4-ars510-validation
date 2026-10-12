"""기본 조건은 보존하고 사용자 요청 설정의 메모리 profile을 별도 실행한다."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,UTC
import json
from pathlib import Path
import subprocess
import sys

WORK=Path(__file__).resolve().parent
cases=[('button_only_cancel',.323,'default'),('button_only_cancel',.323,'user_requested'),
       ('cancel',.323,'user_requested'),('gas',.323,'user_requested'),('brake',.323,'user_requested'),
       ('no_drop',4.,'user_requested'),('delayed_message',.323,'user_requested'),
       ('freeze_plan',4.,'user_requested'),('whole_stall',4.,'user_requested')]


def run(item):
  kind,delay,profile=item
  folder=WORK/'whole_user_profile'/(profile+'_'+kind+'_'+str(round(delay*1000))+'ms')
  folder.mkdir(parents=True,exist_ok=True)
  with (folder/'execution.log').open('w',encoding='utf-8') as stream:
    result=subprocess.run([sys.executable,str(WORK/'whole_fault_one.py'),'--kind',kind,'--delay',str(delay),
                           '--profile',profile,'--output',str(folder)],stdout=stream,stderr=subprocess.STDOUT)
  row={'kind':kind,'delay_s':delay,'profile':profile,'returncode':result.returncode}
  if (folder/'result.json').exists():
    r=json.loads((folder/'result.json').read_text())
    row.update(configuration=r['configuration'],events=r['events'],fault_first=r['fault_first'],
               fault_second=r['fault_second'],first_long_inactive_time=r['first_long_inactive_time'],
               source_unchanged=r['source_unchanged'])
  return row


results=[]
with ThreadPoolExecutor(max_workers=2) as pool:
  for future in as_completed([pool.submit(run,item) for item in cases]):
    row=future.result()
    results.append(row)
    print(json.dumps({k:v for k,v in row.items() if k not in ('fault_first','fault_second')},ensure_ascii=False),flush=True)
    (WORK/'whole_user_profile_progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
report={'recorded_utc':datetime.now(UTC).isoformat(),'cases':results,'process_errors':sum(x['returncode']!=0 for x in results),
        'scope_ko':'SpeedFromPCM0/LongActuatorDelay20/AlphaLongitudinalEnabledTrue 메모리 설정 profile. 실제 사용자 운영 설정 또는 FW준비를 검증한 결과가 아님. CP flags force나 생산 코드 변경 없음.'}
(WORK/'whole_user_profile_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(0 if report['process_errors']==0 else 1)
