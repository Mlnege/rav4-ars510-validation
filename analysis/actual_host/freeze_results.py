"""완료한 익명 관측을 다시 계산하지 않고 검사한 뒤 결과 지문을 고정한다."""
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path


WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
SOURCE = ROOT / 'work/carrotpilot'
LAB = ROOT / 'work/download_e2e'


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
  return json.loads(path.read_text(encoding='utf-8'))


def main():
  results = [read(WORK / 'files' / alias / 'result.json')
             for alias in ('log_a', 'log_b', 'log_c', 'log_d')]
  usable = [r for r in results if r['status'] == 'actual_data_host_observed']
  comparison = read(WORK / 'offline_comparison.json')
  namespace = read(WORK / 'namespace_audit.json')
  factory = read(WORK / 'factory_config_sample.json')
  # 타 팀의 완료 근거를 읽은 출처만 보존하며 직접 실행 건수에 합하지 않는다.
  panda_reference = ROOT / 'work/panda_policy_probe/run01/results.json'
  counts = {}
  for key in ('host_ticks', 'host_initialized', 'host_enabled', 'long_active',
              'c_controls_allowed', 'c_long_allowed', 'c_relay_malfunction',
              'native_model_updates', 'models_with_radar_lead', 'mpc_lead_source', 'solver_nonzero'):
    counts[key] = sum(r['counts'].get(key, 0) for r in usable)
  for key in ('can_count', 'accel_can_count', 'actual_c_accept_count', 'actual_c_deny_count',
              'actual_c_mismatch_count', 'can_nonzero_accel_count', 'timeline_remaining',
              'sensor_preservation_mismatches'):
    counts[key] = sum(r[key] for r in usable)
  for key in ('points', 'records', 'crc_failures', 'radar_leads', 'model_updates', 'radarState_errors'):
    counts[key] = sum(r['radar'][key] for r in usable)
  comparisons = []
  original_by_alias = {r['alias']: r for r in comparison['files']}
  for r in usable:
    old = original_by_alias[r['alias']]
    comparisons.append({
      'alias': r['alias'],
      'point_count_equal': r['radar']['points'] == old['points'],
      'record_count_equal': r['radar']['records'] == old['diagnostics']['records'],
      'dpath_model_count_equal': r['radar']['model_updates'] == old['pipeline_model_updates'],
      'dpath_lead_count_equal': r['radar']['radar_leads'] == old['radar_lead_selections'],
      'host_model_conflation_count': r['radar']['model_updates'] - r['counts']['native_model_updates'],
    })
  recorded_sources = []
  for r in usable:
    for relative, expected in r['source_hashes'].items():
      recorded_sources.append({'alias': r['alias'], 'path': relative,
                               'sha256_at_execution': expected,
                               'current_sha256': sha(SOURCE / relative),
                               'same_now': sha(SOURCE / relative) == expected})
  historic = read(ROOT / 'work/validation_run/release_stopping_reproduction.json')
  native_folder = LAB / 'work/native_sim/build_unique/c_generated_code'
  native = [{'name': name, 'historical_sha256': expected,
             'current_sha256': sha(native_folder / name),
             'same_as_previous_frozen_build': sha(native_folder / name) == expected}
            for name, expected in historic['native_solver_before'].items()]
  safety_path = LAB / 'work/safety_validation/libsafety_download_native.so'
  safety = {'historical_sha256': historic['safety_library_sha256'],
            'current_sha256': sha(safety_path),
            'same_as_previous_frozen_build': sha(safety_path) == historic['safety_library_sha256']}
  release = read(ROOT / 'work/release_repo/validation_manifest.json')
  release_checks = []
  for row in release['patched_source_files']:
    actual = hashlib.sha256((SOURCE / row['path']).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    release_checks.append({'path': row['path'], 'expected_sha256_lf': row['sha256_lf'],
                           'current_sha256_lf': actual, 'same_now': actual == row['sha256_lf']})
  checks = {
    'three_actual_data_runs_complete': len(usable) == 3 and all(not r['failures'] for r in usable),
    'cp_missing_log_remains_unexecuted': results[2]['status'] == 'insufficient_recorded_carParams'
                                       and results[2]['whole_host_executed'] is False,
    'counts_match_369_2433_175': (counts['points'], counts['records'], counts['radar_leads']) == (369, 2433, 175),
    'offline_comparison_counts_equal': all(all(row[k] for k in ('point_count_equal', 'record_count_equal',
                                                              'dpath_model_count_equal', 'dpath_lead_count_equal'))
                                           for row in comparisons),
    'all_crc_valid': counts['crc_failures'] == 0,
    'all_timeline_delivered': counts['timeline_remaining'] == 0,
    'recorded_checked_sensor_fields_preserved': counts['sensor_preservation_mismatches'] == 0,
    'all_source_initial_disabled_checks_pass': all(r['checks']['original_initial_disabled'] for r in usable),
    'recorded_off_conditions_remain_off': all(counts[k] == 0 for k in ('host_enabled', 'long_active',
                                        'c_controls_allowed', 'c_long_allowed', 'can_nonzero_accel_count')),
    'actual_c_expectations_match': counts['actual_c_mismatch_count'] == 0,
    'actual_c_all_generated_denied_in_this_configuration': counts['actual_c_accept_count'] == 0
                                        and counts['actual_c_deny_count'] == counts['can_count'],
    'native_solver_status_zero': counts['solver_nonzero'] == 0,
    'no_forced_permission_or_physical_init': all(r['checks'][k] for r in usable for k in
                        ('synthetic_permission_update_not_called', 'no_controls_true_shortcut', 'no_actual_init')),
    'recorded_source_checks_and_current_hashes_match': all(r['checks']['no_source_changes'] for r in usable)
                                        and all(r['same_now'] for r in recorded_sources),
    'replay_version_is_current_error_propagation_version': comparison['replay_source_sha_before'] ==
                        comparison['replay_source_sha_after'] ==
                        'c5d91ef5c12dd3ca537d0de65e1b338fe25fcac31478e7059e299fb41cb9f1a6',
    'namespace_method_globals_resolved': namespace['all_tested_method_globals_resolved'],
    'namespace_source_constants_equal': namespace['all_source_constants_equal'],
    'native_and_safety_build_unchanged_from_previous_evidence': safety['same_as_previous_frozen_build']
                                        and all(r['same_as_previous_frozen_build'] for r in native),
    'current_release_patched_files_equal': all(r['same_now'] for r in release_checks),
    'separate_factory_card_sample_matches_c_arguments': factory['cp']['safetyConfigs'][0]['safetyModel_raw'] ==
                  factory['c_set_safety_hooks_arguments']['safetyModel'] and
                  factory['cp']['safetyConfigs'][0]['safetyParam'] == factory['c_set_safety_hooks_arguments']['safetyParam'] and
                  factory['cp']['alternativeExperience'] == factory['c_set_alternative_experience_argument'],
  }
  public = {
    'generated_utc': datetime.now(UTC).isoformat(),
    'status': 'actual_radar_data_to_disabled_host_memory_can_observed',
    'counts': counts,
    'per_file': [{
      'alias': r['alias'], 'status': r['status'],
      'points': r['radar']['points'], 'records': r['radar']['records'],
      'dpath_leads': r['radar'].get('radar_leads', 0),
      'radarState_error_models': r['radar'].get('radarState_errors', 0),
      'host_counts': r.get('counts', {}),
      'generated_can': r.get('can_count', 0), 'c_denied': r.get('actual_c_deny_count', 0),
      'original_checks_passed': len(r.get('checks', {})) - len(r.get('failures', [])),
    } for r in results],
    'offline_comparison': comparisons,
    'checks': checks,
    'failures': [k for k, v in checks.items() if not v],
    'source_at_execution_checks': recorded_sources,
    'current_release_patched_file_checks': release_checks,
    'native_build_hashes': native, 'safety_build_hash': safety,
    'separate_factory_card_config_sample': factory,
    'separately_executed_panda_reference': {
      'path': panda_reference.relative_to(ROOT).as_posix(), 'sha256': sha(panda_reference),
      'provenance_ko': '주 에이전트가 직접 실행한 원본 설정 집계를 읽은 근거. 이 하네스의 직접 실행으로 세지 않는다.'},
    'scope_ko': '실제 CAN 객체의 자료 연결 관측. 원본 OFF 조건을 보존했다. 활성 제어·실물 릴레이·실차 안전·ECU 반응은 증명하지 않는다.',
    'corrections_to_preserved_result_metadata_ko': [
      '기존 결과의 collector_clock_assumption 중 수신시각 없음은 부정확한 문구다. 원본 radarInput 메타는 존재하지만 이번 direct-adapter 경로는 이를 소비하지 않는다.',
      '기존 결과의 actual_gvc_assumed=0.0은 이전 하네스의 남은 설명 필드다. 실제 GVC/PCM/HUD 피드백은 원본 CAN의 기존 DBC 파서로 해독했고 세 실행의 미수신 집계는 모두 비어 있다.',
      'c_relay_malfunction은 선언 factoryCP/현재 C에 실제 기록 CAN을 넣어 관측한 메모리 값이다. 실물 Panda 릴레이 고장 확정이 아니다.',
      'sensor_fields_preserved는 명시한 15개 필드의 직접 대조다. Card가 갱신한 radarInput/VCruise/UI 필드는 원본 동일성 주장에 포함하지 않는다.',
    ],
    'unexecuted_scope_ko': [
      '생산 radarcan/RadarCanBatches의 원본 CS 배치 메타 및 100ms 수신나이 경계',
      '전체 Toyota CI.update, 실제 CAN 수집기와 소켓, 실제 CI.init·UDS',
      '실물 Panda 설정 일치·MCU heartbeat·릴레이 상태·차량 ECU 응답',
      'ARS live 등록, PCS/AEB 보존, 회생제동, 신호 Mode2 통합과 실물 카메라 인식',
    ],
  }
  (WORK / 'frozen_results.json').write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding='utf-8')
  artifacts = sorted(p for p in WORK.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                     and p.name != 'evidence_manifest.json')
  manifest = {'generated_utc': datetime.now(UTC).isoformat(),
              'artifact_hashes': {p.relative_to(WORK).as_posix(): sha(p) for p in artifacts},
              'publish_scope_ko': '공개 근거는 익명 JSON과 한국어 보고서 및 도구다. 실행 stdout 로그는 기본 공개 대상에 넣지 않는다. 원본 입력/트랙 CSV는 포함하지 않는다.'}
  (WORK / 'evidence_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps({'checks': len(checks), 'failures': public['failures'], 'counts': counts,
                    'artifact_count': len(artifacts)}, ensure_ascii=False))
  raise SystemExit(1 if public['failures'] else 0)


if __name__ == '__main__':
  main()
