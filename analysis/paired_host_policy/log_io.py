"""원본 입력은메모리에서읽고직접보고할때허용된익명통계만남긴다."""
from contextlib import contextmanager
import io
from pathlib import Path
import shutil
import tempfile
from functools import partial
from types import SimpleNamespace

import capnp
import zstandard

from whole_io import ROOT,SOURCE,WORK,load_definitions


namespace={'contextmanager':contextmanager,'tempfile':SimpleNamespace(TemporaryFile=partial(tempfile.TemporaryFile,dir=WORK)),
           'zstandard':zstandard,'shutil':shutil}
load_definitions('tools/ars510_offline/replay.py',namespace,{'events'})
events=namespace['events']


def recorded_schema():
  folder=ROOT/'work/input/carrot_schemas'
  parser=capnp.SchemaParser()
  schema=parser.load((folder/'log.capnp').as_posix(),imports=[folder.as_posix(),(folder/'include').as_posix()])
  return parser,schema


def inputs():
  names=['rlog.zst','rlog_06.zst','rlog_11.zst','rlog_12.zst']
  return [(f'log_{chr(97+index)}',ROOT/'work/input'/name) for index,name in enumerate(names)]


class MemoryCsvDirectory:
  """원형 replay의 객체 CSV를 파일로 남기지 않는 입출력 경계."""
  def mkdir(self,**kwargs):pass

  def __truediv__(self,name):return self

  @contextmanager
  def open(self,*args,**kwargs):
    # 실제writer본문은유지하되point ID/좌표는어느출판파일에도남기지않는다.
    stream=io.StringIO(newline='')
    yield stream
    stream.close()
