# 최신 소스 PR 준비 결과

기존 반복 검사를 종료하고 최신 Carrot와 ARS 위에 검토용 패치를 갱신했다. 두 포크 topic 브랜치에 고정 commit을 올렸으며 **실제 PR은 아직 제출하지 않았다**. 기존 스냅샷과 다른 차종 기반은 보존했다.

| 대상 | 기준 | 검토 후보 |
|---|---|---|
| Carrot `carrot-wip` | `2ec25da` | `41773212b683181d9ce569c627ef7a97a74f0dc6` |
| ARS `main` | `fb5b29c` | `a63279545adc72c5a4330f84391b9a19d932c6d7` |

- [Carrot PR 제출용 비교](https://github.com/ajouatom/openpilot/compare/carrot-wip...Mlnege:codex/rav4-ars510-carrot-compat?expand=1)
- [ARS PR 제출용 비교](https://github.com/ds-sebastian/ars510-radar/compare/main...Mlnege:codex/carrot-native-ars510-dispatch?expand=1)
- [이슈145](https://github.com/ds-sebastian/ars510-radar/issues/145)

개선은 RAV4의 실제 전방 객체/동역학 연결, 명목60ms, 기존 명령 범위, 감속 목표 보존과 정지 요청, PCM 모드0 관측 동기화다. 필터 계수·정체불명 CAN·회생 제동 값을 추측해 바꾸지 않았다. 외부 설치기의 native 디코더 삭제/덮기 충돌도 수정했다. 다른 차량/Bosch/신호·야간/공유 필터/Panda 기반은 유지했다.

직접 실행 결과는 최종 고정 pycapnp2.1.0의182개 통과, 원격 ARS 새clone 전체271개 통과/설치환경1개 생략, 기존 타차708개 통과/실제IPC2개 미검증이다. 실제3로그는2,399정상레코드·367전달점, 원형Float32 거리/속도 차이0·B4checksum오류0·전달조건71실패0이다. Toyota37모델×2요청의CP74조건에서허용RAV4 지원3필드외차이0·제어/안전설정동일. 반복실행과겹치는시험그룹을합산하지않았다.

원본 제어는 모두OFF이며 실제ECU/FW·PCS/AEB·회생·충돌회피·Konik/ARM전체빌드·실시간마감은미검증이다. 현재 native 계산은 실제 C/Cython solver를 사용했으나 새 전체 빌드를 통과했다고 주장하지 않는다. 운영 설정 변경·차량 설치·CAN 송신·제어 활성화는 실행하지 않았다.

## 다운로드와 소스 확인

Git·curl·프로젝트 요구 범위의 Python(3.12.3이상/3.13미만)이 있는 Linux 개발환경에서 아래를 실행한다. 기존에 없는 새 폴더로 clone하고 고정commit·소스지문·Python구문을 확인한다. 의존성 설치/장치빌드/실차호환검사는 별도이며 운영 `/data/openpilot`에는 쓰지 않는다.

```bash
curl -fL https://raw.githubusercontent.com/Mlnege/rav4-ars510-validation/pr-ready-20261013/pr-preparation/20261013/prepare_pr_sources.sh -o /tmp/rav4_prepare_pr.sh
bash /tmp/rav4_prepare_pr.sh "$HOME/rav4-pr-20261013"
```

직접 clone만 하려면:

```bash
git -c core.autocrlf=false clone --branch codex/rav4-ars510-carrot-compat https://github.com/Mlnege/openpilot.git
git -c core.autocrlf=false clone --branch codex/carrot-native-ars510-dispatch https://github.com/Mlnege/ars510-radar.git
```

## 파일과 재현

`carrot.patch`는 고정2ec25da에, `ars.patch`는 고정fb5b29c에 적용한다. 각각 새 개발 checkout에서 `git apply --check <패치>`를 먼저 실행하고 성공할때만 `git apply <패치>`를 실행한다. 최신 upstream이 달라졌으면 먼저 차이를 검토해야 한다.

수정 소스37개는 `modified_sources/`, 목록과LF지문은 `수정파일목록.csv`에 있다. PR 설명은 `CARROT_PR_BODY_KO.md`/`ARS_PR_BODY_KO.md`, 검사표·CAN분석·미완료와오프라인시험명령은 `검증보고서.md`에 있다. 실제 로그는 포함하지 않았다. `wiki_pcm.patch`는 별도 Wiki의 MANUAL2페이지 수정안이며 upstream Wiki에는 쓰지 않았다.

다운로드검증은 선택한소스만확인하고 `vehicle_deployment_allowed=false`를유지한다. 전체공식의존성설치와 실제native빌드가 필요한 시험은 기술보고서의조건을 따른다. 실제차량적용 전에는 ECU/FW·PCS/AEB·활성/취소/페달전이로그·회생배분·장치빌드/시간검증을 완료해야 한다.
