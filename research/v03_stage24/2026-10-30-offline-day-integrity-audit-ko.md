# LUCA V0.3 — 오프라인 날짜·반복 관찰 감사 (2026-10-30)

## 목적
한 번의 고정 기준 시각에서 만든 성적표에 날짜 장부만 여러 줄 붙여서
**마치 여러 거래일을 독립적으로 검증한 것처럼 보이는 오류**를 경고합니다.
실제 시세 API, SEC 요청, 3차 실측, 주문은 실행하지 않습니다.

## 사용 범위
- `offline_day_coverage.summarize_day_coverage(raw, manifest, day_ledger)`가
  기존 `day_coverage` 외에 `day_integrity_audit`을 반환합니다.
- `offline_session_integrity.audit_day_ledger(manifest, day_ledger)`는
  장부에 기재된 UTC 날짜를 **2026년 예정 NYSE 휴장일 표**와 오프라인 비교합니다.
  표는 저장소의 `nyse_session_gate.py`를 재사용합니다.
- 주말, 예정 휴장일, 미지원 연도, 단축 거래일을 별도로 표시합니다.
  예정 휴장일: https://www.nyse.com/trade/hours-calendars
- 같은 종목이 여러 날짜에 등장하면 고유 종목 수와 반복 관찰 건수를
  별도로 기록합니다. 100건의 기록이 100개의 독립 표본은 아닙니다.
- 고정 시각 1개로 다른 날짜의 관찰을 입증할 수 없으므로
  `SINGLE_REFERENCE_ANCHOR_CANNOT_VERIFY_OTHER_DAYS`를 경고합니다.

## 꼭 알아야 할 한계
1. `observation_date_utc`는 **UTC 날짜**이지 뉴욕 거래일이 아닙니다.
   UTC 날짜만으로 실제 거래일을 확정할 수 없습니다.
2. 2026년 예정 휴장일만 오프라인으로 확인합니다. 임시 휴장·거래 중단·
   실제 개장 여부는 확인하지 않습니다. 따라서 `actual_market_sessions_verified=false`.
3. 단축 거래일은 장중 마감 시간과 5/15/30/60분 결과 시각을 별도로
   확인해야 합니다. 여기서는 실제 가격 시각을 검사하지 않습니다.
4. 같은 종목의 여러 날 관찰은 서로 영향을 받을 수 있습니다.
   `extra_symbol_date_pairs_beyond_first`는 중복 위험을 알려주는 값이지
   통계적 유효 표본 수가 아닙니다.
5. 단일 manifest와 단일 raw에는 다중 세션의 원본 자료가 없습니다.
   `independent_session_count_verified=0`은 보수적인 **미검증 표시**이지
   실제로 시장이 열리지 않았다는 뜻이 아닙니다.
6. 이전 `day_coverage.distinct_observation_days`는 장부에 적힌 날짜 수를
   그대로 보여줍니다. **검증된 거래일 수로 인용하면 안 됩니다.**

## 안전 상태
`NOT_VALIDATED`, `SEC_UNVERIFIED`, `D`, `NO_ORDERS` 유지.
예측 성공률·실전 체결 수익·통계적 유의성을 주장하지 않습니다.
연구 브랜치 `research/v03-stage24-evidence` 및 Ruleset은 변경하지 않습니다.

## 오프라인 재현
```bash
python -m unittest discover -s research/v03_stage24 -p 'test_*.py' -v
```
실제 독립 거래일 검증에는 **각 날짜별 고유 원본 자료와 기준 시각 봉인**,
뉴욕 시간대 변환, 공식 장 운영 확인, 종목 반복 관찰의 상관성 평가가
추가로 필요합니다. 이 문서는 완료 선언이 아니라 다음 연구 단계의 경계입니다.
