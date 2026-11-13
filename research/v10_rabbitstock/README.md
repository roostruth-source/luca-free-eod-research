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
- `exchange_status`에 거래소 상태·효력시각·원문 공개시각·공식 URL을 고정한다. 상태를 확인하지 못하면 `TRADING_STATUS_UNVERIFIED`, 거래정지·상장폐지·OTC 전환이 이미 효력을 냈으면 `TRADING_UNAVAILABLE`, 효력 전이라도 정지가 공식 발표됐으면 `TRADING_RESTRICTION_PENDING`으로 강한 신호를 차단한다.
- 거래상태 근거가 화면 기준시각 뒤에 공개됐으면 `future_exchange_status_evidence_not_allowed`로 거부한다. 현재 페이지에서 나중에 확인한 상태를 과거 신호가 이미 알았던 정보처럼 쓰지 않는다.

## 기업행사 연쇄 조정

`adjust_corporate_actions.py`는 Reverse Split(역분할)과 Ticker Change(티커 변경)를 시간순으로 연결해 과거 가격·주식 수를 신호 시점 단위로 바꾼다. 가격은 역분할 누적계수를 곱하고, OS·Float·워런트 같은 주식 수는 같은 계수로 나눈다. 티커 변경은 `same_security=true`가 확인된 경우에만 같은 증권으로 잇는다. `evidence_available_at`에는 SEC 접수시각이나 공식 발표일의 보수적 마감시각을 넣는다. 신호 뒤에 이용 가능해진 근거, 신호 뒤 기업행사, 끊어진 티커 계보는 모두 거부한다.

Aggregate Share Count(합계 주식 수)를 역분할 비율로 단순 나누면 구성 항목별 단주 처리 때문에 공식 재작성 수치와 차이가 날 수 있다. SEC가 역분할 뒤 총수를 다시 제시한 경우 `official_restated_value`와 원문·공개시각·반영된 마지막 역분할을 함께 저장한다. 기계적 계산값은 `mechanical_adjusted_value`로 보존하고 최종 비교에는 공식 수치를 사용한다. 공식 재작성 근거가 미래이거나 최신 역분할까지 반영하지 않았으면 거부한다.

CDT의 2026년 10월 2일 424B3는 1대25 역분할을 반영한 재판매 등록 673,023주를 제시했다. 11월 9일 424B3는 이어진 1대20 역분할을 반영해 같은 묶음을 33,649주로 다시 제시했다. 단순 나눗셈 `673,023 ÷ 20 = 33,651.15`와 2.15주 차이가 나므로 공식 구성별 재작성값을 우선한다. 이 수치는 Float가 아니며 실제 발행 완료 수량도 아니다.

CDT는 2026년에 3월 1대25, 7월 1대10, 9월 1대25, 11월 1대20의 Reverse Split(역분할)을 시행했다. 2026년 전체 누적계수는 1대125,000이다. 앞 문단의 1대500은 10월 문서에서 11월 문서로 옮기는 데 필요한 9월·11월 두 행사만 뜻한다.

`normalize_financing_terms.py`는 계약 숫자를 Price Term(계약상 가격 조건)과 Share Count(주식 수)로 나누고, 계약 원문이 역분할 조정을 허용하는지 `ADJUSTS/DOES_NOT_ADJUST/UNKNOWN`으로 고정한다. CDT의 3월 ELOC Floor Price(최저 허용가격) $0.60은 원문상 이후 역분할에 맞춰 조정하지 않는 조건이다. 이를 일반 주가처럼 125,000배 하면 $75,000이라는 잘못된 값이 되므로, 계약값은 $0.60으로 유지한다. 조정 조항이 확인되지 않으면 `SPLIT_ADJUSTMENT_CONTRACT_UNKNOWN`, 후속 공식 수치와 충돌하면 `TERM_BASIS_CONFLICT`로 차단한다.

```bash
python -m unittest -v test_normalize_financing_terms.py
python normalize_financing_terms.py cdt_eloc_term_basis_2026.json
```

