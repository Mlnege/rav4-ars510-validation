fork의 native fused 수신기와 그 수신기가 필수로 import하는 ARS package를 외부 설치기가 보존하도록 수정합니다. 기존 hook은 일반 ARS wrapper를 선택해 Carrot factory의 MyTrack·record 시각 처리를 우회할 수 있었고, 설치·제거는 fork 소유 `toyota/ars510/`도 덮거나 삭제했습니다.

fused profile이며 기존 factory가 정수 `ARS510_CARROT_API=1`, `ARS510_CARROT_PROFILE="fused"`, callable `supports_ars510(CP)`의 지원 True를 제공할 때만 원래 factory를 우선합니다. bool True·float1.0·다른 API/profile·미지원 CP·marker 없는 vanilla는 기존 분기를 유지합니다. acc/raw/openpilot/colored의 dispatch도 유지하고 constructor 인자를 그대로 전달합니다. 기존 모델 감지·get_params·CP 제어 설정은 변경하지 않습니다.

installer는 fork Python을 실행하지 않고 해당 클래스의 literal API1/fused/predicate 선언을 AST로 읽습니다. 이 명시적 소유권 계약이 있으면 모든 설치 profile에서 shared package·LICENSE·fork 부속 파일·native receiver/factory를 보존합니다. package의 Python 파일 목록/원바이트가 현재 checkout과 같을 때만 hook/wrapper를 설치하며, 누락·다른 버전·불명확 계약은 변경 전에 거절합니다. `--check`는 이러한 native 상태에서 exit2와 버전 정렬/계약 검토 안내를 제공합니다. native와 legacy patch가 함께 검출돼도 보호 파일을 reverse하지 않습니다. native uninstall은 외부 hook/wrapper만 제거하며, vanilla의 package 설치·제거와 stale check exit0 정책은 유지합니다.

변경은 wrapper hook, installer, README, 계약 테스트의 4파일입니다. decoder·DBC·fused 필터 값·CAN 신호·차량 초기화/송신 코드는 바꾸지 않았습니다.

직접 검증한 결과:

- 최종 LF 사본 전체 pytest: **271통과·1skip**. 기존 aliases/legacy 검사와 추가 strict API/dispatch/소유권/안내 검사를 포함합니다. skip은 환경 미지정인 기존 실제 fork 복사 설치1조건입니다.
- 임시 복사본의 fused/acc/raw 설치→check→uninstall: native decoder9파일·LICENSE·추가 자원·receiver/factory 원바이트 보존. 불일치·누락·불명확 계약은 무변경 거절, vanilla 설치·삭제도 직접 확인했습니다. fake factory/schema는 dispatch 계약만 검사합니다.
- structure exit0, privacy304파일·검출0, 기존 Windows Ruff0.17.0의 `upstream/` 검사 exit0. Linux의 Ruff는 미설치이며 새 설치는 하지 않았습니다. 최종 privacy는 같은 LF 사본을 Linux 내부에서 검사했습니다.
- 별도 실제 Carrot `carrot-wip` 2ec25da의 현재 native receiver/API1와 hook을 메모리에서 연결한2조건: 같은 native receiver 선택, 알려진 합성12record의 순차/batch 처리에서 각각 decoder12record·CRC0·MyTrack12회, 마지막 비교 동역학 지문 동일. 프로젝트 DBC·CANPacker·CANParser로 유효 SPEED checksum 확인, CP/소스 전후 동일. CAN backend는 프로젝트 Python 구현입니다.

전체 pytest/structure 이후 privacy 호출은 Windows 인자 길이 때문에 시작 전에 실패했고, Linux 내부 호출로 같은 사본의304파일·검출0을 확인했습니다. 앞선 `.git` 없는 archive의 privacy 준비 실패와 Windows CRLF legacy fixture 실패도 보존했습니다. 최종271통과는 허용4파일을 LF Git 사본에 반영한 별도 전체 실행 결과이며, 앞선 부분검사 숫자를 합산하지 않았습니다.

실제 상호운용 probe는 get_params/CarInterface.init·운영 Params·전체 호스트 권한·차량 CAN 송신을 실행하지 않았습니다. 실제 설치/재부팅·ECU 식별·PCS/AEB 보존·실차 제동·장치 처리 마감 검증은 아닙니다. marker를 제공하는 Carrot 변경은 별도 PR 범위이며 원형 Carrot의 marker 없는 상태는 기존 경로를 유지합니다.

Codex가 수정·테스트·검증·PR 초안 작성에 참여했습니다.
