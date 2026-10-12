"""실제 신호 수신기가 건강한 원형 호스트 입력에서 redhold를 만드는지 먼저 확인한다."""
from datetime import datetime, UTC
import hashlib
import json
import math

from whole_io import WORK, SOURCE, Clock, clock_inputs, SOURCE_HASHES, source_unchanged
from whole_chain import Chain


def json_clean(value):
  # 진단의 무한대 초기 타이머만 문자열로 보존한다. 판단 객체/타이머는 바꾸지 않는다.
  if isinstance(value,float) and not math.isfinite(value):
    return 'negative_infinity' if value<0 else 'positive_infinity' if value>0 else 'nan'
  if isinstance(value,dict):return {key:json_clean(v) for key,v in value.items()}
  if isinstance(value,(list,tuple)):return [json_clean(v) for v in value]
  return value


def main():
  clock=Clock()
  with clock_inputs(clock):
    chain=Chain(clock)
    for index in range(700):
      clock.now=100.+index*.01
      chain.step(engaged=index>=200,available=index>=150,speed=0.)
    enabled=[r for r in chain.rows if r['enabled'] and r['longActive']]
    held=[r for r in chain.rows if r['signal_start_hold']]
    ctx=[r for r in chain.signal_trace.calls if r['runtime']=='start' and r['context']['valid'] and r['context']['enabled']]
    prepare=[r for r in chain.signal_trace.calls if r['runtime']=='prepare' and r['context']['valid']]
    generated=chain.physical.generated_rows
    held_can=[r for r in generated if r['address']==0x343 and held and r['time_ns']>=round(held[0]['time']*1e9)]
    checks={'initial_disabled':not any(chain.init_snapshot.values()),
      'original_initialized_and_enabled':chain.sd.initialized and bool(enabled),
      'normal_signal_mode2':chain.configuration['SignalAssistMode']=='2',
      'retired_assist_not_injected':chain.carrot.signal_assist is None,
      'actual_start_runtime_valid_enabled':bool(ctx),
      'actual_prepare_runtime_geometry_context_valid':bool(prepare),
      'redhold_acquired':bool(held),
      'redhold_maintained':bool(held) and all(r['signal_start_hold'] for r in chain.rows if r['time']>=held[0]['time']),
      'held_plan_nonpositive':bool(held) and all(r['plan_aTarget']<=0 and r['plan_should_stop'] for r in held),
      'held_actual_generated_can_nonpositive':bool(held_can) and all(r['raw_accel_signed']<=0 for r in held_can),
      'actual_c_tx_matches_expected':all(r['tx_matches_expected'] for r in generated),
      'actual_c_tx_no_authority_mutation':all(r['tx_does_not_create_authority'] for r in generated),
      'known_ox_profile_supplied':all(r['profile'] is not None and r['provenance_supplied'] for r in chain.observations.published),
      'model_camera_eof_nonzero':all(r['input_model_eof']>0 and r['input_model_frame_id']>0 for r in chain.signal_trace.calls),
      'camera_history_matches_after_enable':all(r['camera_history_exact_match'] for r in chain.observations.published if r['delivery_time']>=102.),
      'no_actual_init_tx':not chain.physical.actual_init_executed,'source_unchanged':source_unchanged()}
    result={'recorded_utc':datetime.now(UTC).isoformat(),'checks':checks,
      'failures':[name for name,passed in checks.items() if not passed],
      'initial':chain.init_snapshot,'configuration':chain.configuration,
      'cp':{'fingerprint':str(chain.cp.carFingerprint),'flags':int(chain.cp.flags),
        'pcmCruise':bool(chain.cp.pcmCruise),'directLong':bool(chain.cp.openpilotLongitudinalControl),
        'minEnableSpeed':float(chain.cp.minEnableSpeed),'radarUnavailable':bool(chain.cp.radarUnavailable),
        'alternativeExperience':int(chain.cp.alternativeExperience)},
      'first_enable':enabled[0] if enabled else None,'first_hold':held[0] if held else None,
      'first_actual_context':ctx[0] if ctx else None,'first_prepare_valid_context':prepare[0] if prepare else None,
      'last':chain.rows[-1],'rows':chain.rows,'runtime_calls':chain.signal_trace.calls,
      'publications':chain.observations.published,'generated_can':generated,
      'camera_history':chain.observations.road_history,
      'camera_lineage':{'total':len(chain.observations.published),
        'exact_matches':sum(r['camera_history_exact_match'] for r in chain.observations.published),
        'startup_before_history':sum(r['camera_history_missing_kind']=='before_started_history' for r in chain.observations.published),
        'after_enable_mismatches':sum(not r['camera_history_exact_match'] for r in chain.observations.published if r['delivery_time']>=102.),
        'scope_ko':'합성 메모리에서 발행한 이전 roadCameraState frameId/EOF와 정확히 대조했다. 실제 영상 픽셀/센서 취득은 미검증.'},
      'source_hashes':SOURCE_HASHES,'source_unchanged':source_unchanged(),
      'actual_ci_update':False,'actual_ci_init':False,'actual_vehicle_tx':False,
      'actual_signal_image_detection':False,'actual_mcu_heartbeat':False,
      'scope_ko':'초기비활성→원형건강SubMaster/PCM enable→원형mode2 Start/Prepare runtime→redhold→원형ToyotaCAN/C TX 메모리. 관측/캘리브레이션/이미지규격/standstill/GVC/ECU피드백은 합성이며 실차/인식정확도/PCS/회생/ARS live 미검증.'}
    (WORK/'baseline.json').write_text(json.dumps(json_clean(result),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'failures':result['failures'],'first_enable':enabled[0]['time'] if enabled else None,
      'first_hold':held[0]['time'] if held else None,'start_true_calls':len(ctx),'prepare_valid_calls':len(prepare),
      'generated_can':len(generated),'events':sorted({e for r in chain.rows for e in r['events']})},ensure_ascii=False))
    raise SystemExit(1 if result['failures'] else 0)


if __name__=='__main__':main()
