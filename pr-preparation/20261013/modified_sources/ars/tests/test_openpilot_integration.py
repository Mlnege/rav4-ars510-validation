"""The opendbc integration in openpilot/: install into a copy of a stock opendbc, self-check, uninstall.

Needs an opendbc checkout and a Python with pycapnp, e.g. openpilot's venv:
    ARS510_OPENDBC=$OP/opendbc_repo ARS510_OPENDBC_PYTHON=$OP/.venv/bin/python pytest tests/test_openpilot_integration.py
Skipped when those are not set. Only the copy is modified.
"""
from __future__ import annotations

import os
import importlib.util
import py_compile
import shutil
import subprocess
import sys
import types
from enum import IntFlag
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OPENDBC = os.environ.get("ARS510_OPENDBC")
PYTHON = os.environ.get("ARS510_OPENDBC_PYTHON", sys.executable)


def test_integration_files_compile() -> None:
    for f in ("ars510_radar_interface.py", "install.py", "check_integration.py"):
        py_compile.compile(str(REPO / "openpilot" / f), doraise=True)


@pytest.mark.skipif(not OPENDBC, reason="set ARS510_OPENDBC (and ARS510_OPENDBC_PYTHON) to an opendbc checkout")
def test_install_check_uninstall(tmp_path: Path) -> None:
    dst = tmp_path / "opendbc_repo"
    shutil.copytree(OPENDBC, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"), symlinks=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([*args], cwd=REPO, env=env, capture_output=True, text=True)

    before = (dst / "opendbc/car/toyota/interface.py").read_text()
    r = run(sys.executable, "openpilot/install.py", str(dst))
    assert r.returncode == 0, r.stdout + r.stderr
    r = run(PYTHON, "openpilot/check_integration.py", "--opendbc", str(dst))
    assert r.returncode == 0 and "ALL OK" in r.stdout, r.stdout + r.stderr
    r = run(sys.executable, "openpilot/install.py", str(dst), "--uninstall")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dst / "opendbc/car/toyota/interface.py").read_text() == before
    assert not (dst / "opendbc/car/toyota/ars510").exists()


