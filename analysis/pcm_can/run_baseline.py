"""원형 state_update가 포함된 정상 enable와 Mode0 실제 속도 연결을 먼저 확인한다."""
from datetime import datetime, UTC
import json

from whole_io import WORK, Clock, clock_inputs, SOURCE_HASHES, source_unchanged
from whole_chain import Chain


def main():
  clock = Clock()
  with clock_inputs(clock):
    chain = Chain(clock)
    warm = chain.warm()
    start = clock.now+.01
    for index in range(100):
      clock.now = start+index*.01
      chain.step(pcm_kph=90.)
    result = {
      'recorded_utc':datetime.now(UTC).isoformat(), 'initial':chain.init_snapshot,
      'configuration':chain.configuration,'warm':warm,'changed_speed_final':chain.rows[-1],
      'rows':chain.rows,'source_hashes':SOURCE_HASHES,'source_unchanged':source_unchanged(),
      'actual_card_state_update':True,'actual_ci_update':False,'actual_toyota_can_parser':False,
      'actual_ci_apply':True,'actual_toyota_carcontroller':True,'actual_canpacker':True,
      'actual_c_memory_tx':True,'generated_messages':chain.physical.generated_rows,
      'actual_init_executed':chain.physical.actual_init_executed,
      'actual_vehicle_tx':False,'independent_mcu_heartbeat':False,
      'scope_ko':'원형 Card.state_update/Mode0/계획/호스트 권한→실제 CI.apply/ToyotaCC/CANPacker→실제 C 메모리 TX. CAN 수신은 빈 프레임 capnp 패킷, CI.update 반환/feedback은 합성. 실제 차량 준비/송신/수신 파서와 ARS live/SignalMode2 미검증.',
    }
    (WORK/'baseline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result['source_unchanged']
    assert warm['helper_mode']==0 and warm['cs_vCruise']==75. and warm['longActive']
    assert result['changed_speed_final']['cs_vCruise']==90.
    assert all(r['tx_matches_expected'] and r['tx_does_not_create_authority'] for r in chain.physical.generated_rows)
    print(json.dumps({'normal_enable':True,'mode0_warm_kph':warm['cs_vCruise'],
      'pcm_changed_cs_kph':chain.rows[-1]['cs_vCruise'],
      'planner_kph':chain.rows[-1]['planner_cruise_kph'],'source_unchanged':source_unchanged()},ensure_ascii=False))


if __name__=='__main__':
  main()
