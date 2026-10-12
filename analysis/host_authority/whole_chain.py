"""실제 호스트 권한 판정 메서드를 같은 메모리 메시지 흐름에 연결한다."""
from collections import Counter
import os
import time

from whole_io import MemoryBus, memory_messaging, MemoryConfiguration, Clock, car, log, SOURCE
from offline_io import repo_defaults


class Chain:
  def __init__(self, clock, *, profile='default'):
    os.chdir(SOURCE)
    MemoryConfiguration.values = repo_defaults()
    MemoryConfiguration.bytes_values = {}
    if profile=='user_requested':
      # 사용자 요청값의 메모리 실험만 수행한다. 운영 설정/CP flags는 변경하지 않는다.
      MemoryConfiguration.values.update(SpeedFromPCM='0',LongActuatorDelay='20',AlphaLongitudinalEnabled='1')
    self.profile=profile
    self.bus, self.clock = MemoryBus(), clock
    self.messaging = memory_messaging(self.bus)
    from whole_objects import initialise
    from whole_inputs import VehiclePermissionInput, event, EXTERNAL_SERVICES, SERVICE_LIST
    from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
    from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
    self.event, self.external_services, self.service_list = event, EXTERNAL_SERVICES, SERVICE_LIST
    self.cp, self.sd, self.controls, self.card, self.physical = initialise(self.messaging)
    self.configuration={key:MemoryConfiguration().get(key).decode() if MemoryConfiguration().get(key) is not None else None
                        for key in ('SpeedFromPCM','LongActuatorDelay','AlphaLongitudinalEnabled',
                                    'EnableRadarTracks','SignalAssistMode','NNFF')}
    self.permission = VehiclePermissionInput(self.cp)
    self.planner_sm = self.messaging.SubMaster(['carControl','carState','controlsState','liveParameters','radarState',
      'liveTracks','modelV2','selfdriveState','carrotMan','livePose'], poll='modelV2', ignore_avg_freq=['radarState'])
    self.planner_pm = self.messaging.PubMaster(['longitudinalPlan'])
    self.planner = LongitudinalPlanner(self.cp, init_v=15.)
    self.carrot = CarrotPlanner()
    self.next_emission = dict.fromkeys(self.external_services, clock.now)
    self.rows = []
    self.index = 0
    self.cs = None
    self.init_snapshot = {'initialized': self.sd.initialized, 'enabled': self.sd.enabled, 'active': self.sd.active,
                          'card_initialized_prev': self.card.initialized_prev}
    assert not any(self.init_snapshot.values())
    self.card.state_update = self.state_input_io

  def state_input_io(self):
    self.card.sm.update(0)
    self.card.card_diag_recv_ns = round(self.clock.now*1e9)
    self.card.card_diag_stage_current = dict.fromkeys(self.card.card_diag_stage_names, 0)
    return self.cs

  def step(self, *, engaged=True, available=True, gas=False, brake=False, cancel=False,
           model_age=0., delayed_header=False, freeze_model=False, freeze_plan=False, model_drop=0.):
    now = self.clock.now
    self.permission.update(now, engaged=engaged, gas=gas, brake=brake)
    cs_event = self.event(self.messaging,'carState',now=now,cp=self.cp,permission=self.permission,
                     engaged=engaged,available=available,gas=gas,brake=brake,cancel=cancel)
    self.cs = cs_event.carState.as_reader()
    for service in self.external_services:
      if service == 'carState' or (service == 'modelV2' and freeze_model):
        continue
      frequency = self.service_list[service].frequency
      due = self.index == 0 if frequency <= 0 else now+1e-8 >= self.next_emission[service]
      if due:
        # 늦은 원본 헤더와 새 헤더/오래된 내용의 경우를 분리한다.
        value = self.event(self.messaging,service,now=now,cp=self.cp,permission=self.permission,
          model_age=model_age if service == 'modelV2' else 0.,model_drop=model_drop,
          header=(now-model_age if service=='modelV2' and delayed_header else None))
        self.bus.emit(service,value)
        if frequency>0:
          # 전체 호스트 중단 후 도착한 자료를 가짜 과거100Hz burst로 만들지 않는다.
          self.next_emission[service] = now+1/frequency
    before_apply = len(self.physical.apply_calls)
    self.card.step()
    self.card.rk.monitor_time()
    if self.planner_sm.sock['modelV2'].queue:
      self.planner_sm.update(0)
      if not freeze_plan:
        self.planner.update(self.planner_sm,self.carrot)
        self.planner.publish(self.planner_sm,self.planner_pm,self.carrot)
    self.sd.step()
    self.sd.rk.monitor_time()
    self.controls.update()
    cc,lac = self.controls.state_control()
    self.controls.publish(cc,lac)
    names = {value:key for key,value in log.OnroadEvent.EventName.schema.enumerants.items()}
    states = {value:key for key,value in log.SelfdriveState.OpenpilotState.schema.enumerants.items()}
    row = {'time':now,'frame':self.index,'initialized':self.sd.initialized,'state':states[int(self.sd.state_machine.state)],
      'enabled':self.sd.enabled,'active':self.sd.active,'longActive':bool(cc.longActive),'latActive':bool(cc.latActive),
      'accel':float(cc.actuators.accel),'soft_disable_timer':self.sd.state_machine.soft_disable_timer,
      'events':[names[int(value)] for value in self.sd.events.names],
      'card_applied_this_tick':len(self.physical.apply_calls)>before_apply,
      'card_latest_longActive':self.physical.apply_calls[-1]['longActive'] if self.physical.apply_calls else None,
      'card_initialized_prev':self.card.initialized_prev,'init_io_sink_calls':self.physical.init_io_sink_calls,
      'controlsReady_memory':MemoryConfiguration().get_bool('ControlsReady'),
      'c_controlsAllowed':self.permission.allowed(),'c_rx_invalid':self.permission.invalid(),
      'sd_lagging':self.sd.rk.lagging,'sd_all_checks':self.sd.sm.all_checks(),
      'producer_freeze_model':freeze_model,'producer_freeze_plan':freeze_plan,
      'acquisition_age':now-self.sd.sm['modelV2'].timestampEof*1e-9,
      'model_header_age':now-self.sd.sm.logMonoTime['modelV2']*1e-9,
      'model_receive_age':now-self.sd.sm.recv_time['modelV2'],
      'plan_header_age':now-self.controls.sm.logMonoTime['longitudinalPlan']*1e-9,
      'plan_receive_age':now-self.controls.sm.recv_time['longitudinalPlan'],
      'plan_processing_delay':float(self.controls.sm['longitudinalPlan'].processingDelay),
      'plan_model_header_age':now-self.controls.sm['longitudinalPlan'].modelMonoTime*1e-9,
      'plan_valid':self.controls.sm.valid['longitudinalPlan'],
      'model_alive':self.sd.sm.alive['modelV2'],'plan_alive':self.sd.sm.alive['longitudinalPlan'],
      'cc_alive_at_card':self.card.sm.alive['carControl'],'cc_valid_at_card':self.card.sm.valid['carControl'],
      'cc_freq_at_card':self.card.sm.freq_ok['carControl'],'model_drop':model_drop}
    self.rows.append(row)
    self.index+=1
    return row

  def warm(self):
    start = self.clock.now
    for index in range(350):
      self.clock.now=start+index*.01
      self.step(engaged=index>=200,available=index>=150)
    assert self.sd.initialized and self.sd.enabled and self.rows[-1]['longActive'], '원형 정상 enable 실패'
    assert self.physical.init_io_sink_calls==1 and not self.physical.actual_init_executed
    return self.rows[-1]
