"""원본 로그의 허용된 시각·유효 여부만 읽고 익명 통계로 기록한다.

원본 시각·프레임 번호는 메모리에서 연결에만 사용하며 저장하지 않는다.
영상·위치·차량 식별·경로·설정·예측 배열에는 접근하지 않는다.
소스와 시각 기준이 다른 두 값의 차이를 실제 처리 지연으로 단정하지 않는다.
"""

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

import numpy as np
import zstandard

TASK_ROOT = Path(__file__).resolve().parents[2]
REPO = TASK_ROOT / 'work/carrotpilot'
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'opendbc_repo'))
from openpilot.cereal import car, log

OUTPUT = Path(__file__).resolve().parent
INPUTS = ('rlog.zst', 'rlog_06.zst', 'rlog_11.zst', 'rlog_12.zst')
SERVICES = ('modelV2', 'roadCameraState', 'wideRoadCameraState', 'livePose',
            'longitudinalPlan', 'carControl', 'controlsState', 'selfdriveState')
SOURCE_FILES = (
  'openpilot/cereal/log.capnp', 'opendbc_repo/opendbc/car/car.capnp',
  'openpilot/cereal/messaging/__init__.py', 'openpilot/cereal/messaging/messaging.h',
  'openpilot/common/timing.h', 'openpilot/system/camerad/cameras/spectra.cc',
  'openpilot/system/camerad/cameras/camera_qcom2.cc',
  'openpilot/selfdrive/modeld/modeld.py', 'openpilot/selfdrive/modeld/fill_model_msg.py',
  'openpilot/selfdrive/locationd/locationd.py',
  'openpilot/selfdrive/controls/lib/longitudinal_planner.py',
  'openpilot/selfdrive/controls/controlsd.py',
)


def distribution(values):
  """상대 밀리초의 요약만 반환하고 원본 표본은 버린다."""
  finite = [float(v) for v in values if math.isfinite(v)]
  result = {'count': len(values), 'finite_count': len(finite),
            'nonfinite_count': len(values) - len(finite),
            'negative_count': sum(v < 0 for v in finite),
            'zero_count': sum(v == 0 for v in finite),
            'positive_count': sum(v > 0 for v in finite)}
  if finite:
    result.update({name: round(float(value), 6) for name, value in
                   zip(('p50_ms', 'p95_ms', 'p99_ms', 'max_ms'), np.percentile(finite, (50, 95, 99, 100)), strict=True)})
  else:
    result.update(dict.fromkeys(('p50_ms', 'p95_ms', 'p99_ms', 'max_ms')))
  return result


def delta_ms(later, earlier):
  return (int(later) - int(earlier)) / 1e6


def index_rows(rows, key):
  result = defaultdict(list)
  for row in rows:
    result[key(row)].append(row)
  return result


def short_distribution(values, unit):
  """상대 초기 구간은 개수·99백분위·최대값만 기록한다."""
  finite = [float(v) for v in values if math.isfinite(v)]
  return {'count': len(values), 'nonfinite_count': len(values) - len(finite),
          'p99_' + unit: round(float(np.percentile(finite, 99)), 6) if finite else None,
          'max_' + unit: round(max(finite), 6) if finite else None}


def link_summary(counts, values):
  return {'counts': dict(counts), 'relative_ms': {key: distribution(value) for key, value in values.items()}}


