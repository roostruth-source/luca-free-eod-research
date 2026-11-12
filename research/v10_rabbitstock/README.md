# LUCA V10 급등통합판별기 평가 게이트

연구 전용이며 실거래 주문을 만들지 않는다.

## 이번 단계

- 화면 기준시각과 데이터 기준일을 분리한다.
- 미래 데이터가 과거 신호에 섞이면 즉시 실패한다.
- 5개 엔진의 포착 수·순위·예상가 중앙값·범위를 재현 가능하게 계산한다.
- ATM·ELOC·Toxic Financing·CB·워런트와 역분할 단위 경고를 분리한다.
- Float와 역분할 조정 기준이 확인되지 않거나 `scope_partial=true`이면 강한 신호로 올리지 않는다.
- 같은 종목을 엔진마다 다른 Float로 읽으면 `CROSS_ENGINE_FLOAT_MISMATCH`로 차단한다. 차이가 최근 역분할 비율과 맞으면 단위 미조정 가능성도 표시한다.
- 래빗스탁 화면에 희석 경고가 없더라도 안전하다고 보지 않는다. SEC 기준 ATM·ELOC·CB·워런트·락업·역분할·Shelf(선반등록)를 각각 `CLEAR/PRESENT/UNKNOWN`으로 고정하고, 하나라도 `UNKNOWN`이면 강한 신호를 차단한다.
- SEC 근거 시각이 스냅숏 뒤면 `future_supply_evidence_not_allowed`로 거부해 미래 정보가 과거 신호에 섞이지 않게 한다.
- 모든 결과에 `WATCH_ONLY=true`, `NO_ORDERS=true`, `NOT_VALIDATED`를 강제로 붙인다.

## 실행

```bash
python -m unittest -v test_evaluate_snapshot.py
python evaluate_snapshot.py frozen_snapshot.json
```

현재 코드는 평가 계약의 첫 단계다. 실제 성능 향상이나 적중률은 검증하지 않았다.

`whlr_2026-11-13T0008+09.json`은 자정 화면에서 확인한 WHLR 10거래일 신호를 고정한 연구용 입력이다. 다섯 엔진 동시 포착이어도 Float 단위가 일치하지 않아 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`engs_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 ENGS 사례다. SEC에는 2026년 사모발행·워런트 전량 현금 없는 행사와 9월 10일 효력이 생긴 최대 2억 달러 Shelf가 확인된다. 미확인 항목까지 남아 있으므로 `WATCH_ONLY_BLOCKED`가 되어야 한다.
