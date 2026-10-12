"""기존 합성 trace의 변곡점만 읽는다. 주행 코어나 시뮬레이션을 실행하지 않는다."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
SOURCES = [
  'opendbc_repo/opendbc/car/toyota/ars510/interface.py',
  'opendbc_repo/opendbc/car/toyota/ars510_offline.py',
  'opendbc_repo/opendbc/car/toyota/carcontroller.py',
  'opendbc_repo/opendbc/car/radar_tracks.py',
  'opendbc_repo/opendbc/car/interfaces.py',
  'openpilot/selfdrive/carrot/radar/radard_dpath.py',
  'openpilot/selfdrive/carrot/radar_motion/controller.py',
  'openpilot/selfdrive/carrot/radar_motion/primary.py',
  'openpilot/selfdrive/carrot/radar_motion/lead_dynamics.py',
  'openpilot/selfdrive/controls/lib/longitudinal_planner.py',
  'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py',
  'openpilot/selfdrive/controls/lib/drive_helpers.py',
  'openpilot/selfdrive/selfdrived/selfdrived.py',
  'openpilot/selfdrive/selfdrived/events.py',
]
GRID_NAMES = ['gap55_accfull_noise0.0_delay0.0', 'gap55_accmissing_noise0.0_delay0.0',
              'gap60_accmissing_noise0.0_delay0.0', 'gap65_accmissing_noise0.0_delay0.0',
              'gap60_accmissing_noise0.0_delay0.0_analysis_only_far_gate_off',
              'gap60_accmissing_noise0.0_delay0.0_analysis_only_min_age_1']
MODEL_FIELDS = ['model_time_s', 'true_gap_m', 'true_lead_speed_mps', 'raw_ground_scaled_mps',
                'fused_range_m', 'fused_speed_mps', 'mytrack_count', 'mytrack_accel_mps2',
                'DPath_lead_status', 'DPath_lead_radar', 'DPath_range_m', 'DPath_speed_mps',
                'DPath_accel_mps2', 'DPath_aLeadTau', 'mpc_source', 'prediction_horizon_s',
                'mpc_future_lead_range_m', 'true_future_lead_range_m', 'mpc_convergence_clip_m',
                'planner_accel_target_mps2', 'decoded_ACC_CMD_mps2']
hashes = {}


def read(relative):
  path = ROOT / relative
  raw = path.read_bytes()
  hashes[relative] = hashlib.sha256(raw).hexdigest()
  return raw.decode('utf-8')


def sample(row):
  value = {key: row[key] for key in MODEL_FIELDS}
  value['saved_lead_future_minus_own_truth_m'] = (
    row['mpc_future_lead_range_m'] - row['true_future_lead_range_m']
    if row['DPath_lead_status'] else None)
  return value


def main():
  target = OUTPUT / 'observations.json'
  manifest = OUTPUT / 'input_manifest.json'
  if target.exists() or manifest.exists():
    raise RuntimeError('동결된 출력은 덮어쓰지 않습니다')
  grid = []
  for name in GRID_NAMES:
    data = json.loads(read(f'work/fusion_contract_grid/{name}.json'))
    contact = data['first_contact_s']
    rows = [row for row in data['models'] if contact is None or row['model_time_s'] <= contact]
    grid.append({'name': name, 'first_radar_l1': data['first_radar_l1'],
                 'first_contact_s': contact, 'contact_gap_m': data['first_contact_gap_m'],
                 'software_analysis_only_not_for_vehicle': data['software_analysis_only_not_for_vehicle'],
                 'samples': [sample(min(rows, key=lambda row: abs(row['model_time_s']-time)))
                             for time in (7.0, 7.2, 7.25, 8.0, 8.9, 9.0)]})
  observation = list(csv.DictReader(read('work/native_sim/stop_inspection/observation.csv').splitlines()))
  loss = next(row for previous, row in zip(observation, observation[1:])
              if previous['lead_status'] == 'True' and row['lead_status'] == 'False')
  loss_time = float(loss['time_s'])
  summary = json.loads(read('work/native_sim/stop_inspection/summary.json'))
  contact = summary['first_geometric_overlap_s']
  control = list(csv.DictReader(read('work/native_sim/stop_inspection/ars_near_stop.csv').splitlines()))
  valid = [row for row in control if loss_time <= float(row['t_s']) <= contact]
  released = next(row for row in valid if row['should_stop'] == '0')
  positive = next(row for row in valid if float(row['acc_command_mps2']) > 0)
  witnesses = json.loads(read('work/native_sim/witness_sensitivity/summary.json'))
  witness_counts = [{key: case.get(key) for key in
                    ('name', 'first_geometric_overlap_s', 'post_contact_trajectory_valid')}
                   | {'retain_near': case['ars']['retain_near'], 'witness_mode': case['ars']['witness_mode'],
                      'final_speed_without_contact_mps': case['final_speed'] if case['first_geometric_overlap_s'] is None else None}
                   for case in witnesses]
  for path in SOURCES:
    read('work/carrotpilot/' + path)
  for path in ('work/native_sim/closed_loop.py', 'work/native_sim/radar_bridge.py',
               'work/native_sim/witness_bridge.py', 'work/fusion_contract_grid/run_grid.py',
               'work/native_sim/acc_contract_diagnosis.py'):
    read(path)
  current = json.loads(read('work/fusion_contract_grid/summary.json'))['metadata']['source_sha256']
  meta = {'direct_execution_scope_ko': '이번 직접 실행은 기존 JSON/CSV의 선택·산술·지문 수집뿐이다. 새로운 시뮬레이션·C/MPC 실행은 없다.',
          'input_scope_ko': '변곡값은 합성 plant와 known-field ARS fixture다. 실제 CAN/실물 제동 결과가 아니다.',
          'CAN_backend': 'python', 'MPC_backend': '보존 실험은 C/Cython, 이번 도구는 실행하지 않음',
          'near_control_time_ko': '관측 CSV는 적분 전 센서/lead, control CSV의 차량 상태는 해당 step 적분 후다. CAN 양수 시각은20Hz 보존 표본이며 새 CAN 발행시각의 직접 기록이 아니다.',
          'error_flags_observed_per_step': False, 'measured_flag_observed_in_near_csv': False,
          'current_source_equals_grid_recorded': {path: hashes['work/carrotpilot/'+path] == value
                                                 for path, value in current.items()}}
  target.write_text(json.dumps({'metadata': meta, 'grid': grid, 'near_loss': loss,
                               'near_should_stop_release': released, 'near_first_positive_CAN_sample': positive,
                               'near_first_contact_s': contact, 'witness_cases': witness_counts},
                              ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
  hashes['work/radar_loss_planning_review/extract_preserved.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  manifest.write_text(json.dumps({'files': hashes, 'scope_ko': '현재 읽은 입력·source 지문이다. 실행 당시 지문 전체를 새로 수집한 것으로 소급하지 않는다.'},
                                ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps({'grid_cases_read': len(grid), 'first_loss_s': loss_time,
                    'should_stop_release_s': float(released['t_s']),
                    'positive_CAN_sample_s': float(positive['t_s']), 'input_files_hashed': len(hashes)}))


if __name__ == '__main__':
  main()
