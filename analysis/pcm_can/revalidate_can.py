"""저장된 실제 생성 CAN의 전제와 실제 C relay/권한 상태를 독립 재생한다.

수신은 같은 명시적 정상/운전자 PCM fixture이며 실제 송신/장치 연결은 없다.
"""
import ctypes
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from whole_io import WORK, SOURCE, Clock, clock_inputs, MemoryConfiguration
from whole_io import MemoryBus, memory_messaging


def main():
  clock=Clock()
  details=[]
  module=memory_messaging(MemoryBus())
  from whole_objects import car_params
  from whole_inputs import VehiclePermissionInput
  from openpilot.selfdrive.car.alternative_experience import get_alternative_experience
  suite=json.loads((WORK/'suite_summary.json').read_text())
  for case in suite['cases']:
    path=WORK/'cases'/case['kind']/'result.json'
    result=json.loads(path.read_text())
    generated=result['generated_can_rows']
    invariant_checks={
      'all_exact_bus_dlc':all(r['bus']==0 and r['dlc']==(5 if r['address']==0x2e4 else 8) for r in generated),
      'zero_lka_torque':all(r['decoded_signals']['STEER_TORQUE_CMD']==0 for r in generated if r['address']==0x2e4),
      'nonactuating_lta':all(all(r['decoded_signals'][key]==0 for key in ('STEER_REQUEST','STEER_REQUEST_2',
        'STEER_ANGLE_CMD','TORQUE_WIND_DOWN')) for r in generated if r['address']==0x191),
      'pcs_hud_is_not_preservation_claim':all(r['decoded_signals']['PCS_INDICATOR']==1 and
        r['decoded_signals']['PCS_OFF']==1 for r in generated if r['address']==0x411),
      'uds_only_exact_tester_present':all(r['generated_payload_hex']=='0f023e0000000000' for r in generated if r['address']==0x750),
    }
    by_tick={}
    for row in generated:
      by_tick.setdefault(row['time_ns'],[]).append(row)
    fault_inputs={round(r['time']*1e9):r for r in result['rows']}
    with clock_inputs(clock):
      cp=car_params()
      # 원형 Card constructor가 사용하는 경험 설정 함수의 실제 기본 읽기를 사용한다.
      alternative=get_alternative_experience(MemoryConfiguration().get_bool('DisengageOnAccelerator'))
      assert alternative==result['cp']['alternativeExperience']
      permission=VehiclePermissionInput(SimpleNamespace(safetyConfigs=cp.safetyConfigs,alternativeExperience=alternative))
      permission.probe.lib.get_relay_malfunction.restype=ctypes.c_bool
      trace=[]
      fault_start=min(fault_inputs)
      for t_ns in range(100_000_000_000,max(by_tick)+1,10_000_000):
        clock.now=t_ns*1e-9
        if t_ns>=fault_start:
          inputs=fault_inputs[t_ns]
          permission.update(clock.now,engaged=inputs['engaged'],gas=inputs['gas'],brake=inputs['brake'])
        else:
          permission.update(clock.now,engaged=t_ns>=102_000_000_000)
        for original in by_tick.get(t_ns,[]):
          p=permission.probe
          before=permission.allowed()
          long_before=bool(p.lib.get_longitudinal_allowed())
          relay_before=bool(p.lib.get_relay_malfunction())
          actual=int(p.packet('tx',original['address'],bytes.fromhex(original['generated_payload_hex']),original['bus']))
          after=permission.allowed()
          long_after=bool(p.lib.get_longitudinal_allowed())
          relay_after=bool(p.lib.get_relay_malfunction())
          trace.append({'time_ns':t_ns,'address':original['address'],'c_controls_before':before,
            'c_longitudinal_before':long_before,'c_relay_before':relay_before,'c_relay_after':relay_after,
            'actual_tx':actual,'original_tx':original['actual_tx'],
            'c_permissions_match_original':before==original['c_controls_before'] and long_before==original['c_longitudinal_before'],
            'tx_matches_original':actual==original['actual_tx'],
            'tx_authority_unchanged':before==after and long_before==long_after and relay_before==relay_after})
      invariant_checks.update(all_messages_replayed=len(trace)==len(generated),
        actual_relay_false=all(not r['c_relay_before'] and not r['c_relay_after'] for r in trace),
        actual_c_permissions_match_original=all(r['c_permissions_match_original'] for r in trace),
        actual_c_tx_match_original=all(r['tx_matches_original'] for r in trace),
        actual_c_tx_no_permission_mutation=all(r['tx_authority_unchanged'] for r in trace),
        no_c_permission_shortcut=permission.shortcut_controls_true_calls==0)
      detail={'kind':case['kind'],'generated_case_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'checks':invariant_checks,'failures':[name for name,passed in invariant_checks.items() if not passed],
        'count':len(trace),'trace':trace,'permission_rx_frames':permission.received,
        'factory_safety_param':int(cp.safetyConfigs[0].safetyParam),'source_alternativeExperience':alternative,
        'source_hashes_still_same':all(hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==digest for name,digest in result['source_hashes'].items())}
      folder=WORK/'can_revalidation'/case['kind']
      folder.mkdir(parents=True,exist_ok=True)
      (folder/'result.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
      details.append({key:value for key,value in detail.items() if key!='trace'})
      print(json.dumps({k:detail[k] for k in ('kind','count','failures','source_hashes_still_same')},ensure_ascii=False),flush=True)
  report={'recorded_utc':datetime.now(UTC).isoformat(),'cases':details,
    'message_count':sum(r['count'] for r in details),'failure_count':sum(len(r['failures']) for r in details),
    'assertion_count':sum(len(r['checks']) for r in details),
    'scope_ko':'앞선 원형 호스트/ToyotaCC 생성 결과를 그대로 저장바이트로 독립 C재생. 실제 C relay/permission/TX 불변을 확인함. 처음350틱은 같은 warm schedule, 이후 저장명시 운전자 PCM 입력. controlsAllowed 직접설정0, 실물 relay/ECU/차량 송신 미검증.'}
  (WORK/'can_revalidation_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  assert not report['failure_count'] and all(r['source_hashes_still_same'] for r in details)


if __name__=='__main__':main()