`reconcile_supply_bundles.py`는 한 공시의 ATM·ELOC 등 구성 항목을 개별 수량과 합계로 동시에 보존한다. CDT의 7월 15일 10-Q는 4월 ELOC 39,907주와 5월 ATM 275,121주를 제시했다. 7월 1대10 역분할을 반영한 8월 12일 10-Q는 ELOC 3,000주와 1~6월 ATM 28,501주를 제시했다. 개별 항목은 단순 10분의 1과 크게 다르지만, 두 항목의 합계는 31,502.8주와 31,501주로 1.8주 차이에 불과하다. 분류가 바뀌었거나 기간 범위가 달라진 가능성이 있으므로 개별 항목을 확정 원장으로 쓰지 않고 `BUNDLE_SCOPE_NOT_COMPARABLE`, `COMPONENT_BASIS_CONFLICT`, `COMPONENT_CLASSIFICATION_SHIFT_POSSIBLE`로 차단한다. 합계가 가깝다는 사실은 진단값일 뿐 최신 Float나 실제 잔여 발행량이 아니다.

```bash
python -m unittest -v test_reconcile_supply_bundles.py
python reconcile_supply_bundles.py cdt_supply_bundle_reconciliation_2026.json
```

`reconcile_os_timeline.py`는 공식 OS(발행주식 수) 체크포인트를 역분할 뒤 단위로 맞춘다. CDT는 2026년 8월 12일 786,670주에서 8월 31일 13,693,866주로 1,640.74% 늘었다. 이 기간 순증가 12,907,196주 중 공식 확인된 Pre-funded Warrant(선납형 워런트) 행사 12,131,122주가 93.99%를 차지한다. 9월 1대25 역분할을 반영한 8월 31일 기준값 547,754.64주와 9월 30일 1,477,789주를 비교하면 순증가율은 169.79%다. 이어 10월 23일에는 9,322,805주로 다시 530.86% 늘었다. 이것은 Gross Issuance(총 신규발행)가 아니라 취소·단주 처리까지 합쳐진 Net OS Change(순 발행주식 수 변화)다.

각 수치는 관측일과 SEC 공개시각을 별도로 저장한다. 예를 들어 9월 30일 수치는 10월 7일 공시 전 신호에는 쓸 수 없다. 25% 급증 기준은 성능 최적값이 아니라 공급 불안정을 막기 위한 연구용 안전선이며, 해당 구간은 `RAPID_OS_EXPANSION`과 `OS_MORE_THAN_DOUBLED`로 관찰 전용 차단한다.

```bash
python -m unittest -v test_reconcile_os_timeline.py
python reconcile_os_timeline.py cdt_os_timeline_2026.json
```

`evaluate_cb_reset_event.py`는 CB Reset(전환사채 가격 재조정) 사건을 계약 조건과 후속 가격으로 분리한다. ZBAO의 2026년 9월 17일 전환사채는 Share Combination Event(역분할 같은 주식 병합 사건) 뒤 16번째 거래일에 기존 전환가보다 Event Market Price(사건 시장가격)가 낮으면 전환가를 낮추도록 정했다. 사건 시장가격은 앞선 15거래일 중 VWAP(거래량가중평균가격)가 가장 낮은 5일의 평균이다. 따라서 일봉 OHLC만으로 실제 리셋 전환가를 만들 수 없으며 VWAP 원자료가 없으면 `RESET_PRICE_UNVERIFIED_VWAP_MISSING`으로 남긴다.

`resolve_reset_session_anchor.py`는 역분할 당일을 1일째로 넣을지 생기는 하루 차이를 따로 검증한다. 계약 원문이 `after/following such Share Combination Event Date`처럼 사건일 **뒤**라고 명시하면 사건 당일은 세지 않는다. YFOR/YYGH의 6월 23일 역분할을 당일부터 세면 후보일은 7월 15일이지만, SEC 계약은 사건일 뒤 16번째 거래일이라고 적어 최종 계약상 후보일은 7월 16일이다. 문구가 애매하면 두 날짜를 모두 남기고 `RESET_DATE_ANCHOR_AMBIGUOUS`로 후속 수익률 계산을 막는다. 나스닥 최저가 준수기간처럼 목적이 다른 16일 계산은 전환사채 계약 날짜의 근거로 재사용하지 않는다.

