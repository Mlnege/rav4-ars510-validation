"""확인된 가상 거리·속도 입력과 공개 소프트웨어 조건을 별도로 비교한다.

실물 ECU 모델이 아니며 불확실성 코드47과 알 수 없는 필드는 건드리지 않는다.
노이즈는 임의의 실험용 범위±0.3m/s이고 제조사 물리 sigma가 아니다. 원형
wrapper는 반환값을 바꾸지 않는다. 모든 결과는 첫 가상 접촉에서 종료한다.
"""
import hashlib
import inspect
import json
import random
import sys
from dataclasses import asdict, replace
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT/'work/native_sim'))
from acc_contract_diagnosis import StageObserver, model_row
from closed_loop import NativeClosedLoopPlant, Scenario
from offline_io import BUILD_ROOT, REPO_ROOT
from opendbc.can import native
from opendbc.car.toyota.ars510.interface import FUSED_CONFIG, Ars510NativeRadarInterface
from opendbc.car.toyota.ars510.objects import decode_native_slot
from opendbc.car.toyota.ars510.record import id80_crc_ok, occupied_slots
from radar_bridge import ArsRadarBridge


class GridObserver(StageObserver):
  def __init__(self, CP, *, noise_bound=0., seed=20261012, counterfactual=None, **kwargs):
    super().__init__(CP, **kwargs)
    self.random = random.Random(seed)
    self.noise_bound = noise_bound
    self.first_point = None
    self.first_l1 = None
    self.first_radar_l1 = None
    if counterfactual == 'far_gate_off':
      # 원형은 값>0일 때만 far gate를 적용하므로0은 이 소프트웨어 조건만 끈다.
      assert 'cfg.far_acc_only_m > 0' in inspect.getsource(Ars510NativeRadarInterface._payload)
      self.adapter.decoder.config = replace(FUSED_CONFIG, far_acc_only_m=0.)
    elif counterfactual == 'min_age_1':
      self.adapter.decoder.config = replace(FUSED_CONFIG, min_publish_age=1)
    elif counterfactual is not None:
      raise ValueError('허용되지 않은 분석 전용 조건입니다')

  def _record(self, truth):
    measurement = dict(truth)
    noise = self.random.uniform(-self.noise_bound, self.noise_bound) if self.noise_bound else 0.
    measurement['lead_speed_mps'] += noise
    # raw 객체 속도만 가상 관측으로 흔들며 ACC 관측은 원래 truth를 유지한다.
    record = ArsRadarBridge._record(self, measurement)
    assert id80_crc_ok(record)
    raw = [asdict(decode_native_slot(slot, segment)) for slot, segment in occupied_slots(record)]
    if any(value['vel_unc_code'] != 47 for value in raw):
      raise RuntimeError('기존 공개 슬롯의 불확실성 코드가 바뀌었습니다')
    self.pending_truth.append({'payload': record, 'generation_time_s': self.next_record-self.period_s-self.origin,
                               'truth_at_generation': dict(truth), 'raw_objects': raw,
                               'synthetic_velocity_noise_mps': noise})
    return record

  def update(self, **kwargs):
    previous_records = len(self.record_rows)
    previous_models = self.metrics['model_steps']
    result = super().update(**kwargs)
    now = kwargs['now_s']-self.origin
    for record in self.record_rows[previous_records:]:
      if record['fused_points'] and self.first_point is None:
        point = record['fused_points'][0]
        self.first_point = {'generation_s': record['generation_time_s'],
                            'first_frame_s': record['decoder_first_frame_time_s'],
                            'completed_s': self.adapter._completion_time_s-self.origin,
                            'publication_s': now, 'point_age': point['age'],
                            'range_m': point['dRel'], 'speed_mps': point['v_long_ground']}
    if self.metrics['model_steps'] > previous_models and result.leadOne.status:
      observation = {'time_s': now, 'radar': bool(result.leadOne.radar), 'range_m': float(result.leadOne.dRel),
                     'speed_mps': float(result.leadOne.vLead), 'aLead_mps2': float(result.leadOne.aLeadK)}
      if self.first_l1 is None:
        self.first_l1 = observation
      if result.leadOne.radar and self.first_radar_l1 is None:
        self.first_radar_l1 = observation
    return result


