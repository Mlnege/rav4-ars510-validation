"""합성 입력 진단의 실제 관찰값에서 ACC 추가 관측 영향만 그린다."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

font=Path('/mnt/c/Windows/Fonts/malgun.ttf')
if font.exists():
    font_manager.fontManager.addfont(str(font))
    plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
plt.rcParams['axes.unicode_minus']=False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    full=json.loads((args.input/'full_delay_0.00.json').read_text())
    missing=json.loads((args.input/'missing_delay_0.00.json').read_text())
    fig,axis=plt.subplots(2,1,figsize=(11,7),layout='constrained')
    for data,label,color in ((full,'ACC 보조 관측 있음','#2563eb'),(missing,'ACC 보조 관측 없음','#dc2626')):
        records=data['records']
        times=[r['generation_time_s'] for r in records]
        filtered=[r['filter']['fused_speed_mps'] for r in records]
        axis[0].plot(times,filtered,color=color,label=label)
        distances=[r['fused_internal_range_m'] for r in records]
        axis[1].plot(times,distances,color=color,label=label+' / filtered 거리')
        if data['first_contact_time_s'] is not None:
            for a in axis:
                a.axvline(data['first_contact_time_s'],color=color,linestyle=':',alpha=.5)
    records=full['records']
    times=[r['generation_time_s'] for r in records]
    axis[0].plot(times,[r['truth_at_generation']['lead_speed_mps'] for r in records],color='black',linestyle='--',label='합성 입력의 기준 속도')
    axis[0].plot(times,[r['filter']['raw_ground_scaled_mps'] for r in records],color='gray',alpha=.5,label='0x80 해석 속도')
    for a in axis:
        a.set_xlim(5,15)
        a.set_xlabel('합성 패킷 생성 시각 (초)')
        a.grid(alpha=.2)
        a.legend(fontsize=9)
    axis[0].set_ylabel('선행차 속도 (m/s)')
    axis[1].set_ylabel('각 폐루프의 filtered 거리 (m)')
    axis[1].text(.02,.04,'거리 그래프는 서로 다른 차량 응답의 두 폐루프입니다.\n빨간 세로선: 누락 조건의 가정 거리 0 도달',transform=axis[1].transAxes,fontsize=9)
    fig.suptitle('ACC 보조 관측 누락 조건: raw 해석 정상 이후 filtered 속도 지연\n합성 슬롯 불확실성47 고정 / CHECK_BYTE 미검증 / 실제 ECU·차량 검증 아님',fontsize=13)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.out,dpi=150)
    plt.close(fig)


if __name__=='__main__':
    main()
