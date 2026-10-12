"""원본 레이더 상태의 유효성·오류·선행차 종류만 익명 집계한다."""
import hashlib
import json
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import capnp
import zstandard

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "work/input"
OUT = Path(__file__).resolve().parent / "recorded_radar_contract.json"


def main() -> None:
  if OUT.exists():
    raise RuntimeError("기존 결과는 덮어쓰지 않습니다")
  started = time.perf_counter()
  folder = INPUT / "carrot_schemas"
  schemas = {name: folder / name for name in ("log.capnp", "car.capnp")}
  before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in schemas.items()}
  names = ("rlog.zst", "rlog_06.zst", "rlog_11.zst", "rlog_12.zst")
  stats = {name: ((INPUT / name).stat().st_size, (INPUT / name).stat().st_mtime_ns) for name in names}
  parser = capnp.SchemaParser()
  schema = parser.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  rows = []
  for index, name in enumerate(names):
    counts = Counter()
    contracts = Counter()
    lead_types = Counter()
    with tempfile.TemporaryFile("w+b") as decoded:
      with (INPUT / name).open("rb") as compressed, zstandard.ZstdDecompressor().stream_reader(compressed) as stream:
        shutil.copyfileobj(stream, decoded)
      decoded.seek(0)
      for event in schema.Event.read_multiple(decoded, traversal_limit_in_words=64 * 1024 * 1024):
        kind = event.which()
        if kind == "radarState":
          counts["radarState"] += 1
          body = event.radarState
          errors = body.radarErrors.to_dict()
          active_errors = "+".join(sorted(key for key, value in errors.items() if value)) or "none"
          contracts[f"valid={bool(event.valid)};errors={active_errors}"] += 1
          for number in ("leadOne", "leadTwo"):
            lead = getattr(body, number)
            lead_types[f"{number};status={bool(lead.status)};radar={bool(lead.radar)}"] += 1
        elif kind == "carControl":
          counts["carControl"] += 1
          counts["carControl_longActive_true"] += int(event.carControl.longActive)
          counts["carControl_enabled_true"] += int(event.carControl.enabled)
    rows.append({"alias": "log_" + chr(97 + index), "counts": dict(counts),
                 "radar_contract_counts": dict(contracts), "lead_type_counts": dict(lead_types)})
  after = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in schemas.items()}
  unchanged = all(stats[name] == ((INPUT / name).stat().st_size, (INPUT / name).stat().st_mtime_ns) for name in names)
  result = {"files": rows, "source_schema_before": before, "source_schema_after": after,
            "schema_unchanged": before == after, "original_file_stat_unchanged": unchanged,
            "wall_elapsed_s": time.perf_counter() - started,
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "vehicle_tx": False, "params_access": False, "identity_or_coordinates_inspected": False,
            "scope_ko": "원본 radarState 계약의 익명 집계. 진단 ARS 재생과 별도이며 오류 없음이 객체 탐지·PCS·안전성을 입증하지 않는다."}
  OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps({"files": rows, "schema_unchanged": before == after, "input_stat_unchanged": unchanged}, ensure_ascii=False))
  if before != after or not unchanged:
    raise SystemExit(1)


if __name__ == "__main__":
  main()
