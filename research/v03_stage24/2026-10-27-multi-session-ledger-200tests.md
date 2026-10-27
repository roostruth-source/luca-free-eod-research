# LUCA V0.3 — 실제 미래방향 연구 기록장 (200개 시험)

2026-10-27 KST. **연구 전용 / NOT_VALIDATED / SEC_UNVERIFIED / 실제 주문 금지**

## 이번 단계
- 신규: `research/v03_stage24/multi_session_ledger.py` + `test_multi_session_ledger.py`.
- 전체 독립 연구 오프라인 안전시험 **200/200 통과**:
  https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40488470947
- 전향 T0 후보 동결, 이후 16분 IEX 관찰, 5/15/30/60분 신호 후속, 같은 시각 기준 전체 종목 비교 자료를 **동일 GitHub source run ID**로 재검증한 다음 누적.
- 원본 파일 `frozen_t0.json`, `forward_review.json`, `followup_source_metadata.json` 필수. `outcomes.json` 및 `fixed_clock_reference.json` 선택적이며 누락 시 실제 결과 0%로 해석하지 않고 별도 미확인 상태로 표시.
- GitHub source run 성공/브랜치/워크플로 이름/숫자 ID, T0 해시, 종목·시각·IEX 분봉 완전성, 위험 상태 모두 검증.
- **같은 run ID, 같은 T0 해시, 같은 뉴욕 거래일 중복 누적 차단**. 다른 거래일의 독립된 원본만 추가.
- 날짜별 후보/패턴/무패턴/자료부족, 신호 후속 5·15·30·60분 자료의 완성·누락 건수, 고정시각 전체 후보 비교의 완성·누락 건수만 누적.
- **수익률, 승률, 확률, 유의미한 성능 향상, 실제 체결 성과는 계산하거나 주장하지 않음**. IEX 단일 거래소, 시총/Float/SEC 위험 미확인, 무작위 대조군 아님.
- **실패한 GitHub Actions 실행은 성공 source run 기록장에 포함되지 않음**. 실패한 시험까지 포함한 전체 시험 성공률을 계산하면 생존편향이 생기므로 반드시 별도의 실패실행 목록을 만들기 전까지 `failed_run_counts_not_available=true`.

## 실행 경로
- 연구 브랜치의 기존 후속 1회성 workflow `.github/workflows/luca-v03-followup-once.yml`에 **선택적** 1세션 기록 스텝 추가. T0 source 아티팩트와 GitHub source metadata를 읽고 성공한 후속 검증이 있으면 같은 실행의 `luca_v03_ledger/ledger.json`을 함께 보존.
- 1회 실행에서 한 건만 쌓이며, 여러 거래일 누적은 **미래에 실제 독립 source run이 생긴 이후** Work가 파일들을 모아 CLI로 별도 집계해야 함. 이 단계에서 새로운 반복 예약을 만들지 않았음.
- 예시 CLI (실제 GitHub 아티팩트를 수동/Work가 내려받아 `<source_run_id>` 디렉터리에 검증 자료를 모은 경우에만):
  `python3 research/v03_stage24/multi_session_ledger.py --input-root verified_source_runs --output research_outputs/multi_session_ledger.json`
- 아직 실제 T0 실측 결과가 확보되지 않았으므로 **실제 연구 기록 0건**. 200개는 실전 적중이 아니라 오프라인 검수 테스트임.

## 앞으로
1. 기존 예약된 1회성 장중 T0 실측 성공 여부를 GitHub에서 확인. 중복 실행 금지.
2. 실측 성공·실패·자료 부족을 모두 명시해 기록하고, 60분 후속 데이터가 있는 경우에만 검증된 원본을 연구 기록장에 추가.
3. 향후 여러 날짜의 표본을 모아 결측/시간대/시장상황/선정 편향을 확인. 먼저 실제 실패 실행까지 포함한 전체 실행 목록이 필요.
4. SEC 원문, Float, 호가·스프레드/슬리피지/거래정지 확인 전 A/B 등급 및 실거래 승인 금지.

**운영 main, /api/radar, 사이트, 기존 알림, Stage24 20거래일 고정 시험, 별도 5거래일 시험 및 실제 주문 기능을 이 단계에서 수정하지 않음.**