`evaluate_cb_reset_event.py`도 이제 SEC 계약 문구로 확인된 `AFTER_EVENT_DATE` 기준이 없으면 실행을 거부한다. 이 안전장치는 성능을 높이는 신호가 아니라 Off-by-one Error(하루 밀림 오류)로 기준가격과 후속 수익률이 달라지는 것을 막기 위한 데이터 품질 규칙이다.

```bash
python -m unittest -v test_resolve_reset_session_anchor.py
python resolve_reset_session_anchor.py yfor_reset_session_anchor_2026.json
```

ZBAO의 1대50 역분할 효력일 2026년 10월 9일 다음 16번째 거래일은 11월 2일이다. 교차확인한 공개 일봉에서 11월 2일 종가 $0.26 다음 날 장중 고가가 $0.452로 MFE(기간 중 최대 상승폭) +73.85%였고 거래량은 약 228.80배로 증가했지만 종가는 $0.26으로 0%였다. 3거래일 종가는 -12.69%, 5거래일 종가는 -11.62%였다. 즉 이 한 사례는 ‘리셋 다음 날 장중 급등’은 보여 주지만 ‘5~10일 지속 상승’을 입증하지 않는다. 10거래일은 아직 끝나지 않아 `NOT_MATURE`다.

```bash
python -m unittest -v test_evaluate_cb_reset_event.py
python evaluate_cb_reset_event.py zbao_cb_reset_event_2026.json
```

`build_cb_reset_cohort.py`는 “역분할 뒤 16번째 거래일”이라는 문구만 같다고 같은 사례로 묶지 않는다. 계산창 길이, 낮은 VWAP 선택 일수, 전환가가 내려가기만 하는지, Floor Constraint(최저 전환가 제한)가 있는지까지 모두 같아야 같은 Contract Fingerprint(계약 지문)로 인정한다. 계약 효력일 이전의 역분할도 후속 결과 표본에서 제외한다.

ZBAO와 HUSA의 계약은 16거래일·15거래일 창·최저 5일 평균·하향만 가능·별도 바닥 제한 없음이 일치했다. 그러나 HUSA의 1대10 역분할은 2025년 6월 6일이고 해당 전환사채 발행일은 7월 10일이라 계약 적용 전 사건이다. NIVF는 같은 16·15·5 구조이지만 Floor Price(최저 전환가 바닥)가 있고, GCTK는 계산창이 20거래일이며 바닥 제한도 있어 ZBAO와 같은 집단에서 제외된다. 따라서 현재 독립 비교 사건은 0건이며, ZBAO 1건으로 “5~10일 펌핑 법칙”을 확정할 수 없다.

```bash
python -m unittest -v test_build_cb_reset_cohort.py
python build_cb_reset_cohort.py cb_reset_contract_cohort_2026.json
```

YFOR의 이전 티커 YYGH도 2026년 6월 23일 1대30 역분할 뒤 같은 16·15·5 구조가 작동할 예정이었다. 그러나 계약상 Floor Price(최저 전환가 바닥)는 앞선 1대50 역분할 뒤 $4.60, 두 번째 1대30 역분할 뒤 $138로 올라갔다. 16번째 거래일인 7월 16일 전 측정 구간의 일별 고가는 모두 $2.09 이하였으므로 VWAP 원자료가 없어도 Event Market Price가 $138 아래라는 사실은 수학적으로 확정할 수 있다. 실제 전환가는 시장가격까지 내려갈 수 없고 Floor Price Event(최저가 충돌 사건)가 발생했다.

