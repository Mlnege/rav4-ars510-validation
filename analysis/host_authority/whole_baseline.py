"""비활성부터 원형 정상 초기화/PCM enable을 우선 확인하는 권한 연결 검사."""
from collections import Counter
import contextlib
from datetime import datetime, UTC
import io
import json
import os
from pathlib import Path
import sys

from whole_io import WORK, SOURCE, MemoryBus, memory_messaging, Clock, clock_inputs, MemoryConfiguration, source_unchanged, SOURCE_HASHES


def main():
  os.chdir(SOURCE)
  bus, clock = MemoryBus(), Clock()
  messaging = memory_messaging(bus)
  # 원형 판정 모듈은 메모리 입출력 구성 이후에 가져온다.
  from whole_objects import initialise
  from whole_inputs import VehiclePermissionInput, event, EXTERNAL_SERVICES, SERVICE_LIST
  from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
  from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
  from openpilot.cereal import car, log
  from openpilot.common.swaglog import cloudlog
  with clock_inputs(clock):
    cp, sd, controls, card, physical = initialise(messaging)
    assert not sd.initialized and not sd.enabled and not sd.active and not card.initialized_prev
    permission = VehiclePermissionInput(cp)
    planner_sm = messaging.SubMaster(['carControl', 'carState', 'controlsState', 'liveParameters', 'radarState',
                                     'liveTracks', 'modelV2', 'selfdriveState', 'carrotMan', 'livePose'], poll='modelV2',
                                    ignore_avg_freq=['radarState'])
    planner_pm = messaging.PubMaster(['longitudinalPlan'])
    planner, carrot = LongitudinalPlanner(cp, init_v=15.), CarrotPlanner()
    next_emission = dict.fromkeys(EXTERNAL_SERVICES, 100.)
    initial = {"sd_initialized": sd.initialized, "sd_enabled": sd.enabled, "sd_active": sd.active,
               "card_initialized_prev": card.initialized_prev}
    rows, events_seen = [], Counter()
    cs = None

    def state_input():
      card.sm.update(0)
      card.card_diag_recv_ns = round(clock.now*1e9)
      card.card_diag_stage_current = dict.fromkeys(card.card_diag_stage_names, 0)
      # 이 경계는 차에서 얻은 carState의 합성 입력이다. 상태 추론/판정은 그 다음 원형에서 실행한다.
      return cs

    card.state_update = state_input
    for index in range(700):
      clock.now = 100.+index*.01
      engaged = index >= 200
      available = index >= 150
      permission.update(clock.now, engaged=engaged)
      car_input = event(messaging, 'carState', now=clock.now, cp=cp, permission=permission,
                        engaged=engaged, available=available)
      cs = car_input.carState.as_reader()
      for service in EXTERNAL_SERVICES:
        if service == 'carState':
          continue
        frequency = SERVICE_LIST[service].frequency
        if frequency <= 0:
          due = index == 0
        else:
          due = clock.now+1e-8 >= next_emission[service]
        if due:
          datum = event(messaging, service, now=clock.now, cp=cp, permission=permission)
          bus.emit(service, datum)
          if frequency > 0:
            next_emission[service] += 1/frequency
      # card가 생성하는 carState와 carOutput을 원형 발행으로 다른 소비자에 전달한다.
      card.step()
      card.rk.monitor_time()
      # 원형 Toyota plannerd는 modelV2 poll로 20Hz에 깨어난다.
      # 메모리 poller가 실제 wait를 하지 않으므로 도착이 없을 때 호출하지 않는다.
      if planner_sm.sock['modelV2'].queue:
        planner_sm.update(0)
        planner.update(planner_sm, carrot)
        planner.publish(planner_sm, planner_pm, carrot)
      sd.step()
      sd.rk.monitor_time()
      controls.update()
      cc, lac_log = controls.state_control()
      controls.publish(cc, lac_log)
      events_seen.update(log.OnroadEvent.EventName.schema.enumerants.keys() if False else
                         [str(x) for x in sd.events.names])
      row = {"time_s": clock.now, "frame": index, "sd_initialized": sd.initialized,
             "sd_enabled": sd.enabled, "sd_active": sd.active, "state": int(sd.state_machine.state),
             "longActive": bool(cc.longActive), "latActive": bool(cc.latActive),
             "soft_disable_timer": sd.state_machine.soft_disable_timer,
             "event_ids": list(sd.events.names), "card_apply_calls": len(physical.apply_calls),
             "card_initialized_prev": card.initialized_prev, "init_io_sink_calls": physical.init_io_sink_calls,
             "c_controls_allowed": permission.allowed(), "c_rx_invalid": permission.invalid(),
             "selfdrive_checks": sd.sm.all_checks(), "selfdrive_invalid": [s for s in sd.sm.services if not sd.sm.valid[s]],
             "selfdrive_not_alive": [s for s in sd.sm.services if not sd.sm.alive[s]],
             "selfdrive_not_freq": [s for s in sd.sm.services if sd.sm._check_avg_freq(s) and not sd.sm.freq_ok[s]]}
      rows.append(row)
    result = {"recorded_utc": datetime.now(UTC).isoformat(), "initial": initial, "rows": rows,
              "source_hashes": SOURCE_HASHES, "source_unchanged": source_unchanged(),
              "normal_enabled_observed": any(row['sd_enabled'] and row['longActive'] for row in rows),
              "original_initialization_observed": any(row['sd_initialized'] for row in rows),
              "actual_init_executed": False, "init_io_sink_calls": physical.init_io_sink_calls,
              "actual_vehicle_can_sent": False, "independent_mcu_heartbeat_verified": False,
              "shortcut_controls_true_calls": permission.shortcut_controls_true_calls,
              "cp": {"fingerprint": str(cp.carFingerprint), "flags": int(cp.flags), "pcmCruise": bool(cp.pcmCruise),
                     "alphaLongitudinalAvailable": bool(cp.alphaLongitudinalAvailable),
                     "openpilotLongitudinalControl": bool(cp.openpilotLongitudinalControl),
                     "radarUnavailable": bool(cp.radarUnavailable), "alternativeExperience": int(cp.alternativeExperience)},
              "scope_ko": "실제 data_sample/update_events/StateMachine/state_control/publish/card step/controls_update 실행. carState 수집/파싱 및 물리 CI 초기화/전송은 IO fixture. 상위 enabled/active/longActive 강제 입력 없음. 실물 준비 미실행은 사전 CAN CRC 검증과 무관하다."}
    WORK.mkdir(exist_ok=True)
    (WORK/'whole_baseline_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('normal_enabled_observed','original_initialization_observed','init_io_sink_calls','source_unchanged')}, ensure_ascii=False))


if __name__ == '__main__':
  main()
