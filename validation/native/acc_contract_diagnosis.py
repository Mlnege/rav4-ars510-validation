"""원형 계산은 그대로 두고 ACC 관측 유무·지연의 단계별 값을 읽어 기록한다.

알려진 필드의 합성 센서 입력이며 실제 ECU 모델이 아니다. ACC CHECK_BYTE는
미검증 placeholder0이다. 원형 메서드를 호출하는 관찰 wrapper는 결과를 바꾸지
않으며 차량·Panda·운영 Params에 접근하지 않는다.
"""
import hashlib
import json
from collections import deque
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path

from closed_loop import NativeClosedLoopPlant, Scenario
from offline_io import BUILD_ROOT, REPO_ROOT
from opendbc.can import native
from opendbc.car.toyota.ars510.objects import decode_native_slot
from opendbc.car.toyota.ars510.record import occupied_slots
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import T_IDXS
from witness_bridge import AccWitnessRadarBridge


class StageObserver(AccWitnessRadarBridge):
  def __init__(self, CP, **kwargs):
    super().__init__(CP, **kwargs)
    self.pending_truth = deque()
    self.record_rows = []
    self.last_filter = None
    self.latest_record = None
    self.current_truth = None
    decoder = self.adapter.decoder
    original_speed = decoder._fused_speed
    original_payload = decoder._payload

    def speed_observer(tid, time_s, obj, extra, v_ego=0.0):
      previous = decoder._fused.get(tid)
      cfg = decoder.config
      young = 1.0
      if obj.age < cfg.young_age:
        weight = min(max((cfg.young_age-obj.age)/max(cfg.young_age-60, 1), 0.0), 1.0)
        young = 1.0 + (cfg.young_sigma_scale-1.0)*weight
      sigma = cfg.speed_sigma_per_code * max(obj.vel_unc_code, 1) * young
      prior_p = None if previous is None or len(previous) != 3 else previous[2] + (cfg.lead_accel_std_mps2*(time_s-previous[0]))**2
      value, std = original_speed(tid, time_s, obj, extra, v_ego)
      self.last_filter = {
        "native_id": tid, "age": obj.age, "vel_unc_code": obj.vel_unc_code,
        "raw_range_m": obj.d_rel, "raw_ground_scaled_mps": obj.v_long_ground*cfg.vground_scale,
        "object_sigma_mps": sigma, "object_r": sigma*sigma, "predicted_covariance": prior_p,
        "object_gain": None if prior_p is None else prior_p/(prior_p+sigma*sigma),
        "previous_speed_mps": None if previous is None else previous[1],
        "ACC_extra_measurements": [list(item) for item in extra],
        "fused_speed_mps": value, "fused_std_mps": std,
      }
      return value, std

    def payload_observer(time_s, record):
      truth = self.pending_truth.popleft()
      if truth["payload"] != record:
        raise RuntimeError("관찰용 원본 record와 완성 record의 순서가 다릅니다")
      self.last_filter = None
      decoded = original_payload(time_s, record)
      row = {key: value for key, value in truth.items() if key != 'payload'}
      row["decoder_first_frame_time_s"] = time_s-self.origin
      row["filter"] = self.last_filter
      range_state = None if self.last_filter is None else decoder._range_est.get(self.last_filter['native_id'])
      row["fused_internal_range_m"] = None if range_state is None else range_state[1]
      row["fused_points"] = [dict(point) for point in decoded['radarData']['points']]
      row["acc_associated"] = decoder._acc_assoc is not None
      row["acc_vrel_age_s"] = None if decoder._acc_vrel is None else time_s-decoder._acc_vrel[0]
      row["acc_position_age_s"] = None if decoder._acc_pos is None else time_s-decoder._acc_pos[0]
      self.latest_record = row
      self.record_rows.append(row)
      return decoded

    decoder._fused_speed = speed_observer
    decoder._payload = payload_observer

  def _record(self, truth):
    record = super()._record(truth)
    raw = [asdict(decode_native_slot(slot, segment)) for slot, segment in occupied_slots(record)]
    self.pending_truth.append({"payload": record, "generation_time_s": self.next_record-self.period_s-self.origin,
                               "truth_at_generation": dict(truth), "raw_objects": raw})
    return record

  def update(self, **kwargs):
    self.current_truth = dict(kwargs['truth'])
    return super().update(**kwargs)


