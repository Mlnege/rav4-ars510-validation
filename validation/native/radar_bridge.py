"""명시한 가상 센서 입력을 실제 ARS 조립·fused·당근 코어로 연결한다.

패킷의 알려진 거리·속도·age만 공개 슬롯 형식으로 인코딩한다. 이 입력은
합성 시뮬레이션이며 실물 ECU 식별·센서 정확도의 증거가 아니다.
"""
from collections import Counter, deque
import csv
import zlib

from offline_io import REPO_ROOT
from openpilot.cereal import car, log
from openpilot.selfdrive.carrot.radar_motion import DPathRadarController
from openpilot.selfdrive.carrot.radar_motion.timing import front_radar_distance_delay_s
from opendbc.car.toyota.ars510.constants import ID80_IDLE_SLOT
from opendbc.car.toyota.ars510.record import occupied_slots
from opendbc.car.toyota.ars510_offline import Ars510OfflineRadarInterface


def _code(data, start, length, value):
    bits = int.from_bytes(data, "little")
    mask = ((1 << length) - 1) << start
    bits = (bits & ~mask) | ((int(value) << start) & mask)
    return bits.to_bytes(len(data), "little")


def public_record():
    fixture = REPO_ROOT / "tools/ars510_offline/fixtures/public_id80_record.csv"
    with fixture.open(encoding="utf-8") as stream:
        return b"".join(bytes.fromhex(row["data_hex"])[1:] for row in csv.DictReader(stream))


class ArsRadarBridge:
    def __init__(self, CP, *, period_s=.06, transport_s=.0315, sensor_delay_s=0.0,
                 dropout_interval=None, corruption_interval=None):
        self.adapter = Ars510OfflineRadarInterface(CP, offline=True)
        self.controller = DPathRadarController(enable_radar_tracks=1, production_live_tracks=True,
                                             front_radar_measurement_delay_s=front_radar_distance_delay_s(CP))
        self.base_record = public_record()
        self.base_slot = next(occupied_slots(self.base_record))[1]
        self.period_s, self.transport_s = period_s, transport_s
        self.sensor_delay_s = sensor_delay_s
        self.dropout_interval, self.corruption_interval = dropout_interval, corruption_interval
        self.next_record = None
        self.origin = None
        self.age = 0
        self.queue = deque()
        self.last_rr = car.RadarData()
        self.last_rr.errors.radarUnavailableTemporary = True
        self.last_publication = None
        self.latest_state = log.RadarState()
        self.metrics = Counter()
        self.healthy = False

    def _record(self, truth):
        record = bytearray(self.base_record)
        for index in range(20):
            record[17 + index * 36:53 + index * 36] = ID80_IDLE_SLOT
        present = bool(truth["present"]) and 0 < truth["gap_m"] < 245
        if present:
            self.age = min(126, self.age + 1)
            fields = [(2, 6, 0), (24, 7, self.age),
                      (32, 12, round(truth["gap_m"] * 16 + 160)),
                      (44, 12, round(truth["y_rel_m"] / .015 + 2048)),
                      (64, 10, round(truth["lead_speed_mps"] / .149 + 510.5)),
                      (74, 10, round(truth.get("y_velocity_mps", 0.0) / .15 + 510.5)),
                      (107, 1, 0)]
            slot = self.base_slot
            for start, length, value in fields:
                slot = _code(slot, start, length, max(0, min((1 << length) - 1, value)))
            record[17:53] = slot
        else:
            self.age = 0
        record[14:16] = _code(record[14:16], 3, 5, int(present))
        record[737:741] = zlib.crc32(record[1:737]).to_bytes(4, "little")
        return bytes(record)

    @staticmethod
    def _inside(interval, time_s):
        return interval is not None and interval[0] <= time_s < interval[1]

    def update(self, *, now_s, v_ego, a_ego, model, truth):
        if self.origin is None:
            self.origin = self.next_record = now_s
        speed_code = max(0, min(65535, round(v_ego * 3.6 * 100)))
        wheel = bytes(5) + speed_code.to_bytes(2, "big") + bytes(1)
        yaw = round(125.0 / .244).to_bytes(2, "big") + bytes(6)
        self.queue.append((now_s, (0xb4, wheel, 0)))
        self.queue.append((now_s, (0x24, yaw, 0)))
        while self.next_record <= now_s + 1e-9:
            timestamp = self.next_record
            self.next_record += self.period_s
            age_time = timestamp - self.origin
            record = self._record(truth)
            if self._inside(self.dropout_interval, age_time):
                self.metrics["dropped_records"] += 1
                continue
            if self._inside(self.corruption_interval, age_time):
                corrupted = bytearray(record)
                corrupted[100] ^= 1
                record = bytes(corrupted)
            for index in range(106):
                header = 0x12 if index == 0 else 0x20 | (index & 15)
                dat = bytes([header]) + record[index * 7:index * 7 + 7]
                arrival = timestamp + self.sensor_delay_s + self.transport_s * index / 105
                self.queue.append((arrival, (0x80, dat, 1)))
            self.metrics["scheduled_records"] += 1
        # 주기 경계의 차량 속도와 미완성 레코드를 수신 시각 순서로 처리한다.
        self.queue = deque(sorted(self.queue, key=lambda item: item[0]))
        packets = []
        while self.queue and self.queue[0][0] <= now_s + 1e-9:
            arrival, frame = self.queue.popleft()
            packets.append((round(arrival * 1e9), [frame]))
        result = self.adapter.update_carrot(v_ego, a_ego, now_s, packets)
        if result is not None:
            event = log.Event(logMonoTime=round(now_s * 1e9))
            event.liveTracks = result
            with log.Event.from_bytes(event.to_bytes()) as serialized:
                self.last_rr = serialized.liveTracks.as_builder()
            self.last_publication = now_s
            self.healthy = not any(self.last_rr.errors.to_dict().values())
            self.metrics["liveTracks"] += 1
            self.metrics["radar_point_samples"] += len(self.last_rr.points)
            self.metrics["unavailable_updates"] += int(not self.healthy)
        if model.frameId != getattr(self, "previous_model_frame", None):
            self.previous_model_frame = model.frameId
            output = self.controller.update(time_s=now_s, v_ego=v_ego, radar_points=self.last_rr.points,
                                            model=model, yaw_rate_rad_s=0.0,
                                            radar_to_model_time_s=0.0 if self.last_publication is None else now_s-self.last_publication)
            state = log.RadarState()
            state.radarErrors = self.last_rr.errors
            if output.lead_one:
                state.leadOne = output.lead_one
            if output.lead_two:
                state.leadTwo = output.lead_two
            if output.lead_cutin_risk:
                state.leadCutInRisk = output.lead_cutin_risk
            with log.RadarState.from_bytes(state.to_bytes()) as serialized:
                self.latest_state = serialized.as_builder()
            self.metrics["model_steps"] += 1
            self.metrics["radar_leadOne"] += int(self.latest_state.leadOne.radar)
            self.metrics["vision_leadOne"] += int(self.latest_state.leadOne.status and not self.latest_state.leadOne.radar)
            self.metrics["leadTwo"] += int(self.latest_state.leadTwo.status)
        return self.latest_state

    def summary(self):
        return {"metrics": dict(self.metrics), "adapter": self.adapter.diagnostics,
                "sensor_input": "synthetic_known_ARS_fields", "stock_ACC_target_simulated": False,
                "period_s": self.period_s, "transport_s": self.transport_s, "sensor_delay_s": self.sensor_delay_s}
