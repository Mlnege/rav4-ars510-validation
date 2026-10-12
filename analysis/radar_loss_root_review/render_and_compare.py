"""동결된 실패·수정 결과를 비교하고 가상 명령 전이 그림을 만든다."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "work/radar_loss_authority_review/run01"
NEW = ROOT / "work/radar_loss_authority_root/final/run01"
OUT = ROOT / "outputs"
cases = json.loads((NEW / "results.json").read_text(encoding="utf-8"))["cases"]
same = []
authority = []
keys = ("state", "enabled", "active", "longActive", "soft_disable_timer", "events",
        "c_controlsAllowed", "c_rx_invalid", "radar_valid", "radar_alive", "radar_frequency_ok")
for case in cases:
  kind = case["kind"]
  old = json.loads((OLD / (kind + "_rows.json")).read_text(encoding="utf-8"))
  new = json.loads((NEW / (kind + "_rows.json")).read_text(encoding="utf-8"))
  differences = sum(any(a[key] != b[key] for key in keys) for a, b in zip(old, new))
  authority.append({"kind": kind, "rows": len(new), "authority_or_event_different_rows": differences})
  if kind in ("healthy_empty", "error_with_valid_true", "can_error"):
    same.append({"kind": kind, "full_rows_same": old == new, "rows": len(new)})
result = {"unchanged_cases": same, "authority_event_comparison": authority,
          "scope_ko": "같은 합성 입력의 행 대조. 실제 차량 로그·수신 시간이나 영상 정확도 대조가 아니다."}
(ROOT / "work/radar_loss_root_review/final_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if not all(row["full_rows_same"] for row in same) or any(row["authority_or_event_different_rows"] for row in authority):
  raise RuntimeError("예상하지 않은 권한/정상 경로 차이가 있습니다")

manifest = json.loads((ROOT / "work/release_repo/validation_manifest.json").read_text(encoding="utf-8"))
with (OUT / "수정파일목록_현재64개.csv").open("w", encoding="utf-8", newline="") as stream:
  writer = csv.writer(stream)
  writer.writerow(("path", "sha256_lf"))
  writer.writerows((row["path"], row["sha256_lf"]) for row in manifest["patched_source_files"])

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties

font_manager.fontManager.addfont("/mnt/c/Windows/Fonts/malgun.ttf")
font = FontProperties(fname="/mnt/c/Windows/Fonts/malgun.ttf")
plt.rcParams["font.family"] = font.get_name()
plt.rcParams["axes.unicode_minus"] = False
old = json.loads((OLD / "temporary_rows.json").read_text(encoding="utf-8"))
new = json.loads((NEW / "temporary_rows.json").read_text(encoding="utf-8"))
origin = new[0]["time"]
t = [row["time"] - origin for row in new]
can = json.loads((ROOT / "work/radar_loss_authority_root/tx_transition/generated_can_rows.json").read_text(encoding="utf-8"))
accel = [row for row in can if row["address"] == 0x343]
can_t = [(row["time_ns"] - round(origin * 1e9)) / 1e9 for row in accel]
fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
axes[0].plot(t, [row["accel"] for row in old], label="기존 제어 계산", color="#c8524a", linewidth=2)
axes[0].plot(t, [row["accel"] for row in new], label="수정 제어 계산", color="#277da1", linewidth=2)
axes[0].plot(t, [row["plan_aTarget"] for row in new], label="수정 계획 목표", color="#4d908e", linestyle="--")
axes[0].set_ylabel("가속 명령 (m/s²)", fontproperties=font)
axes[0].legend(prop=font, loc="upper right")
axes[0].set_title("합성 임시 레이더 오류: 감속 요청 전달 수정", fontproperties=font, fontsize=17)
axes[1].step(can_t, [row["raw_accel_signed"] / 1000 for row in accel], where="post", color="#277da1", label="수정 후 생성 ACC CAN")
axes[1].axvline(.34, color="#43aa8b", linestyle="--", label="첫 음수 CAN 0.34초")
axes[1].set_ylabel("CAN 가속 명령 (m/s²)", fontproperties=font)
axes[1].set_xlabel("오류 입력 후 가상 시간 (초)", fontproperties=font)
axes[1].legend(prop=font, loc="upper right")
for ax in axes:
  ax.axhline(0, color="#888888", linewidth=.8)
  ax.axvline(3., color="#555555", linestyle=":")
  ax.axvspan(0, 3, color="#ececec", alpha=.5, zorder=-1)
  ax.grid(alpha=.2)
axes[1].text(3.03, -.85, "3초 후 longActive 해제", fontproperties=font, fontsize=10)
fig.suptitle("고정 ego 15m/s · 가상 100Hz · 실제 차량 운동/송신 없음", fontproperties=font, fontsize=11)
path = OUT / "감속요청_전달_수정_모의결과.png"
fig.savefig(path, dpi=150)
print(json.dumps({"unchanged_full_cases": len(same), "authority_differences": sum(row["authority_or_event_different_rows"] for row in authority),
                  "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
