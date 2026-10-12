"""기존 DBC의 PCM 두 메시지와 저장된 carState를 시간·범주로 대조한다.

원본 payload·개인 식별자·절대시간은 저장하지 않는다. 누락/체크섬 실패의
기본값0을 유효한 원본0으로 취급하지 않으며 CAN 송신은 하지 않는다.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import zstandard

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT/'work/native_sim'))
from offline_io import prepare

prepare()
from opendbc.can import CANParser, native
from opendbc.car.toyota.toyotacan import toyota_checksum
from openpilot.cereal import log

MESSAGES = {0x1d2: ('PCM_CRUISE', 'CRUISE_ACTIVE', 'enabled'),
            0x1d3: ('PCM_CRUISE_2', 'MAIN_ON', 'available')}


def age_category(age_ms):
  if age_ms < 0.:
    return 'future_rejected'
  if age_ms <= 20.:
    return '0_to_20ms'
  if age_ms <= 50.:
    return '20_to_50ms'
  if age_ms <= 100.:
    return '50_to_100ms'
  if age_ms <= 500.:
    return '100_to_500ms'
  return 'over_500ms'


def observe(path, label):
  events = []
  with zstandard.ZstdDecompressor().stream_reader(path.read_bytes()) as stream:
    data = stream.read()
  for event in log.Event.read_multiple_bytes(data):
    kind = event.which()
    if kind == 'can':
      for frame in event.can:
        if frame.address in MESSAGES and frame.src in (0, 1, 2):
          events.append((int(event.logMonoTime), 0, (int(frame.address), bytes(frame.dat), int(frame.src))))
    elif kind == 'carState':
      events.append((int(event.logMonoTime), 1,
                     (bool(event.carState.cruiseState.enabled), bool(event.carState.cruiseState.available))))
  events.sort(key=lambda item: (item[0], item[1]))
  dbc = TASK_ROOT/'work/native_sim/dbc/toyota_nodsu_pt_generated.dbc'
  parsers = {bus: CANParser(str(dbc), [(msg[0], float('nan')) for msg in MESSAGES.values()], bus) for bus in (0, 1, 2)}
  latest = {}
  frame_counts, signal_counts, comparisons, freshness = (Counter() for _ in range(4))
  for timestamp, kind, payload in events:
    if kind == 0:
      address, data, bus = payload
      name, signal, _ = MESSAGES[address]
      key = f'bus{bus}:{name}'
      frame_counts[key+':received'] += 1
      if len(data) != 8:
        frame_counts[key+':bad_dlc'] += 1
        continue
      if toyota_checksum(address, None, bytearray(data)) != data[-1]:
        frame_counts[key+':bad_checksum'] += 1
        continue
      accepted = parsers[bus].update([(timestamp, [(address, data, bus)])])
      if address not in accepted:
        frame_counts[key+':parser_rejected'] += 1
        continue
      value = bool(parsers[bus].vl[name][signal])
      latest[(bus, address)] = (timestamp, value)
      frame_counts[key+':accepted'] += 1
      signal_counts[key+':'+signal+':'+str(value)] += 1
    else:
      enabled, available = payload
      for bus in (0, 1, 2):
        for address, (name, _, field) in MESSAGES.items():
          key = f'bus{bus}:{name}'
          if (bus, address) not in latest:
            comparisons[key+':no_valid_observation'] += 1
            continue
          observed_time, value = latest[(bus, address)]
          age_ms = (timestamp-observed_time)*1e-6
          freshness[key+':'+age_category(age_ms)] += 1
          if age_ms > 100.:
            comparisons[key+':older_than_100ms'] += 1
            continue
          current = enabled if field == 'enabled' else available
          comparisons[key+':'+('match' if value == current else 'mismatch')] += 1
  return {'anonymous_log': label, 'frame_category_counts': dict(frame_counts), 'signal_category_counts': dict(signal_counts),
          'same_time_carState_category_counts': dict(comparisons), 'relative_freshness_counts': dict(freshness),
          'CAN_raw_backend': native.BACKEND,
          'fresh_comparison_limit_ms': 100., 'real_vehicle_tx_count': 0,
          'interpretation': '유효 원본만 비교한다. 100ms는 진단용 경계이며 실제 제어 조건을 바꾸지 않는다'}


def main():
  results = []
  for index, filename in enumerate(('rlog.zst', 'rlog_06.zst', 'rlog_11.zst', 'rlog_12.zst'), 1):
    result = observe(TASK_ROOT/'work/input'/filename, f'log_{index}')
    results.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
  Path(__file__).with_name('pcm_bus_observations.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
  main()
