"""순정 명령 관측과 기록 Panda Toyota 모드 전환의 상대시각을 대조한다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import capnp
from panda_policy_probe import INPUT, FILES, events


def inspect(path, schema, alias):
  toyota_times = []
  stock_times = {0x2e4: [], 0x343: []}
  panda_order = "unseen"
  by_order = {address: Counter() for address in stock_times}
  with events(path, schema) as stream:
    for event in stream:
      kind = event.which()
      if kind == "pandaStates":
        modes = [str(value.safetyModel) for value in event.pandaStates]
        panda_order = "+".join(modes) if modes else "empty"
        if "toyota" in modes:
          toyota_times.append(int(event.logMonoTime))
      elif kind == "can":
        for frame in event.can:
          address = int(frame.address)
          if int(frame.src) == 0 and address in stock_times:
            stock_times[address].append(int(event.logMonoTime))
            by_order[address][panda_order] += 1
  first_toyota = min(toyota_times) if toyota_times else None
  samples = []
  for address, values in stock_times.items():
    deltas = [value-first_toyota for value in values] if first_toyota is not None else []
    samples.append({"address": hex(address), "bus": 0, "frames": len(values),
      "latest_panda_mode_by_storage_order_counts": dict(by_order[address]),
      "before_first_recorded_toyota_header": sum(value < 0 for value in deltas),
      "at_or_after_first_recorded_toyota_header": sum(value >= 0 for value in deltas),
      "relative_to_first_toyota_min_ms": min(deltas)/1e6 if deltas else None,
      "relative_to_first_toyota_max_ms": max(deltas)/1e6 if deltas else None})
  return {"alias": alias, "first_toyota_observed": first_toyota is not None, "stock_command_observations": samples}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  args = parser.parse_args()
  if (args.output_dir / "results.json").exists():
    raise RuntimeError("이전 결과를 덮어쓰지 않습니다")
  folder = INPUT / "carrot_schemas"
  schema_parser = capnp.SchemaParser()
  schema = schema_parser.load((folder / "log.capnp").as_posix(), imports=[folder.as_posix(), (folder / "include").as_posix()])
  result = {"files": [inspect(INPUT / name, schema.Event, "log_"+chr(97+index)) for index, name in enumerate(FILES)],
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "vehicle_tx": False,
    "scope_ko": "기록된 최초 Toyota 상태 헤더와 CAN 헤더의 상대관찰. 실제 모드전환 순간/MCU clock/릴레이 상태 증명이 아님"}
  args.output_dir.mkdir(parents=True, exist_ok=True)
  (args.output_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
  main()
