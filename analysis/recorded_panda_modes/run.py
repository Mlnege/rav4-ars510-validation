"""기록된 Panda 모드 전환과 모든 원본 CAN을 실제 C RX에 메모리 재생한다."""
import ast
from collections import Counter
from contextlib import contextmanager
import ctypes
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import capnp
import zstandard


WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
SOURCE = ROOT / 'work/carrotpilot'
LAB = ROOT / 'work/download_e2e'
LIBRARY = LAB / 'work/safety_validation/libsafety_download_native.so'
sys.path.insert(0, str(LAB / 'work/safety_validation'))
from verify_compiled import Probe, quiet_c_stdout

INPUTS = [('log_a', 'rlog.zst'), ('log_b', 'rlog_06.zst'),
          ('log_c', 'rlog_11.zst'), ('log_d', 'rlog_12.zst')]


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def load_events():
  path = SOURCE / 'tools/ars510_offline/replay.py'
  tree = ast.parse(path.read_text())
  selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'events']
  assert len(selected) == 1
  namespace = {'contextmanager': contextmanager, 'tempfile': tempfile,
               'zstandard': zstandard, 'shutil': shutil}
  exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
  return namespace['events']


def dataset(path, schema, events):
  rows = []
  original = Counter()
  original_can_items = 0
  origin = maximum = previous = None
  inversions = 0
  with events(path, schema.Event) as stream:
    for event in stream:
      ns = int(event.logMonoTime)
      if origin is None:
        origin = ns
      maximum = ns if maximum is None else max(maximum, ns)
      inversions += int(previous is not None and ns < previous)
      previous = ns
      kind = event.which()
      original[kind] += 1
      if kind == 'can':
        # 실제 프레임은 메모리에만 보관하며 파일에는 개수만 작성한다.
        body = [(int(f.address), bytes(f.dat), int(f.src)) for f in event.can]
        original_can_items += len(body)
      elif kind == 'pandaStates':
        body = [{'model': str(p.safetyModel), 'model_raw': int(p.safetyModel.raw),
                 'param': int(p.safetyParam), 'alt': int(p.alternativeExperience),
                 'recorded_controls': bool(p.controlsAllowed),
                 'recorded_rx_invalid': bool(p.safetyRxChecksInvalid),
                 'recorded_fault_count': len(p.faults)} for p in event.pandaStates]
      elif kind == 'carState':
        cs = event.carState
        body = {'pcm_enabled': bool(cs.cruiseState.enabled),
                'pcm_available': bool(cs.cruiseState.available),
                'gas': bool(cs.gasPressed), 'brake': bool(cs.brakePressed),
                'canValid': bool(cs.canValid), 'canTimeout': bool(cs.canTimeout)}
      else:
        continue
      rows.append(((maximum - origin) // 1000, (ns - origin) // 1000,
                   kind, bool(event.valid), body))
  return rows, {'event_counts': dict(original), 'header_storage_order_reversals': inversions,
                'original_can_item_count': original_can_items}


class ClockedProbe:
  def __init__(self, phase_us):
    self.probe = Probe(LIBRARY)
    self.lib = self.probe.lib
    self.lib.get_relay_malfunction.restype = ctypes.c_bool
    self.lib.get_current_safety_mode.restype = ctypes.c_int
    self.lib.get_current_safety_param.restype = ctypes.c_int
    self.counter = ctypes.c_uint32.in_dll(self.lib, 'safety_mode_cnt')
    self.rx_invalid = ctypes.c_bool.in_dll(self.lib, 'safety_rx_checks_invalid')
    self.operations = Counter()
    self.next_tick_us = 1_000_000 if phase_us == 0 else phase_us
    self.mode = (0, 0)
    self.alt = 0
    # 기록 전의 실제 모드는 알 수 없다. 안전한 초기 silent를 명시한다.
    self.set_mode(0, 0, 0)
    self.lib.set_timer(0)

  def set_mode(self, model, param, alt):
    if self.lib.set_safety_hooks(model, param) != 0:
      raise RuntimeError(f'기록 모드가 현재 C에서 미지원: model={model},param={param}')
    self.operations['set_safety_hooks'] += 1
    self.mode = (model, param)
    self.lib.set_alternative_experience(alt)
    self.operations['set_alternative_experience'] += 1
    self.alt = alt

  def advance(self, now_us):
    while self.next_tick_us <= now_us:
      self.lib.set_timer(self.next_tick_us & 0xffffffff)
      # source board/main.c의 외부 1Hz 증가만 재현한다. 권한 값은 직접 쓰지 않는다.
      self.counter.value += 1
      self.operations['mode_counter_1hz_increment'] += 1
      self.lib.safety_tick_current_safety_config()
      self.operations['safety_tick_1hz'] += 1
      self.next_tick_us += 1_000_000
    self.lib.set_timer(now_us & 0xffffffff)

  def state(self):
    return {'controls': bool(self.lib.get_controls_allowed()),
            'long': bool(self.lib.get_longitudinal_allowed()),
            'relay': bool(self.lib.get_relay_malfunction()),
            'rx_invalid': bool(self.rx_invalid.value), 'counter': int(self.counter.value)}


