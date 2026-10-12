"""완료된 61분 실행의 실제 소스/수치 라이브러리 끝점 지문을 별도로 비교한다."""
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
folder = WORK/'signal_validation/realtime_ox_final_61min'
launch = json.loads((folder/'launch_snapshot.json').read_text(encoding='utf-8'))
summary = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
root = WORK/'carrotpilot'
source = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in launch['source_hashes']}
native_root = WORK/'native_sim'/launch['native_snapshot']
native = {name: hashlib.sha256((native_root/name).read_bytes()).hexdigest() for name in launch['native_hashes']}
result = {'source_unchanged_direct': source == launch['source_hashes'] == summary['source_hashes'],
          'native_unchanged_direct': native == launch['native_hashes'],
          'source_count': len(source), 'native_count': len(native), 'selected_scope': 'signal_to_longcontrol_not_carcontroller',
          'source_hashes': source, 'native_hashes': native}
(folder/'endpoint_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if not key.endswith('_hashes')}))
raise SystemExit(int(not result['source_unchanged_direct'] or not result['native_unchanged_direct']))
