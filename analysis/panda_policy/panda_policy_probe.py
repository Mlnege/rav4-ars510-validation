"""기록 CP/Panda의 안전 설정·권한·오류만 익명 집계한다. 식별 필드는 읽지 않는다."""
import argparse
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import capnp
import zstandard

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "work/input"
FILES = ("rlog.zst", "rlog_06.zst", "rlog_11.zst", "rlog_12.zst")


@contextmanager
def events(path, schema):
  with tempfile.TemporaryFile("w+b") as decoded:
    with path.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as stream:
      shutil.copyfileobj(stream, decoded)
    decoded.seek(0)
    yield schema.read_multiple(decoded, traversal_limit_in_words=64 * 1024 * 1024)


def collect(path, schema, alias):
  cp = Counter()
  settings = Counter()
  faults = Counter()
  state = Counter()
  available_fields = set()
  for_kind = Counter()
  with events(path, schema) as stream:
    for event in stream:
      kind = event.which()
      if kind == "carParams":
        value = event.carParams
        for_kind["carParams"] += 1
        config = tuple((str(item.safetyModel), int(item.safetyParam)) for item in value.safetyConfigs)
        cp[(config, int(value.alternativeExperience))] += 1
      elif kind == "pandaStates":
        for_kind["pandaStates_events"] += 1
        for value in event.pandaStates:
          for_kind["pandaState_entries"] += 1
          fields = value.schema.fields
          available_fields.update(name for name in ("controlsAllowed", "safetyModel", "safetyParam",
            "alternativeExperience", "faults", "safetyRxChecksInvalid", "rxChecksInvalid") if name in fields)
          setting = (str(value.safetyModel), int(value.safetyParam), int(value.alternativeExperience))
          settings[setting] += 1
          state["controlsAllowed_true"] += int(value.controlsAllowed)
          for name in ("safetyRxChecksInvalid", "rxChecksInvalid"):
            if name in fields:
              state[name+"_true"] += int(getattr(value, name))
          for fault in value.faults:
            faults[str(fault)] += 1
  return {"alias": alias, "record_counts": dict(for_kind), "available_allowed_fields": sorted(available_fields),
    "recorded_cp_configs": [{"safetyConfigs": [{"safetyModel": model, "safetyParam": parameter} for model, parameter in config],
                             "alternativeExperience": alternative, "samples": count}
                            for (config, alternative), count in cp.items()],
    "recorded_panda_configs": [{"safetyModel": model, "safetyParam": parameter,
                                "alternativeExperience": alternative, "samples": count}
                               for (model, parameter, alternative), count in settings.items()],
    "permission_and_rx_counts": dict(state), "fault_sample_counts": dict(faults)}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("이미 있는 결과를 덮어쓰지 않습니다")
  args.output_dir.mkdir(parents=True, exist_ok=True)
  folder = INPUT / "carrot_schemas"
  schema_parser = capnp.SchemaParser()
  schema = schema_parser.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  results = [collect(INPUT / name, schema.Event, "log_"+chr(97+index)) for index, name in enumerate(FILES)]
  report = {"files": results, "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "vehicle_tx": False, "settings_modified": False, "firmware_identity_read": False,
            "scope_ko": "기록된 설정·오류 표본 집계이며 설치 펌웨어 코드나 실물 릴레이 동작 검증은 아님"}
  (args.output_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
  main()
