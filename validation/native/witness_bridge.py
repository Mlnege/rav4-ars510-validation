"""원형 fused에 필요한 ACC 관측을 명시적 합성 입력으로 추가한다.

0x235/0x237의 필드는 원형 DBC·support decoder와 동일하다. CHECK_BYTE의 실물
검증 알고리즘은 확인하지 않았으므로 상위 바이트0은 placeholder이다. ECU가
유효하다고 판단할 프레임이나 실차 호환 증거가 아니며 차량 송신은 하지 않는다.
"""
import math

from radar_bridge import ArsRadarBridge
from openpilot.selfdrive.carrot.radar_motion import DPathRadarController
from openpilot.selfdrive.carrot.radar_motion.timing import front_radar_distance_delay_s
from opendbc.car.toyota.ars510.support import parse_acc_target


def _put(value, start, length, code):
  if not 0 <= code < 1 << length:
    raise ValueError("합성 ACC 필드 범위를 벗어났습니다")
  return value | (int(code) << start)


def encode_acc_witness(truth, v_ego, a_ego, counter=0, *, active=True):
  gap, lateral = float(truth["gap_m"]), float(truth["y_rel_m"])
  relative_speed = float(truth["lead_speed_mps"] - v_ego)
  relative_accel = float(truth["lead_accel_mps2"] - a_ego)
  active = (active and bool(truth["present"]) and all(math.isfinite(v) for v in
            (gap, lateral, relative_speed, relative_accel)) and 0 < gap <= 204.775
            and -20.0 <= lateral <= 20.95 and -128.0 <= relative_speed <= 127.875
            and -12.5 <= relative_accel <= 19.375)
  data235 = _put(0, 52, 4, counter & 15)
  data235 = _put(data235, 48, 4, 5 if active else 0)
  data235 = _put(data235, 29, 11, round(relative_speed / .125) + 1024 if active else 1024)
  data235 = _put(data235, 40, 8, round(relative_accel / .125) + 100 if active else 100)
  data235 = _put(data235, 8, 11, 1024)
  data235 = _put(data235, 19, 8, 100)
  data235 = _put(data235, 0, 5, 1 if active else 0)
  data237 = _put(0, 52, 4, counter & 15)
  data237 = _put(data237, 39, 13, round(gap / .025) if active else 0)
  data237 = _put(data237, 27, 12, round(lateral / .01) + 2000 if active else 2000)
  data237 = _put(data237, 10, 1, int(active))
  data237 = _put(data237, 8, 1, int(active))
  data237 = _put(data237, 4, 3, 5 if active else 0)
  frames = data235.to_bytes(8, "big"), data237.to_bytes(8, "big")
  decoded = parse_acc_target(*frames)
  assert (decoded is not None) == bool(active)
  return frames


class AccWitnessRadarBridge(ArsRadarBridge):
  def __init__(self, CP, *, witness_mode="full", stale_after_s=3.0, retain_near=False, **kwargs):
    super().__init__(CP, **kwargs)
    if witness_mode not in ("full", "missing", "idle", "stale"):
      raise ValueError("합성 ACC 관측 모드를 확인할 수 없습니다")
    self.witness_mode, self.stale_after_s = witness_mode, stale_after_s
    self.next_witness = None
    self.witness_origin = None
    self.witness_counter = 0
    self.controller = DPathRadarController(enable_radar_tracks=1, production_live_tracks=True,
                                          front_radar_measurement_delay_s=front_radar_distance_delay_s(CP),
                                          retain_confirmed_near_front=retain_near)

  def update(self, *, now_s, v_ego, a_ego, model, truth):
    if self.next_witness is None:
      self.witness_origin = self.next_witness = now_s
    while self.next_witness <= now_s + 1e-9:
      sample_s = self.next_witness
      self.next_witness += self.period_s
      if self.witness_mode == "missing" or (self.witness_mode == "stale" and sample_s-self.witness_origin >= self.stale_after_s):
        continue
      frames = encode_acc_witness(truth, v_ego, a_ego, self.witness_counter,
                                  active=self.witness_mode != "idle")
      self.witness_counter += 1
      for address, data in zip((0x235, 0x237), frames, strict=True):
        self.queue.append((sample_s + self.sensor_delay_s, (address, data, 1)))
      self.metrics["synthetic_ACC_pairs"] += 1
    return super().update(now_s=now_s, v_ego=v_ego, a_ego=a_ego, model=model, truth=truth)

  def summary(self):
    return super().summary() | {"stock_ACC_target_simulated": self.witness_mode != "missing",
                               "witness_mode": self.witness_mode, "check_byte": "unverified_placeholder_zero",
                               "real_vehicle_tx_count": 0, "retain_near": self.controller.retain_confirmed_near_front}
