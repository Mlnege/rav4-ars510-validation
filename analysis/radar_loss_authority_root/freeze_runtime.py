"""기존 native 파일을 보존하고 새 Python 소스와 바이너리 사본을 동결한다."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work/carrotpilot"
PREVIOUS = ROOT / "work/download_e2e/work/native_sim/build_unique"
TARGET = ROOT / "work/native_sim/build_force_decel_frozen"

if TARGET.exists():
  raise RuntimeError("기존 동결 런타임은 덮어쓰지 않습니다")
(TARGET / "c_generated_code").mkdir(parents=True)
files = []
for path in sorted((PREVIOUS / "c_generated_code").iterdir()):
  if not path.is_file() or ".so" not in path.name:
    continue
  target = TARGET / "c_generated_code" / path.name
  before = hashlib.sha256(path.read_bytes()).hexdigest()
  shutil.copyfile(path, target)
  copied = hashlib.sha256(target.read_bytes()).hexdigest()
  after = hashlib.sha256(path.read_bytes()).hexdigest()
  files.append({"name": path.name, "sha256_before": before, "sha256_copy": copied,
                "sha256_after": after, "same": before == copied == after})
mpc = SOURCE / "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py"
shutil.copyfile(mpc, TARGET / "long_mpc.py")
report = {"native_files": files, "native_rebuilt": False, "original_files_modified": False,
          "python_source_sha256": hashlib.sha256(mpc.read_bytes()).hexdigest(),
          "python_copy_sha256": hashlib.sha256((TARGET / "long_mpc.py").read_bytes()).hexdigest()}
(TARGET / "snapshot.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
if len(files) != 6 or not all(row["same"] for row in files):
  raise SystemExit(1)