8월 20일 공시는 보유자가 전환사채 전체 상환을 요구했고 회사가 원금·이자에 125% Redemption Premium(상환 가산금)을 적용한 $6,794,775.79를 상환하기로 했다고 확인한다. 이 정보는 7월 16일 당시에는 공개되지 않았으므로 `retrospective_disposition`으로만 저장한다. 7월 16일 기준으로 이미 알 수 있었던 $138 바닥과 $2.09 이하 가격 상한만으로 `FLOOR_BINDING_RESET_NOT_COMPARABLE`을 판정한다.

공개 일봉 2곳을 맞춘 참고 성과는 7월 16일 종가 $1.07 기준 1거래일 -0.93%, 3거래일 +19.63%, 5거래일 +19.63%, 10거래일 +16.82%다. 10거래일 MFE(기간 중 최대 상승폭)는 +45.79%, MAE(기간 중 최대 하락폭)는 -4.67%다. 하지만 실제 처리는 전환가 리셋이 아니라 바닥 충돌 후 상환이었으므로 이 수익률을 “CB 리셋 펌핑 적중”으로 세지 않는다.

```bash
python evaluate_cb_reset_event.py yfor_cb_reset_event_2026.json
```

YFOR는 2026년 3월 23일 1대50, 6월 23일 1대30 역분할 뒤 9월 2일 YYGH에서 YFOR로 티커가 바뀌었다. 따라서 3월 첫 역분할 전 자료를 11월 신호 단위로 바꾸는 누적계수는 1대1,500이다. `yfor_corporate_actions_2026.json`의 가격 $1와 주식 수 1,500,000은 실제 시세·OS가 아니라 계수 작동만 검증하는 단위 시험값이다. 실제 후속 수익률에는 검증된 원시 시세를 별도로 넣어야 한다.

공시가 과거의 주식 수·주당 수치를 역분할 후 단위로 소급해 다시 적은 경우에는 관측값의 `split_basis_effective_through`에 이미 반영된 마지막 역분할 시각을 넣는다. 이 시각 이전의 역분할은 다시 적용하지 않아 이중 조정을 막는다. `basis_effective_through`는 이전 입력 호환용 별칭이며 두 필드 값이 다르면 거부한다.

소급조정 기준을 임의로 넣어 역분할을 건너뛰지 못하도록 `split_basis_scope=RETROACTIVE_SPLIT_ADJUSTED`, SEC 원문 URL, 원문 이용 가능 시각을 필수로 저장한다. 원문 시각이 평가 기준 뒤이거나, 기준시각이 검증된 역분할 효력시각과 맞지 않으면 거부한다. 이 기준은 가격·주식 수 단위에만 적용하고 Ticker Change(티커 변경) 계보는 관측시각부터 별도로 연결한다. `yfor_retroactive_basis_guard_2026.json`은 SEC가 두 역분할을 반영해 다시 적었다고 밝힌 시험값 3,000주가 1,500으로 다시 나뉘지 않는지 확인한다. 이 3,000주는 실제 YFOR OS가 아니다.

```bash
python -m unittest -v test_adjust_corporate_actions.py
python adjust_corporate_actions.py yfor_corporate_actions_2026.json
```

## 실행

```bash
python -m unittest -v test_evaluate_snapshot.py
python evaluate_snapshot.py frozen_snapshot.json
```

현재 코드는 평가 계약의 첫 단계다. 실제 성능 향상이나 적중률은 검증하지 않았다.

## 실행 가능한 통합 연구판

`run_research_build.py`는 이 폴더의 동결 스냅숏 중 필수 필드가 있는 자료를 자동으로 읽어 NASDAQ 7.0과 중국계 1.0 연구 경로로 나눈 뒤 한 번에 평가한다. 중국계 1.0은 SEC 원문에서 PRC Operations(중국 사업)가 확인되고 그 근거가 스냅숏 시각보다 먼저 공개됐을 때만 사용한다. 공통 평가에는 5개 엔진 동시 포착, SEC 공급·희석, Float(실제 유통주식 수), 역분할, 거래상태, 미래정보 차단이 들어간다.

