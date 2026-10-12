"""새 정책 없이 원형 호스트 권한 체인에 한 종류의 지연/운전자 입력을 준다."""
import argparse
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path
import time

from whole_io import WORK, SOURCE, Clock, clock_inputs, SOURCE_HASHES, source_unchanged
from whole_chain import Chain


def main():
  parser=argparse.ArgumentParser()
  parser.add_argument('--kind',required=True,choices=['no_drop','delayed_message','freeze_model','freeze_plan',
                       'whole_stall','actual_sleep','cancel','button_only_cancel','gas','brake','model_drop'])
  parser.add_argument('--profile',choices=['default','user_requested'],default='default')
  parser.add_argument('--delay',type=float,default=.323)
  parser.add_argument('--output',type=Path,required=True)
  args=parser.parse_args()
  args.output.mkdir(parents=True,exist_ok=True)
  clock=Clock()
  with clock_inputs(clock):
    chain=Chain(clock,profile=args.profile)
    chain.warm()
    warm_row=chain.rows[-1].copy()
    start=clock.now+.01
    resume_time=None
    actual_wall=None
    cpu_gap=None
    if args.kind in ('whole_stall','actual_sleep'):
      if args.kind=='actual_sleep':
        wall,cpu=time.perf_counter(),time.thread_time()
        time.sleep(args.delay)
        actual_wall=time.perf_counter()-wall
        cpu_gap=time.thread_time()-cpu
        start+=actual_wall
      else:
        start+=args.delay
      resume_time=start
    fault_start_index=len(chain.rows)
    duration=max(.8,args.delay+.8) if args.kind in ('freeze_model','freeze_plan') else .8
    duration=max(duration,4.) if args.kind in ('whole_stall','actual_sleep','model_drop') else duration
    for index in range(round(duration/.01)):
      clock.now=start+index*.01
      elapsed=index*.01
      kwargs={}
      if args.kind in ('no_drop','delayed_message'):
        kwargs.update(model_age=args.delay,delayed_header=args.kind=='delayed_message')
      if args.kind=='freeze_model':
        kwargs['freeze_model']=elapsed<args.delay
      if args.kind=='freeze_plan':
        kwargs['freeze_plan']=elapsed<args.delay
      if args.kind=='cancel':
        kwargs.update(engaged=False,cancel=elapsed<.05)
      if args.kind=='button_only_cancel':
        kwargs.update(cancel=elapsed<.05)
      if args.kind=='gas':
        kwargs['gas']=elapsed<.2
      if args.kind=='brake':
        kwargs['brake']=elapsed<.2
      if args.kind=='model_drop':
        kwargs['model_drop']=30. if elapsed<args.delay else 0.
      chain.step(**kwargs)
    rows=chain.rows[fault_start_index:]
    result={'kind':args.kind,'delay_s':args.delay,'profile':args.profile,'configuration':chain.configuration,
      'alpha_get_params_argument':True,'physical_configuration_verified':False,
      'live_ars_and_signal_integration_included':False,
      'initial':chain.init_snapshot,'normal_enable_baseline':warm_row,
      'fault_rows':rows,'fault_first':rows[0],'fault_second':rows[1],'fault_last':rows[-1],
      'first_long_inactive_time':next((r['time'] for r in rows if not r['longActive']),None),
      'first_soft_disable_time':next((r['time'] for r in rows if r['state']=='softDisabling'),None),
      'events':sorted({e for r in rows for e in r['events']}),'source_hashes':SOURCE_HASHES,
      'source_unchanged':source_unchanged(),'actual_wall_gap_s':actual_wall,'thread_cpu_gap_s':cpu_gap,
      'host_loop_resume_time':resume_time,'init_io_sink_calls':chain.physical.init_io_sink_calls,
      'actual_init_executed':False,'actual_vehicle_can_sent':False,
      'whole_host_stall_mcu_rx_during_gap_executed':False,'independent_mcu_heartbeat_verified':False,
      'post_resume_c_inputs':'재개 후 명시적인 정상/운전자 PCM RX. 정지 동안 MCU/차량의 독립 물리는 미검증.',
      'shortcut_controls_true_calls':chain.permission.shortcut_controls_true_calls,
      'software_scope':'원형 호스트 판단 체인, 상태·판정·상위권한 고정 대체 없음. 입력 건강/송신/수집은 명시한 IO fixture.',
      'actor_order':'외부입력→card 상태발행/이전CC 적용→model20Hz계획→selfdrived→controls100Hz발행. 기존 큐CC와 새CC 상태를 각각 기록.',
      'recorded_utc':datetime.now(UTC).isoformat()}
    (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('kind','delay_s','first_long_inactive_time',
                    'first_soft_disable_time','events','source_unchanged')},ensure_ascii=False))


if __name__=='__main__':
  main()
