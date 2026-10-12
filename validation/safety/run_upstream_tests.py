"""별도 출력 위치의 실제 C libsafety로 저장소의 원형 pytest를 실행한다."""

import argparse
from pathlib import Path
import runpy
import shutil
import sys


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('library', type=Path)
  parser.add_argument('tests', nargs='+')
  parser.add_argument('--select')
  parser.add_argument('--junit', type=Path)
  parser.add_argument('--quiet-c', action='store_true')
  parser.add_argument('--repo', type=Path)
  args = parser.parse_args()
  root = (args.repo or (Path(__file__).resolve().parents[1] / 'carrotpilot')).resolve()
  sys.path[:0] = [str(root), str(root / 'opendbc_repo')]
  from tools.ars510_offline.bootstrap import prepare
  prepare()
  # 원본 DBC 생성기를 복사한 작업 공간에서 실행한다. 차량 소스는 변경하지 않는다.
  import opendbc
  from opendbc.dbc.generator import generator
  work = Path(__file__).resolve().parent
  dbc_path = work / 'dbcs'
  source_path = work / 'dbc_generator'
  if not source_path.exists():
    shutil.copytree(generator.generator_path, source_path)
  dbc_path.mkdir(exist_ok=True)
  if not (dbc_path / 'toyota_nodsu_pt_generated.dbc').exists():
    # 환경설정을 건드리지 않고 같은 원형 generator 스크립트·조립 함수를 실행한다.
    for script in sorted(source_path.glob('*/*.py')):
      runpy.run_path(str(script), run_name='__main__')
    for source in sorted(source_path.glob('*/*.dbc')):
      if not source.name.startswith('_'):
        generator.create_dbc(str(source.parent), source.name, str(dbc_path))
  for source in Path(opendbc.DBC_PATH).glob('*.dbc'):
    destination = dbc_path / source.name
    if not destination.exists():
      shutil.copyfile(source, destination)
  opendbc.DBC_PATH = str(dbc_path)
  import opendbc.can.dbc
  opendbc.can.dbc.DBC_PATH = str(dbc_path)
  import cffi
  original = cffi.FFI.dlopen
  def load_fixture(ffi, name, *extra, **kwargs):
    # 안전 알고리즘을 대체하지 않고 컴파일 산출물 위치만 지정한다.
    if str(name).endswith('/tests/libsafety/libsafety.so'):
      name = str(args.library.resolve())
    return original(ffi, name, *extra, **kwargs)
  cffi.FFI.dlopen = load_fixture
  try:
    from opendbc.safety.tests.libsafety import libsafety_py
    assert libsafety_py.libsafety is not None
  finally:
    cffi.FFI.dlopen = original
  import pytest
  arguments = ['--confcutdir=' + str(root / 'opendbc_repo/opendbc/safety/tests'),
               '-c', str(root / 'tools/ars510_offline/pytest.ini'), '-q', '--tb=short', *args.tests]
  if args.select:
    arguments.extend(['-k', args.select])
  if args.junit:
    arguments.append('--junitxml=' + str(args.junit.resolve()))
  if args.quiet_c:
    from verify_compiled import quiet_c_stdout
    arguments.append('--capture=sys')
    with quiet_c_stdout():
      result = pytest.main(arguments)
    print('pytest_exit_code=' + str(int(result)))
  else:
    result = pytest.main(arguments)
  raise SystemExit(result)


if __name__ == '__main__':
  main()