후보 정렬은 엔진 수가 많은 순서, 같은 수면 최고 엔진 순위가 높은 순서다. 이것은 급등 확률이나 추천 점수가 아니다. 위험 확인이 끝나지 않은 종목은 순위에 보여도 `WATCH_ONLY_BLOCKED`로 남는다.

```bash
python -m unittest discover -v
python run_research_build.py \
  --input-dir . \
  --output build_outputs/latest_research_build.json \
  --built-at "2026-11-14T00:30:00+09:00"
```

2026년 11월 14일 00:30 KST 동결 실행에서는 실제 래빗스탁 화면 기반 스냅숏 6개를 오류 없이 평가했다. NASDAQ 7.0 경로 4개, 중국계 1.0 경로 2개였으며 WHLR 5개 엔진, ENGS·HUHU·BDMD·INLF 4개 엔진, NXXT 2개 엔진 순으로 정렬됐다. 그러나 6개 모두 거래상태·Float·희석·역분할 등 미해결 위험 때문에 관찰 전용 차단 상태다. 전체 자동검사 100개가 통과했다.

GitHub Actions용 `.github/workflows/luca-v10-research-build-ci.yml`은 모든 검사를 실행하고 같은 동결 실데이터 보고서를 만든 뒤 `WATCH_ONLY`, `NO_ORDERS`, `NOT_VALIDATED`를 다시 확인한다. 라이브 전 종목 탐색, SEC 문서 자동 추출, 예측 정확도 검증, 체결·슬리피지 모델은 아직 미완성이다.

## 거래량 이상 급증과 늦은 신호 차단

`evaluate_volume_anomaly.py`는 정규장이 끝난 일봉 거래량을 서로 다른 공개 제공자 2곳에서 확인한 뒤, 직전 10거래일 평균의 5배 이상인지 계산한다. 5배 기준은 성능을 맞춘 최적값이 아니라 이후 검증할 사전 고정 기준이다. 두 출처가 1% 넘게 다르거나, 출처 공개시각이 평가시각보다 늦거나, 장중 미완성 자료이면 결과를 만들지 않는다.

거래량이 커도 직전 거래일 주가가 이미 20% 이상 올랐다면 `ALREADY_SURGED_PREVIOUS_SESSION`으로 막는다. 이는 급등 전에 잡은 신호와 이미 오른 뒤 따라붙은 신호를 섞지 않기 위한 오탐 차단이다. Float(실제 유통주식 수)가 공식적으로 확인되지 않으면 거래량 회전율을 계산하지 않고 `FLOAT_TURNOVER_UNVERIFIED`로 둔다.

CODX 2026년 11월 10일 동결 사례에서 거래량은 74,930,653주, 직전 10거래일 평균은 2,946,651.55주로 25.429배였다. 하지만 전날인 11월 9일 주가가 이미 24.221% 올라 있었고 Float도 확인되지 않아 `WATCH_ONLY_BLOCKED`로 판정했다. 즉 거래량 이상은 확인했지만 급등 전 조기포착 성공으로 세지 않는다.

```bash
python -m unittest -v test_evaluate_volume_anomaly.py
python evaluate_volume_anomaly.py codx_volume_anomaly_2026-11-10.json
```

V40 전체 자동검사 107개와 동결 실데이터 통합 실행은 통과했다. 통합 보고서에는 기존 엔진 후보 6개와 CODX 거래량 사건 1개가 함께 저장되며, 주문 안전장치는 계속 강제된다.

## 후속 수익률 평가

`evaluate_followups.py`는 신호 뒤 완료된 1·3·5·10거래일 일봉만 사용한다. 모든 가격은 신호 시점 기준으로 역분할·분할 조정됐다는 `SPLIT_ADJUSTED_TO_SIGNAL` 표시가 있어야 한다. 장중 미완성 일봉, 평가시각 뒤의 미래 일봉, 신호 이전 일봉은 거부한다.

