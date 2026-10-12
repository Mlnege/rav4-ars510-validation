# 레이더 CAN 묶음·필터·모델 투영 시각 독립 읽기 검토

원형 경로는 서로 다른 시각을 각각 사용한다. CAN/CarState 묶음의 신선도는 **card 수신 시각**, ARS 객체 조립·fused 필터는 **원래 CAN 헤더와 record 첫 프레임 시각**, DPath 위치 투영은 **liveTracks 발행 헤더와 모델 EOF**를 기준으로 한다. 이 차이를 같은 ‘레이더 시간’으로 묶으면 오프라인 비교의 의미가 달라진다. 현재 근거만으로 의도된 보정이나 결함 중 하나로 확정하지 않았다.

이번 작업은 생산 source, 스키마 설명, 기존 검사 소스/보고서 읽기만 수행했다. 새 테스트·로그 재생·빌드·socket·차량 송신은 실행하지 않았다. source/스키마/CP/age cutoff/바이너리를 수정하지 않고 이 문서만 작성했다.

## 읽은 버전과 현재 실행 경계

| 파일 | SHA-256 |
|---|---|
| radar/radarcan.py | `3f2da75508194aa86179056574fa87fb0259c7aa65c45fd318b26325ef1c500b` |
| radar/can_batch.py | `73d72c3c45ef500886af90224cf3f64fbb3f2ca6c638bdc65b9986f0b83ec040` |
| radar/radard_dpath.py | `f3f3506398dd9bd939b96c83ab21409d8daf3f326fccabb6adf79fb1948d7be2` |
| toyota/ars510_offline.py | `8b471914b92466fb9589c298b976fe377eea18e7c111e81f89258cab45d12a50` |
| tools/ars510_offline/replay.py | `c5d91ef5c12dd3ca537d0de65e1b338fe25fcac31478e7059e299fb41cb9f1a6` |

생산 radarcan은 `interfaces[CP.carFingerprint].RadarInterface(CP)`를 만든다. 현재 ARS510 어댑터는 등록되지 않은 offline=True 전용이고, RAV4의 radarUnavailable=True도 유지한다. Toyota 원형 RadarInterface는 이 조건에서 radar CAN parser를 만들지 않는다. 따라서 아래 ARS와 생산 batch 경로의 연결은 **향후 오프라인 비교에 필요한 시간 계약**이며 이미 실차에서 ARS가 이 경로를 실행했다는 주장이 아니다.

## 시간 기호

| 기호 | 시각의 의미 |
|---|---|
| Cᵢ | 원본 CAN Event의 logMonoTime. 한 Event 안의 여러 frame은 같은 헤더를 공유 |
| R | CS.radarInput.receiveMonoTime. 정상 card가 CAN socket drain 직후 읽은 monotonic_ns |
| S | CarState Event 발행 헤더 |
| F | 완성 ARS record의 **첫 0x80 프레임 헤더** |
| K | ARS record 마지막 프레임이 들어온 CAN 헤더, 소프트웨어 조립 완료 시점 |
| P | liveTracks Event가 새로 생성된 발행 헤더 |
| E | modelV2.timestampEof. 0이면 모델 Event 헤더를 대신 사용 |
| D | DPath의 전방 거리 보정 지연. 일반 차량은 max(0, CP.radarDelay), MEB는 별도 0 정책 |

기호는 소스상의 역할이다. Cᵢ/F/K가 ECU 내부의 실제 객체 측정 시각이라는 증거는 아니다. 현재 CAN 발행 C++ 경로의 BOOTTIME 계열과 Python receive/publication의 MONOTONIC 계열을 실제 장치에서 무조건 같은 기원으로 가정하지 않았다. R/S는 현재 source 설명상 같은 host의 Python 시각이며, 실제 clock offset/절전/collector 수신 내역은 별도 검증 대상이다.

## 생산 경로에서 사용하는 시각

