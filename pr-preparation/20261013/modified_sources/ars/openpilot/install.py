#!/usr/bin/env python3
"""Install (or remove) the ARS510 radar-track integration into openpilot or any fork.

    python openpilot/install.py /data/openpilot                     # install (acc profile, the default), then reboot
    python openpilot/install.py /data/openpilot --profile raw       # the unfiltered decode, for comparison
    python openpilot/install.py /data/openpilot --check             # report the state only
    python openpilot/install.py /data/openpilot --uninstall         # remove everything this installer added

The path may be the openpilot checkout or its opendbc_repo. The same install works on openpilot, sunnypilot,
StarPilot, CarrotPilot and other forks: the installer adds new files and one marked block to the fork. The installer
  - copies the decoder package to        opendbc/car/toyota/ars510/
  - copies the radar interface to        opendbc/car/toyota/ars510_radar_interface.py (profile line set)
  - copies the openpilot version to      opendbc/car/toyota/ars510_upstream.py (used by --profile openpilot)
  - copies the ACC-target file to        opendbc/car/toyota/ars510_acc_target.py (used by --profile acc)
    and its DBC to                       opendbc/dbc/toyota_tss2_ars510.dbc
  - copies two research files to         opendbc/car/toyota/ars510_shared_{speed,range}.py (--profile shared_speed / shared_range)
  - appends one marked block to the end of opendbc/car/toyota/interface.py, which wraps the fork's own
    CarInterface: ARS510 detection in _get_params and dispatch in RadarInterface (see ars510_radar_interface.py)
An install made with an older, patch-based version of this installer is removed first.

Profiles (docs/08 has the details and replay numbers):
  acc       (default) the radar's ACC target alone as one point (upstream/ars510_acc_target.py with
            toyota_tss2_ars510.dbc): the car Toyota's own ACC follows; every other car comes from the camera. It
            publishes a target as soon as the radar picks it; fused holds new tracks back for 60 cycles (docs/11)
  fused     FUSED_CONFIG: the radar decode + range fusion + one Kalman speed filter per track that weights
            the object list and the radar's ACC target by their own uncertainty, with a path gate (= the openpilot version)
  raw       BASE_CONFIG: the unfiltered radar decode with only what radard
            needs to run. Velocity excursions reach the planner unfiltered; for research and comparison only
  openpilot fused in one file (upstream/ars510_radar.py, opendbc style), driving identically, points with trackId /
            dRel / yRel / vRel only. The all-tracks upstream alternative; the proposal is acc
  Also tried, set aside (installable for research; docs/12, docs/17): colored (fused with a colored-noise state) and
  shared_speed / shared_range (every object and the ACC target through one gate-free Kalman model)

Legacy names are aliases: anchor/steady select fused, upstream selects openpilot,
and stock/default select raw. Every alias prints its selection. Omit --profile for the recommended acc default.
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LEGACY_PATCHES = sorted((HERE / "legacy").glob("*.patch"))
PROFILE_LINE = 'PROFILE = PROFILES["acc"]'
PROFILE_NAMES = ("acc", "fused", "openpilot", "raw", "colored", "shared_speed", "shared_range")
LEGACY_NAMES = {"anchor": "fused", "steady": "fused", "stock": "raw", "default": "raw", "upstream": "openpilot"}
DBCS = ("ars510_radar_bus.dbc", "ars510_objects_vbus.dbc")  # repo dbc/ serves Cabana on a PC and stays in the repo
BEGIN = "# >>> ars510-radar: added by ars510-radar/openpilot/install.py; remove with install.py --uninstall"
END = "# <<< ars510-radar"
HOOK = f"""
{BEGIN}
from opendbc.car.toyota.ars510_radar_interface import hook_car_interface as _ars510_hook_car_interface  # noqa: E402
CarInterface = _ars510_hook_car_interface(CarInterface)
{END}
"""


def find_opendbc(path: Path) -> Path | None:
  """The opendbc checkout: the directory holding the real opendbc/ package. openpilot checkouts have a top-level
  `opendbc` symlink into opendbc_repo; resolve it, so git sees the files where they are tracked."""
  for root in (path / "opendbc_repo", path, path / "opendbc"):
    pkg = root / "opendbc"
    if (pkg / "car" / "toyota" / "interface.py").exists():
      return pkg.resolve().parent
  return None


def targets(root: Path) -> dict[str, Path]:
  toyota = root / "opendbc" / "car" / "toyota"
  return {"package": toyota / "ars510", "interface": toyota / "ars510_radar_interface.py",
          "upstream": toyota / "ars510_upstream.py", "acc_target": toyota / "ars510_acc_target.py",
          "shared_speed": toyota / "ars510_shared_speed.py", "shared_range": toyota / "ars510_shared_range.py",
          "acc_dbc": root / "opendbc" / "dbc" / "toyota_tss2_ars510.dbc"}


def old_dbcs(root: Path) -> list[Path]:
  """Cabana DBCs that older versions of this installer copied into the fork; parsing reads the decoder package alone."""
  return [p for p in (root / "opendbc" / "dbc" / dbc for dbc in DBCS) if p.exists()]


def git_apply(root: Path, patch: Path, *args: str) -> bool:
  """git apply with paths relative to the opendbc checkout. When opendbc_repo sits inside a larger work tree
  (openpilot vendors it), git would resolve paths from that tree's top and skip files it considers elsewhere while
  still exiting 0. GIT_CEILING_DIRECTORIES stops the search above opendbc_repo, and any skipped file counts as failure."""
  env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(root.resolve().parent)}
  r = subprocess.run(["git", "apply", "-v", *args, str(patch)], cwd=root, env=env, capture_output=True, text=True)
  return r.returncode == 0 and "Skipped patch" not in r.stdout + r.stderr


def legacy_patch(root: Path) -> Path | None:
  """The older patch-based install, if one is applied here."""
  for patch in LEGACY_PATCHES:
    if git_apply(root, patch, "--check", "--reverse"):
      return patch
  return None


def sources() -> dict[str, Path]:
  """What each target is copied from (the interface file differs from its source only by the profile line)."""
  return {"package": REPO / "ars510", "interface": HERE / "ars510_radar_interface.py",
          "upstream": REPO / "upstream" / "ars510_radar.py", "acc_target": REPO / "upstream" / "ars510_acc_target.py",
          "shared_speed": HERE / "standalone" / "ars510_shared_speed.py",
          "shared_range": HERE / "standalone" / "ars510_shared_range.py",
          "acc_dbc": REPO / "upstream" / "toyota_tss2_ars510.dbc"}


def native_package_owner(root: Path) -> tuple[str, str]:
  """fork Python을 실행하지 않고 명시한 native package 보호 계약만 읽는다."""
  path = root / "opendbc" / "car" / "toyota" / "radar_interface.py"
  if not path.exists():
    return "installer", "no native contract"
  try:
    text = path.read_text(encoding="utf-8")
  except (OSError, UnicodeError):
    return "ambiguous", "cannot read native contract source"
  markers = ("ARS510_CARROT_API", "ARS510_CARROT_PROFILE")
  if not any(name in text for name in markers):
    return "installer", "no native contract"
  try:
    tree = ast.parse(text)
  except SyntaxError:
    return "ambiguous", "cannot parse native contract"
  if not any((isinstance(node, ast.Name) and node.id in markers) or
             (isinstance(node, ast.Attribute) and node.attr in markers) for node in ast.walk(tree)):
    return "installer", "no native contract"
  classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RadarInterface"]
  if len(classes) != 1:
    return "ambiguous", "expected one native RadarInterface class"
  values: dict[str, list[ast.expr]] = {name: [] for name in (*markers, "supports_ars510")}
  predicate_functions = 0
  for node in classes[0].body:
    if isinstance(node, ast.FunctionDef) and node.name == "supports_ars510":
      predicate_functions += 1
    if isinstance(node, ast.Assign):
      targets, value = node.targets, node.value
    elif isinstance(node, ast.AnnAssign):
      targets, value = [node.target], node.value
    else:
      continue
    for target in targets:
      if isinstance(target, ast.Name) and target.id in values and value is not None:
        values[target.id].append(value)
  api, profile = values[markers[0]], values[markers[1]]
  if not (len(api) == len(profile) == 1 and isinstance(api[0], ast.Constant)
          and type(api[0].value) is int and api[0].value == 1
          and isinstance(profile[0], ast.Constant) and profile[0].value == "fused"):
    return "ambiguous", "unsupported or nonliteral native API/profile"
  support = values["supports_ars510"]
  if predicate_functions + len(support) != 1:
    return "ambiguous", "expected one native support predicate declaration"
  predicate = predicate_functions == 1
  if len(support) == 1:
    value = support[0]
    predicate |= isinstance(value, (ast.Name, ast.Attribute, ast.Lambda)) or (
      isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
      and value.func.id in ("staticmethod", "classmethod") and len(value.args) == 1
      and isinstance(value.args[0], (ast.Name, ast.Attribute, ast.Lambda)))
  if not predicate:
    return "ambiguous", "missing native support predicate declaration"
  return "fork", "API 1, fused, support predicate declared"


def package_state(src: Path, dst: Path) -> str:
  """version 문자열 대신 공유 Python 파일 목록과 원바이트를 대조한다."""
  if not dst.is_dir():
    return "missing"
  try:
    files = sorted(p.relative_to(src) for p in src.rglob("*.py"))
    if files != sorted(p.relative_to(dst) for p in dst.rglob("*.py")) or \
       any((src / f).read_bytes() != (dst / f).read_bytes() for f in files):
      return "different"
  except OSError:
    return "unreadable"
  return "compatible"


def stale(t: dict[str, Path]) -> list[str]:
  """Installed targets that differ from this checkout: an install made with an older (or newer) ars510-radar."""
  out = []
  for name, src in sources().items():
    dst = t[name]
    if not dst.exists():
      continue
    if src.is_dir():
      files = sorted(p.relative_to(src) for p in src.rglob("*.py"))
      if files != sorted(p.relative_to(dst) for p in dst.rglob("*.py")) or \
         any((src / f).read_bytes() != (dst / f).read_bytes() for f in files):
        out.append(name)
    elif name == "interface":
      txt = dst.read_text()
      prof = next((k for k in PROFILE_NAMES if f'PROFILE = PROFILES["{k}"]' in txt), None)
      if prof is None or txt.replace(f'PROFILE = PROFILES["{prof}"]', PROFILE_LINE) != src.read_text():
        out.append(name)
    elif src.read_bytes() != dst.read_bytes():
      out.append(name)
  return out


def remove_hook(text: str) -> str:
  if BEGIN not in text:
    return text
  head, rest = text.split(BEGIN, 1)
  return head.rstrip("\n") + "\n" + rest.split(END, 1)[1].lstrip("\n")


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("openpilot", type=Path, help="openpilot (or fork) checkout, or its opendbc_repo")
  ap.add_argument("--profile", choices=PROFILE_NAMES + tuple(LEGACY_NAMES), default="acc",
                  metavar="{" + ",".join(PROFILE_NAMES) + "}", help="default: acc; legacy aliases also accepted")
  ap.add_argument("--flavor", help=argparse.SUPPRESS)  # accepted for old instructions; ignored
  g = ap.add_mutually_exclusive_group()
  g.add_argument("--check", action="store_true")
  g.add_argument("--uninstall", action="store_true")
  args = ap.parse_args()
  if args.profile in LEGACY_NAMES:
    new = LEGACY_NAMES[args.profile]
    retired = "the tuned profile was removed; " if new == "fused" else ""
    print(f"note: {retired}'{args.profile}' is an alias for '{new}'; the recommended default is 'acc'")
    args.profile = new
  root = find_opendbc(args.openpilot)
  if root is None:
    print(f"expected opendbc/car/toyota/interface.py under {args.openpilot} (or its opendbc_repo)", file=sys.stderr)
    return 2
  t = targets(root)
  interface_py = root / "opendbc" / "car" / "toyota" / "interface.py"
  text = interface_py.read_text()
  owner, ownership_reason = native_package_owner(root)
  native_state = package_state(REPO / "ars510", t["package"]) if owner == "fork" else None
  legacy = legacy_patch(root)

  if args.check:
    print(f"opendbc: {root}")
    print(f"hook in toyota/interface.py: {'present' if BEGIN in text else 'to be installed'}")
    print(f"older patch-based install: {legacy.name if legacy else 'none'}")
    if t["interface"].exists():
      txt = t["interface"].read_text()
      prof = next((k for k in PROFILE_NAMES + tuple(LEGACY_NAMES) if f'PROFILE = PROFILES["{k}"]' in txt), "other")
      print(f"profile: {prof}")
    for name, p in t.items():
      print(f"{name}: {'present' if p.exists() else 'to be installed'} ({p})")
    for p in old_dbcs(root):
      print(f"leftover from an older install (removed on the next install): {p}")
    if owner == "fork":
      print(f"native decoder package: fork-owned ({native_state}); install/uninstall preserve it")
    elif owner == "ambiguous":
      print(f"native decoder contract: ambiguous ({ownership_reason}); no changes permitted")
    if t["interface"].exists():
      diff = stale(t)
      if owner == "fork" and native_state != "compatible":
        remedy = "update the fork or use a matching ars510-radar checkout; do not overwrite the native package"
      elif owner == "ambiguous":
        remedy = "review the fork's native contract before making changes"
      else:
        remedy = "run install.py again, then reboot"
      print("installed files: " + ("match this checkout" if not diff else
            f"differ from this checkout ({', '.join(diff)}); {remedy}"))
    if owner == "fork" and native_state != "compatible":
      print("native decoder alignment required: update the fork or use a matching ars510-radar checkout; no package overwrite")
    elif owner == "ambiguous":
      print("native contract review required: verify the fork's API/profile/predicate declaration before making changes")
    return 2 if owner == "ambiguous" or (owner == "fork" and (native_state != "compatible" or legacy is not None)) else 0

  # 공유 package 문제는 legacy reverse·hook/DBC 제거보다 앞에서 중단한다.
  if owner == "ambiguous":
    print(f"native decoder contract: ambiguous ({ownership_reason}); checkout unchanged", file=sys.stderr)
    return 2
  if owner == "fork" and not args.uninstall and native_state != "compatible":
    print(f"native decoder package: fork-owned ({native_state}); update the fork or use a matching ars510-radar checkout; "
          "checkout unchanged", file=sys.stderr)
    return 2
  if owner == "fork" and legacy is not None:
    print("native decoder contract with an older patch-based install; cannot reverse fork-owned files; checkout unchanged",
          file=sys.stderr)
    return 2

  if legacy is not None and not git_apply(root, legacy, "--reverse"):
    print(f"could not remove the older install ({legacy.name}); the checkout stays as it was", file=sys.stderr)
    return 1
  text = remove_hook(interface_py.read_text())
  for p in old_dbcs(root):
    p.unlink()

  if args.uninstall:
    interface_py.write_text(text)
    for name, p in t.items():
      if name == "package" and owner == "fork":
        continue
      if p.is_dir():
        shutil.rmtree(p)
      elif p.exists():
        p.unlink()
    print("removed" + (f" (including the older {legacy.name})" if legacy else ""))
    if owner == "fork":
      print(f"preserved fork-owned native decoder package ({native_state})")
    return 0

  if "class CarInterface" not in text:
    print("expected a CarInterface class in toyota/interface.py; the checkout stays as it was", file=sys.stderr)
    return 1
  if owner != "fork":
    if t["package"].exists():
      shutil.rmtree(t["package"])
    shutil.copytree(REPO / "ars510", t["package"], ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
  shutil.copyfile(REPO / "upstream" / "ars510_radar.py", t["upstream"])
  shutil.copyfile(REPO / "upstream" / "ars510_acc_target.py", t["acc_target"])
  shutil.copyfile(REPO / "upstream" / "toyota_tss2_ars510.dbc", t["acc_dbc"])
  for name in ("shared_speed", "shared_range"):
    shutil.copyfile(HERE / "standalone" / f"ars510_{name}.py", t[name])
  src = (HERE / "ars510_radar_interface.py").read_text()
  assert src.count(PROFILE_LINE) == 1
  t["interface"].write_text(src.replace(PROFILE_LINE, f'PROFILE = PROFILES["{args.profile}"]'))
  interface_py.write_text(text.rstrip("\n") + "\n" + HOOK)
  if owner == "fork":
    print("preserved fork-owned native decoder package (compatible)")
  print(f"installed into {root} ({args.profile} profile" + (f"; replaced the older {legacy.name}" if legacy else "") +
        "). Reboot the device to activate.")
  if args.profile in ("shared_speed", "shared_range"):
    print("warning: a research profile. The object list's slow, correlated errors reach the planner: replays ask for hard\n"
          "radar-only braking 7-21 times as often as fused (docs/17). Keep to research use.")
  if args.profile == "raw":
    print("warning: the raw profile publishes the unfiltered radar decode. Velocity excursions (false closings beyond 40 m)\n"
          "reach the planner unfiltered: 93 hard radar-only braking ticks on the held-out replay routes against 16 for fused and\n"
          "14 for acc (docs/11). Use it for research and comparison; install.py alone installs acc.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
