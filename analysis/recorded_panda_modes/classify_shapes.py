"""원본 CAN 목록의 src와 길이만 익명 집계한다. 신호나 프레임 원문은 출력하지 않는다."""
from collections import Counter
import json

import capnp

from run import ROOT, WORK, INPUTS, load_events


def main():
  folder = ROOT / 'work/input/carrot_schemas'
  parser = capnp.SchemaParser()
  schema = parser.load(str(folder / 'log.capnp'), imports=[str(folder), str(folder / 'include')])
  events = load_events()
  results = []
  for alias, name in INPUTS:
    shapes = Counter()
    with events(ROOT / 'work/input' / name, schema.Event) as stream:
      for event in stream:
        if event.which() == 'can':
          for frame in event.can:
            shapes[f'src{int(frame.src)}/length{len(frame.dat)}'] += 1
    results.append({'alias': alias, 'shape_counts': dict(shapes), 'frame_count': sum(shapes.values())})
  result = {'files': results, 'scope_ko': 'src/DLC 익명 개수만 직접 집계. src 표시는 물리 bus와 returned/rejected 통지 offset을 구분해야 한다. raw bytes·주소·원본 시각은 출력하지 않음.'}
  (WORK / 'shape_counts.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
  print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
  main()