def observe(path, label):
  rows = {name: [] for name in SERVICES}
  event_counts = Counter()
  # 완전 스키마로 읽되 아래 명시한 스칼라 필드 외에는 접근하지 않는다.
  with path.open('rb') as stream, zstandard.ZstdDecompressor().stream_reader(stream) as reader:
    data = reader.read()
  for event in log.Event.read_multiple_bytes(data):
    which = event.which()
    event_counts[which] += 1
    if which not in rows:
      continue
    body = getattr(event, which)
    row = {'header': int(event.logMonoTime), 'valid': bool(event.valid)}
    if which in ('roadCameraState', 'wideRoadCameraState'):
      row.update(fid=int(body.frameId), eof=int(body.timestampEof))
    elif which == 'modelV2':
      row.update(fid=int(body.frameId), eof=int(body.timestampEof), frame_age=int(body.frameAge),
                 frame_drop=float(body.frameDropPerc), execution_time=float(body.modelExecutionTime))
    elif which == 'livePose':
      row.update(timestamp=int(body.timestamp), sensors_ok=bool(body.sensorsOK),
                 inputs_ok=bool(body.inputsOK), posenet_ok=bool(body.posenetOK))
    elif which == 'longitudinalPlan':
      row.update(model=int(body.modelMonoTime), processing_delay=float(body.processingDelay))
    elif which == 'controlsState':
      row.update(plan=int(body.longitudinalPlanMonoTime), model=int(body.lateralPlanMonoTime),
                 long_off=str(body.longControlState) == 'off')
    elif which == 'carControl':
      row.update(enabled=bool(body.enabled), long_active=bool(body.longActive), lat_active=bool(body.latActive))
      if 'longitudinalPlanMonoTime' in car.CarControl.schema.fields:
        row['plan'] = int(body.longitudinalPlanMonoTime)
    elif which == 'selfdriveState':
      row.update(enabled=bool(body.enabled), active=bool(body.active))
    rows[which].append(row)
  del data

  result = {'anonymous_log': label, 'total_event_count': sum(event_counts.values()),
            'service_counts': {name: len(rows[name]) for name in SERVICES},
            'carControl_plan_reference_field_present_in_current_schema': 'longitudinalPlanMonoTime' in car.CarControl.schema.fields,
            'controlsState_exact_modelMonoTime_field_present_in_current_schema': 'modelMonoTime' in log.ControlsState.schema.fields,
            'controlsState_lateralPlanMonoTime_field_present_in_current_schema': 'lateralPlanMonoTime' in log.ControlsState.schema.fields,
            'services': {}}
  for name, records in rows.items():
    headers = [r['header'] for r in records]
    stats = {'count': len(records), 'invalid_event_count': sum(not r['valid'] for r in records),
             'zero_header_count': headers.count(0),
             'header_interval': distribution([delta_ms(b, a) for a, b in pairwise(headers)])}
    ref = 'eof' if name in ('roadCameraState', 'wideRoadCameraState', 'modelV2') else 'timestamp' if name == 'livePose' else None
    if ref:
      stats['zero_content_timestamp_count'] = sum(r[ref] == 0 for r in records)
      differences = [delta_ms(r['header'], r[ref]) for r in records if r['header'] and r[ref]]
      stats['header_minus_content_timestamp'] = distribution(differences)
      stats['content_timestamp_after_header_count'] = sum(d < 0 for d in differences)
      stats['future_content_ahead_of_header'] = distribution([-d for d in differences if d < 0])
    if name in ('modelV2', 'roadCameraState', 'wideRoadCameraState'):
      steps = [b['fid'] - a['fid'] for a, b in pairwise(records)]
      stats['frame_id_forward_gap_pair_count'] = sum(step > 1 for step in steps)
      stats['frame_id_unobserved_numbers_between_records_count'] = sum(step - 1 for step in steps if step > 1)
      stats['frame_id_nonincreasing_pair_count'] = sum(step <= 0 for step in steps)
    if name == 'modelV2':
      stats['frame_age_zero_count'] = sum(r['frame_age'] == 0 for r in records)
      stats['frame_age_positive_count'] = sum(r['frame_age'] > 0 for r in records)
      stats['first_model_header_minus_exposure_eof'] = distribution([
        delta_ms(r['header'], r['eof']) for r in records[:1] if r['header'] and r['eof']])
      stats['remaining_models_header_minus_exposure_eof'] = distribution([
        delta_ms(r['header'], r['eof']) for r in records[1:] if r['header'] and r['eof']])
      stats['first_ten_models_header_minus_exposure_eof'] = distribution([
        delta_ms(r['header'], r['eof']) for r in records[:10] if r['header'] and r['eof']])
      stats['after_first_ten_models_header_minus_exposure_eof'] = distribution([
        delta_ms(r['header'], r['eof']) for r in records[10:] if r['header'] and r['eof']])
      stats['model_exposure_to_header_over_100ms_count'] = sum(delta_ms(r['header'], r['eof']) > 100
                                                              for r in records if r['header'] and r['eof'])
      stats['recorded_model_execution_duration'] = distribution([r['execution_time'] * 1000 for r in records])
      stats['first_model_recorded_execution_duration'] = distribution([r['execution_time'] * 1000 for r in records[:1]])
      stats['header_minus_exposure_minus_recorded_execution'] = distribution([
        delta_ms(r['header'], r['eof']) - r['execution_time'] * 1000
        for r in records if r['header'] and r['eof']])
    if name == 'livePose':
      for flag in ('sensors_ok', 'inputs_ok', 'posenet_ok'):
        stats[flag + '_true_count'] = sum(r[flag] for r in records)
      stats['valid_event_with_zero_timestamp_count'] = sum(r['valid'] and not r['timestamp'] for r in records)
      stats['invalid_event_with_zero_timestamp_count'] = sum(not r['valid'] and not r['timestamp'] for r in records)
    if name in ('carControl', 'selfdriveState'):
      for flag in ('enabled', 'long_active', 'lat_active') if name == 'carControl' else ('enabled', 'active'):
        stats[flag + '_true_count'] = sum(r[flag] for r in records)
    if name == 'controlsState':
      stats['long_control_off_count'] = sum(r['long_off'] for r in records)
    result['services'][name] = stats

  camera = {name: index_rows(rows[name], lambda r: (r['fid'], r['eof']))
            for name in ('roadCameraState', 'wideRoadCameraState')}
  camera_fids = {name: index_rows(rows[name], lambda r: r['fid']) for name in camera}
  models = index_rows(rows['modelV2'], lambda r: r['header'])
  plans = index_rows(rows['longitudinalPlan'], lambda r: r['header'])
  first_model_header = rows['modelV2'][0]['header'] if rows['modelV2'] else None
  windows = {key: defaultdict(list) for key in ('first_1s', 'first_5s', 'between_1s_and_5s', 'after_5s')}

  def window_names(model):
    relative = delta_ms(model['header'], first_model_header) if first_model_header is not None else -1
    return ([name for name, include in (
      ('first_1s', 0 <= relative < 1000), ('first_5s', 0 <= relative < 5000),
      ('between_1s_and_5s', 1000 <= relative < 5000), ('after_5s', relative >= 5000)) if include])

  camera_counts, camera_deltas = Counter(), defaultdict(list)
  unique_model_camera = {}
  for model in rows['modelV2']:
    for name in window_names(model):
      windows[name]['frame_drop_percent'].append(model['frame_drop'])
      windows[name]['recorded_model_execution_duration_ms'].append(model['execution_time'] * 1000)
      if model['eof']:
        windows[name]['model_header_minus_exposure_eof_ms'].append(delta_ms(model['header'], model['eof']))
    candidates = []
    for name, lookup in camera.items():
      matches = lookup.get((model['fid'], model['eof']), []) if model['eof'] else []
      if matches:
        camera_counts[name + '_exact_fid_eof_match_model_count'] += 1
      elif camera_fids[name].get(model['fid']):
        camera_counts[name + '_fid_present_but_no_exact_eof_model_count'] += 1
      candidates.extend((name, match) for match in matches)
    camera_counts['candidate_pair_count'] += len(candidates)
    if len(candidates) != 1:
      camera_counts['no_exact_pair_model_count' if not candidates else 'ambiguous_exact_pair_model_count'] += 1
      continue
    camera_counts['unique_exact_pair_model_count'] += 1
    name, frame = candidates[0]
    camera_deltas[name + '_model_header_minus_camera_header'].append(delta_ms(model['header'], frame['header']))
    camera_deltas[name + '_model_header_minus_exposure_eof'].append(delta_ms(model['header'], frame['eof']))
    unique_model_camera[id(model)] = (name, frame)
  result['exact_camera_model_linkage'] = link_summary(camera_counts, camera_deltas)

  plan_counts, plan_deltas = Counter(), defaultdict(list)
  for plan in rows['longitudinalPlan']:
    plan_deltas['stored_processing_delay_ms'].append(plan['processing_delay'] * 1000)
    if not plan['model']:
      plan_counts['zero_model_reference_count'] += 1
      continue
    computed = delta_ms(plan['header'], plan['model'])
    plan_deltas['plan_header_minus_model_reference'].append(computed)
    plan_deltas['stored_minus_header_computed_processing_delay'].append(plan['processing_delay'] * 1000 - computed)
    plan_deltas['absolute_stored_minus_header_computed_processing_delay'].append(abs(plan['processing_delay'] * 1000 - computed))
    if computed < 0:
      plan_counts['model_reference_after_plan_header_count'] += 1
    matched = models.get(plan['model'], [])
    if len(matched) != 1:
      plan_counts['model_header_not_in_segment_count' if not matched else 'ambiguous_model_header_count'] += 1
      continue
    plan_counts['unique_exact_model_header_match_count'] += 1
    model = matched[0]
    plan_deltas['linked_plan_header_minus_model_header'].append(delta_ms(plan['header'], model['header']))
    for name in window_names(model):
      windows[name]['plan_header_minus_model_header_ms'].append(delta_ms(plan['header'], model['header']))
      if model['eof']:
        windows[name]['plan_header_minus_exposure_eof_ms'].append(delta_ms(plan['header'], model['eof']))
    if model['eof']:
      plan_deltas['linked_plan_header_minus_model_exposure_eof'].append(delta_ms(plan['header'], model['eof']))
    if id(model) in unique_model_camera:
      plan_counts['unique_camera_model_plan_chain_count'] += 1
      name, frame = unique_model_camera[id(model)]
      plan_deltas[name + '_linked_plan_header_minus_camera_header'].append(delta_ms(plan['header'], frame['header']))
      plan_deltas[name + '_linked_plan_header_minus_exposure_eof'].append(delta_ms(plan['header'], frame['eof']))
  result['exact_model_plan_linkage'] = link_summary(plan_counts, plan_deltas)
  result['relative_model_start_windows'] = {
    'origin': '세그먼트의 첫 modelV2 헤더를 0초로 삼는다. 촬영 시각이나 장치 절대 시각을 출력하지 않는다.',
    'first_5s_includes_first_1s': True,
    'values': {name: {key: short_distribution(samples, 'percent' if key == 'frame_drop_percent' else 'ms')
                      for key, samples in values.items()} for name, values in windows.items()},
  }

  control_counts, control_deltas = Counter(), defaultdict(list)
  for row in rows['controlsState']:
    if not row['plan']:
      control_counts['zero_plan_reference_count'] += 1
      continue
    control_deltas['controls_header_minus_plan_reference'].append(delta_ms(row['header'], row['plan']))
    matched = plans.get(row['plan'], [])
    if len(matched) == 1:
      control_counts['unique_exact_plan_header_match_count'] += 1
      control_deltas['linked_controls_header_minus_plan_header'].append(delta_ms(row['header'], matched[0]['header']))
      plan = matched[0]
      control_counts['controls_model_reference_same_as_plan_model_count' if row['model'] == plan['model']
                     else 'controls_model_reference_differs_from_plan_model_count'] += 1
      if row['model'] != plan['model']:
        control_counts['controls_lateral_model_reference_newer_than_plan_model_count' if row['model'] > plan['model']
                       else 'controls_lateral_model_reference_older_than_plan_model_count'] += 1
        control_deltas['different_lateral_reference_minus_plan_model_header'].append(delta_ms(row['model'], plan['model']))
      model_matches = models.get(plan['model'], [])
      if len(model_matches) == 1:
        control_counts['unique_controls_plan_model_chain_count'] += 1
        model = model_matches[0]
        control_deltas['linked_controls_header_minus_plan_model_header'].append(delta_ms(row['header'], model['header']))
        if model['eof']:
          control_deltas['linked_controls_header_minus_plan_model_exposure_eof'].append(delta_ms(row['header'], model['eof']))
        if id(model) in unique_model_camera:
          control_counts['unique_controls_plan_model_camera_chain_count'] += 1
    else:
      control_counts['plan_header_not_in_segment_count' if not matched else 'ambiguous_plan_header_count'] += 1
    lateral_matches = models.get(row['model'], [])
    if len(lateral_matches) == 1:
      control_counts['unique_controls_lateral_reference_model_match_count'] += 1
      control_deltas['controls_header_minus_lateral_model_header'].append(delta_ms(row['header'], lateral_matches[0]['header']))
  result['controlsState_plan_reference_linkage'] = link_summary(control_counts, control_deltas)
  return result


