#!/usr/bin/env python3
"""개발용 Carrot 복제본에 확인된 실행 패치만 선택 검사·적용한다.

기본은 읽기 전용이다. 운영 디렉터리 적용, 강제/3-way 적용, fetch/rebase,
차량 실행 또는 설정 변경 기능이 없다. JSON 보고서는 명시한 repo 밖 새 경로에만 쓴다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PARTS = ('radar', 'pcm', 'longitudinal')
ARTIFACTS = frozenset(f'patches/{part}.patch' for part in PARTS)
TOYOTA = 'opendbc_repo/opendbc/car/toyota/'
RADARCAN = 'openpilot/selfdrive/carrot/radar/radarcan.py'
VENDOR = tuple(TOYOTA + 'ars510/' + name for name in (
  '__init__.py', 'constants.py', 'interface.py', 'objects.py', 'record.py',
  'shell85.py', 'support.py', 'tracks.py', 'transport.py', 'LICENSE',
))
ALLOWED_FILES = {
  'radar': frozenset((TOYOTA + 'interface.py', TOYOTA + 'radar_interface.py', TOYOTA + 'ars510_carrot.py', RADARCAN, *VENDOR)),
  'pcm': frozenset(('openpilot/selfdrive/car/cruise.py', 'openpilot/selfdrive/car/toyota_pcm_speed.py')),
  'longitudinal': frozenset((TOYOTA + 'carcontroller.py',
                           'openpilot/selfdrive/controls/lib/longitudinal_planner.py',
                           'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py')),
}
RUNTIME_FILES = frozenset().union(*ALLOWED_FILES.values())
EXISTING_FILES = frozenset((TOYOTA + 'interface.py', TOYOTA + 'radar_interface.py', TOYOTA + 'carcontroller.py',
                            'openpilot/selfdrive/car/cruise.py', 'openpilot/selfdrive/controls/lib/longitudinal_planner.py',
                            'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py', RADARCAN))
SCHEMAS = ('opendbc_repo/opendbc/car/car.capnp', 'openpilot/cereal/log.capnp')
REQUIRED_GUARDS = {
  'radar': frozenset(('opendbc_repo/opendbc/car/interfaces.py', 'opendbc_repo/opendbc/car/radar_tracks.py',
                     'opendbc_repo/opendbc/can/parser.py', TOYOTA + 'values.py', TOYOTA + 'toyotacan.py',
                     TOYOTA + 'carstate.py', 'openpilot/selfdrive/carrot/radar/can_batch.py',
                     'openpilot/selfdrive/carrot/radar/radard_dpath.py', *SCHEMAS)),
  'pcm': frozenset((*SCHEMAS, 'openpilot/selfdrive/carrot/carrot_functions.py',
                   'openpilot/selfdrive/carrot/carrot_man_input.py')),
  'longitudinal': frozenset(('opendbc_repo/opendbc/car/interfaces.py', TOYOTA + 'values.py',
                            TOYOTA + 'toyotacan.py', *SCHEMAS, 'openpilot/selfdrive/controls/lib/longcontrol.py',
                            'openpilot/selfdrive/carrot/carrot_functions.py',
                            'openpilot/selfdrive/carrot/signal_start_guard.py',
                            'openpilot/selfdrive/carrot/signal_stop_prepare.py')),
}
ALLOWED_GUARDS = frozenset().union(*REQUIRED_GUARDS.values())
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
DIFF = re.compile(r'diff --git a/([^\s]+) b/([^\s]+)\Z')


class OverlayError(Exception):
  """조건을 확인하지 못해 변경을 거절한다."""


@dataclass(frozen=True)
class Plan:
  repo: Path
  assets: Path
  parts: tuple[str, ...]
  baseline: str
  head: str
  files: tuple[str, ...]
  preimages: dict[str, str | None]
  postimages: dict[str, str]
  guards: dict[str, str]
  patch: bytes
  manifest_hash: str
  artifact_hashes: dict[str, str]
  report: Path | None


def sha256(raw: bytes) -> str:
  return hashlib.sha256(raw).hexdigest()


def hash_lf(path: Path) -> str:
  return sha256(path.read_bytes().replace(b'\r\n', b'\n'))


def safe_relative(value: object) -> str:
  if not isinstance(value, str) or not value or '\\' in value or ':' in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
    raise OverlayError('manifest 또는 patch의 상대 경로 형식을 확인할 수 없습니다')
  path = PurePosixPath(value)
  if path.is_absolute() or str(path) != value or any(part in ('.', '..', '.git') for part in path.parts):
    raise OverlayError('경로 이탈 또는 Git 내부 경로를 허용하지 않습니다')
  return value


def symbolic(path: Path) -> bool:
  return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def safe_child(root: Path, name: str) -> Path:
  relative = safe_relative(name)
  target = root
  for part in PurePosixPath(relative).parts:
    target = target / part
    if symbolic(target):
      raise OverlayError(f'심볼릭 경로 또는 junction은 허용하지 않습니다: {relative}')
  if not target.resolve().is_relative_to(root):
    raise OverlayError(f'경로가 지정 디렉터리 밖으로 벗어납니다: {relative}')
  return target


def operational(path: Path, *, report: bool = False) -> bool:
  value = path.as_posix().lower()
  value = re.sub(r'^[a-z]:', '', value)
  # Linux 운영 경로와 Windows의 같은 루트 이름을 모두 거절한다.
  root = '/data' if report else '/data/openpilot'
  return value == root or value.startswith(root + '/')


def git(repo: Path, *args: str, payload: bytes | None = None, accepted: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
  try:
    result = subprocess.run(['git', '-C', str(repo), *args], input=payload,
                            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}, capture_output=True, check=False)
  except OSError as error:
    raise OverlayError('Git 실행 도구를 사용할 수 없습니다') from error
  if result.returncode not in accepted:
    detail = result.stderr.decode('utf-8', errors='replace').strip()[:1200]
    raise OverlayError(f'Git 검사 또는 적용을 완료하지 못했습니다: {detail}')
  return result


def changed_files(repo: Path) -> set[str]:
  status = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all').stdout
  result = set()
  for entry in status.split(b'\0'):
    if not entry:
      continue
    if len(entry) < 4 or entry[2:3] != b' ' or b'R' in entry[:2] or b'C' in entry[:2]:
      raise OverlayError('이름 변경·복사 또는 해석할 수 없는 작업트리 상태를 거절합니다')
    result.add(entry[3:].decode('utf-8', errors='surrogateescape'))
  return result


def ensure_clean(repo: Path) -> None:
  if changed_files(repo):
    raise OverlayError('기존 tracked/untracked 변경이 있습니다. 깨끗한 개발용 clone을 사용해야 합니다')


def unique_object(pairs):
  result = {}
  for key, value in pairs:
    if key in result:
      raise OverlayError('manifest의 중복 JSON 키를 거절합니다')
    result[key] = value
  return result


def valid_hash(value: object) -> bool:
  return isinstance(value, str) and SHA256.fullmatch(value) is not None


def validate_manifest(assets: Path) -> tuple[dict, bytes]:
  path = safe_child(assets, 'runtime_manifest.json')
  try:
    raw = path.read_bytes()
    manifest = json.loads(raw, object_pairs_hook=unique_object)
  except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise OverlayError('runtime_manifest.json을 읽거나 해석할 수 없습니다') from error
  if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or
      manifest.get('schema_version') != 1 or manifest.get('vehicle_deployment_allowed') is not False):
    raise OverlayError('manifest schema 1과 차량 배포 금지 선언이 필요합니다')
  source = manifest.get('source')
  if not isinstance(source, dict) or not isinstance(source.get('baseline'), str) or COMMIT.fullmatch(source['baseline']) is None:
    raise OverlayError('manifest의 기준 Git commit을 확인할 수 없습니다')
  groups = manifest.get('groups')
  artifacts = manifest.get('artifacts_sha256')
  if (not isinstance(groups, dict) or set(groups) != set(PARTS) or
      not isinstance(artifacts, dict) or set(artifacts) != ARTIFACTS):
    raise OverlayError('manifest의 세 component와 patch 지문 목록이 필요합니다')
  for name, expected in artifacts.items():
    safe_relative(name)
    if not valid_hash(expected):
      raise OverlayError('artifact SHA-256 형식이 올바르지 않습니다')
  for part in PARTS:
    group = groups[part]
    if not isinstance(group, dict) or not isinstance(group.get('files'), list):
      raise OverlayError(f'component 파일 목록이 올바르지 않습니다: {part}')
    files = group['files']
    if not all(isinstance(name, str) for name in files) or len(files) != len(set(files)) or set(files) != ALLOWED_FILES[part]:
      raise OverlayError(f'허용한 실행 파일 목록과 다릅니다: {part}')
    for name in files:
      safe_relative(name)
    pre, post, guards = (group.get(key) for key in ('preimage_sha256_lf', 'postimage_sha256_lf', 'compatibility_sha256_lf'))
    if not isinstance(pre, dict) or not isinstance(post, dict) or set(pre) != set(files) or set(post) != set(files) or not isinstance(guards, dict):
      raise OverlayError(f'component의 pre/post/guard 지문 목록이 올바르지 않습니다: {part}')
    for name in files:
      if (pre[name] is not None and not valid_hash(pre[name])) or not valid_hash(post[name]) or pre[name] == post[name]:
        raise OverlayError(f'component의 실행 파일 지문이 올바르지 않습니다: {part}')
      if (pre[name] is not None) != (name in EXISTING_FILES):
        raise OverlayError('기존 7개와 추가 12개의 preimage 선언을 확인할 수 없습니다')
    if set(guards) != REQUIRED_GUARDS[part]:
      raise OverlayError(f'허용한 호환성 source guard가 아닌 경로 또는 필수 guard 누락입니다: {part}')
    for name, expected in guards.items():
      safe_relative(name)
      if name not in ALLOWED_GUARDS or name in RUNTIME_FILES or not valid_hash(expected):
        raise OverlayError(f'guard는 실행 변경 파일과 분리돼야 합니다: {part}')
    patch = safe_relative(group.get('patch'))
    if patch != f'patches/{part}.patch':
      raise OverlayError(f'component patch의 원문 SHA-256이 없습니다: {part}')
  return manifest, raw


def patch_targets(raw: bytes, expected_files: set[str], preimages: dict[str, str | None]) -> set[str]:
  if not raw.endswith(b'\n'):
    raise OverlayError('끝이 잘린 patch를 거절합니다')
  try:
    lines = raw.decode('utf-8').splitlines()
  except UnicodeError as error:
    raise OverlayError('UTF-8 text patch만 허용합니다') from error
  sections = []
  current = None
  for line in lines:
    if line.startswith('diff --git '):
      match = DIFF.fullmatch(line)
      if match is None or match[1] != match[2]:
        raise OverlayError('이름 변경·경로 이탈 형태의 diff를 거절합니다')
      name = safe_relative(match[1])
      if name not in expected_files:
        raise OverlayError(f'선택한 component 밖의 diff 경로를 거절합니다: {name}')
      current = {'path': name, 'new': False, 'old': None, 'next': None, 'hunk': False}
      sections.append(current)
    elif current is None:
      if line:
        raise OverlayError('Git diff 밖의 patch 명령 또는 설명을 거절합니다')
    elif current['hunk'] and line[:1] in (' ', '+', '-', '\\'):
      # hunk 안의 삭제/추가 내용이 ---/+++처럼 보여도 경로 헤더로 해석하지 않는다.
      continue
    elif line.startswith(('old mode ', 'new mode ', 'deleted file mode ', 'rename from ', 'rename to ',
                          'copy from ', 'copy to ', 'GIT binary patch', 'Binary files ', 'similarity index ')):
      raise OverlayError('mode 변경·삭제·이름 변경·복사·binary patch는 허용하지 않습니다')
    elif line.startswith('new file mode '):
      if line != 'new file mode 100644':
        raise OverlayError('새 실행 파일은 일반 파일 mode 100644만 허용합니다')
      current['new'] = True
    elif line.startswith('--- '):
      value = line[4:]
      if value not in ('/dev/null', 'a/' + current['path']):
        raise OverlayError('원형 diff 경로가 선언과 다릅니다')
      current['old'] = value
    elif line.startswith('+++ '):
      value = line[4:]
      if value != 'b/' + current['path']:
        raise OverlayError('최종 diff 경로가 선언과 다릅니다')
      current['next'] = value
    elif line.startswith('@@ '):
      current['hunk'] = True
  names = [section['path'] for section in sections]
  if len(names) != len(set(names)) or set(names) != expected_files:
    raise OverlayError('patch의 실제 변경 목록이 선택 component 목록과 다릅니다')
  for section in sections:
    fresh = preimages[section['path']] is None
    if section['new'] != fresh:
      raise OverlayError('기존/추가 파일의 patch 선언이 preimage와 다릅니다')
    if section['hunk']:
      wanted_old = '/dev/null' if fresh else 'a/' + section['path']
      if section['old'] != wanted_old or section['next'] != 'b/' + section['path']:
        raise OverlayError('diff의 원형·최종 헤더를 확인할 수 없습니다')
    elif not fresh:
      raise OverlayError('기존 파일에 실제 diff hunk가 없습니다')
  return set(names)


def verify_preimages(repo: Path, preimages: dict[str, str | None], guards: dict[str, str]) -> None:
  tracked = git(repo, 'ls-files', '--stage', '-z', '--', *preimages, *guards).stdout
  tracked_paths = set()
  for row in tracked.split(b'\0'):
    if row:
      metadata, name = row.split(b'\t', 1)
      mode, _, stage = metadata.split()
      if mode not in (b'100644', b'100755') or stage != b'0':
        raise OverlayError('symlink·gitlink·충돌 상태의 tracked 경로를 허용하지 않습니다')
      tracked_paths.add(name.decode('utf-8'))
  for name, expected in (*preimages.items(), *guards.items()):
    path = safe_child(repo, name)
    if expected is None:
      if path.exists() or symbolic(path):
        raise OverlayError(f'추가할 파일이 이미 있습니다: {name}')
      # 아직 없는 파일도 ignore 대상이면 적용 후 변경 목록에서 숨겨지므로 먼저 거절한다.
      if git(repo, 'check-ignore', '--no-index', '--', name, accepted=(0, 1)).returncode == 0:
        raise OverlayError(f'추가할 실행 파일이 Git ignore 대상입니다: {name}')
    elif name not in tracked_paths or not path.is_file() or hash_lf(path) != expected:
      raise OverlayError(f'선택 source 또는 읽기 guard 본문이 다릅니다: {name}')


def report_path(value: Path | None, repo: Path) -> Path | None:
  if value is None:
    return None
  absolute = value.absolute()
  for parent in (absolute, *absolute.parents):
    if symbolic(parent):
      raise OverlayError('보고서의 심볼릭 경로 또는 junction을 허용하지 않습니다')
  resolved = absolute.resolve()
  if resolved.is_relative_to(repo) or operational(resolved, report=True):
    raise OverlayError('보고서는 repo 밖의 운영 /data 경로가 아닌 곳에만 쓸 수 있습니다')
  if resolved.exists():
    raise OverlayError('기존 보고서를 덮어쓰지 않습니다. 새 --report 경로를 지정해야 합니다')
  if not resolved.parent.is_dir():
    raise OverlayError('보고서 부모 디렉터리는 미리 존재해야 합니다. 저장 중 새 부모 경로를 만들지 않습니다')
  return resolved


class ReportSink:
  """보고서 경로를 핸들에 연결한다. 일반 경로 재해석으로 쓰지 않는다."""

  def __init__(self, path: Path, repo: Path):
    self.path, self.repo = path, repo
    self.resources = ExitStack()
    self.fd = None
    self.parent_fd = None
    self.created = False
    self.committed = False

  def _validate_actual(self, actual: Path, expected: Path) -> None:
    if actual != expected or actual.is_relative_to(self.repo) or operational(actual, report=True):
      raise OverlayError('보고서의 실제 열린 경로가 외부 지정 경로와 다릅니다')

  def _linux_actual(self, fd: int) -> Path:
    # Linux의 열린 객체 경로를 검사한다. pathname.resolve()만으로 핸들을 대신하지 않는다.
    value = os.readlink(f'/proc/self/fd/{fd}')
    if value.endswith(' (deleted)'):
      raise OverlayError('보고서 디렉터리 또는 파일이 저장 중 제거됐습니다')
    return Path(value)

  def _linux_open(self) -> None:
    if sys.platform != 'linux' or not hasattr(os, 'O_NOFOLLOW'):
      raise OverlayError('이 POSIX 환경에서 보고서 핸들 검사를 지원하지 않습니다')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent = Path(self.path.anchor)
    descriptor = os.open(parent, flags)
    self.resources.callback(os.close, descriptor)
    for component in self.path.parent.parts[1:]:
      parent /= component
      descriptor = os.open(component, flags, dir_fd=descriptor)
      self.resources.callback(os.close, descriptor)
      self._validate_actual(self._linux_actual(descriptor), parent)
    self.parent_fd = descriptor
    self._validate_actual(self._linux_actual(descriptor), self.path.parent)
    self.fd = os.open(self.path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                      0o600, dir_fd=descriptor)
    self.created = True
    self.resources.callback(os.close, self.fd)
    self._validate_actual(self._linux_actual(self.fd), self.path)

  def _windows_open(self) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD)
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.GetFileInformationByHandleEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL

    class AttributeTag(ctypes.Structure):
      _fields_ = [('attributes', wintypes.DWORD), ('tag', wintypes.DWORD)]

    def open_handle(path, access, disposition, flags):
      # 쓰기·삭제 공유를 주지 않아 보유 중인 조상의 rename/junction 변환을 거절한다.
      handle = kernel.CreateFileW(str(path), access, 1, None, disposition, flags, None)
      if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
      return handle

    def actual(handle):
      attributes = AttributeTag()
      if not kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)):
        raise ctypes.WinError(ctypes.get_last_error())
      if attributes.attributes & 0x400:
        raise OverlayError('열린 보고서 조상 또는 파일이 재분석 지점입니다')
      buffer = ctypes.create_unicode_buffer(32768)
      size = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
      if not size or size >= len(buffer):
        raise OverlayError('열린 보고서 핸들의 실제 경로를 확인할 수 없습니다')
      name = buffer.value
      if name.startswith('\\\\?\\UNC\\'):
        name = '\\\\' + name[8:]
      elif name.startswith('\\\\?\\'):
        name = name[4:]
      return Path(name)

    for parent in reversed((self.path.parent, *self.path.parent.parents)):
      handle = open_handle(parent, 0x80000000 | 0x80, 3, 0x02000000 | 0x00200000)
      self.resources.callback(kernel.CloseHandle, handle)
      self._validate_actual(actual(handle), parent)
    handle = open_handle(self.path, 0x40000000 | 0x10000 | 0x80, 1, 0x00200000 | 0x80)
    self.created = True
    try:
      self._validate_actual(actual(handle), self.path)
      self.fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except Exception:
      kernel.CloseHandle(handle)
      raise
    self.resources.callback(os.close, self.fd)
    self._windows_actual = lambda: actual(msvcrt.get_osfhandle(self.fd))

    def remove_own_file():
      remove = wintypes.BOOL(True)
      if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(self.fd), 4,
                                               ctypes.byref(remove), ctypes.sizeof(remove)):
        raise ctypes.WinError(ctypes.get_last_error())
    self._windows_remove = remove_own_file

  def __enter__(self):
    try:
      report_path(self.path, self.repo)
      self._windows_open() if os.name == 'nt' else self._linux_open()
    except Exception:
      self.__exit__(*sys.exc_info())
      raise
    return self

  def write(self, result: dict) -> None:
    # FD를 얻기 전이나 뒤에 경로가 바뀌었으면 결과 본문을 쓰지 않는다.
    actual = self._windows_actual() if os.name == 'nt' else self._linux_actual(self.fd)
    self._validate_actual(actual, self.path)
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    view = memoryview(raw)
    while view:
      count = os.write(self.fd, view)
      if count <= 0:
        raise OverlayError('보고서 저장이 완료되지 않았습니다')
      view = view[count:]
    os.fsync(self.fd)
    actual = self._windows_actual() if os.name == 'nt' else self._linux_actual(self.fd)
    self._validate_actual(actual, self.path)
    self.committed = True

  def __exit__(self, *error):
    # 실패 파일만 제거한다. Linux에서는 동일한 부모 FD에 연결한 자기 파일만 다룬다.
    try:
      if self.created and not self.committed and self.fd is not None:
        if os.name == 'nt':
          self._windows_remove()
        elif self.parent_fd is not None:
          own = os.fstat(self.fd)
          current = os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False)
          if (own.st_dev, own.st_ino) == (current.st_dev, current.st_ino):
            os.unlink(self.path.name, dir_fd=self.parent_fd)
    except OSError:
      pass
    finally:
      self.resources.close()
    # Windows도 소유 핸들로 삭제한다. pathname으로 동시 새 파일을 지우지 않는다.
    return False


def make_plan(repo: Path, assets: Path, parts: tuple[str, ...], *, apply: bool = False, report: Path | None = None) -> Plan:
  if symbolic(repo) or symbolic(assets):
    raise OverlayError('repo 또는 assets의 심볼릭 경로는 허용하지 않습니다')
  repo, assets = repo.resolve(), assets.resolve()
  if apply and operational(repo):
    raise OverlayError('운영 /data/openpilot에는 적용하지 않습니다. 개발용 clone만 허용합니다')
  if not repo.is_dir() or not assets.is_dir():
    raise OverlayError('repo와 assets 디렉터리가 필요합니다')
  top = git(repo, 'rev-parse', '--show-toplevel').stdout.decode('utf-8').strip()
  if Path(top).resolve() != repo or git(repo, 'rev-parse', '--is-inside-work-tree').stdout.strip() != b'true':
    raise OverlayError('repo 인수는 Git 작업트리 루트여야 합니다')
  ensure_clean(repo)
  if not parts or len(parts) != len(set(parts)) or any(part not in PARTS for part in parts):
    raise OverlayError('radar/pcm/longitudinal component를 중복 없이 선택해야 합니다')
  parts = tuple(part for part in PARTS if part in parts)
  manifest, manifest_raw = validate_manifest(assets)
  baseline = manifest['source']['baseline']
  ancestor = git(repo, 'merge-base', '--is-ancestor', baseline, 'HEAD', accepted=(0, 1, 128))
  if ancestor.returncode != 0:
    raise OverlayError('현재 HEAD에 manifest 기준 commit이 ancestor로 존재하지 않습니다')
  head = git(repo, 'rev-parse', 'HEAD').stdout.decode('ascii').strip()
  selected_files, preimages, postimages, guards, combined = set(), {}, {}, {}, []
  artifact_hashes, artifact_contents = {}, {}
  # bundle의 모든 명시 artifact를 검사한다. 선택되지 않은 파일도 변조를 숨기지 않는다.
  for name, expected in manifest['artifacts_sha256'].items():
    artifact = safe_child(assets, name)
    raw = artifact.read_bytes() if artifact.is_file() else None
    if raw is None or sha256(raw) != expected:
      raise OverlayError(f'artifact 원문 SHA-256이 다릅니다: {name}')
    artifact_hashes[name] = expected
    artifact_contents[name] = raw
  for part in parts:
    group = manifest['groups'][part]
    files = set(group['files'])
    selected_files.update(files)
    preimages.update(group['preimage_sha256_lf'])
    postimages.update(group['postimage_sha256_lf'])
    for name, expected in group['compatibility_sha256_lf'].items():
      if name in guards and guards[name] != expected:
        raise OverlayError('component 간 호환성 guard 지문이 서로 다릅니다')
      guards[name] = expected
    # 지문을 확인한 바로 그 bytes를 사용한다. 검사 뒤 파일을 다시 읽어 바꾸지 않는다.
    raw = artifact_contents[group['patch']]
    patch_targets(raw, files, group['preimage_sha256_lf'])
    combined.append(raw)
  patch = b'\n'.join(combined)
  destination = report_path(report, repo)
  verify_preimages(repo, preimages, guards)
  git(repo, '-c', 'core.autocrlf=false', 'apply', '--check', '--whitespace=error', '-', payload=patch)
  return Plan(repo, assets, parts, baseline, head, tuple(sorted(selected_files)), preimages, postimages,
              guards, patch, sha256(manifest_raw), artifact_hashes, destination)


def _execute_checked(plan: Plan, *, apply: bool, applied: list[bool]) -> dict:
  if apply:
    if operational(plan.repo):
      raise OverlayError('운영 /data/openpilot에는 적용할 수 없습니다')
    # 검사 이후의 동시 변경도 다시 거절한다. Git apply는 한 번만 호출한다.
    ensure_clean(plan.repo)
    if git(plan.repo, 'rev-parse', 'HEAD').stdout.decode('ascii').strip() != plan.head:
      raise OverlayError('검사 이후 HEAD가 바뀌어 적용하지 않습니다')
    verify_preimages(plan.repo, plan.preimages, plan.guards)
    git(plan.repo, '-c', 'core.autocrlf=false', 'apply', '--whitespace=error', '-', payload=plan.patch)
    applied[0] = True
    if changed_files(plan.repo) != set(plan.files):
      raise OverlayError('적용 후 변경 목록이 예상과 다릅니다. 성공으로 기록하지 않았으니 개발 clone을 확인해야 합니다')
    for name, expected in plan.postimages.items():
      path = safe_child(plan.repo, name)
      if not path.is_file() or hash_lf(path) != expected:
        raise OverlayError('적용 후 본문 지문이 다릅니다. 자동 덮어쓰기·원복 없이 개발 clone 확인이 필요합니다')
    for name, expected in plan.guards.items():
      if hash_lf(safe_child(plan.repo, name)) != expected:
        raise OverlayError('적용 후 읽기 guard가 바뀌었습니다. 성공으로 기록하지 않습니다')
  result = {
    'schema_version': 1, 'status': '선택 실행 패치 적용·사후검사 완료' if apply else '읽기 전용 검사 완료',
    'mode': 'apply' if apply else 'check', 'repo': str(plan.repo), 'parts': list(plan.parts),
    'baseline': plan.baseline, 'head': plan.head, 'manifest_sha256': plan.manifest_hash,
    'artifacts_sha256': plan.artifact_hashes, 'files': list(plan.files),
    'postimage_sha256_lf': plan.postimages, 'compatibility_sha256_lf': plan.guards,
    'vehicle_deployment_allowed': False,
    '설명': '개발 clone의 선택 source만 검사했습니다. 빌드·제어 실행·실차 또는 firmware 안전 검증이 아닙니다.',
  }
  return result


def execute(plan: Plan, *, apply: bool) -> dict:
  applied = [False]
  try:
    with ExitStack() as resources:
      # 보고서 핸들 획득 실패는 실제 patch 적용보다 먼저 일어나야 한다.
      sink = resources.enter_context(ReportSink(plan.report, plan.repo)) if plan.report is not None else None
      result = _execute_checked(plan, apply=apply, applied=applied)
      if sink is not None:
        sink.write(result)
      return result
  except (OverlayError, OSError, ValueError) as error:
    if applied[0]:
      raise OverlayError(f'패치 적용은 완료됐지만 사후 검사 또는 보고서 저장은 실패했습니다. '
                         f'자동 원복 없이 개발 clone을 확인해야 합니다: {error}') from error
    raise


def main(argv=None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('repo', type=Path, help='운영 경로가 아닌 깨끗한 개발용 Git clone')
  parser.add_argument('--parts', nargs='+', choices=PARTS, default=list(PARTS), help='선택 component; 기본값은 세 군 전부')
  parser.add_argument('--assets', type=Path, default=Path(__file__).resolve().parent / 'assets', help='runtime_manifest.json과 patch 폴더')
  action = parser.add_mutually_exclusive_group()
  action.add_argument('--check', action='store_true', help='읽기 전용 검사; 기본 동작')
  action.add_argument('--apply', action='store_true', help='검사 통과 후 선택 diff를 한 번 적용')
  parser.add_argument('--report', type=Path, help='repo 밖·운영 /data 밖의 새 JSON 경로')
  args = parser.parse_args(argv)
  try:
    plan = make_plan(args.repo, args.assets, tuple(args.parts), apply=args.apply, report=args.report)
    result = execute(plan, apply=args.apply)
  except (OverlayError, OSError, ValueError) as error:
    print(f'거절: {error}', file=sys.stderr)
    return 2
  print(json.dumps(result, ensure_ascii=False, indent=2))
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
