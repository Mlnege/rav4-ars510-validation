"""남은 명령 전환 지연을 실제 메모리 CAN 생성 시각으로 측정한다."""
import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys

import run

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
BUILD = ROOT / "work/native_sim/build_force_decel_frozen"
package = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib")
package.__path__.insert(0, str(BUILD))
mpc = importlib.import_module("openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc")
name = "openpilot.selfdrive.controls.lib.longitudinal_planner"
spec = importlib.util.spec_from_file_location(name, run.SOURCE / "openpilot/selfdrive/controls/lib/longitudinal_planner.py")
planner = importlib.util.module_from_spec(spec)
sys.modules[name] = planner
spec.loader.exec_module(planner)
assert Path(mpc.__file__).resolve() == (BUILD / "long_mpc.py").resolve()
original_chain = run.Chain
instances = []


class ObservedChain(original_chain):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    instances.append(self)


run.Chain = ObservedChain
folder = WORK / "tx_transition"
if folder.exists():
  raise RuntimeError("기존 전환 결과는 덮어쓰지 않습니다")
folder.mkdir()
protected = [BUILD / "long_mpc.py", Path(planner.__file__), *sorted((BUILD / "c_generated_code").glob("*.so*")),
             run.LAB / "work/safety_validation/libsafety_download_native.so"]
before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
with run.quiet_c_stdout(), run.hide_stderr(), contextlib.redirect_stdout(io.StringIO()):
  case, rows = run.one_case("temporary", "radarUnavailableTemporary", False, False)
origin_ns = round(rows[0]["time"] * 1e9)
can_rows = [row for row in instances[0].physical.generated_rows if row["time_ns"] >= origin_ns]
accel = [row for row in can_rows if row["address"] == 0x343]
first_negative = next((row for row in accel if row["raw_accel_signed"] < 0), None)
intervals = [(b["time_ns"] - a["time_ns"]) / 1e9 for a, b in zip(accel, accel[1:])]
after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
result = {"kind": "temporary", "case": case, "accel_can_count": len(accel),
          "first_negative_CAN_s": None if first_negative is None else (first_negative["time_ns"] - origin_ns) / 1e9,
          "first_negative_CAN_c_accept": None if first_negative is None else first_negative["actual_tx"],
          "accel_CAN_interval_s": {"min": min(intervals), "max": max(intervals)},
          "runtime_before": before, "runtime_after": after, "files_unchanged": before == after,
          "actual_vehicle_tx": False, "virtual_time": True,
          "observer_policy_changes": False,
          "scope_ko": "명목100Hz 가상 호출의 메모리 송신 타이밍. 실제 벽시계·차량 감속·Panda USB/MCU 마감 보장은 아니다."}
(folder / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(folder / "generated_can_rows.json").write_text(json.dumps(can_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"first_negative_CAN_s": result["first_negative_CAN_s"],
                  "c_accept": result["first_negative_CAN_c_accept"], "interval_s": result["accel_CAN_interval_s"],
                  "files_unchanged": before == after}, ensure_ascii=False))
raise SystemExit(0 if before == after and first_negative is not None and first_negative["actual_tx"] == 1 and not case["failures"] else 1)
