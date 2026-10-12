"""같은 원형 호스트에서 moving Prepare 경로와 오래된 model EOF를 별도로 관찰한다."""
import argparse
from datetime import datetime, UTC
import json

from whole_io import WORK,Clock,clock_inputs,SOURCE_HASHES,source_unchanged
from whole_chain import Chain
from run_baseline import json_clean


def main():
  parser=argparse.ArgumentParser()
  parser.add_argument('--model-age',type=float,choices=[0.,2.],default=0.)
  args=parser.parse_args()
  clock=Clock()
  with clock_inputs(clock):
    chain=Chain(clock,initial_speed=15.)
    for index in range(750):
      clock.now=100.+index*.01
      chain.step(engaged=index>=200,available=index>=150,speed=15.,model_age=args.model_age)
    active=[r for r in chain.rows if r['signal_prepare_active']]
    eligible=[r for r in chain.signal_trace.calls if r['runtime']=='prepare' and
      r['context']['valid'] and r['context']['enabled']]
    checks={'initial_disabled':not any(chain.init_snapshot.values()),'original_enable':chain.sd.enabled,
      'actual_prepare_context_healthy':bool(eligible),
      'retired_assist_absent':chain.carrot.signal_assist is None,
      'source_unchanged':source_unchanged(),'actual_tx_expected':all(r['tx_matches_expected'] for r in chain.physical.generated_rows),
      'no_tx_authority_change':all(r['tx_does_not_create_authority'] for r in chain.physical.generated_rows),
      'no_actual_init':not chain.physical.actual_init_executed,
      'camera_history_match_after_enable':all(r['camera_history_exact_match'] for r in chain.observations.published if r['delivery_time']>=102.)}
    # 실제 geometry가 부적격이면 활성화를 강제하지 않고 이유를 보존한다.
    result={'recorded_utc':datetime.now(UTC).isoformat(),'model_age_s':args.model_age,'checks':checks,
      'failures':[name for name,passed in checks.items() if not passed],
      'initial':chain.init_snapshot,'configuration':chain.configuration,
      'prepare_active_ticks':len(active),'prepare_healthy_reads':len(eligible),
      'prepare_first_active':active[0] if active else None,
      'prepare_reasons':sorted({r['signal_prepare_reason'] for r in chain.rows}),
      'rows':chain.rows,'runtime_calls':chain.signal_trace.calls,'publications':chain.observations.published,
      'generated_can':chain.physical.generated_rows,'source_hashes':SOURCE_HASHES,
      'min_plan_target':min(r['plan_aTarget'] for r in chain.rows),
      'min_control_accel':min(r['accel'] for r in chain.rows),
      'scope_ko':'고정ego15/GVC0/aEgo0의추가합성moving입력. 원형Prepare 실제context/geometry/active 여부를관찰하며강제활성화하지않음. oldEOF2초에는헤더/수신은신선함을분리. 실차감속/인식/카메라데이터획득/PCS/회생/ARS 미검증.'}
    folder=WORK/'moving_cases'/f'model_age_{int(args.model_age*1000)}ms'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'result.json').write_text(json.dumps(json_clean(result),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('model_age_s','failures','prepare_active_ticks','prepare_reasons','min_plan_target','min_control_accel')},ensure_ascii=False))
    raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
