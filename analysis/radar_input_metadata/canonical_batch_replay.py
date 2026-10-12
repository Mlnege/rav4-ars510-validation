"""원본 CS 묶음 밖 CAN의 위치를 분류하고 다음 오프라인 연결 설계를 보존한다.

현재 실행 범위는 익명 경계 분류뿐이다. 아래 CANONICAL_DESIGN_KO는 읽기 설계이며
새 adapter/DPath/host 재생은 아직 구현·실행하지 않았다. 기존 probe는 동결 상태다.
"""
import argparse
import bisect
import hashlib
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
from probe import CARD_SOURCE, FIELDS, FILES, INPUT, PROCESS_SOURCE, SOURCE

CANONICAL_DESIGN_KO = {
  "status": "읽기 설계만, adapter 새 경로 미실행",
  "direct_reference": "저장순서 CAN Event마다 원본header/latestCS를 offline adapter에 전달한 기존369점 경로를 그대로 비교기준으로 보존",
  "paired_candidate": "원본 CS.radarInput으로 RadarEgoSample을 만들고 원형 RadarCanBatches에서 실제 CAN 묶음을 얻은 뒤 vEgo/aEgo와 receiveMonoTime으로 offline=True adapter를 호출",
  "consumer_clock": "메타 gate의 now는 원본 CS 발행header를 기준으로 하는 독립가정. 실제collector수신시각이 아니며 코드·보고서에 별도 기록",
  "can_clock": "각 CAN Event의 원본header·src/DLC/payload/순서 유지. receive시각을 모든 packetheader에 복사하거나 같은시각 복수record에 가짜 주기를 주지 않음",
  "original_cp": "원본CP 직렬화 불변, radarUnavailable=True 보존. CP 부족은 부족으로 종료. 운영 RadarInterface/live hook 및 CAN TX 없음",
  "missing_policy": "원형 batch의 missing/stale/overflow/invalid 오류와 pending을 보존. 임의 metadata 또는 CAN 범위를 만들지 않음",
  "history_policy": "canonical decoder 초기화·오류 후 재시작을 별도 기록. 묶이지 않은 CAN을 warmup으로 몰래 입력해 개수를 맞추지 않음",
  "comparison": "record/CRC/points/timeout/sequence/orphan/historyreset/published결과와 처리CAN수·ego association·수신시각·초기화범위를 비교. 369점/175선택을 강제 목표로 사용하지 않음",
  "dpath_followup": "175선택 비교를 할 경우 두 decoder출력을 같은 원본model/pose/EOF·정의된수신시각 및 독립mode1 DPath에 연결하되 invalid/error를 버리지 않음. 현재 이분류 도구는DPath미실행",
  "unbound_policy": "최초CS앞/최종CS뒤/범위사이 CAN은 계약에묶이지 않은 기록이다. 실제socket 유실 또는불필요 데이터라고 확정하지 않고 비교원인으로 분리",
}


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(alias, schema, directory):
  path = INPUT / FILES[alias]
  before = path.stat()
  headers, ranges = [], []
  counts = Counter()
  with tempfile.TemporaryFile("w+b", dir=directory) as decoded:
    with path.open("rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
      shutil.copyfileobj(stream, decoded)
    decoded.seek(0)
    for event in schema.Event.read_multiple(decoded, traversal_limit_in_words=64 * 1024 * 1024):
      if event.which() == "can":
        header = int(event.logMonoTime)
        counts["can_header_reversal"] += int(bool(headers) and header < headers[-1])
        headers.append(header)
      elif event.which() == "carState":
        counts["carState"] += 1
        cs = event.carState
        if "radarInput" not in cs.schema.fields or not cs._has("radarInput"):
          counts["metadata_missing"] += 1
          continue
        meta = cs.radarInput
        if not all(field in meta.schema.fields for field in FIELDS):
          counts["metadata_subfield_missing"] += 1
          continue
        first, last, packet_count, receive = (int(getattr(meta, field)) for field in FIELDS)
        if receive <= 0 or packet_count <= 0 or first <= 0 or last < first:
          counts["nonempty_valid_metadata_not_available"] += 1
          continue
        ranges.append((first, last, packet_count))
  covered = set()
  if not counts["can_header_reversal"]:
    for first, last, packet_count in ranges:
      left = bisect.bisect_left(headers, first)
      right = bisect.bisect_right(headers, last)
      if right - left != packet_count or right <= left or headers[left] != first or headers[right - 1] != last:
        counts["exact_range_failure"] += 1
        continue
      counts["metadata_range_overlap"] += sum(index in covered for index in range(left, right))
      covered.update(range(left, right))
  counts["can_events"] = len(headers)
  counts["nonempty_metadata_ranges"] = len(ranges)
  counts["covered_can_events"] = len(covered)
  counts["unbound_can_events"] = len(headers) - len(covered)
  locations = Counter()
  if ranges and not counts["can_header_reversal"]:
    first_boundary, last_boundary = ranges[0][0], ranges[-1][1]
    for index, header in enumerate(headers):
      if index in covered:
        continue
      if header < first_boundary:
        locations["before_first_cs_metadata_range"] += 1
      elif header > last_boundary:
        locations["after_last_cs_metadata_range"] += 1
      else:
        locations["between_cs_metadata_ranges"] += 1
  else:
    locations["unclassifiable_without_ordered_cs_ranges"] = len(headers) - len(covered)
  after = path.stat()
  return {"alias": alias, "counts": dict(counts), "unbound_location_counts": dict(locations),
          "location_counts_sum_matches_unbound": sum(locations.values()) == counts["unbound_can_events"],
          "source_file_stat_unchanged": before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns,
          "raw_timestamps_saved": False, "can_payload_read_or_saved": False,
          "classification_ko": "처음·마지막의유효한원본CS metadata 범위를 기준으로 분류. 실제socket 유실 원인 판정이 아님."}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  parser.add_argument("--aliases", nargs="+", choices=tuple(FILES), default=list(FILES))
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("기존 결과를 덮어쓰지 않습니다. 새 출력 폴더를 지정하세요")
  args.output_dir.mkdir(parents=True, exist_ok=True)
  folder = INPUT / "carrot_schemas"
  loader = capnp.SchemaParser()
  schema = loader.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  protected = {"probe.py": Path(__file__).with_name("probe.py"), "can_batch.py": SOURCE,
               "radarcan.py": PROCESS_SOURCE, "card.py": CARD_SOURCE, "canonical_batch_replay.py": Path(__file__)}
  hashes = {name: sha(path) for name, path in protected.items()}
  started = time.perf_counter()
  reports = [classify(alias, schema, args.output_dir) for alias in args.aliases]
  result = {"recorded_utc": datetime.now(UTC).isoformat(), "wall_seconds": time.perf_counter() - started,
            "files": reports, "read_design_ko": CANONICAL_DESIGN_KO,
            "source_hashes": hashes, "source_unchanged": hashes == {name: sha(path) for name, path in protected.items()},
            "adapter_new_path_executed": False, "dpath_executed": False, "host_executed": False,
            "can_transmitted": False, "new_metadata_generated": False,
            "scope_ko": "원본header/CS메타경계의익명분류만직접실행. adaptercanonical경로는읽기설계만이며점·record·lead를생성하지않음."}
  (args.output_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
  for report in reports:
    print(json.dumps({"alias": report["alias"], "unbound": report["counts"]["unbound_can_events"],
                      "locations": report["unbound_location_counts"]}, ensure_ascii=False))
  return int(not result["source_unchanged"] or any(not report["source_file_stat_unchanged"]
                                                or not report["location_counts_sum_matches_unbound"] for report in reports))


if __name__ == "__main__":
  raise SystemExit(main())
