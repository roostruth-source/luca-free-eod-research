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
- 공식 OS(발행주식 수)와 완전희석 주식 수를 함께 고정해 `fully_diluted_multiple`을 계산한다. 2배 이상이면 `HIGH_FULLY_DILUTED_MULTIPLE`로 차단한다.
- 여러 역분할 비율을 곱한 누적 계수가 250 이상이면 `SERIAL_REVERSE_SPLIT_EXTREME`로 차단한다.
- Pre-funded Warrant(선납형 워런트)는 행사대금이 거의 0이면 경제적으로 주식과 비슷하다. 공시 숫자로 계산한 미행사 추정분은 확정치와 분리하고 `PREFUNDED_WARRANT_SHARE_EQUIVALENT`로 차단한다.
- 완전희석 주식 수가 OS보다 얼마나 많은지 `potential_dilution_pct`로 함께 남긴다.
- Toxic Financing(주가 하락 시 전환가가 함께 낮아져 새 주식이 늘 수 있는 불리한 자금조달)을 공식 공급 점검 항목에 추가한다.
- 완전희석 잠재 증가율이 25% 이상이면 연구용 보수 기준 `SIGNIFICANT_POTENTIAL_DILUTION`으로 차단한다. 25%는 성능이 검증된 최적값이 아니라 이후 백테스트할 사전 고정 기준이다.
- 화면의 ATM·ELOC·Toxic·CB·워런트 경고와 SEC에서 확인한 실제 자금조달 종류가 일치하지 않으면 `SCREEN_SUPPLY_LABEL_UNRECONCILED`로 남긴다.
- 차단 이유는 `block_reasons` 배열로 남겨 같은 입력에서 같은 판정을 재현한다.
- 모든 결과에 `WATCH_ONLY=true`, `NO_ORDERS=true`, `NOT_VALIDATED`를 강제로 붙인다.

## 실행

```bash
python -m unittest -v test_evaluate_snapshot.py
python evaluate_snapshot.py frozen_snapshot.json
```

현재 코드는 평가 계약의 첫 단계다. 실제 성능 향상이나 적중률은 검증하지 않았다.

## 후속 수익률 평가

`evaluate_followups.py`는 신호 뒤 완료된 1·3·5·10거래일 일봉만 사용한다. 모든 가격은 신호 시점 기준으로 역분할·분할 조정됐다는 `SPLIT_ADJUSTED_TO_SIGNAL` 표시가 있어야 한다. 장중 미완성 일봉, 평가시각 뒤의 미래 일봉, 신호 이전 일봉은 거부한다.

각 기간의 종가 기준 수익률과 MFE(기간 중 최대 상승폭), MAE(기간 중 최대 하락폭)를 계산한다. 엔진 1개·2개·3개 이상, Preview+Signal, Signal+Burning Up, 희석 경고 유무로 분리해 표본 수·양수 종가 비율·평균·중앙값·가장 큰 수익 1건 제외 평균을 만든다.

화면 진입가는 실제 체결가가 아니므로 `SCREEN_REFERENCE_PRICE` 결과를 적중률이나 실거래 수익률로 부르지 않는다. 완료된 일봉이 부족하면 `NOT_MATURE`로 남긴다.

```bash
python -m unittest -v test_evaluate_followups.py
python evaluate_followups.py frozen_followups.json
```

## 공개 시세 교차검증

`reconcile_daily_bars.py`는 후속 수익률 계산 전에 서로 독립적인 공개 시세 출처가 최소 2개인지 확인한다. OHLC(시가·고가·저가·종가) 중 하나라도 사전에 고정한 1% 허용범위를 넘겨 다르면 `SOURCE_CONFLICT`로 막고 대표 일봉을 만들지 않는다. 한 출처밖에 없으면 `SINGLE_SOURCE_UNVERIFIED`로 남긴다. 1%는 성능을 높였다고 검증된 값이 아니라 데이터 오류를 찾기 위한 보수적 연구 기준이다.

```bash
python -m unittest -v test_reconcile_daily_bars.py
python reconcile_daily_bars.py whlr_2026-11-12_price_conflict.json
```

`whlr_2026-11-12_price_conflict.json`은 2026-11-12 WHLR 일봉에 대해 ChartExchange와 Investing이 서로 다른 OHLC를 제시한 실제 충돌 사례다. 종가도 약 5.84% 차이가 나므로 1거래일 수익률을 확정하지 않고 `SOURCE_CONFLICT`로 보류한다.

`inlf_2026-11-12_price_conflict.json`은 같은 날짜 INLF 일봉의 두 공개 출처가 종가 $0.4300과 $0.4943을 제시한 사례다. 약 14.95% 차이라 대표 일봉을 만들지 않는다. 각 관측값에는 HTTPS 원문 URL과 조회시각을 의무 저장하며, 이름만 다르고 URL이 같은 자료는 독립 출처로 인정하지 않는다.

`engs_2026-11-12_price_conflict.json`은 Investing의 정규장 종가 $0.504와 Public의 정규장 종가 $0.68이 약 34.92% 다른 사례다. 종가만 제공하는 보조 출처도 이미 관측된 필드의 충돌을 입증하는 데 쓸 수 있다. 다만 두 출처가 종가만 일치하더라도 시가·고가·저가가 각각 2개 출처에서 확인되지 않으면 `INSUFFICIENT_FIELD_COVERAGE`로 막아 완성 일봉을 만들지 않는다.

`whlr_2026-11-13T0008+09.json`은 자정 화면에서 확인한 WHLR 10거래일 신호를 고정한 연구용 입력이다. 다섯 엔진 동시 포착이어도 Float 단위가 일치하지 않아 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`engs_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 ENGS 사례다. SEC에는 2026년 사모발행·워런트 전량 현금 없는 행사와 9월 10일 효력이 생긴 최대 2억 달러 Shelf가 확인된다. 미확인 항목까지 남아 있으므로 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`inlf_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 INLF 10거래일 4엔진 사례다. SEC 기준 완전희석 주식 수는 직전 Class A OS의 약 29.1배이고, 2026년 두 역분할의 누적 계수는 1대3,200이다. `HIGH_FULLY_DILUTED_MULTIPLE`, `SERIAL_REVERSE_SPLIT_EXTREME` 및 미확인 공급 항목 때문에 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`huhu_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 HUHU 10거래일 4엔진 사례다. SEC에는 400,000주와 Pre-funded Warrant 1,600,000개의 등록직접공모가 확인된다. 2026-06-30 OS와 공모 발행 숫자를 맞대면 아직 주식으로 바뀌지 않은 선납형 워런트는 707,901개로 계산되지만, 이는 공시 숫자에서 얻은 추정치다. 거의 0인 행사가 때문에 주식처럼 취급하고 미확인 공급 항목과 함께 `WATCH_ONLY_BLOCKED`로 둔다.

`bdmd_2026-11-13T0008+09.json`은 화면상 ATM 경고가 켜진 BDMD 10거래일 4엔진 사례다. SEC에서 확인된 핵심은 ATM이 아니라 VWAP 연동 전환가를 가진 CB다. 최대 전환 시 OS 대비 잠재 주식이 약 86.33% 늘 수 있어 `SIGNIFICANT_POTENTIAL_DILUTION`, `SCREEN_SUPPLY_LABEL_UNRECONCILED` 및 미확인 공급 항목으로 `WATCH_ONLY_BLOCKED`가 되어야 한다.
