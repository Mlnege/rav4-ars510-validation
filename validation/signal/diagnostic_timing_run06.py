"""검사기의 시간·초기화·계산·기록 비용을 원형 계산과 분리해 측정한다.

센서 입력·시계·전송/저장소만 합성한다. 생산 코드·기존 worker·수치 바이너리,
차량·운영 Params·Panda·PCS를 수정하지 않는다. 전체 앱 활성 게이트는 별도다.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import typing

import numpy as np
import psutil

WORK = Path(__file__).resolve().parents[1]
REPO = WORK/'carrotpilot'
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(WORK/'native_sim'))
from offline_io import BUILD_ROOT
from tools.ars510_validation.signal.native_signal import NativeSignalHarness, input_clock
from tools.ars510_validation.signal.native_signal_can import all_source_hashes
from tools.ars510_validation.signal.realtime_signal import DelayedPlant
from openpilot.cereal import car, log
from openpilot.cereal.services import SERVICE_LIST
from openpilot.common.utils import MovingAverage
from opendbc.can import CANParser
from opendbc.car import Bus
from opendbc.car.toyota.carcontroller import CarController
from opendbc.car.toyota.toyotacan import toyota_checksum
from opendbc.car.toyota.values import DBC
from opendbc.dbc.generator.generator import create_dbc


SERVICES = ('carState', 'radarState', 'modelV2', 'selfdriveState', 'carControl', 'controlsState',
            'livePose', 'liveCalibration', 'roadCameraState', 'deviceState', 'carrotMan', 'longitudinalPlan')
CASE_KINDS = ('frozen_clock_wall_stall', 'real_clock_preserved_source',
              'fresh_producer_header_old_acquisition', 'stopped_model_publisher', 'stopped_plan_publisher')


class DiagnosticClock:
  def __init__(self, value=100.):
    self.value = value
    self.real = False
    self.anchor_ns = time.perf_counter_ns()

  @property
  def now(self):
    return self.value+(time.perf_counter_ns()-self.anchor_ns)*1e-9 if self.real else self.value

  @now.setter
  def now(self, value):
    if not self.real:
      self.value = value

  def activate_real_elapsed(self):
    self.anchor_ns = time.perf_counter_ns()
    self.real = True


class Measurements:
  def __init__(self):
    self.case = 'startup'
    self.rows = []
    self.step = -1
    self.phase = 'startup'

  def call(self, stage, fn, *values, **kwargs):
    wall, cpu = time.perf_counter_ns(), time.thread_time_ns()
    result = fn(*values, **kwargs)
    end, cpu_end = time.perf_counter_ns(), time.thread_time_ns()
    self.rows.append({'case': self.case, 'phase': self.phase, 'step': self.step, 'stage': stage, 'wall_start_ns': wall,
                      'wall_end_ns': end, 'wall_duration_ms': (end-wall)*1e-6, 'thread_cpu_ms': (cpu_end-cpu)*1e-6})
    return result

  def wrap(self, obj, method, stage):
    original = getattr(obj, method)
    def wrapped(*values, **kwargs):
      return self.call(stage, original, *values, **kwargs)
    setattr(obj, method, wrapped)

  def summary(self, selected=None):
    groups = defaultdict(list)
    for row in self.rows if selected is None else selected:
      groups[row['stage']].append(row)
    return {name: {'calls': len(rows), 'wall_total_ms': sum(row['wall_duration_ms'] for row in rows),
                   'thread_cpu_total_ms': sum(row['thread_cpu_ms'] for row in rows),
                   'wall_p99_ms': float(np.percentile([row['wall_duration_ms'] for row in rows], 99)),
                   'wall_p50_ms': float(np.percentile([row['wall_duration_ms'] for row in rows], 50)),
                   'wall_max_ms': max(row['wall_duration_ms'] for row in rows)} for name, rows in groups.items()}


def receiver_classes():
  source = REPO/'openpilot/cereal/messaging/__init__.py'
  nodes = [node for node in ast.parse(source.read_text(encoding='utf-8')).body
           if isinstance(node, ast.ClassDef) and node.name in ('SubMaster', 'FrequencyTracker')]
  import capnp
  namespace = dict(vars(typing), os=os, time=time, capnp=capnp, log=log, SERVICE_LIST=SERVICE_LIST, MovingAverage=MovingAverage)
  body = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes]
  exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(source), 'exec'), namespace)
  return namespace['SubMaster'], namespace['FrequencyTracker']


SubMaster, FrequencyTracker = receiver_classes()


def receiver(services=SERVICES):
  # 소켓 생성자만 배제한 시작 필드다. update_msgs/all_checks/FrequencyTracker는 원형이다.
  sm = SubMaster.__new__(SubMaster)
  sm.frame, sm.services = -1, list(services)
  sm.seen = dict.fromkeys(services, False)
  sm.updated = dict.fromkeys(services, False)
  sm.recv_time = dict.fromkeys(services, 0.)
  sm.recv_frame = dict.fromkeys(services, 0)
  sm.logMonoTime = dict.fromkeys(services, 0)
  on_demand = {name: SERVICE_LIST[name].frequency <= 1e-5 for name in services}
  sm.valid = on_demand.copy()
  sm.alive = on_demand.copy()
  sm.freq_ok = on_demand.copy()
  sm.static_freq_services = {name for name in services if not on_demand[name]}
  sm.data = {name: log.Event.new_message().init(name) for name in services}
  sm.ignore_average_freq, sm.ignore_alive, sm.ignore_valid = [], [], []
  sm.simulation = False
  sm.freq_tracker = {name: FrequencyTracker(SERVICE_LIST[name].frequency, 100., name == 'carControl',
                                           service_freq_range=SERVICE_LIST[name].frequency_range) for name in services}
  # 수신 socket IO만 빈 poller로 격리한다. 원형 update와 update_msgs는 그대로다.
  sm.poller = SimpleNamespace(poll=lambda timeout: [])
  sm.non_polled_services, sm.sock = [], {}
  return sm


def snapshot(event, *, header=None):
  copied = event.copy()
  if header is not None:
    copied.logMonoTime = int(header*1e9)
  return copied


class DiagnosticCanPlant:
  def __init__(self, harness, dbc, measures, *, speed=15.):
    self.h = harness
    self.measures = measures
    selected = DBC[harness.cp.carFingerprint].copy()
    selected[Bus.pt] = str(dbc)
    self.controller = CarController(selected, harness.cp)
    self.parser = CANParser(str(dbc), [('ACC_CONTROL', 33)], 0)
    measures.wrap(self.controller, 'update', 'can_controller')
    measures.wrap(self.parser, 'update', 'can_decode')
    self.fixed = DelayedPlant(speed, delay=.15, tau=.15)
    self.wall = DelayedPlant(speed, delay=.15, tau=.15)
    self.last_wall_ns = time.perf_counter_ns()
    self.residual_wall_s = 0.
    self.command = 0.
    self.tick = 0
    self.rows = []
    self.failures = Counter()
    self.fixed_sensor_feedback = False

  @property
  def speed(self):
    return 15. if self.fixed_sensor_feedback else self.fixed.speed

  @property
  def accel(self):
    return 0. if self.fixed_sensor_feedback else self.fixed.accel

  def integrate_wall_gap(self):
    now = time.perf_counter_ns()
    delta = (now-self.last_wall_ns)*1e-9
    self.last_wall_ns = now
    self.residual_wall_s += delta
    # 모형의 10ms 소구간만 적분한다. 실제 차량의 회생/마찰/경사를 재현하지 않는다.
    while self.residual_wall_s >= .01:
      self.wall.advance(self.command)
      self.residual_wall_s -= .01
    return delta

  def send(self, output, cs, plan, *, active, logical_timestamp, control_state, hold=False):
    self.integrate_wall_gap()
    cc = car.CarControl.new_message(enabled=active, longActive=active, latActive=False, orientationNED=[0., 0., 0.])
    cc.hudControl.leadDistanceBars = 2
    cc.actuators.accel = float(output)
    cc.actuators.aTarget = float(plan.aTarget)
    cc.actuators.jerk = float(plan.jTargetNow)
    cc.actuators.longControlState = control_state
    state = SimpleNamespace(out=cs, gvc=float(cs.aEgo), acc_type=1, pcm_acc_status=8, pcm_follow_distance=2, lkas_hud={})
    _, messages = self.controller.update(cc.as_reader(), state, int(logical_timestamp*1e9))
    created_wall_ns = time.perf_counter_ns()
    packets = [(address, data, bus) for address, data, bus in messages if address == 0x343 and bus == 0]
    for address, data, _ in packets:
      if len(data) != 8 or toyota_checksum(address, None, bytearray(data)) != data[-1]:
        self.failures['checksum'] += 1
    if packets:
      accepted = self.parser.update([(int(logical_timestamp*1e9), packets)])
      if 0x343 not in accepted:
        self.failures['decode'] += 1
      else:
        self.command = float(self.parser.vl['ACC_CONTROL']['ACCEL_CMD'])
      if hold and self.command > 0:
        self.failures['new_positive_hold_message'] += 1
    if self.tick % 3 != 0 and packets:
      self.failures['off_cadence'] += 1
    if not math.isfinite(self.command) or not -3.5 <= self.command <= 2.:
      self.failures['bounds'] += 1
    self.fixed.advance(self.command)
    row = {'control_tick': self.tick, 'logical_timestamp': logical_timestamp, 'can_created_wall_ns': created_wall_ns,
           'created': bool(packets), 'decoded_command': self.command, 'longcontrol_output': float(output),
           'fixture_active': active, 'start_hold': hold, 'fixed_10ms_speed': self.fixed.speed,
           'plan_target': float(plan.aTarget), 'can_valid': bool(cs.canValid),
           'long_control_state': str(control_state), 'pcm_previous_request': float(self.controller.prev_accel),
           'pcm_pid_integral': float(self.controller.long_pid.i), 'start_released': bool(self.h.carrot.start_decision.released),
           'should_stop': bool(plan.shouldStop), 'fixed_10ms_accel': self.fixed.accel,
           'fixed_10ms_position': self.fixed.position, 'wall_integrated_speed': self.wall.speed,
           'wall_integrated_position': self.wall.position, 'wall_residual_unintegrated_s': self.residual_wall_s}
    self.rows.append(row)
    self.tick += 1
    return row

  def advance(self, output, **kwargs):
    del kwargs
    plan = self.h.sink.event.longitudinalPlan
    # 원형 helper의 slot 가산은 frozen 시계에만 적용한다. 진행 시계에는 이중 가산하지 않는다.
    stamp = self.h.clock.now if self.h.clock.real else self.h.clock.now+(self.tick % 5)*.01
    self.send(output, self.h.sm['carState'], plan, active=bool(self.h.sm['carControl'].longActive),
              logical_timestamp=stamp, control_state=self.h.control.long_control_state,
              hold=bool(self.h.carrot.start_decision.hold))


def install_measurements(h, measures):
  for obj, method, name in ((h, 'model_trajectory', 'fixture_input'), (h.planner, 'update', 'planner_total'),
                             (h.planner.mpc, 'update', 'mpc_nested'), (h.planner, 'publish', 'plan_publish'),
                             (h.control, 'update', 'longcontrol'), (h.start_runtime, 'read', 'start_runtime'),
                             (h.prepare_runtime, 'read', 'prepare_runtime')):
    measures.wrap(obj, method, name)


def warm(h, rx, extra, measures, *, signal_mode):
  previous_phase = measures.phase
  measures.phase = 'warmup'
  templates = {}
  for index in range(100):
    now = 100.+index*.05
    h.sm['modelV2'].frameId = index+1
    h.sm['modelV2'].timestampEof = int((now-.1)*1e9)
    measures.step = index
    h.step(now, signal_mode=signal_mode)
    templates = {name: snapshot(event) for name, event in h.sm.events.items()}
    templates['longitudinalPlan'] = snapshot(h.sink.event)
    for slot in range(5):
      tick, received = index*5+slot, []
      recv_now = now+slot*.01
      for name in SERVICES:
        frequency = SERVICE_LIST[name].frequency
        if frequency <= 0 or tick % round(100./frequency):
          continue
        header = now if name in ('modelV2', 'longitudinalPlan') else recv_now
        event = snapshot(templates[name], header=header)
        if name == 'livePose':
          event.livePose.timestamp = int((recv_now-.001)*1e9)
        received.append(event)
      rx.update_msgs(recv_now, received)
      extra.update_msgs(recv_now, [event for event in received if event.which() in extra.services])
  # 동일한 실제 수신값을 이어 쓴다. 별도 float 리터럴로 재구성해 14fs 미래 자료를 만들지 않는다.
  h.clock.now = max(rx.recv_time.values())
  measures.phase = previous_phase
  return templates


def cpu_work(seconds):
  """모델 계산의 가짜 결과가 아니라 별도 명시적 CPU 부하를 주입한다."""
  target = time.thread_time_ns()+round(seconds*1e9)
  value = 1
  while time.thread_time_ns() < target:
    value = (value*1664525+1013904223) & 0xFFFFFFFF
  return value


def periodic_healthy(templates, now, *, model=False):
  # 이 함수가 생성하는 센서는 명시적으로 계속 송신하는 합성 입력이다. 오래된 모델/EOF는 별도로 보존한다.
  names = ['carState', 'carControl', 'controlsState', 'selfdriveState', 'radarState', 'livePose', 'roadCameraState', 'deviceState', 'liveCalibration']
  if model:
    names.append('modelV2')
  packets = [snapshot(templates[name], header=now) for name in names]
  for event in packets:
    if event.which() == 'livePose':
      event.livePose.timestamp = int((now-.001)*1e9)
  return packets


def probe_stall(kind, stall_s, directory, dbc, measures, *, delay_kind='sleep'):
  measures.case = kind+':'+delay_kind+':'+str(stall_s)
  measures.phase = 'setup'
  clock = DiagnosticClock()
  with input_clock(clock):
    h = measures.call('setup', NativeSignalHarness, directory, clock=clock, camera_profile='ox03c10')
    install_measurements(h, measures)
    rx = receiver()
    extra = receiver(('liveCalibration', 'roadCameraState', 'deviceState'))
    signal_mode = 2 if 'preserved' in kind or 'frozen' in kind else 0
    templates = warm(h, rx, extra, measures, signal_mode=signal_mode)
    h.prepare_runtime.extra = extra
    plant = measures.call('can_setup', DiagnosticCanPlant, h, dbc, measures)
    header_before = rx.logMonoTime['modelV2']
    recv_before = rx.recv_time['modelV2']
    acquisition_before = int(rx['modelV2'].timestampEof)
    original_plan_header = rx.logMonoTime['longitudinalPlan']
    before_obs, context_before = h.prepare_runtime.read(rx, h.clock.now)
    if signal_mode == 2 and not context_before['valid']:
      (directory/'invalid_baseline.json').write_text(json.dumps({
        'now': clock.now, 'context': {key: value for key, value in context_before.items() if not callable(value)},
        'obs': before_obs, 'seen': rx.seen, 'valid': rx.valid, 'alive': rx.alive, 'recv_time': rx.recv_time,
        'extra_seen': extra.seen, 'extra_valid': extra.valid, 'extra_alive': extra.alive, 'extra_recv': extra.recv_time,
        'device': str(extra['deviceState'].deviceType), 'sensor': str(extra['roadCameraState'].sensor),
        'calibration': str(extra['liveCalibration'].calStatus), 'rpy': list(extra['liveCalibration'].rpyCalib),
        'pose': rx['livePose'].to_dict()}, ensure_ascii=False, indent=2), encoding='utf-8')
      raise AssertionError('지연을 주기 전 신호 metadata가 원형 판정에서 유효하지 않습니다')
    if kind != 'frozen_clock_wall_stall':
      clock.activate_real_elapsed()
    measures.phase = 'injection'
    wall_before, logical_before = time.perf_counter_ns(), clock.now
    measures.call('injected_sleep' if delay_kind == 'sleep' else 'injected_cpu_work',
                  time.sleep if delay_kind == 'sleep' else cpu_work, stall_s)
    wall_after, logical_after = time.perf_counter_ns(), clock.now
    plant.integrate_wall_gap()
    now = clock.now
    measures.phase = 'post_stall'
    received = []
    if kind in ('fresh_producer_header_old_acquisition', 'stopped_model_publisher', 'stopped_plan_publisher'):
      received = periodic_healthy(templates, now, model=kind != 'stopped_model_publisher')
    rx.update_msgs(now, received)
    extra.update_msgs(now, [event for event in received if event.which() in extra.services])
    observation, prepare_context = h.prepare_runtime.read(rx, now)
    model_updated = bool(rx.updated['modelV2'])
    # Toyota 원형 modelV2 진입 조건이다. 센서 중단 중 새 계획을 강제로 생성하지 않는다.
    run_planner = model_updated and rx.seen['modelV2'] and rx.logMonoTime['modelV2']-header_before >= 25_000_000
    if run_planner:
      h.planner.update(rx, h.carrot)
    new_plan = run_planner and kind != 'stopped_plan_publisher'
    if new_plan:
      h.planner.publish(rx, h.sink, h.carrot)
      rx.update_msgs(clock.now, [snapshot(h.sink.event)])
    else:
      rx.update_msgs(clock.now, [])
    # 현재 peer의 전체 앱 이벤트 검사를 대신하지 않는다. source enabled의 단독 CC 조건이다.
    fixture_active = bool(rx['selfdriveState'].enabled and h.cp.openpilotLongitudinalControl)
    plan = rx['longitudinalPlan']
    frame_age = (rx.frame-rx.recv_frame['longitudinalPlan'])*.01
    output, _, _ = h.control.update(fixture_active, rx['carState'], plan, (-3.5, 2.), frame_age, rx['radarState'])
    can = plant.send(output, rx['carState'], plan, active=fixture_active, logical_timestamp=clock.now,
                     control_state=h.control.long_control_state, hold=bool(h.carrot.start_decision.hold))
    return {'case_kind': kind, 'stall_s': stall_s, 'clock_kind': 'real_elapsed' if clock.real else 'frozen',
            'delay_kind': delay_kind, 'baseline_receive_clock_s': logical_before,
            'signal_assist_mode': signal_mode, 'prepare_context_valid_before_stall': bool(context_before['valid']),
            'injected_wall_s': (wall_after-wall_before)*1e-9, 'logical_advance_during_injected_sleep_s': logical_after-logical_before,
            'now': clock.now, 'model_header_before_ns': header_before, 'model_header_after_ns': rx.logMonoTime['modelV2'],
            'model_acquisition_before_ns': acquisition_before, 'model_acquisition_after_ns': int(rx['modelV2'].timestampEof),
            'model_header_preserved': rx.logMonoTime['modelV2'] == header_before,
            'model_acquisition_preserved': int(rx['modelV2'].timestampEof) == acquisition_before,
            'model_recv_before': recv_before, 'model_recv_after': rx.recv_time['modelV2'],
            'model_header_age_s': clock.now-rx.logMonoTime['modelV2']*1e-9,
            'model_acquisition_age_s': clock.now-rx['modelV2'].timestampEof*1e-9,
            'model_receive_age_s': clock.now-rx.recv_time['modelV2'],
            'plan_original_header_ns': original_plan_header, 'plan_header_ns': rx.logMonoTime['longitudinalPlan'],
            'plan_header_age_s': clock.now-rx.logMonoTime['longitudinalPlan']*1e-9,
            'plan_receive_age_s': clock.now-rx.recv_time['longitudinalPlan'], 't_since_plan_frame_s': frame_age,
            'prepare_context_valid': bool(prepare_context['valid']), 'model_updated': model_updated,
            'prepare_observation_age_s': clock.now-observation['timestamp'] if observation else None,
            'toyota_planner_trigger': run_planner, 'new_plan_published': new_plan,
            'plan_processing_delay_s': float(plan.processingDelay), 'plan_valid': bool(rx.valid['longitudinalPlan']),
            'receiver_alive': rx.alive.copy(), 'receiver_freq_ok': rx.freq_ok.copy(),
            'cc_active_fixture': fixture_active, 'cc_active_full_app': None, 'card_carcontrol_alive': rx.alive['carControl'],
            'can_output_is_standalone_fixture': True, 'can': can, 'can_failures': dict(plant.failures),
            'warm_periodic_synthetic_data': True, 'header_only_refresh_claimed_freshness': False,
            'fixed_plant_pause_limitation': True, 'wall_plant_fixed_10ms_substeps': True,
            'wall_plant_physical_model_validated': False, 'carparams_unchanged': h.unchanged_cp()}


def profile(directory, dbc, measures, *, steps, kind, record, recreate_every=0):
  measures.case = 'cost_profile:'+kind+':'+str(record)+':recreate_'+str(recreate_every)
  measures.phase = 'setup'
  clock = DiagnosticClock()
  with input_clock(clock):
    h = measures.call('setup', NativeSignalHarness, directory, clock=clock, camera_profile='ox03c10')
    install_measurements(h, measures)
    plant = measures.call('can_setup', DiagnosticCanPlant, h, dbc, measures)
    plant.fixed_sensor_feedback = True
    rx, extra = receiver(), receiver(('liveCalibration', 'roadCameraState', 'deviceState'))
    warm(h, rx, extra, measures, signal_mode=2)
    baseline_now = clock.now
    if not h.prepare_runtime.read(h.sm, baseline_now)[1]['valid']:
      raise AssertionError('비용 비교의 공통 warm baseline이 유효하지 않습니다')
    if kind == 'real_elapsed':
      clock.activate_real_elapsed()
    started = time.perf_counter_ns()
    controls = []
    original = h.control.update
    def paced(*values, **kwargs):
      target = started+round((measures.step*.05+(len(controls) % 5)*.01)*1e9)
      wait = (target-time.perf_counter_ns())*1e-9
      if wait > 0:
        measures.call('sleep_wait', time.sleep, wait)
      controls.append(time.perf_counter_ns())
      return original(*values, **kwargs)
    h.control.update = paced
    directory.mkdir(parents=True, exist_ok=True)
    stream = (directory/'plan.csv').open('w', encoding='utf-8', newline='') if record else None
    can_stream = (directory/'can_control.csv').open('w', encoding='utf-8', newline='') if record else None
    plan_writer = can_writer = None
    warm_baselines, cold_setups = 1, 1
    maximum_rss = 0
    try:
      for index in range(steps):
        if recreate_every and index and index % recreate_every == 0:
          measures.phase = 'setup_recreate'
          clock.real = False
          clock.now = 100.
          h = measures.call('setup_recreate', NativeSignalHarness, directory, clock=clock, camera_profile='ox03c10')
          install_measurements(h, measures)
          plant = measures.call('can_setup_recreate', DiagnosticCanPlant, h, dbc, measures)
          plant.fixed_sensor_feedback = True
          warm(h, receiver(), receiver(('liveCalibration', 'roadCameraState', 'deviceState')), measures, signal_mode=2)
          baseline_now = clock.now
          if not h.prepare_runtime.read(h.sm, baseline_now)[1]['valid']:
            raise AssertionError('새 객체 비교의 공통 warm baseline이 유효하지 않습니다')
          if kind == 'real_elapsed':
            clock.activate_real_elapsed()
          original = h.control.update
          h.control.update = paced
          cold_setups += 1
          warm_baselines += 1
        measures.phase = 'paced_cost'
        measures.step = index
        now = clock.now if clock.real else baseline_now+(index % recreate_every if recreate_every else index)*.05
        h.sm['modelV2'].frameId = index+1
        h.sm['modelV2'].timestampEof = int((now-.1)*1e9)
        row = h.step(now, speed=plant.speed, accel=plant.accel, plant=plant)
        if stream:
          record_plan = row | {'case': 'fixed_sensor_input', 'case_elapsed': index*.05, 'cycle': 0}
          if plan_writer is None:
            plan_writer = csv.DictWriter(stream, fieldnames=list(record_plan))
            plan_writer.writeheader()
          measures.call('record_write_plan_csv', plan_writer.writerow, record_plan)
          for sample in plant.rows[-5:]:
            record_can = {'time': sample['logical_timestamp'], 'control_index': sample['control_tick'],
                          'plan_target': sample['plan_target'], 'longcontrol_output': sample['longcontrol_output'],
                          'acc_control_created': sample['created'], 'decoded_acc_command': sample['decoded_command'],
                          'can_valid': sample['can_valid'], 'long_active': sample['fixture_active'], 'start_hold': sample['start_hold'],
                          'long_control_state': sample['long_control_state'], 'pcm_previous_request': sample['pcm_previous_request'],
                          'pcm_pid_integral': sample['pcm_pid_integral'], 'start_released': sample['start_released'],
                          'should_stop': sample['should_stop'], 'plant_speed': sample['fixed_10ms_speed'],
                          'plant_accel': sample['fixed_10ms_accel'], 'case': 'fixed_sensor_input', 'case_elapsed': index*.05, 'cycle': 0}
            if can_writer is None:
              can_writer = csv.DictWriter(can_stream, fieldnames=list(record_can))
              can_writer.writeheader()
            measures.call('record_write_control_csv', can_writer.writerow, record_can)
          if index % 1200 == 0:
            measures.call('record_flush', stream.flush)
            measures.call('record_flush_control', can_stream.flush)
        maximum_rss = max(maximum_rss, measures.call('psutil', psutil.Process().memory_info).rss)
        remaining = (started+round((index+1)*.05*1e9)-time.perf_counter_ns())*1e-9
        if remaining > 0:
          measures.call('plan_sleep_wait', time.sleep, remaining)
    finally:
      if stream:
        measures.call('record_flush', stream.flush)
        stream.close()
        measures.call('record_flush_control', can_stream.flush)
        can_stream.close()
    intervals = np.diff(controls)*1e-6
    return {'profile_kind': kind, 'record_io': record, 'steps': steps, 'control_calls': len(controls),
            'recreate_every_steps': recreate_every, 'cold_setup_count': cold_setups, 'valid_warm_baseline_count': warm_baselines,
            'actual_wall_s': (time.perf_counter_ns()-started)*1e-9, 'maximum_rss_mb': maximum_rss/2**20,
            'intercall_ms': {'min': float(intervals.min()), 'p99': float(np.percentile(intervals, 99)), 'max': float(intervals.max())},
            'can_failures': dict(plant.failures), 'fixed_plant_position': plant.fixed.position,
            'wall_plant_position': plant.wall.position, 'carparams_unchanged': h.unchanged_cp(),
            'fixed_sensor_values_for_cost_comparison': True, 'csv_plan_rows': steps if record else 0,
            'csv_control_rows': steps*5 if record else 0,
            'csv_flush_every_steps': 1200, 'csv_flush_nominal_seconds': 60.,
            'restart_warmup_added_for_equal_ready_baseline': bool(recreate_every),
            'restart_warmup_cost_separately_recorded': True,
            'fresh_synthetic_periodic_input_cost_profile_only': True}


def source_fingerprints():
  result = all_source_hashes()
  for name in ('openpilot/cereal/messaging/__init__.py', 'openpilot/cereal/services.py',
               'openpilot/selfdrive/controls/plannerd.py', 'openpilot/selfdrive/controls/controlsd.py'):
    result[name] = hashlib.sha256((REPO/name).read_bytes()).hexdigest()
  result['diagnostic_timing.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  return result


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--profile-steps', type=int, default=480)
  parser.add_argument('--delay-kinds', choices=('sleep', 'cpu_work', 'both'), default='both')
  args = parser.parse_args()
  if not BUILD_ROOT.name.startswith('build_snapshot_'):
    raise RuntimeError('읽기 전용 native 스냅샷을 CARROT_VALIDATION_BUILD로 지정해야 합니다')
  args.output.mkdir(parents=True, exist_ok=True)
  dbcs = args.output/'generated_dbc'
  dbcs.mkdir(exist_ok=True)
  create_dbc(str(REPO/'opendbc_repo/opendbc/dbc/generator/toyota'), 'toyota_nodsu_pt.dbc', str(dbcs))
  dbc = dbcs/'toyota_nodsu_pt_generated.dbc'
  fingerprints = source_fingerprints()
  native_hashes = {str(path.relative_to(BUILD_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in BUILD_ROOT.rglob('*.so')}
  measures = Measurements()
  cases, profiles = [], []
  for delay_kind in ('sleep', 'cpu_work') if args.delay_kinds == 'both' else (args.delay_kinds,):
    for kind in CASE_KINDS:
      for stall in (.05, .15, .323, .6):
        cases.append(probe_stall(kind, stall, args.output/(kind+'_'+delay_kind+'_'+str(stall)), dbc, measures,
                                delay_kind=delay_kind))
  for recreate_every in (0, 240):
    for record in (False, True):
      profiles.append(profile(args.output/('profile_real_elapsed_'+str(record)+'_'+str(recreate_every)), dbc, measures,
                              steps=args.profile_steps, kind='real_elapsed', record=record, recreate_every=recreate_every))
  report = {'recorded_utc': datetime.now(UTC).isoformat(), 'cases': cases, 'profiles': profiles,
            'stage_costs': measures.summary(), 'stage_nested_in_planner': ['mpc_nested', 'start_runtime', 'prepare_runtime'],
            'stage_costs_by_phase': {phase: measures.summary([row for row in measures.rows if row['phase'] == phase])
                                   for phase in sorted({row['phase'] for row in measures.rows})},
            'source_hashes': fingerprints, 'source_unchanged': fingerprints == source_fingerprints(),
            'native_hashes': native_hashes, 'native_unchanged': native_hashes == {
              str(path.relative_to(BUILD_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in BUILD_ROOT.rglob('*.so')},
            'source_app_full_activation_gate_executed': False, 'receiver_algorithms_original_ast': True,
            'io_socket_constructor_replaced_only': True, 'clock_source_model_separate': True,
            'camera_recognition_verified': False, 'physical_safety_proven': False, 'actual_322ms_rootcause_identified': False,
            'operating_params_writes': 0, 'real_can_sent': False, 'carinterface_init_called': False}
  (args.output/'diagnostic_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  with (args.output/'stage_trace.jsonl').open('w', encoding='utf-8') as stream:
    for row in measures.rows:
      stream.write(json.dumps(row)+'\n')
  print(json.dumps({'cases': len(cases), 'profiles': len(profiles), 'stage_calls': len(measures.rows),
                    'source_unchanged': report['source_unchanged'], 'native_unchanged': report['native_unchanged']}))
  return int(not report['source_unchanged'] or not report['native_unchanged'] or
             any(case['can_failures'] or not case['carparams_unchanged'] for case in cases) or
             any(value['can_failures'] or not value['carparams_unchanged'] for value in profiles))


if __name__ == '__main__':
  raise SystemExit(main())
