"""실제 계산 결과 CSV에서 한국어 그림과 가상 주행 애니메이션을 만든다."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Rectangle
import numpy as np


FONT = Path("/mnt/c/Windows/Fonts/malgun.ttf")
if FONT.is_file():
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(FONT)).get_name()
plt.rcParams["axes.unicode_minus"] = False


def rows(path):
    with path.open() as stream:
        return np.array([list(map(float, row.values())) for row in csv.DictReader(stream)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = json.loads((args.input / "summary.json").read_text())
    chosen = [cases[i] for i in (0,1,2,3)]
    titles = ["정지 상태에서 가속", "코너 제한속도 입력", "지도 제한속도 입력", "선행차 급감속 입력"]
    fig, axes = plt.subplots(4,2,figsize=(13,12),layout="constrained")
    for index, (case,title) in enumerate(zip(chosen,titles)):
        data = rows(args.input/(case["name"]+".csv"))
        axes[index,0].plot(data[:,0],data[:,2]*3.6,label="가상 차량 속도")
        axes[index,0].plot(data[:,0],data[:,7],label="계산한 제한속도",linestyle="--")
        if case["lead"]:
            axes[index,0].plot(data[:,0],data[:,5]*3.6,label="합성 선행차 속도")
            twin = axes[index,1].twinx()
            twin.plot(data[:,0],data[:,6],color="#b45309",label="차간거리",alpha=.6)
            twin.set_ylabel("차간거리 (m)",color="#b45309")
        axes[index,1].plot(data[:,0],data[:,4],label="CAN으로 인코딩한 요청")
        axes[index,1].plot(data[:,0],data[:,3],label="가정한 차량 응답")
        axes[index,0].set_title(title)
        axes[index,0].set_ylabel("속도 (km/h)")
        axes[index,1].set_ylabel("가속도 (m/s²)")
        for axis in axes[index]:
            axis.set_xlabel("모의 시간 (초)")
            axis.grid(alpha=.2)
            axis.legend(fontsize=8,loc="best")
    fig.suptitle("RAV4 종방향 제어: 실제 코드 계산과 가정한 차량 응답\n합성 센서·모델 입력 / PC 오프라인 / 실차 안전성·회생제동 미검증",fontsize=14)
    fig.savefig(args.out/"종방향_계산결과.png",dpi=150)
    plt.close(fig)

    case = chosen[3]
    data = rows(args.input/(case["name"]+".csv"))
    fig, (road, chart) = plt.subplots(2,1,figsize=(11,6),height_ratios=(1,1.4),layout="constrained")
    road.set_xlim(-12, max(100,float(np.max(data[:,6]))+10))
    road.set_ylim(-1,3)
    road.set_yticks([])
    road.set_xlabel("가상 차량 앞쪽 상대 위치 (m)")
    road.axhline(0,color="gray",linestyle="--")
    road.axhline(2,color="gray",linestyle="--")
    ego = Rectangle((-4, .4), 4,1.2,color="#2563eb")
    lead = Rectangle((case["gap"], .4),4,1.2,color="#f97316")
    road.add_patch(ego)
    road.add_patch(lead)
    text = road.text(-9,2.3,"",fontsize=10)
    chart.plot(data[:,0],data[:,2]*3.6,label="가상 차량",color="#2563eb")
    chart.plot(data[:,0],data[:,5]*3.6,label="합성 선행차",color="#f97316")
    cursor = chart.axvline(0,color="gray",linestyle="--")
    chart.set_xlabel("모의 시간 (초)")
    chart.set_ylabel("속도 (km/h)")
    chart.grid(alpha=.2)
    chart.legend()
    fig.suptitle("선행차 급감속 모의주행 — 센서·차량 응답은 가정\n실제 Carrot → native MPC → LongControl → Toyota CAN 계산 사용",fontsize=12)
    selected = np.linspace(0,len(data)-1,180,dtype=int)
    def update(index):
        t,_,speed,accel,command,lead_speed,gap,*_ = data[selected[index]]
        lead.set_x(float(gap))
        cursor.set_xdata([t,t])
        text.set_text(f"{t:4.1f}초 | 차간거리 {gap:.1f}m | 차량 {speed*3.6:.1f}km/h | 요청 {command:.2f}m/s²")
        return lead,cursor,text
    animation = FuncAnimation(fig,update,frames=len(selected),interval=66.7,blit=False)
    animation.save(args.out/"급감속_모의주행.gif",writer=PillowWriter(fps=15),dpi=90)
    plt.close(fig)


if __name__ == "__main__":
    main()
