"""진행 중 검사에 사용한 소스·고정 수치 모듈의 읽기 전용 지문을 남긴다."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
REPO = WORK / 'carrotpilot'
FILES = (
  'openpilot/selfdrive/carrot/carrot_functions.py', 'openpilot/selfdrive/carrot/signal_start_guard.py',
  'openpilot/selfdrive/carrot/signal_stop_prepare.py', 'openpilot/selfdrive/controls/lib/longitudinal_planner.py',
  'openpilot/selfdrive/carrot/signal_stop_prepare_runtime.py', 'openpilot/selfdrive/modeld/signal_tracking_shadow.py',
  'openpilot/selfdrive/controls/lib/longcontrol.py',
  'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py',
  'tools/ars510_validation/signal/core.py', 'tools/ars510_validation/signal/native_signal.py',
  'tools/ars510_validation/signal/realtime_signal.py',
)
target = WORK / 'signal_validation' / 'realtime_ox_final_61min'
snapshot = WORK / 'native_sim' / 'build_snapshot_b0a5c630260ad76b'
progress = json.loads((target / 'progress.json').read_text(encoding='utf-8'))
result = {'started_utc': progress['started_utc'], 'recorded_utc': datetime.now(UTC).isoformat(),
          'camera_profile': 'ox03c10', 'native_snapshot': snapshot.name,
          'source_hashes': {name: hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in FILES},
          'native_hashes': {str(file.relative_to(snapshot)).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in snapshot.rglob('*.so')}}
(target / 'launch_snapshot.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'source_count': len(result['source_hashes']), 'native_count': len(result['native_hashes']),
                  'started_utc': result['started_utc'], 'recorded_utc': result['recorded_utc']}))