각 기간의 종가 기준 수익률과 MFE(기간 중 최대 상승폭), MAE(기간 중 최대 하락폭)를 계산한다. 엔진 1개·2개·3개 이상, Preview+Signal, Signal+Burning Up, 희석 경고 유무로 분리해 표본 수·양수 종가 비율·평균·중앙값·가장 큰 수익 1건 제외 평균을 만든다. 희석 경고는 화면 표시인 `screen_dilution_warning`과 SEC 등 공식 자료에서 확인한 `official_dilution_warning`을 따로 집계한다. 둘 중 하나라도 켜지면 통합 `dilution_warning`은 `YES`가 된다.

화면 진입가는 실제 체결가가 아니므로 `SCREEN_REFERENCE_PRICE` 결과를 적중률이나 실거래 수익률로 부르지 않는다. 완료된 일봉이 부족하면 `NOT_MATURE`로 남긴다.

```bash
python -m unittest -v test_evaluate_followups.py
python evaluate_followups.py frozen_followups.json
```

## 공개 시세 교차검증

`reconcile_daily_bars.py`는 후속 수익률 계산 전에 서로 독립적인 공개 시세 출처가 최소 2개인지 확인한다. OHLC(시가·고가·저가·종가) 중 하나라도 사전에 고정한 1% 허용범위를 넘겨 다르면 `SOURCE_CONFLICT`로 막고 대표 일봉을 만들지 않는다. 한 출처밖에 없으면 `SINGLE_SOURCE_UNVERIFIED`로 남긴다. 1%는 성능을 높였다고 검증된 값이 아니라 데이터 오류를 찾기 위한 보수적 연구 기준이다. URL이 달라도 같은 회사·데이터 제공자의 시세면 독립 출처로 세지 않도록 `provider_id`를 의무화한다. 지역판·실시간 화면·과거시세 화면이 서로 다른 주소여도 같은 제공자면 1개다.

```bash
python -m unittest -v test_reconcile_daily_bars.py
python reconcile_daily_bars.py whlr_2026-11-12_price_conflict.json
```

`whlr_2026-11-12_price_conflict.json`은 2026-11-12 WHLR 일봉에 대해 ChartExchange와 Investing이 서로 다른 OHLC를 제시한 실제 충돌 사례다. 종가도 약 5.84% 차이가 나므로 1거래일 수익률을 확정하지 않고 `SOURCE_CONFLICT`로 보류한다.

`inlf_2026-11-12_price_conflict.json`은 같은 날짜 INLF 일봉의 두 공개 출처가 종가 $0.4300과 $0.4943을 제시한 사례다. 약 14.95% 차이라 대표 일봉을 만들지 않는다. 각 관측값에는 HTTPS 원문 URL과 조회시각을 의무 저장하며, 이름만 다르고 URL이 같은 자료는 독립 출처로 인정하지 않는다.

`engs_2026-11-12_price_conflict.json`은 Investing의 정규장 종가 $0.504와 Public의 정규장 종가 $0.68이 약 34.92% 다른 사례다. 종가만 제공하는 보조 출처도 이미 관측된 필드의 충돌을 입증하는 데 쓸 수 있다. 다만 두 출처가 종가만 일치하더라도 시가·고가·저가가 각각 2개 출처에서 확인되지 않으면 `INSUFFICIENT_FIELD_COVERAGE`로 막아 완성 일봉을 만들지 않는다.

자료를 조회한 시각과 자료 자체가 가리키는 시각은 다르다. 각 출처의 `source_data_asof`가 정규장 마감보다 이르면 페이지가 일별 표처럼 보여도 `SOURCE_NOT_FINAL`로 차단한다. 출처 자체의 기준시각을 확인할 수 없으면 `SOURCE_TIMESTAMP_UNVERIFIED`로 남긴다. 자료 기준시각이 실제 조회시각보다 뒤라면 미래 자료이므로 `source_data_asof_after_retrieval` 오류로 거부한다. 이 규칙을 적용하면 ENGS의 Investing 값은 오후 3시 20분 장중 스냅숏이고, Public의 오후 8시 표시는 당시 조회시각 오후 6시 7분보다 미래다. INLF의 Investing 값도 오전 10시 10분 장중 스냅숏이므로 완료 일봉 충돌 증거가 아니라 미완성 자료다.

