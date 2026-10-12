"""실제 계산 코드는 유지하고 저장소·소켓·로그 입출력만 작업 프로세스에 격리한다."""
from collections import Counter
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from types import ModuleType


TASK_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = TASK_ROOT / "work" / "carrotpilot"
# 긴 검증은 실행 중 파일이 바뀌지 않는 고정 빌드 경로를 지정한다.
BUILD_ROOT = Path(os.environ.get("CARROT_VALIDATION_BUILD", str(Path(__file__).resolve().parent / "build")))


def repo_defaults():
  source = (REPO_ROOT / "openpilot/common/params_keys.h").read_text(encoding="utf-8")
  return dict(re.findall(r'\{"([A-Za-z0-9_]+)",\s*\{[^\n]*?,\s*(?:BOOL|INT|FLOAT|STRING),\s*"([^"\n]*)"\}\}', source))


class MemoryParams:
  values = repo_defaults()
  read_counts = Counter()
  write_counts = Counter()

  def __init__(self, *args, **kwargs):
    pass

  def get(self, key, encoding=None, **kwargs):
    self.read_counts[key] += 1
    value = self.values.get(key)
    if value is None:
      return None
    raw = str(value).encode("utf-8")
    return raw.decode(encoding) if encoding else raw

  def get_int(self, key):
    value = self.get(key)
    return int(value) if value else 0

  def get_float(self, key):
    value = self.get(key)
    return float(value) if value else 0.0

  def get_bool(self, key):
    return self.get(key) == b"1"

  def put(self, key, value):
    self.write_counts[key] += 1
    self.values[key] = value.decode() if isinstance(value, bytes) else str(value)

  put_nonblocking = put

  def put_int_nonblocking(self, key, value):
    self.put(key, int(value))

  def put_bool_nonblocking(self, key, value):
    self.put(key, "1" if value else "0")


class SimulationLog:
  counts = Counter()

  def __getattr__(self, level):
    def record(message, *args, **kwargs):
      self.counts[(level, str(message)[:180])] += 1
    return record


def prepare(*, solver_overlay=False):
  for path in (REPO_ROOT, REPO_ROOT / "opendbc_repo"):
    if str(path) not in sys.path:
      sys.path.insert(0, str(path))
  module = ModuleType("openpilot.common.params")
  module.Params = MemoryParams
  sys.modules[module.__name__] = module
  module = ModuleType("openpilot.common.swaglog")
  module.cloudlog = SimulationLog()
  sys.modules[module.__name__] = module

  from openpilot.cereal import log
  messaging = ModuleType("openpilot.cereal.messaging")
  def new_message(service=None, size=None, **kwargs):
    values = {"valid": True, "logMonoTime": int(time.monotonic() * 1e9)}
    values.update(kwargs)
    event = log.Event.new_message(**values)
    if service:
      event.init(service) if size is None else event.init(service, size)
    return event
  messaging.new_message = new_message
  messaging.SubMaster = type("UnusedSubMaster", (), {})
  messaging.PubMaster = type("UnusedPubMaster", (), {})
  def no_socket(*args, **kwargs):
    raise RuntimeError("오프라인 native 검증에서 소켓을 열 수 없습니다")
  messaging.pub_sock = messaging.sub_sock = no_socket
  sys.modules[messaging.__name__] = messaging

  if solver_overlay:
    import openpilot.selfdrive.controls.lib.longitudinal_mpc_lib as package
    package.__path__.insert(0, str(BUILD_ROOT))
  return MemoryParams


if __name__ == "__main__":
  print(json.dumps({"declared_numeric_defaults": len(MemoryParams.values)}, ensure_ascii=False))
