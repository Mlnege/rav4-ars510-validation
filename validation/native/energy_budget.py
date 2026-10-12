"""롱컨 활성 가정에서 운동에너지 감속량을 계산한다. 실제 회생량은 측정하지 않는다."""
import argparse
import csv
import json
import math
from pathlib import Path

from offline_io import prepare
prepare()
from opendbc.car import gen_empty_fingerprint
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.values import CAR


def kinetic_loss_wh(mass_kg,initial_kph,final_kph):
    if not all(math.isfinite(v) for v in (mass_kg,initial_kph,final_kph)) or mass_kg<=0 or min(initial_kph,final_kph)<0:
        raise ValueError("질량·속도 입력이 유효하지 않습니다")
    return max(0.,.5*mass_kg*((initial_kph/3.6)**2-(final_kph/3.6)**2)/3600.)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--long-active',action='store_true',required=True)
    parser.add_argument('--traces',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mass-kg',type=float)
    args=parser.parse_args()
    cp=CarInterface.get_params(CAR.TOYOTA_RAV4_TSS2_2022,gen_empty_fingerprint(),[],True,False,False)
    mass=float(cp.mass) if args.mass_kg is None else args.mass_kg
    summary=json.loads((args.traces/'summary.json').read_text())
    result={'long_active_assumption':True,'control_authority_assumption':True,
            'long_active_flag_is_assumption_not_vehicle_measurement':True,
            'mass_kg':mass,'mass_source':'기준CarParams질량(실차계근값아님)' if args.mass_kg is None else '사용자지정가정값',
            'factory_hybrid_flag':bool(cp.flags & 1),'factory_longitudinal_delay_s':cp.longitudinalActuatorDelay,
            'physical_energy_recovery_Wh':None,'regen_hardware_filter_effect':'unverified',
            'scope':'평지·고정질량·평동운동에너지만;회전체·구배·배터리수용전력·엔진제동·마찰·공기저항·구름저항미분리',
            'illustrative_speed_changes':[],'native_simulation_traces':[]}
    for initial,final in ((30.,0.),(50.,0.),(80.,0.),(100.,0.),(100.,50.)):
        energy=kinetic_loss_wh(mass,initial,final)
        result['illustrative_speed_changes'].append({'initial_kph':initial,'final_kph':final,
            'kinetic_loss_Wh':energy,'kinetic_component_perfect_recovery_Wh':energy,
            'actual_regen_Wh':None})
    for case in summary:
        if case['name'] not in ('case_001','case_002','case_003'):
            continue
        with (args.traces/(case['name']+'.csv')).open() as stream:
            rows=list(csv.DictReader(stream))
        valid=[]
        for row in rows:
            if case.get('first_geometric_overlap_s') is not None and float(row['t_s'])>=case['first_geometric_overlap_s']:
                break
            valid.append(row)
        lost_joule=0.
        for before,after in zip(valid,valid[1:]):
            initial,final=float(before['ego_v_mps']),float(after['ego_v_mps'])
            lost_joule+=max(0.,.5*mass*(initial*initial-final*final))
        peak=max((max(0.,-mass*float(row['ego_a_mps2'])*float(row['ego_v_mps'])/1000.) for row in valid),default=0.)
        result['native_simulation_traces'].append({'name':case['name'],'input':case['navigation_source'] if not case['lead'] else '합성선행차급감속',
            'kinetic_loss_during_decelerations_Wh':lost_joule/3600.,'peak_assumed_deceleration_power_kW':peak,
            'actual_regen_Wh':None,'battery_acceptance_power_kW':None,'post_contact_rows_excluded':len(valid)!=len(rows)})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
