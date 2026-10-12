"""실제 로그의 차량 속도 기준 차이를 관찰하며 제어·설정·원본 자료를 저장하지 않는다."""
import argparse
import io
import json
import math
import sys
from bisect import bisect_right
from collections import Counter
from contextlib import redirect_stdout
from hashlib import sha256
from pathlib import Path

import numpy as np
import zstandard

ROOT = Path(__file__).resolve().parents[1]
arguments = argparse.ArgumentParser(description=__doc__)
arguments.add_argument("--source-dir", type=Path, default=ROOT / "work/carrotpilot")
arguments.add_argument("--logs-dir", type=Path, default=ROOT / "work/input")
arguments.add_argument("--output-dir", type=Path, default=ROOT / "work/speed_reference")
args = arguments.parse_args()
SOURCE = args.source_dir.resolve()
sys.path[:0] = [str(SOURCE), str(SOURCE / "opendbc_repo")]
from tools.ars510_offline.bootstrap import prepare

prepare()
from opendbc.car.toyota.ars510.interface import parse_toyota_speed_mps
from opendbc.car.toyota.ars510_offline import Ars510OfflineRadarInterface
from openpilot.cereal import car, log
from openpilot.selfdrive.carrot.radar_motion.primary import snapshot_live_radar_points

OUTPUT = args.output_dir.resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
SOURCE_PATHS = (
  "opendbc_repo/opendbc/car/toyota/ars510_offline.py",
  "opendbc_repo/opendbc/car/toyota/ars510/interface.py",
  "opendbc_repo/opendbc/car/toyota/carstate.py",
  "opendbc_repo/opendbc/car/radar_tracks.py",
  "openpilot/selfdrive/carrot/radar_motion/primary.py",
)


def fingerprints():
  return {path: sha256((SOURCE / path).read_bytes()).hexdigest() for path in SOURCE_PATHS}


def stats(values, unit):
  result = {"count": len(values), "unit": unit}
  if values:
    assert all(math.isfinite(value) for value in values)
    result.update({key: float(value) for key, value in zip(
      ("min", "p50", "p95", "p99", "max"), np.percentile(values, (0, 50, 95, 99, 100)), strict=True)})
    result["max_abs"] = max(abs(value) for value in values)
    result["negative_count"] = sum(value < 0. for value in values)
  return result


def load(path):
  with path.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as stream:
    decoded = stream.read()
  return decoded


