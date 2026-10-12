# Panda 권한 검사 복원: 오프라인 C 검증

차량 연결, USB/소켓 접속, CAN 송신, Panda 펌웨어 설치, 운영 설정 변경은 실행하지 않았다. `probe_tx`는 원형 C의 송신 **허용 판정 함수**만 메모리에서 호출한다. 실제 차량 송신 함수가 아니다.

## 변경 범위

- `safety.h`: 가속도 검사에 기존 제어 허용·운전자 가속 조건을 복원했다. 가속도 송신으로 `controls_allowed`를 True로 만드는 코드를 제거했다. 두 조향 검사의 무조건 True AOL 우회와 송신으로 ACC 메인 상태를 바꾸는 코드를 제거했다. 기존 제한·비활성 가속도 코드·0 토크·비활성 각도 규칙을 유지했다.
- `safety_honda.h`, `safety_hyundai.h`, `safety_hyundai_canfd.h`: 이미 거절 판정이 나온 조향 요청에 `tx=false`를 다시 적용했다. 범위·비트 위치·차종 플래그를 변경하지 않았다.
- `tests/common.py`: 가속·토크·각도 송신이 제어 허용·ACC 메인 상태를 만들지 못한다는 회귀 검사를 추가했다. 전달 검사에 실제 CANPacket 포인터를 사용한다.
- `tests/libsafety/libsafety_py.py`, `tests/test_tesla.py`: 원형 테스트의 오래된 전달 함수 선언과 호출을 실제 C ABI에 맞췄다. Tesla의 기존 AEB 입력 패킷은 그대로 사용한다.
- `tests/test_volkswagen_pq.py`: 차량 코드가 현재 선택하는 `vw_pq` DBC로 검사 fixture 두 곳만 정정했다. 이전 `vw_golf_mk4` 입력은 카운터가 바뀐 후 XOR 체크섬이 갱신되지 않아 실제 C가 RX를 거절했으며, 무조건 AOL 우회가 이를 숨기고 있었다.

이 변경은 검증된 별도 조향 권한 없이 `controls_allowed=False`에서 들어오는 AlwaysLateral 요청도 차단한다. 새 권한 플래그를 임의로 만들지 않았다. 실차 적용은 실행하지 않았다.

## 실제 실행 환경과 구분

원형 `tests/libsafety/safety.c`와 C 안전 알고리즘 전체를 WSL GCC로 컴파일했다. 기존 테스트용 `fake_stm.h`의 메모리 타이머를 사용하며 하드웨어 실행 결과가 아니다. 원형 fixture가 빠뜨린 `safety_tx_buffered_for_fwd` 전역 상태 변수만 `probe.c`에 제공했다. 안전 알고리즘·CAN 파서·체크섬·메시지 생성기를 성공하도록 대체하지 않았다.

공식 pytest의 CFFI는 실제 컴파일된 C 함수로 직접 연결된다. 최종 검사에는 임시 전달 ABI adapter가 없다. 설정 저장소 접근만 기존 오프라인 bootstrap으로 금지하고, 컴파일 산출물 위치만 지정한다. DBC는 원형 생성기를 별도 작업 폴더에서 실행했다. 현재 파일과 원형 HEAD의 알고리즘을 동일한 정정 fixture·동일 입력으로 비교했다.

## 재현 명령

CarrotPilot checkout을 `work/carrotpilot`, 이 도구를 `work/safety_validation`에 두고 워크스페이스 루트에서 Linux 명령을 실행한다. 별도 checkout은 pytest 실행기에 `--repo /경로/openpilot`을 지정할 수 있다. Python 3.12, numpy, cffi, pytest, parameterized, pycapnp와 checkout의 의존성이 필요하다.

```sh
gcc -Wall -Werror -nostdlib -fno-builtin -std=gnu11 -Wfatal-errors \
  -Wno-pointer-to-int-cast -shared -fPIC \
  -Iwork/carrotpilot/opendbc_repo/opendbc/safety/board \
  -Iwork/carrotpilot/opendbc_repo/opendbc/safety \
  work/safety_validation/probe.c \
  -o work/safety_validation/libsafety_all_hooks_hardened.so

python3 work/safety_validation/verify_compiled.py \
  work/safety_validation/libsafety_all_hooks_hardened.so \
  --output work/safety_validation/all_hooks_core.json --exhaustive
python3 work/safety_validation/verify_offsets.py \
  work/safety_validation/libsafety_all_hooks_hardened.so \
  --output work/safety_validation/all_hooks_offsets.json
python3 work/safety_validation/verify_timing.py \
  work/safety_validation/libsafety_all_hooks_hardened.so \
  --output work/safety_validation/all_hooks_timing.json
python3 work/safety_validation/verify_brand_steering.py \
  work/safety_validation/libsafety_all_hooks_hardened.so \
  --output work/safety_validation/brand_steering_final.json
```

예시 공식 Toyota/Tesla 검사:

```sh
work/linux_runtime/venv/bin/python work/safety_validation/run_upstream_tests.py \
  work/safety_validation/libsafety_all_hooks_hardened.so \
  work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_toyota.py \
  work/carrotpilot/opendbc_repo/opendbc/safety/tests/test_tesla.py \
  --junit work/safety_validation/toyota_tesla_final.xml --quiet-c
```

원형 비교 빌드는 `baseline_include`에 원형 HEAD의 `safety.h`와 수정 대상 세 차량 header를 넣고, 위 include 경로보다 `-Iwork/safety_validation/baseline_include`를 먼저 지정한다. 원형 header의 상대 include를 위해 `-Iwork/carrotpilot/opendbc_repo/opendbc/safety/safety`도 추가한다. 최초 원형 `libsafety_baseline.so`와 중간 단계 바이너리를 보존했다.

## 근거 파일

- `all_hooks_core.json`: Toyota 명명 사례 171개와 제어 허용·가속 입력·부호 있는 16비트 전체 262,144조건.
- `all_hooks_offsets.json`: 실제 제한·영점·비활성 코드가 다른 6프로파일, 총 1,572,864조건. Tesla/Ford/VW의 0이 아닌 비활성 코드도 유지한다.
- `all_hooks_timing.json`: 1초 경계, uint32 시계 순환, 역행, RX 만료 후 반복 TX, 실제 PCM off→on 수신 재활성화, PCS 전달·relay 차단 297사례.
- `brand_steering_before.json`, `brand_steering_final.json`: Honda·Hyundai·CAN FD의 권한 없는 조향 및 기존 512 제한 초과 요청 11사례. 원형의 5실패를 수정형에서 거절한다.
- `sanitizer_authority.stdout.txt`: ASan·UBSan 실제 C 실행의 패킷 길이·버스·부호 값 131,332사례. 최종 세 차량 hook 버전도 별도 다시 검사한다.
- `affected_brands_all_hooks_final.xml`과 `all_hooks_native_comparison.json`: 8제조사의 원형/수정형 전체 C 검사 비교. 전체 통과가 아니며 남은 기존 실패를 분리한다.
- `source_manifest.json`, `baseline_source_manifest.json`: 수정 대상·원형 소스 SHA256.

전체 ECU 펌웨어·장치 빌드·물리 AEB/PCS·실차 제어 결과는 이 검사로 확정하지 않는다. rlog나 실제 차량의 개인 식별 정보를 이 도구에 복사하지 않았다. 모든 검사 결과는 실제 실행한 파일별 수치를 사용하고 서로 다른 단계의 수치를 합쳐 단일 전건 통과로 표현하지 않는다.