| 단계 | 실제 사용 값 | source 근거·주의 |
|---|---|---|
| card CAN 수집 | drain한 각 CAN Event의 Cᵢ를 보존, drain 직후 R 획득 | `card.py:204–214`, pandad_api_impl.can_capnp_to_list. 하드웨어 개별 frame receipt 시각은 아님 |
| CI.update·CarState | 정확한 packet 목록을 CI.update에 준 뒤 첫/마지막 Cᵢ·count·R을 CS.radarInput에 기록 | `card.py:254–257`. R은 뒤의 S로 대체하지 않음 |
| RadarCanBatches | 같은 CS의 first/last/count로 정확한 CAN Event 목록을 매칭 | `can_batch.py:58–85`. 최신 ego를 임의 선택하는 경로가 아님 |
| 사전 freshness | radarcan now−R>100ms이면 staleEgoState | `can_batch.py:61`. oldest Cᵢ의 나이와 다른 기준 |
| radar interface 호출 | `update_carrot(CS.vEgo, CS.aEgo, R, 원래 Cᵢ packet 목록)` | `radarcan.py:87`. 받아온 packet 헤더를 R로 덮어쓰지 않음 |
| 처리 후 freshness | 현재 now−R>100ms이면 processingTimeout 오류 발행 | `radarcan.py:89–91` |
| CAN/상태 입력 중단 | 마지막 처리한 상태 R과 **마지막 비어 있지 않은 batch의 R** 기준 | `radarcan.py:77–100`. raw 마지막 CAN 헤더 Cᵢ로 측정한 전체 packet age가 아님 |
| liveTracks 발행 | 처리·검사 뒤 new_message가 만드는 P | `radarcan.py:93–99`. 결과 내부 record F/K를 헤더에 직접 넣지 않음 |
| liveTracks 유효 표시 | 오류 구조 중 하나라도 True이면 Event.valid=False | `radarcan.py:94` |
| DPath update | E를 controller.time_s로, E−P를 radar_to_model_time_s로 전달 | `radard_dpath.py:79–83`, `:120–134` |
| 위치 투영 | Δ=E−P+D, dRel+=vRel×Δ, yRel+=yvRel×Δ | `radar_motion/controller.py:744–790`, `primary.py:675–680` |
| skew 자격 | 투영 전 abs(E−P)>150ms 또는 비유한이면 포인트 제외 | `controller.py:750–755`. D가 더해지기 전 publication skew 기준 |
| lead 동역학 시간 | E−(E−P)=P | `controller.py:941`. record F/K를 직접 쓰지 않음 |
| 출력 RadarState 헤더 | 다시 새 발행 시각. mdMonoTime/carStateMonoTime은 각 입력 Event 헤더 | `radard_dpath.py:116–117`, `:147–151` |

원형 SubMaster의 recv_time·alive는 이 헤더들과도 별개의 소비자 수신 시각이다. 오래된 객체 측정 내용이 신선한 발행 헤더에 실려 오는 상황을 헤더 freshness만으로 입증하거나 반박할 수 없다.

## ARS 조립·fused·MyTrack 시각

| 단계 | 실제 시간 기준 |
|---|---|
| 각 frame/support 입력 | Cᵢ. B4 속도·yaw·ACC 보조 cache도 처리한 packet 헤더로 갱신 |
| strict 조립 | K−F가 150ms를 넘으면 거부. frame 길이·순서·CAN 시각 역행도 별도 검사 |
| CompletedRecord | time_s=F. 마지막 프레임에서 조립되지만 완료 시각 K로 바뀌지 않음 |
| native `_payload` | F를 전달. lifecycle·보조 연관·fused speed/range state에 사용 |
| fused dt | 현재 F−앞선 F. 0<dt≤0.5 조건 및 필터/거리 예측에 사용 |
| B4/ACC freshness | `_payload(F)` 호출 때까지 갱신된 cache를 F와 대조. B4/ACC의 해당 함수는 abs(time 차이) 검사 |
| vRel/vLead | vRel=fused ground−사용한 B4, vLead=fused ground. 최신 CS 속도에서 vRel을 만든 것이 아님 |
| MyTrack | 완료 record마다 원형 필터를 실행하되 dt는 검증한 고정 0.06초. vLead로 가속/저크 계산 |
| 외부 ego 이력 | outer batch당 하나의 CS.vEgo/aEgo를 이력에 한 번 추가. 내부 frame 분할마다 추가하지 않음 |
| adapter record timeout | 처리 packet Cᵢ 또는 최종 rcv_time=R에서 마지막 record F와 비교해 0.5초 초과를 검사 |

근거: `ars510_offline.py:38–73`, `:190–311`; `ars510/transport.py:CompletedRecord`, `:push`; `ars510/interface.py:231–295`, `:336–345`, `:431–445`, `:488–496`, `:549–621`; `radar_tracks.py:MyTrack.update`.

