"""직접 실행한 시간 검사에 수입 모듈 출처와 추가 시계·소스 근거를 기록한다."""
import hashlib
import json
from pathlib import Path
import time


WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
SOURCE = ROOT / "work/carrotpilot"
LAB_SOURCE = ROOT / "work/download_e2e/work/carrotpilot"
OUT = WORK / "contract_results.json"
report = json.loads(OUT.read_text())
paths = ["openpilot/cereal/messaging/__init__.py", "openpilot/cereal/messaging/messaging.h",
         "openpilot/cereal/services.py", "openpilot/common/timing.h", "openpilot/common/realtime.py",
         "openpilot/system/camerad/cameras/spectra.cc", "openpilot/selfdrive/modeld/modeld.py",
         "openpilot/selfdrive/modeld/fill_model_msg.py", "openpilot/selfdrive/controls/plannerd.py",
         "openpilot/selfdrive/controls/lib/longitudinal_planner.py", "openpilot/selfdrive/controls/lib/longcontrol.py",
         "openpilot/selfdrive/controls/controlsd.py", "openpilot/selfdrive/car/card.py",
         "openpilot/selfdrive/selfdrived/selfdrived.py", "openpilot/selfdrive/selfdrived/state.py",
         "openpilot/selfdrive/selfdrived/events.py", "openpilot/selfdrive/carrot/signal_assist_runtime.py",
         "openpilot/selfdrive/carrot/signal_stop_prepare_runtime.py", "openpilot/selfdrive/carrot/signal_stop_prepare.py",
         "openpilot/selfdrive/carrot/signal_start_guard.py", "opendbc_repo/opendbc/safety/safety.h",
         "opendbc_repo/opendbc/safety/safety/safety_toyota.h"]
report["review_source_manifest"] = []
for path in paths:
  raw = (SOURCE / path).read_bytes()
  sibling = (LAB_SOURCE / path).read_bytes()
  item = {"path": path, "review_sha256": hashlib.sha256(raw).hexdigest(),
          "review_sha256_lf": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
          "executed_lab_sha256_lf": hashlib.sha256(sibling.replace(b"\r\n", b"\n")).hexdigest()}
  assert item["review_sha256_lf"] == item["executed_lab_sha256_lf"]
  report["review_source_manifest"].append(item)
samples = []
for _ in range(7):
  before = time.monotonic_ns()
  boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
  after = time.monotonic_ns()
  samples.append({"boot_minus_monotonic_midpoint_ns": boot-(before+after)//2,
                  "sampling_uncertainty_ns": (after-before)//2})
report["clock_domain_observations"] = {"runtime": "독립 WSL Python 3.12 환경, Konik 실물 아님", "samples": samples,
  "monotonic": vars(time.get_clock_info("monotonic")), "perf_counter": vars(time.get_clock_info("perf_counter")),
  "actual_device_suspend_offset_verified": False}
report["setup_correction_ko"] = "검사 초안에서 EventName.enable이라는 존재하지 않는 enum을 사용해 중단됐음. 실제 원형 pcmEnable로 고쳐 전체54관측을 다시 실행함. 코어·assertion·정책은 변경하지 않음."
report["measurement_sources"] = ["https://docs.python.org/3.12/library/time.html", "https://docs.kernel.org/core-api/timekeeping.html"]
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"source_files_equal_lf": len(paths), "clock_samples": len(samples)}, ensure_ascii=False))
