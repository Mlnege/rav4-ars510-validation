"""판정 메서드의 실제 global binding과 원형 상수 일치 여부를 기록한다."""
import ast
import builtins
import dis
import hashlib
import json
import os
from pathlib import Path
from types import CodeType

from whole_io import WORK,SOURCE,MemoryBus,memory_messaging,SOURCE_HASHES


def global_names(code):
  values={node.argval for node in dis.get_instructions(code) if node.opname=='LOAD_GLOBAL'}
  for child in code.co_consts:
    if isinstance(child,CodeType):
      values.update(global_names(child))
  return values


def compare_constants(relative,namespace):
  tree=ast.parse((SOURCE/relative).read_text())
  rows=[]
  for node in tree.body:
    if isinstance(node,ast.Assign):
      targets=[x.id for x in node.targets if isinstance(x,ast.Name)]
      if not targets or not all(x in namespace for x in targets):
        continue
      # 초기화/부작용 표현을 제외하고 상수/enum/comprehension 할당만 대조한다.
      copy=dict(namespace)
      exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE/relative),'exec'),copy)
      for name in targets:
        current,original=namespace[name],copy[name]
        rows.append({'name':name,'source_expression':ast.unparse(node.value),'same_value':current==original,
                     'value':str(current) if name not in ('ACTUATOR_FIELDS','LONGITUDINAL_PERSONALITY_MAP') else current})
  return rows


def main():
  os.chdir(SOURCE)
  module=memory_messaging(MemoryBus())
  from whole_objects import load_policies
  sd,controls,card=load_policies(module)
  groups=[(sd,'openpilot/selfdrive/selfdrived/selfdrived.py',
           ['__init__','data_sample','update_events','_big_model_settling','update_reboot_alert','step',
            'update_impact_dashcam','update_alerts','update_system_ready_alert','publish_selfdriveState']),
          (controls,'openpilot/selfdrive/controls/controlsd.py',['__init__','update','state_control','publish']),
          (card,'openpilot/selfdrive/car/card.py',['__init__','state_update','state_publish','controls_update','step'])]
  result=[]
  for cls,relative,methods in groups:
    namespace=cls.__init__.__globals__
    details=[]
    for method in methods:
      function=getattr(cls,method)
      rows=[]
      for name in sorted(global_names(function.__code__)):
        value=namespace.get(name,getattr(builtins,name,None))
        rows.append({'name':name,'resolved':name in namespace or hasattr(builtins,name),
                     'binding_module':getattr(value,'__module__',getattr(value,'__name__',type(value).__module__))})
      details.append({'method':method,'globals':rows,'missing':[row['name'] for row in rows if not row['resolved']]})
    result.append({'class':cls.__name__,'source':relative,'source_sha256':hashlib.sha256((SOURCE/relative).read_bytes()).hexdigest(),
                   'constants':compare_constants(relative,namespace),'methods':details})
  report={'classes':result,'all_tested_method_globals_resolved':all(not m['missing'] for c in result for m in c['methods']),
          'all_source_constants_equal':all(x['same_value'] for c in result for x in c['constants']),
          'io_bindings':['Params: 프로세스 내부 MemoryConfiguration',
                         'messaging: 원형 수신 판정과 메모리 소켓',
                         'VisionIpcClient: 선언한 카메라 목록 입출력',
                         'CI.init: 물리 초기화 실행을 차단하는 sink',
                         'CI.apply: 원형 Toyota 계산과 메모리 CAN/C 검사',
                         'CI.update: 원본 기록 CarState 반환 입출력; 전체 Toyota CI.update는 미실행',
                         'stock feedback: 원본 CAN을 기존 DBC로 해독',
                         'Card CAN drain: 메모리 빈 배치; 원본 C RX와 ARS decoder 입력은 별도 보존'],
          'module_import_scope_ko':'GPU/modeld runtime 전체 import 대신 해당 상수 원형 할당을 실행. 판정 source 전체 class/method 본문은 수정하지 않음. 다른 미실행 메서드의 의존성까지 실행했다고 주장하지 않음.'}
  (WORK/'namespace_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({k:report[k] for k in ('all_tested_method_globals_resolved','all_source_constants_equal')},ensure_ascii=False))


if __name__=='__main__':
  main()