`audit_source_revisions.py`는 같은 URL의 반복 조회값이 바뀌는 과정을 보존한다. 같은 출처를 여러 번 조회해도 독립 출처 수는 1개다. `inlf_yahoo_revision_2026-11-12.json`에서는 Yahoo의 장중 종가 $0.4285가 마감 $0.4110으로 약 4.08% 수정됐다. 이 수정은 오류 적중이나 별도 표본으로 세지 않고, 마감 뒤 최신값만 교차검증 후보로 넘긴다.

ENGS에서는 Investing의 실시간 종목 화면과 과거시세 화면이 서로 다른 URL인데도 11월 12일 값이 다르게 표시됐다. 두 URL을 독립 출처 2개로 세면 안 되므로 같은 `provider_id=investing`으로 묶고 `duplicate_provider_not_independent`로 거부한다. MarketScreener의 국가별 지역판도 같은 방식으로 한 제공자로 취급한다.

`inlf_2026-11-12_verified.json`은 Yahoo와 MarketScreener가 정규장 마감 뒤 공개한 INLF 일봉을 교차검증한 입력이다. 두 출처의 종가 $0.4110이 일치하고 시가·고가·저가도 1% 안에서 일치해 대표 일봉을 만든다. `inlf_2026-11-12_followup.json`은 이 대표 일봉만 사용한 1거래일 참고 성과 입력이다. 화면 진입가 $0.5313은 실제 체결가가 아니므로 결과는 적중률이나 실거래 수익률이 아니다.

`whlr_2026-11-13T0008+09.json`은 자정 화면에서 확인한 WHLR 10거래일 신호를 고정한 연구용 입력이다. 다섯 엔진 동시 포착이어도 Float 단위가 일치하지 않아 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`engs_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 ENGS 사례다. SEC에는 2026년 사모발행·워런트 전량 현금 없는 행사와 9월 10일 효력이 생긴 최대 2억 달러 Shelf가 확인된다. 미확인 항목까지 남아 있으므로 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`inlf_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 INLF 10거래일 4엔진 사례다. SEC 기준 완전희석 주식 수는 직전 Class A OS의 약 29.1배이고, 2026년 두 역분할의 누적 계수는 1대3,200이다. `HIGH_FULLY_DILUTED_MULTIPLE`, `SERIAL_REVERSE_SPLIT_EXTREME` 및 미확인 공급 항목 때문에 `WATCH_ONLY_BLOCKED`가 되어야 한다.

`huhu_2026-11-13T0008+09.json`은 화면상 희석 경고가 없던 HUHU 10거래일 4엔진 사례다. SEC에는 400,000주와 Pre-funded Warrant 1,600,000개의 등록직접공모가 확인된다. 2026-06-30 OS와 공모 발행 숫자를 맞대면 아직 주식으로 바뀌지 않은 선납형 워런트는 707,901개로 계산되지만, 이는 공시 숫자에서 얻은 추정치다. 거의 0인 행사가 때문에 주식처럼 취급하고 미확인 공급 항목과 함께 `WATCH_ONLY_BLOCKED`로 둔다.

`bdmd_2026-11-13T0008+09.json`은 화면상 ATM 경고가 켜진 BDMD 10거래일 4엔진 사례다. SEC에서 확인된 핵심은 ATM이 아니라 VWAP 연동 전환가를 가진 CB다. 최대 전환 시 OS 대비 잠재 주식이 약 86.33% 늘 수 있어 `SIGNIFICANT_POTENTIAL_DILUTION`, `SCREEN_SUPPLY_LABEL_UNRECONCILED` 및 미확인 공급 항목으로 `WATCH_ONLY_BLOCKED`가 되어야 한다.

