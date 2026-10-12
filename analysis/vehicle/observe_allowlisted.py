"""차량 식별 원인을 허용 항목만 읽어 범주·개수로 기록한다.

VIN·펌웨어 문자열·주소·계정·경로·위치·원본 설정 묶음은 읽거나 출력하지 않는다.
initData의 명시한 설정값과 정형 모델명, CAN의 기존 기어/GVC/브레이크만 관찰한다.
CAN 송신·펌웨어 조회·CP/설정 변경·차량 접근 기능은 없다.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

import zstandard

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT/'work/native_sim'))
from offline_io import prepare

prepare()
from opendbc.can import CANDefine, CANParser, native
from opendbc.car import Bus
from opendbc.car.selected_car import get_selected_car_platform
from opendbc.car.toyota.values import CAR, DBC, ToyotaFlags
from openpilot.cereal import log

BOOL_SETTINGS = frozenset(('AlphaLongitudinalEnabled', 'OpenpilotEnabledToggle', 'DisengageOnAccelerator', 'FirmwareQueryDone'))
NUM_SETTINGS = frozenset(('CruiseButtonMode', 'SpeedFromPCM', 'EnableRadarTracks', 'LongActuatorDelay', 'StoppingAccel',
                          'LongTuningKpV', 'LongTuningKiV', 'LongTuningKf'))
PRESENCE_ONLY = frozenset(('CarParamsCache', 'CarParamsPersistent', 'Offroad_NoFirmware'))
ALLOWED_SETTINGS = BOOL_SETTINGS | NUM_SETTINGS | PRESENCE_ONLY | {'CarSelected3'}
FRAME_NAMES = {0x127: 'GEAR_PACKET_HYBRID', 0x3bc: 'GEAR_PACKET', 0x320: 'VSC1S07', 0x226: 'BRAKE_MODULE'}
KNOWN_MODELS = frozenset(str(platform) for platform in CAR)
FLAG_NAMES = ('HYBRID', 'RADAR_ACC', 'DISABLE_RADAR', 'TSS2', 'NO_DSU', 'NO_STOP_TIMER', 'SECOC', 'RAISED_ACCEL_LIMIT')


def sign(value):
  if not math.isfinite(value):
    return 'nonfinite'
  return 'positive' if value > 0. else 'negative' if value < 0. else 'zero'


def safe_setting(entry):
  key = entry.key
  if key in PRESENCE_ONLY:
    return {'present': True}
  raw = bytes(entry.value)
  if key in BOOL_SETTINGS:
    return {'valid_boolean': raw in (b'0', b'1'), 'value': raw == b'1'}
  if key in NUM_SETTINGS:
    try:
      if len(raw) > 24:
        raise ValueError
      value = float(raw.decode('ascii'))
      if not math.isfinite(value):
        raise ValueError
      return {'valid_number': True, 'value': value}
    except (ValueError, UnicodeError):
      return {'valid_number': False}
  if key == 'CarSelected3':
    try:
      if len(raw) > 160:
        raise ValueError
      name = raw.decode('utf-8')
      selected = get_selected_car_platform(name)
      return {'recognized_selection': selected is not None,
              'selected_model': str(selected) if selected is not None else None,
              'known_doc_mentions_hybrid': selected is not None and any(doc.name == name and 'Hybrid' in doc.name for doc in selected.config.car_docs)}
    except (ValueError, UnicodeError):
      return {'recognized_selection': False, 'selected_model': None}
  raise ValueError('허용되지 않은 설정값을 요청했습니다')


def cp_summary(cp):
  model = str(cp.carFingerprint)
  known = model in KNOWN_MODELS
  flags = int(cp.flags)
  # carFw의 ECU 범주와 개수만 접근한다. fwVersion·주소·VIN에는 접근하지 않는다.
  ecu_counts = Counter(str(fw.ecu) for fw in cp.carFw)
  result = {
    'known_toyota_model': known, 'model': model if known else None, 'brand_is_toyota': cp.brand == 'toyota',
    'flags': {name: bool(flags & int(getattr(ToyotaFlags, name))) for name in FLAG_NAMES},
    'carFw_count': len(cp.carFw), 'ecu_type_counts': dict(ecu_counts),
    'fingerprint_source': str(cp.fingerprintSource), 'fuzzy': bool(cp.fuzzyFingerprint),
    'pcmCruise': bool(cp.pcmCruise), 'directLong': bool(cp.openpilotLongitudinalControl),
    'radarUnavailable': bool(cp.radarUnavailable), 'enableDsu': bool(cp.enableDsu), 'passive': bool(cp.passive),
    'longitudinalActuatorDelay': float(cp.longitudinalActuatorDelay), 'radarDelay': float(cp.radarDelay),
    'transmission_type': str(cp.transmissionType),
  }
  if known:
    dbcs = DBC[model]
    result['pt_dbc'] = dbcs.get(Bus.pt)
    result['radar_dbc_present'] = Bus.radar in dbcs
    result['selected_gear_message_by_current_source'] = 'GEAR_PACKET_HYBRID' if result['flags']['SECOC'] else 'GEAR_PACKET'
  return result


def observe(path, label):
  rows = []
  cp_counts = Counter()
  cp_variants = {}
  settings_counts = Counter()
  settings_variants = {}
  event_counts, state_counts, can_counts, signal_counts, controller_counts = (Counter() for _ in range(5))
  dbc = TASK_ROOT/'work/native_sim/dbc/toyota_nodsu_pt_generated.dbc'
  parser = CANParser(str(dbc), [(name, float('nan')) for name in FRAME_NAMES.values()], 0)
  define = CANDefine(str(dbc))
  compressed = path.read_bytes()
  with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
    data = reader.read()
  for event in log.Event.read_multiple_bytes(data):
    kind = event.which()
    if kind not in ('carParams', 'initData', 'carState', 'can', 'carControl', 'selfdriveState'):
      continue
    event_counts[kind] += 1
    if kind == 'carParams':
      result = cp_summary(event.carParams)
      key = json.dumps(result, sort_keys=True)
      cp_counts[key] += 1
      cp_variants[key] = result
    elif kind == 'initData':
      settings = {}
      for entry in event.initData.params.entries:
        # 그 밖의 value나 initData 식별·네트워크·명령 필드는 접근하지 않는다.
        if entry.key in ALLOWED_SETTINGS:
          settings[entry.key] = safe_setting(entry)
      key = json.dumps(settings, sort_keys=True)
      settings_counts[key] += 1
      settings_variants[key] = settings
    elif kind == 'carState':
      cs = event.carState
      state_counts['gear:'+str(cs.gearShifter)] += 1
      state_counts['canValid:'+str(bool(cs.canValid))] += 1
      state_counts['brakePressed:'+str(bool(cs.brakePressed))] += 1
      state_counts['regenBraking:'+str(bool(cs.regenBraking))] += 1
      state_counts['cruiseEnabled:'+str(bool(cs.cruiseState.enabled))] += 1
      state_counts['cruiseAvailable:'+str(bool(cs.cruiseState.available))] += 1
      state_counts['gasPressed:'+str(bool(cs.gasPressed))] += 1
      state_counts['accFaulted:'+str(bool(cs.accFaulted))] += 1
      state_counts['speed:'+('zero' if cs.vEgo == 0. else 'nonzero')] += 1
      state_counts['aEgo:'+sign(float(cs.aEgo))] += 1
      if cs.aEgo < 0. and not cs.brakePressed:
        state_counts['negative_aEgo_without_brakePressed'] += 1
    elif kind == 'carControl':
      control = event.carControl
      controller_counts['state:'+str(control.actuators.longControlState)] += 1
      controller_counts['longActive:'+str(bool(control.longActive))] += 1
      controller_counts['accel:'+sign(float(control.actuators.accel))] += 1
      controller_counts['enabled:'+str(bool(control.enabled))] += 1
      controller_counts['latActive:'+str(bool(control.latActive))] += 1
    elif kind == 'selfdriveState':
      state = event.selfdriveState
      controller_counts['selfdriveEnabled:'+str(bool(state.enabled))] += 1
      controller_counts['selfdriveActive:'+str(bool(state.active))] += 1
    elif kind == 'can':
      packets = []
      for frame in event.can:
        address, bus = int(frame.address), int(frame.src)
        if address not in FRAME_NAMES or bus != 0:
          continue
        can_counts[FRAME_NAMES[address]] += 1
        if len(frame.dat) != 8:
          can_counts['non8byte:'+FRAME_NAMES[address]] += 1
          continue
        packets.append((address, bytes(frame.dat), bus))
      if packets:
        decoded = parser.update([(event.logMonoTime, packets)])
        for address in decoded:
          name = FRAME_NAMES[address]
          values = parser.vl[name]
          if name == 'VSC1S07':
            signal_counts['GVC:'+sign(float(values['GVC']))] += 1
            signal_counts['XGVCINV:'+str(bool(values['XGVCINV']))] += 1
          elif name == 'BRAKE_MODULE':
            signal_counts['BRAKE_PRESSED:'+str(bool(values['BRAKE_PRESSED']))] += 1
          else:
            signal_counts[name+':GEAR_CODE_'+str(int(values['GEAR']))] += 1
            semantic = define.dv[name]['GEAR'].get(int(values['GEAR']), 'unknown')
            signal_counts[name+':GEAR_'+semantic] += 1
  rows.append({'anonymous_log': label, 'event_counts': dict(event_counts),
               'CAN_raw_backend': native.BACKEND,
               'carParams_variants': [value | {'count': cp_counts[key]} for key, value in cp_variants.items()],
               'init_allowlisted_variants': [{'count': settings_counts[key], 'settings': value} for key, value in settings_variants.items()],
               'carState_category_counts': dict(state_counts), 'selected_CAN_counts': dict(can_counts),
               'CAN_signal_category_counts': dict(signal_counts), 'control_category_counts': dict(controller_counts)})
  return rows[0]


def main():
  root = Path(__file__).parent
  inputs = TASK_ROOT/'work/input'
  files = ('rlog.zst', 'rlog_06.zst', 'rlog_11.zst', 'rlog_12.zst')
  results = []
  for index, filename in enumerate(files, 1):
    result = observe(inputs/filename, f'log_{index}')
    results.append(result)
    print(json.dumps({'anonymous_log': result['anonymous_log'], 'carParams_variants': result['carParams_variants'],
                      'init_allowlisted_variants': result['init_allowlisted_variants']}, ensure_ascii=False), flush=True)
  (root/'observations.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
  main()