한 batch에 timestamp가 서로 다른 여러 완성 record가 있으면 각 record가 원형 MyTrack을 거친다. 최종 API 반환은 마지막 결과일 수 있다. 같은 timestamp에 여러 완성 record가 생기면 시각을 추정하지 않고 ambiguous_batch_time으로 거절한다. 이 시간 분할 계약과 생산 RadarCanBatches의 CS/packet 매칭 계약은 다른 층이다.

MyTrack의 dt는 record 실제 F 차이를 매번 인수로 받아 바꾸는 방식이 아니다. 한 CS batch의 ego 인수는 그 안의 모든 record에서 같은 외부 샘플이다. 전방 MyTrack의 현재 가속 필터는 전달 vLead를 쓰고 a_ego 인수로 ground 속도를 재구성하지 않는다. CP.radarDelay의 ego 이력 길이와 DPath의 거리-only 보정 D도 별개다.

RadarData/RadarPoint의 활성 스키마에는 각 포인트의 F/K/R를 담는 timestamp 필드가 없다. deprecated canMonoTimes를 사용해 전달하는 경로도 아니다. 어댑터의 내부 F/K가 liveTracks Event로 직렬화된 후 DPath의 시간 인수가 되는 것은 아니다. DPath snapshot은 또 `vEgo+vRel`로 vLead를 재구성하므로 시간 기준 문제와 앞서 확인한 B4/CarState 속도 기준 문제를 구분해야 한다.

## 실제 15,401 메타 관찰의 정확한 의미

기존 C 담당의 `radar_input_contract_probe/REPORT_KO.md`와 고정 probe를 읽었다. 15,401 CS에서 radarInput wire 포인터·네 양수 필드·CAN 첫/마지막/count의 정합성이 확인되었고, take(now=기록 CS 발행 헤더 S) 조건에서 전부 accepted였다는 범위다. 이 검토자가 그 원본 실행을 다시 한 것은 아니다.

- 단일 Event batch 15,398개, 복수 batch 3개이며 그중 16 Event batch 1개가 있다. packet count는 개별 CAN frame 수가 아니다.
- oldest CAN Cᵢ→R 최대 149.579820ms, R→S 최대 18.395472ms다. former가 100ms보다 크고 latter가 100ms보다 작다는 사실은 서로 다른 측정 기준이므로 모순이 아니다.
- 고정 probe는 CS별 독립 buffer와 실제 기록 헤더를 사용하지만 CAN payload는 빈 frame 목록이며, source take의 now를 S로 정한다. 실제 radarcan 처리/수신/queue/전체 socket 순서·deadline을 실행한 것은 아니다.
- 기록된 CAN 15,834 Event 중 15,432개가 CS metadata에 묶였고 402개는 어느 기록 CS 범위에도 결합되지 않았다. 이를 실제 유실이나 메타 실패로 판정하지 않았다. 새 CS를 만들어 나머지를 끼워 넣으면 원본 계약을 바꾼다.

최대 149.58ms를 ‘실물 레이더 receiptage’ 또는 ‘원형 100ms gate 위반’으로 부르면 안 된다. record 조립의 K−F 150ms, source 입력 freshness의 now−R 100ms, adapter의 now−F 500ms, DPath의 abs(E−P) 150ms는 각각 다른 식이다.

## CAN-event 오프라인과 CS 맞춤 batch의 차이

| 항목 | 현재 offline replay.py | 원형 CS 맞춤 batch 경로 |
|---|---|---|
| 처리 단위 | 로그 순서의 각 CAN Event마다 한 호출 | 기록 CS의 first/last/count에 해당하는 정확한 packet 목록마다 한 호출 |
| 외부 ego | 로그에서 이미 읽은 최신 CS. 해당 CAN을 만들 때 card가 쓴 CS임을 보장하지 않음 | 그 batch를 CI.update에 넣어 생성한 CS의 vEgo/aEgo |
| rcv_time | 해당 CAN Event 헤더 Cᵢ | CS.radarInput.receive R |
| frame decoder 시각 | 원래 Cᵢ | 원래 Cᵢ 보존. R로 덮어쓰지 않음 |
| fused record 시각 | 첫 0x80 F | 같은 패킷이 들어가면 같은 F. metadata-bound subset/누락 범위에 따라 기록 수는 달라질 수 있음 |
| ego history cadence | CAN Event 호출 수 기준 | CS control tick 기준이며 empty batch도 한 상태 틱 |
| liveTracks 시간 대용 | event_out.logMonoTime=Cᵢ, tracks_time=Cᵢ를 직접 부여 | 처리 이후 실제 new_message 발행 P |
| DPath 투영 인수 | E−tracks_time, 즉 E−CAN 헤더 대용 | E−P |
| 결과 의미 | 저장 CAN decode→필터→직렬화→원형 lead 코어 전달 | 정확한 CS/packet association을 보존한 별도 비교. 실제 P/수신은 추가 관찰 필요 |

