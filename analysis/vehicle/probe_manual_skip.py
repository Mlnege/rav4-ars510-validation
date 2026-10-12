"""실제 수동 선택·fingerprint의 조회 생략을 가짜 입출력에서 실행한다.

Params는 메모리이고 CAN 수신은 빈 packet, 송신은 예외로 막는다. 장치·UDS·운영
설정에 접근하지 않는다. 계측 wrapper는 실제 fingerprint를 그대로 호출한다.
"""
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT/'work/native_sim'))
from offline_io import MemoryParams, prepare

prepare()
# Linux에 없는 진행 표시만 이미 설치된 순수 Python 패키지를 읽어 사용한다.
try:
  import tqdm  # noqa: F401
except ModuleNotFoundError:
  progress_path = TASK_ROOT/'work/venv/Lib/site-packages/tqdm'
  progress_spec = importlib.util.spec_from_file_location('tqdm', progress_path/'__init__.py', submodule_search_locations=[str(progress_path)])
  progress_module = importlib.util.module_from_spec(progress_spec)
  sys.modules['tqdm'] = progress_module
  progress_spec.loader.exec_module(progress_module)
from opendbc.can import native
from opendbc.car import car_helpers
from opendbc.car.toyota.values import CAR


class SilentProbeLog:
  """원형 함수의 로그 입출력을 버리고 식별자 출력도 차단한다."""
  def warning(self, *args, **kwargs):
    pass

  def error(self, *args, **kwargs):
    pass


car_helpers.carlog = SilentProbeLog()


class ProbeFinished(Exception):
  pass


counts = {'can_receive_calls': 0, 'can_send_calls': 0, 'OBD_callback_calls': 0, 'fw_count': None,
          'fw_skip_argument': None, 'actual_fingerprint_completed': False}
selected_name = next(doc.name for doc in CAR.TOYOTA_RAV4_TSS2_2022.config.car_docs if 'Hybrid' in doc.name)
MemoryParams.values['CarSelected3'] = selected_name
original_params_get = MemoryParams.get


def selected_text_get(self, key, *args, **kwargs):
  # 원형 Params의 STRING 키 반환형을 유지한다. 그 외 메모리 입출력은 그대로다.
  return selected_name if key == 'CarSelected3' else original_params_get(self, key, *args, **kwargs)


MemoryParams.get = selected_text_get
original = car_helpers.fingerprint


def receive(*args, **kwargs):
  counts['can_receive_calls'] += 1
  return [[]]


def deny_send(*args, **kwargs):
  counts['can_send_calls'] += 1
  raise RuntimeError('읽기 검증은 CAN 송신을 허용하지 않습니다')


def observe_obd(*args, **kwargs):
  counts['OBD_callback_calls'] += 1


def observe_fingerprint(*args, **kwargs):
  counts['fw_skip_argument'] = kwargs.get('skip_fw_query')
  result = original(*args, **kwargs)
  counts['fw_count'] = len(result[3])
  counts['actual_fingerprint_completed'] = True
  # 실제 수신/식별 함수의 결과까지 관찰하고 CP 생성·차량 인터페이스 구성은 실행하지 않는다.
  raise ProbeFinished


car_helpers.fingerprint = observe_fingerprint
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
  try:
    car_helpers.get_car(receive, deny_send, observe_obd, False, True, 1, None)
  except ProbeFinished:
    pass
assert counts['fw_skip_argument'] is True and counts['actual_fingerprint_completed']
assert counts['fw_count'] == 0 and counts['can_send_calls'] == 0
counts['scope'] = '실제 get_car 선택·인자전달과 실제 fingerprint 실행; CP/CI 구성 전 종료'
counts['historical_route_cause_proven'] = False
counts['CAN_raw_backend_in_environment'] = native.BACKEND
counts['CAN_raw_decode_executed'] = False
Path(__file__).with_name('manual_skip_probe.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(counts, ensure_ascii=False), flush=True)
