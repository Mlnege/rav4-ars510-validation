"""현재 MPC 소스를 byte 동일하게 복사해 새 작업 경로에 실제 C/Cython solver를 만든다."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import sysconfig

from offline_io import BUILD_ROOT, REPO_ROOT, prepare


if (BUILD_ROOT / "native_build.json").exists() or list((BUILD_ROOT / "c_generated_code").glob("*.so*")):
  raise RuntimeError("이미 생성된 native 빌드는 덮어쓰지 않습니다. CARROT_VALIDATION_BUILD에 새 경로를 지정하세요")
prepare()
import acados
os.environ["ACADOS_SOURCE_DIR"] = acados.DIR
os.environ["ACADOS_PYTHON_INTERFACE_PATH"] = acados.TEMPLATE_DIR
os.environ["TERA_PATH"] = acados.TERA_PATH
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
BUILD_ROOT.mkdir(parents=True, exist_ok=True)
source = REPO_ROOT / "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py"
copied = BUILD_ROOT / "long_mpc.py"
shutil.copy2(source, copied)
original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
assert original_sha == hashlib.sha256(copied.read_bytes()).hexdigest()
print("unchanged source SHA256:", original_sha, flush=True)
namespace = runpy.run_path(str(copied), run_name="__main__")
from acados.acados_template import AcadosOcpSolver
generated = BUILD_ROOT / "c_generated_code"
AcadosOcpSolver.build(str(generated), with_cython=False)
# 원형 SConscript와 같이 wheel의 실제 TEMPLATE_DIR에서 Cython을 생성한다.
# acados의 생성 Makefile은 개발 소스 트리 경로를 가정해 wheel에서 찾지 못한다.
subprocess.run([
  str(Path(sys.executable).parent / "cython"), "-o", str(generated / "acados_ocp_solver_pyx.c"),
  "-I", str(generated), "-I", acados.TEMPLATE_DIR,
  str(Path(acados.TEMPLATE_DIR) / "acados_ocp_solver_pyx.pyx"),
], check=True)
import numpy
include = Path(acados.INCLUDE_DIR)
shared_flags = ["-shared", "-fPIC", "-O2", "-DACADOS_WITH_QPOASES", "-Wno-unused", "-Wl,--disable-new-dtags", "-Wl,-rpath,$ORIGIN"]
subprocess.run([
  "gcc", *shared_flags, *(str(path) for path in generated.rglob("*.o")),
  "-o", str(generated / "libacados_ocp_solver_long.so"), "-L" + acados.LIB_DIR,
  "-lacados", "-lhpipm", "-lblasfeo", "-lqpOASES_e", "-lm",
], check=True)
extension = generated / ("acados_ocp_solver_pyx" + sysconfig.get_config_var("EXT_SUFFIX"))
subprocess.run([
  "gcc", *shared_flags, "-I" + acados.INCLUDE_DIR, "-I" + str(include / "acados"),
  "-I" + str(include / "blasfeo/include"), "-I" + str(include / "hpipm/include"),
  "-I" + numpy.get_include(), "-I" + sysconfig.get_path("include"),
  str(generated / "acados_ocp_solver_pyx.c"), "-L" + str(generated), "-lacados_ocp_solver_long",
  "-o", str(extension),
], check=True)
extensions = list((BUILD_ROOT / "c_generated_code").glob("acados_ocp_solver_pyx*.so"))
if not extensions:
  raise RuntimeError("acados build 함수의 반환 여부와 별개로 실제 Cython 확장 생성에 실패했습니다")
for name in ("libacados.so", "libblasfeo.so", "libhpipm.so", "libqpOASES_e.so.3.1"):
  shutil.copy2(Path(acados.LIB_DIR) / name, BUILD_ROOT / "c_generated_code" / name)
manifest = {
  "python": sys.version,
  "source_sha256": original_sha,
  "source_file": str(source),
  "native_files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in (BUILD_ROOT / "c_generated_code").glob("*.so*")},
}
(BUILD_ROOT / "native_build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2), flush=True)
