"""저장된 CarState.radarInput의 실제 존재와 CAN 묶음 계약을 익명 집계한다.

원본 값을 생성하거나 정상으로 대체하지 않는다. 원형 RadarCanBatches의 메타
판정만 기록 CS 발행 헤더에서 확인하며 실제 radarcan/collector 실행과 구분한다.
"""
import argparse
import bisect
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
REPO = WORK / "carrotpilot"
INPUT = WORK / "input"
SOURCE = REPO / "openpilot/selfdrive/carrot/radar/can_batch.py"
PROCESS_SOURCE = REPO / "openpilot/selfdrive/carrot/radar/radarcan.py"
CARD_SOURCE = REPO / "openpilot/selfdrive/car/card.py"
FIELDS = ("firstCanMonoTime", "lastCanMonoTime", "canPacketCount", "receiveMonoTime")
FILES = {"log_a": "rlog.zst", "log_b": "rlog_06.zst", "log_c": "rlog_11.zst", "log_d": "rlog_12.zst"}


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def production_classes():
  """IO 의존성이 없는 원형 클래스 전체를 파일에서 그대로 불러온다."""
  spec = importlib.util.spec_from_file_location("radar_contract_original", SOURCE)
  module = importlib.util.module_from_spec(spec)
  sys.modules[spec.name] = module
  spec.loader.exec_module(module)
  return module


def delta_summary(values):
  # 0/누락 timestamp와의 차이는 절대 원본 시각을 노출하므로 계산하지 않는다.
  return {"count": len(values), "min_ms": min(values) / 1e6 if values else None,
          "max_ms": max(values) / 1e6 if values else None,
          "negative_count": sum(value < 0 for value in values),
          "over_100ms_count": sum(value > 100_000_000 for value in values)}