def replay(alias, rows, profile, phase_us):
  if not any(row[2] == 'pandaStates' for row in rows):
    return {'alias': alias, 'phase_us': phase_us, 'status': 'insufficient_recorded_pandaStates',
            'profile': profile, 'c_rx_executed': False}
  clock = ClockedProbe(phase_us)
  counts, by_mode, returns, stock = Counter(), Counter(), Counter(), Counter()
  notification_shapes = Counter()
  cs_counts, panda_counts, counters = Counter(), Counter(), Counter()
  transitions, relay_transitions, rx_invalid_transitions = [], [], []
  first_toyota = None
  last_relay = last_invalid = False
  header_delays = []
  mode_names = {0: 'initial_silent'}
  for now_us, header_us, kind, valid, body in rows:
    clock.advance(now_us)
    if kind == 'pandaStates':
      if len(body) != 1:
        raise RuntimeError('여러 Panda의 연결/버스 대응은 이 단일 C 진단에서 미지원')
      if not valid:
        counts['invalid_panda_events_not_applied'] += 1
      else:
        p = body[0]
        mode_names[p['model_raw']] = p['model']
        mode_change = (p['model_raw'], p['param']) != clock.mode
        alt_change = p['alt'] != clock.alt
        if mode_change:
          before = clock.state()
          clock.set_mode(p['model_raw'], p['param'], p['alt'])
          after = clock.state()
          transitions.append({'relative_receive_s': now_us / 1e6, 'relative_header_s': header_us / 1e6,
                              'model': p['model'], 'model_raw': p['model_raw'],
                              'param': p['param'], 'alt': p['alt'],
                              'counter_before': before['counter'], 'counter_after': after['counter'],
                              'relay_before': before['relay'], 'relay_after': after['relay'],
                              'controls_after': after['controls']})
        elif alt_change:
          clock.lib.set_alternative_experience(p['alt'])
          clock.operations['set_alternative_experience'] += 1
          clock.alt = p['alt']
        else:
          counts['repeated_panda_samples_without_reset'] += 1
        if p['model_raw'] == 2 and first_toyota is None:
          first_toyota = now_us / 1e6
        state = clock.state()
        panda_counts['samples'] += 1
        panda_counts['c_controls_true'] += state['controls']
        panda_counts['c_relay_true'] += state['relay']
        panda_counts['c_rx_invalid_true'] += state['rx_invalid']
        panda_counts['recorded_controls_true'] += p['recorded_controls']
        panda_counts['recorded_rx_invalid_true'] += p['recorded_rx_invalid']
        panda_counts['recorded_fault_sample'] += p['recorded_fault_count'] > 0
        panda_counts['controls_differs_from_recorded'] += state['controls'] != p['recorded_controls']
        panda_counts['rx_invalid_differs_from_recorded'] += state['rx_invalid'] != p['recorded_rx_invalid']
        counts['current_mode_mismatch'] += clock.lib.get_current_safety_mode() != p['model_raw']
        counts['current_param_mismatch'] += clock.lib.get_current_safety_param() != p['param']
    elif kind == 'can':
      counts['can_events'] += 1
      for address, data, bus in body:
        counts['recorded_can_items_consumed'] += 1
        if 128 <= bus <= 135:
          # src+0x80은 송신 반환 통지다. bytes/src를 고치거나 RX로 재주입하지 않는다.
          counts['returned_notifications'] += 1
          notification_shapes[f'returned/src{bus}/length{len(data)}'] += 1
          continue
        if 192 <= bus <= 199:
          # src+0xc0은 거부 통지다. 기존 안전 판단 결과를 새로운 RX로 만들지 않는다.
          counts['rejected_notifications'] += 1
          notification_shapes[f'rejected/src{bus}/length{len(data)}'] += 1
          continue
        if not 0 <= bus <= 7:
          counts['unknown_source_items'] += 1
          notification_shapes[f'unknown/src{bus}/length{len(data)}'] += 1
          continue
        state_before = clock.state()
        result = clock.probe.packet('rx', address, data, bus)
        counts['physical_rx_frames'] += 1
        returns[str(result)] += 1
        mode_label = f'{mode_names.get(clock.mode[0], str(clock.mode[0]))}/param{clock.mode[1]}/alt{clock.alt}'
        by_mode[mode_label] += 1
        if bus == 0 and address in (0x2e4, 0x343):
          stock[f'{mode_label}/{hex(address)}'] += 1
          counts['stock_after_grace'] += state_before['counter'] > 1
        if clock.state()['relay'] and not state_before['relay']:
          counts['relay_rising_rx'] += 1
      counts['can_events_valid'] += valid
    elif kind == 'carState':
      state = clock.state()
      cs_counts['samples'] += 1
      for key in ('controls', 'long', 'relay', 'rx_invalid'):
        cs_counts[f'c_{key}_true'] += state[key]
      for key, value in body.items():
        cs_counts[f'recorded_{key}_true'] += value
      counters[str(state['counter'])] += 1
      header_delays.append((now_us - header_us) / 1000.)
    state = clock.state()
    if state['relay'] != last_relay:
      relay_transitions.append({'relative_receive_s': now_us / 1e6, 'relay': state['relay'],
                                'model': mode_names.get(clock.mode[0], str(clock.mode[0])),
                                'param': clock.mode[1], 'counter': state['counter']})
      last_relay = state['relay']
    if state['rx_invalid'] != last_invalid:
      rx_invalid_transitions.append({'relative_receive_s': now_us / 1e6,
                                     'rx_invalid': state['rx_invalid'], 'counter': state['counter']})
      last_invalid = state['rx_invalid']
  expected_can_events = profile['event_counts'].get('can', 0)
  checks = {'all_recorded_can_events_consumed': counts['can_events'] == expected_can_events,
            'all_recorded_can_items_consumed': counts['recorded_can_items_consumed'] == profile['original_can_item_count'],
            'all_categories_sum_to_original_items': sum(counts[k] for k in ('physical_rx_frames',
                    'returned_notifications', 'rejected_notifications', 'unknown_source_items')) == profile['original_can_item_count'],
            'unknown_source_types_absent': counts['unknown_source_items'] == 0,
            'all_panda_mode_params_match': counts['current_mode_mismatch'] == counts['current_param_mismatch'] == 0,
            'normal_mode_change_counter_resets_only': all(t['counter_after'] == 0 for t in transitions),
            'all_physical_rx_hook_returns_valid': returns.get('-1', 0) == returns.get('0', 0) == 0
                    and returns.get('1', 0) == counts['physical_rx_frames'],
            'actual_cs_count_preserved': cs_counts['samples'] == profile['event_counts'].get('carState', 0),
            'mode_changes_not_repeated_resets': clock.operations['set_safety_hooks'] == len(transitions) + 1,
            '1hz_counter_and_safety_ticks_match': clock.operations['mode_counter_1hz_increment'] == clock.operations['safety_tick_1hz']}
  return {'alias': alias, 'phase_us': phase_us, 'status': 'recorded_policy_c_rx_observed',
          'counts': dict(counts), 'profile': profile, 'rx_return_counts': dict(returns),
          'notification_shapes_preserved_counts': dict(notification_shapes),
          'raw_frames_by_mode': dict(by_mode), 'bus0_stock_frames_by_mode': dict(stock),
          'carState_c_samples': dict(cs_counts), 'carState_mode_counter_histogram': dict(counters),
          'carState_delivery_minus_header_ms_range': [min(header_delays), max(header_delays)] if header_delays else [],
          'panda_c_samples': dict(panda_counts), 'mode_transitions': transitions,
          'relay_transitions': relay_transitions, 'rx_invalid_transitions': rx_invalid_transitions,
          'first_toyota_relative_receive_s': first_toyota,
          'operations': dict(clock.operations), 'final_c_state': clock.state(),
          'checks': checks, 'failures': [name for name, passed in checks.items() if not passed],
          'init_tests_calls': 0, 'controls_allowed_setter_calls': 0, 'relay_setter_calls': 0,
          'counter_arbitrary_reset_calls': 0, 'tx_hook_calls': 0, 'physical_tx': False}