def run_case(gap, mode, noise, delay=0., *, counterfactual=None):
  name = f'gap{gap}_acc{mode}_noise{noise:.1f}_delay{delay:.1f}'
  if counterfactual:
    name += '_analysis_only_'+counterfactual
  scenario = Scenario(name, duration=20, lead=True, initial_speed=20, lead_speed=20, cruise_speed=20,
                      gap=gap, event_time=7, lead_brake=5)
  plant = NativeClosedLoopPlant(scenario)
  bridge = GridObserver(plant.CP, witness_mode=mode, noise_bound=noise, sensor_delay_s=delay,
                        counterfactual=counterfactual)
  plant.radar_bridge = bridge
  first_negative = first_negative_after = None
  rows = []
  while plant.step_index*plant.dt < scenario.duration:
    now = plant.step_index*plant.dt
    previous_acc_messages = plant.acc_messages
    plant.step()
    if plant.acc_messages > previous_acc_messages and plant.command < 0.:
      if first_negative is None:
        first_negative = now
      if now >= 7. and first_negative_after is None:
        first_negative_after = now
    if (plant.step_index-1) % plant.model_divisor == 0:
      rows.append(model_row(plant, bridge, now))
    if plant.first_overlap is not None:
      break
  onset = next(row for row in rows if row['model_time_s'] >= 7.)
  radar_first = next((row for row in rows if row['DPath_lead_radar']), None)
  result = {
    'name': name, 'gap_m': gap, 'ACC_witness': mode, 'raw_noise_bound_mps': noise,
    'raw_noise_definition': '실험용 동일seed uniform 범위±noise, 실물sigma아님', 'sensor_delay_s': delay,
    'velocity_uncertainty_code': 47, 'counterfactual': counterfactual,
    'software_analysis_only_not_for_vehicle': counterfactual is not None,
    'filter_config': asdict(bridge.adapter.decoder.config),
    'first_complete_point': bridge.first_point, 'first_l1': bridge.first_l1,
    'first_radar_l1': bridge.first_radar_l1,
    'first_negative_new_CAN_any_s': first_negative,
    'first_negative_new_CAN_after_event_s': first_negative_after,
    'negative_CAN_after_event_delay_s': None if first_negative_after is None else first_negative_after-7.,
    'first_contact_s': plant.first_overlap,
    'first_contact_gap_m': None if plant.first_overlap is None else plant.lead_distance-plant.distance,
    'post_contact_trajectory_kept': False, 'minimum_gap_before_or_at_contact_m': plant.minimum_gap,
    'final_speed_mps': plant.speed, 'model_steps': len(rows), 'control_steps': plant.step_index,
    'event_onset_model': onset, 'first_radar_model': radar_first,
    'native_MPC_status': dict(plant.native_status), 'CAN_decode_errors': plant.decoder_failures,
    'CAN_raw_backend': native.BACKEND, 'MPC_backend': 'acados_C_Cython', 'Safety_backend': 'not_invoked',
    'synthetic_known_fields_only': True, 'CHECK_BYTE': 'unverified_placeholder_zero', 'real_vehicle_tx_count': 0,
    'bridge': bridge.summary(),
  }
  return result, rows, bridge.record_rows


def main():
  root = Path(__file__).resolve().parent
  cases = [(gap, mode, noise, 0., None) for gap in (55, 60, 65) for mode in ('full', 'missing') for noise in (0., .3)]
  cases += [(gap, mode, 0., .1, None) for gap in (55, 60) for mode in ('full', 'missing')]
  cases += [(60, 'missing', 0., 0., condition) for condition in ('far_gate_off', 'min_age_1')]
  summary = []
  for gap, mode, noise, delay, condition in cases:
    result, rows, records = run_case(gap, mode, noise, delay, counterfactual=condition)
    (root/(result['name']+'.json')).write_text(json.dumps(result | {'models': rows, 'records': records}, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    summary.append(result)
    print(json.dumps({key: result[key] for key in ('name', 'first_complete_point', 'first_radar_l1',
                                                'first_negative_new_CAN_after_event_s', 'first_contact_s',
                                                'minimum_gap_before_or_at_contact_m')}, ensure_ascii=False), flush=True)
  metadata = {'CAN_raw_backend': native.BACKEND, 'MPC_backend': 'acados_C_Cython', 'Safety_backend': 'not_invoked',
              'immutable_native_build': str(BUILD_ROOT),
              'uncertainty_unit_confidence': 'VEL_UNC_240는likely이며 library환산은내부가정이다. 실물sigma로확정하지않는다',
              'source_sha256': {str(path.relative_to(REPO_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
                REPO_ROOT/'opendbc_repo/opendbc/car/toyota/ars510/interface.py',
                REPO_ROOT/'opendbc_repo/opendbc/car/toyota/carcontroller.py',
                REPO_ROOT/'openpilot/selfdrive/carrot/radar_motion/controller.py',
              )}}
  (root/'summary.json').write_text(json.dumps({'metadata': metadata, 'cases': summary}, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
  main()
