"""읽기 전용 진단 결과와 초기 실패 근거를 지문으로 고정한다."""
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path


WORK = Path(__file__).resolve().parent


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
  result = json.loads((WORK / 'results.json').read_text())
  initial = json.loads((WORK / 'initial_all_items_as_rx_failure.json').read_text())
  initial_code = WORK / 'initial_all_items_as_rx_run.py'
  observed = [r for r in result['results'] if r['status'] == 'recorded_policy_c_rx_observed']
  phase0 = [r for r in observed if r['phase_us'] == 0]
  checks = {
    'six_actual_runs_completed': len(observed) == 6,
    'sixty_direct_checks_passed': result['direct_check_count'] == 60 and not result['direct_failed_checks'],
    'initial_six_failures_preserved': len(initial['direct_failed_checks']) == 6,
    'initial_code_fingerprint_preserved': sha(initial_code) == initial['script_sha256'],
    'source_and_shared_library_unchanged': result['source_unchanged'] and result['library_unchanged'],
    'all_unknown_source_types_absent': all(r['counts'].get('unknown_source_items', 0) == 0 for r in observed),
    'no_direct_permission_or_relay_setter': all(r['controls_allowed_setter_calls'] == r['relay_setter_calls'] ==
                      r['init_tests_calls'] == r['counter_arbitrary_reset_calls'] == 0 for r in observed),
    'no_tx_hooks_or_physical_tx': all(r['tx_hook_calls'] == 0 and not r['physical_tx'] for r in observed),
  }
  summary = {'generated_utc': datetime.now(UTC).isoformat(), 'checks': checks,
             'failed': [name for name, passed in checks.items() if not passed],
             'counts_single_phase': {name: sum(r['counts'].get(name, 0) for r in phase0) for name in
                       ('recorded_can_items_consumed', 'physical_rx_frames', 'returned_notifications',
                        'rejected_notifications', 'unknown_source_items')},
             'cs_sample_counts_single_phase': {name: sum(r['carState_c_samples'].get(name, 0) for r in phase0)
                       for name in ('samples', 'c_controls_true', 'c_long_true', 'c_relay_true', 'c_rx_invalid_true')},
             'panda_sample_counts_single_phase': {name: sum(r['panda_c_samples'].get(name, 0) for r in phase0)
                       for name in ('samples', 'controls_differs_from_recorded', 'rx_invalid_differs_from_recorded')},
             'scope_ko': '기록 모드의 현재 C RX·명시적 clock 가정 관측. 이전 whole-host/생성 CAN의 새 허용 결과 또는 실차 안전 통과가 아님.'}
  (WORK / 'frozen_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
  paths = sorted(p for p in WORK.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                 and p.name != 'evidence_manifest.json')
  manifest = {'generated_utc': datetime.now(UTC).isoformat(),
              'artifact_hashes': {p.relative_to(WORK).as_posix(): sha(p) for p in paths}}
  (WORK / 'evidence_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps(summary, ensure_ascii=False))
  raise SystemExit(1 if summary['failed'] else 0)


if __name__ == '__main__':
  main()
