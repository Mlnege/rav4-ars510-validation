"""버스트 보조의 의도적 중단을 완료 결과와 구분해 기록한다."""
import csv
from datetime import UTC, datetime
import json
from pathlib import Path

folder = Path(__file__).resolve().parent/'realtime_can_final_35min'
launch = json.loads((folder/'launch_snapshot.json').read_text(encoding='utf-8'))
progress = json.loads((folder/'progress.json').read_text(encoding='utf-8'))
counts = {}
for name in ('plan.csv', 'can_control.csv'):
  with (folder/name).open(encoding='utf-8') as stream:
    reader = csv.DictReader(stream)
    columns = reader.fieldnames
    counts[name] = sum(all(row.get(key) is not None for key in columns) for row in reader)
result = {'status': 'intentionally_interrupted', 'started_utc': launch['started_utc'],
          'recorded_utc': datetime.now(UTC).isoformat(), 'completed_35_minutes': False,
          'reason': 'burst_control_replaced_by_clock_only_actual_10ms_wait_wrapper',
          'last_recorded_progress': progress, 'complete_csv_rows': counts,
          'included_in_final_gate': False, 'combined_with_final_run': False}
(folder/'interruption.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
