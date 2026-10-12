# 준비 과정의 오류 기록

이 조사에서는 계산 알고리즘이나 모의 차량을 새로 실행하지 않았다. 아래는 파일 읽기와 추출 도구를 준비하면서 생긴 오류이며 생산 코드의 실패가 아니다.

- 처음 파일 읽기 명령의 `Path.read_text()`가 Windows 기본 CP949 인코딩을 사용해 한국어가 있는 기존 JSON에서 `UnicodeDecodeError`가 났다. 후속 읽기와 새 도구는 `encoding="utf-8"`을 명시했다.
- 처음 신호 CSV 선택 명령은 합성 시각의 시작값 100초를 빼지 않아 요청한 경과 2.13초 대신 첫 행을 골랐다. 이 잘못된 선택값은 보고서 근거에서 제외했다. 후속 명령과 새 도구는 첫 행을 0초로 정규화했다.
- 레이더 보조 모듈의 디렉터리를 처음 두 번 잘못 지정해 `rg`가 경로 없음으로 끝났다. 실제 위치인 `openpilot/selfdrive/carrot/radar_motion/`을 확인한 뒤 읽었다.
- 새 `collect_evidence.py`의 첫 실행은 53행짜리 `inspect_stop.py`에서 57행까지 가져오려고 해 `IndexError: list index out of range`로 끝났다. 빈 `frozen_read01/` 폴더를 그대로 보존하고 범위를 43~53행으로 고친 후 별도 `frozen_read02/`에 실행했다. 기존 결과, 생산 코드 및 native 바이너리는 변경하지 않았다.
- 보조 읽기 명령이 별도 `signal_start_guard_runtime.py` 파일을 찾으려고 해 경로 없음으로 끝났다. 실제 reset·가스 처리 근거는 기존 `signal_start_guard.py`에서 읽었다. 이 경로 오류로 누락된 내용을 추정해 채우지 않았다.

32개 파일을 포함하는 최종 도구 실행 결과와 지문은 `frozen_read03/`에 보존했다. `frozen_read02/`는 최초 성공한 29개 파일 읽기 결과로 그대로 보존한다. 현재 읽은 도구 소스와 당시 첫 근거리 실행 소스가 같다고 단정하지 않는다.