def observe(path, label):
  decoded = load(path)
  cp_bytes = None
  for event in log.Event.read_multiple_bytes(decoded):
    if event.which() == "carParams":
      cp_bytes = event.carParams.as_builder().to_bytes()
      break
  if cp_bytes is None:
    return {"anonymous_log": label, "status": "carParams 없음", "points": 0}
  with car.CarParams.from_bytes(cp_bytes) as cp_reader:
    cp = cp_reader.as_builder()
  cp_before = cp.to_bytes()
  cp.clear_write_flag()
  radar = Ars510OfflineRadarInterface(cp, offline=True)
  v_ego = a_ego = 0.
  cs_time = None
  b4 = b4_time = None
  rr = car.RadarData.new_message()
  counts = Counter()
  state_rows, b4_rows = [], []
  lists = {name: [] for name in ("cs_minus_b4", "cs_raw_minus_b4", "cs_age", "b4_age", "inferred_point_ego_minus_latest_b4",
                                "publication_ground_delta", "model_ground_delta", "model_cs_age")}
  previous_time = None
  max_inversion_ms = 0.
  for event in log.Event.read_multiple_bytes(decoded):
    kind = event.which()
    timestamp = int(event.logMonoTime) * 1e-9
    if previous_time is not None and timestamp < previous_time:
      counts["out_of_order_event_header"] += 1
      max_inversion_ms = max(max_inversion_ms, (previous_time-timestamp)*1000)
    previous_time = timestamp
    if kind == "carControl":
      counts["real_longActive_true"] += int(event.carControl.longActive)
      counts["real_controls"] += 1
    elif kind == "carState":
      v_ego, a_ego, cs_time = float(event.carState.vEgo), float(event.carState.aEgo), timestamp
      state_rows.append((timestamp, v_ego, float(event.carState.vEgoRaw)))
      if b4_time is not None and 0. <= timestamp-b4_time <= .1:
        lists["cs_minus_b4"].append(v_ego-b4)
        lists["cs_raw_minus_b4"].append(float(event.carState.vEgoRaw)-b4)
    elif kind == "can":
      frames = []
      for frame in event.can:
        address, bus, payload = int(frame.address), int(frame.src), bytes(frame.dat)
        frames.append((address, payload, bus))
        if bus == 0 and address == 0xb4:
          counts["b4_received"] += 1
          if len(payload) != 8:
            counts["b4_non8byte"] += 1
            continue
          parsed = parse_toyota_speed_mps(payload)
          if parsed is not None and math.isfinite(parsed):
            b4, b4_time = parsed, timestamp
            b4_rows.append((timestamp, parsed))
            counts["b4_length_valid_decoded"] += 1
      result = radar.update_carrot(v_ego, a_ego, timestamp, [(int(event.logMonoTime), frames)])
      if result is None:
        continue
      rr = result
      if cs_time is None or b4_time is None:
        counts["points_without_reference"] += len(rr.points)
        continue
      for point in rr.points:
        counts["points"] += 1
        cs_age, b4_age = timestamp-cs_time, timestamp-b4_time
        lists["cs_age"].append(cs_age*1000)
        lists["b4_age"].append(b4_age*1000)
        if 0. <= b4_age <= .5:
          lists["inferred_point_ego_minus_latest_b4"].append(float(point.vLead)-float(point.vRel)-b4)
        if 0. <= cs_age <= .1:
          lists["publication_ground_delta"].append(v_ego+float(point.vRel)-float(point.vLead))
    elif kind == "modelV2" and cs_time is not None and rr.points:
      snapshots = snapshot_live_radar_points(rr.points, v_ego)
      by_id = {int(point.trackId): point for point in rr.points}
      for snapshot in snapshots:
        lists["model_ground_delta"].append(snapshot.v_lead-float(by_id[snapshot.track_id].vLead))
        lists["model_cs_age"].append((timestamp-cs_time)*1000)
        counts["measured_points_at_model"] += 1
        raw = by_id[snapshot.track_id]
        counts["abs03_speed_classification_disagreement"] += int((abs(snapshot.v_lead) <= .3) != (abs(float(raw.vLead)) <= .3))
        counts["near_retention_geometry_candidates"] += int(0. < float(raw.dRel) <= .5 and abs(float(raw.yRel)) <= .5 and v_ego <= .5)
  assert cp.to_bytes() == cp_before
  # 다른 서비스의 기록 순서를 곧바로 공통 획득 시각으로 취급하지 않는다.
  # 독립 시간 대조는 B4 원래 헤더로 정렬한 직전 값만 사용한다.
  b4_rows.sort()
  b4_times = [row[0] for row in b4_rows]
  joined = {key: [] for key in ("all", "first5s", "after5s")}
  if state_rows:
    start = min(row[0] for row in state_rows)
    for state_time, state_speed, _ in state_rows:
      index = bisect_right(b4_times, state_time)-1
      if index < 0 or not 0. <= state_time-b4_rows[index][0] <= .1:
        continue
      delta = state_speed-b4_rows[index][1]
      joined["all"].append(delta)
      joined["first5s" if state_time-start < 5. else "after5s"].append(delta)
  return {"anonymous_log": label, "status": "오프라인 원형 속도 기준 관찰", "counts": dict(counts),
          "carParams_unchanged": True,
          "max_event_header_inversion_ms": max_inversion_ms,
          "time_joined_cs_minus_b4": {key: stats(values, "m/s") for key, values in joined.items()},
          "statistics": {key: stats(values, "ms" if "age" in key else "m/s") for key, values in lists.items()}}


before = fingerprints()
rows = []
for index, name in enumerate(("rlog.zst", "rlog_06.zst", "rlog_11.zst", "rlog_12.zst"), 1):
  # 원형의 dt 정보 출력만 메모리에 버리며 검사 판정과 반환값은 보존한다.
  with redirect_stdout(io.StringIO()):
    row = observe(args.logs_dir / name, f"log_{index}")
  rows.append(row)
after = fingerprints()
assert before == after
result = {"probe_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
          "source_fingerprints": before, "source_unchanged": before == after, "actual_vehicle_transmissions": 0,
          "vehicle_deployment_allowed": False, "B4_checksum_validation": "원형 helper는 길이·디코딩만 검사; 독립 체크섬 검증을 이 결과에서 주장하지 않음",
          "model_snapshot_scope": "원형 measured snapshot 입력의 속도 계산; 최종 L1 선택·실물 속도 정답 검증 아님",
          "replay_order_scope": "원래 로그 저장 순서의 기존 재생 경로. 음수 시각 차이는 과거 헤더와 이미 읽은 최신 상태의 차이며 실제 각 프로세스 수신 순서를 입증하지 않음",
          "logs": rows}
(OUTPUT / "observations.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
                                        encoding="utf-8", newline="\n")
print(json.dumps({"익명로그": len(rows), "객체표본": sum(row.get("counts", {}).get("points", 0) for row in rows),
                  "소스불변": True, "실차송신": 0}, ensure_ascii=False))