def main():
  WORK.mkdir(parents=True, exist_ok=True)
  schema_path = ROOT / 'work/input/carrot_schemas'
  parser = capnp.SchemaParser()
  schema = parser.load(str(schema_path / 'log.capnp'), imports=[str(schema_path), str(schema_path / 'include')])
  events = load_events()
  source_paths = ['tools/ars510_offline/replay.py', 'panda/board/main.c',
                  'panda/python/__init__.py', 'openpilot/selfdrive/pandad/panda.h',
                  'openpilot/selfdrive/pandad/panda.cc',
                  'opendbc_repo/opendbc/safety/safety.h',
                  'opendbc_repo/opendbc/safety/safety/safety_toyota.h',
                  'opendbc_repo/opendbc/safety/tests/libsafety/safety_helpers.h']
  before = {path: sha(SOURCE / path) for path in source_paths}
  library_before = sha(LIBRARY)
  results = []
  with quiet_c_stdout():
    for alias, name in INPUTS:
      rows, profile = dataset(ROOT / 'work/input' / name, schema, events)
      for phase in (0, 500_000):
        result = replay(alias, rows, profile, phase)
        results.append(result)
  after = {path: sha(SOURCE / path) for path in source_paths}
  observed = [r for r in results if r['status'] == 'recorded_policy_c_rx_observed']
  final = {
    'generated_utc': datetime.now(UTC).isoformat(), 'results': results,
    'source_hashes_before': before, 'source_hashes_after': after,
    'source_unchanged': before == after, 'library_sha256_before': library_before,
    'library_sha256_after': sha(LIBRARY), 'library_unchanged': library_before == sha(LIBRARY),
    'script_sha256': sha(Path(__file__)),
    'direct_observed_runs': len(observed),
    'direct_check_count': sum(len(r['checks']) for r in observed),
    'direct_failed_checks': [{'alias': r['alias'], 'phase_us': r['phase_us'], 'failed': r['failures']}
                             for r in observed if r['failures']],
    'clock_scope_ko': '원본 저장순서. 수신 시각은 지금까지 본 최대 헤더. 원본 CS 헤더와 가정 수신 시각 차이를 별도 기록. 1Hz 위상 0/0.5초는 MCU 위상 가정이다.',
    'scope_ko': '현재 실제 C RX 판단만 실행한다. 정상 모드 변경 초기화와 1Hz 외부 시간 진행만 재현. setter 권한/relay 우회·반복 reset·CAN 삭제·TX 없음. 설치 펌웨어/실물 릴레이/차량/heartbeat는 미검증.',
  }
  (WORK / 'results.json').write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps({'runs': len(observed), 'checks': final['direct_check_count'],
                    'failed': final['direct_failed_checks'], 'source_unchanged': final['source_unchanged'],
                    'library_unchanged': final['library_unchanged'],
                    'relay_true_cs': {f"{r['alias']}/phase{r['phase_us']}": r['carState_c_samples'].get('c_relay_true', 0)
                                      for r in observed}}, ensure_ascii=False))
  raise SystemExit(1 if final['direct_failed_checks'] or not final['source_unchanged'] or not final['library_unchanged'] else 0)


if __name__ == '__main__':
  main()
