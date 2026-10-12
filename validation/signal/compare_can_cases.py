"""수정 전후 실제 CAN 계산의 공통 필드와 정규 송신 타이밍을 비교한다."""
import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
before, after = BASE/'native_signal_can', BASE/'native_signal_can_fixed'
cases = ['moving_red_prepare', 'moving_mode0_red', 'moving_mode1_red', 'moving_stale_red',
         'moving_model_stop', 'moving_can_fault', 'stopped_green_keeps_model_stop']
report = {}
for case in cases:
  details = {}
  for kind in ('plan', 'can_control'):
    with (before/(case+'_'+kind+'.csv')).open(encoding='utf-8') as source:
      old = list(csv.DictReader(source))
    with (after/(case+'_'+kind+'.csv')).open(encoding='utf-8') as source:
      new = list(csv.DictReader(source))
    mismatches = sum(any(row.get(key) != other.get(key) for key in row) for row, other in zip(old, new, strict=True))
    maximum_numeric_delta = {}
    for row, other in zip(old, new, strict=True):
      for key in row:
        try:
          delta = abs(float(row[key])-float(other[key]))
        except (ValueError, TypeError):
          continue
        if delta:
          maximum_numeric_delta[key] = max(delta, maximum_numeric_delta.get(key, 0.))
    details[kind] = {'rows': len(old), 'changed_rows_in_common_fields': mismatches, 'maximum_numeric_deltas': maximum_numeric_delta}
  report[case] = details
result = {'cases': report, 'all_unchanged': all(item['changed_rows_in_common_fields'] == 0
          for detail in report.values() for item in detail.values()),
          'new_diagnostics_excluded_from_comparison': True, 'physical_measurement': False}
(after/'before_after_comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(int(not result['all_unchanged']))