def test_check_reports_an_outdated_install(tmp_path: Path) -> None:
    """--check tells an install from this checkout apart from one made with another ars510-radar version."""
    toyota = tmp_path / "opendbc/car/toyota"
    toyota.mkdir(parents=True)
    (tmp_path / "opendbc/dbc").mkdir()
    (toyota / "interface.py").write_text("class CarInterface:\n  pass\n")

    def run(*args: str) -> str:
        r = subprocess.run([sys.executable, "openpilot/install.py", str(tmp_path), *args], cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout

    run("--profile", "fused")
    assert "installed files: match this checkout" in run("--check")
    old = toyota / "ars510_radar_interface.py"
    old.write_text(old.read_text().replace("def detect(", "def detect_old("))
    (toyota / "ars510/objects.py").write_text("# older\n")
    assert "differ from this checkout (package, interface); run install.py again" in run("--check")
    run()
    assert "installed files: match this checkout" in run("--check")


@pytest.fixture
def dispatch_module(monkeypatch):
    """계산 없이 원형 hook의 분기만 검사한다. 실제 Carrot 동역학은 별도 probe다."""
    import ars510
    from ars510 import constants

    for name in ("opendbc", "opendbc.car", "opendbc.car.toyota"):
        package = types.ModuleType(name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, name, package)

    # fork의 기존 비트를 읽는 계약을 검사하기 위한 metadata fixture이며 CAN 신호가 아니다.
    class ToyotaFlags(IntFlag):
        RADAR_ACC = 1 << 13

    values = types.ModuleType("opendbc.car.toyota.values")
    values.ToyotaFlags = ToyotaFlags
    interfaces = types.ModuleType("opendbc.car.interfaces")
    interfaces.RadarInterfaceBase = type("RadarInterfaceBase", (), {})
    logger = types.ModuleType("opendbc.car.carlog")
    logger.carlog = types.SimpleNamespace(warning=lambda *args: None)
    structs = types.SimpleNamespace(RadarData=types.SimpleNamespace(RadarPoint=types.SimpleNamespace))
    sys.modules["opendbc.car"].structs = structs
    for name, module in ((values.__name__, values), (interfaces.__name__, interfaces), (logger.__name__, logger),
                         ("opendbc.car.toyota.ars510", ars510), ("opendbc.car.toyota.ars510.constants", constants)):
        monkeypatch.setitem(sys.modules, name, module)

    name = "_ars510_dispatch_contract"
    spec = importlib.util.spec_from_file_location(name, REPO / "openpilot/ars510_radar_interface.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)

    class GenericArsFactory:
        def __new__(cls, CP, *args, **kwargs):
            return types.SimpleNamespace(kind="generic_ars", CP=CP, args=args, kwargs=kwargs)

    monkeypatch.setattr(module, "Ars510RadarInterface", GenericArsFactory)
    return module, ToyotaFlags


def _dispatch_fixture(module, flags, *, profile="fused", marker_api=1, marker_profile="fused", supported=True,
                      markers=True, radar_acc=True, unavailable=False, car="TOYOTA_RAV4_TSS2_2022", long_control=True):
    CP = types.SimpleNamespace(carFingerprint=car, flags=int(flags.RADAR_ACC) if radar_acc else 0,
                               radarUnavailable=unavailable, openpilotLongitudinalControl=long_control,
                               pcmCruise=True, selected_control="unchanged")

    class ForkFactory:
        def __new__(cls, CP, *args, **kwargs):
            return types.SimpleNamespace(kind="fork", CP=CP, args=args, kwargs=kwargs)

    if markers:
        ForkFactory.ARS510_CARROT_API = marker_api
        ForkFactory.ARS510_CARROT_PROFILE = marker_profile
        ForkFactory.supports_ars510 = staticmethod(lambda CP: supported)

    class CarInterface:
        RadarInterface = ForkFactory

        @staticmethod
        def _get_params(ret, candidate, fingerprint, car_fw, *, alpha_long=False):
            ret.called = (candidate, fingerprint, car_fw, alpha_long)
            return ret

    module.PROFILE = module.PROFILES[profile]
    return CP, module.hook_car_interface(CarInterface), ForkFactory


@pytest.mark.parametrize("profile, expected", [("fused", "fork"), ("acc", "generic_ars"),
                                               ("raw", "generic_ars"), ("openpilot", "generic_ars"),
                                               ("colored", "generic_ars")])
def test_native_dispatch_is_limited_to_fused(dispatch_module, profile, expected):
    module, flags = dispatch_module
    CP, CI, _ = _dispatch_fixture(module, flags, profile=profile)
    before = vars(CP).copy()
    result = CI.RadarInterface(CP, "extra_constructor", option="preserved")
    assert result.kind == expected
    assert result.CP is CP and result.args == ("extra_constructor",) and result.kwargs == {"option": "preserved"}
    assert vars(CP) == before


@pytest.mark.parametrize("options", [{"markers": False}, {"marker_api": 0}, {"marker_api": 2},
                                      {"marker_api": "1"}, {"marker_api": None}, {"marker_api": True},
                                      {"marker_api": 1.0}, {"marker_profile": "acc"},
                                      {"marker_profile": None}, {"supported": False}])
def test_incompatible_native_markers_keep_generic_ars(dispatch_module, options):
    module, flags = dispatch_module
    CP, CI, _ = _dispatch_fixture(module, flags, **options)
    before = vars(CP).copy()
    assert CI.RadarInterface(CP).kind == "generic_ars"
    assert vars(CP) == before


def test_noncallable_native_support_keeps_generic_ars(dispatch_module):
    module, flags = dispatch_module
    CP, CI, factory = _dispatch_fixture(module, flags)
    factory.supports_ars510 = True
    assert CI.RadarInterface(CP).kind == "generic_ars"


@pytest.mark.parametrize("options", [{"radar_acc": False}, {"unavailable": True},
                                      {"car": "TOYOTA_CHR_TSS2"}])
def test_unsupported_native_model_uses_original_decision(dispatch_module, options):
    module, flags = dispatch_module
    CP, CI, _ = _dispatch_fixture(module, flags, supported=False, **options)
    before = vars(CP).copy()
    expected = "generic_ars" if options.get("car") == "TOYOTA_CHR_TSS2" else "fork"
    assert CI.RadarInterface(CP).kind == expected
    assert vars(CP) == before


@pytest.mark.parametrize("long_control", [False, True])
def test_native_dispatch_preserves_stock_and_direct_control_values(dispatch_module, long_control):
    module, flags = dispatch_module
    CP, CI, _ = _dispatch_fixture(module, flags, long_control=long_control, unavailable=True)
    before = vars(CP).copy()
    assert CI.RadarInterface(CP).kind == "fork"
    assert vars(CP) == before


def test_original_get_params_and_hook_idempotence_are_preserved(dispatch_module):
    module, flags = dispatch_module
    CP, CI, _ = _dispatch_fixture(module, flags, unavailable=True, long_control=False)
    selected = {key: getattr(CP, key) for key in ("flags", "openpilotLongitudinalControl", "pcmCruise", "selected_control")}
    fingerprint, firmware = {1: {}}, []
    assert CI._get_params(CP, CP.carFingerprint, fingerprint, firmware, alpha_long=False) is CP
    assert CP.called == (CP.carFingerprint, fingerprint, firmware, False)
    assert CP.radarUnavailable is False  # 원형의 지원 모델 감지 정책이며 제어 설정은 아니다.
    assert {key: getattr(CP, key) for key in selected} == selected
    wrapped_factory = CI.RadarInterface
    assert module.hook_car_interface(CI) is CI and CI.RadarInterface is wrapped_factory


def _installer_fixture(tmp_path, *, native=True, source=None):
    root = tmp_path / "opendbc_repo"
    toyota = root / "opendbc/car/toyota"
    toyota.mkdir(parents=True)
    (root / "opendbc/dbc").mkdir()
    (root / "opendbc/dbc/ars510_radar_bus.dbc").write_text("old Cabana fixture\n")
    original = "class CarInterface:\n  pass\n"
    (toyota / "interface.py").write_text(original)
    if native:
        source = source or (
            "raise AssertionError('installer must not import a fork')\n"
            "class RadarInterface:\n"
            "  ARS510_CARROT_API = 1\n"
            "  ARS510_CARROT_PROFILE = 'fused'\n"
            "  supports_ars510 = staticmethod(lambda CP: True)\n")
        (toyota / "radar_interface.py").write_text(source)
        (toyota / "ars510_carrot.py").write_text(
            "from opendbc.car.toyota.ars510.interface import FUSED_CONFIG\n")
        shutil.copytree(REPO / "ars510", toyota / "ars510", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(REPO / "LICENSE", toyota / "ars510/LICENSE")
        (toyota / "ars510/fork_notes.txt").write_text("fork-owned extra resource\n")
    return root, toyota, original


def _tree_bytes(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def _run_installer(root, *args):
    return subprocess.run([sys.executable, str(REPO / "openpilot/install.py"), str(root), *args],
                          cwd=REPO, capture_output=True, text=True)


@pytest.mark.parametrize("profile", ["fused", "acc", "raw"])
def test_native_package_survives_install_check_uninstall(tmp_path, profile):
    root, toyota, original = _installer_fixture(tmp_path)
    package_before = _tree_bytes(toyota / "ars510")
    native_before = {name: (toyota / name).read_bytes() for name in ("radar_interface.py", "ars510_carrot.py")}
    installed = _run_installer(root, "--profile", profile)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert "preserved fork-owned native decoder package (compatible)" in installed.stdout
    assert _tree_bytes(toyota / "ars510") == package_before
    checked = _run_installer(root, "--check")
    assert checked.returncode == 0 and "fork-owned (compatible)" in checked.stdout
    assert "installed files: match this checkout" in checked.stdout
    removed = _run_installer(root, "--uninstall")
    assert removed.returncode == 0 and "preserved fork-owned" in removed.stdout
    assert _tree_bytes(toyota / "ars510") == package_before
    assert {name: (toyota / name).read_bytes() for name in native_before} == native_before
    assert (toyota / "interface.py").read_text() == original
    assert not (toyota / "ars510_radar_interface.py").exists()


@pytest.mark.parametrize("mismatch", ["changed", "extra_python", "missing"])
def test_native_incompatible_package_refuses_before_any_mutation(tmp_path, mismatch):
    root, toyota, _ = _installer_fixture(tmp_path)
    if mismatch == "changed":
        (toyota / "ars510/interface.py").write_text("# different native version\n")
    elif mismatch == "extra_python":
        (toyota / "ars510/native_extension.py").write_text("# fork version\n")
    else:
        shutil.rmtree(toyota / "ars510")
    before = _tree_bytes(root)
    installed = _run_installer(root, "--profile", "fused")
    assert installed.returncode == 2 and "fork-owned" in installed.stderr and "checkout unchanged" in installed.stderr
    assert _tree_bytes(root) == before
    checked = _run_installer(root, "--check")
    assert checked.returncode == 2 and "fork-owned" in checked.stdout
    assert _tree_bytes(root) == before


def test_native_uninstall_keeps_a_different_fork_version(tmp_path):
    root, toyota, _ = _installer_fixture(tmp_path)
    assert _run_installer(root, "--profile", "fused").returncode == 0
    (toyota / "ars510/interface.py").write_text("# updated by the fork, not the external installer\n")
    protected = _tree_bytes(toyota / "ars510")
    result = _run_installer(root, "--uninstall")
    assert result.returncode == 0 and "preserved fork-owned native decoder package (different)" in result.stdout
    assert _tree_bytes(toyota / "ars510") == protected


@pytest.mark.parametrize("broken_contract", [False, True])
def test_native_check_ends_with_alignment_or_contract_review(tmp_path, broken_contract):
    root, toyota, _ = _installer_fixture(tmp_path)
    assert _run_installer(root, "--profile", "fused").returncode == 0
    (toyota / "ars510/interface.py").write_text("# a different fork-owned version\n")
    if broken_contract:
        path = toyota / "radar_interface.py"
        path.write_text(path.read_text().replace("ARS510_CARROT_API = 1", "ARS510_CARROT_API = 2"))
    before = _tree_bytes(root)
    result = _run_installer(root, "--check")
    assert result.returncode == 2 and "run install.py again" not in result.stdout
    last = result.stdout.splitlines()[-1]
    assert ("native contract review required" if broken_contract else "native decoder alignment required") in last
    assert _tree_bytes(root) == before


@pytest.mark.parametrize("source", [
    "class RadarInterface:\n  ARS510_CARROT_API = 2\n  ARS510_CARROT_PROFILE = 'fused'\n  supports_ars510 = staticmethod(lambda CP: True)\n",
    "class RadarInterface:\n  ARS510_CARROT_API = 1\n  ARS510_CARROT_PROFILE = 'raw'\n  supports_ars510 = staticmethod(lambda CP: True)\n",
    "class RadarInterface:\n  ARS510_CARROT_API = int('1')\n  ARS510_CARROT_PROFILE = 'fused'\n  supports_ars510 = staticmethod(lambda CP: True)\n",
    "class RadarInterface:\n  ARS510_CARROT_API = True\n  ARS510_CARROT_PROFILE = 'fused'\n  supports_ars510 = staticmethod(lambda CP: True)\n",
    "class RadarInterface:\n  ARS510_CARROT_API = 1\n  ARS510_CARROT_PROFILE = 'fused'\n  supports_ars510 = None\n",
    "class RadarInterface:\n  ARS510_CARROT_API = 1\n  ARS510_CARROT_API = 1\n  ARS510_CARROT_PROFILE = 'fused'\n  supports_ars510 = staticmethod(lambda CP: True)\n",
    "class RadarInterface(:\n  ARS510_CARROT_API = 1\n",
])
def test_ambiguous_native_contract_never_mutates_the_checkout(tmp_path, source):
    root, _, _ = _installer_fixture(tmp_path, source=source)
    before = _tree_bytes(root)
    for args in [("--check",), ("--profile", "fused"), ("--uninstall",)]:
        result = _run_installer(root, *args)
        assert result.returncode == 2 and "ambiguous" in result.stdout + result.stderr
        assert _tree_bytes(root) == before


def test_vanilla_installer_still_owns_and_removes_its_package(tmp_path):
    root, toyota, original = _installer_fixture(tmp_path, native=False)
    assert _run_installer(root, "--profile", "fused").returncode == 0
    assert (toyota / "ars510/interface.py").exists()
    (toyota / "ars510/interface.py").write_text("# stale external version\n")
    checked = _run_installer(root, "--check")
    assert checked.returncode == 0 and "differ from this checkout (package)" in checked.stdout
    assert _run_installer(root, "--uninstall").returncode == 0
    assert not (toyota / "ars510").exists() and (toyota / "interface.py").read_text() == original
