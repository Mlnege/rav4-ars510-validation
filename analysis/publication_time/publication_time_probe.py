"""원본 epoch에서 ARS 레코드/CS/모델 상대시각을 관측하고 미관측 P를 구분한다.

운영 liveTracks의 미래 ARS 발행시각 P를 만들지 않는다. P=S/G 후보의 차이는
통계만 계산하며 DPath·100ms/150ms 정책·radarDelay·host에 주입하지 않는다.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True

import capnp
import zstandard

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / "radar_input_contract_probe"))
from paired_adapter_replay_quality import public_error
from probe import FILES, INPUT, REPO, SOURCE, production_classes


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pure(path, name):
  spec = importlib.util.spec_from_file_location(name, path)
  module = importlib.util.module_from_spec(spec)
  sys.modules[name] = module
  spec.loader.exec_module(module)
  return module


def constant(path, name):
  tree = ast.parse(path.read_text(encoding="utf-8"))
  node = next(node for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
  return ast.literal_eval(node.value)


class RelativeStats:
  def __init__(self, skew_ns, age_ns):
    self.values = []
    self.skew_ns, self.age_ns = skew_ns, age_ns

  def add(self, value):
    self.values.append(value)

  def summary(self):
    values = sorted(self.values)
    def percentile(fraction):
      if not values:
        return None
      index = (len(values) - 1) * fraction
      lower = int(index)
      upper = min(lower + 1, len(values) - 1)
      return (values[lower] + (values[upper] - values[lower]) * (index - lower)) / 1e6
    return {"count": len(values), "min_ms": values[0] / 1e6 if values else None,
            "p50_ms": percentile(.5), "p99_ms": percentile(.99),
            "max_ms": values[-1] / 1e6 if values else None,
            "negative_count": sum(value < 0 for value in values),
            "positive_over_source_age_limit": sum(value > self.age_ns for value in values),
            "absolute_over_source_skew_limit": sum(abs(value) > self.skew_ns for value in values)}


def read(path, schema, directory):
  records, cp_bytes, counts = [], None, Counter()
  before = path.stat()
  with tempfile.TemporaryFile("w+b", dir=directory) as decoded:
    with path.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
      shutil.copyfileobj(stream, decoded)
    decoded.seek(0)
    for event in schema.Event.read_multiple(decoded, traversal_limit_in_words=64 * 1024 * 1024):
      kind, header, value = event.which(), int(event.logMonoTime), None
      if kind == "carParams" and cp_bytes is None:
        cp_bytes = event.carParams.as_builder().to_bytes()
      elif kind == "can":
        value = [(int(frame.address), bytes(frame.dat), int(frame.src)) for frame in event.can]
        counts["can_events"] += 1
      elif kind == "carState":
        value = event.carState.as_builder()
        counts["carState_events"] += 1
      elif kind == "modelV2":
        value = (int(event.modelV2.timestampEof), header, bool(event.valid))
        counts["model_events"] += 1
        counts["model_invalid"] += int(not event.valid)
        counts["model_zero_eof"] += int(value[0] == 0)
      elif kind == "liveTracks":
        # 기존운영message가미래offlineARS 출력의P라는출처근거는없다.
        counts["recorded_other_liveTracks"] += 1
        counts["recorded_other_liveTracks_points"] += len(event.liveTracks.points)
        counts["recorded_other_liveTracks_invalid"] += int(not event.valid)
      records.append((kind, header, value))
  after = path.stat()
  return records, cp_bytes, dict(counts), before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns


def observe(records, cp, adapter_class, original, skew_ns, basis):
  batches = original.RadarCanBatches()
  adapter = adapter_class(cp, offline=True)
  counts, orders, errors = Counter(), Counter(), Counter()
  timestamp_lookup = {}
  state_headers = {}
  now_ns = 0
  latest_model = latest_record = None
  needs_reset = False
  at_record, at_model = {}, {}

  def stats(target, key, delta):
    target.setdefault(key, RelativeStats(skew_ns, original.MAX_INPUT_AGE_NS)).add(delta)

  def model_relation(target, model, record):
    eof, header, valid = model
    if eof <= 0:
      counts["association_skipped_zero_eof"] += 1
      return
    f, k, receive, state_header, consumer = record
    for name, value in (("F", f), ("K", k), ("R", receive), ("S", state_header), ("G_assumed", consumer)):
      stats(target, "E_minus_" + name, eof - value)
    stats(target, "M_minus_E", header - eof)
    counts["associated_model_invalid"] += int(not valid)

  for kind, header, value in records:
    if basis == "storage_max" or kind in ("can", "carState"):
      now_ns = max(now_ns, header)
    if kind == "modelV2":
      latest_model = value
      if latest_record is None:
        counts["model_without_completed_record"] += 1
      else:
        model_relation(at_model, latest_model, latest_record)
        counts["model_with_completed_record"] += 1
    if kind == "can":
      key = header * 1e-9
      if key in timestamp_lookup and timestamp_lookup[key] != header:
        counts["float_packet_timestamp_collision"] += 1
        timestamp_lookup[key] = None
      else:
        timestamp_lookup[key] = header
      batches.add_can([(header, value)])
    elif kind == "carState":
      if "radarInput" not in value.schema.fields:
        counts["schema_metadata_missing"] += 1
        continue
      ego = original.RadarEgoSample.from_car_state(value)
      if ego.receive_ns in state_headers and state_headers[ego.receive_ns] != header:
        counts["receive_timestamp_header_collision"] += 1
      state_headers[ego.receive_ns] = header
      batches.add_state(ego)
    else:
      continue
    while batches.states:
      taken = batches.take(now_ns)
      if taken is None:
        break
      ego, packets, error = taken
      if error:
        errors[error] += 1
        needs_reset = True
        latest_record = None
        continue
      if needs_reset:
        adapter = adapter_class(cp, offline=True)
        counts["batch_error_adapter_restarts"] += 1
        needs_reset = False
      before_records = adapter.diagnostics["records"]
      result = adapter.update_carrot(ego.v_ego, ego.a_ego, ego.receive_ns * 1e-9, packets)
      counts["accepted_batches"] += 1
      new_records = adapter.diagnostics["records"] - before_records
      counts["completed_records"] += new_records
      counts["calls_with_multiple_records"] += int(new_records > 1)
      counts["returned_points"] += len(result.points) if result is not None else 0
      if result is not None and any(result.errors.to_dict().values()):
        counts["returned_error_results"] += 1
        latest_record = None
      if new_records <= 0:
        continue
      f = timestamp_lookup.get(adapter._record_time_s)
      k = timestamp_lookup.get(adapter._completion_time_s)
      state_header = state_headers.get(ego.receive_ns)
      if f is None or k is None or state_header is None:
        counts["unmapped_original_record_timestamp"] += 1
        continue
      record = (f, k, ego.receive_ns, state_header, now_ns)
      latest_record = record
      counts["timestamped_completed_records"] += 1
      # F/K는CAN발행,R/S는Card/CS다. 실제시계영역의호환은미확인인산술관측이다.
      for name, relation in (("F_le_K", f <= k), ("K_le_R_conditional", k <= ego.receive_ns),
                             ("R_le_S", ego.receive_ns <= state_header), ("S_le_G_assumed", state_header <= now_ns)):
        orders[name + ("_true" if relation else "_false")] += 1
      for name, delta in (("K_minus_F", k - f), ("R_minus_K", ego.receive_ns - k),
                          ("S_minus_R", state_header - ego.receive_ns), ("G_minus_S_assumed", now_ns - state_header)):
        stats(at_record, name, delta)
      if latest_model is not None:
        model_relation(at_record, latest_model, record)
      else:
        counts["record_without_observed_model"] += 1
  return {"clock_basis": basis, "counts": dict(counts), "batch_errors": dict(errors), "numeric_order_counts": dict(orders),
          "at_record_completion": {key: value.summary() for key, value in at_record.items()},
          "at_model_event_latest_record": {key: value.summary() for key, value in at_model.items()},
          "P_actual_observed": False, "P_candidates_used_as_input": False,
          "pending_states_at_end": len(batches.states),
          "association_ko": "저장순서에서관측한모델/마지막정상완성record의상대산술. 다른clockdomain의실물동기·측정지연이입증됐다는뜻은아님."}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  parser.add_argument("--aliases", nargs="+", choices=tuple(FILES), default=list(FILES))
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("기존결과는덮지않습니다. 새출력폴더를지정하세요")
  args.output_dir.mkdir(parents=True, exist_ok=True)
  paths = {"publication_time_probe.py": Path(__file__), "can_batch.py": SOURCE,
           "paired_adapter_replay_quality.py": WORK / "radar_input_contract_probe/paired_adapter_replay_quality.py"}
  for name in ("carrot/radar/radarcan.py", "carrot/radar/radard_dpath.py", "carrot/radar_motion/controller.py",
               "carrot/radar_motion/timing.py", "car/card.py", "pandad/pandad.cc", "pandad/pandad_api_impl.py"):
    paths[name] = REPO / "openpilot/selfdrive" / name
  for name in ("ars510_offline.py", "ars510/interface.py", "ars510/transport.py", "ars510/record.py",
               "ars510/objects.py", "ars510/support.py", "ars510/tracks.py", "ars510/constants.py"):
    paths[name] = REPO / "opendbc_repo/opendbc/car/toyota" / name
  paths["interfaces.py"] = REPO / "opendbc_repo/opendbc/car/interfaces.py"
  paths["radar_tracks.py"] = REPO / "opendbc_repo/opendbc/car/radar_tracks.py"
  paths["common/timing.h"] = REPO / "openpilot/common/timing.h"
  paths["cereal/messaging/messaging.h"] = REPO / "openpilot/cereal/messaging/messaging.h"
  paths["cereal/messaging/__init__.py"] = REPO / "openpilot/cereal/messaging/__init__.py"
  hashes = {}
  started, utc = time.perf_counter(), datetime.now(UTC).isoformat()
  results, preparation_errors, phase = [], [], "source_fingerprints"
  try:
    hashes = {name: sha(path) for name, path in paths.items()}
    phase = "bootstrap"
    sys.path.insert(0, str(REPO))
    from tools.ars510_offline.bootstrap import prepare
    params_backend = prepare()
    from opendbc.car.toyota.ars510_offline import Ars510OfflineRadarInterface
    from openpilot.cereal import car
    original = production_classes()
    timing = load_pure(paths["carrot/radar_motion/timing.py"], "original_distance_timing")
    skew_s = constant(paths["carrot/radar_motion/controller.py"], "RADAR_MOTION_MAX_TIME_SKEW_S")
    skew_ns = round(skew_s * 1e9)
    phase = "schema"
    folder = INPUT / "carrot_schemas"
    loader = capnp.SchemaParser()
    schema = loader.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
    for alias in args.aliases:
      phase = alias + ":read"
      records, cp_bytes, counts, unchanged = read(INPUT / FILES[alias], schema, args.output_dir)
      if cp_bytes is None:
        results.append({"alias": alias, "status": "insufficient_original_carParams", "recorded_counts": counts,
                        "source_file_stat_unchanged": unchanged})
        continue
      with car.CarParams.from_bytes(cp_bytes) as reader:
        cp = reader.as_builder()
      before = cp.to_bytes()
      cp.clear_write_flag()
      measured = {}
      for basis in ("input_max", "storage_max"):
        phase = alias + ":observe:" + basis
        measured[basis] = observe(records, cp, Ars510OfflineRadarInterface, original, skew_ns, basis)
      after = cp.to_bytes()
      cp.clear_write_flag()
      results.append({"alias": alias, "status": "timing_observed", "recorded_counts": counts,
                      "source_file_stat_unchanged": unchanged, "original_cp_unchanged": before == after,
                      "original_radarUnavailable": bool(cp.radarUnavailable), "declared_radarDelay_s": float(cp.radarDelay),
                      "original_distance_projection_delay_s": timing.front_radar_distance_delay_s(cp),
                      "observations": measured})
      print(json.dumps({"alias": alias, "records": {basis: value["counts"].get("completed_records", 0) for basis, value in measured.items()},
                        "P_actual_observed": False}, ensure_ascii=False), flush=True)
  except Exception as error:  # noqa: BLE001 - 원본이포함될수있는예외본문은저장하지않는다.
    preparation_errors.append(public_error(error, phase))
    params_backend = locals().get("params_backend", "not_prepared")
    skew_s = locals().get("skew_s")
  report = {"started_utc": utc, "finished_utc": datetime.now(UTC).isoformat(), "wall_seconds": time.perf_counter() - started,
            "files": results, "preparation_errors": preparation_errors, "params_backend": params_backend,
            "source_hashes": hashes, "source_unchanged": bool(hashes) and all(sha(paths[name]) == value for name, value in hashes.items()),
            "source_skew_s": skew_s, "P_actual_observed": False, "actual_collector_clock_observed": False,
            "P_candidates_used_as_input": False, "dpath_executed": False, "host_executed": False,
            "CAN_transmitted": False, "Params_changed": False, "original_epoch_preserved": True,
            "scope_ko": "F/K/R/S/E/M/G의원본epoch상대산술만익명집계. 미래ARS liveTracks P는미관측. S/G를생산P로만들거나skew/age/radarDelay/CP를변경하지않음."}
  (args.output_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
  return int(bool(preparation_errors) or not report["source_unchanged"] or
             any(not value["source_file_stat_unchanged"] or value.get("original_cp_unchanged") is False for value in results))


if __name__ == "__main__":
  raise SystemExit(main())
