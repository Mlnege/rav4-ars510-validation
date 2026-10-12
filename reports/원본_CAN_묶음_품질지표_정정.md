# 공유 레코드의 점 개수 관측 정정·직접 재검사

이전 보고서는 `point_count_delta_on_shared_records=0`을 근거로 공유 레코드의 점 개수가 같다고 설명했다. 이 지표는 **부호 있는 차이의 합**이므로 +1/-1 같은 차이가 서로 상쇄될 수 있다. 이전 근거로 레코드별 동일을 보장한다고 표현한 것은 부정확했다. 기존source·cause_run04_frozen·이전REPORT를 그대로 보존하고, 이 별도 결과로 문구를 정정한다.

새 `paired_adapter_replay_quality.py`는 원형 계산·입력·필터·시각을 바꾸지 않고 다음 관측 지표만 추가했다. 비교 대상은 **두 경로가 모두 완성한 레코드의 교집합**이며 0점 레코드도 포함한다.

- `shared_record_point_count_mismatches`: 각 공유 레코드의 점 개수가 다른 레코드 수.
- `absolute_point_count_delta_sum`: 각 공유 레코드의 점 개수 차이에 절대값을 취한 합계.
- `signed_point_count_delta_on_shared_completed_records`: 같은 교집합의 부호 있는 합계. 진단용으로 보존하며 단독 동일성 근거로 쓰지 않는다.

2026-10-12 **23:30:54.371~23:31:03.625 KST**, 처리구간9.253654초에4로그를 직접 실행했다. exit0, 준비오류0, source 시작/끝지문 동일, 원본파일크기·수정시각 동일, 원본CP불변 및 radarUnavailable=True였다. Ruff도 직접 오류0으로 종료했다. log_c는 원본CP 부족으로 유지했다.

| alias/시각 가정 | 공유 완성 레코드 | 점 개수 불일치 | 절대 차이 합 | 부호 있는 합계 |
|---|---:|---:|---:|---:|
| log_a / input_max |479 |0 |0 |0 |
| log_a / storage_max |479 |0 |0 |0 |
| log_b / input_max |991 |0 |0 |0 |
| log_b / storage_max |990 |0 |0 |0 |
| log_c |원본CP 부족 |판단 불가 |판단 불가 |판단 불가 |
| log_d / input_max |930 |0 |0 |0 |
| log_d / storage_max |930 |0 |0 |0 |
| input_max 합계 |2,400 |0 |0 |0 |
| storage_max 합계 |2,399 |0 |0 |0 |

새 mismatch와절대합이둘다0인이번직접결과에한해, **공유 완성 레코드별 출판점 개수가 같았다**고 말할 수 있다. 좌표·거리·속도·가속도·객체ID·점 배열 내용이 같다는 주장은 하지 않는다. record key는 원본시각으로메모리에서만대조했고출력하지않았다.

계산결과는동결run04와같았다. 직접경로369점/2,433record, paired input_max367점/2,400record, storage_max367점/2,399record, CRC실패0이다. 두경로에서공유되지않는record와없는2점을이품질지표로정상복구한것은아니다. 기존clock가정/stale거절/미결합CAN·source비교범위를그대로유지했다. 숫자369/175를맞추려고값이나drive코어를변경하지않았다.

새source SHA256: `ef23a7eb51506f780fa4c86b8e9459428c56568f547ab612030c65b5ee737388`.

새 `quality_run05_frozen/results.json` SHA256: `3af0ea3c9a4049da38ccb75da9f8b5f95e3e5d7070fc10258d354d85e44c75f0`.

보존된source SHA256: `7565826f714ddc91076fa1e5bfda21393a4f48b458210b1cc3f290ee35f95b7d`; 이전REPORT SHA256: `222e1aa505da91fb20ac116e6d08a15015427ba01723d7c3e66be80fa7d6ed3c`; run04 결과 SHA256: `a6a9036eb5a73d1611ca1b23eaff39e5ac6141bc23e5d17f79297826d500a62c`. 이 셋을 변경하지 않았다.

```powershell
# 새출력폴더만사용. 대표파일은 --aliases log_b로선택할수있다.
& work\venv\Scripts\python.exe -B work\radar_input_contract_probe\paired_adapter_replay_quality.py --output-dir work\radar_input_contract_probe\paired_run01\quality_independent_replay
```

복사재현에는새quality script와동결paired_adapter_replay.py/probe.py/canonical_batch_replay.py를같은work 하위폴더에함께두거나현재source에서새output-dir를사용한다. root는대표log_b를별도복사로직접재실행하고,r8 공개전stage에서새지표·정정문구·결과지문을동기화할예정이다. 이단계에서는release/outputs/production source/.so를변경하지않았으며공개반영을완료했다고보고하지않는다.

완료는새관측지표의직접계산과과거동일성문구정정이다. DPath/175선택·host·실차/PCS안전성·좌표/속도동일성검증은이번범위가아니다.
