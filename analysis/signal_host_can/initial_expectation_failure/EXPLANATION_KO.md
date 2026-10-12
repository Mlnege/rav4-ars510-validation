# 최초 invalid_can 검사 예상 오류

최초31조건 실행은30조건exit0, invalid_can 조건1개에서 `start_preserves_hold_when_valid_false` 검사에 실패했다. 원본 결과와 로그/suite요약을 이 폴더에 보존했다.

이 검사는 전체 호스트에 canValid=False를 입력하면서도 `valid=False만 바뀌고 상위 enabled는 유지`된 부분 실험의 기대를4초 전체에 적용했다. 실제 원형 selfdrived의 canError는 immediate-disable이다(events.py1010행). 따라서103.50초 첫 계획은 이전CC/SDenabledTrue를 읽어 invalid_context에서holdTrue를 보존하지만, 같은틱의 host는disabled가 된다.103.55초 다음model계획은이미CC/SDfalse를읽고원형StartGuard의disabled-reset으로holdFalse가 된다. 양수LoC/CAN은0이고C판정불일치도0이다.

생산 알고리즘/권한/필터를 바꾸지 않았다. 새 검사는 활성 context가invalid인첫plan의hold보존, 원형canError에의한host비활성화, 다음disabled-context의reset을각각확인한다. 부분valid-only반례와전체host의CAN실패를구분하는기대정정이며 이최초실패를삭제하거나source결함수정으로보고하지않는다.
