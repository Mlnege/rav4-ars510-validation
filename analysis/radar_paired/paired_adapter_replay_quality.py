"""동결 재생의 레코드별 출판점 개수 품질 관측을 보강한 별도 버전.

기존 직접 경로도 동일 입력으로 별도 실행해 비교한다. 시각/CS/packetCount를
조작해 개수를 맞추지 않으며 DPath·호스트·실차·운영 Params는 실행하지 않는다.
"""
import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True

import capnp
import zstandard
from probe import FILES, INPUT, REPO, SOURCE, production_classes


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def public_error(error, phase):
  # 데이터나 원본경로가 들어갈 수 있는 exception 본문은 저장하지 않는다.
  return {"phase": phase, "error_type": type(error).__name__,
          "source_frames": [{"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                            for frame in traceback.extract_tb(error.__traceback__)]}


def distribution(values):
  return {"count": len(values), "min_ms": min(values) * 1000 if values else None,
          "max_ms": max(values) * 1000 if values else None,
          "negative_count": sum(value < 0 for value in values),
          "over_100ms_count": sum(value > .1 for value in values)}


def read_input(path, schema, directory):
  records, cp_bytes = [], None
  counts = Counter()
  before = path.stat()
  with tempfile.TemporaryFile("w+b", dir=directory) as decoded:
    with path.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
      shutil.copyfileobj(stream, decoded)
    decoded.seek(0)
    for event in schema.Event.read_multiple(decoded, traversal_limit_in_words=64 * 1024 * 1024):
      kind, header = event.which(), int(event.logMonoTime)
      body = None
      if kind == "carParams" and cp_bytes is None:
        cp_bytes = event.carParams.as_builder().to_bytes()
      if kind == "can":
        body = [(int(frame.address), bytes(frame.dat), int(frame.src)) for frame in event.can]
        counts["can_packets"] += 1
        counts["can_frames"] += len(body)
      elif kind == "carState":
        body = event.carState.as_builder()
        counts["carState"] += 1
        counts["metadata_wire_missing"] += int("radarInput" not in body.schema.fields or not body._has("radarInput"))
      # 다른 서비스는 clock 가정 비교에 header만 쓰고 원본 payload를 보관하지 않는다.
      records.append((kind, header, body))
  after = path.stat()
  return records, cp_bytes, dict(counts), before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns


class AdapterRun:
  """원형 결과와 읽기 전용 diagnostics만 집계한다. 계산 함수를 감싸지 않는다."""

  def __init__(self, cp, adapter_class):
    self.cp, self.adapter_class = cp, adapter_class
    self.adapter = adapter_class(cp, offline=True)
    self.counts = Counter()
    self.errors = Counter()
    self.accumulated = Counter()
    self.deltas = {"call_minus_first_packet": [], "call_minus_last_packet": [],
                   "call_minus_last_record_start": [], "completion_minus_last_record_start": [],
                   "call_minus_last_completion": []}
    self.first_record_call = None
    self.first_call = None
    self.last_call = None
    self.point_records = Counter()
    self.completed_record_times = set()
    self.record_spans = {}
    self.rejected_ranges = []

  def restart(self):
    self.accumulated.update(self.diagnostic_counts())
    self.adapter = self.adapter_class(self.cp, offline=True)
    self.counts["batch_error_adapter_restarts"] += 1

  def diagnostic_counts(self):
    # 객체번호 namespace 자체는 개별 ID를 유추할 수 있으므로 익명 보고에서 제외한다.
    return {key: value for key, value in self.adapter.diagnostics.items()
            if key not in ("namespace_offset", "active_points")}

  def call(self, ego_speed, ego_accel, receive_s, packets):
    self.first_call = receive_s if self.first_call is None else self.first_call
    self.last_call = receive_s
    before_records = self.adapter.diagnostics["records"]
    result = self.adapter.update_carrot(ego_speed, ego_accel, receive_s, packets)
    self.counts["adapter_calls"] += 1
    self.counts["paired_can_packets"] += len(packets)
    self.counts["paired_can_frames"] += sum(len(frames) for _, frames in packets)
    if packets:
      self.deltas["call_minus_first_packet"].append(receive_s - packets[0][0] * 1e-9)
      self.deltas["call_minus_last_packet"].append(receive_s - packets[-1][0] * 1e-9)
    new_records = self.adapter.diagnostics["records"] - before_records
    self.counts["calls_with_new_records"] += int(new_records > 0)
    self.counts["calls_with_multiple_new_records"] += int(new_records > 1)
    if new_records > 0:
      self.first_record_call = receive_s if self.first_record_call is None else self.first_record_call
    start = self.adapter._record_time_s
    completion = self.adapter._completion_time_s
    if new_records > 0 and start is not None and completion is not None:
      self.completed_record_times.add(completion)
      self.record_spans[completion] = (start, completion)
      # 한 호출에 여러record가 있으면 마지막record의 시각이다. 모든record라고 부르지 않는다.
      self.deltas["call_minus_last_record_start"].append(receive_s - start)
      self.deltas["completion_minus_last_record_start"].append(completion - start)
      self.deltas["call_minus_last_completion"].append(receive_s - completion)
    if result is None:
      self.counts["no_result_calls"] += 1
      return
    self.counts["returned_radarData"] += 1
    self.counts["returned_points"] += len(result.points)
    if result.points and completion is not None:
      # 레코드키는비공개원본시각이며메모리에서두경로의개수대조에만사용한다.
      self.point_records[completion] += len(result.points)
    flags = result.errors.to_dict()
    self.counts["returned_error_results"] += int(any(flags.values()))
    for name, enabled in flags.items():
      self.errors[name] += int(enabled)
    for point in result.points:
      required = (point.dRel, point.yRel, point.vRel, point.vLead, point.aLead, point.jLead)
      self.counts["nonfinite_required_points"] += int(not all(math.isfinite(float(value)) for value in required))

  def summary(self):
    diagnostics = self.accumulated.copy()
    diagnostics.update(self.diagnostic_counts())
    return {"counts": dict(self.counts), "radar_error_counts": dict(self.errors),
            "adapter_diagnostics": dict(diagnostics),
            "relative_time_distributions": {key: distribution(values) for key, values in self.deltas.items()},
            "first_record_call_minus_first_call_s": (self.first_record_call - self.first_call
                                                     if self.first_record_call is not None else None),
            "sample_receive_span_s": self.last_call - self.first_call if self.first_call is not None else None,
            "last_record_time_measurement_ko": "record 시각 통계는 각호출 마지막완성record 기준. 원본절대시각/ID/좌표는저장하지않음."}


def direct(records, cp, adapter_class):
  run = AdapterRun(cp, adapter_class)
  v_ego = a_ego = 0.
  have_state = False
  for kind, header, body in records:
    if kind == "carState":
      v_ego, a_ego = float(body.vEgo), float(body.aEgo)
      have_state = True
    elif kind == "can":
      before_points = run.counts["returned_points"]
      before_records = run.adapter.diagnostics["records"]
      run.call(v_ego, a_ego, header * 1e-9, [(header, body)])
      if not have_state:
        run.counts["points_before_first_recorded_cs"] += run.counts["returned_points"] - before_points
        run.counts["records_before_first_recorded_cs"] += run.adapter.diagnostics["records"] - before_records
  result = run.summary()
  result["clock_assumption_ko"] = "기존직접경로: 저장CAN Event마다원본CANheader/latestCS를사용. 첫CS전ego초기값0인기존정책을별도명시."
  return result, run


def paired(records, cp, adapter_class, original, basis):
  buffer = original.RadarCanBatches()
  run = AdapterRun(cp, adapter_class)
  counts, batch_errors = Counter(), Counter()
  gate_ages = []
  now_ns = 0
  needs_reset = False
  for kind, header, body in records:
    if basis == "storage_max" or kind in ("can", "carState"):
      now_ns = max(now_ns, header)
    if kind == "can":
      previous = len(buffer.can)
      buffer.add_can([(header, body)])
      counts["can_packets_received"] += 1
      counts["bounded_can_drops"] += max(0, previous + 1 - len(buffer.can))
    elif kind == "carState":
      counts["source_cs_received"] += 1
      if "radarInput" not in body.schema.fields:
        counts["schema_metadata_missing"] += 1
        continue
      buffer.add_state(original.RadarEgoSample.from_car_state(body))
    else:
      continue
    # 원형 independent-stream take를 그대로 호출하고 반환값을 관측한다.
    while buffer.states:
      previous_headers = Counter(packet[0] for packet in buffer.can)
      result = buffer.take(now_ns)
      selected_headers = Counter(packet[0] for packet in result[1]) if result is not None else Counter()
      remaining_headers = Counter(packet[0] for packet in buffer.can)
      counts["can_discarded_outside_metadata_bounds"] += sum(
        (previous_headers - remaining_headers - selected_headers).values())
      if result is None:
        counts["pending_take_attempts"] += 1
        break
      ego, packets, error = result
      gate_ages.append((now_ns - ego.receive_ns) * 1e-9)
      if error:
        batch_errors[error] += 1
        run.rejected_ranges.append((ego.first_can_ns * 1e-9, ego.last_can_ns * 1e-9, error))
        needs_reset = True
        continue
      if needs_reset:
        # 생산radarcan은잘못된batch후다음정상batch앞에서interface를재생성한다.
        run.restart()
        needs_reset = False
      counts["accepted_batches"] += 1
      counts["empty_batches"] += int(not packets)
      run.call(ego.v_ego, ego.a_ego, ego.receive_ns * 1e-9, packets)
  result = run.summary()
  counts["pending_states_at_end"] = len(buffer.states)
  counts["unpaired_can_packets_at_end"] = len(buffer.can)
  result.update({"batch_counts": dict(counts), "batch_error_counts": dict(batch_errors),
                 "gate_now_minus_receive_distribution": distribution(gate_ages),
                 "clock_basis": basis,
                 "clock_assumption_ko": ("독립CAN/CS 저장순서의최대header를gate now로사용. 그외서비스header는clock에반영하지않음."
                                         if basis == "input_max" else "모든저장Event의최대header를gate now로사용하는별도인과배달가정."),
                 "adapter_receive_clock_ko": "decoder의외부calltime은정확해당원본CS.receiveMonoTime. 내부CAN packetheader는원본을그대로유지.",
                 "full_radarcan_process_executed": False,
                 "socket_and_global_timeout_ko": "소켓/main20ms poll·processingTimeout·state/CAN전체inputTimeout은미실행. 원형batchgate와adapter의원형timeout만실행."})
  return result, run


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  parser.add_argument("--aliases", nargs="+", choices=tuple(FILES), default=list(FILES))
  parser.add_argument("--clock-bases", nargs="+", choices=("input_max", "storage_max"), default=["input_max", "storage_max"])
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("기존결과를덮지않습니다. 새출력폴더를지정하세요")
  args.output_dir.mkdir(parents=True, exist_ok=True)
  protected = {"probe.py": Path(__file__).with_name("probe.py"),
               "canonical_batch_replay.py": Path(__file__).with_name("canonical_batch_replay.py"),
               "can_batch.py": SOURCE, "paired_adapter_replay_quality.py": Path(__file__),
               "frozen_paired_adapter_replay.py": Path(__file__).with_name("paired_adapter_replay.py")}
  for name in ("ars510_offline.py", "ars510/interface.py", "ars510/transport.py", "ars510/record.py",
               "ars510/objects.py", "ars510/support.py", "ars510/tracks.py", "ars510/constants.py"):
    protected[name] = REPO / "opendbc_repo/opendbc/car/toyota" / name
  protected["interfaces.py"] = REPO / "opendbc_repo/opendbc/car/interfaces.py"
  protected["radar_tracks.py"] = REPO / "opendbc_repo/opendbc/car/radar_tracks.py"
  hashes = {}
  results, preparation_errors = [], []
  started, started_utc = time.perf_counter(), datetime.now(UTC).isoformat()
  phase = "source_fingerprints"
  try:
    hashes = {name: sha(path) for name, path in protected.items()}
    phase = "bootstrap"
    sys.path.insert(0, str(REPO))
    from tools.ars510_offline.bootstrap import prepare
    params_backend = prepare()
    from opendbc.car.toyota.ars510_offline import Ars510OfflineRadarInterface
    from openpilot.cereal import car
    original = production_classes()
    phase = "schema"
    folder = INPUT / "carrot_schemas"
    loader = capnp.SchemaParser()
    schema = loader.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
    for alias in args.aliases:
      phase = alias + ":read"
      records, cp_bytes, input_counts, input_unchanged = read_input(INPUT / FILES[alias], schema, args.output_dir)
      if cp_bytes is None:
        results.append({"alias": alias, "status": "insufficient_original_carParams", "input_counts": input_counts,
                        "source_file_stat_unchanged": input_unchanged, "adapter_executed": False})
        print(json.dumps({"alias": alias, "status": "insufficient_original_carParams"}))
        continue
      phase = alias + ":original_cp"
      with car.CarParams.from_bytes(cp_bytes) as reader:
        cp = reader.as_builder()
      cp_before = cp.to_bytes()
      cp.clear_write_flag()
      phase = alias + ":direct"
      reference, reference_run = direct(records, cp, Ars510OfflineRadarInterface)
      reference_point_records = reference_run.point_records
      candidates = {}
      point_comparisons = {}
      for basis in args.clock_bases:
        phase = alias + ":paired:" + basis
        candidate, candidate_run = paired(records, cp, Ars510OfflineRadarInterface, original, basis)
        candidate_point_records = candidate_run.point_records
        candidates[basis] = candidate
        # 0점record도 포함한다. signed 합의 상쇄와 레코드별 동일을 구분한다.
        shared_record_keys = reference_run.completed_record_times & candidate_run.completed_record_times
        point_comparisons[basis] = {
          "shared_completed_record_count": len(shared_record_keys),
          "shared_record_point_count_mismatches": sum(candidate_point_records[key] != reference_point_records[key]
                                                      for key in shared_record_keys),
          "absolute_point_count_delta_sum": sum(abs(candidate_point_records[key] - reference_point_records[key])
                                                 for key in shared_record_keys),
          "signed_point_count_delta_on_shared_completed_records": sum(candidate_point_records[key] - reference_point_records[key]
                                                                      for key in shared_record_keys),
          "direct_points_on_records_absent_from_paired": sum(value for key, value in reference_point_records.items()
                                                            if key not in candidate_point_records),
          "paired_points_on_records_absent_from_direct": sum(value for key, value in candidate_point_records.items()
                                                            if key not in reference_point_records),
          "point_count_delta_on_shared_records": sum(candidate_point_records[key] - reference_point_records[key]
                                                     for key in candidate_point_records.keys() & reference_point_records.keys()),
          "direct_points_on_records_decoded_but_withheld_in_paired": sum(
            value for key, value in reference_point_records.items()
            if key not in candidate_point_records and key in candidate_run.completed_record_times),
          "direct_points_on_records_not_decoded_in_paired": sum(
            value for key, value in reference_point_records.items()
            if key not in candidate_run.completed_record_times),
          "direct_points_with_completion_in_rejected_batch_ranges": sum(
            value for key, value in reference_point_records.items()
            if any(first <= key <= last for first, last, _ in candidate_run.rejected_ranges)),
          "missing_direct_points_whose_record_spans_overlap_rejected_batch_ranges": sum(
            value for key, value in reference_point_records.items()
            if key not in candidate_run.completed_record_times and key in reference_run.record_spans
            and any(first <= reference_run.record_spans[key][1] and last >= reference_run.record_spans[key][0]
                    for first, last, _ in candidate_run.rejected_ranges)),
          "record_keys_saved": False,
        }
      cp_after = cp.to_bytes()
      cp.clear_write_flag()
      comparisons = {basis: {"returned_points_delta": value["counts"].get("returned_points", 0)
                                                        - reference["counts"].get("returned_points", 0),
                             "records_delta": value["adapter_diagnostics"].get("records", 0)
                                              - reference["adapter_diagnostics"].get("records", 0),
                             "crc_failures_delta": value["adapter_diagnostics"].get("crc_failures", 0)
                                                   - reference["adapter_diagnostics"].get("crc_failures", 0)}
                     for basis, value in candidates.items()}
      result = {"alias": alias, "status": "offline_adapters_executed", "input_counts": input_counts,
                "source_file_stat_unchanged": input_unchanged, "original_cp_unchanged": cp_before == cp_after,
                "original_radarUnavailable": bool(cp.radarUnavailable), "direct": reference,
                "paired": candidates, "comparisons": comparisons, "point_record_count_comparisons": point_comparisons}
      results.append(result)
      print(json.dumps({"alias": alias, "direct_points": reference["counts"].get("returned_points", 0),
                        "paired_points": {basis: value["counts"].get("returned_points", 0) for basis, value in candidates.items()},
                        "paired_records": {basis: value["adapter_diagnostics"].get("records", 0) for basis, value in candidates.items()},
                        "batch_errors": {basis: value["batch_error_counts"] for basis, value in candidates.items()}}, ensure_ascii=False), flush=True)
  except Exception as error:  # noqa: BLE001 - 오류 본문에 포함될 수 있는 비공개 원본은 저장하지 않는다.
    preparation_errors.append(public_error(error, phase))
    params_backend = locals().get("params_backend", "not_prepared")
  report = {"started_utc": started_utc, "finished_utc": datetime.now(UTC).isoformat(),
            "wall_seconds": time.perf_counter() - started, "files": results, "preparation_errors": preparation_errors,
            "params_backend": params_backend, "source_hashes": hashes,
            "source_unchanged": bool(hashes) and all(sha(protected[name]) == value for name, value in hashes.items()),
            "dpath_executed": False, "host_executed": False, "can_transmitted": False,
            "new_metadata_generated": False, "mode_or_cp_flags_changed": False,
            "actual_collector_clock_available": False,
            "scope_ko": "원본CAN/CS배치의원형stream매칭과offlineadapter만직접실행. DPath/175선택/host/실차검증아님. rawpayload/ID/좌표/원본절대시각은메모리뿐이며익명count/상대분포만저장."}
  (args.output_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
  return int(bool(preparation_errors) or not report["source_unchanged"] or
             any(not value["source_file_stat_unchanged"] or value.get("original_cp_unchanged") is False for value in results))


if __name__ == "__main__":
  raise SystemExit(main())