def true_future_range(gap, speed, horizon, braking):
  if not braking:
    return gap+speed*horizon
  moving_time = min(horizon, max(0.0, speed)/5.0)
  return gap+speed*moving_time-2.5*moving_time*moving_time


def model_row(plant, bridge, now):
  lead = plant.sm['radarState'].leadOne
  point = bridge.last_rr.points[0] if bridge.last_rr.points else None
  track = None if point is None else bridge.adapter.tracks.get(int(point.trackId))
  trajectory, _ = plant.planner.mpc.process_lead(lead)
  horizon_index = min(range(len(T_IDXS)), key=lambda index: abs(float(T_IDXS[index])-1.0))
  horizon = float(T_IDXS[horizon_index])
  latest = bridge.latest_record
  fused = None if latest is None or not latest['fused_points'] else latest['fused_points'][0]
  filter_state = None if latest is None else latest['filter']
  truth = bridge.current_truth
  row = {
    "model_time_s": now, "true_gap_m": truth['gap_m'], "true_lead_speed_mps": truth['lead_speed_mps'],
    "v_ego_mps": float(plant.sm['carState'].vEgo), "true_lead_accel_mps2": truth['lead_accel_mps2'],
    "record_generation_s": None if latest is None else latest['generation_time_s'],
    "record_generation_age_s": None if latest is None else now-latest['generation_time_s'],
    "raw_age": None if latest is None or not latest['raw_objects'] else latest['raw_objects'][0]['age'],
    "raw_range_m": None if filter_state is None else filter_state['raw_range_m'],
    "raw_ground_scaled_mps": None if filter_state is None else filter_state['raw_ground_scaled_mps'],
    "fused_range_m": None if fused is None else fused['dRel'],
    "fused_speed_mps": None if fused is None else fused['v_long_ground'],
    "object_gain": None if filter_state is None else filter_state['object_gain'],
    "object_sigma_mps": None if filter_state is None else filter_state['object_sigma_mps'],
    "acc_extra_count": 0 if filter_state is None else len(filter_state['ACC_extra_measurements']),
    "mytrack_range_m": None if point is None else float(point.dRel),
    "mytrack_speed_mps": None if point is None else float(point.vLead),
    "mytrack_accel_mps2": None if point is None else float(point.aLead),
    "mytrack_count": None if track is None else track.cnt,
    "DPath_lead_status": bool(lead.status), "DPath_lead_radar": bool(lead.radar),
    "DPath_range_m": float(lead.dRel), "DPath_speed_mps": float(lead.vLead),
    "DPath_accel_mps2": float(lead.aLeadK), "DPath_aLeadTau": float(lead.aLeadTau),
    "mpc_source": plant.planner.mpc.source, "mpc_current_lead_range_m": float(trajectory[0, 0]),
    "mpc_convergence_clip_m": None if not lead.status else float(trajectory[0, 0])-float(lead.dRel),
    "prediction_horizon_s": horizon, "mpc_future_lead_range_m": float(trajectory[horizon_index, 0]),
    "true_future_lead_range_m": true_future_range(truth['gap_m'], truth['lead_speed_mps'], horizon, now >= 7.0),
    "planner_accel_target_mps2": float(plant.planner.output_a_target), "decoded_ACC_CMD_mps2": plant.command,
    "native_status": plant.planner.mpc.solution_status,
  }
  return row


def first(rows, predicate):
  return next((row for row in rows if row['model_time_s'] >= 7.0 and predicate(row)), None)


