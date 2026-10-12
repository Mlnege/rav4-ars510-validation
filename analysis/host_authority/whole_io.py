"""원형 판정은 유지하고 소켓·설정 저장소·물리 초기화/송신만 메모리로 격리한다."""
import ast
from collections import defaultdict
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType
import typing


WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
SOURCE = ROOT / "work/carrotpilot"
LAB = ROOT / "work/download_e2e"
os.environ["CARROT_VALIDATION_BUILD"] = str(LAB / "work/native_sim/build_unique")
sys.path[:0] = [str(SOURCE), str(SOURCE / "opendbc_repo"), str(LAB / "work/native_sim")]
assert "SIMULATION" not in os.environ and "REPLAY" not in os.environ
from offline_io import MemoryParams, prepare
prepare(solver_overlay=True)
sys.path[:0] = [str(SOURCE), str(SOURCE / "opendbc_repo")]


class MemoryConfiguration(MemoryParams):
  """운영 Params API와 같은 입출력 역할만 수행하는 프로세스 내부 저장소."""
  bytes_values = {}

  def get(self, key, encoding=None, **kwargs):
    if key in self.bytes_values:
      value = self.bytes_values[key]
      return value.decode(encoding) if encoding else value
    return super().get(key, encoding=encoding, **kwargs)

  def put_bool(self, key, value):
    self.put(key, "1" if value else "0")

  def put(self, key, value):
    self.write_counts[key] += 1
    if isinstance(value, bytes):
      self.bytes_values[key] = value
    else:
      self.values[key] = json.dumps(value) if isinstance(value, dict) else str(value)

  put_nonblocking = put

  def put_int(self, key, value):
    self.put(key, int(value))

  def put_float(self, key, value):
    self.put(key, float(value))

  put_bool_nonblocking = put_bool
  put_int_nonblocking = put_int

  def remove(self, key):
    self.values.pop(key, None)
    self.bytes_values.pop(key, None)

  def all_keys(self):
    return set(self.values) | set(self.bytes_values)


sys.modules["openpilot.common.params"].Params = MemoryConfiguration
import capnp
from openpilot.cereal import car, log
from openpilot.cereal.services import SERVICE_LIST
from openpilot.common.utils import MovingAverage


class Clock:
  def __init__(self):
    self.now = 100.


@contextlib.contextmanager
def clock_inputs(clock):
  """테스트 프로세스의 시각 입력만 바꾸며 실제 벽시계/CPU 측정은 보존한다."""
  old = time.monotonic, time.monotonic_ns
  time.monotonic = lambda: clock.now
  time.monotonic_ns = lambda: round(clock.now*1e9)
  try:
    yield
  finally:
    time.monotonic, time.monotonic_ns = old


class MemorySocket:
  def __init__(self, service, bus):
    self.service, self.bus = service, bus
    self.queue = []

  def receive(self, non_blocking=False):
    if not self.queue:
      return None
    value = self.queue[-1]
    self.queue.clear()
    return value

  def send(self, value):
    self.bus.emit(self.service, value)

  def all_readers_updated(self):
    return True


class MemoryPoller:
  def __init__(self):
    self.sockets = []

  def poll(self, timeout):
    return [sock for sock in self.sockets if sock.queue]


class MemoryBus:
  def __init__(self):
    self.receivers = defaultdict(list)
    self.sent_counts = defaultdict(int)
    self.latest = {}
    self.records = []

  def subscriber(self, service, poller=None, **kwargs):
    sock = MemorySocket(service, self)
    self.receivers[service].append(sock)
    if poller is not None:
      poller.sockets.append(sock)
    return sock

  def publisher(self, service):
    return MemorySocket(service, self)

  def emit(self, service, value):
    if not isinstance(value, bytes):
      value = value.to_bytes()
    self.latest[service] = value
    self.sent_counts[service] += 1
    for sock in self.receivers[service]:
      sock.queue.append(value)


SOURCE_HASHES = {}


def load_definitions(relative, namespace, names=None):
  raw = (SOURCE / relative).read_bytes()
  SOURCE_HASHES[relative] = hashlib.sha256(raw).hexdigest()
  tree = ast.parse(raw.decode("utf-8"))
  selected = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
              and (names is None or node.name in names)]
  body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *selected]
  exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(SOURCE / relative), "exec"), namespace)
  return namespace


def memory_messaging(bus):
  """new_message/수신/발행/SubMaster 본문을 원형 그대로 사용한다."""
  module = ModuleType("openpilot.cereal.messaging")
  namespace = module.__dict__
  namespace.update(vars(typing))
  namespace.update(os=os, time=time, capnp=capnp, log=log, SERVICE_LIST=SERVICE_LIST, MovingAverage=MovingAverage,
                   Poller=MemoryPoller, sub_sock=bus.subscriber, pub_sock=bus.publisher,
                   NO_TRAVERSAL_LIMIT=2**64-1)
  names = {"log_from_bytes", "new_message", "recv_one", "recv_one_or_none", "FrequencyTracker", "SubMaster", "PubMaster"}
  load_definitions("openpilot/cereal/messaging/__init__.py", namespace, names)
  sys.modules[module.__name__] = module
  import openpilot.cereal
  openpilot.cereal.messaging = module
  return module


class AbsentFaultFile:
  def read_text(self):
    raise FileNotFoundError("테스트 입력: 외부 inference fault 파일 없음")


class PhysicalInterfaceSink:
  """소프트웨어 판정 이후의 실제 차량 초기화/송신을 실행하지 않는다."""
  def __init__(self):
    self.init_io_sink_calls = 0
    self.apply_calls = []
    self.actual_init_executed = False

  def init(self, *args, **kwargs):
    self.init_io_sink_calls += 1

  def apply(self, cc, now, model=None, radar=None):
    self.apply_calls.append({"time_ns": now, "enabled": bool(cc.enabled), "longActive": bool(cc.longActive),
                             "latActive": bool(cc.latActive), "accel": float(cc.actuators.accel),
                             "cancel": bool(cc.cruiseControl.cancel), "model_supplied": model is not None,
                             "radar_supplied": radar is not None})
    return car.CarControl.Actuators(), []


def source_unchanged():
  return all(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest for name, digest in SOURCE_HASHES.items())