def main():
  result = {
    'purpose': '실제 제어 비활성 원본 로그에서 시각 관계만 익명 집계한다.',
    'scope': '실물 제어 활성 성능·재생 주입 성능·CPU 실행 시간·CAN 전달 시간을 입증하는 검사가 아니다.',
    'parser': '전체 Cap’n Proto 스키마와 pycapnp를 사용하며 CAN 파서는 호출하지 않는다.',
    'CAN_backend_reference': 'python',
    'clock_interpretation': {
      'camera_content': '현재 소스의 커널 SOF BOOT_TS와 센서 읽기 시간 보정 EOF',
      'camera_header': '현재 C++ 소스의 CLOCK_BOOTTIME',
      'python_header': '현재 Python 소스의 time.monotonic; Linux CLOCK_MONOTONIC 계열',
      'model_content': '주 카메라 VIPC의 EOF를 복사하며 주 카메라는 road 또는 wide일 수 있다.',
      'plan_reference': 'modelV2의 헤더를 복사하며 촬영 시각을 직접 참조하지 않는다.',
      'pose_content': '카메라 EOF에서 100ms를 뺀 관측 또는 센서 timestamp로 갱신한 필터 시각',
      'cause_limit': '현재 소스의 시간 기원 설명이며 원본 장치의 실제 시계 오프셋·절전·센서 소실 원인을 확정하지 않는다.',
    },
    'source_sha256': {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in SOURCE_FILES},
    'logs': [observe(TASK_ROOT / 'work/input' / name, 'log_' + str(i)) for i, name in enumerate(INPUTS, 1)],
  }
  (OUTPUT / 'observations.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
  print(json.dumps({'anonymous_log_count': len(result['logs']),
                    'model_count': sum(r['service_counts']['modelV2'] for r in result['logs']),
                    'plan_count': sum(r['service_counts']['longitudinalPlan'] for r in result['logs']),
                    'saved': 'observations.json'}, ensure_ascii=False))


if __name__ == '__main__':
  main()
