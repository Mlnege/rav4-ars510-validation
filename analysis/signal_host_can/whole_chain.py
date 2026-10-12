"""실제 호스트 권한 판정 메서드를 같은 메모리 메시지 흐름에 연결한다."""
from collections import Counter
import os
import time

from whole_io import MemoryBus, memory_messaging, MemoryConfiguration, Clock, car, log, SOURCE
from offline_io import repo_defaults


class Chain:
  def __init__(self, clock, *, profile='user_requested',initial_speed=0.):
    os.chdir(SOURCE)
    MemoryConfiguration.values = repo_defaults()
    MemoryConfiguration.bytes_values = {}
    if profile=='user_requested':
      # 사용자 요청값의 메모리 실험만 수행한다. 운영 설정/CP flags는 변경하지 않는다.
      MemoryConfiguration.values.update(SpeedFromPCM='0',LongActuatorDelay='20',AlphaLongitudinalEnabled='1')
    MemoryConfiguration.values['SignalAssistMode']='2'
    self.profile=profile
    self.bus, self.clock = MemoryBus(), clock
    self.messaging = memory_messaging(self.bus)
    from signal_io import install_io,ObservationProducer,RuntimeObservation
    install_io()
    from whole_objects import initialise
    from whole_inputs import VehiclePermissionInput, event, EXTERNAL_SERVICES, SERVICE_LIST
    from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
    from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
    from openpilot.selfdrive.carrot.curve_speed import VisionCurveSpeed, curve_speed
    self.event, self.external_services, self.service_list = event, EXTERNAL_SERVICES, SERVICE_LIST
    self.cp, self.sd, self.controls, self.card, self.physical = initialise(self.messaging)
    self.configuration={key:MemoryConfiguration().get(key).decode() if MemoryConfiguration().get(key) is not None else None
                        for key in ('SpeedFromPCM','LongActuatorDelay','AlphaLongitudinalEnabled',
                                    'EnableRadarTracks','SignalAssistMode','NNFF')}
    self.permission = VehiclePermissionInput(self.cp)
    self.physical.tx_permission = self.permission
    self.planner_sm = self.messaging.SubMaster(['carControl','carState','controlsState','liveParameters','radarState',
      'liveTracks','modelV2','selfdriveState','carrotMan','livePose'], poll='modelV2', ignore_avg_freq=['radarState'])
    self.planner_pm = self.messaging.PubMaster(['longitudinalPlan'])
    self.planner = LongitudinalPlanner(self.cp, init_v=initial_speed)
    self.carrot = CarrotPlanner()
    self.observations=ObservationProducer(self.messaging)
    self.signal_trace=RuntimeObservation()
    self.signal_trace.attach(self.carrot._start_runtime,'start')
    self.signal_trace.attach(self.carrot._prepare_runtime,'prepare')
    self.curve_filter, self.curve_function = VisionCurveSpeed(), curve_speed
    self.curve_result = None
    self.curve_cap_kph = None
    self.navigation_emitted_kph = None
    self.next_emission = dict.fromkeys(self.external_services, clock.now)
    self.rows = []
    self.index = 0
    self.next_signal_emission=clock.now
    self.cs = None
    self.init_snapshot = {'initialized': self.sd.initialized, 'enabled': self.sd.enabled, 'active': self.sd.active,
                          'card_initialized_prev': self.card.initialized_prev}
    assert not any(self.init_snapshot.values())

  def step(self, *, engaged=True, available=True, gas=False, brake=False, cancel=False,
           model_age=0., delayed_header=False, freeze_model=False, freeze_plan=False, model_drop=0.,
           pcm_kph=75., map_cap_kph=None, curve_yaw=None, freeze_navigation=False,
           speed=0.,signal_color='red',signal_latency=.1,signal_publish=True,signal_order='before',
           signal_session='synthetic_whole_signal',signal_provenance=True,can_valid=True,freeze_services=()):
    now = self.clock.now
    self.permission.update(now, engaged=engaged, gas=gas, brake=brake,speed=speed)
    cs_event = self.event(self.messaging,'carState',now=now,cp=self.cp,permission=self.permission,
                     engaged=engaged,available=available,gas=gas,brake=brake,cancel=cancel,speed=speed)
    self.cs = cs_event.carState
    self.cs.canValid=can_valid
    self.cs.cruiseState.speed = self.cs.cruiseState.speedCluster = pcm_kph/3.6
    self.physical.next_state = self.cs
    # 이 이벤트는 수집 시각만 가진다. 실제 차량 프레임/DBC decode를 만들지 않는다.
    self.bus.emit('can', self.messaging.new_message('can', 0, valid=True, logMonoTime=round(now*1e9)))
    for service in self.external_services:
      if service == 'carState' or service in freeze_services or (service == 'modelV2' and freeze_model) or (service=='carrotMan' and freeze_navigation):
        continue
      frequency = self.service_list[service].frequency
      if service == 'carrotMan':
        frequency = 20.
      due = self.index == 0 if frequency <= 0 else now+1e-8 >= self.next_emission[service]
      if due:
        # 늦은 원본 헤더와 새 헤더/오래된 내용의 경우를 분리한다.
        value = self.event(self.messaging,service,now=now,cp=self.cp,permission=self.permission,
          model_age=model_age if service == 'modelV2' else 0.,model_drop=model_drop,
          header=(now-model_age if service=='modelV2' and delayed_header else None),speed=speed)
        if service=='modelV2':
          from signal_io import model_trajectory
          model_trajectory(value.modelV2,self.cs,speed)
        if service == 'modelV2' and curve_yaw is not None:
          # 같은 속도/yaw의 원 궤적을 가진 합성 모델이며 실제 도로 곡률 측정은 아니다.
          import numpy as np
          from openpilot.selfdrive.modeld.constants import ModelConstants
          value.modelV2.orientationRate.z = [curve_yaw]*33
          if curve_yaw:
            angles=np.asarray(ModelConstants.T_IDXS)*curve_yaw
            value.modelV2.position.x = (15./curve_yaw*np.sin(angles)).tolist()
            value.modelV2.position.y = (15./curve_yaw*(1-np.cos(angles))).tolist()
          self.curve_result = self.curve_function(value.modelV2,15.,
            MemoryConfiguration().get_float('AutoCurveSpeedFactor')*.01,
            MemoryConfiguration().get_float('AutoCurveSpeedLowerLimit'),speed_ratio=1.,a_ego=0.)
          self.curve_cap_kph = abs(self.curve_filter.update(self.curve_result,now,model_time=round(now*1e9)))
        if service == 'carrotMan' and (map_cap_kph is not None or curve_yaw is not None):
          caps=[250.]
          if map_cap_kph is not None:
            caps.append(map_cap_kph)
          if curve_yaw is not None:
            caps.append(self.curve_cap_kph)
          # 발행 경계의 desiredSpeed는 합성 I/O. CarrotServ 전체 서버/route 조합은 실행하지 않는다.
          self.navigation_emitted_kph = int(min(caps))
          value.carrotMan.desiredSpeed = self.navigation_emitted_kph
          value.carrotMan.nRoadLimitSpeed = 100
          value.carrotMan.activeCarrot = 2
          if curve_yaw is not None:
            value.carrotMan.vTurnSpeed = int(self.curve_cap_kph)
        if service=='roadCameraState':
          self.observations.road_history.append({'frame_id':int(value.roadCameraState.frameId),
            'timestamp_eof':int(value.roadCameraState.timestampEof),'publisher_header':int(value.logMonoTime),
            'delivery_time':now})
        self.bus.emit(service,value)
        if frequency>0:
          # 전체 호스트 중단 후 도착한 자료를 가짜 과거100Hz burst로 만들지 않는다.
          self.next_emission[service] = now+1/frequency
    before_apply = len(self.physical.apply_calls)
    before_generated = len(self.physical.generated_rows)
    self.card.step()
    self.card.rk.monitor_time()
    plan_updated=False
    signal_due=now+1e-8>=self.next_signal_emission
    if signal_publish and signal_due and signal_order=='before':
      self.observations.publish(now,color=signal_color,latency=signal_latency,session=signal_session,provenance=signal_provenance)
    if self.planner_sm.sock['modelV2'].queue:
      self.planner_sm.update(0)
      if not freeze_plan:
        self.planner.update(self.planner_sm,self.carrot)
        self.planner.publish(self.planner_sm,self.planner_pm,self.carrot)
        plan_updated=True
    if signal_publish and signal_due and signal_order=='after':
      self.observations.publish(now,color=signal_color,latency=signal_latency,session=signal_session,provenance=signal_provenance)
    if signal_due:self.next_signal_emission=now+.05
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
    row.update(pcm_kph=pcm_kph,available=available,engaged=engaged,gas=gas,brake=brake,cancel=cancel,
      cs_vCruise=float(self.card.CS_prev.vCruise),cs_vCruiseCluster=float(self.card.CS_prev.vCruiseCluster),
      cs_activateCruise=int(self.card.CS_prev.activateCruise),cs_latEnabled=bool(self.card.CS_prev.latEnabled),
      cs_logCarrot=str(self.card.CS_prev.logCarrot),helper_vCruise=float(self.card.v_cruise_helper.v_cruise_kph),
      helper_mode=int(self.card.v_cruise_helper.speed_from_pcm),map_cap_kph=map_cap_kph,
      planner_cruise_kph=float(self.planner.v_cruise_kph),carrot_cruise_ms=float(self.carrot.v_cruise),
      plan_aTarget=float(self.controls.sm['longitudinalPlan'].aTarget),
      plan_target_speed=float(self.controls.sm['longitudinalPlan'].speeds[-1]) if self.controls.sm['longitudinalPlan'].speeds else None,
      plan_target_accel=float(self.controls.sm['longitudinalPlan'].accels[-1]) if self.controls.sm['longitudinalPlan'].accels else None,
      ci_update_io_calls=self.physical.update_io_calls,can_packet_count=int(self.card.CS_prev.radarInput.canPacketCount),
      actual_can_frame_count=sum(len(packet[1]) for packet in self.physical.last_can_packets))
    row.update(curve_yaw=curve_yaw,curve_cap_kph=self.curve_cap_kph,navigation_emitted_kph=self.navigation_emitted_kph,
      navigation_age=now-self.planner_sm.recv_time['carrotMan'],freeze_navigation=freeze_navigation,
      configuration_CruiseEcoControl=MemoryConfiguration().get_int('CruiseEcoControl'))
    row.update(c_longitudinal_allowed=bool(self.permission.probe.lib.get_longitudinal_allowed()),
      actual_ci_apply_calls=self.physical.actual_ci_apply_calls,generated_messages=len(self.physical.generated_rows),
      actual_controller_frame=self.physical.actual.CC.frame,
      actual_controller_accel=float(self.physical.actual.CC.accel),
      actual_controller_pid_integral=float(self.physical.actual.CC.long_pid.i))
    row.update(speed=speed,signal_color=signal_color,signal_publish=signal_publish,signal_order=signal_order,
      signal_plan_updated=plan_updated,signal_runtime_start=self.signal_trace.latest.get('start'),
      signal_runtime_prepare=self.signal_trace.latest.get('prepare'),
      signal_last_publication=self.observations.last,
      signal_legacy_assist_present=self.carrot.signal_assist is not None,
      signal_start_hold=bool(self.carrot.start_guard.hold),signal_start_cooldown_until=float(self.carrot.start_guard.cooldown),
      signal_start_box=self.carrot.start_guard.box,signal_start_session=self.carrot.start_guard.session,
      signal_start_pending=self.carrot.start_guard.pending,signal_start_count=self.carrot.start_guard.count,
      signal_start_reason=self.carrot.start_decision.reason,signal_start_released=bool(self.carrot.start_decision.released),
      signal_prepare_active=bool(self.carrot.prepare_decision.active),signal_prepare_reason=self.carrot.prepare_decision.reason,
      signal_prepare_cooldown_until=float(self.carrot.stop_prepare.cooldown),
      plan_should_stop=bool(self.controls.sm['longitudinalPlan'].shouldStop),
      plan_native_solver_status=int(self.planner.mpc.solution_status),
      input_road_frame_id=int(self.sd.sm['roadCameraState'].frameId),
      input_road_eof=int(self.sd.sm['roadCameraState'].timestampEof),
      can_generated_this_tick=self.physical.generated_rows[before_generated:],
      guard_decision_this_tick=plan_updated,input_can_valid=can_valid,freeze_services=list(freeze_services))
    self.rows.append(row)
    self.index+=1
    return row

  def warm(self,*,signal_order='before',speed=0.):
    start = self.clock.now
    for index in range(350):
      self.clock.now=start+index*.01
      self.step(engaged=index>=200,available=index>=150,signal_order=signal_order,speed=speed)
    assert self.sd.initialized and self.sd.enabled and self.rows[-1]['longActive'], '원형 정상 enable 실패'
    assert self.physical.init_io_sink_calls==1 and not self.physical.actual_init_executed
    return self.rows[-1]
