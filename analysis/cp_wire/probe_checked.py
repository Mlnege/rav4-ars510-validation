"""기록 CP를 현재 cereal로 읽었을 때 허용된 제어 필드의 의미를 대조한다."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import capnp
import zstandard

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work/carrotpilot"
INPUT = ROOT / "work/input"
FIELDS = ("carFingerprint", "flags", "openpilotLongitudinalControl", "pcmCruise", "radarUnavailable",
          "alternativeExperience", "mass", "wheelbase", "centerToFront", "steerRatio", "radarDelay",
          "longitudinalActuatorDelay", "enableDsu", "enableBsm", "minEnableSpeed", "minSteerSpeed")


def snapshot(value):
  return {"control_fields": {key: getattr(value, key) for key in FIELDS},
          "safety_configs": [{"model": str(config.safetyModel), "parameter": int(config.safetyParam)}
                             for config in value.safetyConfigs], "firmware_entry_count": len(value.carFw)}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("이미 있는 결과는 덮어쓰지 않습니다")
  protected = {"current_car_schema": SOURCE / "opendbc_repo/opendbc/car/car.capnp",
               "recorded_car_schema": INPUT / "carrot_schemas/car.capnp",
               "recorded_log_schema": INPUT / "carrot_schemas/log.capnp",
               "bootstrap": SOURCE / "tools/ars510_offline/bootstrap.py"}
  before_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in protected.items()}
  input_stats = {name: ((INPUT / name).stat().st_size, (INPUT / name).stat().st_mtime_ns)
                 for name in ("rlog.zst", "rlog_06.zst", "rlog_11.zst", "rlog_12.zst")}
  spec = importlib.util.spec_from_file_location("offline_bootstrap", SOURCE / "tools/ars510_offline/bootstrap.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  params_backend = module.prepare()
  from openpilot.cereal import car
  folder = INPUT / "carrot_schemas"
  schema_parser = capnp.SchemaParser()
  schema = schema_parser.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  results = []
  failures = []
  for index, name in enumerate(("rlog.zst", "rlog_06.zst", "rlog_11.zst", "rlog_12.zst")):
    alias = "log_"+chr(97+index)
    cp_rows = []
    with tempfile.TemporaryFile("w+b") as decoded:
      with (INPUT / name).open("rb") as compressed, zstandard.ZstdDecompressor().stream_reader(compressed) as stream:
        shutil.copyfileobj(stream, decoded)
      decoded.seek(0)
      for event in schema.Event.read_multiple(decoded, traversal_limit_in_words=64*1024*1024):
        if event.which() != "carParams":
          continue
        old = event.carParams
        raw = old.as_builder().to_bytes()
        with car.CarParams.from_bytes(raw) as current:
          before, after = snapshot(old), snapshot(current)
          differences = [key for key in before if before[key] != after[key]]
          if differences:
            failures.append({"alias": alias, "sample": len(cp_rows), "different_groups": differences})
          cp_rows.append({"same": not differences, "recorded_fields": before})
    results.append({"alias": alias, "carParams_samples": len(cp_rows), "snapshots": cp_rows})
  after_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in protected.items()}
  unchanged = before_hashes == after_hashes
  original_stat_unchanged = all(input_stats[name] == ((INPUT / name).stat().st_size, (INPUT / name).stat().st_mtime_ns)
                                for name in input_stats)
  result = {"files": results, "failures": failures, "params_backend": params_backend,
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "fields_checked": list(FIELDS), "vehicle_tx": False, "source_unchanged": unchanged,
            "source_hashes_before": before_hashes, "source_hashes_after": after_hashes,
            "original_file_stat_unchanged": original_stat_unchanged,
            "identity_fields_inspected": False,
            "scope_ko": "기록 CP wire의 허용 필드와 현재 reader 대조. 모든 ordinal·미검사 필드·생성자 동작·설치 펌웨어 호환성 증명이 아님"}
  args.output_dir.mkdir(parents=True, exist_ok=True)
  (args.output_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps({"samples": sum(row["carParams_samples"] for row in results), "failures": failures,
                    "params_backend": params_backend}, ensure_ascii=False))
  return int(bool(failures) or not unchanged or not original_stat_unchanged)


if __name__ == "__main__":
  sys.exit(main())
