"""기록 CP의 종방향 설정과 안전 설정을 익명 대조한다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import capnp
from panda_policy_probe import INPUT, FILES, events


def main():
  parser = argparse.ArgumentParser(description="기록 CP의 롱컨·순정 롱컨 안전 비트를 직접 대조한다")
  parser.add_argument("--output-dir", type=Path, required=True)
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("이전 결과는 덮어쓰지 않습니다")
  folder = INPUT / "carrot_schemas"
  schema_parser = capnp.SchemaParser()
  schema = schema_parser.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  rows = []
  for index, filename in enumerate(FILES):
    values = Counter()
    with events(INPUT / filename, schema.Event) as stream:
      for event in stream:
        if event.which() == "carParams":
          cp = event.carParams
          configs = tuple((str(item.safetyModel), int(item.safetyParam)) for item in cp.safetyConfigs)
          values[(bool(cp.openpilotLongitudinalControl), bool(cp.pcmCruise), bool(cp.radarUnavailable),
                  int(cp.flags), configs, int(cp.alternativeExperience))] += 1
    snapshots = []
    for (direct_long, pcm, unavailable, flags, configs, alternative), count in values.items():
      snapshots.append({"openpilotLongitudinalControl": direct_long, "pcmCruise": pcm,
        "radarUnavailable": unavailable, "flags": flags, "alternativeExperience": alternative,
        "safetyConfigs": [{"safetyModel": model, "safetyParam": parameter,
                           "stock_longitudinal_bit_512": bool(parameter & 512)} for model, parameter in configs],
        "samples": count})
    rows.append({"alias": "log_"+chr(97+index), "carParams_snapshots": snapshots})
  result = {"files": rows, "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "bit_meaning_source": "현재 ToyotaSafetyFlags.STOCK_LONGITUDINAL=(2 << 8)",
            "scope_ko": "원본 CP 설정 표본이다. actual longActive나 설치 펌웨어 코드 실행을 뜻하지 않는다",
            "settings_modified": False, "vehicle_tx": False}
  args.output_dir.mkdir(parents=True, exist_ok=True)
  (args.output_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
  main()
