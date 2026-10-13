"""격리된 실제 MPC 계산에 메모리 설정과 소켓 차단을 제공한다."""
from collections import Counter
import os
from pathlib import Path
import re
import sys
from types import ModuleType
import time

REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_defaults():
  source = (REPO_ROOT / "openpilot/common/params_keys.h").read_text(encoding="utf-8")
  return dict(re.findall(r'\{"([A-Za-z0-9_]+)",\s*\{[^\n]*?,\s*(?:BOOL|INT|FLOAT|STRING),\s*"([^"\n]*)"\}\}', source))


class MemoryParams:
  """검사 프로세스 내부의 설정이다. 운영 저장소를 열거나 갱신하지 않는다."""
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
    raw = str(value).encode()
    return raw.decode(encoding) if encoding else raw

  def get_int(self, key):
    return int(self.get(key) or 0)

  def get_float(self, key):
    return float(self.get(key) or 0.0)

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


class QuietLog:
  def __getattr__(self, level):
    return lambda *args, **kwargs: None


def prepare_io():
  """계산 코드는 바꾸지 않고 설정·로그·전송 입출력만 격리한다."""
  for path in (REPO_ROOT, REPO_ROOT / "opendbc_repo"):
    if str(path) not in sys.path:
      sys.path.insert(0, str(path))
  params = ModuleType("openpilot.common.params")
  params.Params = MemoryParams
  sys.modules[params.__name__] = params
  logging = ModuleType("openpilot.common.swaglog")
  logging.cloudlog = QuietLog()
  sys.modules[logging.__name__] = logging
  from openpilot.cereal import log
  messaging = ModuleType("openpilot.cereal.messaging")

  def new_message(service=None, size=None, **kwargs):
    fields = {"valid": True, "logMonoTime": time.monotonic_ns(), **kwargs}
    event = log.Event.new_message(**fields)
    if service:
      event.init(service) if size is None else event.init(service, size)
    return event

  def forbidden_socket(*args, **kwargs):
    raise RuntimeError("오프라인 계산 검사에서 소켓을 열 수 없습니다")

  messaging.new_message = new_message
  messaging.SubMaster = type("UnusedSubMaster", (), {})
  messaging.PubMaster = type("UnusedPubMaster", (), {})
  messaging.pub_sock = messaging.sub_sock = forbidden_socket
  sys.modules[messaging.__name__] = messaging
  return MemoryParams


def prepare(*, solver_root=None):
  """수신/설정 입출력과 별도로 동결 native MPC 사본을 선택한다."""
  prepare_io()
  build = solver_root or os.environ.get("CARROT_VALIDATION_BUILD")
  if not build:
    raise RuntimeError("별도의 동결 native MPC 경로를 지정해야 합니다")
  build = Path(build).resolve()
  original = (REPO_ROOT / "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py").read_bytes().replace(b"\r\n", b"\n")
  if (build / "long_mpc.py").read_bytes().replace(b"\r\n", b"\n") != original:
    raise RuntimeError("동결 Python 사본이 검사할 소스와 다릅니다")
  import openpilot.selfdrive.controls.lib.longitudinal_mpc_lib as package
  if "openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc" in sys.modules:
    raise RuntimeError("MPC가 이미 다른 경로에서 로드됐습니다. 새 프로세스를 사용하세요")
  package.__path__.insert(0, str(build))
  return MemoryParams