def inspect_file(alias, path, event_schema, directory, original):
  counts, zeros, positive, presence, intrinsic, joins = (Counter() for _ in range(6))
  headers, samples = [], []
  deltas = {"cs_header_minus_receive": [], "receive_minus_first_can": [],
            "receive_minus_last_can": [], "last_minus_first_can": []}
  packet_counts = Counter()
  previous_sample = None
  covered_can_indices = set()
  source_stat = path.stat()
  schema_fields = None
  # 메모리 parser를 위한 해제 가능한 임시 파일도 허용된 신규 폴더에만 둔다.
  with tempfile.TemporaryFile("w+b", dir=directory) as decoded:
    with path.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
      shutil.copyfileobj(stream, decoded)
    decoded.seek(0)
    for event in event_schema.read_multiple(decoded, traversal_limit_in_words=64 * 1024 * 1024):
      kind = event.which()
      if kind == "can":
        header = int(event.logMonoTime)
        if headers and header < headers[-1]:
          counts["can_header_reversal"] += 1
        if headers and header == headers[-1]:
          counts["can_header_duplicate"] += 1
        headers.append(header)
        counts["can_events"] += 1
        counts["can_event_invalid"] += int(not event.valid)
        continue
      if kind != "carState":
        continue
      counts["carState_events"] += 1
      counts["carState_event_invalid"] += int(not event.valid)
      cs = event.carState
      counts["carState_can_valid"] += int(cs.canValid)
      if "radarInput" not in cs.schema.fields:
        presence["schema_field_missing"] += 1
        continue
      presence["schema_field_present"] += 1
      present = bool(cs._has("radarInput"))
      presence["wire_struct_present" if present else "wire_struct_absent"] += 1
      batch = cs.radarInput
      schema_fields = {name: name in batch.schema.fields for name in FIELDS}
      if not all(schema_fields.values()):
        presence["schema_subfield_missing"] += 1
        continue
      # Reader의 absent pointer에서 읽는 숫자0은 Cap'n Proto 기본값이다.
      # 원형 from_car_state와 같은 읽기를 쓰며 producer 메타를 새로 쓰지 않는다.
      values = {name: int(getattr(batch, name)) for name in FIELDS}
      for name, value in values.items():
        zeros[name] += int(value == 0)
        positive[name] += int(value > 0)
      all_zero = not any(values.values())
      presence["all_four_zero"] += int(all_zero)
      presence["present_but_all_four_zero"] += int(present and all_zero)
      first, last, packet_count, receive = (values[name] for name in FIELDS)
      packet_counts[packet_count] += 1
      intrinsic["receive_missing_zero"] += int(receive == 0)
      intrinsic["empty_count_nonzero_boundary"] += int(packet_count == 0 and bool(first or last))
      intrinsic["nonempty_count_first_zero"] += int(packet_count > 0 and first == 0)
      intrinsic["nonempty_count_last_before_first"] += int(packet_count > 0 and last < first)
      intrinsic["packet_count_over_source_max"] += int(packet_count > original.MAX_CAN_PACKETS)
      header = int(event.logMonoTime)
      if header > 0 and receive > 0:
        deltas["cs_header_minus_receive"].append(header - receive)
      if receive > 0 and first > 0:
        deltas["receive_minus_first_can"].append(receive - first)
      if receive > 0 and last > 0:
        deltas["receive_minus_last_can"].append(receive - last)
      if first > 0 and last > 0:
        deltas["last_minus_first_can"].append(last - first)
      if receive > 0:
        intrinsic["receive_after_cs_publication"] += int(receive > header)
      if receive > 0 and last > 0:
        intrinsic["last_can_after_receive"] += int(last > receive)
      # CS/속도·가속/원본 시각은 메모리 내부에만 유지하고 보고서에 쓰지 않는다.
      ego = original.RadarEgoSample.from_car_state(cs)
      if previous_sample is not None:
        intrinsic["receive_time_reversal"] += int(ego.receive_ns < previous_sample.receive_ns)
        intrinsic["receive_time_repeat"] += int(ego.receive_ns == previous_sample.receive_ns)
        intrinsic["nonempty_batch_overlap_previous"] += int(
          ego.packet_count > 0 and previous_sample.packet_count > 0
          and ego.first_can_ns <= previous_sample.last_can_ns)
      previous_sample = ego
      samples.append((header, ego))

  for header, ego in samples:
    # 실제 CAN의 발행 header만 필요하다. 원형 batch 판정은 payload를 읽지 않는다.
    # 기록 전체에서 발견한 bounds 일치는 collector 수신 순서의 증거가 아니다.
    candidate_headers = []
    if ego.packet_count > 0 and ego.first_can_ns > 0 and ego.last_can_ns >= ego.first_can_ns:
      if counts["can_header_reversal"]:
        joins["ordered_exact_join_not_evaluated"] += 1
      else:
        left = bisect.bisect_left(headers, ego.first_can_ns)
        right = bisect.bisect_right(headers, ego.last_can_ns)
        candidate_headers = headers[left:right]
        joins["covered_header_reuse_occurrences"] += sum(index in covered_can_indices for index in range(left, right))
        covered_can_indices.update(range(left, right))
        joins["nonempty_metadata_evaluated"] += 1
        joins["first_boundary_found"] += int(bool(candidate_headers) and candidate_headers[0] == ego.first_can_ns)
        joins["last_boundary_found"] += int(bool(candidate_headers) and candidate_headers[-1] == ego.last_can_ns)
        joins["packet_count_matches_range"] += int(len(candidate_headers) == ego.packet_count)
        joins["exact_endpoints_and_count"] += int(
          bool(candidate_headers) and candidate_headers[0] == ego.first_can_ns
          and candidate_headers[-1] == ego.last_can_ns and len(candidate_headers) == ego.packet_count)
    buffer = original.RadarCanBatches()
    buffer.add_can([(value, []) for value in candidate_headers])
    buffer.add_state(ego)
    result = buffer.take(header)
    joins["source_gate_pending" if result is None else ("source_gate_" + (result[2] or "accepted"))] += 1

  joins["recorded_can_headers_covered_by_metadata"] = len(covered_can_indices)
  joins["recorded_can_headers_not_bound_to_cs_metadata"] = len(headers) - len(covered_can_indices)

  after = path.stat()
  return {
    "alias": alias, "counts": dict(counts), "presence": dict(presence),
    "radar_input_subfields": schema_fields, "zero_counts": {name: zeros[name] for name in FIELDS},
    "positive_counts": {name: positive[name] for name in FIELDS}, "intrinsic_counts": dict(intrinsic),
    "can_packet_count_frequency": {str(key): value for key, value in sorted(packet_counts.items())},
    "relative_delta_summaries": {name: delta_summary(values) for name, values in deltas.items()},
    "recorded_can_header_join_counts": dict(joins),
    "source_file_stat_unchanged": source_stat.st_size == after.st_size and source_stat.st_mtime_ns == after.st_mtime_ns,
    "source_gate_clock_assumption_ko": "원형 take(now)는 기록 CS 발행 header를 now로 사용. 실제 collector/처리 시각이 아님.",
    "wire_absence_default_ko": "wire 포인터 부재 시 읽은0은 스키마 기본값이며 기록 producer가 쓴 메타가 아님.",
    "can_payload_examined": False, "can_transmitted": False,
  }


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output", "--output-dir", dest="output", type=Path, required=True)
  parser.add_argument("--aliases", nargs="+", choices=tuple(FILES), default=list(FILES))
  args = parser.parse_args()
  if (args.output / "results.json").exists():
    raise RuntimeError("결과가 이미 있는 폴더는 덮어쓰지 않습니다. 새 출력 폴더를 지정하세요")
  args.output.mkdir(parents=True, exist_ok=True)
  folder = INPUT / "carrot_schemas"
  capnp_parser = capnp.SchemaParser()
  schema = capnp_parser.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  source_paths = {"can_batch.py": SOURCE, "radarcan.py": PROCESS_SOURCE, "card.py": CARD_SOURCE,
                  "reader_log.capnp": folder / "log.capnp", "reader_car.capnp": folder / "car.capnp",
                  "probe.py": Path(__file__)}
  hashes = {name: sha(path) for name, path in source_paths.items()}
  original = production_classes()
  started, utc = time.perf_counter(), datetime.now(UTC).isoformat()
  results, failures = [], []
  for alias in args.aliases:
    try:
      result = inspect_file(alias, INPUT / FILES[alias], schema.Event, args.output, original)
      results.append(result)
      print(json.dumps({"alias": alias, "carState": result["counts"].get("carState_events", 0),
                        "wire_absent": result["presence"].get("wire_struct_absent", 0),
                        "wire_present": result["presence"].get("wire_struct_present", 0),
                        "gate": result["recorded_can_header_join_counts"]}, ensure_ascii=False), flush=True)
    except Exception as error:  # noqa: BLE001 - 비공개 원본이 포함될 수 있는 오류 본문을 저장하지 않는다.
      # 원본 경로·payload·절대시각이 포함될 수 있는 예외 본문은 공개하지 않는다.
      failures.append({"alias": alias, "error_type": type(error).__name__})
  report = {
    "recorded_utc": utc, "wall_seconds": time.perf_counter() - started, "files": results, "failures": failures,
    "max_input_age_ns_from_source": original.MAX_INPUT_AGE_NS, "max_can_packets_from_source": original.MAX_CAN_PACKETS,
    "source_hashes": hashes, "source_unchanged": hashes == {name: sha(path) for name, path in source_paths.items()},
    "operating_params_access": False, "carparams_modified": False, "can_transmitted": False,
    "radarcan_process_executed": False, "new_card_metadata_generated": False,
    "actual_collector_receive_clock_available": False, "original_batch_class_executed": True,
    "scope_ko": "기록 schema와 원본 CS/CAN header의 익명집계. 실제 payload/절대원본시각/식별자 출력 없음. 원형 metadata gate를 CS 발행 header 가정에서 실행하며 실제 radarcan/host/차량 활성검증이 아님.",
  }
  (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
  if any(not value["source_file_stat_unchanged"] for value in results):
    raise RuntimeError("진단 중 원본 파일의 크기 또는 수정시각이 바뀌었습니다")
  return int(bool(failures) or not report["source_unchanged"])


if __name__ == "__main__":
  raise SystemExit(main())
