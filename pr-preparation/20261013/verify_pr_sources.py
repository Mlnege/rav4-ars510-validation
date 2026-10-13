"""PR 후보 checkout의 고정 commit·소스 지문을 확인한다. 차량에는 접근하지 않는다."""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def git(root, *args):
  return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def verify(root, spec):
  root = root.resolve()
  if git(root, 'rev-parse', 'HEAD') != spec['commit']:
    raise RuntimeError('요청한 고정 commit과 checkout이 다릅니다')
  subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', spec['base'], 'HEAD'], check=True)
  checked = 0
  for relative, expected in spec['files_sha256_lf'].items():
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
      raise RuntimeError('검사 경로가 checkout 밖입니다')
    content = path.read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(content).hexdigest() != expected:
      raise RuntimeError(f'소스 지문이 다릅니다: {relative}')
    if path.suffix == '.py':
      ast.parse(content, filename=relative)
    checked += 1
  if git(root, 'status', '--porcelain', '--untracked-files=all'):
    raise RuntimeError('checkout에 추적 중인 변경 또는 추가 파일이 있습니다')
  return {'commit': spec['commit'], 'checked_files': checked, 'source_verified': True}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('carrot', type=Path)
  parser.add_argument('ars', type=Path)
  parser.add_argument('manifest', type=Path)
  args = parser.parse_args()
  if not (sys.version_info >= (3, 12, 3) and sys.version_info < (3, 13)):
    raise RuntimeError('최신 Carrot의 Python 요구 범위는 3.12.3 이상, 3.13 미만입니다')
  manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
  result = {'carrot': verify(args.carrot, manifest['carrot']),
            'ars': verify(args.ars, manifest['ars']),
            'vehicle_compatibility_verified': False, 'vehicle_deployment_allowed': False,
            'full_native_build_verified': False,
            '안내': '소스와 구문을 확인했습니다. 장치 빌드·ECU·PCS·회생·실차 호환성은 별도 검증 대상입니다.'}
  print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
  main()
