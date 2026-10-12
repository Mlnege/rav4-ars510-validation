"""원본 epoch를 유지한 wire 변환의 주요 NS 필드를 별도 읽기 검사한다."""
import sys
sys.dont_write_bytecode=True
from collections import Counter
import json

from whole_io import WORK
from log_io import inputs,events,recorded_schema
from paired_stream import wire_event


def main():
  parser,schema=recorded_schema()
  reports=[]
  for alias,path in inputs():
    counts=Counter()
    mismatches=Counter()
    with events(path,schema.Event) as stream:
      for old in stream:
        kind=old.which()
        if kind not in ('carState','modelV2','livePose','roadCameraState','wideRoadCameraState','driverCameraState'):continue
        new=wire_event(old)
        before,after=getattr(old,kind),getattr(new,kind)
        counts['event_headers_checked']+=1
        mismatches['event_header']+=int(old.logMonoTime!=new.logMonoTime)
        for name in ('timestamp','timestampEof','timestampSof'):
          if name in before.schema.fields:
            counts[kind+'/'+name]+=1
            mismatches[kind+'/'+name]+=int(name not in after.schema.fields or int(getattr(before,name))!=int(getattr(after,name)))
        if kind=='carState':
          for name in ('firstCanMonoTime','lastCanMonoTime','receiveMonoTime','canPacketCount'):
            counts['radarInput/'+name]+=1
            mismatches['radarInput/'+name]+=int(getattr(before.radarInput,name)!=getattr(after.radarInput,name))
    reports.append({'alias':alias,'counts':dict(counts),'mismatches':dict(mismatches),
                    'failed_count':sum(mismatches.values())})
  result={'files':reports,'failed_count':sum(r['failed_count'] for r in reports),
    'scope_ko':'주요 camera/model/pose NS와 CS nested radarInput/header의 같은 값 직접 대조. 전체 schema ordinal·장치 clock 동등성·물리 수신 지연을 증명하지 않는다. 값·원본 절대시각은 출력하지 않는다.'}
  (WORK/'wire_time_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'failed_count':result['failed_count'],'event_headers':sum(r['counts'].get('event_headers_checked',0) for r in reports)},ensure_ascii=False))
  raise SystemExit(1 if result['failed_count'] else 0)


if __name__=='__main__':main()