현재 오프라인 성공 수치를 원형 batch/시간 계약까지 검증한 결과라고 확대하면 안 된다. 반대로 두 경로의 값이 달라도 batch 단위·미결합 CAN·CS 선택·publication time 대용부터 분리해야 한다. 명세의 의도나 decoder 결함으로 바로 판정할 수 없다.

## 명세·지연 보정에서 확인이 필요한 부분

스키마 설명은 card가 사용한 **정확한 CAN 묶음과 ego 상태**를 독립 radar 수신에 연결하고 R를 뒤의 publication timestamp로 바꾸지 않는 목적을 명시한다. can_batch 원형은 이 목적과 일치하는 매칭을 수행한다. socket 도착 순서가 달라도 개별 stream은 순서를 유지한다는 전제다.

DPath의 식은 포인트 거리의 기준 시각을 P−D로 놓고 E까지 투영하는 형태다. ARS 내부 필터의 소프트웨어 record 기준은 F다. 두 기준의 차이 P−F에는 조립, card 처리, 별도 프로세스 대기·필터·발행이 섞일 수 있다. CP.radarDelay/D가 이를 의도적으로 보정하는지, native 객체 자체가 어떤 ECU 측정 시각의 값인지 아직 확인되지 않았다. ARS를 live 등록하지 않은 현재 상태에서 이를 실차 보정 오류라고 확정하지 않는다.

동일 CAN Event의 개별 frame에는 서로 다른 실제 수신 시각이 보존되어 있지 않을 수 있다. 지원 ECU의 record 생성/내부 측정 epoch와 packet header의 관계를 모르면 F/K 중 하나를 실제 측정 시각이라고 임의 지정해서는 안 된다.

## 필요한 후속 검증 — 이번에는 실행하지 않음

- 같은 원본의 metadata-bound batch와 CAN-event 경로를 구분해 비교하고 402 미결합 Event 처리 범위를 먼저 고정한다. 모든 CAN을 임의 새 CS에 결합하지 않는다.
- Cᵢ/F/K/R/S/P/E와 처리 시작/끝을 원형 반환을 바꾸지 않는 observer로 구분한다. 개인정보/절대 원본 시각은 결과에 저장하지 않고 상대 차이·개수만 집계한다.
- record별 원형 fused 결과·MyTrack 호출/고정 dt·CS ego 이력 append·객체 삭제/재사용·최종 반환 시각을 관찰한다. metadata gate acceptance만으로 decoder/pipeline acceptance를 선언하지 않는다.
- DPath에 넘긴 P 또는 대용 시각의 종류를 명시하고 publication skew·추가 거리 보정 D·동역학 sample time을 각각 기록한다. actual P가 없으면 S를 대용으로 쓴 가정을 분리한다.
- original CAN/CS/model 시각을 하나의 상대 epoch로 바꾸는 도구는 nested radarInput의 first/last/receive도 같은 변환을 적용했는지 검토한다. 통과를 위해 R를 새 now로 바꾸거나 packetCount를 생성하지 않는다.
- 원형 REPLAY 분기는 card의 R를 첫 CAN 헤더로 선택하고 radarcan의 now를 기록 ego.receive로 사용한다. 외부 replay framework가 publication header 시계까지 어떻게 공급하는지 확인하지 않은 채 실제 wallclock freshness 검사로 소개하지 않는다.
- 실제 sender의 clock 기원과 ECU 측정 지연, 실제 radarcan의 queue/processing/publication 지연, 누락·overflow·timeout 오류 전파를 별도로 검증한다. 기록상 gate 15,401 accepted를 물리 수신 지연의 상한 증거로 사용하지 않는다.

현재 source/스키마/.so/CP 및 cutoff를 그대로 두었다. 메타가 실제로 존재한다는 사실, 각 필터가 사용하는 시각, 모델 투영의 기준 시각을 분리해 다음 비교의 명세를 정리한 범위다. 실제 ECU/firmware·ARS live·호스트 제어 허용·차량 안전성을 검증한 결과가 아니다. 허용 범위 밖 인계 파일도 수정하지 않았다.
