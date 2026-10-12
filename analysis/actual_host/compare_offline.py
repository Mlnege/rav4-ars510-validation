"""기존 재생 함수를 원형 그대로 실행하되 공개 통계와 메모리 CSV만 사용한다."""
from datetime import datetime,UTC
import hashlib
import json

from whole_io import WORK,SOURCE
from log_io import recorded_schema,inputs,MemoryCsvDirectory


def main():
  # bootstrap는현재프로세스의격리Params를읽기만하고교체하지않는다.
  from tools.ars510_offline import replay as module
  path=SOURCE/'tools/ars510_offline/replay.py'
  before=hashlib.sha256(path.read_bytes()).hexdigest()
  parser,schema=recorded_schema()
  reports=[]
  allowed=('status','points','serialized_liveTracks','pipeline_model_updates','models_with_points',
    'points_present_at_models','radar_lead_selections','baseline_radar_lead_selections','serialized_radarState',
    'nonfinite_required','error_publications','unique_tracks','deleted_track_occurrences',
    'original_radarUnavailable','original_openpilotLongitudinalControl','carParams_unchanged','diagnostics',
    'serialized_error_publications','serialized_can_error_publications','serialized_temp_unavailable_publications')
  for alias,input_path in inputs():
    raw=module.replay(input_path,schema.Event,MemoryCsvDirectory())
    report={'alias':alias,**{key:raw[key] for key in allowed if key in raw}}
    reports.append(report)
    print(json.dumps({'alias':alias,'status':raw['status'],'points':raw['points'],
      'records':raw.get('diagnostics',{}).get('records',0),'radar_leads':raw.get('radar_lead_selections',0)},ensure_ascii=False),flush=True)
  after=hashlib.sha256(path.read_bytes()).hexdigest()
  result={'recorded_utc':datetime.now(UTC).isoformat(),'replay_source_sha_before':before,'replay_source_sha_after':after,
    'replay_file_unchanged_during_execution':before==after,'files':reports,
    'point_count':sum(r['points'] for r in reports),'record_count':sum(r.get('diagnostics',{}).get('records',0) for r in reports),
    'crc_failures':sum(r.get('diagnostics',{}).get('crc_failures',0) for r in reports),
    'radar_lead_selections':sum(r.get('radar_lead_selections',0) for r in reports),
    'raw_point_csv_saved':False,'scope_ko':'원형read-only replay/data/decoder/DPath를직접실행. CSV는메모리sink, 실제ID/좌표/절대시각/FW/원본CAN은저장하지않음. 원형historical 오류전파누락버전과현재replay sourceSHA를별도구분.'}
  (WORK/'offline_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
  assert result['point_count']==369 and result['record_count']==2433 and result['crc_failures']==0
  assert result['radar_lead_selections']==175 and before==after


if __name__=='__main__':main()
