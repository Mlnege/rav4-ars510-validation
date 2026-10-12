"""최초 CAN 연결 실패의 원본 CSV에서 수치 증거만 읽는다."""
import csv
import json
from pathlib import Path

folder = Path(__file__).resolve().parent/'native_signal_can'
with (folder/'stopped_red_green_go_can_control.csv').open(encoding='utf-8') as stream:
  rows = list(csv.DictReader(stream))
held = [row for row in rows if row['start_hold'] == 'True']
positive = [row for row in held if float(row['decoded_acc_command']) > 0]
negative = next(row for row in held if float(row['decoded_acc_command']) < 0)
result = {'source': 'original_failed_stopped_red_green_go_can_control.csv',
          'positive_held_control_ticks': len(positive),
          'positive_new_acc_messages_while_held': sum(row['acc_control_created'] == 'True' for row in positive),
          'first_held_s': float(held[0]['time'])-100.,
          'first_nonpositive_decoded_command_after_hold_s': float(negative['time'])-100.,
          'maximum_positive_command_while_held_mps2': max(float(row['decoded_acc_command']) for row in positive),
          'maximum_model_speed_while_held_mps': max(float(row['plant_speed']) for row in held),
          'distance_during_held_in_explicit_point_mass_model_m': sum(float(row['plant_speed'])*.01 for row in held),
          'physical_measurement': False}
(folder/'failed_hold_metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