def summarize(models, records):
  after = [row for row in models if row['model_time_s'] >= 7.0]
  switch = next((row for previous, row in pairwise(after) if not previous['DPath_lead_radar'] and row['DPath_lead_radar']), None)
  raw_errors = []
  for record in records:
    if record['generation_time_s'] < 7.0 or not record['raw_objects']:
      continue
    raw = record['raw_objects'][0]
    raw_errors.append(abs(raw['v_long_ground']*.149/.15-record['truth_at_generation']['lead_speed_mps']))
  return {
    "raw_max_quantization_error_mps": max(raw_errors, default=0.0),
    "first_internal_fused_speed_above_raw_by_0_15": next((r for r in records if r['generation_time_s'] >= 7.0
      and r['filter'] is not None and r['filter']['fused_speed_mps']-r['filter']['raw_ground_scaled_mps'] > .15), None),
    "first_internal_fused_range_above_raw_by_0_15": next((r for r in records if r['generation_time_s'] >= 7.0
      and r['fused_internal_range_m'] is not None and r['fused_internal_range_m']-r['filter']['raw_range_m'] > .15), None),
    "first_fused_speed_above_raw_by_0_15": first(models, lambda r: r['fused_speed_mps'] is not None and r['fused_speed_mps']-r['raw_ground_scaled_mps'] > .15),
    "first_fused_speed_above_current_truth_by_0_5": first(models, lambda r: r['fused_speed_mps'] is not None and r['fused_speed_mps']-r['true_lead_speed_mps'] > .5),
    "first_fused_range_above_current_truth_by_0_5": first(models, lambda r: r['fused_range_m'] is not None and r['fused_range_m']-r['true_gap_m'] > .5),
    "first_MPC_clip_above_observed_range": first(models, lambda r: r['mpc_convergence_clip_m'] is not None and r['mpc_convergence_clip_m'] > 1e-6),
    "first_vision_to_radar_after_brake": switch,
    "integer_second_samples": [r for r in models if 7 <= r['model_time_s'] <= 12 and abs(r['model_time_s']-round(r['model_time_s'])) < 1e-9],
  }


def main():
  root = Path(__file__).parent / 'acc_contract_diagnosis'
  root.mkdir(exist_ok=True)
  summary = []
  cases = [(mode, delay) for delay in (0.0, .05, .15) for mode in ('full', 'missing')]
  cases += [('idle', 0.0), ('stale', 0.0)]
  for mode, delay in cases:
    scenario = Scenario(f'{mode}_delay_{delay:.2f}', duration=15, lead=True, initial_speed=20,
                        lead_speed=20, cruise_speed=20, gap=60, event_time=7, lead_brake=5)
    plant = NativeClosedLoopPlant(scenario)
    bridge = StageObserver(plant.CP, witness_mode=mode, sensor_delay_s=delay)
    plant.radar_bridge = bridge
    model_rows = []
    while plant.step_index*plant.dt < scenario.duration:
      now = plant.step_index*plant.dt
      plant.step()
      if (plant.step_index-1) % plant.model_divisor == 0:
        model_rows.append(model_row(plant, bridge, now))
      if plant.first_overlap is not None:
        break
    result = {
      "name": scenario.name, "sensor_delay_s": delay, "witness_mode": mode, "synthetic_known_fields_only": True,
      "check_byte": 'unverified_placeholder_zero', "real_vehicle_tx_count": 0,
      "CP_radarUnavailable": plant.CP.radarUnavailable, "CP_radarDelay": plant.CP.radarDelay,
      "first_contact_time_s": plant.first_overlap,
      "first_contact_gap_m": None if plant.first_overlap is None else plant.lead_distance-plant.distance,
      "post_contact_trajectory_kept": False, "minimum_gap_before_or_at_contact_m": plant.minimum_gap,
      "final_speed_mps": plant.speed, "native_status": dict(plant.native_status),
      "ACC_decode_errors": plant.decoder_failures, "diagnosis": summarize(model_rows, bridge.record_rows),
      "bridge": bridge.summary(), "filter_config": asdict(bridge.adapter.decoder.config),
    }
    artifact = result | {"records": bridge.record_rows, "models": model_rows}
    (root/(scenario.name+'.json')).write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    summary.append(result)
    print(json.dumps({k: result[k] for k in ('name', 'first_contact_time_s', 'first_contact_gap_m', 'final_speed_mps')}, ensure_ascii=False), flush=True)
  metadata = {
    "native_build": str(BUILD_ROOT),
    "CAN_raw_backend": native.BACKEND,
    "MPC_backend": 'acados_C_Cython',
    "Safety_backend": 'not_invoked_in_this_observer',
    "source_sha256": {str(path.relative_to(REPO_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
      REPO_ROOT/'opendbc_repo/opendbc/car/toyota/ars510/interface.py',
      REPO_ROOT/'openpilot/selfdrive/carrot/radar_motion/controller.py',
      REPO_ROOT/'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py',
    )},
  }
  (root/'summary.json').write_text(json.dumps({'metadata': metadata, 'cases': summary}, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
  main()
