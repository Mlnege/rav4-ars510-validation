"""기존 결과를 실행하지 않고 동결 지문과 공개 금지 필드만 읽기 검사한다."""
import hashlib
import json
from pathlib import Path


WORK=Path(__file__).resolve().parent
BLOCKED={'carVin','vin','serial','fwVersion','firmwareSignature','latitude','longitude','altitude',
         'generated_payload_hex','payload_hex','dat','trackId','objectId','radarTrackId'}


def scan(value,path=''):
  rows=[]
  if isinstance(value,dict):
    for key,child in value.items():
      branch=path+'/'+key
      if key in BLOCKED:rows.append(branch)
      rows.extend(scan(child,branch))
  elif isinstance(value,list):
    for index,child in enumerate(value):rows.extend(scan(child,path+'/'+str(index)))
  return rows


def main():
  manifest=json.loads((WORK/'evidence_manifest.json').read_text())
  mismatch=[relative for relative,expected in manifest['artifact_hashes'].items()
            if hashlib.sha256((WORK/relative).read_bytes()).hexdigest()!=expected]
  files=list(WORK.rglob('*.json'))
  findings=[]
  for path in files:
    prohibited=scan(json.loads(path.read_text()))
    if prohibited:findings.append({'file':path.relative_to(WORK).as_posix(),'fields':prohibited})
  print(json.dumps({'new_dynamic_execution':False,'artifacts':len(manifest['artifact_hashes']),
    'hash_mismatches':mismatch,'json_files':len(files),'prohibited_fields':findings},ensure_ascii=False))
  raise SystemExit(1 if mismatch or findings else 0)


if __name__=='__main__':main()
