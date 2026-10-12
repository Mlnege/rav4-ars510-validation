"""동일한 단일 C 상태에 기록 정책 RX와 생성 CAN TX를 연결한다."""
from collections import Counter
import importlib.util

from whole_io import ROOT


path=ROOT/'work/recorded_panda_mode_replay/run.py'
spec=importlib.util.spec_from_file_location('recorded_mode_frozen',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecordedPolicy:
  def __init__(self,origin,phase_us):
    self.origin=origin
    self.clock=module.ClockedProbe(phase_us)
    self.probe=self.clock.probe
    self.counts=Counter()
    self.transitions=[]

  def advance(self,ns):
    self.clock.advance(max(0,(ns-self.origin)//1000))

  def receive_panda(self,event,ns):
    if not event.valid:
      self.counts['invalid_panda_events']+=1
      return
    if len(event.pandaStates)!=1:raise RuntimeError('단일 Panda 범위가 아닙니다')
    p=event.pandaStates[0]
    current=(int(p.safetyModel.raw),int(p.safetyParam))
    alt=int(p.alternativeExperience)
    if current!=self.clock.mode:
      self.clock.set_mode(*current,alt)
      self.transitions.append({'relative_time_s':(ns-self.origin)*1e-9,
          'model':str(p.safetyModel),'param':current[1],'alt':alt})
    elif alt!=self.clock.alt:
      self.clock.lib.set_alternative_experience(alt)
      self.clock.operations['set_alternative_experience']+=1
      self.clock.alt=alt
    else:self.counts['panda_no_reset_samples']+=1
    self.counts['panda_samples']+=1
    self.counts['recorded_controls_true']+=bool(p.controlsAllowed)
    self.counts['recorded_rx_invalid_true']+=bool(p.safetyRxChecksInvalid)

  def receive_can(self,frames):
    for addr,data,src in frames:
      self.counts['all_can_items']+=1
      if 128<=src<=135:self.counts['returned_notifications']+=1
      elif 192<=src<=199:self.counts['rejected_notifications']+=1
      elif 0<=src<=7:
        self.counts['physical_rx']+=1
        result=self.probe.packet('rx',addr,data,src)
        self.counts['physical_rx_return_'+str(result)]+=1
      else:self.counts['unknown_src']+=1

  def allowed(self):return self.clock.state()['controls']

  def summary(self):
    return {'counts':dict(self.counts),'mode_transitions':self.transitions,
            'operations':dict(self.clock.operations),'final_c_state':self.clock.state(),
            'controls_setter_calls':0,'relay_setter_calls':0,'init_tests_calls':0,
            'scope_ko':'RX와 TX는 같은 C 메모리 상태. 기록 설정 변경만 초기화하며 통지는 변경/재주입하지 않는다.'}
